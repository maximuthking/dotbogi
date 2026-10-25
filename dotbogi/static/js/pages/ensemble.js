/* 앙상블: OOF가 있는 실험을 골라 가중치 찾기, 정직한 점수, 저장 */
(function () {
  "use strict";
  const D = window.D;
  const T = D.t;
  const h = D.h;
  const f = D.fmt;

  D.pages.ensemble = {
    title: T("앙상블"),
    subtitle: T("OOF로 섞는 비율 찾기"),
    async render(root, params, ctx) {
      root.appendChild(D.card(null, null, D.loading()));
      const data = await D.api("/api/experiments");
      if (!ctx.isCurrent()) return;
      D.clear(root);
      const cand = data.experiments.filter((e) => e.has_oof && !e.metric_mismatch);
      if (cand.length < 2) {
        root.appendChild(D.card(null, null, D.empty(T("OOF가 있는 실험이 2개 이상 필요합니다"),
          T("지금 {0}개입니다. 검증 설계에서 기본 모델을 돌리거나, 학습 스크립트에서 dotbogi.log(oof=...)로 기록하면 OOF가 붙습니다.", cand.length), "merge",
          h("button", { class: "btn", onclick: () => D.go("experiments") }, T("실험 대장으로")))));
        return;
      }
      const hib = data.higher_is_better;
      const chosen = new Set(cand.slice().sort((a, b) => (hib ? (b.cv ?? -Infinity) - (a.cv ?? -Infinity) : (a.cv ?? Infinity) - (b.cv ?? Infinity))).slice(0, Math.min(5, cand.length)).map((e) => e.id));
      let method = "hill";
      let useRank = false;
      const rankable = ["auc", "macro_auc", "ap"].includes(D.settings().metric);
      const list = D.table({
        columns: [
          { key: "pick", label: "", sortable: false, width: "34px", render: (e) => h("input", { type: "checkbox", checked: chosen.has(e.id), onchange: (ev) => { if (ev.target.checked) chosen.add(e.id); else chosen.delete(e.id); } }) },
          { key: "name", label: T("실험"), render: (e) => h("span", { class: "bold" }, e.name) },
          { key: "cv", label: "CV", num: true, render: (e) => f.score(e.cv) },
          { key: "lb_public", label: "Public", num: true, render: (e) => f.score(e.lb_public) },
          { key: "has_test", label: T("test 예측"), render: (e) => (e.has_test ? h("span", { class: "badge ok" }, T("있음")) : h("span", { class: "badge warn", title: T("제출 파일을 만들 수 없습니다") }, T("없음"))) },
        ],
        rows: cand, compact: true, sort: { key: "cv", asc: !hib }, maxHeight: "320px",
      });
      const out = h("div");
      const runBtn = h("button", { class: "btn primary", onclick: () => D.busy(runBtn, run) }, D.icon("play"), T("가중치 찾기"));
      root.appendChild(D.card(T("섞을 실험 고르기"), { hint: T("같은 폴드로 만든 OOF끼리 섞어야 정직한 점수가 정확합니다") }, list,
        h("div", { class: "row mt12" },
          D.seg([["hill", T("힐클라이밍")], ["mean", T("단순 평균")]], method, (v) => (method = v)),
          rankable ? h("label", { class: "check" }, h("input", { type: "checkbox", onchange: (e) => (useRank = e.target.checked) }), T("순위로 바꿔 섞기 (AUC용)")) : null,
          h("span", { class: "grow" }), runBtn),
        h("div", { class: "small muted mt8" }, T("힐클라이밍은 가장 좋은 모델에서 시작해 점수를 가장 올리는 모델을 하나씩 더합니다(같은 모델 반복 가능, 가중치는 항상 0 이상). 음수 가중치는 CV를 낙관적으로 만들어서 쓰지 않습니다."))));
      root.appendChild(out);

      async function run() {
        if (chosen.size < 2) throw new Error(T("실험을 2개 이상 고르세요."));
        const r = await D.api("/api/ensemble", { body: { ids: [...chosen], method, use_rank: useRank } });
        const res = await D.runJob(r.job);
        if (ctx.isCurrent()) show(res);
      }
      function show(res) {
        D.charts.disposeIn(out);
        D.clear(out);
        const better = (a, b) => (hib ? a > b : a < b);
        const honest = res.honest;
        const gainOk = honest ? better(honest.score, res.best_single.score) : res.gain > 0;
        const wEl = D.charts.el("chart sm");
        const hEl = D.charts.el("chart sm");
        const cEl = D.charts.el("chart");
        out.appendChild(D.card(T("결과"), { hint: T("공통 OOF {0}행", f.int(res.rows_used)) },
          h("div", { class: "grid g3" },
            h("div", { class: "col" }, h("div", { class: "muted small" }, T("가장 좋은 단일 모델")), h("div", { class: "hero-num", style: { fontSize: "28px" } }, f.score(res.best_single.score)), h("div", { class: "small muted ellipsis" }, res.best_single.name)),
            h("div", { class: "col" }, h("div", { class: "muted small" }, T("앙상블 (가중치를 같은 데이터로 찾은 점수)")), h("div", { class: "hero-num", style: { fontSize: "28px" } }, f.score(res.score)), h("div", { class: "small muted" }, T("낙관적인 값입니다"))),
            h("div", { class: "col" }, h("div", { class: "muted small" }, T("정직한 앙상블 점수 (다른 폴드로 검증)")),
              h("div", { class: "hero-num", style: { fontSize: "28px", color: honest ? (gainOk ? "var(--ok)" : "var(--danger)") : "inherit" } }, honest ? f.score(honest.score) : "–"),
              h("div", { class: "small muted" }, honest ? T("폴드마다 나머지 폴드로 가중치를 찾아 잰 점수") : T("폴드 정보가 없어 계산하지 못했습니다")))),
          h("div", { class: "mt12" }, D.callout(gainOk ? "ok" : "warn", gainOk
            ? T("섞으면 단일 모델보다 좋아집니다{0}.", honest ? T(" (정직한 점수 기준 {0} 개선)", f.score(Math.abs(honest.score - res.best_single.score))) : "")
            : T("정직한 점수로는 단일 모델보다 나아지지 않습니다. 가중치가 OOF에 과적합됐을 수 있으니, 서로 다른 모델(다른 알고리즘·피처)을 더 모으거나 단순 평균을 써 보세요."))),
          h("div", { class: "grid g2 mt12" },
            h("div", null, h("div", { class: "bold small" }, T("가중치")), wEl),
            h("div", null, h("div", { class: "bold small" }, T("모델을 하나씩 더할 때 점수")), hEl)),
          res.by_target ? h("div", { class: "mt12" }, h("div", { class: "bold small" }, T("타깃별 점수 (섞은 결과, 같은 데이터로 잼)")),
            h("div", { class: "row small" }, res.by_target.map((b) => h("span", { class: "badge" }, `${b.target} ${f.score(b.score)}`)))) : null,
          h("div", { class: "bold small mt12" }, T("OOF 예측 상관 (낮을수록 섞을 때 얻는 게 많음)")), cEl,
          h("div", { class: "row mt12" }, h("span", { class: "grow small muted" }, res.has_all_tests ? T("저장하면 블렌딩한 OOF·test 예측·제출 파일이 새 실험으로 기록됩니다.") : T("고른 실험 중 test 예측이 없는 것이 있어 제출 파일은 만들 수 없습니다(OOF만 저장).")),
            h("button", { class: "btn primary needs-server", onclick: (e) => D.busy(e.currentTarget, async () => {
              const r = await D.api("/api/ensemble/save", { body: {} });
              D.toast((r.has_submission ? T("앙상블을 실험으로 저장하고 제출 파일을 만들었습니다.") : T("앙상블을 실험으로 저장했습니다.")) + (r.notice ? " " + r.notice : ""), r.notice ? "warn" : "ok", r.notice ? 7000 : 3200);
              D.go("experiments");
            }) }, T("실험으로 저장")))));
        setTimeout(() => {
          D.charts.barH(wEl, res.weights.filter((w) => w.weight > 0).map((w) => ({ name: w.name, value: w.weight })), { left: 150, fmt: (v) => f.pct(v, 1), axisFmt: (v) => f.pct(v, 0), valueLabel: T("가중치") });
          if (res.history && res.history.length > 1) D.charts.line(hEl, res.history, { xName: T("단계") });
          else hEl.appendChild(D.empty(res.method === "mean" ? T("단순 평균은 단계가 없습니다") : T("가장 좋은 모델 하나에 더해서 점수가 오르는 모델이 없었습니다"), null));
          D.charts.heatmap(cEl, res.correlation.names, res.correlation.matrix, { min: Math.min(0.5, ...res.correlation.matrix.flat()), max: 1, colors: ["#f2f3f5", "#9fbdf2", "#2f6fdf"] });
        }, 0);
      }
    },
  };
})();
