/* 설정: 데이터 파일, 대회 정보, 사용자 지표, 보고서, 저장 위치 */
(function () {
  "use strict";
  const D = window.D;
  const T = D.t;
  const h = D.h;

  const METRIC_TEMPLATE = T("# 대회 평가식을 그대로 옮겨 적으세요. 돋보기가 CV·앙상블·LB 흔들림 계산에 씁니다.\nimport numpy as np\n\nNAME = \"대회 점수\"          # 화면에 보일 이름\nHIGHER_IS_BETTER = False    # 낮을수록 좋으면 False\n\ndef score(y_true, y_pred):\n    # y_true: 이진분류 0/1, 다중분류 0..K-1, 회귀 값\n    # y_pred: 이진분류 양성 확률, 다중분류 (행, 클래스) 확률, 회귀 예측값\n    from sklearn.metrics import roc_auc_score\n    auc = roc_auc_score(y_true, y_pred)\n    brier = np.mean((y_pred - y_true) ** 2)\n    return 0.5 * (1 - auc) + 0.5 * brier\n");

  /* 대회와 상관없는 앱 설정: 새 버전 확인 */
  function appCard() {
    const prefs = (D.state && D.state.prefs) || {};
    const res = h("span", { class: "small muted" });
    const show = (r) => {
      if (!r) return;
      if (r.error) res.textContent = r.error;
      else if (r.enabled === false) res.textContent = T("새 버전 확인이 꺼져 있습니다.");
      else if (r.newer) { D.clear(res).appendChild(h("span", null, T("새 버전 {0}이(가) 있습니다. ", r.latest), h("a", { href: r.url, target: "_blank", rel: "noopener" }, T("릴리스 페이지 열기")))); }
      else res.textContent = T("지금 버전 {0}이(가) 최신입니다.", r.current);
    };
    const cb = h("input", { type: "checkbox", checked: prefs.update_check !== false, onchange: async () => {
      try { D.state.prefs = await D.api("/api/prefs", { body: { update_check: cb.checked } }); if (cb.checked) show(await D.checkUpdate()); else { D.update = null; D.renderSidebar(); show({ enabled: false }); } }
      catch (e) { D.fail(e); }
    } });
    const now = h("button", { class: "btn sm", onclick: () => D.busy(now, async () => show(await D.checkUpdate(true))) }, D.icon("refresh"), T("지금 확인"));
    if (D.update) show(D.update);
    const langSel = h("select", { class: "select sm", "aria-label": "Language / 화면 언어", onchange: () => D.setLang(langSel.value) },
      h("option", { value: "ko", selected: D.lang === "ko" }, "한국어"), h("option", { value: "en", selected: D.lang === "en" }, "English"));
    return D.card(T("앱 설정"), { hint: T("모든 대회에 함께 적용됩니다") },
      h("div", { class: "row" }, h("span", { class: "small muted" }, "화면 언어 · Language"), langSel),
      h("div", { class: "row mt12" }, h("label", { class: "check" }, cb, T("새 버전이 나오면 알려 주기")), now, res),
      h("div", { class: "small muted mt8" }, T("하루에 한 번 GitHub에 최신 버전 번호만 물어봅니다. 데이터나 사용 기록은 보내지 않습니다.")));
  }

  D.pages.settings = {
    title: T("설정"),
    subtitle: () => (D.project() ? D.project().root : ""),
    async render(root) {
      const proj = D.project();
      const s = proj.settings;
      const comp = s.competition || {};

      // 데이터 파일
      const tr = D.pathField(abs(s.files.train), { placeholder: T("train 파일"), start: proj.root });
      const te = D.pathField(abs(s.files.test), { placeholder: T("test 파일 (없으면 비워 두기)"), start: proj.root });
      const ss = D.pathField(abs(s.files.sample_submission), { placeholder: T("sample_submission 파일 (없으면 비워 두기)"), start: proj.root });
      const applyBtn = h("button", { class: "btn primary", onclick: () => D.busy(applyBtn, async () => {
        const r = await D.api("/api/files", { body: { train: tr.value, test: te.value, sample_submission: ss.value } });
        await D.runJob(r.job); await D.refreshState(); D.navBadges = {}; D.toast(T("파일을 다시 불러왔습니다. 타깃·ID 추론도 새로 했습니다.")); D.render();
      }) }, T("이 파일들로 다시 불러오기"));
      const reloadBtn = h("button", { class: "btn", onclick: () => D.busy(reloadBtn, async () => {
        const r = await D.api("/api/reload", { body: {} });
        await D.runJob(r.job); await D.refreshState(); D.navBadges = {}; D.toast(T("파일을 다시 읽었습니다.")); D.render();
      }) }, D.icon("refresh"), T("디스크에서 다시 읽기"));
      root.appendChild(appCard());
      root.appendChild(D.card(T("데이터 파일"), { hint: T("파일을 바꾸면 타깃·ID·지표를 다시 추론합니다") },
        h("div", { class: "col" }, field("train", tr), field("test", te), field(T("제출 양식 (sample_submission)"), ss)),
        h("div", { class: "row mt12" }, h("span", { class: "grow small muted" }, T("같은 파일 내용이 바뀌었으면 '디스크에서 다시 읽기'를 누르세요. 큰 CSV는 처음 읽을 때 parquet 사본을 만들어 두고 다음부터 빨리 엽니다.")), reloadBtn, applyBtn)));

      // 대회 정보
      const name = h("input", { class: "input", value: s.name || "" });
      let platform = comp.platform || "other";
      const url = h("input", { class: "input", value: comp.url || "", placeholder: "https://www.kaggle.com/competitions/titanic" });
      const share = h("input", { class: "input", value: comp.public_share ? Math.round(comp.public_share * 1000) / 10 : "", placeholder: T("예: 30"), inputmode: "decimal" });
      const limit = h("input", { class: "input", value: comp.daily_limit ?? "", placeholder: T("예: 5"), inputmode: "numeric" });
      const picks = h("input", { class: "input", value: comp.final_picks ?? 2, inputmode: "numeric" });
      const end = h("input", { class: "input", type: "date", value: comp.end_date || "" });
      const rules = h("textarea", { class: "textarea", rows: "3", placeholder: T("예: 외부 데이터 금지, test로 전처리 fit 금지, 하루 3회") }, comp.rules_note || "");
      const platSeg = D.seg(Object.entries(D.state.platforms).map(([k, v]) => [k, v.label]), platform, (v) => {
        platform = v;
        const d = D.state.platforms[v];
        if (d && !limit.value && d.daily_limit) limit.value = d.daily_limit;
      });
      const saveComp = h("button", { class: "btn primary", onclick: () => D.busy(saveComp, async () => {
        const n = (el) => (el.value.trim() === "" ? null : Number(el.value));
        for (const el of [share, limit, picks]) if (el.value.trim() && Number.isNaN(Number(el.value))) throw new Error(T("숫자 칸에는 숫자를 적으세요."));
        if (share.value.trim() && (n(share) <= 0 || n(share) > 100)) throw new Error(T("Public 비율은 0~100 사이로 적으세요."));
        await D.api("/api/settings", { body: { name: name.value.trim() || s.name, competition: { platform, url: url.value.trim(), public_share: n(share),
          daily_limit: n(limit), final_picks: n(picks) || 2, end_date: end.value || null, rules_note: rules.value } } });
        await D.refreshState(); D.toast(T("대회 정보를 저장했습니다."));
      }) }, T("저장"));
      root.appendChild(D.card(T("대회 정보"), { hint: T("실험 화면의 제출 횟수·LB 흔들림·최종 선택 안내에 쓰입니다") },
        h("div", { class: "grid g2", style: { gap: "12px" } },
          field(T("이름"), name), field(T("플랫폼"), platSeg),
          field(T("대회 주소"), url, T("Kaggle이면 제출 기록 가져오기에 씁니다")), field(T("Public LB 비율 (%)"), share, T("대회 안내에 'Public은 test의 30%'처럼 적혀 있습니다")),
          field(T("하루 제출 한도"), limit), field(T("최종 제출로 고를 수 있는 수"), picks),
          field(T("마감일"), end, T("사이드바에 D-day로 보입니다")), field(T("규칙 메모"), rules)),
        h("div", { class: "row mt12" }, h("span", { class: "grow" }), saveComp)));

      // 사용자 지표
      const cm = s.custom_metric || {};
      const mPath = D.pathField(cm.path ? abs(cm.path) : "", { placeholder: T("metric.py 경로"), start: proj.root });
      const mHib = h("input", { type: "checkbox", checked: cm.higher_is_better !== false });
      const mNeeds = D.select([["proba", T("확률")], ["label", T("라벨")], ["value", T("값 (회귀)")]], cm.needs || (s.task === "regression" ? "value" : "proba"), null);
      const mLabel = h("input", { class: "input", value: cm.label || "", placeholder: T("파일의 NAME을 쓰려면 비워 두기") });
      const mSave = h("button", { class: "btn primary", onclick: () => D.busy(mSave, async () => {
        if (!mPath.value) throw new Error(T("지표 파일 경로를 적으세요."));
        await D.api("/api/settings", { body: { custom_metric: { path: mPath.value, higher_is_better: mHib.checked, needs: mNeeds.value, label: mLabel.value } } });
        await D.refreshState(); D.toast(T("사용자 지표를 등록하고 평가 지표로 정했습니다.")); D.render();
      }) }, T("등록하고 쓰기"));
      const mOff = cm.path ? h("button", { class: "btn", onclick: () => D.busy(mOff, async () => {
        await D.api("/api/settings", { body: { custom_metric: null } }); await D.refreshState(); D.toast(T("사용자 지표를 껐습니다.")); D.render();
      }) }, T("끄기")) : null;
      root.appendChild(D.card(T("대회 전용 평가식"), { hint: T("데이콘 복합 지표처럼 목록에 없는 계산식") },
        proj.custom_metric_error ? D.callout("danger", T("지표 파일을 불러오지 못했습니다: ") + proj.custom_metric_error) : null,
        s.custom_metric ? D.callout("ok", T("지금 '{0}'를 쓰고 있습니다.", (proj.metric_info || {}).label || T("사용자 지표"))) : null,
        h("div", { class: "grid g2 mt8", style: { gap: "12px" } }, field(T("지표 파일 (.py)"), mPath), field(T("화면 이름"), mLabel),
          field(T("예측 형태"), mNeeds), field(T("방향"), h("label", { class: "check" }, mHib, T("높을수록 좋음 (파일에 HIGHER_IS_BETTER가 있으면 그것을 따름)")))),
        h("div", { class: "row mt12" }, h("span", { class: "grow small muted" }, T("파일은 score(y_true, y_pred) 함수 하나면 됩니다. 등록할 때 예시 데이터로 한 번 불러 확인하고, OOF가 있는 기존 실험은 새 지표로 다시 채점해 보여 줍니다. 기본 지표 중 Brier, ECE도 있습니다.")), mOff, mSave),
        h("details", { class: "mt8" }, h("summary", { class: "small", style: { cursor: "pointer" } }, T("파일 예시 (데이콘 AUC+Brier 복합 지표)")), h("div", { class: "mt8" }, D.codeBlock(METRIC_TEMPLATE)))));

      // 보고서
      const repBtn = h("button", { class: "btn primary", onclick: () => D.busy(repBtn, async () => {
        const r = await D.api("/api/report", { body: {} });
        const res = await D.runJob(r.job);
        repOut.replaceChildren(D.callout("ok", h("b", null, T("보고서를 만들었습니다. ")), h("code", null, res.path), ` (${D.fmt.bytes(res.bytes)})`,
          h("div", { class: "mt8" }, h("a", { class: "btn sm", href: `/api/download?path=${encodeURIComponent(res.path)}&t=${encodeURIComponent(D.token)}` }, D.icon("download"), T("내려받기")))));
      }) }, D.icon("report"), T("HTML 보고서 만들기"));
      const repOut = h("div", { class: "mt8" });
      root.appendChild(D.card(T("보고서 내보내기"), { hint: T("팀원 공유·기록용") },
        h("div", { class: "row" }, h("span", { class: "grow small muted" }, T("개요·데이터 점검·컬럼·train vs test·탐색·검증 추천·실험 대장을 HTML 파일 하나로 저장합니다. 원본 데이터는 넣지 않아 가볍고, 인터넷 없이 열립니다.")), repBtn), repOut));

      // 정보
      const ex = s.excluded || [];
      const kinds = Object.entries(s.kinds || {});
      root.appendChild(D.card(T("저장 위치와 상태"), null, h("dl", { class: "kv" },
        h("dt", null, T("대회 폴더")), h("dd", null, h("code", null, proj.root)),
        h("dt", null, T("기록 저장 위치")), h("dd", null, h("code", null, proj.store)),
        h("dt", null, T("모델 엔진")), h("dd", null, D.state.lightgbm ? "LightGBM" : T("scikit-learn HistGradientBoosting (LightGBM을 설치하면 더 빠름)")),
        h("dt", null, T("버전")), h("dd", null, D.state.version),
        h("dt", null, T("모델에서 뺀 컬럼")), h("dd", null, ex.length ? h("div", { class: "row", style: { gap: "6px" } }, ex.map((c) => h("span", { class: "chip on", title: T("다시 넣기"), onclick: async () => {
          await D.api("/api/settings", { body: { excluded: ex.filter((x) => x !== c) } }).catch(D.fail); await D.refreshState(); D.render(); } }, c, h("span", { class: "x" }, "×")))) : T("없음")),
        h("dt", null, T("직접 바꾼 종류")), h("dd", null, kinds.length ? kinds.map(([k, v]) => `${k} → ${D.KIND_LABEL[v] || v}`).join(", ") : T("없음")))));

      function abs(p) {
        if (!p) return "";
        if (/^([a-zA-Z]:[\\/]|\/)/.test(p)) return p;
        return proj.root.replace(/[\\/]$/, "") + (proj.root.includes("\\") ? "\\" : "/") + p;
      }
    },
  };

  function field(label, control, help) {
    return h("div", { class: "field" }, h("label", null, label), control, help ? h("div", { class: "help" }, help) : null);
  }
})();
