"""독립 검수에서 나온 결함이 다시 생기지 않는지 확인하는 테스트 (번호는 검수 보고서의 결함 번호)"""
from __future__ import annotations

import json
import multiprocessing as mp
import os
import stat
import sys
import time

import numpy as np
import pandas as pd
import pytest

from conftest import make_planted, open_app, ready, wait, write
import dotbogi
from dotbogi.api import App
from dotbogi.io import LoadError, read_table
from dotbogi.schema import guess_competition, infer_columns
from dotbogi.submission import check_submission


def _binary_frame(n=1200, seed=0):
    rng = np.random.default_rng(seed)
    x = rng.normal(size=n)
    y = (rng.random(n) < 1 / (1 + np.exp(-2 * x))).astype(int)
    return pd.DataFrame({"x": x, "z": rng.normal(size=n), "target": y})


# A1: 앞자리 0이 있는 ID
def test_leading_zero_ids(tmp_path):
    df = _binary_frame(1500)
    df.insert(0, "id", [f"{i:06d}" for i in range(1500)])
    tr, te = df.iloc[:1000], df.iloc[1000:].drop(columns=["target"])
    ss = pd.DataFrame({"id": te["id"], "target": 0.5})
    folder = write(tmp_path / "zero", tr, te, ss)
    assert read_table(folder / "sample_submission.csv")["id"].iloc[0] == "001000"
    app = open_app(folder)
    good = folder / "good.csv"
    ss.assign(target=0.3).to_csv(good, index=False)
    assert app.submission_check(str(good))["ok"]
    bad = folder / "bad.csv"
    pd.DataFrame({"id": te["id"].astype(int), "target": 0.3}).to_csv(bad, index=False)
    r = app.submission_check(str(bad))
    assert not r["ok"] and any("앞자리 0" in it["detail"] for it in r["items"])
    res = wait(app, app.baseline({}))
    sub = app.experiment_file(res["experiment"]["id"], "submission").read_text(encoding="utf-8")
    assert "\n001000," in sub
    assert app.submission_check("", exp=res["experiment"]["id"])["ok"]


# A2: 행 순서가 다른 test 예측끼리 섞을 때 ID로 맞춘다
def test_ensemble_aligns_test_rows(tmp_path):
    df = _binary_frame(1500)
    df.insert(0, "id", np.arange(1500))
    tr, te = df.iloc[:1000], df.iloc[1000:].drop(columns=["target"])
    ss = pd.DataFrame({"id": te["id"].to_numpy()[::-1], "target": 0.5})  # 제출 양식은 test 역순
    folder = write(tmp_path / "order", tr, te, ss)
    app = open_app(folder)
    base = wait(app, app.baseline({}))
    e1 = base["experiment"]
    sub_path = app.experiment_file(e1["id"], "submission")
    oof_path = folder / "oof.csv"
    o = pd.read_parquet(app.experiment_file(e1["id"], "oof"))
    o[["id", "pred"]].to_csv(oof_path, index=False)
    e2 = app.add_experiment({"name": "같은 예측(제출 파일 순서)", "oof_path": str(oof_path), "submission_path": str(sub_path)})["experiment"]
    wait(app, app.ensemble({"ids": [e1["id"], e2["id"]], "method": "mean"}))
    saved = app.ensemble_save({})
    assert saved["has_submission"]
    a = pd.read_csv(sub_path)
    b = pd.read_csv(app.experiment_file(saved["experiment"]["id"], "submission"))
    assert (a["id"].to_numpy() == b["id"].to_numpy()).all()
    assert np.allclose(a["target"], b["target"])  # 같은 예측 둘을 섞으면 그대로여야


# A3: 노트북용 report를 여러 번 불러도 된다
def test_report_twice(planted_dir, tmp_path):
    dotbogi.report(str(planted_dir), str(tmp_path / "a.html"), show=False)
    dotbogi.report(str(planted_dir), str(tmp_path / "b.html"), show=False)
    assert callable(dotbogi.report)


# A4: 'Status_C'처럼 접두사가 붙은 확률 컬럼
def test_prefixed_proba_columns(tmp_path):
    rng = np.random.default_rng(1)
    n = 1500
    x = rng.normal(size=n)
    status = np.where(x < -0.5, "C", np.where(x < 0.7, "CL", "D"))
    df = pd.DataFrame({"id": np.arange(n), "x": x + rng.normal(scale=0.3, size=n), "w": rng.normal(size=n), "Status": status})
    tr, te = df.iloc[:1000], df.iloc[1000:].drop(columns=["Status"])
    ss = pd.DataFrame({"id": te["id"], "Status_C": 0.3, "Status_CL": 0.4, "Status_D": 0.3})
    folder = write(tmp_path / "prefixed", tr, te, ss)
    app = open_app(folder)
    s = app.project.settings
    assert s["task"] == "multiclass" and s["submission_format"] == "proba_columns" and s["classes"] == ["C", "CL", "D"]
    y, mask, _ = app.project.encoded_target()
    assert mask.all()
    res = wait(app, app.baseline({}))
    sub = pd.read_csv(app.experiment_file(res["experiment"]["id"], "submission"))
    assert list(sub.columns) == ["id", "Status_C", "Status_CL", "Status_D"]
    assert np.allclose(sub[["Status_C", "Status_CL", "Status_D"]].sum(axis=1), 1, atol=1e-6)


# A5: 타깃이 둘
def test_two_targets(tmp_path):
    rng = np.random.default_rng(2)
    n = 1200
    x = rng.normal(size=n)
    df = pd.DataFrame({"id": np.arange(n), "x": x, "t1": 3 * x + rng.normal(size=n), "t2": -2 * x + rng.normal(size=n)})
    tr, te = df.iloc[:900], df.iloc[900:].drop(columns=["t1", "t2"])
    ss = pd.DataFrame({"id": te["id"], "t1": 0.0, "t2": 0.0})
    folder = write(tmp_path / "two", tr, te, ss)
    app = open_app(folder)
    assert app.project.settings["target"] == ["t1", "t2"]
    res = wait(app, app.baseline({}))
    assert len(res["targets"]) == 2
    sub = pd.read_csv(app.experiment_file(res["experiment"]["id"], "submission"))
    assert sub["t1"].std() > 0.5 and sub["t2"].std() > 0.5
    assert np.corrcoef(sub["t1"], sub["t2"])[0, 1] < -0.8


# A6: 행이 아주 적은 클래스가 있는 다중분류 (두 엔진)
@pytest.mark.parametrize("engine", ["sklearn", "auto"])
def test_rare_classes(tmp_path, engine):
    rng = np.random.default_rng(3)
    n = 2000
    cls = rng.integers(0, 47, n)
    cls[:3] = 47; cls[3:5] = 48; cls[5] = 49  # 1~3행짜리 클래스
    df = pd.DataFrame({"x": cls + rng.normal(scale=2, size=n), "z": rng.normal(size=n), "label": [f"c{c}" for c in cls]})
    df = df.sample(frac=1, random_state=0).reset_index(drop=True)
    folder = write(tmp_path / f"rare_{engine}", df, None, None)
    app = open_app(folder)
    app.update_settings({"target": ["label"], "task": "multiclass"})
    app.make_folds({"strategy": "stratified", "n_splits": 3})
    res = wait(app, app.baseline({"engine": engine}))
    assert np.isfinite(res["cv"])


# A7·A8: ID만 다른 중복 행, 고유값 많은 숫자형 문자, 쉼표 숫자
def test_duplicate_and_numeric_text_checks(tmp_path):
    df = _binary_frame(1000)
    df["price"] = np.random.default_rng(0).choice(["1,000", "2,500", "10,000", "500", "3,000"], 1000)
    vals = np.round(np.random.default_rng(1).normal(100, 10, 1000), 3).astype(str)
    vals[::30] = "?"
    df["measure"] = vals
    df = pd.concat([df, df.iloc[:50]], ignore_index=True)
    df.insert(0, "id", np.arange(len(df)))
    folder = write(tmp_path / "dups", df, None, None)
    app = open_app(folder)
    kinds = {c.name: c.kind for c in app.project.columns}
    assert kinds["measure"] == "categorical"
    chk = ready(app, app.checks)
    by = {it["id"]: it for it in chk["items"]}
    assert by["dup_rows"]["data"]["n_dup"] >= 50
    assert {"price", "measure"} <= set(by["numeric_as_text"]["columns"])


# A9·A28: 문자열 ID의 정렬 누수는 잡고, 무작위 ID는 잡지 않는다
def test_string_id_order_leak(tmp_path):
    df = _binary_frame(1500).sort_values("target").reset_index(drop=True)
    df.insert(0, "ID", [f"TRAIN_{i:06d}" for i in range(len(df))])
    tr, te = df.iloc[:1200], df.iloc[1200:].drop(columns=["target"])
    te = te.assign(ID=[f"TEST_{i:06d}" for i in range(len(te))])
    ss = pd.DataFrame({"ID": te["ID"], "target": 0.5})
    app = open_app(write(tmp_path / "strid", tr, te, ss))
    chk = ready(app, app.checks)
    assert any(it["id"] == "order_leak" for it in chk["items"])
    rnd = _binary_frame(320, seed=9).sample(frac=1, random_state=3).reset_index(drop=True)
    rnd.insert(0, "id", np.random.default_rng(5).permutation(320))
    app2 = open_app(write(tmp_path / "rnd", rnd, None, None))
    chk2 = ready(app2, app2.checks)
    assert not any(it["id"] == "order_leak" for it in chk2["items"])


# A10: Kaggle CLI가 경고 줄을 먼저 출력해도
def test_kaggle_warning_line(planted_dir, tmp_path, monkeypatch):
    app = open_app(planted_dir)
    e = app.ledger().add("v1", "auc", 0.8)
    fake = tmp_path / "bin"
    fake.mkdir()
    csv = ("Warning: Looks like you're using an outdated API Version, please consider updating (server 1.7 / client 1.6)\n"
           "fileName,date,description,status,publicScore,privateScore\n"
           f"{e['id']}_submission.csv,2026-10-16 10:00:00,v1,SubmissionStatus.COMPLETE,0.8,\n")
    if sys.platform == "win32":
        (fake / "out.txt").write_text(csv)
        (fake / "kaggle.bat").write_text(f"@echo off\ntype \"{fake / 'out.txt'}\"\n")
    else:
        sc = fake / "kaggle"
        sc.write_text("#!/bin/sh\ncat <<'EOF'\n" + csv + "EOF\n")
        sc.chmod(sc.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(fake) + os.pathsep + os.environ.get("PATH", ""))
    app.update_settings({"competition": {"url": "https://www.kaggle.com/competitions/x"}})
    assert app.kaggle_import({})["matched"] == 1


# A11: 여러 프로세스가 동시에 기록해도 사라지지 않는다
def _writer(d, tag, n):
    from dotbogi.experiments import Ledger
    led = Ledger(d)
    for i in range(n):
        led.add(f"{tag}{i}", "auc", 0.5)


def test_concurrent_ledger(tmp_path):
    from dotbogi.experiments import Ledger
    ps = [mp.Process(target=_writer, args=(str(tmp_path), t, 40)) for t in "ab"]
    [p.start() for p in ps]
    [p.join() for p in ps]
    assert [p.exitcode for p in ps] == [0, 0]
    assert len(Ledger(tmp_path).load()) == 80
    (tmp_path / "experiments.json").write_text('{"experiments": null}', encoding="utf-8")
    assert Ledger(tmp_path).load() == []  # 모양이 틀린 파일은 백업 후 빈 목록
    (tmp_path / "experiments.json").write_text('{"experiments": [{"id": "x", "cv": "0.5"}, {"name": "id없음"}]}', encoding="utf-8")
    got = Ledger(tmp_path).load()
    assert len(got) == 1 and got[0]["cv"] == 0.5


# A12·A23: 컬럼 순서만 바뀐 확률 제출, 소수점 ID
def test_submission_column_order_and_float_id(planted_dir):
    app = open_app(planted_dir)
    sample = pd.read_csv(planted_dir / "sample_submission.csv")
    f = planted_dir / "swapped.csv"
    sample.assign(target=0.2)[["target", "id"]].to_csv(f, index=False)
    r = app.submission_check(str(f))
    assert r["ok"] and any(it["level"] == "warn" and "순서" in it["title"] for it in r["items"])
    g = planted_dir / "floatid.csv"
    sample.assign(id=sample["id"].astype(float), target=0.2).to_csv(g, index=False)
    r2 = app.submission_check(str(g))
    assert any("소수점" in it["title"] for it in r2["items"])
    fx = app.submission_fix(str(g))
    assert "ID를 sample_submission과 같은 형식으로 맞춤" in fx["done"]
    assert app.submission_check(fx["path"])["ok"]
    empty = planted_dir / "empty.csv"
    empty.write_text("")
    with pytest.raises(LoadError):
        app.submission_check(str(empty))


# A13·A14: 제출 양식 고르기, 이름이 바뀐 파일, 대회가 여러 개 든 폴더
def test_file_detection(tmp_path):
    tr, te, ss = make_planted(500, 200)
    folder = write(tmp_path / "comp", tr, te, ss, names=("train.csv", "test.csv", "gender_submission.csv"))
    time.sleep(0.05)
    ss.assign(target=0.9).iloc[:-3].to_csv(folder / "bad_submission.csv", index=False)  # 나중에 만든 사용자 파일
    app = open_app(folder)
    assert app.project.settings["files"]["sample_submission"] == "gender_submission.csv"
    os.rename(folder / "train.csv", folder / "train_v2.csv")
    app2 = open_app(folder)
    assert app2.project.settings["files"]["train"] == "train_v2.csv" and app2.project.notices
    parent = tmp_path
    write(tmp_path / "comp2", tr, te, ss)
    write(tmp_path / "comp3", tr, te, ss)
    a = App()
    r = a.open_project(str(parent))
    job = a.jobs.get(r["job"]["id"])
    while job.state == "running":
        time.sleep(0.05)
    assert job.state == "error" and "여러 개" in job.error
    assert a.project is not None and not a.project.loaded  # 파일을 직접 고를 수 있게 기억
    r = a.set_files({"train": str(folder / "train_v2.csv"), "test": str(folder / "test.csv")})
    job = a.jobs.get(r["job"]["id"])
    while job.state == "running":
        time.sleep(0.05)
    assert job.state == "done" and a.project.loaded


# A15: 값이 하나뿐인 타깃
def test_one_class_target(tmp_path):
    df = _binary_frame(500).assign(target=1)
    app = open_app(write(tmp_path / "one", df, None, None))
    chk = ready(app, app.checks)
    assert chk["items"][0]["id"] == "target_constant"
    with pytest.raises(LoadError):
        app.baseline({})
    app.correlation()


# A16: 처음 기본 모델을 돌릴 때 진행률이 뒤로 가지 않는다
def test_progress_monotonic(planted_dir):
    app = open_app(planted_dir)
    r = app.baseline({})
    job = app.jobs.get(r["job"]["id"])
    seen = []
    while job.state == "running":
        seen.append(job.progress)
        time.sleep(0.01)
    assert job.state == "done"
    assert all(b >= a - 1e-9 for a, b in zip(seen, seen[1:]))


# A17·A20·A26: 잘못된 입력은 한국어로, 다른 조건의 같은 작업은 거부
def test_bad_inputs(planted_dir):
    app = open_app(planted_dir)
    with pytest.raises(LoadError):
        app.rows({"limit": "abc"})
    e = app.ledger().add("x", "auc", 0.5)
    with pytest.raises(ValueError):
        app.update_experiment(e["id"], {"lb_public": "0.5a"})
    with pytest.raises(ValueError):
        dotbogi.log(str(planted_dir), name="bad", oof=np.zeros((len(app.project.train), 3)))
    r1 = app.adversarial(["x1"], rerun=True)
    with pytest.raises(LoadError):
        app.adversarial(["x2"], rerun=True)
    wait(app, r1)


# A19: 사용자 지표 교체가 실패하면 이전 지표 유지
def test_custom_metric_keeps_previous(planted_dir, tmp_path):
    app = open_app(planted_dir)
    good = tmp_path / "good.py"
    good.write_text("def score(y, p):\n    return float(((p - y) ** 2).mean())\n")
    app.update_settings({"custom_metric": {"path": str(good)}})
    bad = tmp_path / "bad.py"
    bad.write_text("def score(y, p):\n    raise RuntimeError('항상 실패')\n")
    with pytest.raises(LoadError):
        app.update_settings({"custom_metric": {"path": str(bad)}})
    assert app.project.settings["metric"] == "custom"
    txt = tmp_path / "m.txt"
    txt.write_text("x")
    with pytest.raises(LoadError):
        app.update_settings({"custom_metric": {"path": str(txt)}})


# A21·A22: 날짜 종류가 적으면 폴드가 줄었다고 알리고, 시간 검증 코드 조각은 fold < k
def test_few_dates_and_time_snippet(tmp_path):
    df = _binary_frame(600)
    df["date"] = np.where(np.arange(600) < 300, "2024-01-01", "2024-02-01")
    df["date"] = df["date"].where(np.arange(600) % 3 != 0, "2024-03-01")
    app = open_app(write(tmp_path / "dates", df, None, None))
    r = app.make_folds({"strategy": "time", "n_splits": 3, "time_col": "date"})
    assert r["notice"] and "2개" in r["notice"]
    info = ready(app, app.cv_info)
    assert "train.fold < k" in info["snippet"]


# A24: 깨진 설정 파일은 백업
def test_broken_project_json(planted_dir):
    app = open_app(planted_dir)
    (app.project.dir / "project.json").write_text("{깨짐", encoding="utf-8")
    app2 = open_app(planted_dir)
    assert any("깨져" in n for n in app2.project.notices)
    assert list(app2.project.dir.glob("project.broken-*.json"))


# A27: 머리글만 있는 train
def test_header_only_train(tmp_path):
    folder = tmp_path / "hdr"
    folder.mkdir()
    (folder / "train.csv").write_text("a,b,target\n")
    from dotbogi.project import Project
    with pytest.raises(LoadError, match="행이 없습니다"):
        Project(folder).load()


# 화면 검수 B8·B9·B10·B7: 지표 바꾸면 다시 채점, 한글 문장, 뺀 컬럼, 숫자×범주 그래프
def test_rescore_text_exclude_explore(planted_dir, tmp_path):
    app = open_app(planted_dir)
    app.update_settings({"excluded": ["leak_col"]})
    chk = ready(app, app.checks)
    ids = {it["id"] for it in chk["items"]}
    assert "excluded" in ids and "leak_suspect" not in ids
    wait(app, app.baseline({}))
    m = tmp_path / "m.py"
    m.write_text("import numpy as np\nHIGHER_IS_BETTER=False\ndef score(y, p):\n    return float(np.mean((p-y)**2))\n")
    app.update_settings({"custom_metric": {"path": str(m)}})
    ex = app.experiments()
    e = ex["experiments"][0]
    assert e.get("rescored") and not e["metric_mismatch"] and ex["best_cv_id"] == e["id"]
    r = app.explore({"x": "x1", "y": "grade"})
    assert r["type"] == "box" and r["note"]
    from dotbogi.schema import infer_kind
    reviews = pd.Series([f"배송이 빠르고 품질이 좋아요 {i}번째" if i % 2 else f"별로예요 다시는 안 사요 {i}" for i in range(300)])
    assert infer_kind(reviews, "review")[0] == "text"
