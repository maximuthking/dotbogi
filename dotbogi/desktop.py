"""돋보기 데스크톱 앱: 브라우저 없이 자기 창(Windows는 WebView2) 안에 화면을 띄운다.

구조 (VS Code·노션 데스크톱 앱처럼 둘로 나눔)
- 창 프로세스: WebView2 창만 띄운다. Windows 제목 표시줄은 없애고 화면 맨 위 줄이 제목 표시줄 역할을 한다.
- 분석 엔진 프로세스: 같은 프로그램을 --server로 한 번 더 실행해 데이터 분석과 로컬 서버(127.0.0.1)를 맡는다.
  창과 분석 라이브러리(LightGBM 등)가 한 프로세스에 있으면 묶은 exe에서 충돌이 나서 나눴고,
  무거운 분석 중에도 창이 멈추지 않는다. 창을 닫거나 창 프로세스가 죽으면 엔진도 스스로 끝난다.
- 폴더·파일 고르기와 내려받기는 운영체제 기본 창(열기·다른 이름으로 저장)을 쓴다.
- pywebview가 없으면 예전처럼 Edge/Chrome 앱 창이나 브라우저 탭으로 연다.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import urllib.request
from pathlib import Path

HOME = Path(os.environ.get("DOTBOGI_HOME", Path.home() / ".dotbogi"))
TABLE_TYPES = ("Table files (*.csv;*.tsv;*.txt;*.parquet;*.xlsx;*.xls;*.feather)", "All files (*.*)")
WIN = sys.platform == "win32"


def available() -> bool:
    try:
        import webview  # noqa: F401
    except Exception:
        return False
    return True


def _existing_dir(start: str) -> str:
    if not start:
        return ""
    p = Path(start)
    if p.is_file():
        p = p.parent
    return str(p) if p.is_dir() else ""


def _system_dark() -> bool:
    if not WIN:
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def _quiet_streams(name: str = "desktop.log"):
    """콘솔 없는 실행(pythonw, exe)에서는 표준 출력이 없으므로 로그 파일로 보낸다."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        HOME.mkdir(parents=True, exist_ok=True)
        log = open(HOME / name, "a", encoding="utf-8", buffering=1)
    except OSError:
        log = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = log
    if sys.stderr is None:
        sys.stderr = log


# ───────────────────────────── Win32: 제목 표시줄 없애기, 끌어서 옮기기
class _Win32:
    GWL_STYLE = -16
    WS_CAPTION, WS_THICKFRAME, WS_SYSMENU = 0x00C00000, 0x00040000, 0x00080000
    WS_MINIMIZEBOX, WS_MAXIMIZEBOX = 0x00020000, 0x00010000
    SWP_FLAGS = 0x0001 | 0x0002 | 0x0004 | 0x0020  # NOSIZE | NOMOVE | NOZORDER | FRAMECHANGED

    def __init__(self):
        import ctypes
        from ctypes import wintypes
        self.c = ctypes
        self.u = ctypes.windll.user32
        self.u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        self.u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.u.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        self.u.SendMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.u.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.u.IsZoomed.argtypes = [wintypes.HWND]
        self.u.MonitorFromPoint.restype = ctypes.c_void_p
        self.u.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        try:
            self.dwm = ctypes.windll.dwmapi
        except OSError:
            self.dwm = None

    def hide_caption(self, hwnd: int):
        s = self.u.GetWindowLongPtrW(hwnd, self.GWL_STYLE)
        s = (s & ~self.WS_CAPTION) | self.WS_THICKFRAME | self.WS_SYSMENU | self.WS_MINIMIZEBOX | self.WS_MAXIMIZEBOX
        self.u.SetWindowLongPtrW(hwnd, self.GWL_STYLE, s)
        self.u.SetWindowPos(hwnd, None, 0, 0, 0, 0, self.SWP_FLAGS)
        if self.dwm is not None:  # Windows 11 둥근 모서리 유지
            pref = self.c.c_int(2)
            self.dwm.DwmSetWindowAttribute(self.c.c_void_p(hwnd), 33, self.c.byref(pref), 4)

    def drag(self, hwnd: int, on_maximize=None):
        """마우스 왼쪽 버튼이 눌린 동안 커서를 따라 창을 옮긴다 (화면 스크립트의 mousedown에서 시작).
        최대화 상태면 원래 크기로 돌아가며 커서 아래에 오고, 화면 맨 위에 놓으면 최대화한다."""
        from ctypes import wintypes
        c, u = self.c, self.u
        pt, r = wintypes.POINT(), wintypes.RECT()
        u.GetCursorPos(c.byref(pt))
        u.GetWindowRect(hwnd, c.byref(r))
        if self.zoomed(hwnd):
            ratio = (pt.x - r.left) / max(1, r.right - r.left)
            u.ShowWindow(hwnd, 9)  # SW_RESTORE
            u.GetWindowRect(hwnd, c.byref(r))
            w = r.right - r.left
            left, top = int(pt.x - w * ratio), pt.y - 20
            u.SetWindowPos(hwnd, None, left, top, 0, 0, 0x0001 | 0x0004 | 0x0010)
            u.GetWindowRect(hwnd, c.byref(r))
        off_x, off_y = pt.x - r.left, pt.y - r.top
        swap = u.GetSystemMetrics(23)  # 왼손잡이 설정이면 오른쪽 버튼이 주 버튼
        vk = 0x02 if swap else 0x01
        while u.GetAsyncKeyState(vk) & 0x8000:
            u.GetCursorPos(c.byref(pt))
            u.SetWindowPos(hwnd, None, pt.x - off_x, pt.y - off_y, 0, 0, 0x0001 | 0x0004 | 0x0010)  # NOSIZE|NOZORDER|NOACTIVATE
            time.sleep(0.008)
        # 화면 맨 위에 놓으면 최대화 (Windows 스냅처럼)
        mon = u.MonitorFromPoint(pt, 2)
        info = (c.c_ulong * 10)()
        info[0] = c.sizeof(info)
        if mon and u.GetMonitorInfoW(c.c_void_p(mon), c.byref(info)) and pt.y <= c.c_long(info[2]).value + 2:
            if on_maximize:
                on_maximize()

    def zoomed(self, hwnd: int) -> bool:
        return bool(self.u.IsZoomed(hwnd))


# ───────────────────────────── 화면(JS)에서 부르는 함수들
class Bridge:
    """화면에서 window.pywebview.api.이름(...)으로 부른다. 밑줄로 시작하는 속성은 화면에 드러나지 않는다."""

    def __init__(self, url: str = "", token: str = ""):
        self._url = url.rstrip("/")
        self._token = token
        self._window = None
        self._win32 = None
        self._hwnd = None

    # 파일 창
    def _dialog(self, kind, **kw):
        r = self._window.create_file_dialog(kind, **kw)
        if not r:
            return None
        return r if isinstance(r, str) else r[0]

    def pick_folder(self, start: str = ""):
        import webview
        return self._dialog(webview.FileDialog.FOLDER, directory=_existing_dir(start))

    def pick_file(self, start: str = ""):
        import webview
        return self._dialog(webview.FileDialog.OPEN, directory=_existing_dir(start), file_types=TABLE_TYPES)

    def _api(self, path: str, params: dict):
        req = urllib.request.Request(f"{self._url}{path}?{urllib.parse.urlencode(params)}", headers={"X-Dotbogi-Token": self._token})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return json.loads(e.read().decode("utf-8"))
            except Exception:
                return {"error": f"분석 엔진 오류 ({e.code})"}

    def save_download(self, exp: str = "", kind: str = "submission", path: str = ""):
        import webview
        info = self._api("/api/download/resolve", {"exp": exp, "kind": kind, "path": path})
        if not info or info.get("error"):
            return {"error": (info or {}).get("error") or "받을 수 있는 파일이 아닙니다."}
        f = Path(info["path"])
        target = self._dialog(webview.FileDialog.SAVE, directory=info.get("root") or "", save_filename=info["name"])
        if not target:
            return {"cancelled": True}
        if Path(target).resolve() != f.resolve():
            shutil.copyfile(f, target)
        return {"path": target}

    # 창
    def set_title(self, title: str):
        if self._window and title:
            self._window.set_title(str(title)[:200])

    def minimize(self):
        self._window.minimize()

    def toggle_maximize(self):
        if self.is_maximized():
            self._window.restore()
        else:
            self._window.maximize()
        return self.is_maximized()

    def is_maximized(self):
        return bool(self._win32 and self._hwnd and self._win32.zoomed(self._hwnd))

    def close(self):
        self._window.destroy()

    def start_drag(self):
        if self._win32 and self._hwnd:
            self._win32.drag(self._hwnd, on_maximize=self._window.maximize)

    def frameless(self):
        """제목 표시줄을 없앴는지: 화면이 창 버튼을 직접 그릴지 정한다."""
        return bool(self._hwnd)


# ───────────────────────────── 분석 엔진 프로세스
def _lightgbm_first():
    """점검용: 다른 라이브러리보다 LightGBM을 먼저 써 본다 (C++ 런타임 순서 문제 재발 확인)."""
    import numpy as np
    import lightgbm as lgb
    X = np.arange(40, dtype=float).reshape(20, 2)
    lgb.LGBMRegressor(n_estimators=2, min_child_samples=2, verbose=-1).fit(X, X[:, 0].copy())


def serve_engine(folder: str | None, port: int, parent: int, ready: str):
    _quiet_streams("engine.log")
    from .server import TOKEN, make_server
    httpd, app, port = make_server(folder, port)
    info = {"url": f"http://127.0.0.1:{port}/", "token": TOKEN, "pid": os.getpid()}
    tmp = ready + ".tmp"
    Path(tmp).write_text(json.dumps(info), encoding="utf-8")
    os.replace(tmp, ready)
    print(f"분석 엔진 시작: {info['url']}", flush=True)

    def watch_parent():  # 창 프로세스가 끝나면 엔진도 끝낸다
        if WIN and parent:
            import ctypes
            h = ctypes.windll.kernel32.OpenProcess(0x00100000, False, parent)  # SYNCHRONIZE
            if h:
                ctypes.windll.kernel32.WaitForSingleObject(h, 0xFFFFFFFF)
        else:
            while parent:
                try:
                    os.kill(parent, 0)
                except OSError:
                    break
                time.sleep(2)
        httpd.shutdown()
    threading.Thread(target=watch_parent, daemon=True).start()
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()


def _engine_cmd() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    return [str(pyw if WIN and pyw.exists() else exe), "-m", "dotbogi.desktop"]


def start_engine(folder: str | None, port: int) -> tuple[subprocess.Popen, dict]:
    HOME.mkdir(parents=True, exist_ok=True)
    ready = HOME / f"engine-{os.getpid()}.json"
    ready.unlink(missing_ok=True)
    cmd = _engine_cmd() + ["--server", "--port", str(port), "--parent", str(os.getpid()), "--ready", str(ready)]
    if folder:
        cmd.append(folder)
    log = open(HOME / "engine.log", "a", encoding="utf-8")
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                            creationflags=0x08000000 if WIN else 0)  # CREATE_NO_WINDOW
    for _ in range(600):  # 최대 2분 (첫 실행은 백신 검사로 느릴 수 있음)
        if ready.exists():
            info = json.loads(ready.read_text(encoding="utf-8"))
            ready.unlink(missing_ok=True)
            return proc, info
        if proc.poll() is not None:
            break
        time.sleep(0.2)
    proc.kill()
    raise RuntimeError("분석 엔진을 시작하지 못했습니다. ~/.dotbogi/engine.log를 확인하세요.")


LOADING_HTML = """<!doctype html><meta charset="utf-8"><body style="margin:0;height:100vh;display:grid;place-items:center;
background:{bg};color:{fg};font:14px 'Segoe UI','Malgun Gothic',sans-serif"><div>돋보기를 여는 중…</div></body>"""


def main(folder: str | None = None, port: int = 8765) -> int:
    _quiet_streams()
    if not available():
        from .server import serve
        serve(folder, port=port)
        return 0
    import webview
    dark = _system_dark()
    bridge = Bridge()
    win = webview.create_window(
        "돋보기", html=LOADING_HTML.format(bg="#191919" if dark else "#FFFFFF", fg="#9b9b9b" if dark else "#787774"),
        js_api=bridge, width=1440, height=920, min_size=(900, 600), text_select=True,
        background_color="#191919" if dark else "#FFFFFF")
    bridge._window = win
    state: dict = {}

    def on_shown():
        if WIN:
            try:
                bridge._win32 = _Win32()
                bridge._hwnd = int(win.native.Handle.ToInt64())
                bridge._win32.hide_caption(bridge._hwnd)
            except Exception:
                traceback.print_exc()
                bridge._hwnd = None

    win.events.shown += on_shown

    def boot():
        try:
            proc, info = start_engine(folder, port)
            state["proc"] = proc
            bridge._url, bridge._token = info["url"].rstrip("/"), info["token"]
            # 창 안의 WebView2가 첫 화면을 다 띄운 뒤에 넘어가야 요청이 버려지지 않는다. 안 넘어가면 다시 시도.
            win.events.loaded.wait(30)
            for _ in range(5):
                win.load_url(info["url"])
                for _ in range(25):
                    time.sleep(0.2)
                    if (win.get_current_url() or "").startswith(bridge._url):
                        break
                if (win.get_current_url() or "").startswith(bridge._url):
                    break
            print(f"돋보기 앱 창을 열었습니다: {info['url']}", flush=True)
        except Exception as e:
            traceback.print_exc()
            win.load_html(f"<body style='font:14px Segoe UI,Malgun Gothic;padding:40px'><h3>돋보기를 시작하지 못했습니다</h3><p>{e}</p></body>")

    try:
        HOME.mkdir(parents=True, exist_ok=True)
        webview.start(boot, private_mode=False, storage_path=str(HOME / "webview"), gui="edgechromium" if WIN else None)
    except Exception:
        traceback.print_exc()
        return 1
    finally:
        proc = state.get("proc")
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    return 0


def selftest() -> int:
    """묶은 exe가 분석 엔진을 제대로 쓰는지 작게 돌려 본다: Dotbogi.exe --selftest [대회 폴더] (결과는 desktop.log)"""
    import io
    import numpy as np
    import pandas as pd
    steps = []
    try:
        if "--lightgbm-first" in sys.argv:  # 다른 라이브러리보다 LightGBM을 먼저 (C++ 런타임 순서 문제 재발 확인)
            _lightgbm_first()
            steps.append("lightgbm-first")
        rng = np.random.default_rng(0)
        X = pd.DataFrame(rng.normal(size=(400, 4)), columns=list("abcd"))
        y = (X["a"] + rng.normal(size=400) > 0).astype(int)
        buf = io.BytesIO(); X.to_parquet(buf); pd.read_parquet(io.BytesIO(buf.getvalue()))
        steps.append("parquet")
        from sklearn.ensemble import HistGradientBoostingClassifier
        HistGradientBoostingClassifier(max_iter=20).fit(X, y)
        steps.append("sklearn")
        import lightgbm as lgb
        lgb.LGBMClassifier(n_estimators=20, verbose=-1).fit(X, y)
        steps.append("lightgbm")
        folder = next((a for a in sys.argv[1:] if not a.startswith("-") and Path(a).is_dir()), None)
        if folder:  # 실제 대회 폴더로 열기 → 기본 모델까지
            from .api import App
            app = App()

            def wait(r):
                j = app.jobs.get(r["job"]["id"]) if isinstance(r, dict) and r.get("job") else None
                while j is not None and j.state == "running":
                    time.sleep(0.2)
                if j is not None and j.state == "error":
                    raise RuntimeError(j.error + "\n" + (getattr(j, "detail", "") or ""))
            wait(app.open_project(folder))
            steps.append("open")
            wait(app.baseline({}))
            steps.append("baseline")
        print("selftest ok:", ", ".join(steps), flush=True)
        return 0
    except Exception:
        print("selftest failed after:", ", ".join(steps) or "(none)", flush=True)
        traceback.print_exc()
        return 1


def run():
    """설치 파일·바로가기에서 부르는 진입점: Dotbogi.exe [대회 폴더]"""
    ap = argparse.ArgumentParser(prog="dotbogi-app", add_help=False)
    ap.add_argument("folder", nargs="?")
    ap.add_argument("--server", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--parent", type=int, default=0)
    ap.add_argument("--ready", default="")
    a, _ = ap.parse_known_args()
    folder = a.folder if a.folder and Path(a.folder).is_dir() else None
    if a.server:
        serve_engine(folder, a.port, a.parent, a.ready)
        return
    if a.selftest:
        _quiet_streams()
        sys.exit(selftest())
    sys.exit(main(folder, port=a.port))


if __name__ == "__main__":
    run()
