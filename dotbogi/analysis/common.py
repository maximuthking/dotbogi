"""분석 모듈 공통: 타깃 인코딩, AUC, 단일 피처 예측력(OOF), 구간 나누기."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import rankdata

from ..utils import to_float


def encode_target(y: pd.Series, task: str, classes: list | None = None):
    """타깃을 숫자 배열로. 이진: 0/1(두 번째 클래스가 1), 다중: 0..K-1 코드, 회귀: float.
    반환: (값 배열, 유효 마스크, 클래스 목록)"""
    if task == "regression":
        v = to_float(y)
        return v, np.isfinite(v), []
    if not classes:
        classes = sorted((_norm(v) for v in pd.unique(y.dropna())), key=lambda v: (str(type(v)), v))
    lookup = {str(_norm(c)): i for i, c in enumerate(classes)}
    raw_codes, uniques = pd.factorize(y, use_na_sentinel=True)
    u_map = np.array([lookup.get(str(_norm(u)), -1) for u in uniques] + [-1], dtype=np.int64)
    codes = u_map[raw_codes]  # 결측(-1)은 마지막 칸(-1)으로
    mask = codes >= 0
    if task == "binary":
        return (codes == 1).astype("float64"), mask, list(classes)
    return codes, mask, list(classes)


def _norm(v):
    if isinstance(v, np.generic):
        v = v.item()
    if isinstance(v, float) and v.is_integer():
        return int(v)
    return v


def auc_score(y01: np.ndarray, score: np.ndarray) -> float:
    """순위 기반 ROC AUC (동점은 평균 순위). 한쪽 클래스만 있으면 NaN."""
    y01 = np.asarray(y01, dtype=bool)
    n_pos = int(y01.sum())
    n_neg = int(len(y01) - n_pos)
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    r = rankdata(score)
    return float((r[y01].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def quantile_codes(x: np.ndarray, n_bins: int = 20, edges: np.ndarray | None = None):
    """숫자 배열을 분위수 구간 코드로. NaN은 마지막 코드. (코드, 경계) 반환."""
    finite = np.isfinite(x)
    if edges is None:
        fx = x[finite]
        if fx.size == 0:
            edges = np.array([0.0])
        else:
            edges = np.unique(np.quantile(fx, np.linspace(0, 1, n_bins + 1)[1:-1]))
    codes = np.searchsorted(edges, x, side="right")
    codes[~finite] = len(edges) + 1
    return codes.astype(np.int64), edges


def category_codes(s: pd.Series):
    codes, uniques = pd.factorize(s, use_na_sentinel=True)
    codes = codes.astype(np.int64)
    codes[codes < 0] = len(uniques)
    return codes, uniques


def feature_codes(s: pd.Series, kind: str, n_bins: int = 20) -> np.ndarray:
    if kind in ("numeric", "datetime") and not (kind == "numeric" and s.nunique() <= n_bins):
        return quantile_codes(to_float(s), n_bins)[0]
    return category_codes(s)[0]


def oof_power(codes: np.ndarray, y: np.ndarray, task: str, n_folds: int = 5,
              smoothing: float = 20.0, seed: int = 42, max_rows: int = 1_000_000) -> dict:
    """구간/카테고리 코드 하나로 타깃을 얼마나 맞추는지 OOF 타깃 인코딩으로 잰다.
    고유값이 많은 컬럼이 학습 데이터를 외워서 점수가 부풀려지는 걸 막는다.
    반환: {"metric": 이름, "value": 원점수, "power": 0~1 정규화 점수}"""
    n = len(codes)
    rng = np.random.default_rng(seed)
    idx = np.arange(n)
    if n > max_rows:
        idx = np.sort(rng.choice(n, size=max_rows, replace=False))
        codes, y = codes[idx], y[idx]
        n = max_rows
    if n < n_folds * 4:
        return {"metric": None, "value": None, "power": None}
    fold = rng.permutation(n) % n_folds
    n_codes = int(codes.max()) + 1

    if task == "multiclass":
        y = y.astype(np.int64)
        counts = np.bincount(y)
        top = np.argsort(counts)[::-1][:20]
        top = [k for k in top if counts[k] > 0 and counts[k] < n]
        if not top:
            return {"metric": None, "value": None, "power": None}
        aucs, weights = [], []
        for k in top:
            yk = (y == k).astype("float64")
            enc = _oof_encode(codes, yk, fold, n_folds, n_codes, smoothing)
            a = auc_score(yk, enc)
            if np.isfinite(a):
                aucs.append(a)
                weights.append(counts[k])
        if not aucs:
            return {"metric": None, "value": None, "power": None}
        auc = float(np.average(aucs, weights=weights))
        return {"metric": "macro_auc", "value": auc, "power": max(0.0, (auc - 0.5) * 2)}

    y = y.astype("float64")
    enc = _oof_encode(codes, y, fold, n_folds, n_codes, smoothing)
    if task == "binary":
        auc = auc_score(y, enc)
        if not np.isfinite(auc):
            return {"metric": None, "value": None, "power": None}
        return {"metric": "auc", "value": auc, "power": max(0.0, (auc - 0.5) * 2)}
    sst = float(((y - y.mean()) ** 2).sum())
    if sst <= 0:
        return {"metric": None, "value": None, "power": None}
    r2 = 1 - float(((y - enc) ** 2).sum()) / sst
    return {"metric": "r2", "value": r2, "power": max(0.0, r2)}


def _oof_encode(codes, y, fold, n_folds, n_codes, smoothing):
    enc = np.empty(len(y), dtype="float64")
    for f in range(n_folds):
        va = fold == f
        tr = ~va
        prior = y[tr].mean()
        s = np.bincount(codes[tr], weights=y[tr], minlength=n_codes)
        c = np.bincount(codes[tr], minlength=n_codes)
        table = (s + prior * smoothing) / (c + smoothing)
        enc[va] = table[codes[va]]
    return enc
