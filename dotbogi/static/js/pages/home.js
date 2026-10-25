/* 시작 화면: 노션 페이지처럼 제목 아래 블록을 차례로 (폴더 열기, 최근 대회, 할 수 있는 일, 단축키) */
(function () {
  "use strict";
  const D = window.D;
  const T = D.t;
  const h = D.h;

  D.pages.home = {
    title: T("시작"),
    headTitle: T("돋보기"),
    logoIcon: true,
    subtitle: T("캐글·데이콘 정형 데이터 대회 분석. 함정을 먼저 찾고, 실험과 리더보드를 한 곳에서 비교하고, 제출 파일을 올리기 전에 검사합니다."),
    async render(root) {
      const st = D.state || {};
      const proj = D.project();
      const page = h("div", { class: "home" });
      root.appendChild(page);

      const loadJob = (st.jobs || []).find((j) => j.kind === "load");
      if (loadJob) {
        page.appendChild(h("div", { class: "callout" }, h("span", { class: "spinner" }),
          h("div", { class: "grow" }, h("div", { class: "bold" }, T("데이터를 불러오는 중입니다")),
            h("div", { class: "muted small" }, T("큰 CSV는 처음 한 번만 오래 걸리고, 다음부터는 저장해 둔 사본으로 빠르게 엽니다.")))));
        D.runJob(loadJob).then(() => D.refreshState()).then(() => D.go("overview")).catch(D.fail);
      }

      if (proj && !proj.loaded && proj.load_error) {
        const s = proj.settings;
        const abs = (p) => (!p ? "" : /^([a-zA-Z]:[\\/]|\/)/.test(p) ? p : proj.root.replace(/[\\/]$/, "") + "\\" + p);
        const tr = D.pathField(abs(s.files.train), { placeholder: T("train 파일"), start: proj.root });
        const te = D.pathField(abs(s.files.test), { placeholder: T("test 파일 (없으면 비워 두기)"), start: proj.root });
        const ss = D.pathField(abs(s.files.sample_submission), { placeholder: T("sample_submission 파일 (없으면 비워 두기)"), start: proj.root });
        const go = h("button", { class: "btn primary", onclick: () => D.busy(go, async () => {
          if (!tr.value) throw new Error(T("train 파일을 고르세요."));
          const r = await D.api("/api/files", { body: { train: tr.value, test: te.value, sample_submission: ss.value } });
          await D.runJob(r.job); await D.refreshState(); D.toast(T("대회 폴더를 열었습니다.")); D.go("overview");
        }) }, T("이 파일들로 열기"));
        page.appendChild(D.card(T("이 폴더를 열지 못했습니다"), { hint: proj.root },
          D.callout("warn", proj.load_error),
          h("div", { class: "col mt12" }, h("div", { class: "small muted" }, T("파일을 직접 고르면 그대로 엽니다.")), tr, te, ss),
          h("div", { class: "row mt12" }, h("span", { class: "grow" }), go)));
      }

      if (proj && proj.loaded) {
        page.appendChild(h("div", { class: "callout info" }, D.icon("overview"),
          h("div", { class: "grow" }, T("지금 "), h("b", null, proj.settings.name || proj.root), T(" 대회가 열려 있습니다.")),
          h("button", { class: "btn sm", onclick: () => D.go("overview") }, T("개요 보기"))));
      }

      // 폴더 열기
      const input = h("input", { class: "input", placeholder: T("대회 폴더 경로를 붙여 넣으세요"), value: "", "aria-label": T("대회 폴더 경로") });
      const openBtn = h("button", { class: "btn primary lg", onclick: () => D.busy(openBtn, () => {
        if (!input.value.trim()) throw new Error(T("폴더 경로를 적거나 '찾아보기'로 고르세요."));
        return D.openProject(input.value.trim());
      }) }, T("열기"));
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") openBtn.click(); });
      const browse = async () => {
        const p = await D.browse({ mode: "folder", start: input.value || (proj ? proj.root : (st.recent && st.recent[0] ? st.recent[0].path : "")) });
        if (p) { input.value = p; openBtn.click(); }
      };
      page.appendChild(h("h2", null, T("대회 폴더 열기")));
      page.appendChild(h("div", { class: "open-box" }, input, h("button", { class: "btn lg", onclick: browse }, D.icon("folder"), T("찾아보기")), openBtn));
      page.appendChild(h("p", { class: "small muted" }, T("train·test·sample_submission이 든 폴더를 고르면 타깃·ID·과제를 추론합니다. 결과와 실험 기록은 그 폴더의 "),
        h("code", null, ".dotbogi"), T(" 안에 저장됩니다.")));

      // 최근
      const recent = st.recent || [];
      page.appendChild(h("h2", null, T("최근 연 대회")));
      const list = h("div", { class: "recent-list" });
      if (!recent.length) list.appendChild(h("div", { class: "recent-empty" }, T("아직 없습니다. 위에서 대회 폴더를 열면 여기에 쌓입니다.")));
      for (const r of recent) {
        list.appendChild(h("div", { class: "recent-item", role: "button", title: r.path, onclick: () => D.busy(null, () => D.openProject(r.path)) },
          h("span", { class: "ri" }, D.icon("folder")),
          h("span", { class: "name" }, r.name),
          h("span", { class: "path grow" }, r.path),
          h("span", { class: "muted small nowrap" }, r.opened_at || ""),
          h("button", { class: "icon-btn", title: T("목록에서 빼기"), onclick: async (e) => {
            e.stopPropagation();
            await D.api("/api/recent/forget", { body: { path: r.path } }).catch(D.fail);
            await D.refreshState(); D.render();
          } }, D.icon("x"))));
      }
      page.appendChild(list);

      const feats = [
        ["shield", T("함정 먼저 찾기"), T("누수 의심, train-test 겹침, 시간·그룹 구조, 새 범주, 지저분한 값까지 15가지를 점검합니다.")],
        ["versus", T("train과 test 비교"), T("분포 차이를 수치로 줄 세우고, 적대적 검증으로 둘을 가르는 컬럼을 보여줍니다.")],
        ["layers", T("검증 방법 추천"), T("데이터 구조에 맞는 K-Fold를 이유와 함께 추천하고 폴드 파일을 만듭니다.")],
        ["flask", T("CV와 리더보드 한 곳에"), T("실험 점수와 LB를 비교하고, LB 차이가 우연인지 알려주고, 최종 제출을 골라줍니다.")],
        ["merge", T("OOF 앙상블"), T("OOF로 가중치를 찾고, 다른 폴드로 검증한 정직한 점수를 보여줍니다.")],
        ["upload", T("제출 전 검사"), T("컬럼·행·ID·확률/라벨·인코딩 실수를 잡고, 안전하게 고친 파일을 만듭니다.")],
      ];
      page.appendChild(h("h2", null, T("할 수 있는 일")));
      page.appendChild(h("div", { class: "gallery" },
        feats.map(([ic, t, d]) => h("div", { class: "gcard" }, h("div", { class: "fi" }, D.icon(ic)), h("b", null, t), h("span", null, d)))));

      page.appendChild(h("h2", null, T("단축키")));
      page.appendChild(h("div", { class: "keys" },
        h("kbd", null, "Ctrl+O"), h("span", null, T("대회 폴더 열기")),
        h("kbd", null, "Ctrl+1 ~ 0"), h("span", null, T("왼쪽 메뉴 순서대로 화면 이동")),
        h("kbd", null, "Ctrl+B"), h("span", null, T("사이드바 닫기·열기")),
        h("kbd", null, "Esc"), h("span", null, T("대화 상자 닫기"))));
    },
  };
})();
