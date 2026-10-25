/* 데이터 표: 스프레드시트처럼 모든 행을 스크롤로 본다.
   보이는 행·열만 그리고(가로·세로 가상 스크롤), 필요한 구간만 서버에서 가져온다.
   정렬·전체 검색·조건 필터·컬럼 고르기·폭 조절·셀 복사·실험 예측과 오차 붙이기·CSV 내보내기. */
(function () {
  "use strict";
  const D = window.D;
  const T = D.t;
  const h = D.h;
  const f = D.fmt;
  const RH = 28;            // 행 높이(px)
  const CHUNK = 200;        // 한 번에 가져오는 행 수
  const MAXH = 15e6;        // 브라우저 요소 높이 한계 아래로 (이보다 길면 스크롤 위치를 비율로 바꿔 씀)
  const RN = 64;            // 행 번호 칸 폭
  const OPS = [["==", "="], ["!=", "≠"], [">", ">"], [">=", "≥"], ["<", "<"], ["<=", "≤"], ["contains", T("포함")],
    ["isnull", T("비어 있음")], ["notnull", T("값 있음")]];
  const OPL = Object.fromEntries(OPS);
  const W_KIND = { numeric: 104, binary: 84, datetime: 156, text: 260, categorical: 140, id: 116, constant: 96, pred: 132 };
  const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function fmtCell(v) {
    if (v === null || v === undefined) return null;
    if (typeof v === "number") return Number.isInteger(v) ? String(v) : String(Number(v.toPrecision(10)));
    if (typeof v === "boolean") return v ? "true" : "false";
    return String(v);
  }

  D.pages.sheet = {
    title: T("데이터 표"),
    subtitle: T("모든 행을 스프레드시트처럼 봅니다. 정렬·검색·필터, 실험의 예측과 오차를 옆에 붙여 볼 수 있습니다"),
    async render(root, params, ctx) {
      const proj = D.project();
      const st = {
        which: params.which || "train", exp: params.exp || "", search: params.q || "", filters: [], sort: null, asc: true,
        cols: [], order: [], hidden: new Set(), widths: {}, matched: 0, total: 0,
        chunks: new Map(), pending: new Set(), qv: 0, sel: null,
      };

      // ── 도구 줄
      const sources = [["train", "train"], ...(proj.shapes.test ? [["test", "test"]] : []),
        ...(proj.shapes.sample_submission ? [["sample_submission", T("제출 양식")]] : [])];
      const seg = D.seg(sources, st.which, (v) => { st.which = v; st.exp = v === "train" ? st.exp : ""; expSel.disabled = v !== "train"; if (v !== "train") expSel.value = ""; st.filters = []; st.sort = null; renderChips(); query(); });
      const expSel = h("select", { class: "select sm", title: T("실험의 OOF 예측과 오차를 train 옆에 붙입니다"), disabled: st.which !== "train",
        onchange: () => { st.exp = expSel.value; query(true); } }, h("option", { value: "" }, T("예측 붙이지 않음")));
      D.api("/api/experiments").then((r) => {
        for (const e of r.experiments || []) if (e.has_oof) expSel.appendChild(h("option", { value: e.id, selected: e.id === st.exp }, `${e.name}${e.cv != null ? " · CV " + f.score(e.cv) : ""}`));
        if (expSel.options.length === 1) expSel.title = T("OOF가 있는 실험이 아직 없습니다");
      }).catch(() => {});
      const search = h("input", { class: "input sm sheet-search", placeholder: T("모든 열에서 찾기"), value: st.search, "aria-label": T("모든 열에서 찾기") });
      let searchT = 0;
      search.addEventListener("input", () => { clearTimeout(searchT); searchT = setTimeout(() => { st.search = search.value.trim(); query(); }, 350); });
      const filterBtn = h("button", { class: "btn sm", onclick: (e) => openFilter(e.currentTarget) }, D.icon("filter"), T("필터"));
      const colBtn = h("button", { class: "btn sm", onclick: (e) => openColumns(e.currentTarget) }, D.icon("columns"), T("컬럼"));
      const exportBtn = h("button", { class: "btn sm", title: T("지금 보이는 결과(필터·정렬·보이는 열)를 CSV로"), onclick: () => D.busy(exportBtn, exportCsv) }, D.icon("download"), T("CSV 내보내기"));
      const chips = h("div", { class: "row sheet-chips" });

      // ── 표
      const colgroup = h("colgroup");
      const thead = h("thead");
      const tbody = h("tbody");
      const table = h("table", { class: "sheet" }, colgroup, thead, tbody);
      const scroller = h("div", { class: "sheet-scroll", tabindex: "0", role: "grid", "aria-label": T("데이터 표") }, table);
      const cellRef = h("span", { class: "sheet-ref" });
      const cellVal = h("span", { class: "sheet-val" });
      const status = h("span", { class: "sheet-status num" });
      const foot = h("div", { class: "sheet-foot" }, cellRef, cellVal, status);
      const card = h("div", { class: "card sheet-card" },
        h("div", { class: "sheet-tools" }, seg, expSel, search, filterBtn, colBtn, h("span", { class: "grow" }), exportBtn), chips, scroller, foot);
      root.appendChild(card);

      const fit = () => {
        const top = scroller.getBoundingClientRect().top;
        scroller.style.height = Math.max(240, window.innerHeight - top - foot.offsetHeight - 28) + "px";
        draw();
      };
      window.addEventListener("resize", fit);
      const alive = () => ctx.isCurrent() && document.body.contains(scroller);

      // ── 서버에서 가져오기
      const body = (offset, limit) => ({ which: st.which, exp: st.exp || null, search: st.search, filters: st.filters, sort: st.sort, asc: st.asc, offset, limit });
      async function query(fromExp) {
        const qv = ++st.qv;
        const justAdded = st.justAdded;
        st.justAdded = false;
        st.chunks.clear(); st.pending.clear(); st.sel = null;
        status.textContent = T("불러오는 중…");
        try {
          const r = await D.api("/api/sheet", { body: body(0, CHUNK) });
          if (qv !== st.qv || !alive()) return;
          const prevNames = st.cols.map((c) => c.name).join("|");
          st.cols = r.columns; st.matched = r.matched; st.total = r.total;
          st.chunks.set(0, { rows: r.rows, pos: r.positions });
          if (st.cols.map((c) => c.name).join("|") !== prevNames) layoutColumns(fromExp);
          scroller.scrollTop = 0;
          renderHead(); fit(); updateStatus();
          if (fromExp && st.exp) D.toast(T("오차 열의 머리글을 누르면 가장 크게 틀린 행부터 볼 수 있습니다."), "ok", 4500);
        } catch (e) {
          if (qv !== st.qv) return;
          if (justAdded && st.filters.length) { st.filters.pop(); renderChips(); }  // 방금 넣은 필터가 잘못됐으면 되돌림
          D.fail(e); status.textContent = "";
        }
      }
      async function ensure(first, last) {
        const qv = st.qv;
        for (let k = Math.floor(first / CHUNK); k <= Math.floor(Math.max(first, last) / CHUNK); k++) {
          if (st.chunks.has(k) || st.pending.has(k) || k * CHUNK >= st.matched) continue;
          st.pending.add(k);
          D.api("/api/sheet", { body: body(k * CHUNK, CHUNK) }).then((r) => {
            if (qv !== st.qv || !alive()) return;
            st.pending.delete(k);
            st.chunks.set(k, { rows: r.rows, pos: r.positions });
            draw();
          }).catch((e) => { st.pending.delete(k); if (qv === st.qv) D.fail(e); });
        }
      }
      const rowAt = (i) => { const c = st.chunks.get(Math.floor(i / CHUNK)); return c ? { row: c.rows[i % CHUNK], pos: c.pos[i % CHUNK] } : null; };

      // ── 열 배치
      function layoutColumns(extraFirst) {
        const idx = st.cols.map((_, i) => i);
        const extra = idx.filter((i) => st.cols[i].extra);
        const rest = idx.filter((i) => !st.cols[i].extra);
        st.order = extraFirst || extra.length ? [...extra, ...rest] : rest;
        for (const c of st.cols) if (!st.widths[c.name]) {
          const base = W_KIND[c.kind] || 128;
          st.widths[c.name] = Math.min(320, Math.max(base, c.name.length * 8 + 46));
        }
      }
      const visible = () => st.order.filter((i) => !st.hidden.has(st.cols[i].name));

      function renderHead() {
        const vis = visible();
        const tr = h("tr", null, h("th", { class: "rn" }, "#"));
        tr.appendChild(h("th", { class: "sp sp-l" }));
        for (const ci of vis) {
          const c = st.cols[ci];
          const sorted = st.sort === c.name;
          const th = h("th", { class: (c.numeric ? "num " : "") + (c.extra ? "extra " : "") + (sorted ? "sorted" : ""), "data-ci": ci,
            title: c.name + (c.role === "target" ? T(" (타깃)") : c.role === "id" ? " (ID)" : "") + T("\n누르면 정렬 (오름 → 내림 → 원래 순서)") },
          h("span", { class: "th-name" }, c.name),
          c.role === "target" ? h("span", { class: "badge primary" }, T("타깃")) : c.extra ? h("span", { class: "badge ok" }, T("예측")) : null,
          sorted ? h("span", { class: "arrow" }, st.asc ? "▲" : "▼") : null,
          h("span", { class: "rz", title: T("끌어서 폭 바꾸기"), onmousedown: (e) => startResize(e, c.name) }));
          th.addEventListener("click", (e) => { if (e.target.classList.contains("rz")) return; cycleSort(c.name); });
          tr.appendChild(th);
        }
        tr.appendChild(h("th", { class: "sp sp-r" }));
        D.clear(thead).appendChild(tr);
        colsRange = null;
      }
      function cycleSort(name) {
        if (st.sort !== name) { st.sort = name; st.asc = true; } else if (st.asc) st.asc = false; else st.sort = null;
        renderHead(); query();
      }

      // ── 그리기 (보이는 행·열만)
      let colsRange = null;
      let raf = 0;
      function draw() { if (!raf) raf = requestAnimationFrame(() => { raf = 0; paint(); }); }
      scroller.addEventListener("scroll", draw, { passive: true });

      function paint() {
        if (!alive()) return;
        const vis = visible();
        const widths = vis.map((ci) => st.widths[st.cols[ci].name]);
        const totalW = widths.reduce((a, b) => a + b, 0);
        // 가로: 보이는 열 범위
        const sl = scroller.scrollLeft, vw = scroller.clientWidth - RN;
        let x = 0, c0 = 0, c1 = vis.length - 1;
        for (let i = 0; i < vis.length; i++) { if (x + widths[i] >= sl) { c0 = i; break; } x += widths[i]; }
        const leftW = x;
        let x2 = leftW;
        for (let i = c0; i < vis.length; i++) { x2 += widths[i]; if (x2 >= sl + vw) { c1 = i; break; } }
        c0 = Math.max(0, c0 - 1); c1 = Math.min(vis.length - 1, c1 + 1);
        const lw = widths.slice(0, c0).reduce((a, b) => a + b, 0);
        const rw = widths.slice(c1 + 1).reduce((a, b) => a + b, 0);
        table.style.width = (RN + totalW) + "px";
        // 머리글·열 폭: 범위가 바뀔 때만 다시
        const key = c0 + ":" + c1 + ":" + vis.length + ":" + totalW;
        if (key !== colsRange) {
          colsRange = key;
          D.clear(colgroup);
          colgroup.appendChild(h("col", { style: { width: RN + "px" } }));
          colgroup.appendChild(h("col", { style: { width: lw + "px" } }));
          for (let i = c0; i <= c1; i++) colgroup.appendChild(h("col", { style: { width: widths[i] + "px" } }));
          colgroup.appendChild(h("col", { style: { width: rw + "px" } }));
          const ths = [...thead.querySelectorAll("th[data-ci]")];
          ths.forEach((th, i) => { th.style.display = i >= c0 && i <= c1 ? "" : "none"; });
        }
        // 세로: 보이는 행 범위 (아주 길면 비율로)
        const n = st.matched;
        const full = n * RH;
        const H = Math.min(full, MAXH);
        const vh = scroller.clientHeight - RH;
        const visRows = Math.ceil(vh / RH) + 2;
        let first, topPad;
        const stp = scroller.scrollTop;
        if (full <= MAXH) { first = Math.floor(stp / RH); topPad = first * RH; }
        else { const frac = stp / Math.max(1, H - vh); first = Math.min(n - visRows, Math.round(frac * (n - visRows))); topPad = stp; }
        first = Math.max(0, first);
        const last = Math.min(n - 1, first + visRows);
        ensure(first, last);
        let html = `<tr class="sp"><td colspan="${c1 - c0 + 4}" style="height:${topPad}px"></td></tr>`;
        for (let i = first; i <= last; i++) {
          const r = rowAt(i);
          html += `<tr data-r="${i}"><td class="rn">${r ? f.int(r.pos + 1) : ""}</td><td class="sp"></td>`;
          for (let k = c0; k <= c1; k++) {
            const ci = vis[k];
            const col = st.cols[ci];
            const v = r ? fmtCell(r.row[ci]) : undefined;
            const isSel = st.sel && st.sel.r === i && st.sel.c === k;
            const cls = (col.numeric ? "num" : "") + (v === null ? " n" : "") + (isSel ? " sel" : "") + (col.extra ? " extra" : "");
            html += `<td class="${cls}" data-c="${k}">${v === undefined ? '<span class="ld"></span>' : v === null ? "" : esc(v)}</td>`;
          }
          html += `<td class="sp"></td></tr>`;
        }
        const bottom = Math.max(0, H - topPad - (last - first + 1) * RH);
        html += `<tr class="sp"><td colspan="${c1 - c0 + 4}" style="height:${bottom}px"></td></tr>`;
        tbody.innerHTML = html;
        updateFoot();
      }

      // ── 셀 고르기·키보드·복사
      tbody.addEventListener("mousedown", (e) => {
        const td = e.target.closest("td[data-c]");
        const tr = e.target.closest("tr[data-r]");
        if (!td || !tr) return;
        st.sel = { r: Number(tr.dataset.r), c: Number(td.dataset.c) };
        scroller.focus({ preventScroll: true });
        paint();
      });
      scroller.addEventListener("keydown", (e) => {
        if (!st.sel) return;
        const vis = visible();
        const page = Math.max(1, Math.floor((scroller.clientHeight - RH) / RH) - 1);
        const mv = { ArrowDown: [1, 0], ArrowUp: [-1, 0], ArrowRight: [0, 1], ArrowLeft: [0, -1], PageDown: [page, 0], PageUp: [-page, 0] }[e.key];
        if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "c") {
          const v = selValue();
          if (v !== undefined) { navigator.clipboard.writeText(v === null ? "" : v).then(() => D.toast(T("셀 값을 복사했습니다."))).catch(() => {}); }
          e.preventDefault(); return;
        }
        if (!mv) return;
        e.preventDefault();
        st.sel = { r: Math.max(0, Math.min(st.matched - 1, st.sel.r + mv[0])), c: Math.max(0, Math.min(vis.length - 1, st.sel.c + mv[1])) };
        reveal(); paint();
      });
      function reveal() {
        const n = st.matched;
        if (n * RH <= MAXH) {
          const y = st.sel.r * RH, vh = scroller.clientHeight - RH;
          if (y < scroller.scrollTop) scroller.scrollTop = y;
          else if (y + RH > scroller.scrollTop + vh) scroller.scrollTop = y + RH - vh;
        }
        const vis = visible();
        let x = 0;
        for (let i = 0; i < st.sel.c; i++) x += st.widths[st.cols[vis[i]].name];
        const w = st.widths[st.cols[vis[st.sel.c]].name], vw = scroller.clientWidth - RN;
        if (x < scroller.scrollLeft) scroller.scrollLeft = x;
        else if (x + w > scroller.scrollLeft + vw) scroller.scrollLeft = x + w - vw;
      }
      function selValue() {
        if (!st.sel) return undefined;
        const r = rowAt(st.sel.r);
        if (!r) return undefined;
        return fmtCell(r.row[visible()[st.sel.c]]);
      }
      function updateFoot() {
        if (!st.sel) { cellRef.textContent = ""; cellVal.textContent = T("셀을 누르면 전체 값이 여기에 나옵니다. 화살표로 움직이고 Ctrl+C로 복사합니다."); cellVal.classList.add("faint"); return; }
        const r = rowAt(st.sel.r);
        const col = st.cols[visible()[st.sel.c]];
        cellRef.textContent = `${r ? f.int(r.pos + 1) + T("행") : ""} · ${col ? col.name : ""}`;
        const v = selValue();
        cellVal.classList.toggle("faint", v === null || v === undefined);
        cellVal.textContent = v === undefined ? T("불러오는 중…") : v === null ? T("비어 있음") : v;
        cellVal.title = v || "";
      }
      function updateStatus() {
        const parts = [st.matched === st.total ? T("{0}행", f.int(st.total)) : T("{0}행 중 {1}행", f.int(st.total), f.int(st.matched))];
        const nVis = visible().length;
        parts.push(nVis === st.cols.length ? T("열 {0}개", st.cols.length) : T("열 {0}개 중 {1}개", st.cols.length, nVis));
        if (st.sort) parts.push(T("정렬 {0} {1}", st.sort, st.asc ? "▲" : "▼"));
        status.textContent = parts.join(" · ");
      }

      // ── 폭 조절
      function startResize(e, name) {
        e.preventDefault(); e.stopPropagation();
        const x0 = e.clientX, w0 = st.widths[name];
        const move = (ev) => { st.widths[name] = Math.max(48, Math.min(900, w0 + ev.clientX - x0)); colsRange = null; paint(); };
        const up = () => { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); document.body.classList.remove("resizing"); };
        document.body.classList.add("resizing");
        document.addEventListener("mousemove", move);
        document.addEventListener("mouseup", up);
      }

      // ── 작은 팝업 (필터·컬럼)
      function popover(anchor, content) {
        document.querySelectorAll(".pop").forEach((x) => x.remove());
        const pop = h("div", { class: "pop", role: "dialog" }, content);
        document.body.appendChild(pop);
        const r = anchor.getBoundingClientRect();
        pop.style.top = (r.bottom + 6) + "px";
        pop.style.left = Math.min(r.left, window.innerWidth - pop.offsetWidth - 12) + "px";
        const close = (ev) => {
          if (ev.type === "keydown" && ev.key !== "Escape") return;
          if (ev.type === "mousedown" && (pop.contains(ev.target) || anchor.contains(ev.target))) return;
          pop.remove(); document.removeEventListener("mousedown", close, true); document.removeEventListener("keydown", close, true);
        };
        setTimeout(() => { document.addEventListener("mousedown", close, true); document.addEventListener("keydown", close, true); });
        pop.close = () => { pop.remove(); document.removeEventListener("mousedown", close, true); document.removeEventListener("keydown", close, true); };
        return pop;
      }
      function openFilter(anchor) {
        const names = st.order.map((i) => st.cols[i].name);
        const col = D.select(names.map((n) => [n, n]), st.sel ? st.cols[visible()[st.sel.c]].name : names[0], null, { class: "sm" });
        const op = D.select(OPS, "==", () => { val.disabled = ["isnull", "notnull"].includes(op.value); }, { class: "sm" });
        const val = h("input", { class: "input sm", placeholder: T("값"), style: { width: "150px" } });
        const add = h("button", { class: "btn primary sm", onclick: () => {
          const needs = !["isnull", "notnull"].includes(op.value);
          if (needs && !val.value.trim()) { D.toast(T("비교할 값을 적으세요."), "error"); return; }
          st.filters.push({ col: col.value, op: op.value, value: val.value.trim() });
          st.justAdded = true;
          pop.close(); renderChips(); query();
        } }, T("추가"));
        val.addEventListener("keydown", (e) => { if (e.key === "Enter") add.click(); });
        const pop = popover(anchor, h("div", { class: "col" }, h("b", null, T("조건 필터")), h("div", { class: "row", style: { flexWrap: "nowrap" } }, col, op, val, add)));
        val.focus();
      }
      function openColumns(anchor) {
        const q = h("input", { class: "input sm", placeholder: T("컬럼 이름으로 찾기") });
        const list = h("div", { class: "pop-list" });
        const fill = () => {
          D.clear(list);
          const term = q.value.trim().toLowerCase();
          for (const i of st.order) {
            const c = st.cols[i];
            if (term && !c.name.toLowerCase().includes(term)) continue;
            const cb = h("input", { type: "checkbox", checked: !st.hidden.has(c.name), onchange: () => {
              if (cb.checked) st.hidden.delete(c.name); else st.hidden.add(c.name);
              renderHead(); paint(); updateStatus();
            } });
            list.appendChild(h("label", { class: "check pop-item" }, cb, h("span", { class: "ellipsis grow" }, c.name), c.extra ? h("span", { class: "badge ok" }, T("예측")) : D.kindBadge(c.kind)));
          }
        };
        q.addEventListener("input", fill);
        const all = (show) => { if (show) st.hidden.clear(); else st.order.forEach((i) => st.hidden.add(st.cols[i].name)); fill(); renderHead(); paint(); updateStatus(); };
        popover(anchor, h("div", { class: "col", style: { width: "280px" } }, q,
          h("div", { class: "row" }, h("button", { class: "btn sm", onclick: () => all(true) }, T("모두 보이기")), h("button", { class: "btn sm", onclick: () => all(false) }, T("모두 숨기기"))), list));
        fill(); q.focus();
      }
      function renderChips() {
        D.clear(chips);
        chips.style.display = st.filters.length ? "" : "none";
        st.filters.forEach((fl, i) => chips.appendChild(h("span", { class: "chip on", title: T("눌러서 지우기"), onclick: () => { st.filters.splice(i, 1); renderChips(); query(); } },
          fl.op === "isnull" || fl.op === "notnull" ? `${fl.col} ${OPL[fl.op]}` : `${fl.col} ${OPL[fl.op]} ${fl.value}`, h("span", { class: "x" }, "×"))));
        if (st.filters.length > 1) chips.appendChild(h("button", { class: "btn ghost sm", onclick: () => { st.filters = []; renderChips(); query(); } }, T("모두 지우기")));
      }

      // ── 내보내기
      async function exportCsv() {
        const cols = visible().map((i) => st.cols[i].name);
        const r = await D.api("/api/sheet/export", { body: { ...body(0, 1), columns: cols } });
        const a = h("a", { href: `/api/download?path=${encodeURIComponent(r.path)}&t=${encodeURIComponent(D.token)}`, download: "" });
        document.body.appendChild(a); a.click(); a.remove();
        D.toast(T("{0}행 × {1}열을 CSV로 만들었습니다.", f.int(r.rows), r.columns));
      }

      renderChips();
      await query(!!st.exp);
    },
  };
})();
