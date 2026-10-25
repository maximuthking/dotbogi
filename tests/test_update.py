"""새 버전 알림: GitHub 대신 가짜 응답으로 확인한다 (실제 네트워크에 접속하지 않음)."""
from __future__ import annotations

import io
import json
import urllib.request

import pytest

from dotbogi import __version__, api


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "HOME", tmp_path)
    return tmp_path


def fake_release(monkeypatch, tag, calls):
    def urlopen(req, timeout=None):
        calls.append(req.full_url)
        body = {"tag_name": tag, "html_url": f"https://github.com/maximuthking/dotbogi/releases/tag/{tag}",
                "assets": [{"name": f"Dotbogi-Setup-{tag.lstrip('v')}.exe", "browser_download_url": "https://x/setup.exe"}]}
        return FakeResp(json.dumps(body).encode())
    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


def test_version_compare():
    assert api._version_tuple("1.10.0") > api._version_tuple("1.9.3")
    assert api._version_tuple("v2.0") > api._version_tuple("1.99.99")
    assert api._version_tuple("1.0.0") == api._version_tuple("1.0")


def test_newer_release_is_reported_and_cached(home, monkeypatch):
    calls = []
    fake_release(monkeypatch, "v99.0.0", calls)
    app = api.App()
    r = app.check_update()
    assert r["newer"] and r["latest"] == "99.0.0" and r["current"] == __version__
    assert r["setup_url"] == "https://x/setup.exe"
    app.check_update()                      # 하루 안에는 다시 묻지 않는다
    assert len(calls) == 1
    app.check_update(force=True)            # '지금 확인'은 바로 묻는다
    assert len(calls) == 2


def test_same_version_is_not_newer(home, monkeypatch):
    fake_release(monkeypatch, "v" + __version__, [])
    assert api.App().check_update()["newer"] is False


def test_disabled_and_offline(home, monkeypatch):
    calls = []
    fake_release(monkeypatch, "v99.0.0", calls)
    app = api.App()
    app.set_prefs({"update_check": False})
    assert app.check_update() == {"enabled": False, "current": __version__}
    assert calls == [] and api.load_prefs()["update_check"] is False

    app.set_prefs({"update_check": True})

    def offline(*a, **k):
        raise OSError("no network")
    monkeypatch.setattr(urllib.request, "urlopen", offline)
    r = app.check_update()
    assert r["enabled"] and "error" in r and "newer" not in r
    with pytest.raises(Exception):
        app.set_prefs({"lang": "fr"})
