/* ECharts 감싸기. 색은 CSS 변수에서 읽어 테마와 맞춘다. train=파랑, test=주황으로 통일. */
(function () {
  "use strict";
  const D = window.D;
  const T = D.t;
  const instances = [];
  const f = D.fmt;

  function css(name) { return getComputedStyle(document.documentElement).getPropertyValue(name).trim(); }
  function palette() {
    return {
      text: css("--text"), text2: css("--text-2"), muted: css("--muted"), faint: css("--faint"), border: css("--border"),
      surface: css("--surface"), surface3: css("--surface-3"), primary: css("--primary"), train: css("--train"), test: css("--test"),
      danger: css("--danger"), warn: css("--warn"), ok: css("--ok"), info: css("--info"),
      series: ["#2f6fdf", "#e5762b", "#23874d", "#8b4fd6", "#cf3434", "#0f9bb3", "#c49a00", "#d94f9c", "#5f6b7a", "#7a9a1a"],
    };
  }
  D.palette = palette;

  function base(p) {
    return {
      animationDuration: 300,
      textStyle: { fontFamily: getComputedStyle(document.body).fontFamily, color: p.text2 },
      grid: { left: 54, right: 18, top: 28, bottom: 40, containLabel: false },
      tooltip: {
        backgroundColor: p.surface, borderColor: p.border, textStyle: { color: p.text, fontSize: 12 },
        extraCssText: "box-shadow: 0 6px 20px rgba(0,0,0,0.18); border-radius: 8px;", confine: true,
      },
    };
  }
  /* 비율 축 눈금: 최댓값이 작으면 소수 자릿수를 늘려 '3%, 3%' 같은 중복을 막는다 */
  function pctAxisFmt(maxVal) {
    const d = maxVal < 0.02 ? 2 : maxVal < 0.2 ? 1 : 0;
    return (v) => (v * 100).toFixed(d) + "%";
  }
  function arrMax(...arrs) { let m = 0; arrs.forEach((a) => (a || []).forEach((v) => { if (v > m) m = v; })); return m; }
  function axis(p, extra) {
    return Object.assign({
      axisLine: { lineStyle: { color: p.border } }, axisTick: { show: false },
      axisLabel: { color: p.muted, fontSize: 11 }, splitLine: { lineStyle: { color: p.border, type: "dashed" } },
      nameTextStyle: { color: p.muted, fontSize: 11 },
    }, extra || {});
  }

  function make(el, option) {
    if (!window.echarts) { el.textContent = T("차트 라이브러리를 불러오지 못했습니다."); return null; }
    const chart = window.echarts.init(el, null, { renderer: "canvas" });
    chart.setOption(option);
    const ro = new ResizeObserver(() => { if (!chart.isDisposed()) chart.resize(); });
    ro.observe(el);
    instances.push({ chart, ro });
    return chart;
  }

  const C = (D.charts = {});
  C.disposeAll = function () {
    while (instances.length) {
      const { chart, ro } = instances.pop();
      ro.disconnect();
      if (!chart.isDisposed()) chart.dispose();
    }
  };
  /* el 안에 있는 차트만 정리 (같은 화면의 다른 차트는 그대로) */
  C.disposeIn = function (el) {
    for (let i = instances.length - 1; i >= 0; i--) {
      const { chart, ro } = instances[i];
      const dom = chart.getDom && chart.getDom();
      if (dom && el.contains(dom)) {
        ro.disconnect();
        if (!chart.isDisposed()) chart.dispose();
        instances.splice(i, 1);
      }
    }
  };
  C.el = (cls = "chart") => D.h("div", { class: cls });

  function binLabels(edges, isDate) {
    const out = [];
    for (let i = 0; i < edges.length - 1; i++) {
      const mid = (edges[i] + edges[i + 1]) / 2;
      out.push(isDate ? f.day(mid) : f.num(mid, 3));
    }
    return out;
  }
  function rangeLabel(a, b, isDate) {
    return isDate ? f.day(a) + " ~ " + f.day(b) : f.num(a, 4) + " ~ " + f.num(b, 4);
  }

  /* train vs test 분포 (히스토그램 또는 범주 막대). 값은 비율 */
  C.dist = function (el, dist, opts = {}) {
    const p = palette();
    if (!dist) { el.appendChild(D.empty(T("분포를 그릴 값이 없습니다"), null)); return; }
    const o = base(p);
    const series = [];
    let cats;
    if (dist.type === "hist") {
      cats = binLabels(dist.edges, dist.datetime);
      const tip = (i) => rangeLabel(dist.edges[i], dist.edges[i + 1], dist.datetime);
      o.tooltip.trigger = "axis";
      o.tooltip.formatter = (ps) => {
        const i = ps[0].dataIndex;
        return `<b>${D.esc(tip(i))}</b><br>` + ps.map((s) => `${s.marker}${s.seriesName} ${f.pct(s.value, 2)}`).join("<br>");
      };
      if (dist.train) series.push({ name: "train", type: "bar", data: dist.train, barGap: "-100%", barCategoryGap: "4%", itemStyle: { color: p.train, opacity: 0.6 } });
      if (dist.test) series.push({ name: "test", type: "bar", data: dist.test, barGap: "-100%", barCategoryGap: "4%", z: 3,
        itemStyle: { color: "rgba(0,0,0,0)", borderColor: p.test, borderWidth: 1.6 } });
    } else {
      cats = dist.categories;
      o.tooltip.trigger = "axis";
      o.tooltip.formatter = (ps) => `<b>${D.esc(cats[ps[0].dataIndex])}</b><br>` + ps.map((s) => `${s.marker}${s.seriesName} ${f.pct(s.value, 2)}`).join("<br>");
      if (dist.train) series.push({ name: "train", type: "bar", data: dist.train, itemStyle: { color: p.train, borderRadius: [3, 3, 0, 0] }, barMaxWidth: 26 });
      if (dist.test) series.push({ name: "test", type: "bar", data: dist.test, itemStyle: { color: p.test, borderRadius: [3, 3, 0, 0] }, barMaxWidth: 26 });
    }
    o.legend = { show: false };
    o.xAxis = axis(p, { type: "category", data: cats, axisLabel: { color: p.muted, fontSize: 11, hideOverlap: true, rotate: dist.type === "bar" && cats.length > 8 ? 30 : 0, formatter: (v) => (v.length > 14 ? v.slice(0, 13) + "…" : v) } });
    o.yAxis = axis(p, { type: "value", axisLabel: { color: p.muted, fontSize: 11, formatter: pctAxisFmt(arrMax(dist.train, dist.test)) } });
    if (dist.type === "bar" && cats.length > 8) o.grid.bottom = 70;
    o.series = series;
    return make(el, o);
  };

  /* 타깃과의 관계: 구간/범주별 양성 비율·평균 (막대=행 수, 선=타깃) */
  C.target = function (el, tg, opts = {}) {
    const p = palette();
    if (!tg || !tg.groups || !tg.groups.length) { el.appendChild(D.empty(T("타깃 관계를 그릴 수 없습니다"), null)); return; }
    const o = base(p);
    const labels = tg.groups.map((g) => {
      if (g.label_type === "range") return rangeLabel(g.label[0], g.label[1], tg.datetime);
      if (g.label_type === "missing") return T("(결측)");
      return String(g.label);
    });
    // 축에는 구간 시작값만, 전체 구간은 툴팁에
    const short = tg.groups.map((g, i) => {
      if (g.label_type === "range") return (tg.datetime ? f.day(g.label[0]) : f.num(g.label[0], 3)) + "~";
      const s = labels[i];
      return s.length > 14 ? s.slice(0, 13) + "…" : s;
    });
    o.xAxis = axis(p, { type: "category", data: short, axisLabel: { color: p.muted, fontSize: 11, rotate: labels.length > 6 ? 30 : 0, hideOverlap: true } });
    o.grid.bottom = labels.length > 6 ? 80 : 40;
    o.grid.right = 54;
    o.tooltip.trigger = "axis";
    if (tg.task === "multiclass") {
      o.yAxis = axis(p, { type: "value", max: 1, axisLabel: { color: p.muted, fontSize: 11, formatter: (v) => f.pct(v, 0) } });
      o.series = tg.classes.map((c, k) => ({
        name: String(c), type: "bar", stack: "r", data: tg.groups.map((g) => g.rates[k]), barMaxWidth: 34,
        itemStyle: { color: p.series[k % p.series.length] },
      }));
      o.legend = { top: 0, textStyle: { color: p.muted, fontSize: 11 }, itemWidth: 10, itemHeight: 10, type: "scroll" };
      o.grid.top = 34;
      o.tooltip.formatter = (ps) => T("<b>{0}</b> ({1}행)<br>", D.esc(labels[ps[0].dataIndex]), f.int(tg.groups[ps[0].dataIndex].count)) +
        ps.map((s) => `${s.marker}${D.esc(s.seriesName)} ${f.pct(s.value, 1)}`).join("<br>");
      return make(el, o);
    }
    const isBin = tg.task === "binary";
    const vals = tg.groups.map((g) => g.mean);
    o.yAxis = [
      axis(p, { type: "value", name: isBin ? T("양성 비율") : T("타깃 평균"), axisLabel: { color: p.muted, fontSize: 11, formatter: (v) => (isBin ? f.pct(v, 0) : f.num(v, 3)) } }),
      axis(p, { type: "value", name: T("행 수"), splitLine: { show: false }, axisLabel: { color: p.faint, fontSize: 10, formatter: (v) => f.num(v, 2) } }),
    ];
    o.series = [
      { name: T("행 수"), type: "bar", yAxisIndex: 1, data: tg.groups.map((g) => g.count), itemStyle: { color: p.surface3 }, barMaxWidth: 34, z: 1 },
      { name: isBin ? T("양성 비율") : T("타깃 평균"), type: "line", data: vals, symbolSize: 8, z: 3, itemStyle: { color: p.primary },
        lineStyle: { width: tg.groups.every((g) => g.label_type !== "range") ? 0 : 2.4, color: p.primary },
        markLine: tg.overall !== null && tg.overall !== undefined ? { silent: true, symbol: "none", lineStyle: { color: p.muted, type: "dashed" },
          label: { formatter: T("전체 ") + (isBin ? f.pct(tg.overall, 1) : f.num(tg.overall, 4)), color: p.muted, fontSize: 11, position: "insideEndTop" },
          data: [{ yAxis: tg.overall }] } : undefined },
    ];
    o.tooltip.formatter = (ps) => {
      const i = ps[0].dataIndex; const g = tg.groups[i];
      return T("<b>{0}</b><br>행 수 {1}<br>", D.esc(labels[i]), f.int(g.count)) + (isBin ? T("양성 비율 {0}", f.pct(g.mean, 1)) : T("평균 {0} (표준편차 {1})", f.num(g.mean, 4), f.num(g.std, 3)));
    };
    return make(el, o);
  };

  /* 가로 막대 (중요도, 예측력 등). items: [{name, value, color?, sub?}] */
  C.barH = function (el, items, opts = {}) {
    const p = palette();
    const o = base(p);
    const data = items.slice(0, opts.limit || 30).reverse();
    o.grid = { left: opts.left || 150, right: 50, top: opts.mark !== undefined ? 26 : 8, bottom: 26 };
    o.yAxis = axis(p, { type: "category", data: data.map((d) => d.name), axisLabel: { color: p.text2, fontSize: 11.5, width: (opts.left || 150) - 12, overflow: "truncate" } });
    o.xAxis = axis(p, { type: "value", max: opts.max, min: opts.min, axisLabel: { color: p.muted, fontSize: 11, formatter: opts.axisFmt || ((v) => f.num(v, 3)) } });
    o.tooltip.trigger = "item";
    o.tooltip.formatter = (s) => `<b>${D.esc(s.name)}</b><br>${opts.valueLabel || T("값")} ${opts.fmt ? opts.fmt(s.value) : f.num(s.value, 4)}` + (data[s.dataIndex].sub ? `<br>${D.esc(data[s.dataIndex].sub)}` : "");
    o.series = [{ type: "bar", data: data.map((d) => ({ value: d.value, itemStyle: { color: d.color || opts.color || p.primary, borderRadius: [0, 3, 3, 0] } })),
      barMaxWidth: 16, label: { show: true, position: "right", color: p.muted, fontSize: 11, formatter: (s) => (opts.fmt ? opts.fmt(s.value) : f.num(s.value, 3)) },
      markLine: opts.mark !== undefined ? { silent: true, symbol: "none", lineStyle: { color: p.danger, type: "dashed" }, label: { formatter: opts.markLabel || "", color: p.danger, fontSize: 11, position: "end", distance: 4 }, data: [{ xAxis: opts.mark }] } : undefined }];
    // 최소값보다 작은 막대(예: 우연보다 낮은 AUC)는 축 시작점에 붙이고, 글자는 원래 값으로
    o.series[0].data.forEach((d) => { d.raw = d.value; if (opts.min !== undefined && d.value < opts.min) d.value = opts.min; });
    o.series[0].label.formatter = (s) => (opts.fmt ? opts.fmt(s.data.raw) : f.num(s.data.raw, 3));
    o.tooltip.formatter = (s) => `<b>${D.esc(s.name)}</b><br>${opts.valueLabel || T("값")} ${opts.fmt ? opts.fmt(s.data.raw) : f.num(s.data.raw, 4)}` + (data[s.dataIndex].sub ? `<br>${D.esc(data[s.dataIndex].sub)}` : "");
    el.style.height = Math.max(160, Math.min(900, data.length * 22 + 40)) + "px";
    return make(el, o);
  };

  /* 상관 행렬 (-1~1) */
  C.heatmap = function (el, names, matrix, opts = {}) {
    const p = palette();
    const o = base(p);
    const n = names.length;
    const data = [];
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) data.push([j, i, matrix[i][j]]);
    const short = names.map((s) => (s.length > 18 ? s.slice(0, 17) + "…" : s));
    o.grid = { left: 140, right: 70, top: 10, bottom: 110 };
    o.xAxis = axis(p, { type: "category", data: short, axisLabel: { color: p.text2, fontSize: 10.5, rotate: 50, interval: 0 }, splitArea: { show: false } });
    o.yAxis = axis(p, { type: "category", data: short, inverse: true, axisLabel: { color: p.text2, fontSize: 10.5, interval: 0 } });
    o.visualMap = { min: opts.min ?? -1, max: opts.max ?? 1, calculable: false, orient: "vertical", right: 6, top: "middle", itemHeight: 160,
      inRange: { color: opts.colors || ["#2f6fdf", "#9fbdf2", "#f2f3f5", "#f3b48b", "#d9541e"] }, textStyle: { color: p.muted, fontSize: 11 } };
    o.tooltip.formatter = (s) => `${D.esc(names[s.value[1]])}<br>${D.esc(names[s.value[0]])}<br><b>${f.num(s.value[2], 3)}</b>`;
    o.series = [{ type: "heatmap", data, label: { show: n <= 14, fontSize: 10, color: "#111", formatter: (s) => s.value[2].toFixed(2) },
      emphasis: { itemStyle: { borderColor: p.text, borderWidth: 1 } } }];
    el.style.height = Math.max(320, Math.min(820, n * 22 + 140)) + "px";
    const ch = make(el, o);
    if (ch && opts.onClick) ch.on("click", (s) => opts.onClick(names[s.value[1]], names[s.value[0]]));
    return ch;
  };

  /* 산점도. groups가 있으면 색으로 나눈다 */
  C.scatter = function (el, r) {
    const p = palette();
    const o = base(p);
    o.grid = { left: 64, right: 24, top: 30, bottom: 48 };
    o.xAxis = axis(p, { type: "value", name: r.x, nameLocation: "middle", nameGap: 28, scale: true, axisLabel: { color: p.muted, fontSize: 11, formatter: (v) => (r.x_date ? f.day(v) : f.num(v, 3)) } });
    o.yAxis = axis(p, { type: "value", name: r.y, nameLocation: "middle", nameGap: 46, scale: true, axisLabel: { color: p.muted, fontSize: 11, formatter: (v) => (r.y_date ? f.day(v) : f.num(v, 3)) } });
    const fmtV = (v, d) => (d ? f.day(v) : f.num(v, 5));
    o.tooltip.trigger = "item";
    o.tooltip.formatter = (s) => `${D.esc(r.x)}: ${fmtV(s.value[0], r.x_date)}<br>${D.esc(r.y)}: ${fmtV(s.value[1], r.y_date)}` + (s.seriesName && s.seriesName !== T("점") ? `<br>${D.esc(r.color)}: ${D.esc(s.seriesName)}` : "");
    if (r.groups) {
      const by = new Map();
      r.points.forEach((pt, i) => { const g = r.groups[i]; if (!by.has(g)) by.set(g, []); by.get(g).push(pt); });
      const keys = [...by.keys()].sort((a, b) => by.get(b).length - by.get(a).length);
      o.series = keys.map((k, i) => ({ name: k, type: "scatter", data: by.get(k), symbolSize: 5, itemStyle: { color: p.series[i % p.series.length], opacity: 0.6 }, large: by.get(k).length > 2000 }));
      o.legend = { top: 0, textStyle: { color: p.muted, fontSize: 11 }, type: "scroll" };
    } else {
      o.series = [{ name: T("점"), type: "scatter", data: r.points, symbolSize: 5, itemStyle: { color: p.primary, opacity: 0.5 }, large: r.points.length > 2000 }];
    }
    return make(el, o);
  };

  C.box = function (el, r) {
    const p = palette();
    const o = base(p);
    o.grid = { left: 64, right: 20, top: 20, bottom: 70 };
    const labels = r.boxes.map((b) => b.label);
    o.xAxis = axis(p, { type: "category", data: labels, axisLabel: { color: p.muted, fontSize: 11, rotate: labels.length > 8 ? 30 : 0, formatter: (v) => (v.length > 14 ? v.slice(0, 13) + "…" : v) } });
    o.yAxis = axis(p, { type: "value", name: r.y, scale: true, axisLabel: { color: p.muted, fontSize: 11, formatter: (v) => (r.y_date ? f.day(v) : f.num(v, 3)) } });
    o.tooltip.trigger = "item";
    o.tooltip.formatter = (s) => { const b = r.boxes[s.dataIndex]; const v = b.stats.map((x) => (r.y_date ? f.day(x) : f.num(x, 4)));
      return T("<b>{0}</b> ({1}행)<br>위 수염 {2}<br>3사분위 {3}<br>중앙값 {4}<br>1사분위 {5}<br>아래 수염 {6}", D.esc(b.label), f.int(b.n), v[4], v[3], v[2], v[1], v[0]); };
    o.series = [{ type: "boxplot", data: r.boxes.map((b) => b.stats), itemStyle: { color: p.train + "33", borderColor: p.train } }];
    return make(el, o);
  };

  /* 여러 계열 히스토그램/막대 (그래프 만들기) */
  C.series = function (el, r) {
    const p = palette();
    const o = base(p);
    const isHist = r.type === "hist";
    const cats = isHist ? binLabels(r.edges, r.x_date) : r.categories;
    o.grid = { left: 60, right: 20, top: r.series.length > 1 ? 34 : 18, bottom: isHist ? 40 : 70 };
    o.xAxis = axis(p, { type: "category", data: cats, axisLabel: { color: p.muted, fontSize: 11, rotate: !isHist && cats.length > 8 ? 30 : 0, hideOverlap: true, formatter: (v) => (v.length > 14 ? v.slice(0, 13) + "…" : v) } });
    o.yAxis = axis(p, { type: "value", name: T("행 수"), axisLabel: { color: p.muted, fontSize: 11, formatter: (v) => f.num(v, 3) } });
    o.tooltip.trigger = "axis";
    o.series = r.series.map((s, i) => ({ name: s.name, type: "bar", stack: r.series.length > 1 ? "s" : undefined, data: s.counts,
      barCategoryGap: isHist ? "4%" : "20%", itemStyle: { color: r.series.length > 1 ? p.series[i % p.series.length] : p.primary } }));
    if (r.series.length > 1) o.legend = { top: 0, textStyle: { color: p.muted, fontSize: 11 }, type: "scroll" };
    return make(el, o);
  };

  C.crossHeat = function (el, r) {
    const p = palette();
    const o = base(p);
    const data = [];
    let max = 1;
    r.values.forEach((row, i) => row.forEach((v, j) => { data.push([i, j, v]); max = Math.max(max, v); }));
    o.grid = { left: 120, right: 70, top: 10, bottom: 80 };
    o.xAxis = axis(p, { type: "category", data: r.xs, name: r.x, nameLocation: "middle", nameGap: 56, axisLabel: { color: p.text2, fontSize: 11, rotate: 30 } });
    o.yAxis = axis(p, { type: "category", data: r.ys, name: r.y, axisLabel: { color: p.text2, fontSize: 11 } });
    o.tooltip.formatter = (s) => D.esc(r.x) + ": " + D.esc(r.xs[s.value[0]]) + "<br>" + D.esc(r.y) + ": " + D.esc(r.ys[s.value[1]]) + "<br><b>" + f.int(s.value[2]) + T("행</b>");
    o.visualMap = { min: 0, max, right: 6, top: "middle", itemHeight: 140, inRange: { color: ["#f1f4f9", "#2f6fdf"] }, textStyle: { color: p.muted } };
    o.series = [{ type: "heatmap", data, label: { show: r.xs.length * r.ys.length <= 120, fontSize: 10, color: "#111", formatter: (s) => f.int(s.value[2]) } }];
    return make(el, o);
  };

  /* CV ↔ Public LB */
  C.cvlb = function (el, res, metricLabel, onClick) {
    const p = palette();
    const o = base(p);
    const pts = res.points || [];
    const xs = pts.map((d) => d.cv), ys = pts.map((d) => d.lb);
    const outl = new Map((res.outliers || []).map((d) => [d.id, d.kind]));
    o.grid = { left: 72, right: 24, top: 24, bottom: 52 };
    o.xAxis = axis(p, { type: "value", name: "CV (" + metricLabel + ")", nameLocation: "middle", nameGap: 30, scale: true, axisLabel: { color: p.muted, fontSize: 11, formatter: (v) => f.num(v, 5) } });
    o.yAxis = axis(p, { type: "value", name: "Public LB", nameLocation: "middle", nameGap: 56, scale: true, axisLabel: { color: p.muted, fontSize: 11, formatter: (v) => f.num(v, 5) } });
    o.tooltip.trigger = "item";
    o.tooltip.formatter = (s) => { if (s.seriesType !== "scatter") return ""; const d = pts[s.dataIndex];
      return `<b>${D.esc(d.name)}</b><br>CV ${f.score(d.cv)}<br>Public ${f.score(d.lb)}` + (d.private !== null && d.private !== undefined ? `<br>Private ${f.score(d.private)}` : ""); };
    const series = [{ type: "scatter", data: pts.map((d) => ({ value: [d.cv, d.lb], itemStyle: { color: outl.get(d.id) === "lb_lucky" ? p.warn : outl.get(d.id) === "lb_unlucky" ? p.danger : p.primary } })),
      symbolSize: 11, label: { show: pts.length <= 25, position: "right", formatter: (s) => (pts[s.dataIndex].name.length > 14 ? pts[s.dataIndex].name.slice(0, 13) + "…" : pts[s.dataIndex].name), color: p.muted, fontSize: 10.5 } }];
    if (res.fit && xs.length >= 2) {
      const lo = Math.min(...xs), hi = Math.max(...xs);
      series.push({ type: "line", data: [[lo, res.fit.slope * lo + res.fit.intercept], [hi, res.fit.slope * hi + res.fit.intercept]], symbol: "none",
        lineStyle: { color: p.muted, type: "dashed", width: 1.5 }, silent: true, tooltip: { show: false } });
    }
    o.series = series;
    const ch = make(el, o);
    if (ch && onClick) ch.on("click", (s) => { if (s.seriesType === "scatter") onClick(pts[s.dataIndex]); });
    return ch;
  };

  C.line = function (el, values, opts = {}) {
    const p = palette();
    const o = base(p);
    o.grid = { left: 64, right: 20, top: 20, bottom: 36 };
    o.xAxis = axis(p, { type: "category", data: values.map((_, i) => String(i + 1)), name: opts.xName || "" });
    o.yAxis = axis(p, { type: "value", scale: true, axisLabel: { color: p.muted, fontSize: 11, formatter: (v) => f.num(v, 5) } });
    o.tooltip.trigger = "axis";
    o.series = [{ type: "line", data: values, symbolSize: 6, lineStyle: { color: p.primary, width: 2 }, itemStyle: { color: p.primary } }];
    return make(el, o);
  };

  /* 타깃 분포 (개요) */
  C.targetDist = function (el, t, log) {
    const p = palette();
    const o = base(p);
    if (t.classes) {
      const cls = t.classes.slice(0, 30);
      o.xAxis = axis(p, { type: "category", data: cls.map((c) => c.value), axisLabel: { color: p.muted, fontSize: 11, rotate: cls.length > 8 ? 30 : 0 } });
      o.yAxis = axis(p, { type: "value", axisLabel: { color: p.muted, fontSize: 11, formatter: (v) => f.num(v, 3) } });
      o.tooltip.trigger = "axis";
      o.tooltip.formatter = (ps) => { const c = cls[ps[0].dataIndex]; return T("<b>{0}</b><br>{1}행 ({2})", D.esc(c.value), f.int(c.count), f.pct(c.rate, 1)); };
      o.series = [{ type: "bar", data: cls.map((c) => c.count), barMaxWidth: 46, itemStyle: { color: p.primary, borderRadius: [4, 4, 0, 0] },
        label: { show: cls.length <= 12, position: "top", color: p.muted, fontSize: 11, formatter: (s) => f.pct(cls[s.dataIndex].rate, 1) } }];
      if (cls.length > 8) o.grid.bottom = 70;
      return make(el, o);
    }
    const hst = log && t.log_hist ? t.log_hist : t.hist;
    if (!hst) return null;
    const cats = binLabels(hst.edges, false);
    o.xAxis = axis(p, { type: "category", data: cats, name: log ? T("log1p(타깃)") : "", axisLabel: { color: p.muted, fontSize: 11, hideOverlap: true } });
    o.yAxis = axis(p, { type: "value", axisLabel: { color: p.muted, fontSize: 11, formatter: (v) => f.num(v, 3) } });
    o.tooltip.trigger = "axis";
    o.tooltip.formatter = (ps) => { const i = ps[0].dataIndex; return T("<b>{0}</b><br>{1}행", rangeLabel(hst.edges[i], hst.edges[i + 1]), f.int(ps[0].value)); };
    o.series = [{ type: "bar", data: hst.counts, barCategoryGap: "4%", itemStyle: { color: p.primary } }];
    return make(el, o);
  };

  /* 폴드별 막대 */
  C.folds = function (el, rows, key, label, fmtFn, isRate) {
    const p = palette();
    const o = base(p);
    const vis = rows.filter((r) => r.fold >= 0);
    o.grid = { left: 60, right: 54, top: 26, bottom: 34 };
    o.xAxis = axis(p, { type: "category", data: vis.map((r) => T("폴드 ") + r.fold) });
    o.yAxis = [axis(p, { type: "value", name: T("행 수"), axisLabel: { color: p.muted, fontSize: 11, formatter: (v) => f.num(v, 3) } }),
      axis(p, { type: "value", name: label || "", splitLine: { show: false }, scale: !isRate, min: isRate ? 0 : undefined, max: isRate ? 1 : undefined, axisLabel: { color: p.muted, fontSize: 11, formatter: fmtFn || ((v) => f.num(v, 3)) } })];
    o.tooltip.trigger = "axis";
    o.series = [{ name: T("행 수"), type: "bar", data: vis.map((r) => r.rows), barMaxWidth: 40, itemStyle: { color: p.surface3 } }];
    if (key) o.series.push({ name: label, type: "line", yAxisIndex: 1, data: vis.map((r) => r[key]), symbolSize: 7, itemStyle: { color: p.primary }, lineStyle: { color: p.primary } });
    return make(el, o);
  };

  /* 적대적 검증 test 유사도 분포 */
  C.likeness = function (el, hist) {
    return C.dist(el, { type: "hist", edges: hist.edges, train: hist.train, test: hist.test });
  };

  /* 점수 분포 (LB 흔들림) */
  C.noise = function (el, r) {
    const p = palette();
    const o = base(p);
    o.grid = { left: 30, right: 30, top: 20, bottom: 36 };
    const lo = r.p05, hi = r.p95, full = r.full;
    const pad = (hi - lo) * 0.6 || Math.abs(full) * 0.01 || 0.01;
    o.xAxis = axis(p, { type: "value", min: lo - pad, max: hi + pad, axisLabel: { color: p.muted, fontSize: 11, formatter: (v) => f.num(v, 5) } });
    o.yAxis = { show: false, min: 0, max: 1 };
    o.series = [{ type: "line", data: [[lo, 0.5], [hi, 0.5]], symbol: "none", lineStyle: { color: p.primary, width: 10, opacity: 0.35 }, silent: true },
      { type: "scatter", data: [[full, 0.5]], symbolSize: 14, itemStyle: { color: p.primary }, label: { show: true, position: "top", formatter: "CV " + f.score(full), color: p.text2 } },
      { type: "scatter", data: [[lo, 0.5], [hi, 0.5]], symbol: "rect", symbolSize: [2, 22], itemStyle: { color: p.muted },
        label: { show: true, position: "bottom", color: p.muted, fontSize: 11, formatter: (s) => f.score(s.value[0]) } }];
    o.tooltip = { show: false };
    el.style.height = "130px";
    return make(el, o);
  };
})();
