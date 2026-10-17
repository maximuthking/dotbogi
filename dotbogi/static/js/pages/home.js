/* 시작 화면: IDE 시작 페이지처럼 왼쪽은 시작하기, 오른쪽은 최근 대회 */
(function () {
  "use strict";
  const D = window.D;
  const h = D.h;

  D.pages.home = {
    title: "시작",
    async render(root) {
      const st = D.state || {};
      const proj = D.project();
      const page = h("div", { class: "home" });
      root.appendChild(page);

      page.appendChild(h("div", { class: "home-hero" }, h("div", { class: "brand-mark" }, D.logo()),
        h("div", null, h("h1", null, "돋보기"),
          h("p", null, "캐글·데이콘 정형 데이터 대회 분석. 함정을 먼저 찾고, 실험과 리더보드를 한 곳에서 비교하고, 제출 파일을 올리기 전에 검사합니다."))));

      const loadJob = (st.jobs || []).find((j) => j.kind === "load");
      if (loadJob) {
        const box = h("div", { class: "col" }, h("div", { class: "row" }, h("span", { class: "spinner" }), h("b", null, "데이터를 불러오는 중입니다")),
          h("div", { class: "muted small" }, "큰 CSV는 처음 한 번만 오래 걸리고, 다음부터는 저장해 둔 사본으로 빠르게 엽니다."));
        page.appendChild(D.card(null, null, box));
        D.runJob(loadJob).then(() => D.refreshState()).then(() => D.go("overview")).catch(D.fail);
      }

      if (proj && !proj.loaded && proj.load_error) {
        const s = proj.settings;
        const abs = (p) => (!p ? "" : /^([a-zA-Z]:[\\/]|\/)/.test(p) ? p : proj.root.replace(/[\\/]$/, "") + "\\" + p);
        const tr = D.pathField(abs(s.files.train), { placeholder: "train 파일", start: proj.root });
        const te = D.pathField(abs(s.files.test), { placeholder: "test 파일 (없으면 비워 두기)", start: proj.root });
        const ss = D.pathField(abs(s.files.sample_submission), { placeholder: "sample_submission 파일 (없으면 비워 두기)", start: proj.root });
        const go = h("button", { class: "btn primary", onclick: () => D.busy(go, async () => {
          if (!tr.value) throw new Error("train 파일을 고르세요.");
          const r = await D.api("/api/files", { body: { train: tr.value, test: te.value, sample_submission: ss.value } });
          await D.runJob(r.job); await D.refreshState(); D.toast("대회 폴더를 열었습니다."); D.go("overview");
        }) }, "이 파일들로 열기");
        page.appendChild(D.card("이 폴더를 열지 못했습니다", { hint: proj.root },
          D.callout("warn", proj.load_error),
          h("div", { class: "col mt12" }, h("div", { class: "small muted" }, "파일을 직접 고르면 그대로 엽니다."), tr, te, ss),
          h("div", { class: "row mt12" }, h("span", { class: "grow" }), go)));
      }

      // 왼쪽: 시작하기
      const input = h("input", { class: "input", placeholder: "대회 폴더 경로 붙여 넣기", value: "", "aria-label": "대회 폴더 경로" });
      const openBtn = h("button", { class: "btn primary", onclick: () => D.busy(openBtn, () => {
        if (!input.value.trim()) throw new Error("폴더 경로를 적거나 '찾아보기'로 고르세요.");
        return D.openProject(input.value.trim());
      }) }, "열기");
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") openBtn.click(); });
      const browse = async () => {
        const p = await D.browse({ mode: "folder", start: input.value || (proj ? proj.root : (st.recent && st.recent[0] ? st.recent[0].path : "")) });
        if (p) { input.value = p; openBtn.click(); }
      };
      const action = (icon, title, desc, key, onclick) => h("button", { class: "action", onclick },
        h("span", { class: "ai" }, D.icon(icon)), h("span", null, h("b", null, title), h("span", { class: "d" }, desc)), key ? h("kbd", null, key) : null);

      const left = h("div", null);
      const start = h("div", { class: "home-sec" }, h("h2", null, "시작하기"));
      if (proj && proj.loaded) {
        start.appendChild(action("overview", "개요로 돌아가기", proj.settings.name || proj.root, "Ctrl+2", () => D.go("overview")));
      }
      start.appendChild(action("folder", "대회 폴더 찾아보기", "train·test·sample_submission이 든 폴더", "Ctrl+O", browse));
      start.appendChild(h("div", { class: "open-box" }, input,
        h("button", { class: "btn", onclick: browse }, "찾아보기"), openBtn));
      start.appendChild(h("div", { class: "small muted mt8" }, "파일 이름으로 train, test, 제출 양식을 찾고 타깃·ID·과제를 추론합니다. 결과와 실험 기록은 그 폴더의 ",
        h("code", null, ".dotbogi"), " 안에 저장됩니다."));
      left.appendChild(start);

      const keys = h("div", { class: "home-sec" }, h("h2", null, "단축키"),
        h("dl", { class: "kv" },
          h("dt", null, h("kbd", null, "Ctrl+O")), h("dd", null, "대회 폴더 열기"),
          h("dt", null, h("kbd", null, "Ctrl+1 ~ 0")), h("dd", null, "왼쪽 메뉴 순서대로 화면 이동"),
          h("dt", null, h("kbd", null, "Ctrl+B")), h("dd", null, "메뉴 접기·펴기"),
          h("dt", null, h("kbd", null, "Esc")), h("dd", null, "대화 상자 닫기")));
      left.appendChild(keys);

      // 오른쪽: 최근 대회
      const recent = st.recent || [];
      const right = h("div", { class: "home-sec" }, h("h2", null, "최근 연 대회"));
      const list = h("div", { class: "recent-list" });
      if (!recent.length) list.appendChild(h("div", { class: "recent-empty" }, "아직 연 대회가 없습니다. 왼쪽에서 대회 폴더를 고르면 여기에 쌓입니다."));
      for (const r of recent) {
        list.appendChild(h("div", { class: "recent-item", role: "button", title: r.path, onclick: () => D.busy(null, () => D.openProject(r.path)) },
          h("span", { class: "ri" }, D.icon("folder")),
          h("div", { class: "grow" }, h("div", { class: "bold ellipsis" }, r.name), h("div", { class: "path" }, r.path)),
          h("span", { class: "muted small nowrap" }, r.opened_at || ""),
          h("button", { class: "icon-btn", title: "목록에서 빼기", onclick: async (e) => {
            e.stopPropagation();
            await D.api("/api/recent/forget", { body: { path: r.path } }).catch(D.fail);
            await D.refreshState(); D.render();
          } }, D.icon("x"))));
      }
      right.appendChild(list);
      page.appendChild(h("div", { class: "home-cols" }, left, right));

      const feats = [
        ["shield", "함정 먼저 찾기", "누수 의심, train-test 겹침, 시간·그룹 구조, 새 범주, 지저분한 값까지 15가지를 점검합니다."],
        ["versus", "train과 test 비교", "분포 차이를 수치로 줄 세우고, 적대적 검증으로 둘을 가르는 컬럼을 보여줍니다."],
        ["layers", "검증 방법 추천", "데이터 구조에 맞는 K-Fold를 이유와 함께 추천하고 폴드 파일을 만듭니다."],
        ["flask", "CV와 리더보드 한 곳에", "실험 점수와 LB를 비교하고, LB 차이가 우연인지 알려주고, 최종 제출을 골라줍니다."],
        ["merge", "OOF 앙상블", "OOF로 가중치를 찾고, 다른 폴드로 검증한 정직한 점수를 보여줍니다."],
        ["upload", "제출 전 검사", "컬럼·행·ID·확률/라벨·인코딩 실수를 잡고, 안전하게 고친 파일을 만듭니다."],
      ];
      page.appendChild(h("div", { class: "home-sec" }, h("h2", null, "할 수 있는 일"),
        h("div", { class: "feature-list" },
          feats.map(([ic, t, d]) => h("div", { class: "feature" }, h("div", { class: "fi" }, D.icon(ic)), h("div", null, h("b", null, t), h("span", null, d)))))));
    },
  };
})();
