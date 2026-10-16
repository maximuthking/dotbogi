/* 개요: 파일 크기, 대회 설정(타깃·과제·지표·ID), 타깃 분포, 주의할 점 */
(function () {
  "use strict";
  const D = window.D;
  const h = D.h;
  const f = D.fmt;

  D.pages.overview = {
    title: "개요",
    subtitle: () => (D.project() ? D.project().settings.name : ""),
    async render(root, params, ctx) {
      root.appendChild(D.loading("데이터 요약을 만드는 중"));
      const ov = await D.api("/api/overview");
      if (!ctx.isCurrent()) return;
      D.clear(root);
      const proj = D.project();
      const s = proj.settings;

      // 파일 타일
      const tiles = h("div", { class: "grid g4" });
      const tile = (label, dot, main, small, foot) => h("div", { class: "card stat" },
        h("div", { class: "label" }, dot ? h("span", { class: "dot " + dot }) : null, label),
        h("div", { class: "value" }, main, small ? h("small", null, small) : null), foot ? h("div", { class: "foot" }, foot) : null);
      const fl = ov.files;
      tiles.appendChild(tile("train", "train", f.int(fl.train.rows), "행", `${f.int(fl.train.cols)}열 · 메모리 ${f.mb(fl.train.memory_mb)}`));
      tiles.appendChild(fl.test ? tile("test", "test", f.int(fl.test.rows), "행", `${f.int(fl.test.cols)}열 · test/train ${f.pct(fl.test.rows / fl.train.rows, 0)}`)
        : tile("test", "test", "없음", null, "설정에서 test 파일을 지정할 수 있습니다"));
      tiles.appendChild(fl.sample_submission ? tile("제출 양식", null, f.int(fl.sample_submission.rows), "행", `컬럼 ${fl.sample_submission.cols}개`)
        : tile("제출 양식", null, "없음", null, "제출 검사가 덜 꼼꼼해집니다"));
      const kinds = Object.entries(ov.kinds).sort((a, b) => b[1] - a[1]);
      tiles.appendChild(h("div", { class: "card stat" }, h("div", { class: "label" }, "컬럼 종류"),
        h("div", { class: "row mt8", style: { gap: "6px" } }, kinds.map(([k, n]) => h("span", { class: "badge kind " + k }, `${D.KIND_LABEL[k] || k} ${n}`)))));
      root.appendChild(tiles);

      const grid = h("div", { class: "grid g-wide" });
      root.appendChild(grid);
      const left = h("div", { class: "col", style: { gap: "16px" } });
      const right = h("div", { class: "col", style: { gap: "16px" } });
      grid.append(left, right);

      // 대회 설정
      left.appendChild(settingsCard(proj, ov));
      // 타깃 분포
      if (ov.target) left.appendChild(targetCard(ov.target));
      else left.appendChild(D.card("타깃", null, D.callout("warn", "타깃 컬럼을 찾지 못했습니다. 위에서 직접 고르면 타깃 관계·예측력·기본 모델을 쓸 수 있습니다.")));

      // 주의할 점 (점검 결과 요약)
      const checkBody = h("div", null, D.loading("데이터를 점검하는 중 (처음 한 번)"));
      right.appendChild(h("div", { class: "card" }, h("div", { class: "card-h" }, h("h3", null, "주의할 점"),
        h("div", { class: "actions" }, h("button", { class: "btn sm", onclick: () => D.go("checks") }, "전체 보기"))), h("div", { class: "card-b flush" }, checkBody)));
      right.appendChild(nextSteps());

      try {
        const chk = await D.ensure("/api/checks");
        if (!ctx.isCurrent()) return;
        D.updateCheckBadge(chk.counts);
        D.clear(checkBody);
        const top = chk.items.filter((it) => it.level !== "ok").slice(0, 6);
        if (!top.length) checkBody.appendChild(h("div", { class: "card-b" }, D.callout("ok", "큰 문제는 보이지 않습니다. 그래도 컬럼별 분포와 train/test 차이를 한 번 확인하세요.")));
        for (const it of top) checkBody.appendChild(D.findingRow(it, true));
        const rec = chk.recommend;
        if (rec) checkBody.appendChild(h("div", { class: "card-b" }, h("div", { class: "callout info" }, D.icon("layers"),
          h("div", { class: "grow" }, h("b", null, "추천 검증 방법: " + rec.label + " (" + rec.n_splits + "폴드)"), h("div", { class: "small" }, rec.reasons[0] || ""),
            h("button", { class: "btn sm mt8", onclick: () => D.go("cv") }, "검증 설계로")))));
      } catch (e) {
        D.clear(checkBody).appendChild(D.errorBox(e, () => D.render()));
      }
    },
  };

  function settingsCard(proj, ov) {
    const s = proj.settings;
    const trainCols = proj.columns.filter((c) => c.in_train).map((c) => c.name);
    const allCols = proj.columns.map((c) => c.name);
    const save = async (patch, msg) => {
      try {
        await D.api("/api/settings", { body: patch });
        await D.refreshState();
        D.navBadges = {};
        D.toast(msg || "바꿨습니다. 분석을 새로 계산합니다.");
        D.render();
      } catch (e) { D.fail(e); }
    };
    const targetSel = D.select([["", "(없음)"], ...trainCols.map((c) => [c, c])], s.target[0] || "", (v) => save({ target: v ? [v] : [] }), { title: "타깃 컬럼" });
    const taskSel = D.select([["binary", "이진분류"], ["multiclass", "다중분류"], ["regression", "회귀"]], s.task, (v) => save({ task: v }));
    const metricSel = D.select(proj.metrics.map((m) => [m.key, m.label + (m.higher_is_better ? " ↑" : " ↓")]), s.metric, (v) => save({ metric: v }, "평가 지표를 바꿨습니다."));
    const idSel = D.select([["", "(없음)"], ...allCols.map((c) => [c, c])], s.id_col || "", (v) => save({ id_col: v || null }, "ID 컬럼을 바꿨습니다."));
    const mi = proj.metric_info;
    const body = h("div", { class: "col" },
      h("div", { class: "grid g2", style: { gap: "12px" } },
        h("div", { class: "field" }, h("label", null, "타깃 (맞혀야 할 값)"), targetSel),
        h("div", { class: "field" }, h("label", null, "과제 유형"), taskSel),
        h("div", { class: "field" }, h("label", null, "평가 지표"), metricSel,
          mi ? h("div", { class: "help" }, (mi.higher_is_better ? "높을수록 좋음" : "낮을수록 좋음") + " · " + ({ proba: "확률을 제출", label: "라벨을 제출", value: "값을 제출" }[mi.needs] || "")) : null),
        h("div", { class: "field" }, h("label", null, "ID (제출 파일의 행 이름)"), idSel)),
      s.task !== "regression" && s.classes && s.classes.length ? h("div", { class: "small muted" }, "클래스: ",
        s.classes.slice(0, 12).map((c, i) => h("span", { class: "badge", style: { marginRight: "4px" } }, (s.task === "binary" && i === 1 ? "양성 " : "") + String(c))),
        s.classes.length > 12 ? ` 외 ${s.classes.length - 12}개` : "") : null,
      ov.reasons && ov.reasons.length ? h("details", { class: "small muted" }, h("summary", { style: { cursor: "pointer" } }, "어떻게 추론했나요?"),
        h("ul", { style: { margin: "6px 0 0", paddingLeft: "18px" } }, ov.reasons.map((r) => h("li", null, r)))) : null,
      D.callout("info", "평가 지표는 대회 안내문과 같게 맞추세요. 대회 전용 계산식은 설정에서 파이썬 파일로 등록할 수 있습니다."));
    return D.card("대회 설정", { hint: "틀리면 바로 고치세요" }, body);
  }

  function targetCard(t) {
    const el = D.charts.el("chart");
    let log = false;
    const info = h("div", { class: "row small muted" });
    if (t.classes) {
      const minority = Math.min(...t.classes.map((c) => c.rate));
      info.append(`클래스 ${t.n_classes}개`, " · ", `가장 적은 클래스 ${f.pct(minority, 2)}`, t.missing ? ` · 비어 있는 행 ${f.int(t.missing)}개` : "");
    } else {
      info.append(`평균 ${f.num(t.mean)} · 중앙값 ${f.num(t.median)} · 표준편차 ${f.num(t.std)} · 범위 ${f.num(t.min)} ~ ${f.num(t.max)} · 왜도 ${f.num(t.skew, 3)}`,
        t.missing ? ` · 비어 있는 행 ${f.int(t.missing)}개` : "");
    }
    const actions = t.log_hist ? D.seg([["raw", "원래 값"], ["log", "log1p"]], "raw", (v) => { log = v === "log"; D.charts.disposeAll(); D.clear(el); D.charts.targetDist(el, t, log); }) : null;
    const card = D.card("타깃 분포 · " + t.name, { actions }, info, el);
    setTimeout(() => D.charts.targetDist(el, t, log), 0);
    return card;
  }

  function nextSteps() {
    const steps = [
      ["checks", "shield", "데이터 점검", "위험·주의 항목부터 확인"],
      ["drift", "versus", "train vs test", "적대적 검증으로 분포 차이 확인"],
      ["cv", "layers", "검증 설계", "폴드 파일 만들고 기본 모델로 기준 점수"],
      ["experiments", "flask", "실험", "학습 스크립트에서 dotbogi.log로 기록"],
    ];
    return D.card("다음 단계", null, h("div", { class: "col", style: { gap: "4px" } }, steps.map(([pg, ic, t, d]) =>
      h("div", { class: "recent-item", style: { borderTop: "0", padding: "8px 4px", borderRadius: "8px" }, onclick: () => D.go(pg) },
        h("div", { class: "fi", style: { width: "30px", height: "30px", borderRadius: "8px", display: "grid", placeItems: "center", background: "var(--primary-soft)", color: "var(--primary)" } }, D.icon(ic)),
        h("div", { class: "grow" }, h("div", { class: "bold" }, t), h("div", { class: "small muted" }, d))))));
  }
})();
