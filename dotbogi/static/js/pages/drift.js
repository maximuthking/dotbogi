/* train vs test: 적대적 검증과 컬럼별 분포 차이 순위 */
(function () {
  "use strict";
  const D = window.D;
  const h = D.h;
  const f = D.fmt;
  const LEVEL = { same: ["ok", "거의 같음"], slight: ["info", "약간 다름"], moderate: ["warn", "꽤 다름"], large: ["danger", "크게 다름"] };

  D.pages.drift = {
    title: "train vs test",
    subtitle: "두 데이터가 같은 방식으로 뽑혔는지",
    async render(root, params, ctx) {
      const proj = D.project();
      if (!proj.shapes.test) {
        root.appendChild(D.card(null, null, D.empty("test 파일이 없습니다", "설정에서 test 파일을 지정하면 비교할 수 있습니다.", "versus",
          h("button", { class: "btn", onclick: () => D.go("settings") }, "설정으로"))));
        return;
      }
      const advCard = h("div", { class: "card" });
      root.appendChild(advCard);
      const driftCard = h("div", { class: "card" }, h("div", { class: "card-b" }, D.loading("컬럼별 분포 차이를 계산하는 중")));
      root.appendChild(driftCard);

      // 적대적 검증
      let exclude = [];
      async function renderAdv(result) {
        D.clear(advCard);
        const head = h("div", { class: "card-h" }, h("h3", null, "적대적 검증"),
          h("span", { class: "hint" }, "train 행과 test 행을 구분하는 모델을 만들어 봅니다"));
        advCard.appendChild(head);
        const body = h("div", { class: "card-b" });
        advCard.appendChild(body);
        const runBtn = h("button", { class: "btn primary needs-server", onclick: () => D.busy(runBtn, run) }, D.icon("play"), result ? "다시 실행" : "실행하기");
        if (!result) {
          body.appendChild(h("div", { class: "row" }, h("div", { class: "grow muted" },
            "두 데이터를 섞어 '이 행은 test인가?'를 맞히는 모델을 학습합니다. AUC가 0.5에 가까우면 둘이 구분되지 않는다는 뜻이고(좋음), 1에 가까우면 무작위 K-Fold 점수가 리더보드보다 낙관적일 수 있습니다. 보통 수 초~1분 걸립니다."), runBtn));
          return;
        }
        const r = result.result;
        const [cls, label] = LEVEL[r.level] || ["", r.level];
        const exChips = h("div", { class: "row", style: { gap: "6px" } });
        const renderEx = () => {
          D.clear(exChips);
          if (!exclude.length) exChips.appendChild(h("span", { class: "small muted" }, "아래 표에서 컬럼을 눌러 빼고 다시 실행할 수 있습니다."));
          for (const c of exclude) exChips.appendChild(h("span", { class: "chip on", onclick: () => { exclude = exclude.filter((x) => x !== c); renderEx(); } }, c, h("span", { class: "x" }, "×")));
        };
        renderEx();
        const top = h("div", { class: "grid g3" },
          h("div", { class: "col" }, h("div", { class: "muted small" }, "구분 AUC (0.5 = 구분 안 됨)"),
            h("div", { class: "row" }, h("span", { class: "hero-num" }, r.auc.toFixed(3)), h("span", { class: "badge " + cls }, label)),
            h("div", { class: "small muted" }, `폴드별 편차 ±${r.auc_std.toFixed(3)} · train ${f.int(r.n_train_used)}행, test ${f.int(r.n_test_used)}행 사용 · ${r.engine === "lightgbm" ? "LightGBM" : "HistGradientBoosting"} · ${f.sec(r.seconds)}`)),
          h("div", { class: "col", style: { gridColumn: "span 2" } }, D.callout(cls === "ok" ? "ok" : cls === "danger" ? "danger" : cls === "warn" ? "warn" : "info", r.advice),
            result.exclude && result.exclude.length ? h("div", { class: "small muted" }, "이번 결과에서 뺀 컬럼: " + result.exclude.join(", ")) : null));
        body.appendChild(top);
        body.appendChild(h("div", { class: "sep" }));
        const impEl = D.charts.el("chart");
        const likeEl = D.charts.el("chart sm");
        const share = r.test_like_share;
        body.appendChild(h("div", { class: "grid g2" },
          h("div", null, h("div", { class: "bold small" }, "무엇이 train과 test를 가르나 (모델 중요도)"), impEl),
          h("div", null, h("div", { class: "row" }, h("div", { class: "bold small grow" }, "행마다 'test 같은 정도' 분포"),
            h("div", { class: "legend" }, h("span", { class: "item" }, h("span", { class: "dot train" }), "train 행"), h("span", { class: "item" }, h("span", { class: "dot test" }), "test 행"))),
            likeEl,
            h("div", { class: "small muted" }, share !== null && share !== undefined ? [`test 행의 중간값보다 'test 같은' train 행: `, h("b", null, f.pct(share, 1)), " (차이가 없으면 약 50%)"] : null),
            r.scores_file ? h("div", { class: "small muted mt8" }, "train 행별 점수 저장: ", h("code", null, r.scores_file), " → 점수가 높은 train 행으로 검증 세트를 만들 수 있습니다.") : null)));
        setTimeout(() => {
          D.charts.barH(impEl, r.features.slice(0, 15).map((x) => ({ name: x.name, value: x.importance, sub: `혼자서 구분 AUC ${f.num(x.single_auc, 3)} · ${x.encoding}` })),
            { left: 160, valueLabel: "중요도", fmt: (v) => f.pct(v, 1), axisFmt: (v) => f.pct(v, 0) });
          D.charts.likeness(likeEl, r.hist);
        }, 0);
        body.appendChild(h("div", { class: "sep" }));
        const featRows = r.features.map((x) => ({ ...x }));
        const tbl = D.table({
          columns: [
            { key: "name", label: "컬럼", render: (x) => h("span", { class: "bold" }, x.name) },
            { key: "importance", label: "구분 기여", num: true, render: (x) => f.pct(x.importance, 1) },
            { key: "single_auc", label: "혼자서 구분 AUC", num: true, render: (x) => h("span", { class: x.single_auc >= 0.7 ? "badge danger" : x.single_auc >= 0.6 ? "badge warn" : "" }, f.num(x.single_auc, 3)) },
            { key: "encoding", label: "모델 입력", sortable: false, render: (x) => h("span", { class: "small muted" }, x.encoding) },
            { key: "act", label: "", sortable: false, render: (x) => h("button", { class: "btn sm needs-server", onclick: () => { if (!exclude.includes(x.name)) { exclude.push(x.name); renderEx(); } } }, "빼고 보기") },
          ],
          rows: featRows, compact: true, sort: { key: "importance", asc: false }, maxHeight: "360px",
          onRow: (x) => D.go("columns", { name: x.name }),
        });
        body.appendChild(h("div", { class: "row" }, h("div", { class: "bold small" }, "컬럼별 결과"), h("span", { class: "grow" }), exChips, runBtn));
        body.appendChild(h("div", { class: "mt8" }, tbl));
        const sk = Object.entries(r.skipped || {});
        if (sk.length) body.appendChild(h("div", { class: "tiny muted mt8" }, "비교에서 빠진 컬럼: " + sk.map(([k, v]) => `${k}(${v})`).join(", ")));
      }
      async function run() {
        const r = await D.api("/api/adversarial", { body: { exclude } });
        await D.runJob(r.job);
        const res = await D.api("/api/adversarial");
        if (ctx.isCurrent()) { D.charts.disposeAll(); await renderAdv(res); renderDriftTable(); }
      }

      let cols = null;
      function renderDriftTable() {
        if (!cols) return;
        D.clear(driftCard);
        const rows = cols.filter((c) => c.in_train && c.in_test && c.role === "feature" && c.psi !== null && c.psi !== undefined);
        const counts = { shift: 0, watch: 0, stable: 0 };
        rows.forEach((r) => (counts[r.drift] = (counts[r.drift] || 0) + 1));
        driftCard.appendChild(h("div", { class: "card-h" }, h("h3", null, "컬럼별 분포 차이"),
          h("span", { class: "hint" }, `많이 다름 ${counts.shift}개 · 조금 다름 ${counts.watch}개 · 안정 ${counts.stable}개`)));
        driftCard.appendChild(h("div", { class: "card-b" }, D.table({
          columns: [
            { key: "name", label: "컬럼", render: (r) => h("span", { class: "bold" }, r.name) },
            { key: "kind", label: "종류", render: (r) => D.kindBadge(r.kind) },
            { key: "psi", label: "PSI", num: true, render: (r) => f.num(r.psi, 3) },
            { key: "drift", label: "판정", sortValue: (r) => ({ shift: 2, watch: 1, stable: 0 }[r.drift] ?? -1), render: (r) => D.driftBadge(r.drift) },
            { key: "unseen_rate", label: "test 새 범주", num: true, render: (r) => (r.unseen_rate ? f.pct(r.unseen_rate, 1) : h("span", { class: "faint" }, "–")) },
            { key: "missing_gap", label: "결측 (train→test)", num: true, sortValue: (r) => Math.abs((r.missing_test || 0) - (r.missing_train || 0)),
              render: (r) => `${f.pct(r.missing_train, 1)} → ${f.pct(r.missing_test, 1)}` },
          ],
          rows, compact: true, sort: { key: "psi", asc: false }, maxHeight: "520px", onRow: (r) => D.go("columns", { name: r.name }),
          empty: D.empty("비교할 컬럼이 없습니다", null),
        }), h("div", { class: "tiny muted mt8" }, "PSI(Population Stability Index): 0.1 미만은 안정, 0.1~0.25는 조금 다름, 0.25 이상은 많이 다름으로 봅니다. 결측 비율 차이도 포함해 계산합니다.")));
      }

      advCard.appendChild(h("div", { class: "card-b" }, D.loading()));
      try {
        const [adv, colRes] = await Promise.all([D.api("/api/adversarial"), D.ensureProfiles()]);
        if (!ctx.isCurrent()) return;
        cols = colRes.columns;
        if (adv.exclude) exclude = [...adv.exclude];
        await renderAdv(adv.ready ? adv : null);
        renderDriftTable();
      } catch (e) {
        D.clear(advCard).appendChild(D.errorBox(e, () => D.render()));
      }
    },
  };
})();
