/* 여러 화면이 같이 쓰는 부품: 폴더·파일 고르기, 경로 입력칸, 컬럼 바로가기 칩 */
(function () {
  "use strict";
  const D = window.D;
  const h = D.h;

  /* 폴더/파일 고르기 창. mode: "folder" | "file". 고르면 경로를, 닫으면 null을 돌려준다. */
  D.browse = function ({ mode = "folder", start = "", title } = {}) {
    return new Promise((resolve) => {
      let picked = false;
      const pathInput = h("input", { class: "input grow", value: start || "", placeholder: "경로를 입력하고 Enter" });
      const list = h("div", { class: "browser-list" }, D.loading());
      const drives = h("div", { class: "row" });
      const detect = h("div");
      let current = null;
      const okBtn = h("button", { class: "btn primary", onclick: () => { if (current) finish(current.path); } }, mode === "folder" ? "이 폴더 열기" : "취소");
      const finish = (v) => { picked = true; m.close(); resolve(v); };

      async function load(path) {
        D.clear(list).appendChild(D.loading());
        try {
          const r = await D.api("/api/browse", { params: { path } });
          current = r;
          pathInput.value = r.path;
          D.clear(drives);
          for (const d of r.drives || []) drives.appendChild(h("span", { class: "chip" + (r.path.toUpperCase().startsWith(d.toUpperCase()) ? " on" : ""), onclick: () => load(d) }, d));
          D.clear(list);
          if (r.parent) list.appendChild(h("div", { class: "browser-item", onclick: () => load(r.parent) }, D.icon("up"), "상위 폴더"));
          for (const d of r.dirs) list.appendChild(h("div", { class: "browser-item", ondblclick: () => mode === "folder" && finish(d.path), onclick: () => load(d.path) }, D.icon("folder"), d.name));
          for (const fl of r.files) {
            list.appendChild(h("div", { class: "browser-item file" + (mode === "file" ? " pick" : ""), onclick: mode === "file" ? () => finish(fl.path) : null },
              D.icon("file"), fl.name, h("span", { class: "size" }, D.fmt.bytes(fl.size))));
          }
          if (!r.dirs.length && !r.files.length) list.appendChild(h("div", { class: "browser-item file" }, "비어 있습니다 (표 파일·하위 폴더 없음)"));
          D.clear(detect);
          if (mode === "folder" && (r.ambiguous || []).length) {
            detect.appendChild(h("div", { class: "callout info mt8" }, D.icon("info"), h("div", { class: "grow" },
              h("div", { class: "bold" }, "이 폴더 아래에 대회가 여러 개 있습니다. 하나를 고르세요."),
              h("div", { class: "row mt8", style: { gap: "6px" } }, r.ambiguous.map((d) => h("span", { class: "chip", onclick: () => load(d) }, rel(d, r.path) || d))))));
            okBtn.disabled = true;
          } else if (mode === "folder") {
            const dt = r.detected || {};
            const any = dt.train || dt.test || dt.sample_submission;
            detect.appendChild(any
              ? h("dl", { class: "detect" },
                h("dt", null, "train"), h("dd", null, rel(dt.train, r.path) || "못 찾음"),
                h("dt", null, "test"), h("dd", null, rel(dt.test, r.path) || "없음"),
                h("dt", null, "제출 양식"), h("dd", null, rel(dt.sample_submission, r.path) || "없음"))
              : h("div", { class: "small muted mt8" }, "이 폴더에서는 train 파일을 찾지 못했습니다. 대회 데이터가 든 폴더로 들어가세요."));
            okBtn.disabled = !dt.train;
          }
        } catch (e) {
          D.clear(list).appendChild(h("div", { class: "browser-item file" }, e.message));
        }
      }
      const rel = (p, base) => (p ? (p.startsWith(base) ? p.slice(base.length).replace(/^[\\/]/, "") : p) : null);
      pathInput.addEventListener("keydown", (e) => { if (e.key === "Enter") load(pathInput.value); });
      const m = D.modal({
        title: title || (mode === "folder" ? "대회 폴더 고르기" : "파일 고르기"), wide: true,
        body: h("div", { class: "col" }, h("div", { class: "row" }, pathInput, h("button", { class: "btn", onclick: () => load(pathInput.value) }, "이동")),
          drives, list, detect,
          h("div", { class: "small muted" }, mode === "folder" ? "폴더를 누르면 들어갑니다. train 파일이 있는 폴더에서 '이 폴더 열기'를 누르세요." : "csv, parquet, xlsx 등 표 파일만 보입니다.")),
        footer: mode === "folder" ? [h("button", { class: "btn", onclick: () => finish(null) }, "취소"), okBtn] : [h("button", { class: "btn", onclick: () => finish(null) }, "취소")],
        onClose: () => { if (!picked) resolve(null); },
      });
      load(start);
    });
  };

  /* 경로 입력칸 + 찾아보기 */
  D.pathField = function (value, { mode = "file", placeholder = "파일 경로", start, onChange } = {}) {
    const inp = h("input", { class: "input grow", value: value || "", placeholder, onchange: () => onChange && onChange(inp.value) });
    const wrap = h("div", { class: "row", style: { flexWrap: "nowrap" } }, inp,
      h("button", { class: "btn", type: "button", onclick: async () => {
        const base = inp.value || start || (D.project() ? D.project().root : "");
        const p = await D.browse({ mode, start: base });
        if (p) { inp.value = p; if (onChange) onChange(p); }
      } }, "찾아보기"));
    wrap.input = inp;
    Object.defineProperty(wrap, "value", { get: () => inp.value.trim(), set: (v) => (inp.value = v) });
    return wrap;
  };

  D.colChip = (name) => h("span", { class: "chip", title: name + " 컬럼 보기", onclick: (e) => { e.stopPropagation(); D.go("columns", { name }); } }, name);

  /* 대회 폴더 열기 (작업 진행률 표시 후 개요로) */
  D.openProject = async function (path) {
    if (!path) return;
    const r = await D.api("/api/open", { body: { path } });
    try {
      await D.runJob(r.job);
    } catch (e) {
      await D.refreshState();  // 열지 못한 폴더도 기억해서 시작 화면에서 파일을 고를 수 있게
      D.render();
      throw e;
    }
    await D.refreshState();
    D.navBadges = {};
    const notes = (D.project().notices || []).join(" ");
    D.toast("대회 폴더를 열었습니다." + (notes ? " " + notes : ""), notes ? "warn" : "ok", notes ? 7000 : 3200);
    D.go("overview");
  };

  /* 공통: 프로필 준비 (첫 컬럼 분석) */
  D.ensureProfiles = () => D.ensure("/api/columns");

  /* 점검 결과로 사이드바 배지 갱신 */
  D.updateCheckBadge = function (counts) {
    if (!counts) return;
    if (counts.danger) D.navBadges.checks = { kind: "danger", text: counts.danger };
    else if (counts.warn) D.navBadges.checks = { kind: "warn", text: counts.warn };
    else delete D.navBadges.checks;
    D.renderSidebar();
  };

  D.metricLabel = () => { const p = D.project(); return (p && p.metric_info && p.metric_info.label) || (p && p.settings.metric) || "점수"; };
  D.higherBetter = () => { const p = D.project(); return !p || !p.metric_info || p.metric_info.higher_is_better; };
})();
