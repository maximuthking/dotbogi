"""데스크톱 앱 연결(Bridge): 운영체제 창은 가짜로 바꿔 끼우고, 분석 엔진은 실제 로컬 서버로 확인한다."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from dotbogi import desktop, server

webview = pytest.importorskip("webview")


class FakeWindow:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []
        self.title = None

    def create_file_dialog(self, kind, **kw):
        self.calls.append((kind, kw))
        return self.answer

    def set_title(self, t):
        self.title = t


@pytest.fixture
def engine(planted_dir):
    httpd, app, port = server.make_server(str(planted_dir), port=18930)
    for j in list(app.jobs.jobs.values()):  # 폴더 열기 작업이 끝날 때까지
        while j.state == "running":
            threading.Event().wait(0.1)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}/", app
    httpd.shutdown()
    httpd.server_close()


def bridge(url, answer):
    b = desktop.Bridge(url, server.TOKEN)
    b._window = FakeWindow(answer)
    return b


def test_save_download_copies_project_file(engine, planted_dir, tmp_path):
    url, _ = engine
    target = tmp_path / "out" / "saved.csv"
    target.parent.mkdir()
    b = bridge(url, [str(target)])
    src = Path(planted_dir) / "train.csv"
    assert b.save_download(path=str(src)) == {"path": str(target)}
    assert target.read_bytes() == src.read_bytes()
    kind, kw = b._window.calls[0]
    assert kind == webview.FileDialog.SAVE and kw["save_filename"] == "train.csv"
    assert Path(kw["directory"]).resolve() == Path(planted_dir).resolve()  # 대회 폴더에서 시작


def test_save_download_refuses_outside_and_cancel(engine, planted_dir, tmp_path):
    url, _ = engine
    outside = tmp_path / "secret.txt"
    outside.write_text("x", encoding="utf-8")
    b = bridge(url, None)
    assert "error" in b.save_download(path=str(outside))
    assert b._window.calls == []  # 허용되지 않은 파일이면 저장 창도 열지 않음
    assert b.save_download(path=str(Path(planted_dir) / "train.csv")) == {"cancelled": True}


def test_resolve_needs_token(engine):
    url, _ = engine
    b = desktop.Bridge(url, "wrong-token")
    b._window = FakeWindow(None)
    assert "error" in b.save_download(path="x")


def test_pick_folder_and_title(planted_dir):
    b = bridge("", (str(planted_dir),))
    assert b.pick_folder(str(Path(planted_dir) / "train.csv")) == str(planted_dir)
    kind, kw = b._window.calls[0]
    assert kind == webview.FileDialog.FOLDER and kw["directory"] == str(planted_dir)  # 파일을 주면 그 폴더에서 시작
    b.set_title("개요 - 돋보기")
    assert b._window.title == "개요 - 돋보기"
    assert b.frameless() is False and b.is_maximized() is False  # 창 핸들이 없으면 창 버튼을 그리지 않음


def test_bridge_exposes_no_internal_objects():
    # pywebview는 js_api의 공개 속성을 화면에 노출하므로 내부 객체는 밑줄로 숨긴다
    public = [n for n in vars(desktop.Bridge()) if not n.startswith("_")]
    assert public == []
