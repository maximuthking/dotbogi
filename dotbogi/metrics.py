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


def _brier(y, p):
    return float(np.mean((np.asarray(p, float) - y) ** 2))


def _ece(y, p, n_bins: int = 10):
    """Expected Calibration Error: 확률 구간별 |평균 예측 - 실제 비율|의 가중 평균."""
    p = np.clip(np.asarray(p, float), 0, 1)
    bins = np.minimum((p * n_bins).astype(int), n_bins - 1)
    total = 0.0
    for b in range(n_bins):
        m = bins == b
        if m.any():
            total += m.mean() * abs(y[m].mean() - p[m].mean())
    return float(total)


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
    Metric("brier", "Brier Score", ("binary",), False, "proba", _brier),
    Metric("ece", "ECE (보정 오차)", ("binary",), False, "proba", _ece, "확률 10구간 기준"),
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


CUSTOM_KEY = "custom"


def register_custom(path: str, task: str, higher_is_better: bool = True, needs: str = "proba",
                    label: str | None = None) -> Metric:
    """대회 전용 평가식(파이썬 파일의 score(y_true, y_pred) 함수)을 'custom' 지표로 등록한다.
    y_true: 이진 0/1, 다중 0..K-1 코드, 회귀 값. y_pred: 이진 양성 확률, 다중 (행, K) 확률, 회귀 값."""
    import importlib.util
    from pathlib import Path
    pth = Path(path)
    if not pth.is_file():
        raise ValueError(f"지표 파일이 없습니다: {path}")
    if pth.suffix.lower() != ".py":
        raise ValueError("파이썬(.py) 파일만 등록할 수 있습니다.")
    spec = importlib.util.spec_from_file_location(f"dotbogi_custom_metric_{abs(hash(str(pth)))}", pth)
    if spec is None or spec.loader is None:
        raise ValueError("지표 파일을 불러오지 못했습니다.")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        raise ValueError(f"지표 파일을 실행하다 오류가 났습니다: {type(e).__name__}: {e}") from e
    fn = getattr(mod, "score", None)
    if not callable(fn):
        raise ValueError("지표 파일에 score(y_true, y_pred) 함수가 없습니다.")
    if needs not in ("proba", "label", "value"):
        needs = "value" if task == "regression" else "proba"
    # 등록하기 전에 작은 예시로 한 번 불러 본다 (항상 오류 나는 함수를 막기 위해)
    if task == "binary":
        ty, tp = np.array([0, 1, 0, 1, 1, 0], float), np.array([0.2, 0.7, 0.4, 0.9, 0.6, 0.3])
        if needs == "label":
            tp = (tp >= 0.5).astype(float)
    elif task == "multiclass":
        ty = np.array([0, 1, 2, 0, 1, 2])
        tp = np.array([[.7, .2, .1], [.2, .6, .2], [.1, .2, .7], [.5, .3, .2], [.3, .4, .3], [.2, .2, .6]])
        if needs == "label":
            tp = tp.argmax(axis=1)
    else:
        ty, tp = np.array([1.0, 2.0, 3.0, 4.0]), np.array([1.1, 1.9, 3.2, 3.7])
    try:
        trial = float(fn(ty, tp))
    except Exception as e:
        raise ValueError(f"score 함수를 예시 데이터로 불러 봤더니 오류가 났습니다: {type(e).__name__}: {e}") from e
    if not np.isfinite(trial):
        raise ValueError("score 함수가 예시 데이터에서 숫자가 아닌 값(NaN·무한대)을 돌려줬습니다.")
    m = Metric(CUSTOM_KEY, label or getattr(mod, "NAME", None) or f"사용자 지표 ({pth.name})", (task,),
               bool(getattr(mod, "HIGHER_IS_BETTER", higher_is_better)), needs,
               lambda y, p: float(fn(y, p)), f"{pth.name}의 score 함수")
    METRICS[CUSTOM_KEY] = m
    return m


def unregister_custom() -> None:
    METRICS.pop(CUSTOM_KEY, None)


def metrics_for(task: str) -> list[dict]:
    return [{"key": m.key, "label": m.label, "higher_is_better": m.higher_is_better, "needs": m.needs,
             "note": m.note} for m in METRICS.values() if task in m.tasks]


def score(metric: str, y: np.ndarray, pred: np.ndarray) -> float:
    """y가 (행, 타깃) 2차원이면 다중 타깃: 타깃별 점수의 평균 (사용자 지표는 표 전체를 그대로 넘긴다)."""
    m = METRICS[metric]
    y = np.asarray(y)
    pred = np.asarray(pred)
    if y.ndim == 2 and m.tasks[0] != "multiclass" and metric != CUSTOM_KEY:
        if pred.shape != y.shape:
            raise ValueError(f"예측 모양 {pred.shape}이 정답 모양 {y.shape}과 다릅니다.")
        return float(np.mean([score(metric, y[:, j], pred[:, j]) for j in range(y.shape[1])]))
    if m.tasks[0] != "multiclass":
        y = y.astype(float)
    return m.fn(y, pred)


def better(metric: str, a: float, b: float) -> bool:
    """a가 b보다 좋은가"""
    return a > b if METRICS[metric].higher_is_better else a < b
