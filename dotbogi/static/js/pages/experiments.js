/* 실험: CV·Public·Private 대장, CV↔LB 관계, Public LB 흔들림, 최종 제출 고르기 */
(function () {
  "use strict";
  const D = window.D;
  const h = D.h;
  const f = D.fmt;
  const SOURCE = { baseline: ["기본 모델", "primary"], script: ["스크립트", "info"], manual: ["직접 입력", ""], ensemble: ["앙상블", "ok"], kaggle: ["Kaggle", "warn"] };
  const VERDICT = {
    aligned: ["ok", "CV와 Public LB가 같이 움직입니다", "CV가 오르면 LB도 오릅니다. CV를 기준으로 실험을 고르세요."],
    weak: ["warn", "CV와 Public LB의 관계가 약합니다", "Public LB는 test 일부라 우연히 흔들릴 수 있습니다. 아래 'Public LB 흔들림'으로 차이가 의미 있는지 보고, 검증 방법이 test 구조와 맞는지 검증 설계·train vs test 화면에서 확인하세요."],
    mismatch: ["danger", "CV와 Public LB가 따로 움직입니다", "검증 방법이 test가 뽑힌 방식(시간·그룹)과 다를 가능성이 큽니다. 데이터 점검의 시간·그룹 항목과 적대적 검증 결과를 확인하세요. Public LB만 보고 고르면 셰이크업 위험이 큽니다."],
    not_enough: ["info", "아직 판단할 실험이 부족합니다", "CV와 Public LB가 둘 다 있는 실험이 3개 이상이면 관계를 계산합니다."],
    unknown: ["info", "관계를 계산할 수 없습니다", "점수가 모두 같으면 상관을 잴 수 없습니다."],
  };

  D.pages.experiments = {
    title: "실험",
    subtitle: "CV와 리더보드를 한 곳에서",
    async render(root, params, ctx, again) {
      if (!again) root.appendChild(D.card(null, null, D.loading()));
      const data = await D.api("/api/experiments");
      if (!ctx.isCurrent()) return;
      D.charts.disposeAll();
      D.clear(root);
      const reload = () => D.pages.experiments.render(root, params, ctx, true);
      const exps = data.experiments;
      const hib = data.higher_is_better;
      const metricLabel = D.metricLabel();

      // 액션
      D.clear(ctx.actions);
      ctx.actions.append(...[
        h("button", { class: "btn needs-server", onclick: () => snippetModal(data) }, D.icon("code"), "스크립트로 기록"),
        data.platform === "kaggle" || (D.settings().competition || {}).slug ? h("button", { class: "btn needs-server", onclick: (e) => D.busy(e.currentTarget, async () => {
          const r = await D.api("/api/kaggle/import", { body: {} });
          D.toast(`Kaggle 제출 ${r.total}개 확인: ${r.matched}개 연결, ${r.created}개 새로 추가` + (r.skipped ? `, ${r.skipped}개(오류·채점 중) 건너뜀` : ""));
          reload();
        }) }, D.icon("kaggle"), "Kaggle 기록 가져오기") : null,
        h("button", { class: "btn primary needs-server", onclick: () => addModal(reload) }, D.icon("plus"), "실험 추가")].filter(Boolean));

      // 요약 타일
      const best = exps.find((e) => e.id === data.best_cv_id);
      const withLb = exps.filter((e) => e.lb_public !== null && e.lb_public !== undefined && !e.metric_mismatch);
      const bestLb = withLb.length ? withLb.reduce((a, b) => ((hib ? b.lb_public > a.lb_public : b.lb_public < a.lb_public) ? b : a)) : null;
      const limit = data.daily_limit;
      const left = limit ? limit - data.submissions_today : null;
      const tile = (label, main, foot, cls) => h("div", { class: "card stat" }, h("div", { class: "label" }, label), h("div", { class: "value " + (cls || "") }, main), foot ? h("div", { class: "foot ellipsis" }, foot) : null);
      root.appendChild(h("div", { class: "grid g4" },
        tile("실험", f.int(exps.length), `LB까지 있는 실험 ${withLb.length}개`),
        tile(`최고 CV (${metricLabel})`, best ? f.score(best.cv) : "–", best ? best.name : "CV가 기록된 실험이 없습니다"),
        tile("최고 Public LB", bestLb ? f.score(bestLb.lb_public) : "–", bestLb ? bestLb.name : "LB 점수를 표에 적어 넣으세요"),
        tile("오늘 제출", limit ? `${data.submissions_today} / ${limit}` : f.int(data.submissions_today),
          limit ? (left > 0 ? `오늘 ${left}번 더 낼 수 있습니다` : "오늘 제출 한도를 다 썼습니다") : "설정에서 하루 제출 한도를 적을 수 있습니다")));

      // 대장
      root.appendChild(ledgerCard(exps, data, reload));

      // CV↔LB + 최종 선택
      const g = h("div", { class: "grid g2" });
      root.appendChild(g);
      g.appendChild(cvlbCard(data, metricLabel));
      g.appendChild(finalCard(data, exps, reload));
      root.appendChild(noiseCard(exps, data));
    },
  };

  function ledgerCard(exps, data, reload) {
    const update = async (id, fields) => { await D.api("/api/experiments/update", { body: { id, fields } }); reload(); };
    const cols = [
      { key: "final", label: "", sortable: false, width: "34px", render: (e) => h("button", { class: "icon-btn needs-server", title: e.final ? "최종 제출 표시 해제" : "최종 제출로 표시", style: { color: e.final ? "#e0a100" : "var(--faint)" },
        onclick: () => update(e.id, { final: !e.final }).catch(D.fail) }, (() => { const ic = D.icon("star"); if (e.final) ic.setAttribute("fill", "currentColor"); return ic; })()) },
      { key: "name", label: "이름", render: (e) => h("div", { class: "col", style: { gap: "1px" } },
        D.editable(e.name, e.name, (v) => update(e.id, { name: v })),
        e.metric_mismatch ? h("span", { class: "tiny", style: { color: "var(--warn)" } }, `다른 지표(${e.metric})로 잰 실험`) : null) },
      { key: "cv", label: "CV", num: true, render: (e) => h("div", { class: "col", style: { gap: "0", alignItems: "flex-end" } },
        D.editable(e.cv, e.cv === null ? null : f.score(e.cv), (v) => update(e.id, { cv: v }), { type: "number", placeholder: "입력" }),
        e.cv_std ? h("span", { class: "tiny faint" }, "±" + f.score(e.cv_std)) : null) },
      { key: "lb_public", label: "Public", num: true, render: (e) => D.editable(e.lb_public, e.lb_public === null ? null : f.score(e.lb_public), (v) => update(e.id, { lb_public: v }), { type: "number", placeholder: "입력" }) },
      { key: "lb_private", label: "Private", num: true, render: (e) => D.editable(e.lb_private, e.lb_private === null ? null : f.score(e.lb_private), (v) => update(e.id, { lb_private: v }), { type: "number", placeholder: "–" }) },
      { key: "gap", label: "LB−CV", num: true, title: "Public LB에서 CV를 뺀 값", sortValue: (e) => (e.cv !== null && e.lb_public !== null ? e.lb_public - e.cv : null),
        render: (e) => (e.cv !== null && e.lb_public !== null ? h("span", { class: "small " + (((e.lb_public - e.cv) > 0) === data.higher_is_better ? "" : "muted") }, (e.lb_public - e.cv > 0 ? "+" : "") + f.score(e.lb_public - e.cv)) : h("span", { class: "faint" }, "–")) },
      { key: "created_at", label: "만든 때", render: (e) => h("span", { class: "small muted nowrap", title: e.submitted_at ? "제출: " + f.when(e.submitted_at) : "" }, f.when(e.created_at).slice(5)) },
      { key: "source", label: "출처", render: (e) => { const [l, c] = SOURCE[e.source] || [e.source, ""]; return h("span", { class: "badge " + c }, l); } },
      { key: "files", label: "파일", sortable: false, render: (e) => h("div", { class: "row", style: { gap: "4px", flexWrap: "nowrap" } },
        e.has_oof ? h("span", { class: "badge ok", title: "OOF 예측 있음 (앙상블·흔들림 계산 가능)" }, "OOF") : null,
        e.has_submission ? h("a", { class: "badge primary needs-server", href: D.downloadUrl(e.id), title: "제출 파일 내려받기" }, "제출 ↓") : null,
        e.has_submission && D.STATIC ? h("span", { class: "badge" }, "제출") : null) },
      { key: "notes", label: "메모", render: (e) => D.editable(e.notes, e.notes ? (e.notes.length > 40 ? e.notes.slice(0, 39) + "…" : e.notes) : null, (v) => update(e.id, { notes: v }), { placeholder: "메모" }) },
      { key: "del", label: "", sortable: false, render: (e) => h("button", { class: "icon-btn needs-server", title: "삭제 (휴지통으로)", onclick: async () => {
        if (await D.confirm("실험 삭제", `'${e.name}'을(를) 대장에서 뺍니다. 파일은 .dotbogi/trash로 옮겨져 되살릴 수 있습니다.`, "삭제", true)) {
          await D.api("/api/experiments/delete", { body: { id: e.id } }).catch(D.fail); reload();
        } } }, D.icon("trash")) },
    ];
    const tbl = D.table({ columns: cols, rows: exps, compact: true, sort: { key: "created_at", asc: false }, maxHeight: "520px",
      rowClass: (e) => (e.id === data.best_cv_id ? "best" : ""), onRow: (e) => detailModal(e.id),
      empty: D.empty("아직 기록된 실험이 없습니다", "검증 설계에서 기본 모델을 돌리거나, 학습 스크립트에서 dotbogi.log(...)로 기록하거나, '실험 추가'로 점수를 적어 넣으세요.", "flask") });
    return D.card("실험 대장", { hint: `${D.metricLabel()} · ${data.higher_is_better ? "높을수록" : "낮을수록"} 좋음 · 점수 칸을 눌러 바로 고칠 수 있습니다` }, tbl);
  }

  function cvlbCard(data, metricLabel) {
    const r = data.cv_lb;
    const [cls, title, text] = VERDICT[r.verdict] || VERDICT.unknown;
    const el = D.charts.el("chart");
    const card = D.card("CV ↔ Public LB", { hint: r.n ? `실험 ${r.n}개` : "" },
      h("div", { class: "callout " + cls }, D.icon(D.LEVEL_ICON[cls] || "info"), h("div", null, h("b", null, title), h("div", { class: "small" }, text))),
      r.spearman !== undefined && r.spearman !== null ? h("div", { class: "row small muted mt8", style: { gap: "14px" } },
        h("span", null, "순위 상관(스피어만) ", h("b", { style: { color: "var(--text)" } }, f.num(r.spearman, 3))),
        r.pearson !== null && r.pearson !== undefined ? h("span", null, "피어슨 ", f.num(r.pearson, 3)) : null,
        r.fit ? h("span", null, "기울기 ", f.num(r.fit.slope, 3)) : null) : null,
      r.n ? el : null,
      (r.outliers || []).length ? h("div", { class: "small mt8" }, h("b", null, "추세에서 벗어난 실험: "),
        r.outliers.map((o) => h("span", { class: "badge " + (o.kind === "lb_lucky" ? "warn" : "danger"), style: { marginRight: "6px" } },
          `${o.name} (${o.kind === "lb_lucky" ? "LB가 CV보다 좋음 → 운일 수 있음" : "LB가 CV보다 나쁨"})`))) : null);
    if (r.n) setTimeout(() => D.charts.cvlb(el, r, metricLabel, (p) => detailModal(p.id)), 0);
    return card;
  }

  function finalCard(data, exps, reload) {
    const sug = data.suggest;
    const finals = exps.filter((e) => e.final);
    const plat = data.platform;
    const body = h("div", { class: "col" });
    if (!sug.picks.length) body.appendChild(D.callout("info", (sug.reasons || []).join(" ") || "CV가 있는 실험이 생기면 추천합니다."));
    sug.picks.forEach((p, i) => {
      const e = exps.find((x) => x.id === p.id);
      body.appendChild(h("div", { class: "row", style: { padding: "8px 10px", border: "1px solid var(--border)", borderRadius: "8px", alignItems: "flex-start" } },
        h("span", { class: "badge primary" }, `${i + 1}번`),
        h("div", { class: "grow" }, h("div", { class: "bold" }, p.name), h("div", { class: "small muted" }, p.why),
          e ? h("div", { class: "small" }, `CV ${f.score(e.cv)}` + (e.lb_public !== null ? ` · Public ${f.score(e.lb_public)}` : "")) : null),
        e && !e.final ? h("button", { class: "btn sm needs-server", onclick: () => D.api("/api/experiments/update", { body: { id: e.id, fields: { final: true } } }).then(reload).catch(D.fail) }, "최종 표시") :
          h("span", { class: "badge ok" }, "표시됨")));
    });
    if (sug.tolerance) body.appendChild(h("div", { class: "tiny muted" }, `CV 차이 ${f.score(sug.tolerance)} 이내는 '거의 같음'으로 봤습니다. Public LB 흔들림을 계산하면 더 정확한 기준을 알 수 있습니다.`));
    body.appendChild(h("div", { class: "small" }, `최종 제출로 표시한 실험: ${finals.length ? finals.map((e) => e.name).join(", ") : "없음"} (대회에서 고를 수 있는 수: ${data.final_picks}개)`));
    if (plat === "dacon") body.appendChild(D.callout("warn", h("b", null, "데이콘 주의: "), "최종 제출을 고른 뒤 새 파일을 제출하면 선택이 Public 최고점 파일로 자동으로 바뀔 수 있습니다. 마지막 제출 뒤에 데이콘 화면에서 최종 선택을 다시 확인하세요."));
    if (plat === "kaggle") body.appendChild(D.callout("info", "Kaggle은 최종 제출을 직접 고르지 않으면 Public 점수 기준으로 자동 선택됩니다. 마감 전에 직접 고르세요."));
    return D.card("최종 제출 고르기", { hint: "셰이크업에 강하게" }, body);
  }

  function noiseCard(exps, data) {
    const withOof = exps.filter((e) => e.has_oof && !e.metric_mismatch);
    const out = h("div");
    if (withOof.length === 0) return D.card("Public LB 흔들림", null, D.callout("info", "OOF 예측이 있는 실험이 있어야 계산할 수 있습니다. 기본 모델이나 dotbogi.log(oof=...)로 기록한 실험에 OOF가 붙습니다."));
    let a = withOof[0].id, b = "";
    const sa = D.select(withOof.map((e) => [e.id, e.name]), a, (v) => (a = v));
    const sb = D.select([["", "(비교 안 함)"], ...withOof.map((e) => [e.id, e.name])], b, (v) => (b = v));
    const btn = h("button", { class: "btn primary", onclick: () => D.busy(btn, run) }, "계산");
    async function run() {
      const r = await D.api("/api/lbnoise", { body: { id: a, id_b: b || undefined } });
      D.clear(out);
      if (!r.ok) { out.appendChild(D.callout("warn", "점수를 계산하지 못했습니다.")); return; }
      const ea = withOof.find((e) => e.id === a), eb = withOof.find((e) => e.id === b);
      const el = D.charts.el("chart sm");
      out.appendChild(h("div", { class: "grid g2 mt12" },
        h("div", null,
          h("div", { class: "small muted" }, `Public LB ≈ ${f.int(r.rows)}행` + (r.share_assumed ? " (Public 비율을 몰라 test의 30%로 가정. 설정에서 바꿀 수 있습니다)" : ` (test의 ${f.pct(r.public_share, 0)})`)),
          h("div", { style: { fontSize: "15px", marginTop: "4px" } }, `같은 모델이라도 Public 점수는 우연히 `, h("b", null, "±" + f.score(r.std)), ` 정도 흔들립니다.`),
          h("div", { class: "small muted" }, `90% 범위 ${f.score(r.p05)} ~ ${f.score(r.p95)}`), el),
        h("div", null, r.win_rate !== undefined ? h("div", { class: "col" },
          h("div", { class: "small muted" }, `'${ea.name}' vs '${eb.name}'`),
          h("div", { style: { fontSize: "15px" } }, `Public에서 '${ea.name}'이(가) 더 좋게 나올 확률 `, h("b", null, f.pct(r.win_rate, 0))),
          h("div", { class: "small muted" }, `전체 OOF 점수 차이 ${f.score(r.full - r.full_b)}, Public 크기 표본에서의 차이 편차 ±${f.score(r.diff_std)}`),
          D.callout(Math.abs(r.win_rate - 0.5) < 0.3 ? "warn" : "ok", Math.abs(r.win_rate - 0.5) < 0.3
            ? "두 실험의 Public 순위는 운에 많이 좌우됩니다. Public LB 차이로 하나를 고르지 말고 CV를 믿으세요."
            : "이 정도 차이면 Public에서도 대체로 같은 순서가 나옵니다.")) :
          h("div", { class: "small muted" }, "두 번째 실험을 고르면, 두 실험의 Public 순위가 운에 얼마나 좌우되는지도 계산합니다."))));
      setTimeout(() => D.charts.noise(el, r), 0);
    }
    return D.card("Public LB 흔들림", { hint: "OOF에서 Public 크기만큼 무작위로 뽑아 200번 채점합니다" },
      h("div", { class: "row" }, h("div", { class: "field grow" }, h("label", null, "실험"), sa), h("div", { class: "field grow" }, h("label", null, "비교할 실험 (선택)"), sb),
        h("div", { class: "field" }, h("label", null, " "), btn)), out);
  }

  async function detailModal(id) {
    let e;
    try { e = await D.api("/api/experiment", { params: { id } }); } catch (err) { D.fail(err); return; }
    const body = h("div", { class: "col" });
    body.appendChild(h("dl", { class: "kv" },
      h("dt", null, "지표"), h("dd", null, e.metric || "–"),
      h("dt", null, "CV"), h("dd", null, f.score(e.cv) + (e.cv_std ? ` ± ${f.score(e.cv_std)}` : "")),
      h("dt", null, "Public / Private"), h("dd", null, `${f.score(e.lb_public)} / ${f.score(e.lb_private)}`),
      h("dt", null, "만든 때"), h("dd", null, f.when(e.created_at)),
      h("dt", null, "제출한 때"), h("dd", null, f.when(e.submitted_at)),
      h("dt", null, "출처"), h("dd", null, (SOURCE[e.source] || [e.source])[0]),
      h("dt", null, "ID"), h("dd", null, h("code", null, e.id))));
    if (e.notes) body.appendChild(h("div", { class: "callout info" }, D.icon("info"), h("div", null, e.notes)));
    const params = Object.entries(e.params || {}).filter(([k]) => k !== "weights");
    if (params.length) body.appendChild(h("div", null, h("div", { class: "bold small" }, "설정"),
      h("table", { class: "stats" }, h("tbody", null, params.map(([k, v]) => h("tr", null, h("td", null, k), h("td", { style: { textAlign: "left" } }, typeof v === "object" ? JSON.stringify(v) : String(v))))))));
    if (e.params && e.params.weights) body.appendChild(h("div", null, h("div", { class: "bold small" }, "앙상블 가중치"),
      h("table", { class: "stats" }, h("tbody", null, e.params.weights.map((w) => h("tr", null, h("td", null, w.name), h("td", null, f.pct(w.weight, 1))))))));
    if (e.fold_scores && e.fold_scores.length) body.appendChild(h("div", null, h("div", { class: "bold small" }, "폴드별 점수"),
      h("div", { class: "row small" }, e.fold_scores.map((s) => h("span", { class: "badge" }, `폴드 ${s.fold}: ${f.score(s.score)}`)))));
    if (e.importance && e.importance.length) {
      const el = D.charts.el("chart");
      body.appendChild(h("div", null, h("div", { class: "bold small" }, "피처 중요도"), el));
      setTimeout(() => D.charts.barH(el, e.importance.slice(0, 20).map((x) => ({ name: x.name, value: x.importance })), { left: 160, fmt: (v) => f.pct(v, 1), axisFmt: (v) => f.pct(v, 0) }), 30);
    }
    const files = e.files || {};
    body.appendChild(h("div", { class: "row needs-server" },
      files.submission ? h("a", { class: "btn sm", href: D.downloadUrl(e.id, "submission") }, D.icon("download"), "제출 파일") : null,
      files.oof ? h("a", { class: "btn sm", href: D.downloadUrl(e.id, "oof") }, D.icon("download"), "OOF (parquet)") : null,
      files.test ? h("a", { class: "btn sm", href: D.downloadUrl(e.id, "test") }, D.icon("download"), "test 예측 (parquet)") : null,
      files.submission ? h("button", { class: "btn sm needs-server", onclick: () => { m.close(); D.go("submission", { exp: e.id }); } }, "제출 파일 검사") : null));
    const m = D.modal({ title: e.name, body, wide: true });
  }

  function addModal(reload) {
    const name = h("input", { class: "input", placeholder: "예: lgbm_v3_피처12개" });
    const cv = h("input", { class: "input", placeholder: "비우면 OOF로 계산", inputmode: "decimal" });
    const lb = h("input", { class: "input", placeholder: "선택", inputmode: "decimal" });
    const priv = h("input", { class: "input", placeholder: "선택", inputmode: "decimal" });
    const notes = h("textarea", { class: "textarea", rows: "2", placeholder: "무엇을 바꿨는지" });
    const oof = D.pathField("", { placeholder: "OOF 예측 파일 (csv/parquet, 선택)" });
    const sub = D.pathField("", { placeholder: "제출 파일 (csv, 선택)" });
    const num = (el) => (el.value.trim() === "" ? null : Number(el.value.replace(",", ".")));
    const save = h("button", { class: "btn primary", onclick: () => D.busy(save, async () => {
      for (const el of [cv, lb, priv]) if (el.value.trim() && Number.isNaN(num(el))) throw new Error("점수 칸에는 숫자를 적으세요.");
      const r = await D.api("/api/experiments", { body: { name: name.value, cv: num(cv), lb_public: num(lb), lb_private: num(priv), notes: notes.value, oof_path: oof.value || undefined, submission_path: sub.value || undefined } });
      m.close();
      D.toast("실험을 추가했습니다." + (r.info && r.info.oof ? ` OOF는 ${r.info.oof}.` : "") + (r.info && r.info.cv_computed ? " CV는 OOF로 계산했습니다." : ""));
      reload();
    }) }, "추가");
    const m = D.modal({ title: "실험 추가", body: h("div", { class: "col" },
      h("div", { class: "field" }, h("label", null, "이름"), name),
      h("div", { class: "grid g3", style: { gap: "10px" } }, h("div", { class: "field" }, h("label", null, "CV"), cv), h("div", { class: "field" }, h("label", null, "Public LB"), lb), h("div", { class: "field" }, h("label", null, "Private LB"), priv)),
      h("div", { class: "field" }, h("label", null, "메모"), notes),
      h("div", { class: "field" }, h("label", null, "OOF 예측 파일"), oof, h("div", { class: "help" }, "train과 같은 행 순서이거나 ID 컬럼이 있어야 합니다. 예측 컬럼 이름은 pred 권장 (다중분류는 클래스별 컬럼)")),
      h("div", { class: "field" }, h("label", null, "제출 파일"), sub, h("div", { class: "help" }, "앙상블에 쓸 test 예측으로도 저장됩니다"))),
      footer: [h("button", { class: "btn", onclick: () => m.close() }, "취소"), save] });
  }

  function snippetModal(data) {
    D.modal({ title: "학습 스크립트에서 기록하기", wide: true, body: h("div", { class: "col" },
      h("div", null, "학습 코드 끝에 아래처럼 한 줄을 넣으면 CV·OOF·test 예측·제출 파일이 대장에 바로 기록됩니다. 돋보기 화면은 새로고침만 하면 보입니다."),
      D.codeBlock(data.snippet),
      h("ul", { class: "small", style: { margin: "0", paddingLeft: "18px" } },
        h("li", null, "oof는 train 행 순서의 예측입니다. 폴드에 안 쓰인 행은 NaN으로 두면 됩니다."),
        h("li", null, "이진분류는 양성 확률, 다중분류는 (행, 클래스) 확률 배열입니다. 클래스 순서는 개요 화면에 보이는 순서입니다."),
        h("li", null, "같은 폴드를 쓰려면 dotbogi.folds(대회폴더)로 폴드 번호를 읽으세요."),
        h("li", null, "명령줄: python -m dotbogi sub-check 제출파일.csv --project 대회폴더 (문제가 있으면 종료 코드 1)"))) });
  }
})();
