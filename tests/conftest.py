"""테스트용 합성 대회 데이터. 일부러 문제를 심어 두고 돋보기가 찾는지 본다."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def make_planted(n_train: int = 3000, n_test: int = 1500, seed: int = 0) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """이진분류 대회. 심어 둔 문제:
    - leak_col: 타깃을 거의 그대로 담은 누수 컬럼
    - const_col: 값이 하나뿐
    - num_as_text: 숫자인데 일부가 '-'인 문자 컬럼
    - city: 'Seoul'과 'seoul '처럼 공백·대소문자만 다른 범주, test에 새 범주(Jeju)
    - shift_col: test에서 분포가 크게 이동
    - 행 순서/ID가 타깃 순으로 정렬됨(순서 누수)
    - train 안 완전 중복 행, test 행 일부가 train 행과 똑같음
    - 결측 비율이 train/test에서 다른 컬럼
    """
    rng = np.random.default_rng(seed)
    n = n_train + n_test
    x1 = rng.normal(size=n)
    x2 = rng.uniform(0, 10, size=n)
    cat = rng.choice(["A", "B", "C", "D"], size=n, p=[0.4, 0.3, 0.2, 0.1])
    logit = 1.2 * x1 - 0.3 * x2 + (cat == "A") * 0.8 + 1.0
    y = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int)
    df = pd.DataFrame({
        "x1": x1, "x2": x2, "grade": cat,
        "leak_col": y + rng.normal(scale=0.01, size=n),
        "const_col": 7,
        "num_as_text": np.where(rng.random(n) < 0.05, "-", np.round(rng.normal(100, 10, size=n), 1).astype(str)),
        "city": rng.choice(["Seoul", "Busan", "seoul ", "Incheon"], size=n, p=[0.4, 0.3, 0.1, 0.2]),
        "shift_col": rng.normal(size=n),
        "miss_gap": rng.normal(size=n),
        "target": y,
    })
    train = df.iloc[:n_train].copy()
    test = df.iloc[n_train:].drop(columns=["target"]).copy()
    # test 분포 이동, 새 범주, 결측 차이
    test["shift_col"] = test["shift_col"] + 2.5
    test.loc[test.sample(frac=0.2, random_state=1).index, "city"] = "Jeju"
    train.loc[train.sample(frac=0.02, random_state=2).index, "miss_gap"] = np.nan
    test.loc[test.sample(frac=0.4, random_state=3).index, "miss_gap"] = np.nan
    # 타깃 순 정렬 + 순서대로 ID (ID/행 순서 누수)
    train = train.sort_values("target", kind="stable").reset_index(drop=True)
    train.insert(0, "id", np.arange(len(train)))
    test.insert(0, "id", np.arange(len(train), len(train) + len(test)))
    # train 안 중복 행 20개, test 행 30개를 train 행으로 덮어쓰기(입력값 동일)
    dup = train.sample(20, random_state=4).copy()
    dup["id"] = np.arange(len(train), len(train) + 20)
    train = pd.concat([train, dup], ignore_index=True)
    test["id"] = np.arange(len(train), len(train) + len(test))
    feats = [c for c in train.columns if c not in ("id", "target")]
    src = train.sample(30, random_state=5)[feats].to_numpy()
    test.iloc[:30, [test.columns.get_loc(c) for c in feats]] = src
    # 완전 중복 행이 되게 id도 같게 (id는 비교에서 빠지지만 duplicated() 검사용)
    train.loc[train.index[-20:], "id"] = train.loc[dup.index, "id"].to_numpy()
    sample = pd.DataFrame({"id": test["id"].to_numpy(), "target": 0.5})
    return train, test, sample


def make_time_group(seed: int = 0):
    """회귀 대회: 날짜로 나뉜 test(미래), 가게(store) 단위 반복."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=200, freq="D")
    rows = []
    for d in dates:
        for s in range(15):
            rows.append((d, s, rng.normal(10 + s, 2) + d.dayofweek))
    df = pd.DataFrame(rows, columns=["date", "store", "sales"])
    df["promo"] = rng.integers(0, 2, len(df))
    df["sales"] += df["promo"] * 3
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    train = df[df["date"] < "2024-06-01"].reset_index(drop=True)
    test = df[df["date"] >= "2024-06-01"].drop(columns=["sales"]).reset_index(drop=True)
    train.insert(0, "row_id", np.arange(len(train)))
    test.insert(0, "row_id", np.arange(len(train), len(train) + len(test)))
    sample = pd.DataFrame({"row_id": test["row_id"], "sales": 0.0})
    return train, test, sample


def make_groups(seed: int = 0):
    """test가 train에 없는 사용자(user_id)로 이뤄진 다중분류 대회."""
    rng = np.random.default_rng(seed)
    users = np.arange(300)
    rows = []
    for u in users:
        bias = rng.normal()
        for _ in range(rng.integers(5, 15)):
            f = rng.normal() + bias
            label = "low" if f < -0.5 else ("mid" if f < 0.5 else "high")
            rows.append((u, f, rng.normal(), label))
    df = pd.DataFrame(rows, columns=["user_id", "feat", "noise", "label"])
    tr_users = set(users[:220])
    train = df[df.user_id.isin(tr_users)].reset_index(drop=True)
    test = df[~df.user_id.isin(tr_users)].drop(columns=["label"]).reset_index(drop=True)
    train.insert(0, "uid", [f"tr{i:05d}" for i in range(len(train))])
    test.insert(0, "uid", [f"te{i:05d}" for i in range(len(test))])
    sample = pd.DataFrame({"uid": test["uid"], "label": "mid"})
    return train, test, sample


def write(folder, train, test, sample, encoding="utf-8", names=("train.csv", "test.csv", "sample_submission.csv")):
    folder.mkdir(parents=True, exist_ok=True)
    train.to_csv(folder / names[0], index=False, encoding=encoding)
    if test is not None:
        test.to_csv(folder / names[1], index=False, encoding=encoding)
    if sample is not None:
        sample.to_csv(folder / names[2], index=False, encoding=encoding)
    return folder


@pytest.fixture
def planted_dir(tmp_path):
    return write(tmp_path / "planted", *make_planted())


@pytest.fixture
def time_dir(tmp_path):
    return write(tmp_path / "timeseries", *make_time_group())


@pytest.fixture
def group_dir(tmp_path):
    return write(tmp_path / "groups", *make_groups())


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """최근 목록 등 사용자 홈에 쓰는 파일을 테스트 폴더로 돌린다."""
    home = tmp_path / "_home"
    monkeypatch.setenv("DOTBOGI_HOME", str(home))
    import dotbogi.api as api
    monkeypatch.setattr(api, "HOME", home)
    yield home


def open_app(folder):
    from dotbogi.api import App
    from dotbogi.project import Project
    app = App()
    p = Project(folder)
    p.load()
    app.project = p
    return app


def wait(app, res):
    """{ready: False, job} 또는 {job} 응답의 작업을 끝까지 기다린다."""
    import time
    info = res.get("job") if isinstance(res, dict) else None
    if not info:
        return None
    job = app.jobs.get(info["id"])
    t0 = time.time()
    while job.state == "running":
        time.sleep(0.05)
        assert time.time() - t0 < 300, "작업이 너무 오래 걸립니다"
    assert job.state == "done", f"작업 실패: {job.error}\n{job.detail}"
    return job.result


def ready(app, fn, *args):
    for _ in range(5):
        r = fn(*args)
        if not (isinstance(r, dict) and r.get("ready") is False):
            return r
        wait(app, r)
    raise AssertionError("결과가 준비되지 않았습니다")
