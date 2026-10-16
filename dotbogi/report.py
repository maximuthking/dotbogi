"""HTML 보고서: 화면 코드를 한 파일에 넣고, 서버 응답 대신 미리 계산한 결과를 넣는다.
원본 데이터 행은 넣지 않는다(요약만) → 가볍고 인터넷·서버 없이 열린다."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .utils import jsonable

STATIC = Path(__file__).parent / "static"


class _Progress:
    """작업 객체가 없을 때(명령줄) 쓰는 대용품"""
    def __init__(self, job=None):
        self.job = job

    def update(self, frac, msg=None):
        if self.job is not None:
            self.job.update(frac, msg)


def static_key(path: str, params: dict | None = None) -> str:
    """화면(core.js staticApi)과 같은 규칙으로 만든 응답 키"""
    if not params:
        return path
    items = sorted([[str(k), str(v)] for k, v in params.items() if v is not None])
    return path + json.dumps(items, ensure_ascii=False, separators=(",", ":"))


def build_report(app, out_path: Path | None = None, job=None, run_adversarial: bool = False) -> dict:
    prog = _Progress(job)
    p = app.require()
    out_path = Path(out_path) if out_path else p.dir / f"report-{time.strftime('%Y%m%d-%H%M')}.html"

    prog.update(0.02, "컬럼 분석 확인")
    if "profiles" not in p.cache and not app.profiles_status().get("ready"):
        app._profiles_job(_Inner(prog, 0.02, 0.5), p)
    prog.update(0.5, "데이터 점검")
    if "checks" not in p.cache:
        app._checks_job(_Inner(prog, 0.5, 0.65), p)
    if run_adversarial and p.test is not None and not p.cache.get("adv:last"):
        prog.update(0.65, "적대적 검증")
        app._adv_job(_Inner(prog, 0.65, 0.85), p, [], "adv:")

    prog.update(0.86, "보고서 내용 모으기")
    res: dict = {}
    state = app.state()
    state["recent"] = []
    state["jobs"] = []
    res["/api/state"] = state
    res["/api/overview"] = app.overview()
    res["/api/columns"] = app.columns()
    for c in p.columns:
        res[static_key("/api/column", {"name": c.name})] = app.column(c.name)
    res["/api/checks"] = app.checks()
    pages = ["overview", "checks", "columns", "explore", "cv", "experiments"]
    if p.test is not None:
        adv = app.adversarial(None)
        res["/api/adversarial"] = adv if adv.get("ready") else {"ready": False, "job": None}
        pages.insert(3, "drift")
    try:
        res["/api/cv"] = app.cv_info()
    except Exception:
        pages.remove("cv")
    try:
        res["/api/correlation"] = app.correlation()
    except Exception:
        pass
    exps = app.experiments()
    res["/api/experiments"] = exps
    for e in exps["experiments"]:
        res[static_key("/api/experiment", {"id": e["id"]})] = app.experiment_detail(e["id"])

    payload = {"created_at": time.strftime("%Y-%m-%d %H:%M"), "project": p.settings["name"], "pages": pages,
               "responses": jsonable(res)}
    html = _assemble(payload)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    prog.update(1.0, "완료")
    return {"path": str(out_path), "bytes": out_path.stat().st_size}


class _Inner:
    """내부 작업의 진행률을 보고서 전체 진행률의 일부 구간으로 바꿔 준다."""
    def __init__(self, prog: _Progress, lo: float, hi: float):
        self.prog, self.lo, self.hi = prog, lo, hi

    def update(self, frac, msg=None):
        self.prog.update(self.lo + (self.hi - self.lo) * float(frac), msg)


def _safe_script(text: str) -> str:
    return text.replace("</script", "<\\/script").replace("</SCRIPT", "<\\/SCRIPT")


def _assemble(payload: dict) -> str:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "css" / "style.css").read_text(encoding="utf-8")
    html = html.replace('<link rel="stylesheet" href="/static/css/style.css">', f"<style>\n{css}\n</style>")
    html = html.replace("__DOTBOGI_TOKEN__", "")
    m = re.search(r"<!-- DOTBOGI-SCRIPTS.*?-->(.*?)<!-- /DOTBOGI-SCRIPTS -->", html, re.S)
    if not m:
        raise RuntimeError("index.html에서 스크립트 목록을 찾지 못했습니다.")
    srcs = re.findall(r'<script src="/static/([^"]+)"></script>', m.group(1))
    data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    parts = [f"<script>window.__DOTBOGI_STATIC__ = {data};</script>"]
    for src in srcs:
        code = (STATIC / src).read_text(encoding="utf-8")
        parts.append(f"<script>/* {src} */\n{_safe_script(code)}\n</script>")
    html = html[: m.start()] + "\n".join(parts) + html[m.end():]
    html = html.replace("<title>돋보기</title>", f"<title>돋보기 보고서 · {_esc(payload['project'])}</title>")
    return html


def _esc(s: str) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
