"""분석 엔진 단위 테스트: 불러오기, 추론, 지표, 점검, 적대적 검증, 폴드, 기본 모델, 제출, 대장, 앙상블"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from conftest import make_groups, make_planted, make_time_group, write
from dotbogi import metrics as M
from dotbogi.analysis.adversarial import run_adversarial
from dotbogi.analysis.baseline import run_baseline
from dotbogi.analysis.checks import run_checks
from dotbogi.analysis.common import encode_target, oof_power, quantile_codes
from dotbogi.analysis.cv import make_folds, recommend
from dotbogi.analysis.features import build_matrix
from dotbogi.analysis.gbm import HAS_LGB
from dotbogi.analysis.profile import profile_column
from dotbogi.ensemble import run_ensemble
from dotbogi.experiments import Ledger, cv_lb_analysis, lb_noise, make_submission, suggest_final
from dotbogi.io import detect_encoding, read_table
from dotbogi.schema import guess_competition, infer_columns
from dotbogi.submission import check_submission, compare_submissions, fix_submission

ENGINES = ["sklearn"] + (["lightgbm"] if HAS_LGB else [])


# ───────────────────────────── 불러오기
def test_cp949_korean_csv(tmp_path):
    df = pd.DataFrame({"지역": ["서울", "부산", "대구"] * 50, "매출액": np.arange(150), "정답": [0, 1, 0] * 50})
    p = tmp_path / "train.csv"
    df.to_csv(p, index=False, encoding="cp949")
    assert detect_encoding(p) == "cp949"
    got = read_table(p)
    assert list(got.columns) == ["지역", "매출액", "정답"]
    assert got["지역"].iloc[0] == "서울"


def test_utf8_bom_tsv_and_duplicate_columns(tmp_path):
    p = tmp_path / "train.tsv"
    p.write_bytes("﻿a\ta\tb\n1\t2\t3\n4\t5\t6\n".encode("utf-8"))
    got = read_table(p)
    assert list(got.columns) == ["a", "a.1", "b"]


def test_parquet_cache(tmp_path):
    df = pd.DataFrame({"x": np.arange(400_000), "y": np.random.default_rng(0).random(400_000)})
    p = tmp_path / "big.csv"
    df.to_csv(p, index=False)
    cache = tmp_path / "cache"
    a = read_table(p, cache_dir=cache)
    assert len(list(cache.glob("*.parquet"))) == 1
    b = read_table(p, cache_dir=cache)
    assert a.shape == b.shape and np.allclose(a["y"], b["y"])


def test_missing_and_unsupported(tmp_path):
    from dotbogi.io import LoadError
    with pytest.raises(LoadError):
        read_table(tmp_path / "nope.csv")
    (tmp_path / "x.json").write_text("{}")
    with pytest.raises(LoadError):
        read_table(tmp_path / "x.json")


# ───────────────────────────── 추론
def test_guess_binary_planted():
    tr, te, ss = make_planted()
    cols = infer_columns(tr, te)
    g = guess_competition(tr, te, ss, cols)
    kinds = {c.name: c.kind for c in cols}
    assert g.target == ["target"] and g.id_col == "id" and g.task == "binary"
    assert kinds["const_col"] == "constant"
    assert kinds["grade"] == "categorical"


def test_guess_regression_datetime():
    tr, te, ss = make_time_group()
    cols = infer_columns(tr, te)
    g = guess_competition(tr, te, ss, cols)
    kinds = {c.name: c.kind for c in cols}
    assert kinds["date"] == "datetime"
    assert g.target == ["sales"] and g.id_col == "row_id" and g.task == "regression"


def test_guess_multiclass_label_and_proba_columns():
    tr, te, ss = make_groups()
    g = guess_competition(tr, te, ss, infer_columns(tr, te))
    assert g.task == "multiclass" and g.target == ["label"] and g.id_col == "uid"
    proba = pd.DataFrame({"uid": te["uid"], "high": 0.3, "low": 0.3, "mid": 0.4})
    g2 = guess_competition(tr, te, proba, infer_columns(tr, te))
    assert g2.submission_format == "proba_columns" and g2.classes == ["high", "low", "mid"]


# ───────────────────────────── 지표
def test_metrics_match_sklearn():
    from sklearn.metrics import log_loss, mean_absolute_error, roc_auc_score
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 500)
    p = np.clip(y * 0.6 + rng.random(500) * 0.4, 0.01, 0.99)
    assert M.score("auc", y, p) == pytest.approx(roc_auc_score(y, p))
    assert M.score("logloss", y, p) == pytest.approx(log_loss(y, p))
    yr, pr = rng.normal(size=300), rng.normal(size=300)
    assert M.score("mae", yr, pr) == pytest.approx(mean_absolute_error(yr, pr))
    assert M.score("brier", y, p) == pytest.approx(np.mean((p - y) ** 2))
    assert 0 <= M.score("ece", y, p) <= 1
    P = rng.dirichlet(np.ones(3), 200)
    yc = rng.integers(0, 3, 200)
    assert M.score("mlogloss", yc, P) == pytest.approx(log_loss(yc, P, labels=[0, 1, 2]))
    assert M.better("rmse", 1.0, 2.0) and M.better("auc", 0.9, 0.8)


def test_custom_metric(tmp_path):
    f = tmp_path / "metric.py"
    f.write_text("NAME='반전 AUC'\nHIGHER_IS_BETTER=False\nfrom sklearn.metrics import roc_auc_score\n"
                 "def score(y, p):\n    return 1 - roc_auc_score(y, p)\n", encoding="utf-8")
    m = M.register_custom(str(f), "binary", True, "proba")
    try:
        assert m.label == "반전 AUC" and m.higher_is_better is False
        assert M.score("custom", np.array([0, 1, 1, 0]), np.array([0.1, 0.9, 0.8, 0.2])) == pytest.approx(0.0)
    finally:
        M.unregister_custom()
    bad = tmp_path / "bad.py"
    bad.write_text("def nope(): pass\n")
    with pytest.raises(ValueError):
        M.register_custom(str(bad), "binary")


# ───────────────────────────── 단일 피처 예측력
def test_oof_power_not_fooled_by_ids():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 5000).astype(float)
    ids = np.arange(5000)  # 고유값 → 외우면 AUC 1, OOF로는 0.5 근처
    p = oof_power(ids, y, "binary")
    assert p["value"] < 0.6
    strong = oof_power(quantile_codes(y + rng.normal(scale=0.1, size=5000))[0], y, "binary")
    assert strong["value"] > 0.95


# ───────────────────────────── 점검 (심어 둔 문제를 모두 찾는가)
def _run_checks(tr, te, ss):
    cols = infer_columns(tr, te)
    g = guess_competition(tr, te, ss, cols)
    y, mask, classes = encode_target(tr[g.target[0]], g.task, g.classes)
    prof = {c.name: profile_column(c.name, c.kind, c.discrete, tr[c.name] if c.in_train else None,
                                   te[c.name] if c.in_test else None, y, mask, g.task, classes)
            for c in cols if c.name not in g.target}
    items = run_checks(tr, te, ss, cols, g.target, g.id_col, g.task, y, mask, prof)
    return items, g, y


def test_checks_find_planted_problems():
    items, g, y = _run_checks(*make_planted())
    by = {it["id"]: it for it in items}
    assert "leak_col" in by["leak_suspect"]["columns"] and by["leak_suspect"]["level"] == "danger"
    assert by["overlap"]["level"] in ("danger", "warn") and by["overlap"]["data"]["n_overlap"] >= 30
    assert "dup_rows" in by
    assert "const_col" in by["constant"]["columns"]
    assert "num_as_text" in by["numeric_as_text"]["columns"]
    assert "city" in by["dirty_categories"]["columns"]
    assert "city" in by["unseen"]["columns"]
    assert "shift_col" in by["drift"]["columns"]
    assert "miss_gap" in by["missing_gap"]["columns"]
    assert "order_leak" in by
    levels = [it["level"] for it in items]
    assert levels == sorted(levels, key=["danger", "warn", "info", "ok"].index)


def test_checks_time_and_group_and_recommendation():
    items, g, y = _run_checks(*make_time_group())
    by = {it["id"]: it for it in items}
    assert by["time_split"]["data"]["split"] == "after"
    rec = recommend(g.task, items, 3000, y)
    assert rec["strategy"] == "time" and rec["time_col"] == "date"

    items, g, y = _run_checks(*make_groups())
    by = {it["id"]: it for it in items}
    assert "user_id" in by["groups"]["columns"]
    rec = recommend(g.task, items, 3000, y)
    assert rec["strategy"] == "stratified_group" and rec["group_col"] == "user_id"


# ───────────────────────────── 적대적 검증
@pytest.mark.parametrize("engine", ENGINES)
def test_adversarial(engine):
    tr, te, ss = make_planted()
    cols = infer_columns(tr, te)
    mat = build_matrix(tr, te, [c for c in cols if c.name not in ("target", "id")])
    r = run_adversarial(mat, engine=engine, max_rows_each=3000)
    assert r["auc"] > 0.8
    top = r["features"][0]["name"] if engine == "lightgbm" else max(r["features"], key=lambda f: f["single_auc"] or 0)["name"]
    assert top in ("shift_col", "city")
    assert len(r["_train_scores"]) == len(tr)
    sh = tr.sample(frac=1, random_state=0).reset_index(drop=True)  # 무작위로 둘로 나누면 구분이 안 돼야
    same = build_matrix(sh.iloc[:1500], sh.iloc[1500:].drop(columns=["target"]),
                        [c for c in cols if c.name not in ("target", "id", "shift_col", "city", "miss_gap")])
    r2 = run_adversarial(same, engine=engine)
    assert r2["auc"] < 0.6


# ───────────────────────────── 폴드
def test_folds_strategies():
    tr, te, ss = make_groups()
    y, mask, classes = encode_target(tr["label"], "multiclass")
    f = make_folds(tr, "stratified_group", 5, 0, y, mask, group_col="user_id")
    assert set(f) == set(range(5))
    for k in range(5):  # 같은 사용자가 두 폴드에 나뉘지 않는다
        assert not set(tr.user_id[f == k]) & set(tr.user_id[f != k])
    f2 = make_folds(tr, "group", 4, 0, y, mask, group_col="user_id")
    assert set(f2) == set(range(4))

    tr, te, ss = make_time_group()
    yr, mr, _ = encode_target(tr["sales"], "regression")
    ft = make_folds(tr, "time", 4, 0, yr, mr, time_col="date")
    assert (ft == -1).any()
    d = pd.to_datetime(tr["date"])
    for k in range(3):  # 다음 폴드는 항상 더 뒤의 기간
        assert d[ft == k].max() < d[ft == k + 1].min()
    fs = make_folds(tr, "stratified", 5, 0, yr, mr)  # 회귀 층화도 동작
    assert set(fs) == set(range(5))
    with pytest.raises(ValueError):
        make_folds(tr.iloc[:4], "kfold", 5, 0)


# ───────────────────────────── 기본 모델 (세 과제 × 두 엔진)
@pytest.mark.parametrize("engine", ENGINES)
@pytest.mark.parametrize("kind", ["binary", "multiclass", "regression"])
def test_baseline_all_tasks(engine, kind):
    if kind == "binary":
        tr, te, ss = make_planted()
        tr = tr.drop(columns=["leak_col"]); te = te.drop(columns=["leak_col"])
        target, metric, strat, extra = "target", "auc", "stratified", {}
    elif kind == "multiclass":
        tr, te, ss = make_groups()
        target, metric, strat, extra = "label", "mlogloss", "stratified_group", {"group_col": "user_id"}
    else:
        tr, te, ss = make_time_group()
        target, metric, strat, extra = "sales", "rmse", "time", {"time_col": "date"}
    cols = infer_columns(tr, te)
    g = guess_competition(tr, te, ss, cols)
    y, mask, classes = encode_target(tr[target], g.task, g.classes)
    fold = make_folds(tr, strat, 4, 0, y, mask, **extra)
    exclude = {target, g.id_col} | ({extra["group_col"]} if "group_col" in extra else set())
    mat = build_matrix(tr, te, [c for c in cols if c.name not in exclude])
    n_classes = len(classes) if g.task == "multiclass" else 2
    r = run_baseline(mat, y, mask, g.task, n_classes, fold, metric, strat, engine=engine, n_estimators=200)
    assert np.isfinite(r["cv"]) and len(r["fold_scores"]) == 4
    used = r["_used"]
    assert used.sum() == (fold >= 0).sum()
    assert r["_test"].shape[0] == len(te)
    if kind == "binary":
        assert r["cv"] > 0.7
    if kind == "multiclass":
        assert r["_oof"].shape[1] == 3 and r["cv"] < 1.0
    sub = make_submission(r["_test"], ss, te, g.id_col, g.task, classes, g.submission_format, metric)
    chk = check_submission(sub, ss, g.id_col, g.task, metric, classes, g.submission_format, tr[target])
    assert chk["ok"], chk["items"]


# ───────────────────────────── 제출 검사
def test_submission_checks_and_fix():
    tr, te, ss = make_planted()
    good = ss.copy()
    good["target"] = np.random.default_rng(0).random(len(ss))
    r = check_submission(good, ss, "id", "binary", "auc", [0, 1], "value", tr["target"])
    assert r["ok"]
    bad = good.sample(frac=1, random_state=0)
    bad["target"] = bad["target"] * 1.5
    bad.insert(0, "Unnamed: 0", 0)
    bad = bad.rename(columns={"target": "Target "})
    r = check_submission(bad, ss, "id", "binary", "auc", [0, 1], "value", tr["target"])
    titles = " ".join(it["title"] for it in r["items"])
    assert not r["ok"] and "인덱스" in titles and "대소문자" in titles
    fixed, done = fix_submission(bad, ss, "id", "binary")
    assert list(fixed.columns) == ["id", "target"] and (fixed["id"].to_numpy() == ss["id"].to_numpy()).all()
    assert fixed["target"].max() <= 1
    r2 = check_submission(fixed, ss, "id", "binary", "auc", [0, 1], "value", tr["target"])
    assert r2["ok"], r2["items"]
    # 앞자리 0이 사라진 ID
    s0 = pd.DataFrame({"id": ["0012", "0013"], "p": [0.1, 0.2]})
    g0 = pd.DataFrame({"id": [12, 13], "p": [0.1, 0.2]})
    r3 = check_submission(g0, s0, "id", "binary", "auc", [0, 1])
    assert not r3["ok"] and any("앞자리 0" in it["detail"] for it in r3["items"])
    cmp = compare_submissions(good, fixed, "id", ["target"])
    assert cmp["matched_rows"] == len(ss)


def test_submission_multiclass_and_regression():
    sample = pd.DataFrame({"id": [1, 2, 3], "a": 0.3, "b": 0.3, "c": 0.4})
    sub = sample.copy()
    sub[["a", "b", "c"]] = [[0.5, 0.5, 0.5], [0.2, 0.2, 0.6], [1.2, -0.1, 0.1]]
    r = check_submission(sub, sample, "id", "multiclass", "mlogloss", ["a", "b", "c"], "proba_columns")
    assert not r["ok"]
    fixed, done = fix_submission(sub, sample, "id", "multiclass", "proba_columns")
    assert np.allclose(fixed[["a", "b", "c"]].sum(axis=1), 1)
    reg_s = pd.DataFrame({"id": [1, 2], "y": 0.0})
    reg = pd.DataFrame({"id": [1, 2], "y": [-3.0, 5.0]})
    r = check_submission(reg, reg_s, "id", "regression", "rmse", [], "value", pd.Series([1.0, 2.0, 3.0]))
    assert any("음수" in it["title"] for it in r["items"])


# ───────────────────────────── 대장·LB 흔들림·앙상블
def test_ledger_noise_ensemble(tmp_path):
    rng = np.random.default_rng(0)
    n = 4000
    y = rng.integers(0, 2, n).astype(float)
    a = np.clip(y * 0.3 + rng.random(n) * 0.7, 0, 1)
    b = np.clip(y * 0.3 + rng.random(n) * 0.7, 0, 1)
    c = rng.random(n)
    fold = np.arange(n) % 5
    led = Ledger(tmp_path / ".dotbogi")
    e1 = led.add("a", "auc", M.score("auc", y, a), lb_public=0.80)
    e2 = led.add("b", "auc", M.score("auc", y, b), lb_public=0.81)
    e3 = led.add("c", "auc", M.score("auc", y, c), lb_public=0.5)
    led.update(e1["id"], notes="메모", lb_private=0.79)
    assert led.get(e1["id"])["lb_private"] == 0.79
    res = cv_lb_analysis(led.load(), "auc")
    assert res["n"] == 3 and res["verdict"] in ("aligned", "weak", "mismatch")
    sug = suggest_final(led.load(), "auc", 2)
    assert len(sug["picks"]) == 2 and sug["picks"][0]["name"] in ("a", "b")
    led.delete(e3["id"])
    assert len(led.load()) == 2 and (tmp_path / ".dotbogi" / "trash" / f"{e3['id']}.json").exists()
    noise = lb_noise(y, a, "auc", 1000, pred_b=b)
    assert noise["ok"] and 0 <= noise["win_rate"] <= 1 and noise["std"] > 0
    er = run_ensemble(["a", "b", "c"], [a, b, c], y, "auc", fold)
    w = {d["name"]: d["weight"] for d in er["weights"]}
    assert all(v >= 0 for v in w.values()) and abs(sum(w.values()) - 1) < 1e-9
    assert w["c"] < 0.2  # 쓸모없는 모델은 거의 안 섞음
    assert er["score"] >= max(M.score("auc", y, a), M.score("auc", y, b)) - 1e-9
    assert er["honest"] is not None and len(er["honest"]["fold_scores"]) == 5
    with pytest.raises(ValueError):
        run_ensemble(["a"], [a], y, "auc")


def test_profile_kinds():
    tr, te, ss = make_time_group()
    y, mask, _ = encode_target(tr["sales"], "regression")
    p = profile_column("date", "datetime", False, tr["date"], te["date"], y, mask, "regression", [])
    assert p["dist"]["datetime"] and p["drift"]["level"] == "shift"
    text_tr = pd.Series(["a quick brown fox jumps over"] * 50 + ["short one here today ok"] * 50)
    p2 = profile_column("t", "text", False, text_tr, text_tr, None, None, "binary", [0, 1])
    assert p2["basis"] == "length" and p2["drift"]["level"] == "stable"
    cat = pd.Series([f"v{i}" for i in range(500)])
    p3 = profile_column("c", "categorical", False, cat, pd.Series([f"w{i}" for i in range(200)]), None, None, "binary", [0, 1])
    assert p3["drift"]["level_basis"] == "unseen" and p3["drift"]["level"] == "shift"
    allnan = pd.Series([np.nan] * 10)
    p4 = profile_column("n", "constant", False, allnan, allnan, None, None, "binary", [0, 1])
    assert p4["train"]["missing_rate"] == 1.0
