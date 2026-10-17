/* 검증 설계: 검증 방법 추천, 폴드 만들기, 기본 모델 교차검증 */
(function () {
  "use strict";
  const D = window.D;
  const h = D.h;
  const f = D.fmt;
  const NEEDS_GROUP = new Set(["group", "stratified_group"]);

  D.downloadUrl = (expId, kind = "submission") => `/api/download?exp=${encodeURIComponent(expId)}&kind=${kind}&t=${encodeURIComponent(D.token)}`;

  D.pages.cv = {
    title: "검증 설계",
    subtitle: "리더보드와 비슷하게 움직이는 CV 만들기",
    async render(root, params, ctx) {
      root.appendChild(D.card(null, null, D.loading("데이터 구조를 살펴보는 중")));
      const info = await D.ensure("/api/cv");
      if (!ctx.isCurrent()) return;
      D.clear(root);
      const proj = D.project();
      const s = proj.settings;
      const rec = info.recommend;
      const cur = info.current;

      // 추천
      root.appendChild(h("div", { class: "card" }, h("div", { class: "card-b" }, h("div", { class: "row", style: { alignItems: "flex-start" } },
        h("div", { class: "fi", style: { width: "40px", height: "40px", borderRadius: "10px", display: "grid", placeItems: "center", background: "var(--primary-soft)", color: "var(--primary)" } }, D.icon("layers")),
        h("div", { class: "grow" }, h("div", { class: "muted small" }, "추천 검증 방법"),
          h("div", { style: { fontSize: "18px", fontWeight: "750" } }, `${rec.label} · ${rec.n_splits}폴드`,
            rec.group_col ? h("span", { class: "badge primary", style: { marginLeft: "8px" } }, "그룹: " + rec.group_col) : null,
            rec.time_col ? h("span", { class: "badge primary", style: { marginLeft: "8px" } }, "날짜: " + rec.time_col) : null),
          h("ul", { style: { margin: "6px 0 0", paddingLeft: "18px" } }, rec.reasons.map((r) => h("li", null, r)))),
        h("button", { class: "btn primary needs-server", onclick: (e) => D.busy(e.currentTarget, () => makeFolds({ strategy: rec.strategy, n_splits: rec.n_splits, seed: 42, group_col: rec.group_col, time_col: rec.time_col })) },
          cur ? "추천대로 다시 만들기" : "추천대로 폴드 만들기")))));

      // 설정 폼
      let form = { strategy: (cur || rec).strategy, n_splits: (cur || rec).n_splits, seed: cur ? cur.seed : 42,
        group_col: (cur || rec).group_col || (info.group_candidates[0] || {}).column || "", time_col: (cur || rec).time_col || info.time_columns[0] || "" };
      const groupOpts = [...info.group_candidates.map((g) => [g.column, `${g.column} (그룹 ${f.int(g.n_groups)}개, test 새 그룹 ${f.pct(g.test_unseen_rate, 0)})`]),
        ...info.all_columns.filter((c) => !info.group_candidates.some((g) => g.column === c)).map((c) => [c, c])];
      const groupField = h("div", { class: "field" }, h("label", null, "그룹 컬럼"), D.select(groupOpts, form.group_col, (v) => (form.group_col = v)),
        h("div", { class: "help" }, "같은 값(사람·가게·경기 등)은 한 폴드에만 들어갑니다"));
      const timeField = h("div", { class: "field" }, h("label", null, "날짜 컬럼"),
        info.time_columns.length ? D.select(info.time_columns.map((c) => [c, c]), form.time_col, (v) => (form.time_col = v)) : h("div", { class: "small muted" }, "날짜로 인식된 컬럼이 없습니다. 컬럼 화면에서 종류를 '날짜'로 바꿀 수 있습니다."),
        h("div", { class: "help" }, "시간 순으로 나눠 과거로 학습하고 다음 기간으로 검증합니다"));
      const toggle = () => { groupField.style.display = NEEDS_GROUP.has(form.strategy) ? "" : "none"; timeField.style.display = form.strategy === "time" ? "" : "none"; };
      const strat = D.seg(Object.entries(info.strategies), form.strategy, (v) => { form.strategy = v; toggle(); });
      const nIn = h("input", { class: "input", type: "number", min: "2", max: "20", value: form.n_splits, onchange: (e) => (form.n_splits = Number(e.target.value)) });
      const seedIn = h("input", { class: "input", type: "number", value: form.seed, onchange: (e) => (form.seed = Number(e.target.value)) });
      const makeBtn = h("button", { class: "btn primary", onclick: () => D.busy(makeBtn, () => {
        form.n_splits = Number(nIn.value);
        form.seed = Number(seedIn.value);
        if (!Number.isInteger(form.n_splits) || form.n_splits < 2 || form.n_splits > 20) throw new Error("폴드 수는 2~20 사이 정수로 적으세요.");
        if (!Number.isInteger(form.seed)) throw new Error("시드는 정수로 적으세요.");
        return makeFolds(form);
      }) }, "폴드 만들기");
      root.appendChild(h("div", { class: "card needs-server" }, h("div", { class: "card-h" }, h("h3", null, "직접 정하기")),
        h("div", { class: "card-b col" }, strat,
          h("div", { class: "grid g4", style: { gap: "12px" } },
            h("div", { class: "field" }, h("label", null, "폴드 수"), nIn), h("div", { class: "field" }, h("label", null, "시드"), seedIn), groupField, timeField),
          h("div", { class: "row" }, h("span", { class: "grow small muted" }, "폴드를 다시 만들면 이전 실험의 OOF와 폴드가 달라져 앙상블의 '정직한 점수'가 덜 정확해집니다."), makeBtn))));
      toggle();

      // 현재 폴드
      const foldCard = h("div");
      root.appendChild(foldCard);
      renderFolds(foldCard, info);

      // 기본 모델
      root.appendChild(baselineCard(proj, info));

      async function makeFolds(p) {
        const r = await D.api("/api/cv/folds", { body: p });
        await D.refreshState();
        D.toast(`폴드를 만들었습니다: ${r.path}`);
        D.render();
      }
    },
  };

  function renderFolds(box, info) {
    const cur = info.current;
    if (!cur || !info.has_folds) {
      box.appendChild(D.card("현재 폴드", null, D.callout("info", "아직 폴드를 만들지 않았습니다. 추천대로 만들면 학습 코드에서 같은 폴드를 읽어 쓸 수 있고, 실험끼리 OOF를 공정하게 비교·앙상블할 수 있습니다.")));
      return;
    }
    const s = D.settings();
    const sum = info.summary || [];
    const key = s.task === "binary" ? "positive_rate" : s.task === "regression" ? "target_mean" : "top_class_rate";
    const label = s.task === "binary" ? "양성 비율" : s.task === "regression" ? "타깃 평균" : "최다 클래스 비율";
    const el = D.charts.el("chart sm");
    const unused = sum.find((r) => r.fold === -1);
    const rows = sum.filter((r) => r.fold >= 0);
    const cols = [{ key: "fold", label: "폴드", num: true }, { key: "rows", label: "검증 행", num: true, render: (r) => f.int(r.rows) }];
    if (rows[0] && rows[0][key] !== undefined) cols.push({ key, label, num: true, render: (r) => (s.task === "regression" ? f.num(r[key], 4) : f.pct(r[key], 2)) });
    if (rows[0] && rows[0].groups !== undefined) cols.push({ key: "groups", label: "그룹 수", num: true, render: (r) => f.int(r.groups) });
    if (rows[0] && rows[0].time_from) cols.push({ key: "time_from", label: "기간", render: (r) => `${r.time_from} ~ ${r.time_to}` });
    box.appendChild(D.card("현재 폴드", { hint: `${D.STRATEGY_LABEL(cur.strategy, info)} · ${cur.n_splits}폴드 · 시드 ${cur.seed}` + (cur.group_col ? ` · 그룹 ${cur.group_col}` : "") + (cur.time_col ? ` · 날짜 ${cur.time_col}` : "") + ` · ${cur.created_at || ""}` },
      h("div", { class: "grid g2" },
        h("div", null, el, unused ? h("div", { class: "small muted" }, `검증에 쓰지 않는 행(시간 검증의 첫 구간 등): ${f.int(unused.rows)}행` + (unused.time_from ? ` (${unused.time_from} ~ ${unused.time_to})` : "")) : null),
        D.table({ columns: cols, rows, compact: true, sort: { key: "fold", asc: true } })),
      h("div", { class: "sep" }),
      h("div", { class: "bold small" }, "학습 코드에서 쓰기"),
      h("div", { class: "small muted", style: { margin: "4px 0 8px" } }, "폴드 파일: ", h("code", null, info.folds_path), " · 파이썬에서는 ", h("code", null, "dotbogi.folds(대회폴더)"), "로도 읽을 수 있습니다."),
      D.codeBlock(info.snippet)));
    setTimeout(() => D.charts.folds(el, sum, rows[0] && rows[0][key] !== undefined ? key : null, label, s.task === "regression" ? (v) => f.num(v, 3) : (v) => f.pct(v, 0)), 0);
  }
  D.STRATEGY_LABEL = (k, info) => ((info && info.strategies) || (D.state && D.state.strategies) || {})[k] || k;

  function baselineCard(proj, info) {
    const s = proj.settings;
    const out = h("div");
    if (!s.target.length) return D.card("기본 모델로 기준 점수", null, D.callout("warn", "타깃을 먼저 정하세요."));
    let engine = "auto";
    let lr = 0.05;
    let exclude = [];
    const feats = proj.columns.filter((c) => !s.target.includes(c.name) && c.name !== s.id_col && !s.excluded.includes(c.name) && c.in_train && c.kind !== "id" && c.kind !== "constant");
    const exChips = h("div", { class: "row", style: { gap: "6px" } });
    const addSel = D.select([["", "+ 뺄 컬럼 고르기"], ...feats.map((c) => [c.name, c.name])], "", (v) => { if (v && !exclude.includes(v)) exclude.push(v); renderEx(); addSel.value = ""; }, { class: "sm" });
    const renderEx = () => { D.clear(exChips); exclude.forEach((c) => exChips.appendChild(h("span", { class: "chip on", onclick: () => { exclude = exclude.filter((x) => x !== c); renderEx(); } }, c, h("span", { class: "x" }, "×")))); };
    const engSel = D.select([["auto", D.state.lightgbm ? "LightGBM (설치됨)" : "자동 (HistGradientBoosting)"], ...(D.state.lightgbm ? [["sklearn", "HistGradientBoosting (scikit-learn)"]] : [])], engine, (v) => (engine = v));
    const lrIn = h("input", { class: "input", value: lr, inputmode: "decimal", onchange: (e) => (lr = Number(e.target.value) || 0.05) });
    const nameIn = h("input", { class: "input", placeholder: "비우면 자동 이름" });
    const runBtn = h("button", { class: "btn primary", onclick: () => D.busy(runBtn, run) }, D.icon("play"), "교차검증 실행");
    async function run() {
      lr = Number(String(lrIn.value).replace(",", "."));
      if (!(lr > 0 && lr <= 1)) throw new Error("학습률은 0보다 크고 1 이하인 숫자로 적으세요.");
      const r = await D.api("/api/baseline", { body: { engine, learning_rate: lr, exclude, name: nameIn.value.trim() || undefined } });
      const res = await D.runJob(r.job);
      await D.refreshState();
      showResult(res);
      D.toast("기본 모델 결과를 실험 대장에 기록했습니다.");
    }
    function showResult(res) {
      D.charts.disposeIn(out);
      D.clear(out);
      const e = res.experiment;
      const impEl = D.charts.el("chart");
      const fsCols = [{ key: "fold", label: "폴드", num: true }, { key: "score", label: D.metricLabel(), num: true, render: (r) => f.score(r.score) },
        { key: "rows", label: "검증 행", num: true, render: (r) => f.int(r.rows) }, { key: "train_rows", label: "학습 행", num: true, render: (r) => f.int(r.train_rows) },
        { key: "best_iteration", label: "트리 수", num: true }];
      out.appendChild(h("div", { class: "sep" }));
      out.appendChild(h("div", { class: "grid g3" },
        h("div", { class: "col" }, h("div", { class: "muted small" }, `CV ${D.metricLabel()} (${D.higherBetter() ? "높을수록" : "낮을수록"} 좋음)`),
          h("div", { class: "hero-num" }, f.score(res.cv)), h("div", { class: "small muted" }, `폴드 편차 ±${f.score(res.cv_std)} · 피처 ${res.n_features}개 · ${f.sec(res.seconds)}`),
          h("div", { class: "row mt8" }, h("button", { class: "btn sm", onclick: () => D.go("experiments") }, "실험 대장에서 보기"),
            e.files && e.files.submission ? h("a", { class: "btn sm", href: D.downloadUrl(e.id) }, D.icon("download"), "제출 파일") : null)),
        h("div", { style: { gridColumn: "span 2" } }, D.table({ columns: fsCols, rows: res.fold_scores, compact: true, sort: { key: "fold", asc: true } }))));
      out.appendChild(h("div", { class: "bold small mt12" }, "피처 중요도" + (res.engine === "lightgbm" ? " (gain)" : " (순열 중요도)")), impEl);
      const sk = Object.entries(res.skipped || {});
      if (sk.length) out.appendChild(h("div", { class: "tiny muted" }, "학습에서 빠진 컬럼: " + sk.map(([k, v]) => `${k}(${v})`).join(", ")));
      setTimeout(() => D.charts.barH(impEl, res.importance.slice(0, 25).map((x) => ({ name: x.name, value: x.importance, sub: x.encoding })), { left: 170, fmt: (v) => f.pct(v, 1), axisFmt: (v) => f.pct(v, 0), valueLabel: "중요도" }), 0);
    }
    return D.card("기본 모델로 기준 점수", { hint: "피처 엔지니어링 전 출발점. 결과는 실험 대장에 OOF·제출 파일과 함께 기록됩니다", class: "needs-server" },
      h("div", { class: "grid g3", style: { gap: "12px" } },
        h("div", { class: "field" }, h("label", null, "모델"), engSel),
        h("div", { class: "field" }, h("label", null, "학습률"), lrIn),
        h("div", { class: "field" }, h("label", null, "실험 이름"), nameIn)),
      h("div", { class: "row mt12" }, h("span", { class: "small muted" }, "뺄 컬럼"), addSel, exChips, h("span", { class: "grow" }), runBtn),
      h("div", { class: "small muted mt8" }, info.has_folds ? "현재 폴드로 학습합니다. " : "폴드가 없으면 추천 방법으로 먼저 만듭니다. ",
        "조기 종료는 검증 폴드가 아닌 학습 폴드 안쪽 10%로 해서 OOF가 낙관적으로 나오지 않게 합니다. 그룹 검증이면 그룹 컬럼은 입력에서 뺍니다."),
      out);
  }
})();
