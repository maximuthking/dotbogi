/* 제출 검사: 파일 검사, 안전한 자동 수정, 두 제출 비교 */
(function () {
  "use strict";
  const D = window.D;
  const h = D.h;
  const f = D.fmt;

  D.pages.submission = {
    title: "제출 검사",
    subtitle: "올리기 전에 형식 실수를 잡습니다",
    async render(root, params, ctx) {
      const proj = D.project();
      let exps = [];
      try { exps = (await D.api("/api/experiments")).experiments.filter((e) => e.has_submission); } catch (e) { /* 실험 없어도 됨 */ }
      if (!ctx.isCurrent()) return;
      const fromExp = params.exp ? exps.find((e) => e.id === params.exp) : null;

      const out = h("div");
      const field = D.pathField(params.path || "", { placeholder: "제출할 CSV 파일 경로", start: proj.root });
      const expSel = exps.length ? D.select([["", "또는 실험의 제출 파일 고르기"], ...exps.map((e) => [e.id, e.name])], fromExp ? fromExp.id : "", (v) => { if (v) check({ exp: v }); }) : null;
      const btn = h("button", { class: "btn primary", onclick: () => D.busy(btn, () => { if (expSel) expSel.value = ""; return check({ path: field.value }); }) }, "검사");
      field.input.addEventListener("keydown", (e) => { if (e.key === "Enter") btn.click(); });
      root.appendChild(D.card("제출 파일 검사", { hint: proj.shapes.sample_submission ? "sample_submission과 비교합니다" : "sample_submission이 없어 일부만 검사합니다" },
        h("div", { class: "row", style: { flexWrap: "nowrap" } }, h("div", { class: "grow" }, field), btn), expSel ? h("div", { class: "mt8" }, expSel) : null, out));

      async function check({ path, exp }) {
        if (!path && !exp) throw new Error("파일 경로를 적거나 고르세요.");
        D.clear(out).appendChild(D.loading("검사하는 중"));
        let r;
        try {
          r = await D.api("/api/submission/check", { body: exp ? { exp } : { path } });
        } catch (e) {
          D.clear(out).appendChild(D.errorBox(e));
          return;
        }
        if (!ctx.isCurrent()) return;
        field.value = r.path;
        D.setParams({ path: r.path });
        renderResult(r);
      }

      function renderResult(r) {
        D.clear(out);
        const head = r.ok
          ? D.callout("ok", h("b", null, "올려도 되는 형식입니다. "), `${f.int(r.rows)}행, 예측 컬럼 ${r.pred_cols.join(", ") || "–"}`)
          : D.callout("danger", h("b", null, "이대로 올리면 오류가 나거나 점수가 틀어질 수 있습니다. "), "아래 위험 항목을 고치세요.");
        out.append(h("div", { class: "mt12" }, head));
        const list = h("div", { class: "card mt12", style: { boxShadow: "none" } });
        for (const it of r.items) list.appendChild(D.findingRow({ ...it, columns: [] }));
        out.appendChild(list);
        if (r.fixable) {
          const fixBtn = h("button", { class: "btn primary", onclick: () => D.busy(fixBtn, async () => {
            const res = await D.api("/api/submission/fix", { body: { path: r.path } });
            if (!res.path) { D.toast("고칠 것이 없었습니다."); return; }
            D.toast("고친 파일을 저장했습니다.");
            out.appendChild(h("div", { class: "mt12" }, D.callout("ok", h("b", null, "저장: "), h("code", null, res.path), h("div", { class: "small" }, "한 일: " + res.done.join(", ")),
              h("button", { class: "btn sm mt8", onclick: () => check({ path: res.path }) }, "고친 파일 다시 검사"))));
          }) }, "안전하게 고친 파일 저장");
          out.appendChild(h("div", { class: "row mt12" }, h("span", { class: "grow small muted" }, "의미를 바꾸지 않는 것만 고칩니다: 인덱스 컬럼 삭제, 컬럼·행 순서 맞추기, 확률 범위 자르기·정규화, 음수 예측 0으로, UTF-8로 다시 저장. 원본은 그대로 둡니다."), fixBtn));
        }
        // 통계와 미리보기
        const st = Object.entries(r.stats || {});
        if (st.length) out.appendChild(h("div", { class: "mt12" }, h("div", { class: "bold small" }, "예측값 요약"),
          h("table", { class: "stats" }, h("thead", null, h("tr", null, h("th", null, "컬럼"), h("th", null, "평균"), h("th", null, "표준편차"), h("th", null, "최소"), h("th", null, "최대"), h("th", null, "고유값"))),
            h("tbody", null, st.map(([c, s]) => h("tr", null, h("td", null, c), h("td", null, f.num(s.mean)), h("td", null, f.num(s.std)), h("td", null, f.num(s.min)), h("td", null, f.num(s.max)), h("td", null, f.int(s.n_unique))))))));
        if (r.preview) {
          const t = h("table", { class: "t grid-data compact" }, h("thead", null, h("tr", null, r.preview.columns.map((c) => h("th", null, c)))),
            h("tbody", null, r.preview.rows.map((row) => h("tr", null, row.map((v) => h("td", null, v))))));
          out.appendChild(h("div", { class: "mt12" }, h("div", { class: "bold small" }, "앞부분 미리보기"), h("div", { class: "table-wrap" }, t)));
        }
      }

      // 비교
      const a = D.pathField("", { placeholder: "제출 파일 A", start: proj.root });
      const b = D.pathField("", { placeholder: "제출 파일 B", start: proj.root });
      const cmpOut = h("div");
      const cmpBtn = h("button", { class: "btn", onclick: () => D.busy(cmpBtn, async () => {
        D.clear(cmpOut);
        if (!a.value || !b.value) throw new Error("두 파일을 모두 고르세요.");
        if (a.value === b.value) throw new Error("서로 다른 두 파일을 고르세요.");
        const r = await D.api("/api/submission/compare", { body: { a: a.value, b: b.value } });
        cmpOut.appendChild(h("div", { class: "small muted mt8" }, `맞춘 행 ${f.int(r.matched_rows)}개`));
        cmpOut.appendChild(D.table({ columns: [
          { key: "column", label: "컬럼" }, { key: "pearson", label: "피어슨 상관", num: true, render: (x) => f.num(x.pearson, 4) },
          { key: "spearman", label: "순위 상관", num: true, render: (x) => f.num(x.spearman, 4) },
          { key: "mean_abs_diff", label: "평균 절대 차이", num: true, render: (x) => f.num(x.mean_abs_diff, 4) },
          { key: "changed_rate", label: "값이 다른 행", num: true, render: (x) => f.pct(x.changed_rate, 1) }], rows: r.columns, compact: true }));
        const c0 = r.columns[0];
        if (c0 && c0.spearman !== undefined && c0.spearman !== null) cmpOut.appendChild(h("div", { class: "mt8" }, D.callout(c0.spearman > 0.98 ? "info" : "ok",
          c0.spearman > 0.98 ? "두 제출이 거의 같습니다. 둘 다 최종 제출로 고르면 보험 효과가 적습니다." : "두 제출이 꽤 다릅니다. 최종 제출 2개로 고르면 서로 보험이 됩니다.")));
      }) }, "비교");
      root.appendChild(D.card("두 제출 비교", { hint: "최종 제출 2개가 서로 다른지, 수정 전후가 얼마나 바뀌었는지" },
        h("div", { class: "grid g2", style: { gap: "10px" } }, a, b), h("div", { class: "row mt8" }, h("span", { class: "grow" }), cmpBtn), cmpOut));

      if (fromExp) D.busy(btn, () => check({ exp: fromExp.id }));
      else if (params.path) D.busy(btn, () => check({ path: params.path }));
    },
  };
})();
