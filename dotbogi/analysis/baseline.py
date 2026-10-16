"""기본 모델 빠른 교차검증: 고른 폴드로 GBM을 돌려 OOF·test 예측·폴드별 점수·중요도를 만든다."""
from __future__ import annotations

import time

import numpy as np

from .. import metrics as M
from .features import Matrix
from .gbm import GBM, permutation_importance


def run_baseline(mat: Matrix, y: np.ndarray, y_mask: np.ndarray, task: str, n_classes: int,
                 fold: np.ndarray, metric: str, strategy: str, engine: str = "auto", seed: int = 42,
                 n_estimators: int = 2000, learning_rate: float = 0.05, progress=None) -> dict:
    t0 = time.time()
    folds = sorted(k for k in set(fold.tolist()) if k >= 0)
    n = len(y)
    oof = np.full((n, n_classes) if task == "multiclass" else n, np.nan)
    test_preds, fold_scores, importances, iters = [], [], [], []
    X = mat.train
    yfit = y.astype(int) if task in ("binary", "multiclass") else y
    for i, k in enumerate(folds):
        if progress:
            progress(i / (len(folds) + 0.5), f"폴드 {i + 1}/{len(folds)} 학습 중")
        va = fold == k
        if strategy == "time":
            tr = (fold < k) & y_mask  # 앞선 기간 전부(첫 구간 -1 포함)로 학습
        else:
            tr = (fold != k) & (fold >= 0) & y_mask
        if tr.sum() == 0 or va.sum() == 0:
            continue
        m = GBM(task, n_classes=n_classes, engine=engine, seed=seed + k,
                n_estimators=n_estimators, learning_rate=learning_rate)
        m.fit(X[tr], yfit[tr], X[va], yfit[va], categorical=mat.categorical, early_stopping=100)
        p = m.predict(X[va])
        oof[va] = p
        fold_scores.append({"fold": int(k), "score": M.score(metric, y[va], p), "rows": int(va.sum()),
                            "train_rows": int(tr.sum()), "best_iteration": m.best_iteration})
        iters.append(m.best_iteration)
        imp = m.importance()
        if imp is None:
            sc = (lambda a, b: -M.score(metric, a, b)) if not M.METRICS[metric].higher_is_better \
                else (lambda a, b: M.score(metric, a, b))
            imp = permutation_importance(m, X[va], y[va], sc, n_rows=5000)
        importances.append(imp)
        if mat.test is not None:
            test_preds.append(m.predict(mat.test))

    if not fold_scores:
        raise ValueError("학습할 수 있는 폴드가 없습니다. 폴드 설정을 확인하세요.")
    used = fold >= 0
    if task == "multiclass":
        used &= ~np.isnan(oof).any(axis=1)
    else:
        used &= ~np.isnan(oof)
    cv = M.score(metric, y[used], oof[used])
    if test_preds:
        # 시간 검증은 가장 최근까지 학습한 마지막 폴드 모델, 나머지는 폴드 모델 평균
        test_pred = test_preds[-1] if strategy == "time" else np.mean(test_preds, axis=0)
    else:
        test_pred = None
    feats = mat.features
    imp_mean = {f: float(np.mean([d.get(f, 0.0) for d in importances])) for f in feats}
    scores = [f["score"] for f in fold_scores]
    return {
        "cv": cv, "cv_std": float(np.std(scores)), "fold_scores": fold_scores, "metric": metric,
        "engine": GBM(task, engine=engine).engine, "n_features": len(feats),
        "importance": sorted(({"name": f, "importance": imp_mean[f], "encoding": mat.encodings.get(f, "")}
                              for f in feats), key=lambda d: -d["importance"]),
        "seconds": time.time() - t0, "mean_best_iteration": float(np.mean(iters)) if iters else None,
        "_oof": oof, "_test": test_pred, "_used": used,
    }
