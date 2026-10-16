"""OOF 기반 앙상블: 상관 행렬, 힐클라이밍(Caruana) 가중치, 폴드 교차로 잰 정직한 앙상블 점수."""
from __future__ import annotations

import numpy as np
from scipy.stats import rankdata

from . import metrics as M


def _to_rank(p: np.ndarray) -> np.ndarray:
    if p.ndim == 1:
        return rankdata(p) / len(p)
    return np.column_stack([rankdata(p[:, k]) / len(p) for k in range(p.shape[1])])


def correlation(preds: dict[str, np.ndarray]) -> dict:
    names = list(preds)
    flat = [np.asarray(preds[n], float).reshape(len(preds[n]), -1).ravel() for n in names]
    m = np.corrcoef(np.vstack(flat)) if len(names) > 1 else np.ones((1, 1))
    return {"names": names, "matrix": np.nan_to_num(m, nan=0.0).tolist()}


def _blend(preds: list[np.ndarray], w: np.ndarray) -> np.ndarray:
    out = np.zeros_like(preds[0], dtype="float64")
    for p, wi in zip(preds, w):
        if wi:
            out += wi * p
    return out / max(w.sum(), 1e-12)


def hill_climb(preds: list[np.ndarray], y: np.ndarray, metric: str, max_iter: int = 60,
               tol: float = 1e-7) -> tuple[np.ndarray, list[float]]:
    """가장 좋은 단일 모델에서 시작해, 점수를 가장 올리는 모델을 하나씩(중복 허용) 더한다."""
    hib = M.METRICS[metric].higher_is_better
    sign = 1.0 if hib else -1.0
    single = [sign * M.score(metric, y, p) for p in preds]
    counts = np.zeros(len(preds))
    best_i = int(np.argmax(single))
    counts[best_i] = 1
    cur = preds[best_i].astype("float64").copy()
    cur_score = single[best_i]
    history = [sign * cur_score]
    total = 1
    for _ in range(max_iter):
        cand_scores = []
        for i, p in enumerate(preds):
            cand = (cur * total + p) / (total + 1)
            cand_scores.append(sign * M.score(metric, y, cand))
        i = int(np.argmax(cand_scores))
        if cand_scores[i] <= cur_score + tol:
            break
        cur = (cur * total + preds[i]) / (total + 1)
        total += 1
        counts[i] += 1
        cur_score = cand_scores[i]
        history.append(sign * cur_score)
    return counts / counts.sum(), history


def run_ensemble(names: list[str], oofs: list[np.ndarray], y: np.ndarray, metric: str,
                 fold: np.ndarray | None = None, method: str = "hill", use_rank: bool = False,
                 max_rows: int = 200_000, seed: int = 0) -> dict:
    """oofs: 같은 행 순서의 OOF 예측들 (결측 행은 미리 빼서 넘긴다)."""
    if len(oofs) < 2:
        raise ValueError("앙상블하려면 OOF가 있는 실험을 2개 이상 고르세요.")
    preds = [_to_rank(np.asarray(p, float)) if use_rank else np.asarray(p, float) for p in oofs]
    singles = [{"name": n, "score": M.score(metric, y, p)} for n, p in zip(names, oofs)]

    def fit(idx):
        if method == "mean":
            return np.ones(len(preds)) / len(preds), []
        sub = idx
        if len(sub) > max_rows:
            sub = np.random.default_rng(seed).choice(sub, max_rows, replace=False)
        return hill_climb([p[sub] for p in preds], y[sub], metric)

    all_idx = np.arange(len(y))
    w, history = fit(all_idx)
    blend = _blend(preds, w)
    score_all = M.score(metric, y, blend)

    honest = None
    if fold is not None and method != "mean":
        ks = sorted(k for k in set(fold.tolist()) if k >= 0)
        if len(ks) >= 2:
            fold_scores, oof_blend = [], np.zeros_like(blend)
            for k in ks:
                tr, va = np.flatnonzero(fold != k), np.flatnonzero(fold == k)
                wk, _ = fit(tr)
                oof_blend[va] = _blend([p[va] for p in preds], wk)
                fold_scores.append(M.score(metric, y[va], oof_blend[va]))
            used = np.isin(fold, ks)
            honest = {"score": M.score(metric, y[used], oof_blend[used]), "fold_scores": fold_scores}

    best_single = max(singles, key=lambda s: s["score"] if M.METRICS[metric].higher_is_better else -s["score"])
    gain = score_all - best_single["score"]
    return {
        "weights": [{"name": n, "weight": float(wi)} for n, wi in zip(names, w)],
        "score": score_all, "history": history, "honest": honest, "singles": singles,
        "best_single": best_single, "gain": gain if M.METRICS[metric].higher_is_better else -gain,
        "use_rank": use_rank, "method": method, "correlation": correlation(dict(zip(names, oofs))),
        "_weights": w,
    }


def blend_test(tests: list[np.ndarray], w: np.ndarray, use_rank: bool = False) -> np.ndarray:
    preds = [_to_rank(np.asarray(p, float)) if use_rank else np.asarray(p, float) for p in tests]
    return _blend(preds, np.asarray(w, float))
