/* 돋보기 화면 공통: DOM 도우미, 숫자 표시, API·작업, 라우터, 사이드바, 모달·토스트.
   빌드 없이 <script>로 순서대로 읽고, 전역 D 하나만 쓴다. (보고서 HTML에 그대로 넣기 위해) */
(function () {
  "use strict";
  const D = (window.D = window.D || {});
  D.pages = D.pages || {};
  D.STATIC = window.__DOTBOGI_STATIC__ || null;

  // ───────────────────────────── 아이콘 (직접 그린 단순 선 아이콘)
  const LOGO = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><circle cx="21" cy="32" r="18" fill="#3A86D6"/><circle cx="43" cy="32" r="18" fill="#F07A3A"/><path d="M32 17.75A18 18 0 0 1 32 46.25A18 18 0 0 1 32 17.75Z" fill="#FFFFFF"/><path d="M30.2 27.8Q30.8 23.9 33.3 22.4" fill="none" stroke="#0F2530" stroke-width="2.3" stroke-linecap="round" opacity=".5"/></svg>';
  D.logo = () => { const t = document.createElement("template"); t.innerHTML = LOGO; return t.content.firstChild; };

  const ICONS = {
    filter: '<path d="M4 5h16l-6 7.5V19l-4-2v-4.5z"/>',
    chevrons: '<path d="M17 17l-5-5 5-5"/><path d="M11 17l-5-5 5-5"/>',
    menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
    table: '<rect x="4" y="5" width="16" height="14" rx="2"/><path d="M4 10h16M10 10v9"/>',
    clock: '<circle cx="12" cy="12" r="8"/><path d="M12 8v4l3 2"/>',
    panel: '<rect x="3.5" y="4.5" width="17" height="15" rx="2"/><path d="M9 4.5v15"/>',
    lens: '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5.5 5.5"/><path d="M8 10.5h5M10.5 8v5"/>',
    home: '<path d="M4 11l8-7 8 7"/><path d="M6 10v9h12v-9"/>',
    overview: '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    shield: '<path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z"/><path d="M9 12l2 2 4-4"/>',
    columns: '<path d="M5 6h14M5 12h14M5 18h14"/><circle cx="8" cy="6" r="0.6"/><circle cx="8" cy="12" r="0.6"/>',
    versus: '<path d="M4 18V9M8 18V5M12 18v-7"/><path d="M15 18v-4M19 18V7"/>',
    explore: '<path d="M4 20h16"/><path d="M5 16l4-5 3 3 5-7 3 4"/>',
    layers: '<path d="M12 4l8 4-8 4-8-4z"/><path d="M4 12l8 4 8-4"/><path d="M4 16l8 4 8-4"/>',
    flask: '<path d="M9 3h6"/><path d="M10 3v6l-5 9a2 2 0 0 0 2 3h10a2 2 0 0 0 2-3l-5-9V3"/><path d="M7.5 15h9"/>',
    merge: '<circle cx="6" cy="6" r="2.2"/><circle cx="6" cy="18" r="2.2"/><circle cx="18" cy="12" r="2.2"/><path d="M8 7l8 4M8 17l8-4"/>',
    upload: '<path d="M7 4h7l4 4v12H7z"/><path d="M14 4v4h4"/><path d="M10 14l2 2 3-4"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    folder: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    file: '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4"/>',
    up: '<path d="M12 19V6M6 11l6-6 6 6"/>',
    alert: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.5v.5"/>',
    stop: '<circle cx="12" cy="12" r="9"/><path d="M12 7.5v6M12 16.5v.5"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
    check: '<circle cx="12" cy="12" r="9"/><path d="M8 12.5l3 3 5-6"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    download: '<path d="M12 4v11M7 10l5 5 5-5"/><path d="M5 19h14"/>',
    copy: '<rect x="8" y="8" width="11" height="11" rx="2"/><path d="M5 15V6a1 1 0 0 1 1-1h9"/>',
    trash: '<path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12"/>',
    star: '<path d="M12 4l2.4 5 5.4.6-4 3.7 1.1 5.4L12 16l-4.9 2.7 1.1-5.4-4-3.7 5.4-.6z"/>',
    play: '<path d="M8 5l11 7-11 7z"/>',
    refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    search: '<circle cx="11" cy="11" r="6"/><path d="M15.5 15.5L20 20"/>',
    link: '<path d="M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1"/><path d="M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1"/>',
    report: '<path d="M7 3h7l4 4v14H7z"/><path d="M10 13h5M10 17h5M10 9h2"/>',
    kaggle: '<path d="M8 4v16M8 13l7-8M10.5 11l5.5 9"/>',
    code: '<path d="M9 8l-4 4 4 4M15 8l4 4-4 4"/>',
  };
  D.icon = function (name, cls) {
    const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    s.setAttribute("viewBox", "0 0 24 24");
    s.setAttribute("fill", "none");
    s.setAttribute("stroke-width", "1.8");
    s.setAttribute("stroke-linecap", "round");
    s.setAttribute("stroke-linejoin", "round");
    s.setAttribute("aria-hidden", "true");
    if (cls) s.setAttribute("class", cls);
    s.innerHTML = ICONS[name] || ICONS.info;
    return s;
  };

  // ───────────────────────────── DOM 만들기
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === "class") el.className = v;
        else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
        else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
        else if (k === "dataset") Object.assign(el.dataset, v);
        else if (k === "value") el.value = v;
        else if (k === "checked") el.checked = !!v;
        else if (k === "disabled") el.disabled = !!v;
        else if (k === "selected") el.selected = !!v;
        else el.setAttribute(k, v === true ? "" : v);
      }
    }
    add(el, kids);
    return el;
  }
  function add(el, kids) {
    for (const k of kids) {
      if (k === null || k === undefined || k === false) continue;
      if (Array.isArray(k)) add(el, k);
      else if (k instanceof Node) el.appendChild(k);
      else el.appendChild(document.createTextNode(String(k)));
    }
  }
  D.h = h;
  D.clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
  D.esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ───────────────────────────── 숫자·날짜 표시
  const nf = new Intl.NumberFormat("ko-KR");
  D.fmt = {
    int(n) { return n === null || n === undefined || Number.isNaN(n) ? "–" : nf.format(Math.round(n)); },
    num(x, sig = 4) {
      if (x === null || x === undefined || Number.isNaN(x)) return "–";
      if (x === 0) return "0";
      const a = Math.abs(x);
      if (a < 1e-4) return (x < 0 ? ">-" : "<") + "0.0001";
      if (a >= 1e8) return (x / 1e8).toFixed(a >= 1e10 ? 0 : 1).replace(/\.0$/, "") + "억";
      if (a >= 1e6) return (x / 1e4).toFixed(0) + "만";
      if (Number.isInteger(x) && a < 1e6) return nf.format(x);
      const s = Number(x.toPrecision(sig));
      return a >= 1000 ? nf.format(s) : String(s);
    },
    score(x) {
      if (x === null || x === undefined || Number.isNaN(x)) return "–";
      const a = Math.abs(x);
      if (a >= 1000) return nf.format(Number(x.toFixed(1)));
      if (a >= 10) return x.toFixed(3);
      return x.toFixed(5);
    },
    pct(x, d = 1) {
      if (x === null || x === undefined || Number.isNaN(x)) return "–";
      const v = x * 100;
      if (v !== 0 && Math.abs(v) < Math.pow(10, -d)) return (v > 0 ? "<" : ">-") + Math.pow(10, -d) + "%";
      return v.toFixed(d) + "%";
    },
    mb(x) { return x === null || x === undefined ? "–" : x >= 1000 ? (x / 1000).toFixed(2) + " GB" : x >= 10 ? x.toFixed(0) + " MB" : x.toFixed(1) + " MB"; },
    bytes(n) { return n === null || n === undefined ? "" : n > 1e9 ? (n / 1e9).toFixed(1) + " GB" : n > 1e6 ? (n / 1e6).toFixed(1) + " MB" : n > 1e3 ? (n / 1e3).toFixed(0) + " KB" : n + " B"; },
    day(d) {
      if (d === null || d === undefined || Number.isNaN(d)) return "–";
      const dt = new Date(Math.round(d * 86400000));
      return dt.toISOString().slice(0, 10);
    },
    sec(s) { if (s === null || s === undefined) return "–"; return s < 1 ? "1초 미만" : s < 60 ? Math.round(s) + "초" : Math.floor(s / 60) + "분 " + Math.round(s % 60) + "초"; },
    when(iso) { if (!iso) return "–"; return iso.replace("T", " ").slice(0, 16); },
  };

  D.KIND_LABEL = { numeric: "숫자", categorical: "범주", binary: "이진", datetime: "날짜", text: "문장", id: "ID", constant: "상수" };
  D.TASK_LABEL = { binary: "이진분류", multiclass: "다중분류", regression: "회귀" };
  D.LEVEL_LABEL = { danger: "위험", warn: "주의", info: "참고", ok: "괜찮음" };
  D.LEVEL_ICON = { danger: "stop", warn: "alert", info: "info", ok: "check" };
  D.DRIFT_LABEL = { stable: "안정", watch: "조금 다름", shift: "많이 다름", unknown: "–" };
  D.DRIFT_CLASS = { stable: "ok", watch: "warn", shift: "danger", unknown: "" };
  D.kindBadge = (k) => h("span", { class: "badge kind " + k }, D.KIND_LABEL[k] || k);
  D.levelBadge = (lv) => h("span", { class: "badge " + lv }, D.LEVEL_LABEL[lv] || lv);
  D.driftBadge = (lv) => (lv && lv !== "unknown" ? h("span", { class: "badge " + D.DRIFT_CLASS[lv] }, D.DRIFT_LABEL[lv]) : h("span", { class: "faint" }, "–"));

  // ───────────────────────────── API
  const TOKEN = (document.querySelector('meta[name="dotbogi-token"]') || {}).content || "";
  D.token = TOKEN;
  let offlineShown = false;

  async function api(path, opts = {}) {
    const method = opts.body !== undefined ? "POST" : opts.method || "GET";
    let url = path;
    if (opts.params) {
      const q = new URLSearchParams();
      for (const [k, v] of Object.entries(opts.params)) if (v !== undefined && v !== null) q.set(k, v);
      const s = q.toString();
      if (s) url += (url.includes("?") ? "&" : "?") + s;
    }
    if (D.STATIC) return staticApi(url, method);
    let res;
    try {
      res = await fetch(url, {
        method,
        headers: { "Content-Type": "application/json", "X-Dotbogi-Token": TOKEN },
        body: method === "POST" ? JSON.stringify(opts.body || {}) : undefined,
      });
    } catch (e) {
      showOffline();
      throw new Error("돋보기 서버에 연결할 수 없습니다.");
    }
    hideOffline();
    let data;
    try { data = await res.json(); } catch (e) { throw new Error("서버 응답을 읽지 못했습니다 (" + res.status + ")."); }
    if (!res.ok) {
      const err = new Error(data.error || "오류가 났습니다.");
      err.detail = data.detail;
      throw err;
    }
    return data;
  }
  D.api = api;

  /* 보고서(report.py static_key)와 같은 규칙: 경로 + 정렬한 [이름, 값] 목록의 JSON */
  function staticKey(url) {
    const i = url.indexOf("?");
    if (i < 0) return url;
    const entries = [...new URLSearchParams(url.slice(i + 1)).entries()].map(([k, v]) => [k, v]);
    entries.sort((a, b) => (a[0] < b[0] ? -1 : a[0] > b[0] ? 1 : 0));
    return url.slice(0, i) + JSON.stringify(entries);
  }
  function staticApi(url, method) {
    const store = D.STATIC.responses || {};
    if (method !== "GET") {
      return Promise.reject(new Error("보고서 파일에서는 이 기능을 쓸 수 없습니다. 돋보기 프로그램에서 열어 주세요."));
    }
    const key = staticKey(url);
    if (key in store) return Promise.resolve(JSON.parse(JSON.stringify(store[key])));
    return Promise.reject(new Error("이 보고서에는 해당 내용이 들어 있지 않습니다."));
  }

  function showOffline() {
    if (offlineShown) return;
    offlineShown = true;
    const bar = h("div", { class: "offline", id: "offline" },
      D.icon("alert"), "서버와 연결이 끊겼습니다. 터미널에서 돋보기를 다시 실행한 뒤 새로고침하세요.",
      h("button", { class: "btn", onclick: () => location.reload() }, "새로고침"));
    document.body.appendChild(bar);
  }
  function hideOffline() {
    if (!offlineShown) return;
    offlineShown = false;
    const el = document.getElementById("offline");
    if (el) el.remove();
  }

  // ───────────────────────────── 오래 걸리는 작업
  const running = new Map();
  D.runJob = function (job) {
    if (!job) return Promise.resolve(null);
    return new Promise((resolve, reject) => {
      const entry = running.get(job.id) || { job, waiters: [] };
      entry.waiters.push({ resolve, reject });
      if (running.has(job.id)) return;
      running.set(job.id, entry);
      renderJobs();
      const tick = async () => {
        let j;
        try {
          j = await api("/api/job", { params: { id: job.id } });
        } catch (e) {
          running.delete(job.id); renderJobs();
          entry.waiters.forEach((w) => w.reject(e));
          return;
        }
        entry.job = j;
        renderJobs();
        if (j.state === "running") { setTimeout(tick, j.elapsed > 20 ? 900 : 450); return; }
        running.delete(job.id);
        renderJobs();
        if (j.state === "done") entry.waiters.forEach((w) => w.resolve(j.result));
        else {
          const err = new Error(j.error || "작업이 실패했습니다.");
          entry.waiters.forEach((w) => w.reject(err));
        }
      };
      setTimeout(tick, 250);
    });
  };
  /* 결과가 준비될 때까지 기다리는 GET: {ready:false, job}이면 작업을 기다렸다 다시 부른다. */
  D.ensure = async function (path, opts) {
    for (let i = 0; i < 6; i++) {
      const r = await api(path, opts);
      if (r.ready === false && r.job) { await D.runJob(r.job); continue; }
      return r;
    }
    throw new Error("결과를 준비하지 못했습니다. 새로고침해 보세요.");
  };

  function renderJobs() {
    const slot = document.getElementById("tb-jobs");
    if (!slot) return;
    D.clear(slot);
    const jobs = [...running.values()].map((r) => r.job);
    if (!jobs.length) return;
    const job = jobs[0];
    const pct = Math.round((job.progress || 0) * 100);
    const cur = D.project();
    const other = job.project && cur && job.project !== cur.root && D.state && (D.state.tabs || []).find((t) => t.root === job.project);
    slot.appendChild(h("span", { class: "job-pill", title: (job.label || "") + " · " + (job.message || "") },
      h("span", { class: "spinner sm" }), other ? h("span", { class: "job-proj" }, other.name) : null, h("b", null, job.label || "작업 중"),
      h("span", { class: "job-msg" }, job.message || ""),
      h("span", { class: "job-bar" }, h("span", { style: { width: Math.max(3, pct) + "%" } })),
      h("span", { class: "num" }, pct + "%"),
      jobs.length > 1 ? h("span", { class: "faint" }, ` 외 ${jobs.length - 1}개`) : null));
  }

  // ───────────────────────────── 토스트·모달
  D.toast = function (msg, kind = "ok", ms = 3200) {
    let box = document.getElementById("toasts");
    if (!box) { box = h("div", { class: "toasts", id: "toasts" }); document.body.appendChild(box); }
    const t = h("div", { class: "toast " + kind }, msg);
    box.appendChild(t);
    setTimeout(() => t.remove(), kind === "error" ? Math.max(ms, 6000) : ms);
  };
  D.fail = (e) => D.toast(e && e.message ? e.message : String(e), "error");

  D.modal = function ({ title, body, footer, wide, onClose }) {
    const close = () => { back.remove(); document.removeEventListener("keydown", onKey); if (onClose) onClose(); };
    const onKey = (e) => {
      if (e.key !== "Escape") return;
      const all = document.querySelectorAll(".modal-back");
      if (all[all.length - 1] === back) { e.stopPropagation(); close(); }
    };
    const back = h("div", { class: "modal-back", onmousedown: (e) => { if (e.target === back) close(); } },
      h("div", { class: "modal" + (wide ? " wide" : ""), role: "dialog", "aria-modal": "true" },
        h("div", { class: "modal-h" }, h("h3", null, title), h("span", { class: "grow" }),
          h("button", { class: "icon-btn", title: "닫기", onclick: close }, D.icon("x"))),
        h("div", { class: "modal-b" }, body),
        footer ? h("div", { class: "modal-f" }, footer) : null));
    document.body.appendChild(back);
    document.addEventListener("keydown", onKey);
    const first = back.querySelector("input, select, textarea");
    if (first) setTimeout(() => first.focus(), 30);
    return { close, el: back };
  };
  D.confirm = function (title, text, okLabel = "확인", danger = false) {
    return new Promise((resolve) => {
      let m, settled = false;
      const done = (v) => { if (settled) return; settled = true; resolve(v); m.close(); };
      m = D.modal({
        title, body: h("p", { style: { margin: "4px 0 8px" } }, text),
        footer: [h("button", { class: "btn", onclick: () => done(false) }, "취소"),
          h("button", { class: "btn " + (danger ? "danger" : "primary"), onclick: () => done(true) }, okLabel)],
        onClose: () => { if (!settled) { settled = true; resolve(false); } },
      });
    });
  };

  /* 버튼을 누르는 동안 돌아가는 표시 + 오류 토스트 */
  D.busy = async function (btn, fn) {
    if (btn) { btn.classList.add("busy"); btn.disabled = true; }
    try { return await fn(); }
    catch (e) { D.fail(e); return undefined; }
    finally { if (btn) { btn.classList.remove("busy"); btn.disabled = false; } }
  };

  D.copy = async function (text, btn) {
    try {
      await navigator.clipboard.writeText(text);
    } catch (e) {
      const ta = h("textarea", { style: { position: "fixed", left: "-9999px" } }, text);
      document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove();
    }
    D.toast("복사했습니다.");
    if (btn) { const old = btn.textContent; btn.textContent = "복사됨"; setTimeout(() => (btn.textContent = old), 1200); }
  };
  D.codeBlock = (text) => h("div", { class: "code" }, text,
    h("div", { class: "copy" }, h("button", { class: "btn sm", onclick: (e) => D.copy(text, e.currentTarget) }, "복사")));

  // 공통 상태 표시
  D.loading = (msg = "불러오는 중") => h("div", { class: "loading" }, h("span", { class: "spinner" }), msg);
  D.empty = (title, text, icon = "info", action) => h("div", { class: "empty" }, D.icon(icon), h("div", { class: "big" }, title),
    text ? h("div", null, text) : null, action ? h("div", { class: "mt12" }, action) : null);
  D.errorBox = (e, retry) => h("div", { class: "errbox" }, h("div", { class: "callout danger" }, D.icon("stop"),
    h("div", { class: "grow" }, h("div", { class: "bold" }, "불러오지 못했습니다"), h("div", null, e.message || String(e)),
      retry ? h("button", { class: "btn sm mt8", onclick: retry }, "다시 시도") : null)));
  D.callout = (kind, ...kids) => h("div", { class: "callout " + kind }, D.icon(D.LEVEL_ICON[kind] || "info"), h("div", { class: "grow" }, kids));
  D.card = (title, opts, ...body) => {
    opts = opts || {};
    return h("div", { class: "card " + (opts.class || ""), id: opts.id },
      title || opts.actions ? h("div", { class: "card-h" }, title ? h("h3", null, title) : null,
        opts.hint ? h("span", { class: "hint" }, opts.hint) : null,
        opts.actions ? h("div", { class: "actions" }, opts.actions) : null) : null,
      h("div", { class: "card-b" + (opts.flush ? " flush" : "") }, body));
  };
  D.select = (options, value, onchange, attrs = {}) => {
    const s = h("select", { class: "select " + (attrs.class || ""), onchange: (e) => onchange && onchange(e.target.value), title: attrs.title });
    for (const o of options) {
      const [v, label] = Array.isArray(o) ? o : [o, o];
      s.appendChild(h("option", { value: v ?? "", selected: String(v ?? "") === String(value ?? "") }, label));
    }
    return s;
  };
  D.seg = (options, value, onchange) => {
    const wrap = h("div", { class: "seg" });
    for (const [v, label] of options) {
      wrap.appendChild(h("button", { class: v === value ? "on" : "", type: "button", onclick: () => {
        wrap.querySelectorAll("button").forEach((b) => b.classList.remove("on"));
        wrapButtons.get(v).classList.add("on");
        onchange(v);
      } }, label));
    }
    const wrapButtons = new Map([...wrap.children].map((b, i) => [options[i][0], b]));
    return wrap;
  };
  D.barCell = (v, max = 1, hot) => h("div", { class: "bar-cell" },
    h("div", { class: "track" }, h("div", { class: "fill" + (hot ? " hot" : ""), style: { width: Math.max(0, Math.min(100, (v || 0) / (max || 1) * 100)) + "%" } })),
    h("span", null, v === null || v === undefined ? "–" : (v * 100).toFixed(0)));

  /* 정렬 가능한 표 */
  D.table = function ({ columns, rows, onRow, rowClass, sort, compact, empty, maxHeight, grid }) {
    let state = { key: sort ? sort.key : null, asc: sort ? !!sort.asc : true };
    const wrap = h("div", { class: "table-wrap", style: maxHeight ? { maxHeight } : null });
    const render = () => {
      D.clear(wrap);
      let data = rows.slice();
      if (state.key) {
        const col = columns.find((c) => c.key === state.key);
        const get = col && col.sortValue ? col.sortValue : (r) => r[state.key];
        data.sort((a, b) => {
          const va = get(a), vb = get(b);
          const na = va === null || va === undefined || Number.isNaN(va), nb = vb === null || vb === undefined || Number.isNaN(vb);
          if (na && nb) return 0; if (na) return 1; if (nb) return -1;
          if (typeof va === "number" && typeof vb === "number") return state.asc ? va - vb : vb - va;
          return state.asc ? String(va).localeCompare(String(vb), "ko") : String(vb).localeCompare(String(va), "ko");
        });
      }
      const table = h("table", { class: "t" + (compact ? " compact" : "") + (grid ? " grid-data" : "") });
      const tr = h("tr");
      for (const c of columns) {
        const sortable = c.sortable !== false && !!c.key;
        tr.appendChild(h("th", {
          class: (c.num ? "num " : "") + (sortable ? "sortable" : ""), style: c.width ? { width: c.width } : null, title: c.title,
          onclick: sortable ? () => { if (state.key === c.key) state.asc = !state.asc; else { state.key = c.key; state.asc = c.num ? false : true; } render(); } : null,
        }, c.label, state.key === c.key ? h("span", { class: "arrow" }, state.asc ? "▲" : "▼") : null));
      }
      table.appendChild(h("thead", null, tr));
      const tb = h("tbody");
      for (const r of data) {
        const row = h("tr", { class: (onRow ? "click " : "") + (rowClass ? rowClass(r) || "" : ""), onclick: onRow ? (e) => { if (!e.target.closest("button, input, a, select, .editable")) onRow(r, e); } : null });
        for (const c of columns) {
          const v = c.render ? c.render(r) : r[c.key];
          row.appendChild(h("td", { class: (c.num ? "num " : "") + (c.cls || "") }, v === null || v === undefined ? "–" : v));
        }
        tb.appendChild(row);
      }
      table.appendChild(tb);
      wrap.appendChild(table);
      if (!data.length && empty) wrap.appendChild(empty);
    };
    render();
    wrap.update = (newRows) => { rows = newRows; render(); };
    return wrap;
  };

  /* 칸을 눌러 바로 고치기 */
  D.editable = function (value, display, onSave, { type = "text", placeholder = "입력" } = {}) {
    if (D.STATIC) return h("span", null, display !== undefined && display !== null && display !== "" ? display : h("span", { class: "faint" }, "–"));
    const span = h("span", { class: "editable", title: "눌러서 고치기", role: "button", tabindex: "0", "aria-label": (placeholder || "값") + " 고치기" },
      display !== undefined && display !== null && display !== "" ? display : h("span", { class: "faint" }, placeholder));
    span.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); span.click(); } });
    span.addEventListener("click", (e) => {
      e.stopPropagation();
      const inp = h("input", { class: "cell-input", type: type === "number" ? "text" : "text", value: value ?? "", inputmode: type === "number" ? "decimal" : null });
      span.replaceWith(inp);
      inp.focus(); inp.select();
      let done = false;
      const finish = async (save) => {
        if (done) return; done = true;
        if (save && inp.value !== String(value ?? "")) {
          let v = inp.value.trim();
          if (type === "number") {
            if (v === "") v = null;
            else { v = Number(v.replace(",", ".")); if (Number.isNaN(v)) { D.toast("숫자를 입력하세요.", "error"); inp.replaceWith(span); return; } }
          }
          try { await onSave(v); } catch (err) { D.fail(err); inp.replaceWith(span); }
        } else inp.replaceWith(span);
      };
      inp.addEventListener("keydown", (ev) => { if (ev.key === "Enter") finish(true); if (ev.key === "Escape") finish(false); });
      inp.addEventListener("blur", () => finish(true));
    });
    return span;
  };

  // ───────────────────────────── 상태와 라우터
  D.state = null;
  D.refreshState = async function () {
    D.state = await api("/api/state");
    renderChrome();
    return D.state;
  };
  D.project = () => (D.state && D.state.project) || null;
  D.settings = () => (D.project() ? D.project().settings : null);

  const NAV = [
    { group: null, items: [["home", "시작", "home"]] },
    { group: "데이터 이해", items: [["overview", "개요", "overview"], ["checks", "데이터 점검", "shield"], ["columns", "컬럼", "columns"], ["sheet", "데이터 표", "table"],
      ["drift", "train vs test", "versus"], ["explore", "탐색", "explore"]] },
    { group: "모델·제출", items: [["cv", "검증 설계", "layers"], ["experiments", "실험", "flask"], ["ensemble", "앙상블", "merge"],
      ["submission", "제출 검사", "upload"]] },
    { group: null, items: [["settings", "설정", "gear"]] },
  ];
  D.navBadges = {};

  const navIcon = (name) => { for (const g of NAV) for (const it of g.items) if (it[0] === name) return it[2]; return "file"; };
  const navLabel = (name) => { for (const g of NAV) for (const it of g.items) if (it[0] === name) return it[1]; return ""; };
  const daysLeft = (proj) => {
    const comp = (proj && proj.settings.competition) || {};
    if (!comp.end_date) return null;
    return Math.ceil((new Date(comp.end_date + "T23:59:59") - new Date()) / 86400000);
  };

  /* 사이드바: 맨 위 작업공간(로고·대회), 메뉴, 맨 아래 데이터 정보·테마 */
  function renderSidebar() {
    const sb = document.getElementById("sidebar");
    if (!sb) return;
    D.clear(sb);
    const proj = D.project();
    const cur = D.route.name;
    const dark = document.documentElement.dataset.theme === "dark";
    const loaded = proj && proj.loaded;

    const wsName = D.STATIC ? (D.STATIC.project || "보고서") : loaded ? (proj.settings.name || proj.root) : "돋보기";
    const wsMeta = D.STATIC ? "읽기 전용 보고서" : loaded
      ? (D.TASK_LABEL[proj.settings.task] || "과제 미정") + ", " + ((proj.metric_info && proj.metric_info.label) || proj.settings.metric || "지표 미정")
      : "대회 데이터 분석";
    sb.appendChild(h("div", { class: "ws" },
      h("div", { class: "ws-main", role: "button", title: loaded ? proj.root : "시작 화면", onclick: () => D.go(loaded ? "settings" : "home") },
        h("span", { class: "brand-mark" }, D.logo()),
        h("div", { class: "ws-text" }, h("div", { class: "ws-name" }, wsName), h("div", { class: "ws-meta" }, wsMeta))),
      h("button", { class: "icon-btn ws-collapse", title: "사이드바 닫기 (Ctrl+B)", onclick: toggleNav }, D.icon("chevrons"))));

    if (!D.STATIC) {
      sb.appendChild(h("div", { class: "nav-item", role: "button", title: "대회 폴더 열기 (Ctrl+O)", onclick: openFolder },
        D.icon("folder"), h("span", null, "폴더 열기"), h("kbd", { class: "nav-kbd" }, "Ctrl+O")));
    }

    let n = 0;
    for (const g of NAV) {
      if (g.group) sb.appendChild(h("div", { class: "nav-group" }, g.group));
      for (const [name, label, icon] of g.items) {
        const disabled = name !== "home" && !loaded;
        if (D.STATIC && !(D.STATIC.pages || []).includes(name)) continue;
        const badge = D.navBadges[name];
        const key = ++n <= 10 ? (n % 10) : null;
        sb.appendChild(h("div", { class: "nav-item" + (cur === name ? " active" : "") + (disabled ? " disabled" : ""), role: "button",
          title: disabled ? "대회 폴더를 먼저 여세요" : label + (key !== null ? ` (Ctrl+${key})` : ""), onclick: () => { if (!disabled) D.go(name); } },
          D.icon(icon), h("span", null, label),
          badge ? h("span", { class: "nav-badge " + badge.kind }, badge.text) : null));
      }
    }

    const foot = h("div", { class: "side-foot" });
    if (loaded && !D.STATIC) {
      const sh = proj.shapes || {};
      foot.appendChild(h("div", { class: "side-info", title: proj.root, role: "button", onclick: () => D.go("settings") },
        D.icon("folder"), h("span", { class: "ellipsis" }, proj.root)));
      const sizes = [];
      if (sh.train) sizes.push(`train ${D.fmt.int(sh.train[0])}×${sh.train[1]}`);
      if (sh.test) sizes.push(`test ${D.fmt.int(sh.test[0])}×${sh.test[1]}`);
      if (sizes.length) foot.appendChild(h("div", { class: "side-info num" }, D.icon("table"), h("span", null, sizes.join(", "))));
      const d = daysLeft(proj);
      if (d !== null) foot.appendChild(h("div", { class: "side-info" + (d >= 0 && d <= 3 ? " hot" : "") }, D.icon("clock"),
        h("span", null, d >= 0 ? `마감까지 D-${d}` : "대회가 끝났습니다")));
    } else if (D.STATIC) {
      foot.appendChild(h("div", { class: "side-info" }, D.icon("clock"), h("span", null, `${D.STATIC.created_at || ""} 기준`)));
    }
    if (D.update && D.update.newer) {
      foot.appendChild(h("a", { class: "side-update", href: D.update.url, target: "_blank", rel: "noopener", title: "릴리스 페이지 열기" },
        D.icon("download"), h("span", null, `새 버전 ${D.update.latest} 받기`)));
    }
    foot.appendChild(h("div", { class: "side-bottom" },
      h("span", { class: "side-ver", title: D.state && !D.state.lightgbm ? "LightGBM을 설치하면 기본 모델이 더 빠릅니다 (pip install lightgbm)" : "" },
        D.state ? `v${D.state.version}, ${D.state.lightgbm ? "LightGBM" : "scikit-learn"}` : ""),
      h("button", { class: "icon-btn", title: dark ? "밝은 테마로" : "어두운 테마로", onclick: toggleTheme }, D.icon(dark ? "sun" : "moon"))));
    sb.appendChild(foot);
  }

  /* 위쪽 줄: 사이드바 열기, 브레드크럼(대회 / 화면), 진행 중 작업 */
  function renderTopbar(page, name) {
    const top = document.getElementById("topbar");
    if (!top) return;
    D.clear(top);
    const proj = D.project();
    top.appendChild(h("button", { class: "icon-btn open-nav", title: "사이드바 열기 (Ctrl+B)", onclick: toggleNav }, D.icon("menu")));
    const tabs = (!D.STATIC && D.state && D.state.tabs) || [];
    if (tabs.length) {
      const strip = h("div", { class: "tabs-strip", role: "tablist", "aria-label": "열린 대회" });
      for (const t of tabs) {
        const active = t.active && (name !== "home" || t.error);  // 열지 못한 대회는 시작 화면에서 파일을 고르므로 그 탭이 활성
        const tab = h("div", { class: "tab" + (active ? " active" : "") + (t.error ? " error" : ""), role: "tab", "aria-selected": active ? "true" : "false",
          title: t.root + (t.error ? "\n열지 못한 폴더입니다" : ""), onclick: () => D.switchProject(t.root),
          onauxclick: (e) => { if (e.button === 1) { e.preventDefault(); D.closeProject(t.root); } } },
        h("span", { class: "tab-logo" }, D.logo()), h("span", { class: "tab-name" }, t.name),
        h("button", { class: "tab-x", title: "탭 닫기" + (document.body.classList.contains("desktop") ? " (Ctrl+W)" : ""), "aria-label": t.name + " 탭 닫기",
          onclick: (e) => { e.stopPropagation(); D.closeProject(t.root); } }, D.icon("x")));
        strip.appendChild(tab);
      }
      strip.appendChild(h("button", { class: "tab-add", title: "대회 폴더 열기 (Ctrl+O)", "aria-label": "대회 폴더 열기", onclick: openFolder }, D.icon("plus")));
      top.appendChild(strip);
      top.appendChild(h("div", { class: "tb-jobs", id: "tb-jobs" }));
      top.appendChild(h("div", { class: "win-ctl", id: "win-ctl" }));
      renderJobs();
      renderWinCtl();
      return;
    }
    const crumbs = h("nav", { class: "crumbs", "aria-label": "위치" });
    const projName = D.STATIC ? (D.STATIC.project || "보고서") : proj && proj.loaded ? (proj.settings.name || proj.root) : null;
    if (projName && name !== "home") {
      crumbs.appendChild(h("span", { class: "crumb", role: "button", onclick: () => D.go(D.STATIC ? "overview" : "settings") },
        h("span", { class: "crumb-logo" }, D.logo()), h("span", { class: "ellipsis" }, projName)));
      crumbs.appendChild(h("span", { class: "crumb-sep" }, "/"));
    }
    crumbs.appendChild(h("span", { class: "crumb now" }, D.icon(navIcon(name)), h("span", null, page.title || navLabel(name))));
    top.appendChild(crumbs);
    if (D.STATIC) top.appendChild(h("span", { class: "badge" }, "읽기 전용"));
    top.appendChild(h("span", { class: "grow" }));
    top.appendChild(h("div", { class: "tb-jobs", id: "tb-jobs" }));
    top.appendChild(h("div", { class: "win-ctl", id: "win-ctl" }));
    renderJobs();
    renderWinCtl();
  }

  /* 데스크톱 앱 창 버튼 (제목 표시줄을 없앴을 때): 최소화 · 최대화/복원 · 닫기 */
  let frameless = false;
  const GLYPH = { min: "\uE921", max: "\uE922", restore: "\uE923", close: "\uE8BB" };
  function renderWinCtl() {
    const box = document.getElementById("win-ctl");
    if (!box) return;
    D.clear(box);
    const dk = D.desktop();
    if (!dk || !frameless) return;
    const max = document.body.classList.contains("maximized");
    box.appendChild(h("button", { class: "wc", title: "최소화", "aria-label": "최소화", onclick: () => dk.minimize() }, GLYPH.min));
    box.appendChild(h("button", { class: "wc", title: max ? "이전 크기로" : "최대화", "aria-label": max ? "이전 크기로" : "최대화", onclick: toggleMax },
      max ? GLYPH.restore : GLYPH.max));
    box.appendChild(h("button", { class: "wc close", title: "닫기", "aria-label": "닫기", onclick: () => dk.close() }, GLYPH.close));
  }
  async function syncMax() {
    const dk = D.desktop();
    if (!dk || !frameless) return;
    const m = await dk.is_maximized();
    if (m !== document.body.classList.contains("maximized")) { document.body.classList.toggle("maximized", !!m); renderWinCtl(); }
  }
  async function toggleMax() {
    const dk = D.desktop();
    if (!dk) return;
    document.body.classList.toggle("maximized", !!(await dk.toggle_maximize()));
    renderWinCtl();
  }
  // 위쪽 줄 빈 곳: 끌면 창 이동(Windows 기본 이동이라 화면 가장자리 스냅도 됨), 두 번 누르면 최대화
  let lastDown = { t: 0, x: 0, y: 0 };
  document.addEventListener("mousedown", (e) => {
    const dk = D.desktop();
    if (!dk || !frameless || e.button !== 0) return;
    const t = e.target;
    if (!t.closest || !t.closest(".topbar") || t.closest("button, a, input, select, [role='button'], .job-pill")) return;
    e.preventDefault();
    const now = Date.now();
    if (now - lastDown.t < 450 && Math.abs(e.screenX - lastDown.x) < 5 && Math.abs(e.screenY - lastDown.y) < 5) {
      lastDown = { t: 0, x: 0, y: 0 };
      toggleMax();
      return;
    }
    lastDown = { t: now, x: e.screenX, y: e.screenY };
    dk.start_drag();
  });
  window.addEventListener("resize", () => { clearTimeout(syncMax.t); syncMax.t = setTimeout(syncMax, 120); });

  function renderChrome() {
    renderSidebar();
  }
  D.renderSidebar = renderChrome;

  function toggleNav() {
    const app = document.getElementById("app");
    app.classList.toggle("nav-collapsed");
    try { localStorage.setItem("dotbogi-nav", app.classList.contains("nav-collapsed") ? "collapsed" : "open"); } catch (e) { /* 무시 */ }
  }

  async function openFolder() {
    const p = await D.browse({ mode: "folder", start: D.project() ? D.project().root : "" });
    if (p) D.busy(null, () => D.openProject(p));
  }

  /* 데스크톱 단축키: Ctrl+O 폴더 열기, Ctrl+B 탐색 접기, Ctrl+1~0 화면 이동 */
  document.addEventListener("keydown", (e) => {
    if (!(e.ctrlKey || e.metaKey) || e.altKey || document.querySelector(".modal-back")) return;
    const k = e.key.toLowerCase();
    if (e.key === "Tab") { e.preventDefault(); cycleTab(e.shiftKey ? -1 : 1); return; }
    if (k === "w" && document.body.classList.contains("desktop") && D.project()) { e.preventDefault(); D.closeProject(D.project().root); return; }
    if (k === "o" && !D.STATIC) { e.preventDefault(); openFolder(); return; }
    if (k === "b") { e.preventDefault(); toggleNav(); return; }
    if (/^[0-9]$/.test(k)) {
      const items = NAV.flatMap((g) => g.items).filter(([name]) => !D.STATIC || (D.STATIC.pages || []).includes(name));
      const idx = k === "0" ? 9 : Number(k) - 1;
      const target = items[idx];
      const proj = D.project();
      if (target && (target[0] === "home" || (proj && proj.loaded) || D.STATIC)) { e.preventDefault(); D.go(target[0]); }
    }
  });

  function toggleTheme() {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("dotbogi-theme", next); } catch (e) { /* 저장 못 해도 괜찮음 */ }
    renderChrome();
    D.render();
  }

  D.route = { name: "home", params: {} };
  function parseHash() {
    const raw = location.hash.replace(/^#\/?/, "");
    const [name, qs] = raw.split("?");
    const params = Object.fromEntries(new URLSearchParams(qs || ""));
    return { name: name || "home", params };
  }
  D.go = function (name, params) {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    const target = "#/" + name + qs;
    if (location.hash === target) D.render();
    else location.hash = target;
  };
  D.setParams = function (params) {  // 화면은 그대로 두고 주소만 바꿈
    const qs = new URLSearchParams(params).toString();
    history.replaceState(null, "", "#/" + D.route.name + (qs ? "?" + qs : ""));
    D.route.params = params;
  };

  let renderSeq = 0;
  D.render = async function () {
    const seq = ++renderSeq;
    D.route = parseHash();
    rememberRoute();
    if (D.charts) D.charts.disposeAll();
    let name = D.route.name;
    const proj = D.project();
    if (name !== "home" && !(proj && proj.loaded)) name = "home";
    if (D.STATIC && (name === "home" || !(D.STATIC.pages || []).includes(name))) name = "overview";
    const page = D.pages[name] || D.pages.home;
    renderChrome();
    renderTopbar(page, name);
    document.title = (page.title ? page.title + " - " : "") + "돋보기";
    syncTitle();
    const body = document.getElementById("content");
    D.clear(body);
    const actions = h("div", { class: "row page-actions" });
    const sub = page.subtitle ? (typeof page.subtitle === "function" ? page.subtitle() : page.subtitle) : null;
    body.appendChild(h("header", { class: "page-head" },
      h("div", { class: "page-icon" + (page.logoIcon ? " logo" : "") }, page.logoIcon ? D.logo() : D.icon(navIcon(name))),
      h("div", { class: "page-title-row" },
        h("div", { class: "grow" }, h("h1", { class: "page-title" }, page.headTitle || page.title), sub ? h("p", { class: "page-sub" }, sub) : null),
        actions)));
    const root = h("div", { class: "page" });
    body.appendChild(root);
    body.scrollTop = 0;
    try {
      await page.render(root, D.route.params, { actions, isCurrent: () => seq === renderSeq });
    } catch (e) {
      if (seq !== renderSeq) return;
      console.error(e);
      D.clear(root);
      root.appendChild(D.card(null, null, D.errorBox(e, () => D.render())));
    }
  };
  D.isCurrent = (seq) => seq === renderSeq;

  /* 탭: 대회마다 마지막으로 보던 화면을 기억했다가 돌아온다 */
  D.tabRoutes = {};
  const rememberRoute = () => {
    const p = D.project();
    if (p && p.loaded && D.route.name !== "home") D.tabRoutes[p.root] = location.hash;
  };
  D.switchProject = async function (root) {
    rememberRoute();
    try {
      await api("/api/switch", { body: { path: root } });
      await D.refreshState();
    } catch (e) { D.fail(e); return; }
    const p = D.project();
    const target = D.tabRoutes[root] || (p && p.loaded ? "#/overview" : "#/home");
    if (location.hash === target) D.render(); else location.hash = target;
  };
  D.closeProject = async function (root) {
    const wasActive = D.project() && D.project().root === root;
    delete D.tabRoutes[root];
    try {
      await api("/api/close", { body: { path: root } });
      await D.refreshState();
    } catch (e) { D.fail(e); return; }
    if (!wasActive) { D.render(); return; }
    const p = D.project();
    const target = p ? (D.tabRoutes[p.root] || (p.loaded ? "#/overview" : "#/home")) : "#/home";
    if (location.hash === target) D.render(); else location.hash = target;
  };
  function cycleTab(step) {
    const tabs = (D.state && D.state.tabs) || [];
    if (tabs.length < 2) return;
    const i = Math.max(0, tabs.findIndex((t) => t.active));
    D.switchProject(tabs[(i + step + tabs.length) % tabs.length].root);
  }

  /* 데스크톱 앱(자기 창) 연결: pywebview가 넣어 주는 window.pywebview.api */
  D.desktop = () => (window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder ? window.pywebview.api : null);
  function syncTitle() { const dk = D.desktop(); if (dk) Promise.resolve(dk.set_title(document.title)).catch(() => {}); }
  window.addEventListener("pywebviewready", async () => {
    document.body.classList.add("desktop");
    syncTitle();
    try { frameless = !!(await D.desktop().frameless()); } catch (e) { frameless = false; }
    document.body.classList.toggle("frameless", frameless);
    syncMax();
    renderWinCtl();
  });
  // 내려받기 링크: 앱 창에서는 '다른 이름으로 저장' 창으로
  document.addEventListener("click", async (e) => {
    const a = e.target.closest ? e.target.closest('a[href*="/api/download"]') : null;
    const dk = D.desktop();
    if (!a || !dk) return;
    e.preventDefault();
    const u = new URL(a.getAttribute("href"), location.href);
    try {
      const r = await dk.save_download(u.searchParams.get("exp") || "", u.searchParams.get("kind") || "submission", u.searchParams.get("path") || "");
      if (r && r.error) D.toast(r.error, "error");
      else if (r && r.path) D.toast("저장했습니다: " + r.path);
    } catch (err) { D.fail(err); }
  });

  window.addEventListener("hashchange", () => D.render());

  D.boot = async function () {
    let theme = null;
    try { theme = localStorage.getItem("dotbogi-theme"); } catch (e) { /* 무시 */ }
    if (!theme) theme = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    document.documentElement.dataset.theme = theme;
    try { if (localStorage.getItem("dotbogi-nav") === "collapsed") document.getElementById("app").classList.add("nav-collapsed"); } catch (e) { /* 무시 */ }
    if (D.STATIC) document.body.classList.add("static");
    try {
      await D.refreshState();
      for (const j of (D.state.jobs || [])) {
        D.runJob(j).then(() => D.refreshState()).then(() => D.render()).catch(D.fail);
      }
    } catch (e) {
      document.getElementById("content").appendChild(D.errorBox(e, () => location.reload()));
      return;
    }
    D.render();
    if (!D.STATIC) setTimeout(D.checkUpdate, 1500);
  };

  /* 새 버전 확인: 하루 한 번 (서버가 결과를 기억). 새 버전이면 사이드바에 표시하고 처음 한 번만 알림 */
  D.update = null;
  D.checkUpdate = async function (force) {
    try {
      const r = await api("/api/update", { params: force ? { force: "1" } : {} });
      D.update = r;
      renderChrome();
      if (r.newer) {
        let seen = null;
        try { seen = localStorage.getItem("dotbogi-update-seen"); } catch (e) { /* 무시 */ }
        if (seen !== r.latest || force) {
          D.toast(`돋보기 ${r.latest}이(가) 나왔습니다. 사이드바 아래에서 받을 수 있습니다.`, "ok", 6000);
          try { localStorage.setItem("dotbogi-update-seen", r.latest); } catch (e) { /* 무시 */ }
        }
      }
      return r;
    } catch (e) {
      if (force) throw e;
      return null;
    }
  };
})();
