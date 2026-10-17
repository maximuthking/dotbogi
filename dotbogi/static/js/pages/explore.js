/* 탐색: 예측력 순위, 상관 관계, 그래프 만들기, 데이터 표 */
(function () {
  "use strict";
  const D = window.D;
  const h = D.h;
  const f = D.fmt;

  D.pages.explore = {
    title: "탐색",
    subtitle: "피처 순위, 상관, 직접 그리는 그래프, 원본 데이터",
    async render(root, params, ctx) {
      const tab = params.tab || "power";
      const tabs = h("div", { class: "tabs" });
      const body = h("div", { class: "col", style: { gap: "16px" } });
      const names = [["power", "예측력 순위"], ["corr", "상관 관계"], ["chart", "그래프 만들기"], ["data", "데이터 보기"]];
      for (const [k, label] of names) {
        if (D.STATIC && (k === "chart" || k === "data")) continue;
        tabs.appendChild(h("button", { class: k === tab ? "on" : "", onclick: () => D.go("explore", { tab: k }) }, label));
      }
      root.append(tabs, body);
      if (tab === "power") return power(body, ctx);
      if (tab === "corr") return corr(body, ctx);
      if (tab === "chart") return chart(body, params, ctx);
      return data(body, params, ctx);
    },
  };

  async function power(body, ctx) {
    const proj = D.project();
    if (!proj.settings.target.length) { body.appendChild(D.card(null, null, D.empty("타깃이 정해지지 않았습니다", "개요에서 타깃을 고르면 피처 예측력을 볼 수 있습니다.", "info"))); return; }
    body.appendChild(D.card(null, null, D.loading("컬럼 분석을 불러오는 중")));
    const res = await D.ensureProfiles();
    if (!ctx.isCurrent()) return;
    D.clear(body);
    const rows = res.columns.filter((c) => c.role === "feature" && c.power_value !== null && c.power_value !== undefined);
    rows.sort((a, b) => (b.power || 0) - (a.power || 0));
    const metric = rows[0] ? rows[0].power_metric : "auc";
    const mName = { auc: "AUC", macro_auc: "평균 AUC", r2: "R²" }[metric] || metric;
    const leakLine = metric === "r2" ? 0.9 : 0.97;
    const p = D.palette();
    const el = D.charts.el("chart");
    const zero = rows.filter((r) => (r.power || 0) < 0.005).length;
    body.appendChild(D.card("컬럼 하나로 타깃을 얼마나 맞히나", { hint: `단일 피처 ${mName} (5폴드 교차, 높을수록 강함)` },
      h("div", { class: "small muted" }, "숫자 컬럼은 20개 구간으로, 범주 컬럼은 값별로 나눠 타깃 평균을 다른 폴드에서 배운 뒤 맞혀 본 점수입니다. 고유값이 많아 학습 데이터를 외우는 컬럼은 점수가 부풀지 않습니다.",
        metric !== "r2" ? " 0.5는 우연 수준입니다." : " 0은 평균으로 찍는 수준입니다."),
      el,
      zero ? h("div", { class: "small muted" }, `혼자서는 거의 정보가 없는 컬럼 ${zero}개 (다른 컬럼과 함께 쓰면 쓸모 있을 수 있습니다)`) : null));
    setTimeout(() => D.charts.barH(el, rows.slice(0, 40).map((r) => ({
      name: r.name, value: r.power_value, color: r.power_value >= leakLine ? p.danger : null, sub: D.KIND_LABEL[r.kind] })),
      { left: 170, limit: 40, valueLabel: mName, fmt: (v) => f.num(v, 3), axisFmt: (v) => f.num(v, 2), mark: leakLine, markLabel: "누수 의심선", max: 1, min: metric === "r2" ? 0 : 0.5 }), 0);
  }

  async function corr(body, ctx) {
    let method = "spearman";
    const out = h("div");
    const seg = D.seg([["spearman", "스피어만 (순위)"], ["pearson", "피어슨 (선형)"]], method, (v) => { method = v; load(); });
    body.appendChild(D.card("숫자 컬럼 상관 행렬", { hint: "예측력 상위 30개, 3만 행 표본", actions: D.STATIC ? null : seg }, out));
    async function load() {
      D.charts.disposeIn(out);
      D.clear(out).appendChild(D.loading());
      try {
        const r = D.STATIC ? await D.api("/api/correlation") : await D.api("/api/correlation", { params: { method } });
        if (!ctx.isCurrent()) return;
        D.clear(out);
        if (!r.names || r.names.length < 2) { out.appendChild(D.empty("숫자 컬럼이 2개 이상 있어야 합니다", null)); return; }
        const el = D.charts.el("chart lg");
        out.appendChild(el);
        D.charts.heatmap(el, r.names, r.matrix, { onClick: (a) => { if (!a.startsWith("타깃:")) D.go("columns", { name: a }); } });
        if (r.pairs.length) {
          out.appendChild(h("div", { class: "bold small mt12" }, "강하게 연결된 쌍 (|r| ≥ 0.8)"));
          out.appendChild(D.table({ columns: [
            { key: "a", label: "컬럼 A", render: (x) => D.colChip(x.a) }, { key: "b", label: "컬럼 B", render: (x) => D.colChip(x.b) },
            { key: "r", label: "상관", num: true, sortValue: (x) => Math.abs(x.r), render: (x) => f.num(x.r, 3) }], rows: r.pairs, compact: true, sort: { key: "r", asc: false }, maxHeight: "300px" }));
        }
      } catch (e) { D.clear(out).appendChild(D.errorBox(e, load)); }
    }
    load();
  }

  async function chart(body, params, ctx) {
    const proj = D.project();
    const cols = proj.columns;
    let x = params.x || (cols.find((c) => c.kind === "numeric" && c.in_train) || cols[0]).name;
    let y = params.y || "";
    let color = params.color ?? (proj.settings.target.length ? "target" : "");
    let which = params.which || "train";
    const out = h("div");
    const opt = (list) => list.map((c) => [c.name, c.name]);
    const trainCols = cols.filter((c) => (which === "train" ? c.in_train : c.in_test));
    const sx = D.select(opt(trainCols), x, (v) => { x = v; draw(); });
    const sy = D.select([["", "(없음: 분포)"], ...opt(trainCols)], y, (v) => { y = v; draw(); });
    const sc = D.select([["", "(없음)"], ...(proj.settings.target.length ? [["target", "타깃: " + proj.settings.target[0]]] : []), ...opt(trainCols.filter((c) => !proj.settings.target.includes(c.name)))], color, (v) => { color = v; draw(); });
    const sw = D.seg([["train", "train"], ...(proj.shapes.test ? [["test", "test"]] : [])], which, (v) => { which = v; if (v === "test" && color === "target") color = ""; D.go("explore", { tab: "chart", x, y, color, which }); });
    body.appendChild(D.card("그래프 만들기", { hint: "x만 고르면 분포, y까지 고르면 관계를 그립니다" },
      h("div", { class: "grid g4", style: { gap: "12px" } },
        h("div", { class: "field" }, h("label", null, "x"), sx), h("div", { class: "field" }, h("label", null, "y"), sy),
        h("div", { class: "field" }, h("label", null, "색으로 나누기"), sc), h("div", { class: "field" }, h("label", null, "데이터"), sw)),
      h("div", { class: "mt12" }, out)));
    async function draw() {
      D.setParams({ tab: "chart", x, y, color, which });
      D.charts.disposeIn(out);
      D.clear(out).appendChild(D.loading());
      try {
        const r = await D.api("/api/explore", { body: { x, y, color, which } });
        if (!ctx.isCurrent()) return;
        D.clear(out);
        const el = D.charts.el("chart xl");
        out.appendChild(el);
        if (r.type === "scatter") D.charts.scatter(el, r);
        else if (r.type === "box") D.charts.box(el, r);
        else if (r.type === "heat") D.charts.crossHeat(el, r);
        else D.charts.series(el, r);
        out.appendChild(h("div", { class: "tiny muted" }, r.sampled ? `전체 ${f.int(r.n)}행 중 표본으로 그렸습니다.` : `전체 ${f.int(r.n)}행`));
      } catch (e) { D.clear(out).appendChild(D.errorBox(e, draw)); }
    }
    draw();
  }

  async function data(body, params, ctx) {
    const proj = D.project();
    let which = params.which || "train";
    let offset = 0;
    const limit = 100;
    let sort = null, asc = true;
    let filters = [];
    const out = h("div");
    const info = h("span", { class: "small muted" });
    const fCol = D.select(proj.columns.map((c) => [c.name, c.name]), proj.columns[0].name, null, { class: "sm" });
    const fOp = D.select([["==", "="], ["!=", "≠"], [">", ">"], [">=", "≥"], ["<", "<"], ["<=", "≤"], ["contains", "포함"], ["isnull", "비어 있음"], ["notnull", "값 있음"]], "==", null, { class: "sm" });
    const fVal = h("input", { class: "input sm", placeholder: "값", style: { width: "140px" } });
    const chips = h("div", { class: "row", style: { gap: "6px" } });
    const renderChips = () => {
      D.clear(chips);
      filters.forEach((fl, i) => chips.appendChild(h("span", { class: "chip on", onclick: () => { filters.splice(i, 1); offset = 0; renderChips(); load(); } },
        `${fl.col} ${fl.op} ${fl.op === "isnull" || fl.op === "notnull" ? "" : fl.value}`, h("span", { class: "x" }, "×"))));
    };
    const addF = h("button", { class: "btn sm", onclick: () => { filters.push({ col: fCol.value, op: fOp.value, value: fVal.value }); offset = 0; renderChips(); load(); } }, "필터 추가");
    fVal.addEventListener("keydown", (e) => { if (e.key === "Enter") addF.click(); });
    const sw = D.seg([["train", "train"], ...(proj.shapes.test ? [["test", "test"]] : []), ...(proj.shapes.sample_submission ? [["sample_submission", "제출 양식"]] : [])], which,
      (v) => { which = v; offset = 0; filters = []; sort = null; renderChips(); load(); });
    const prev = h("button", { class: "btn sm", onclick: () => { offset = Math.max(0, offset - limit); load(); } }, "이전");
    const next = h("button", { class: "btn sm", onclick: () => { offset += limit; load(); } }, "다음");
    body.appendChild(D.card("데이터 보기", { actions: sw },
      h("div", { class: "row" }, fCol, fOp, fVal, addF, chips, h("span", { class: "grow" }), info, prev, next), h("div", { class: "mt12" }, out)));
    async function load() {
      D.clear(out).appendChild(D.loading());
      try {
        const r = await D.api("/api/rows", { body: { which, offset, limit, sort, asc, filters } });
        if (!ctx.isCurrent()) return;
        D.clear(out);
        info.textContent = r.matched ? `${f.int(r.offset + 1)}–${f.int(Math.min(r.offset + limit, r.matched))} / ${f.int(r.matched)}행` + (r.matched !== r.total ? ` (전체 ${f.int(r.total)})` : "") : "맞는 행 없음";
        prev.disabled = offset === 0; next.disabled = offset + limit >= r.matched;
        const table = h("table", { class: "t grid-data compact" });
        const trh = h("tr", null, h("th", { class: "num" }, "#"));
        for (const c of r.columns) trh.appendChild(h("th", { class: "sortable", onclick: () => { if (sort === c) asc = !asc; else { sort = c; asc = true; } offset = 0; load(); } },
          c, sort === c ? h("span", { class: "arrow" }, asc ? "▲" : "▼") : null));
        table.appendChild(h("thead", null, trh));
        const tb = h("tbody");
        r.rows.forEach((row, i) => tb.appendChild(h("tr", null, h("td", { class: "num faint" }, r.index[i]),
          row.map((v) => h("td", { class: v === null ? "null" : "", title: v === null ? "" : String(v) }, v === null ? "null" : typeof v === "number" ? f.num(v, 8) : String(v))))));
        table.appendChild(tb);
        out.appendChild(h("div", { class: "table-wrap", style: { maxHeight: "560px" } }, table));
      } catch (e) { D.clear(out).appendChild(D.errorBox(e, load)); }
    }
    load();
  }
})();
