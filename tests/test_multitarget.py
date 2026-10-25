"""다중 타깃 대회: OOF·test 예측을 타깃마다 저장하고, 점수는 타깃별 점수의 평균으로 계산한다."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import dotbogi
from conftest import open_app, wait, write
from dotbogi import metrics as M
from dotbogi.experiments import Ledger


def make_multi(task: str, n: int = 800, n_test: int = 300, seed: int = 3):
    rng = np.random.default_rng(seed)
    m = n + n_test
    x1, x2 = rng.normal(size=m), rng.uniform(0, 4, size=m)
    grade = rng.choice(["A", "B", "C"], size=m)
    if task == "regression":
        t1 = 3 * x1 + (grade == "A") + rng.normal(scale=0.5, size=m)
        t2 = -2 * x2 + rng.normal(scale=0.5, size=m)
    else:
        t1 = (x1 + rng.normal(scale=0.5, size=m) > 0).astype(int)
        t2 = (x2 + rng.normal(scale=0.5, size=m) > 2).astype(int)
    df = pd.DataFrame({"uid": np.arange(m), "x1": x1, "x2": x2, "grade": grade, "t1": t1, "t2": t2})
    train = df.iloc[:n].reset_index(drop=True)
    test = df.iloc[n:].drop(columns=["t1", "t2"]).reset_index(drop=True)
    sample = pd.DataFrame({"uid": test["uid"], "t1": 0.0, "t2": 0.0})
    return train, test, sample


@pytest.fixture(params=["regression", "binary"])
def multi_app(request, tmp_path):
    folder = write(tmp_path / f"multi_{request.param}", *make_multi(request.param))
    app = open_app(folder)
    p = app.project
    if p.settings["target"] != ["t1", "t2"]:
        app.update_settings({"target": ["t1", "t2"]})
    if p.settings["task"] != request.param:
        app.update_settings({"task": request.param})
    return app, folder, request.param


def test_score_averages_targets():
    y = np.array([[1.0, 2.0], [2.0, 4.0], [3.0, 6.0]])
    pred = np.array([[1.0, 2.0], [2.0, 5.0], [3.0, 6.0]])
    expect = np.mean([M.score("rmse", y[:, 0], pred[:, 0]), M.score("rmse", y[:, 1], pred[:, 1])])
    assert M.score("rmse", y, pred) == pytest.approx(expect)


def test_truth_is_two_dimensional(multi_app):
    app, _, task = multi_app
    tr = app._truth(app.project)
    assert tr["multi"] and tr["targets"] == ["t1", "t2"]
    assert tr["y"].shape == (len(app.project.train), 2)


def test_baseline_saves_every_target(multi_app):
    app, _, task = multi_app
    res = wait(app, app.baseline({}))
    e = res["experiment"]
    led = Ledger(app.project.dir)
    oof = led.read_oof(e)
    assert {"pred:t1", "pred:t2"} <= set(oof.columns)
    sub = pd.read_csv(led.file_path(e, "submission"))
    assert list(sub.columns) == ["uid", "t1", "t2"]
    assert sub["t1"].nunique() > 1 and sub["t2"].nunique() > 1  # 두 타깃 모두 채워짐
    by = e["params"]["cv_by_target"]
    assert e["cv"] == pytest.approx(np.mean([by["t1"], by["t2"]]))
    assert "첫 타깃" not in e["notes"]
    # 다시 채점해도 같은 값 (OOF가 두 타깃 모두 있으므로)
    tr = app._truth(app.project)
    pred = app._pred(app.project, oof)
    ok = tr["mask"] & ~np.isnan(pred).any(axis=1)
    assert M.score(app.project.settings["metric"], tr["y"][ok], pred[ok]) == pytest.approx(e["cv"], rel=1e-6)


def test_log_ensemble_noise_and_sheet(multi_app):
    app, folder, task = multi_app
    p = app.project
    tr = app._truth(p)
    rng = np.random.default_rng(0)
    y = tr["y"]
    noise = 0.6 if task == "regression" else 0.25
    exps = []
    for k in range(2):
        oof = y + rng.normal(scale=noise, size=y.shape)
        tp = rng.normal(size=(len(p.test), 2))
        if task == "binary":
            oof, tp = np.clip(oof, 0, 1), 1 / (1 + np.exp(-tp))
        exps.append(dotbogi.log(str(folder), name=f"m{k}", oof=oof, test_pred=tp))
        expect = M.score(p.settings["metric"], y, oof)
        assert exps[-1]["cv"] == pytest.approx(expect)

    # 모양이 틀리면 분명한 오류
    with pytest.raises(ValueError, match="타깃 2개"):
        dotbogi.log(str(folder), name="bad", oof=y[:, 0])

    res = wait(app, app.ensemble({"ids": [e["id"] for e in exps]}))
    assert [b["target"] for b in res["by_target"]] == ["t1", "t2"]
    saved = app.ensemble_save({})
    assert saved["has_submission"]
    sub = pd.read_csv(Ledger(p.dir).file_path(saved["experiment"], "submission"))
    assert {"t1", "t2"} <= set(sub.columns)

    noise_res = app.lb_noise({"id": exps[0]["id"], "id_b": exps[1]["id"]})
    assert noise_res["ok"] and noise_res["targets"] == ["t1", "t2"]

    sheet = app.sheet({"which": "train", "exp": exps[0]["id"], "limit": 5})
    names = [c["name"] for c in sheet["columns"] if c["extra"]]
    assert any(n.startswith("예측 · t1") for n in names) and any(n.startswith("예측 · t2") for n in names)
    assert any(n.startswith("오차 · t2") for n in names)


def test_old_single_target_oof_is_reported(multi_app):
    """예전 버전처럼 첫 타깃 OOF만 있는 기록은 앙상블에서 분명하게 알려 준다."""
    app, folder, task = multi_app
    p = app.project
    y = app._truth(p)["y"]
    a = dotbogi.log(str(folder), name="full", oof=y.astype(float))
    led = Ledger(p.dir)
    old = led.add("old", p.settings["metric"], 0.5, source="script",
                  oof=pd.DataFrame({"row": np.arange(len(y)), "pred": y[:, 0].astype(float)}))
    from dotbogi.io import LoadError
    with pytest.raises(LoadError, match="일부 타깃"):
        app._ensemble_job(type("J", (), {"update": lambda *a, **k: None})(), p, {"ids": [a["id"], old["id"]]})
