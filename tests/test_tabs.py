"""대회 여러 개를 탭으로 열기: 바꾸기·닫기·다시 열기, 작업은 시작한 대회에만."""
from __future__ import annotations

import time

import pytest

from conftest import make_groups, make_planted, wait, write
from dotbogi.api import App
from dotbogi.experiments import Ledger
from dotbogi.io import LoadError


@pytest.fixture
def two(tmp_path):
    a = write(tmp_path / "comp_a", *make_planted(n_train=600, n_test=300))
    b = write(tmp_path / "comp_b", *make_groups())
    app = App()
    wait(app, app.open_project(str(a)))
    wait(app, app.open_project(str(b)))
    return app, a, b


def test_open_switch_close(two):
    app, a, b = two
    tabs = app.state()["tabs"]
    assert [t["name"] for t in tabs] == ["comp_a", "comp_b"]
    assert tabs[1]["active"] and app.project.root.name == "comp_b"

    app.switch_project(str(a.resolve()))
    assert app.project.root.name == "comp_a"
    assert app.overview()  # 활성 대회 기준으로 동작

    # 이미 열린 대회를 다시 열면 불러오지 않고 그 탭으로
    r = app.open_project(str(b))
    assert r.get("switched") and app.project.root.name == "comp_b"

    # 활성 탭을 닫으면 남은 탭이 활성
    app.close_project(str(b.resolve()))
    assert [t["name"] for t in app.state()["tabs"]] == ["comp_a"]
    assert app.project.root.name == "comp_a"
    app.close_project(str(a.resolve()))
    assert app.project is None and app.state()["tabs"] == []
    with pytest.raises(LoadError):
        app.switch_project(str(a))


def test_tab_limit(two, tmp_path, monkeypatch):
    app, a, b = two
    monkeypatch.setattr(App, "MAX_TABS", 2)
    c = write(tmp_path / "comp_c", *make_planted(n_train=300, n_test=100, seed=5))
    with pytest.raises(LoadError, match="2개까지"):
        app.open_project(str(c))


def test_jobs_are_per_project(two):
    """두 대회에서 같은 종류의 작업(컬럼 분석)을 동시에 돌려도 막히지 않는다."""
    app, a, b = two
    pa, pb = app.projects[str(a.resolve())], app.projects[str(b.resolve())]
    ja = app.jobs.submit("profiles", "컬럼 분석", app._profiles_job, pa)
    jb = app.jobs.submit("profiles", "컬럼 분석", app._profiles_job, pb)
    assert ja is not jb and ja.project != jb.project
    for j in (ja, jb):
        t0 = time.time()
        while j.state == "running" and time.time() - t0 < 300:
            time.sleep(0.05)
        assert j.state == "done", j.error


def test_baseline_writes_to_its_own_project(two):
    """기본 모델을 돌리는 도중 다른 탭으로 바꿔도 실험은 시작한 대회에만 기록된다."""
    app, a, b = two
    app.switch_project(str(a.resolve()))
    r = app.baseline({})
    app.switch_project(str(b.resolve()))           # 작업 도중 탭 바꾸기
    job = app.jobs.get(r["job"]["id"])
    t0 = time.time()
    while job.state == "running" and time.time() - t0 < 300:
        time.sleep(0.05)
    assert job.state == "done", job.error
    assert job.project == str(a.resolve())
    pa, pb = app.projects[str(a.resolve())], app.projects[str(b.resolve())]
    assert len(Ledger(pa.dir).load()) == 1
    assert Ledger(pb.dir).load() == []
    assert pa.load_folds() is not None and pb.load_folds() is None
