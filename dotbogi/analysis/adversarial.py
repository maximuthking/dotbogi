"""적대적 검증(adversarial validation): train과 test를 구분하는 모델을 만들어 두 데이터가 얼마나 다른지 잰다."""
from __future__ import annotations

import time

import numpy as np
import pandas as pd

from .common import auc_score, oof_power, quantile_codes
from .features import Matrix
from .gbm import GBM, permutation_importance


def interpret_auc(auc: float, top: list[str] | None = None) -> tuple[str, str]:
    names = ", ".join(f"'{t}'" for t in (top or [])[:3])
    who = f" 가장 크게 가르는 컬럼은 {names}입니다." if names else ""
    if auc < 0.55:
        return "same", "train과 test가 거의 구분되지 않습니다. 일반적인 무작위 K-Fold 검증 점수를 믿어도 됩니다."
    if auc < 0.65:
        return "slight", "약간 다릅니다." + who + " 그 컬럼의 분포 차이를 확인하고, 검증 점수와 리더보드 차이를 지켜보세요."
    if auc < 0.8:
        return "moderate", ("꽤 다릅니다." + who + " 그 컬럼을 빼거나 변환해 다시 실행해 보고, test와 비슷한 train 행으로 "
                            "검증 세트를 만드는 것도 고려하세요.")
    return "large", ("train과 test가 쉽게 구분됩니다." + who + " 날짜·ID·그룹 컬럼이 원인이면 데이터 점검의 시간·그룹 항목대로 "
                     "그 기준으로 검증하고, 일반 컬럼의 분포 차이가 원인이면 그 컬럼을 빼거나 변환해 보세요. "
                     "이 상태에서 무작위 K-Fold 점수는 리더보드보다 낙관적일 수 있습니다.")


def run_adversarial(mat: Matrix, n_folds: int = 5, max_rows_each: int = 100_000, seed: int = 42,
                    engine: str = "auto", progress=None) -> dict:
    """mat: train/test가 모두 있는 행렬. progress(fraction, message) 콜백 선택."""
    if mat.test is None or len(mat.test) == 0:
        raise ValueError("test 데이터가 있어야 적대적 검증을 할 수 있습니다.")
    if not mat.features:
        raise ValueError("비교할 컬럼이 없습니다.")
    t0 = time.time()
    rng = np.random.default_rng(seed)
    n_tr, n_te = len(mat.train), len(mat.test)
    tr_idx = np.sort(rng.choice(n_tr, min(n_tr, max_rows_each), replace=False))
    te_idx = np.sort(rng.choice(n_te, min(n_te, max_rows_each), replace=False))
    X = pd.concat([mat.train.iloc[tr_idx], mat.test.iloc[te_idx]], ignore_index=True)
    y = np.r_[np.zeros(len(tr_idx)), np.ones(len(te_idx))]
    fold = np.empty(len(y), dtype=int)
    for cls in (0, 1):  # 층화
        where = np.flatnonzero(y == cls)
        fold[where] = rng.permutation(len(where)) % n_folds

    oof = np.zeros(len(y))
    fold_aucs, importances, models = [], [], []
    for f in range(n_folds):
        if progress:
            progress(f / (n_folds + 1), f"구분 모델 학습 중 ({f + 1}/{n_folds})")
        tr, va = fold != f, fold == f
        m = GBM("binary", engine=engine, seed=seed + f, n_estimators=500, learning_rate=0.05)
        m.fit(X[tr], y[tr], X[va], y[va], categorical=mat.categorical, early_stopping=30)
        oof[va] = m.predict(X[va])
        fold_aucs.append(auc_score(y[va], oof[va]))
        imp = m.importance()
        if imp is None:
            imp = permutation_importance(m, X[va], y[va], lambda a, b: auc_score(a, b), n_rows=10_000)
        importances.append(imp)
        models.append(m)

    if progress:
        progress(n_folds / (n_folds + 1), "컬럼별 구분력 계산 중")
    auc = auc_score(y, oof)
    imp_mean = {c: float(np.mean([d.get(c, 0.0) for d in importances])) for c in mat.features}

    # 컬럼 하나만으로 train/test를 얼마나 구분하는지 (모델과 무관한 지표)
    single = {}
    for c in mat.features:
        v = X[c].to_numpy(dtype="float64")
        if c in mat.categorical:
            codes = np.where(np.isnan(v), -1, v).astype(np.int64)
            codes[codes < 0] = codes.max() + 1 if codes.size else 0
        else:
            codes = quantile_codes(v, 20)[0]
        single[c] = oof_power(codes, y, "binary", seed=seed)["value"]

    # 샘플에 안 들어간 train 행은 폴드 모델 평균으로 예측 (학습에 안 쓰였으니 공정한 값)
    p_train = np.empty(n_tr)
    p_train[tr_idx] = oof[: len(tr_idx)]
    rest = np.setdiff1d(np.arange(n_tr), tr_idx, assume_unique=True)
    if rest.size:
        if progress:
            progress(0.95, "나머지 train 행의 test 유사도 계산 중")
        chunk = 200_000
        for s in range(0, rest.size, chunk):
            part = rest[s:s + chunk]
            Xp = mat.train.iloc[part]
            p_train[part] = np.mean([m.predict(Xp) for m in models], axis=0)

    top_names = [c for c in sorted(mat.features, key=lambda c: -imp_mean[c]) if imp_mean[c] > 0.05][:3]
    level, advice = interpret_auc(auc, top_names)
    p_te = oof[len(tr_idx):]
    bins = np.linspace(0, 1, 41)
    feats = sorted(mat.features, key=lambda c: -imp_mean[c])
    return {
        "auc": auc, "auc_std": float(np.std(fold_aucs)), "fold_aucs": fold_aucs,
        "level": level, "advice": advice,
        "engine": models[0].engine, "n_train_used": int(len(tr_idx)), "n_test_used": int(len(te_idx)),
        "features": [{"name": c, "importance": imp_mean[c], "single_auc": single[c],
                      "encoding": mat.encodings.get(c, "")} for c in feats],
        "skipped": mat.skipped,
        "hist": {"edges": bins.tolist(),
                 "train": (np.histogram(p_train, bins)[0] / n_tr).tolist(),
                 "test": (np.histogram(p_te, bins)[0] / max(len(p_te), 1)).tolist()},
        # test 행 중앙값 이상으로 test스러운 train 행 비율: 차이가 없으면 약 50%, 클수록 0%에 가까움
        "test_like_share": float((p_train >= np.median(p_te)).mean()) if len(p_te) else None,
        "seconds": time.time() - t0,
        "_train_scores": p_train,  # 저장용 (화면에는 안 보냄)
    }
