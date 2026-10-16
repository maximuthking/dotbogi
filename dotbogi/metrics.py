"""대회에서 자주 쓰는 평가 지표. 예측 형태(확률/라벨/값)와 높을수록 좋은지 여부를 같이 관리한다."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from .analysis.common import auc_score


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    tasks: tuple[str, ...]
    higher_is_better: bool
    needs: str  # proba | label | value
    fn: Callable[[np.ndarray, np.ndarray], float]
    note: str = ""


def _clip(p, eps=1e-15):
    return np.clip(p, eps, 1 - eps)


def _logloss_bin(y, p):
    p = _clip(np.asarray(p, float))
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def _logloss_multi(y, P):
    P = np.asarray(P, float)
    P = _clip(P / P.sum(axis=1, keepdims=True))
    return float(-np.mean(np.log(P[np.arange(len(y)), y.astype(int)])))


def _labels(p, task):
    p = np.asarray(p)
    if task == "binary":
        return (p >= 0.5).astype(int)
    return p.argmax(axis=1)


def _f1_bin(y, p):
    yl = _labels(p, "binary")
    tp = np.sum((yl == 1) & (y == 1))
    fp = np.sum((yl == 1) & (y == 0))
    fn = np.sum((yl == 0) & (y == 1))
    return float(2 * tp / max(2 * tp + fp + fn, 1))


def _f1_macro(y, P):
    from sklearn.metrics import f1_score
    return float(f1_score(y.astype(int), _labels(P, "multiclass"), average="macro"))


def _f1_weighted(y, P):
    from sklearn.metrics import f1_score
    return float(f1_score(y.astype(int), _labels(P, "multiclass"), average="weighted"))


def _ap(y, p):
    from sklearn.metrics import average_precision_score
    return float(average_precision_score(y, p))


def _macro_auc(y, P):
    P = np.asarray(P, float)
    aucs = [auc_score(y == k, P[:, k]) for k in range(P.shape[1]) if 0 < np.sum(y == k) < len(y)]
    return float(np.mean(aucs)) if aucs else float("nan")


def _qwk(y, P):
    from sklearn.metrics import cohen_kappa_score
    P = np.asarray(P)
    pred = _labels(P, "multiclass") if P.ndim == 2 else np.rint(P).astype(int)
    return float(cohen_kappa_score(y.astype(int), pred, weights="quadratic"))


def _rmse(y, p):
    return float(np.sqrt(np.mean((y - p) ** 2)))


def _rmsle(y, p):
    return float(np.sqrt(np.mean((np.log1p(np.clip(p, 0, None)) - np.log1p(np.clip(y, 0, None))) ** 2)))


def _mape(y, p):
    m = y != 0
    return float(np.mean(np.abs((y[m] - p[m]) / y[m]))) if m.any() else float("nan")


def _smape(y, p):
    d = np.abs(y) + np.abs(p)
    m = d != 0
    return float(np.mean(2 * np.abs(y[m] - p[m]) / d[m])) if m.any() else 0.0


def _r2(y, p):
    sst = np.sum((y - y.mean()) ** 2)
    return float(1 - np.sum((y - p) ** 2) / sst) if sst > 0 else float("nan")


METRICS: dict[str, Metric] = {m.key: m for m in [
    Metric("auc", "ROC AUC", ("binary",), True, "proba", lambda y, p: auc_score(y, p)),
    Metric("logloss", "Log Loss", ("binary",), False, "proba", _logloss_bin),
    Metric("accuracy", "Accuracy", ("binary",), True, "label",
           lambda y, p: float(np.mean(_labels(p, "binary") == y)), "0.5 기준으로 라벨을 정합니다"),
    Metric("f1", "F1", ("binary",), True, "label", _f1_bin, "0.5 기준으로 라벨을 정합니다"),
    Metric("ap", "PR AUC (AP)", ("binary",), True, "proba", _ap),
    Metric("mlogloss", "Log Loss", ("multiclass",), False, "proba", _logloss_multi),
    Metric("macc", "Accuracy", ("multiclass",), True, "label",
           lambda y, P: float(np.mean(_labels(P, "multiclass") == y))),
    Metric("macro_f1", "Macro F1", ("multiclass",), True, "label", _f1_macro),
    Metric("weighted_f1", "Weighted F1", ("multiclass",), True, "label", _f1_weighted),
    Metric("macro_auc", "Macro AUC (OvR)", ("multiclass",), True, "proba", _macro_auc),
    Metric("qwk", "Quadratic Weighted Kappa", ("multiclass",), True, "label", _qwk, "순서가 있는 클래스용"),
    Metric("rmse", "RMSE", ("regression",), False, "value", _rmse),
    Metric("mae", "MAE", ("regression",), False, "value", lambda y, p: float(np.mean(np.abs(y - p)))),
    Metric("rmsle", "RMSLE", ("regression",), False, "value", _rmsle, "음수 예측은 0으로 자릅니다"),
    Metric("mape", "MAPE", ("regression",), False, "value", _mape, "정답이 0인 행은 뺍니다"),
    Metric("smape", "SMAPE", ("regression",), False, "value", _smape),
    Metric("r2", "R²", ("regression",), True, "value", _r2),
]}

DEFAULT_METRIC = {"binary": "auc", "multiclass": "mlogloss", "regression": "rmse"}


def default_metric(task: str, sample=None, target: str | None = None, submission_format: str = "value") -> str:
    """제출 파일이 라벨을 받는지 확률을 받는지 보고 기본 지표를 고른다. (대회 안내와 다르면 사용자가 바꾼다)"""
    import pandas as pd
    if task == "binary" and sample is not None and target in getattr(sample, "columns", []):
        return "auc" if pd.api.types.is_float_dtype(sample[target]) else "accuracy"
    if task == "multiclass":
        if submission_format == "proba_columns":
            return "mlogloss"
        if sample is not None and target in getattr(sample, "columns", []):
            return "macro_f1"
    return DEFAULT_METRIC.get(task, "rmse")


def metrics_for(task: str) -> list[dict]:
    return [{"key": m.key, "label": m.label, "higher_is_better": m.higher_is_better, "needs": m.needs,
             "note": m.note} for m in METRICS.values() if task in m.tasks]


def score(metric: str, y: np.ndarray, pred: np.ndarray) -> float:
    m = METRICS[metric]
    y = np.asarray(y)
    pred = np.asarray(pred)
    if m.tasks[0] != "multiclass":
        y = y.astype(float)
    return m.fn(y, pred)


def better(metric: str, a: float, b: float) -> bool:
    """a가 b보다 좋은가"""
    return a > b if METRICS[metric].higher_is_better else a < b
