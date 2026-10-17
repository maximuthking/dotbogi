/* 컬럼: 왼쪽 전체 목록(정렬·검색·필터), 오른쪽 선택한 컬럼의 상세 */
(function () {
  "use strict";
  const D = window.D;
  const h = D.h;
  const f = D.fmt;
  let cache = null;  // { key, rows }

  D.pages.columns = {
    title: "컬럼",
    subtitle: "분포, train/test 차이, 타깃 관계, 단일 피처 예측력",
    async render(root, params, ctx) {
      root.appendChild(D.card(null, null, D.loading("컬럼을 분석하는 중 (처음 한 번)")));
      const res = await D.ensureProfiles();
      if (!ctx.isCurrent()) return;
      D.clear(root);
      const proj = D.project();
      const s = proj.settings;
      const rows = res.columns;
      const hasTest = !!proj.shapes.test;
      const hasTarget = !!s.target.length;

      let selected = params.name && rows.find((r) => r.name === params.name) ? params.name : null;
      if (!selected) {
        const firstFeat = rows.filter((r) => r.role === "feature").sort((a, b) => (b.power ?? -1) - (a.power ?? -1))[0];
        selected = firstFeat ? firstFeat.name : rows[0] && rows[0].name;
      }

      // ── 목록
      let query = params.q || "";
      let kindFilter = params.kind || "";
      const search = h("input", { class: "input sm grow", placeholder: "컬럼 이름 검색", value: query });
      const kinds = [...new Set(rows.map((r) => r.kind))];
      const kindSel = D.select([["", "모든 종류"], ...kinds.map((k) => [k, D.KIND_LABEL[k] || k])], kindFilter, (v) => { kindFilter = v; refresh(); }, { class: "sm" });
      const maxPower = Math.max(0.0001, ...rows.map((r) => r.power || 0));
      const columns = [
        { key: "name", label: "컬럼", render: (r) => h("div", { class: "col", style: { gap: "2px" } },
          h("div", { class: "row", style: { gap: "6px", flexWrap: "nowrap" } }, h("span", { class: "ellipsis bold", style: { maxWidth: "190px" }, title: r.name }, r.name),
            r.role === "target" ? h("span", { class: "badge primary" }, "타깃") : r.role === "id" ? h("span", { class: "badge" }, "ID") : null,
            r.excluded ? h("span", { class: "badge" }, "제외") : null)) },
        { key: "kind", label: "종류", render: (r) => D.kindBadge(r.kind) },
        { key: "missing_train", label: "결측", num: true, title: "train 결측 비율 (test)", render: (r) => h("span", { title: `train ${f.pct(r.missing_train, 2)} · test ${f.pct(r.missing_test, 2)}` },
          f.pct(r.missing_train, 0), hasTest && r.missing_test !== null && Math.abs((r.missing_test || 0) - (r.missing_train || 0)) > 0.05 ? h("span", { class: "faint" }, " / " + f.pct(r.missing_test, 0)) : null) },
        hasTarget ? { key: "power", label: "예측력", title: "컬럼 하나로 타깃을 맞히는 정도 (0~100, 다른 폴드로 잰 값)", render: (r) => r.role === "feature" && r.kind !== "constant" ? D.barCell(r.power, maxPower, (r.power_metric === "r2" ? r.power_value >= 0.9 : r.power_value >= 0.97)) : h("span", { class: "faint" }, "–") } : null,
        hasTest ? { key: "psi", label: "분포 차이", num: true, title: "PSI: 0.1 미만 안정, 0.25 이상 많이 다름. 고유값이 많은 범주는 test의 새 범주 비율로 판정",
          sortValue: (r) => (r.role !== "feature" ? null : r.drift_basis === "unseen" ? r.unseen_rate : r.psi),
          render: (r) => r.role !== "feature" || r.psi === null || r.psi === undefined ? h("span", { class: "faint" }, "–")
            : r.drift_basis === "unseen" ? h("span", { class: "badge " + (D.DRIFT_CLASS[r.drift] || ""), title: "test 행 중 처음 보는 범주 비율" }, "새 " + f.pct(r.unseen_rate, 0))
            : h("span", { class: "badge " + (D.DRIFT_CLASS[r.drift] || "") }, r.psi < 0.001 ? "<0.001" : r.psi.toFixed(r.psi < 0.1 ? 3 : 2)) } : null,
      ].filter(Boolean);
      const listBox = h("div");
      const list = h("div", { class: "card list" }, h("div", { class: "card-h" }, h("h3", null, "전체 컬럼 " + rows.length + "개")),
        h("div", { class: "card-b", style: { paddingBottom: "8px" } }, h("div", { class: "row" }, search, kindSel)), listBox);
      let table;
      const filtered = () => rows.filter((r) => (!query || r.name.toLowerCase().includes(query.toLowerCase())) && (!kindFilter || r.kind === kindFilter));
      const refresh = () => { if (table) table.update(filtered()); };
      table = D.table({
        columns, rows: filtered(), compact: true, sort: hasTarget ? { key: "power", asc: false } : { key: "name", asc: true },
        rowClass: (r) => (r.name === selected ? "sel" : ""),
        onRow: (r) => { selected = r.name; D.setParams({ name: r.name }); refresh(); showDetail(r.name); },
        empty: D.empty("맞는 컬럼이 없습니다", null, "search"),
      });
      listBox.appendChild(table);
      search.addEventListener("input", () => { query = search.value; refresh(); });

      const detail = h("div", { class: "col", style: { gap: "16px" } });
      root.appendChild(h("div", { class: "split" }, list, detail));

      let detailSeq = 0;
      async function showDetail(name) {
        const seq = ++detailSeq;
        D.charts.disposeIn(detail);
        D.clear(detail).appendChild(D.card(null, null, D.loading()));
        try {
          const c = await D.api("/api/column", { params: { name } });
          if (seq !== detailSeq || !ctx.isCurrent()) return;
          D.clear(detail);
          renderDetail(detail, c, proj);
        } catch (e) { D.clear(detail).appendChild(D.card(null, null, D.errorBox(e, () => showDetail(name)))); }
      }
      if (selected) showDetail(selected);
      else detail.appendChild(D.card(null, null, D.empty("컬럼을 고르세요", null)));
    },
  };

  function renderDetail(root, c, proj) {
    const s = proj.settings;
    const hasTest = !!proj.shapes.test;
    // 머리
    const kindSel = D.select(proj.columns.length ? Object.entries(D.KIND_LABEL) : [], c.kind, async (v) => {
      try { await D.api("/api/settings", { body: { kinds: { [c.name]: v } } }); await D.refreshState(); D.navBadges = {}; D.toast(`'${c.name}'의 종류를 '${D.KIND_LABEL[v]}'(으)로 바꿨습니다. 분석을 다시 계산합니다.`); D.render(); }
      catch (e) { D.fail(e); }
    }, { class: "sm", title: "종류 바꾸기" });
    const exBtn = h("button", { class: "btn sm needs-server", onclick: async () => {
      const ex = new Set(s.excluded);
      if (ex.has(c.name)) ex.delete(c.name); else ex.add(c.name);
      try { await D.api("/api/settings", { body: { excluded: [...ex] } }); await D.refreshState(); D.navBadges = {};
        D.toast(ex.has(c.name) ? `'${c.name}'을(를) 모델 입력에서 뺐습니다. 데이터 점검에는 '뺀 컬럼'으로 따로 표시됩니다.` : `'${c.name}'을(를) 다시 넣었습니다.`); D.render(); }
      catch (e) { D.fail(e); }
    } }, c.excluded ? "다시 넣기" : "모델에서 빼기");
    const pw = c.power;
    const powerText = pw && pw.metric ? `${{ auc: "AUC", macro_auc: "평균 AUC", r2: "R²" }[pw.metric]} ${f.num(pw.value, 4)}` : "–";
    root.appendChild(h("div", { class: "card" }, h("div", { class: "card-b" },
      h("div", { class: "row" }, h("h2", { style: { fontSize: "19px", wordBreak: "break-all" } }, c.name), D.kindBadge(c.kind),
        c.role === "target" ? h("span", { class: "badge primary" }, "타깃") : null, c.role === "id" ? h("span", { class: "badge" }, "ID") : null,
        c.kind_overridden ? h("span", { class: "badge info" }, "직접 정한 종류") : null,
        h("span", { class: "grow" }), h("span", { class: "small muted needs-server" }, "종류"), h("span", { class: "needs-server" }, kindSel), exBtn),
      h("div", { class: "row small muted mt8", style: { gap: "14px" } },
        h("span", null, "자료형 ", h("code", null, c.dtype || "–")), h("span", null, "고유값(train+test) ", f.int(c.n_unique)),
        !c.in_test && hasTest ? h("span", { class: "badge warn" }, "test에 없음") : null, !c.in_train ? h("span", { class: "badge warn" }, "train에 없음") : null,
        c.role === "feature" && pw && c.kind !== "constant" ? h("span", null, "단일 피처 예측력 ", h("b", { style: { color: "var(--text)" } }, powerText)) : null,
        c.note ? h("span", null, c.note) : null),
      c.examples && c.examples.length ? h("div", { class: "row mt8", style: { gap: "6px" } }, h("span", { class: "small muted" }, "값 예시"),
        c.examples.map((v) => h("span", { class: "badge", style: { fontWeight: "500", maxWidth: "200px", overflow: "hidden" } }, v))) : null)));

    // 분포
    const distEl = D.charts.el("chart");
    const drift = c.drift;
    const legend = h("div", { class: "legend" }, h("span", { class: "item" }, h("span", { class: "dot train" }), "train"), hasTest && c.in_test ? h("span", { class: "item" }, h("span", { class: "dot test" }), "test") : null);
    const driftLine = drift ? h("div", { class: "row small", style: { gap: "12px" } }, D.driftBadge(drift.level),
      h("span", { class: "muted" }, "PSI ", h("b", { class: "num", style: { color: "var(--text)" } }, f.num(drift.psi, 3))),
      drift.ks !== undefined && drift.ks !== null ? h("span", { class: "muted" }, "KS ", f.num(drift.ks, 3)) : null,
      drift.unseen_rate ? h("span", { class: "muted" }, "test의 새 범주 ", h("b", { style: { color: "var(--warn)" } }, f.pct(drift.unseen_rate, 1)), ` (${f.int(drift.unseen_categories)}종)`) : null,
      drift.test_out_of_range ? h("span", { class: "muted" }, "train 범위 밖 test 값 ", f.pct(drift.test_out_of_range, 1)) : null,
      drift.level_basis === "unseen" ? h("span", { class: "muted" }, "(고유값이 많아 '새 범주 비율'로 판정)") : null) : null;
    root.appendChild(D.card("분포 " + (hasTest && c.in_test ? "train vs test" : "") + (c.basis === "length" ? " (글자 수)" : ""), { actions: legend },
      driftLine, distEl, c.dist && c.dist.clipped ? h("div", { class: "tiny muted" }, "양 끝 0.5%는 가장자리 칸에 모아 그렸습니다.") : null,
      c.dist && c.dist.type === "bar" && c.dist.n_categories > 20 ? h("div", { class: "tiny muted" }, `범주 ${f.int(c.dist.n_categories)}개 중 상위 20개만 따로 그렸습니다.`) : null));
    setTimeout(() => D.charts.dist(distEl, c.dist), 0);

    // 타깃 관계
    if (c.target && s.target.length) {
      const tEl = D.charts.el("chart");
      const tg = c.target;
      const what = tg.task === "binary" ? `구간별 '${tg.positive_class}' 비율` : tg.task === "multiclass" ? "구간별 클래스 비율" : "구간별 타깃 평균";
      root.appendChild(D.card("타깃과의 관계", { hint: what }, tEl));
      setTimeout(() => D.charts.target(tEl, tg), 0);
    }

    // 통계
    root.appendChild(D.card("통계", null, statsTable(c, hasTest)));
  }

  function statsTable(c, hasTest) {
    const tr = c.train || {}, te = c.test || {};
    const showTest = hasTest && c.test;
    const isNum = c.kind === "numeric" && !c.discrete;
    const rows = [];
    const add = (label, a, b, fmt = f.num, warnFn) => rows.push({ label, a, b, fmt, warn: warnFn ? warnFn(a, b) : false });
    add("행 수", tr.count, te.count, f.int);
    add("결측", tr.missing_rate, te.missing_rate, (x) => f.pct(x, 2), (a, b) => b !== undefined && Math.abs((a || 0) - (b || 0)) > 0.05);
    if (c.kind === "datetime") {
      rows.push({ label: "처음", a: tr.min, b: te.min, fmt: (x) => (x ? x.slice(0, 10) : "–") });
      rows.push({ label: "마지막", a: tr.max, b: te.max, fmt: (x) => (x ? x.slice(0, 10) : "–") });
      add("고유값", tr.n_unique, te.n_unique, f.int);
    } else if (isNum) {
      add("평균", tr.mean, te.mean, f.num, (a, b) => b !== undefined && tr.std > 0 && Math.abs(a - b) / tr.std > 0.2);
      add("표준편차", tr.std, te.std);
      add("최소", tr.min, te.min);
      add("1%", tr.p01, te.p01);
      add("25%", tr.p25, te.p25);
      add("중앙값", tr.median, te.median);
      add("75%", tr.p75, te.p75);
      add("99%", tr.p99, te.p99);
      add("최대", tr.max, te.max);
      add("0 비율", tr.zeros_rate, te.zeros_rate, (x) => f.pct(x, 1));
      add("음수 비율", tr.negative_rate, te.negative_rate, (x) => f.pct(x, 1));
      add("이상치 비율 (IQR)", tr.outlier_rate, te.outlier_rate, (x) => f.pct(x, 2));
      add("왜도", tr.skew, te.skew);
      add("고유값", tr.n_unique, te.n_unique, f.int);
    } else {
      add("고유값", tr.n_unique, te.n_unique, f.int);
      add("최빈값 비율", tr.top1_rate, te.top1_rate, (x) => f.pct(x, 1));
      add("한 번만 나온 값 비율", tr.singleton_rate, te.singleton_rate, (x) => f.pct(x, 1));
      if (c.train_num) { add("평균", c.train_num.mean, (c.test_num || {}).mean); add("최소", c.train_num.min, (c.test_num || {}).min); add("최대", c.train_num.max, (c.test_num || {}).max); }
    }
    const table = h("table", { class: "stats" }, h("thead", null, h("tr", null, h("th", null, ""), h("th", null, h("span", { class: "dot train" }), " train"), showTest ? h("th", null, h("span", { class: "dot test" }), " test") : null)),
      h("tbody", null, rows.map((r) => h("tr", { class: r.warn ? "diff" : "" }, h("td", null, r.label), h("td", null, r.fmt(r.a)), showTest ? h("td", null, r.fmt(r.b)) : null))));
    const tops = [];
    if (tr.top) tops.push(h("div", { class: "mt12" }, h("div", { class: "small muted bold" }, "train 상위 값"),
      h("table", { class: "stats" }, h("tbody", null, tr.top.map((t) => h("tr", null, h("td", { title: t.value }, t.value.length > 30 ? t.value.slice(0, 29) + "…" : t.value), h("td", null, f.int(t.count)), h("td", null, f.pct(t.rate, 1))))))));
    return h("div", null, table, rows.some((r) => r.warn) ? h("div", { class: "tiny muted mt8" }, "노란 줄은 train과 test가 눈에 띄게 다른 값입니다.") : null, tops);
  }
})();
