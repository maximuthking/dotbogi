"""검증 전략 추천과 폴드 만들기."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..schema import to_datetime_safe

STRATEGIES = {
    "kfold": "K-Fold (무작위)",
    "stratified": "층화 K-Fold",
    "group": "그룹 K-Fold",
    "stratified_group": "층화 그룹 K-Fold",
    "time": "시간 순서 검증",
}


def recommend(task: str, checks: list[dict], n_rows: int, y: np.ndarray | None = None) -> dict:
    """점검 결과를 보고 검증 방법을 고른다. 이유를 문장으로 같이 돌려준다."""
    by_id = {}
    for it in checks:
        by_id.setdefault(it["id"], it)
    reasons = []
    time_item = by_id.get("time_split")
    group_item = by_id.get("groups")
    n_splits = 5 if n_rows >= 500 else 3 if n_rows >= 100 else 2

    if time_item and (time_item.get("data") or {}).get("split") in ("after", "before"):
        col = time_item["columns"][0]
        reasons.append(f"test가 train과 다른 기간('{col}')이라, 과거로 학습하고 이후 기간으로 검증해야 리더보드와 비슷하게 나옵니다.")
        return {"strategy": "time", "time_col": col, "group_col": None, "n_splits": n_splits,
                "reasons": reasons, "label": STRATEGIES["time"]}
    if group_item:
        col = group_item["columns"][0]
        cand = (group_item.get("data") or {}).get("candidates", [{}])[0]
        reasons.append(f"test의 '{col}' 값 {cand.get('test_unseen_rate', 0):.0%}가 train에 없는 새 그룹입니다. "
                       "같은 그룹이 학습·검증에 동시에 들어가지 않게 해야 합니다.")
        n_groups = cand.get("n_groups", 0)
        if n_groups and n_groups < n_splits:
            n_splits = max(2, n_groups)
        strat = "stratified_group" if task in ("binary", "multiclass") else "group"
        if strat == "stratified_group":
            reasons.append("분류 문제라 폴드마다 클래스 비율도 맞춥니다.")
        return {"strategy": strat, "group_col": col, "time_col": None, "n_splits": n_splits,
                "reasons": reasons, "label": STRATEGIES[strat]}
    if task in ("binary", "multiclass"):
        reasons.append("train과 test가 같은 방식으로 뽑힌 것으로 보여 무작위로 나누되, 폴드마다 클래스 비율을 맞춥니다.")
        if by_id.get("rare_class"):
            reasons.append("드문 클래스가 있어 모든 폴드에 들어가도록 층화가 꼭 필요합니다.")
        return {"strategy": "stratified", "group_col": None, "time_col": None, "n_splits": n_splits,
                "reasons": reasons, "label": STRATEGIES["stratified"]}
    reasons.append("train과 test가 같은 방식으로 뽑힌 것으로 보여 무작위 K-Fold를 씁니다.")
    if by_id.get("dup_rows"):
        reasons.append("단, 완전히 같은 행이 있어 점수가 약간 부풀 수 있습니다.")
    return {"strategy": "kfold", "group_col": None, "time_col": None, "n_splits": n_splits,
            "reasons": reasons, "label": STRATEGIES["kfold"]}


def make_folds(train: pd.DataFrame, strategy: str, n_splits: int = 5, seed: int = 42,
               y: np.ndarray | None = None, y_mask: np.ndarray | None = None,
               group_col: str | None = None, time_col: str | None = None) -> np.ndarray:
    """각 train 행이 검증으로 쓰이는 폴드 번호. 검증에 안 쓰이는 행(시간 검증의 첫 구간, 타깃 결측)은 -1."""
    from sklearn.model_selection import GroupKFold, KFold, StratifiedGroupKFold, StratifiedKFold
    n = len(train)
    fold = np.full(n, -1, dtype=np.int64)
    valid = y_mask.copy() if y_mask is not None else np.ones(n, bool)
    idx = np.flatnonzero(valid)
    if len(idx) < n_splits * 2:
        raise ValueError("행이 너무 적어 폴드를 나눌 수 없습니다.")

    if strategy == "time":
        if not time_col:
            raise ValueError("시간 검증에는 날짜 컬럼이 필요합니다.")
        t = to_datetime_safe(train[time_col]).to_numpy()
        order = idx[np.argsort(t[idx], kind="stable")]
        # 시간 순으로 n_splits+1 구간: k번째 폴드는 (k+1)번째 구간을 검증, 그 이전 전부로 학습
        # 같은 시점이 두 구간에 걸치지 않도록 시점 경계에서 자른다.
        tt = t[order]
        cuts = [0]
        for k in range(1, n_splits + 1):
            pos = int(round(len(order) * k / (n_splits + 1)))
            while 0 < pos < len(order) and tt[pos] == tt[pos - 1]:
                pos += 1
            cuts.append(min(pos, len(order)))
        cuts.append(len(order))
        for k in range(n_splits):
            fold[order[cuts[k + 1]:cuts[k + 2]]] = k
        return fold

    yy = None
    if y is not None:
        yy = y[idx]
        if strategy in ("stratified", "stratified_group") and yy.dtype.kind == "f" and len(np.unique(yy)) > 50:
            yy = pd.qcut(yy, 10, labels=False, duplicates="drop")  # 회귀 타깃 층화용 구간

    if strategy in ("group", "stratified_group"):
        if not group_col:
            raise ValueError("그룹 검증에는 그룹 컬럼이 필요합니다.")
        groups = pd.factorize(train[group_col].astype("string").fillna("<NA>"))[0][idx]
        n_groups = len(np.unique(groups))
        if n_groups < n_splits:
            raise ValueError(f"그룹이 {n_groups}개뿐이라 {n_splits}개 폴드로 나눌 수 없습니다.")
        if strategy == "stratified_group" and yy is not None:
            splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
            splits = splitter.split(idx, yy, groups)
        else:
            # GroupKFold는 shuffle 지원이 버전마다 달라서, 그룹 순서를 섞어서 넘긴다
            rng = np.random.default_rng(seed)
            perm = rng.permutation(n_groups)
            splits = GroupKFold(n_splits=n_splits).split(idx, groups=perm[groups])
    elif strategy == "stratified" and yy is not None:
        splits = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=seed).split(idx, yy)
    else:
        splits = KFold(n_splits=n_splits, shuffle=True, random_state=seed).split(idx)
    for k, (_, va) in enumerate(splits):
        fold[idx[va]] = k
    return fold


def fold_summary(train: pd.DataFrame, fold: np.ndarray, task: str, y: np.ndarray | None,
                 classes: list | None = None, group_col: str | None = None,
                 time_col: str | None = None) -> list[dict]:
    out = []
    t = to_datetime_safe(train[time_col]) if time_col else None
    for k in sorted(set(fold.tolist())):
        sel = fold == k
        row = {"fold": int(k), "rows": int(sel.sum())}
        if y is not None and k >= 0:
            yy = y[sel]
            if task == "binary":
                row["positive_rate"] = float(np.mean(yy))
            elif task == "multiclass":
                row["top_class_rate"] = float(np.bincount(yy.astype(int)).max() / max(len(yy), 1))
            else:
                row["target_mean"] = float(np.nanmean(yy))
        if group_col:
            row["groups"] = int(train.loc[sel, group_col].nunique())
        if t is not None:
            tt = t[sel].dropna()
            if len(tt):
                row["time_from"] = f"{tt.min():%Y-%m-%d}"
                row["time_to"] = f"{tt.max():%Y-%m-%d}"
        out.append(row)
    return out
