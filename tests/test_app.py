"""화면이 쓰는 기능(App)·HTTP 서버·명령줄·스크립트 API를 끝에서 끝까지 확인"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from conftest import make_planted, open_app, ready, wait, write
import dotbogi
from dotbogi.utils import jsonable


def test_full_flow_binary(planted_dir):
    app = open_app(planted_dir)
    s = app.project.settings
    assert s["target"] == ["target"] and s["id_col"] == "id" and s["metric"] == "auc"
    st = app.state()
    json.dumps(jsonable(st))
    ov = app.overview()
    assert ov["target"]["classes"] and ov["files"]["test"]["rows"] == 1500
    cols = ready(app, app.columns)
    names = {c["name"] for c in cols["columns"]}
    assert {"x1", "leak_col", "city"} <= names
    for name in names:
        c = app.column(name)
        json.dumps(jsonable(c))
    chk = ready(app, app.checks)
    assert chk["counts"]["danger"] >= 1 and chk["counts"]["warn"] >= 5
    # 적대적 검증 (빼고 다시)
    assert app.adversarial(None)["ready"] is False
    wait(app, app.adversarial(["leak_col"], rerun=True))
    adv = app.adversarial(None)
    assert adv["ready"] and adv["result"]["auc"] > 0.8 and adv["exclude"] == ["leak_col"]
    wait(app, app.adversarial(["leak_col", "shift_col"], rerun=True))
    adv2 = app.adversarial(None)  # 조회는 마지막 실행 결과
    assert adv2["exclude"] == ["leak_col", "shift_col"]
    assert all(f["name"] != "shift_col" for f in adv2["result"]["features"])
    again = app.adversarial(["leak_col"])  # 같은 조건은 다시 계산하지 않고 재사용
    assert again["ready"] and app.adversarial(None)["exclude"] == ["leak_col"]
    assert (app.project.dir / "test_likeness.csv").exists()
    # 검증 설계 + 기본 모델
    cv = ready(app, app.cv_info)
    assert cv["recommend"]["strategy"] == "stratified"
    app.make_folds({"strategy": "stratified", "n_splits": 4, "seed": 1})
    assert app.project.load_folds() is not None
    app.update_settings({"excluded": ["leak_col"]})
    res = wait(app, app.baseline({"engine": "auto"}))
    assert 0.6 < res["cv"] < 0.99 and res["experiment"]["files"]["submission"]
    res2 = wait(app, app.baseline({"engine": "sklearn", "learning_rate": 0.1}))
    ex = app.experiments()
    assert len(ex["experiments"]) == 2 and ex["best_cv_id"]
    e1, e2 = ex["experiments"]
    app.update_experiment(e1["id"], {"lb_public": "0.8", "notes": "첫 제출"})
    assert app.experiments()["submissions_today"] == 1
    noise = app.lb_noise({"id": e1["id"], "id_b": e2["id"]})
    assert noise["ok"] and noise["share_assumed"]
    # 앙상블 → 저장 → 제출 파일
    ens = wait(app, app.ensemble({"ids": [e1["id"], e2["id"]], "method": "hill", "use_rank": True}))
    assert ens["use_rank"] is True and ens["honest"]
    saved = app.ensemble_save({})
    assert saved["has_submission"]
    sub_path = app.experiment_file(saved["experiment"]["id"], "submission")
    chk_sub = app.submission_check(str(sub_path))
    assert chk_sub["ok"], chk_sub["items"]
    assert app.submission_check("", exp=saved["experiment"]["id"])["ok"]
    # 외부 OOF 파일 추가 (ID로 섞인 순서)
    oof_df = pd.DataFrame({"id": app.project.train["id"], "pred": np.random.default_rng(0).random(len(app.project.train))})
    oof_path = planted_dir / "my_oof.csv"
    oof_df.sample(frac=1, random_state=0).to_csv(oof_path, index=False)
    added = app.add_experiment({"name": "외부 실험", "oof_path": str(oof_path), "lb_public": 0.7})
    assert added["info"]["cv_computed"] and abs(added["experiment"]["cv"] - 0.5) < 0.05
    # 삭제
    app.delete_experiment(added["experiment"]["id"])
    assert all(e["id"] != added["experiment"]["id"] for e in app.experiments()["experiments"])
    # 탐색
    for params in ({"x": "x1"}, {"x": "grade"}, {"x": "x1", "y": "x2", "color": "target"},
                   {"x": "grade", "y": "x1"}, {"x": "grade", "y": "city"}, {"x": "x1", "color": "grade", "which": "test"}):
        r = app.explore(params)
        json.dumps(jsonable(r))
    rows = app.rows({"which": "train", "filters": [{"col": "x1", "op": ">", "value": "0"}, {"col": "city", "op": "contains", "value": "seo"}],
                     "sort": "x2", "asc": False, "limit": 50})
    assert rows["matched"] < rows["total"] and len(rows["rows"]) <= 50
    corr = app.correlation()
    assert corr["names"]
    # 보고서
    from dotbogi.report import build_report
    rep = build_report(app, planted_dir / "report.html")
    html = (planted_dir / "report.html").read_text(encoding="utf-8")
    assert rep["bytes"] < 5_000_000 and "__DOTBOGI_STATIC__" in html and "<script src=" not in html


def test_settings_changes(planted_dir, tmp_path):
    app = open_app(planted_dir)
    st = app.update_settings({"task": "regression"})
    assert st["project"]["settings"]["metric"] == "rmse"
    app.update_settings({"task": "binary"})
    app.update_settings({"metric": "logloss"})
    with pytest.raises(Exception):
        app.update_settings({"metric": "rmse"})  # 이진분류에 회귀 지표
    with pytest.raises(Exception):
        app.update_settings({"target": ["없는컬럼"]})
    app.update_settings({"kinds": {"x2": "categorical"}})
    assert app.project.column("x2").kind == "categorical"
    ready(app, app.columns)
    metric = tmp_path / "m.py"
    metric.write_text("import numpy as np\nHIGHER_IS_BETTER=False\ndef score(y, p):\n    return float(np.mean((p-y)**2))\n")
    st = app.update_settings({"custom_metric": {"path": str(metric), "needs": "proba"}})
    assert st["project"]["settings"]["metric"] == "custom" and st["project"]["metric_info"]["higher_is_better"] is False
    broken = tmp_path / "broken.py"
    broken.write_text("raise RuntimeError('x')\n")
    with pytest.raises(Exception):
        app.update_settings({"custom_metric": {"path": str(broken)}})
    st = app.update_settings({"custom_metric": None})
    assert st["project"]["settings"]["metric"] != "custom"
    app.update_settings({"competition": {"platform": "dacon", "public_share": 30, "daily_limit": 3, "end_date": "2026-12-31"}})
    assert app.project.settings["competition"]["public_share"] == pytest.approx(0.3)
    # 설정이 디스크에 남고 다시 열면 유지
    app2 = open_app(planted_dir)
    assert app2.project.settings["competition"]["daily_limit"] == 3
    assert app2.project.column("x2").kind == "categorical"


def test_edge_cases(tmp_path):
    from dotbogi.api import App
    from dotbogi.io import LoadError
    # 타깃 없음 + test 없음 + 전부 결측 컬럼 + 한글 이름 + cp949
    df = pd.DataFrame({"이름": ["가", "나", "다"] * 40, "값": np.arange(120.0), "빈칸": np.nan})
    folder = tmp_path / "한글폴더"
    folder.mkdir()
    df.to_csv(folder / "train.csv", index=False, encoding="cp949")
    app = open_app(folder)
    assert app.project.settings["target"] == []
    ready(app, app.columns)
    chk = ready(app, app.checks)
    assert any(it["id"] == "no_test" for it in chk["items"])
    with pytest.raises(LoadError):
        app.adversarial(["x"], rerun=True)
    with pytest.raises(LoadError):
        app.baseline({})
    assert app.experiments()["experiments"] == []
    # 빈 폴더 / 없는 폴더
    empty = tmp_path / "empty"
    empty.mkdir()
    a = App()
    r = a.open_project(str(empty))
    job = a.jobs.get(r["job"]["id"])
    import time
    while job.state == "running":
        time.sleep(0.05)
    assert job.state == "error" and "train" in job.error
    with pytest.raises(LoadError):
        App().open_project(str(tmp_path / "없음"))
    # 빈 CSV
    e2 = tmp_path / "emptycsv"
    e2.mkdir()
    (e2 / "train.csv").write_text("")
    r = a.open_project(str(e2))
    job = a.jobs.get(r["job"]["id"])
    while job.state == "running":
        time.sleep(0.05)
    assert job.state == "error"


def test_readonly_folder_uses_home_store(tmp_path, isolated_home):
    tr, te, ss = make_planted(500, 200)
    folder = write(tmp_path / "ro", tr, te, ss)
    import dotbogi.project as P
    real = P._pick_store

    def fake(root):  # 쓰기 실패를 흉내
        orig_mkdir = Path.mkdir
        def boom(self, *a, **k):
            if self == root / ".dotbogi":
                raise PermissionError("read-only")
            return orig_mkdir(self, *a, **k)
        Path.mkdir = boom
        try:
            return real(root)
        finally:
            Path.mkdir = orig_mkdir
    P._pick_store = fake
    try:
        app = open_app(folder)
        assert str(app.project.dir).startswith(str(isolated_home))
        assert not (folder / ".dotbogi").exists()
    finally:
        P._pick_store = real


def test_script_api(planted_dir):
    app = open_app(planted_dir)
    app.make_folds({"strategy": "stratified", "n_splits": 5})
    fold = dotbogi.folds(str(planted_dir))
    assert len(fold) == len(app.project.train)
    tr = app.project.train
    oof = tr["x1"].to_numpy() * 0.1 + 0.5
    test_pred = np.full(1500, 0.4)
    e = dotbogi.log(str(planted_dir), name="스크립트", oof=oof, test_pred=test_pred, params={"a": 1}, lb=0.7)
    assert e["cv"] > 0.5 and e["files"]["submission"]
    with pytest.raises(ValueError):
        dotbogi.log(str(planted_dir), name="x", oof=oof[:10])
    sub = pd.read_csv(Path(app.project.dir) / "runs" / e["id"] / "submission.csv")
    assert list(sub.columns) == ["id", "target"] and len(sub) == 1500
    r = dotbogi.check_submission_file(str(planted_dir), str(Path(app.project.dir) / "runs" / e["id"] / "submission.csv"))
    assert r["ok"]


def test_report_function(planted_dir, tmp_path):
    out = tmp_path / "r.html"
    res = dotbogi.report(str(planted_dir), str(out), adversarial=True, show=False)
    html = out.read_text(encoding="utf-8")
    assert res["bytes"] == out.stat().st_size and '"/api/adversarial":{"ready":true' in html.replace(" ", "")


def test_kaggle_import_with_fake_cli(planted_dir, tmp_path, monkeypatch):
    app = open_app(planted_dir)
    e = app.ledger().add("lgbm_v1", "auc", 0.81)
    fake_dir = tmp_path / "bin"
    fake_dir.mkdir()
    csv = ("fileName,date,description,status,publicScore,privateScore\n"
           f"{e['id']}_submission.csv,2026-10-16 10:00:00,first,SubmissionStatus.COMPLETE,0.80123,\n"
           "other.csv,2026-10-15 09:00:00,manual try,SubmissionStatus.COMPLETE,0.79,0.78\n"
           "bad.csv,2026-10-15 08:00:00,broken,SubmissionStatus.ERROR,,\n")
    if sys.platform == "win32":
        script = fake_dir / "kaggle.bat"
        (fake_dir / "out.csv").write_text(csv)
        script.write_text(f"@echo off\ntype \"{fake_dir / 'out.csv'}\"\n")
    else:
        script = fake_dir / "kaggle"
        script.write_text("#!/bin/sh\ncat <<'EOF'\n" + csv + "EOF\n")
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(fake_dir) + os.pathsep + os.environ.get("PATH", ""))
    app.update_settings({"competition": {"url": "https://www.kaggle.com/competitions/titanic"}})
    r = app.kaggle_import({})
    assert r["matched"] == 1 and r["created"] == 1 and r["skipped"] == 1
    again = app.kaggle_import({})  # 다시 가져와도 중복으로 늘지 않음
    assert again["created"] == 0
    got = app.ledger().get(e["id"])
    assert got["lb_public"] == pytest.approx(0.80123)


# ───────────────────────────── HTTP 서버
@pytest.fixture
def server(planted_dir):
    from dotbogi import server as S
    httpd, app, port = S.make_server(None, port=18765)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}", S.TOKEN, app, planted_dir
    httpd.shutdown()
    httpd.server_close()


def _req(url, token=None, body=None, host=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Dotbogi-Token", token)
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


def test_http_server(server):
    base, token, app, folder = server
    code, body = _req(base + "/")
    assert code == 200 and token.encode() in body
    assert _req(base + "/static/js/core.js")[0] == 200
    assert _req(base + "/static/../server.py")[0] == 404
    assert _req(base + "/api/state")[0] == 403  # 토큰 없음
    assert _req(base + "/api/state", token, host="evil.example:80")[0] == 403  # 다른 호스트
    code, body = _req(base + "/api/state", token)
    assert code == 200 and json.loads(body)["project"] is None
    code, body = _req(base + "/api/open", token, {"path": str(folder)})
    job = json.loads(body)["job"]
    import time
    for _ in range(200):
        code, body = _req(base + f"/api/job?id={job['id']}", token)
        if json.loads(body)["state"] != "running":
            break
        time.sleep(0.1)
    assert json.loads(body)["state"] == "done"
    code, body = _req(base + "/api/overview", token)
    assert code == 200 and json.loads(body)["target"]["name"] == "target"
    code, body = _req(base + "/api/column?name=" + urllib.parse.quote("없는"), token)
    assert code == 400 and "error" in json.loads(body)
    code, body = _req(base + "/api/nothing", token)
    assert code == 404
    code, body = _req(base + "/api/settings", token, {"metric": "없는지표"})
    assert code == 400 and "지표" in json.loads(body)["error"]


# ───────────────────────────── 명령줄
def _cli(*args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    return subprocess.run([sys.executable, "-m", "dotbogi", *args], capture_output=True, text=True, encoding="utf-8", env=env, timeout=600)


def test_cli(planted_dir):
    r = _cli("check", str(planted_dir))
    assert r.returncode == 2 and "누수" in r.stdout  # 위험 항목이 있으면 2
    r = _cli("check", str(planted_dir), "--json")
    assert json.loads(r.stdout)["counts"]["danger"] >= 1
    sample = pd.read_csv(planted_dir / "sample_submission.csv")
    good = planted_dir / "good.csv"
    sample.to_csv(good, index=False)
    assert _cli("sub-check", str(good), "-p", str(planted_dir)).returncode == 0
    bad = planted_dir / "bad.csv"
    sample.iloc[:-5].to_csv(bad)
    r = _cli("sub-check", str(bad), "-p", str(planted_dir), "--fix")
    assert r.returncode == 1 and "실패" in r.stdout
    r = _cli("report", str(planted_dir), "-o", str(planted_dir / "r.html"))
    assert r.returncode == 0 and (planted_dir / "r.html").exists()
    assert _cli("--version").stdout.strip() == dotbogi.__version__
    assert _cli("check", str(planted_dir / "nope")).returncode == 1
