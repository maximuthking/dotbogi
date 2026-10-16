"""표준 라이브러리만 쓰는 로컬 웹 서버. 127.0.0.1에만 열고, API는 실행할 때 만든 토큰이 있어야 쓴다."""
from __future__ import annotations

import json
import mimetypes
import os
import secrets
import socket
import sys
import threading
import traceback
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .api import App
from .io import LoadError
from .utils import jsonable

STATIC = Path(__file__).parent / "static"
TOKEN = secrets.token_urlsafe(24)


def _routes(app: App):
    def q1(q, k, default=None):
        v = q.get(k)
        return v[0] if v else default

    return {
        ("GET", "/api/state"): lambda q, b: app.state(),
        ("GET", "/api/browse"): lambda q, b: app.browse(q1(q, "path")),
        ("POST", "/api/open"): lambda q, b: app.open_project(b.get("path", "")),
        ("POST", "/api/recent/forget"): lambda q, b: app.forget_recent(b.get("path", "")),
        ("POST", "/api/files"): lambda q, b: app.set_files(b),
        ("POST", "/api/reload"): lambda q, b: app.reload(),
        ("POST", "/api/settings"): lambda q, b: app.update_settings(b),
        ("GET", "/api/overview"): lambda q, b: app.overview(),
        ("GET", "/api/columns"): lambda q, b: app.columns(),
        ("GET", "/api/column"): lambda q, b: app.column(q1(q, "name", "")),
        ("GET", "/api/checks"): lambda q, b: app.checks(),
        ("GET", "/api/adversarial"): lambda q, b: app.adversarial(None),
        ("POST", "/api/adversarial"): lambda q, b: app.adversarial(b.get("exclude") or [], rerun=True),
        ("GET", "/api/cv"): lambda q, b: app.cv_info(),
        ("POST", "/api/cv/folds"): lambda q, b: app.make_folds(b),
        ("POST", "/api/baseline"): lambda q, b: app.baseline(b),
        ("GET", "/api/experiments"): lambda q, b: app.experiments(),
        ("GET", "/api/experiment"): lambda q, b: app.experiment_detail(q1(q, "id", "")),
        ("POST", "/api/experiments"): lambda q, b: app.add_experiment(b),
        ("POST", "/api/experiments/update"): lambda q, b: app.update_experiment(b.get("id", ""), b.get("fields") or {}),
        ("POST", "/api/experiments/delete"): lambda q, b: app.delete_experiment(b.get("id", "")),
        ("POST", "/api/lbnoise"): lambda q, b: app.lb_noise(b),
        ("POST", "/api/ensemble"): lambda q, b: app.ensemble(b),
        ("POST", "/api/ensemble/save"): lambda q, b: app.ensemble_save(b),
        ("POST", "/api/submission/check"): lambda q, b: app.submission_check(b.get("path", ""), b.get("exp")),
        ("POST", "/api/submission/fix"): lambda q, b: app.submission_fix(b.get("path", ""), b.get("out") or None),
        ("POST", "/api/submission/compare"): lambda q, b: app.submission_compare(b.get("a", ""), b.get("b", "")),
        ("GET", "/api/correlation"): lambda q, b: app.correlation(q1(q, "method", "spearman")),
        ("POST", "/api/explore"): lambda q, b: app.explore(b),
        ("POST", "/api/rows"): lambda q, b: app.rows(b),
        ("POST", "/api/kaggle/import"): lambda q, b: app.kaggle_import(b),
        ("POST", "/api/report"): lambda q, b: app.report(b),
        ("GET", "/api/job"): lambda q, b: _job(app, q1(q, "id", "")),
    }


def _job(app: App, job_id: str):
    j = app.jobs.get(job_id)
    if j is None:
        raise LoadError("작업을 찾을 수 없습니다. 프로그램을 다시 시작했다면 다시 실행해 주세요.")
    return j.to_dict()


class Handler(BaseHTTPRequestHandler):
    app: App = None  # type: ignore
    routes: dict = {}
    port: int = 0
    server_version = "Dotbogi"

    def log_message(self, fmt, *args):  # 터미널을 조용하게
        if os.environ.get("DOTBOGI_DEBUG"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    # ─────────────────────────── 보안: 다른 사이트가 이 서버를 부르지 못하게
    def _host_ok(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        return host in (f"127.0.0.1:{self.port}", f"localhost:{self.port}")

    def _token_ok(self, query) -> bool:
        tok = self.headers.get("X-Dotbogi-Token") or (query.get("t") or [""])[0]
        return secrets.compare_digest(tok, TOKEN)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def _handle(self, method: str):
        if not self._host_ok():
            return self._send(HTTPStatus.FORBIDDEN, b"forbidden", "text/plain")
        url = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(url.query)
        path = url.path
        if path.startswith("/api/"):
            if not self._token_ok(query):
                return self._json(HTTPStatus.FORBIDDEN, {"error": "접근 토큰이 맞지 않습니다. 화면을 새로고침하세요."})
            if path == "/api/download" and method == "GET":
                return self._download(query)
            fn = self.routes.get((method, path))
            if fn is None:
                return self._json(HTTPStatus.NOT_FOUND, {"error": "없는 기능입니다."})
            body = {}
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n > 20_000_000:
                    return self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "요청이 너무 큽니다."})
                raw = self.rfile.read(n) if n else b"{}"
                try:
                    body = json.loads(raw.decode("utf-8") or "{}")
                except (json.JSONDecodeError, UnicodeDecodeError):
                    return self._json(HTTPStatus.BAD_REQUEST, {"error": "요청 형식이 잘못됐습니다."})
            try:
                res = fn(query, body)
                return self._json(HTTPStatus.OK, jsonable(res))
            except LoadError as e:
                return self._json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
            except (ValueError, KeyError, FileNotFoundError) as e:
                msg = str(e) if not isinstance(e, KeyError) else f"찾을 수 없음: {e}"
                return self._json(HTTPStatus.BAD_REQUEST, {"error": msg})
            except Exception as e:
                traceback.print_exc()
                return self._json(HTTPStatus.INTERNAL_SERVER_ERROR,
                                  {"error": f"예상하지 못한 오류: {type(e).__name__}: {e}",
                                   "detail": traceback.format_exc()[-2000:]})
        return self._static(path)

    def _download(self, query):
        try:
            exp = (query.get("exp") or [""])[0]
            kind = (query.get("kind") or ["submission"])[0]
            if exp:
                f = self.app.experiment_file(exp, kind)
                name = f"{exp}_{f.name}"
            else:
                f = Path((query.get("path") or [""])[0])
                proj = self.app.project
                allowed = proj is not None and (f.resolve().is_relative_to(proj.root)
                                                or f.resolve().is_relative_to(proj.dir.resolve()))
                if not allowed or not f.is_file():
                    raise LoadError("받을 수 있는 파일이 아닙니다.")
                name = f.name
        except LoadError as e:
            return self._json(HTTPStatus.BAD_REQUEST, {"error": str(e)})
        data = f.read_bytes()
        self.send_response(HTTPStatus.OK)
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        quoted = urllib.parse.quote(name)
        self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quoted}")
        self.end_headers()
        self.wfile.write(data)

    def _static(self, path: str):
        if path in ("/", "/index.html"):
            html = (STATIC / "index.html").read_text(encoding="utf-8")
            html = html.replace("__DOTBOGI_TOKEN__", TOKEN)
            return self._send(HTTPStatus.OK, html.encode("utf-8"), "text/html; charset=utf-8", cache=False)
        rel = path.lstrip("/")
        if rel.startswith("static/"):
            rel = rel[len("static/"):]
        f = (STATIC / rel).resolve()
        if not str(f).startswith(str(STATIC.resolve())) or not f.is_file():
            return self._send(HTTPStatus.NOT_FOUND, "없는 파일입니다".encode("utf-8"), "text/plain; charset=utf-8")
        ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
        if f.suffix == ".js":
            ctype = "text/javascript; charset=utf-8"
        elif f.suffix == ".css":
            ctype = "text/css; charset=utf-8"
        return self._send(HTTPStatus.OK, f.read_bytes(), ctype, cache="vendor/" in rel)

    def _json(self, status, obj):
        data = json.dumps(obj, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self._send(status, data, "application/json; charset=utf-8", cache=False)

    def _send(self, status, data: bytes, ctype: str, cache: bool = False):
        try:
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "max-age=86400" if cache else "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass


def _free_port(start: int) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise OSError("빈 포트를 찾지 못했습니다.")


def make_server(path: str | None = None, port: int = 8765):
    app = App()
    if path:
        app.open_project(path)
    port = _free_port(port)
    handler = type("BoundHandler", (Handler,), {"app": app, "routes": _routes(app), "port": port})
    httpd = ThreadingHTTPServer(("127.0.0.1", port), handler)
    httpd.daemon_threads = True
    return httpd, app, port


def serve(path: str | None = None, port: int = 8765, open_browser: bool = True):
    httpd, app, port = make_server(path, port)
    url = f"http://127.0.0.1:{port}/"
    print(f"돋보기가 열렸습니다: {url}")
    print("끝내려면 이 창에서 Ctrl+C를 누르세요.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n돋보기를 종료합니다.")
    finally:
        httpd.server_close()
