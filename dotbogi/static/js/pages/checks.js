/* 데이터 점검: 위험·주의·참고 순으로 정리된 자동 점검 결과 */
(function () {
  "use strict";
  const D = window.D;
  const T = D.t;
  const h = D.h;

  D.findingRow = function (it, compact) {
    const cols = it.columns || [];
    return h("div", { class: "finding " + it.level },
      h("div", { class: "ic" }, D.icon(D.LEVEL_ICON[it.level])),
      h("div", { class: "grow" },
        h("div", { class: "row", style: { gap: "8px" } }, h("span", { class: "title" }, it.title), compact ? null : D.levelBadge(it.level)),
        h("div", { class: "detail" }, it.detail),
        it.action ? h("div", { class: "todo" }, h("b", null, T("할 일 ")), it.action) : null,
        cols.length ? h("div", { class: "cols" }, cols.slice(0, compact ? 6 : 30).map(D.colChip),
          cols.length > (compact ? 6 : 30) ? h("span", { class: "muted small" }, T("외 {0}개", cols.length - (compact ? 6 : 30))) : null) : null));
  };

  D.pages.checks = {
    title: T("데이터 점검"),
    subtitle: T("대회에서 자주 터지는 문제를 자동으로 찾습니다"),
    async render(root, params, ctx) {
      root.appendChild(D.card(null, null, D.loading(T("점검하는 중 (컬럼 분석이 먼저 끝나야 합니다)"))));
      const chk = await D.ensure("/api/checks");
      if (!ctx.isCurrent()) return;
      D.updateCheckBadge(chk.counts);
      D.clear(root);
      const c = chk.counts;
      const tile = (lv, n, text) => h("div", { class: "card stat" }, h("div", { class: "label" }, D.levelBadge(lv)),
        h("div", { class: "value" }, n, h("small", null, T("개"))), h("div", { class: "foot" }, text));
      root.appendChild(h("div", { class: "grid g4" },
        tile("danger", c.danger, T("점수가 크게 틀어질 수 있는 문제")), tile("warn", c.warn, T("확인하고 대응할 문제")),
        tile("info", c.info, T("알아두면 좋은 사실")), tile("ok", c.ok, T("문제가 없다고 확인된 항목"))));

      const groups = [["danger", T("위험")], ["warn", T("주의")], ["info", T("참고")], ["ok", T("괜찮음")]];
      for (const [lv, label] of groups) {
        const items = chk.items.filter((it) => it.level === lv);
        if (!items.length) continue;
        root.appendChild(h("div", { class: "card" }, h("div", { class: "card-h" }, h("h3", null, label), h("span", { class: "hint" }, items.length + T("개"))),
          h("div", { class: "card-b flush" }, items.map((it) => D.findingRow(it)))));
      }
      if (!chk.items.length) root.appendChild(D.card(null, null, D.empty(T("점검할 항목이 없습니다"), null, "check")));

      const rec = chk.recommend;
      if (rec) {
        root.appendChild(D.card(T("추천 검증 방법"), { actions: h("button", { class: "btn sm primary", onclick: () => D.go("cv") }, T("검증 설계로")) },
          h("div", { class: "bold" }, T("{0} · {1}폴드", rec.label, rec.n_splits) + (rec.group_col ? T(" · 그룹: {0}", rec.group_col) : "") + (rec.time_col ? T(" · 날짜: {0}", rec.time_col) : "")),
          h("ul", { style: { margin: "6px 0 0", paddingLeft: "18px" } }, rec.reasons.map((r) => h("li", null, r)))));
      }
      root.appendChild(h("div", { class: "small muted" },
        T("누수 의심은 '컬럼 하나만으로 타깃을 맞히는 정도'를 다른 폴드로 잰 값입니다. 정말 강한 피처일 수도 있으니, test에서도 같은 방식으로 얻을 수 있는 값인지 확인하세요. "),
        T("데이콘처럼 test 정보를 전처리에 쓰지 못하게 하는 대회도 있으니, 분포 차이 결과를 전처리에 반영할 때는 대회 규칙을 먼저 보세요.")));
    },
  };
})();
