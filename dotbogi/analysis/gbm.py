"""그래디언트 부스팅 모델 감싸기. LightGBM이 있으면 쓰고, 없으면 scikit-learn HistGradientBoosting."""
from __future__ import annotations

import os
import warnings

import numpy as np
import pandas as pd

try:  # LightGBM은 선택 의존성
    import lightgbm as lgb
    HAS_LGB = True
except Exception:  # pragma: no cover - 설치 안 된 환경
    lgb = None
    HAS_LGB = False

N_JOBS = max(1, (os.cpu_count() or 2) - 1)


def engine_name(prefer: str = "auto") -> str:
    if prefer == "sklearn" or not HAS_LGB:
        return "sklearn"
    return "lightgbm"


class GBM:
    """fit/predict/importance만 있는 얇은 래퍼. task: binary | multiclass | regression"""

    def __init__(self, task: str, n_classes: int = 2, engine: str = "auto", seed: int = 42,
                 n_estimators: int = 1000, learning_rate: float = 0.05, num_leaves: int = 31,
                 params: dict | None = None):
        self.task = task
        self.n_classes = n_classes
        self.engine = engine_name(engine)
        self.seed = seed
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.num_leaves = num_leaves
        self.params = params or {}
        self.model = None
        self.best_iteration = None
        self.features: list[str] = []

    def fit(self, X: pd.DataFrame, y: np.ndarray, X_val: pd.DataFrame | None = None,
            y_val: np.ndarray | None = None, categorical: list[str] | None = None,
            early_stopping: int = 50):
        categorical = [c for c in (categorical or []) if c in X.columns]
        self.features = list(X.columns)
        if self.engine == "lightgbm":
            return self._fit_lgb(X, y, X_val, y_val, categorical, early_stopping)
        return self._fit_sk(X, y, X_val, y_val, categorical, early_stopping)

    def _fit_lgb(self, X, y, X_val, y_val, categorical, early_stopping):
        params = dict(
            n_estimators=self.n_estimators, learning_rate=self.learning_rate,
            num_leaves=self.num_leaves, subsample=0.8, subsample_freq=1, colsample_bytree=0.8,
            min_child_samples=20, random_state=self.seed, n_jobs=N_JOBS, verbose=-1,
        )
        params.update(self.params)
        if self.task == "regression":
            model = lgb.LGBMRegressor(**params)
        else:
            model = lgb.LGBMClassifier(**params)
        Xc = _lgb_frame(X, categorical)
        fit_kw = {"categorical_feature": categorical or "auto"}
        callbacks = [lgb.log_evaluation(0)]
        if X_val is not None and y_val is not None and early_stopping:
            fit_kw["eval_set"] = [(_lgb_frame(X_val, categorical), y_val)]
            callbacks.append(lgb.early_stopping(early_stopping, verbose=False))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(Xc, y, callbacks=callbacks, **fit_kw)
        self.model = model
        self.best_iteration = int(model.best_iteration_ or params["n_estimators"])
        self._cats = categorical
        return self

    def _fit_sk(self, X, y, X_val, y_val, categorical, early_stopping):
        from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
        cat_mask = [c in categorical for c in X.columns]
        kw = dict(max_iter=self.n_estimators, learning_rate=self.learning_rate,
                  max_leaf_nodes=self.num_leaves, random_state=self.seed,
                  categorical_features=cat_mask if any(cat_mask) else None)
        # 검증 세트를 따로 줄 수 없어서 내부 10%로 조기 종료.
        # 단, 행이 아주 적은 클래스가 있으면 내부 층화 분할이 실패하므로 조기 종료 없이 반복 수를 줄인다.
        small_class = False
        if self.task != "regression":
            _, cnt = np.unique(np.asarray(y), return_counts=True)
            small_class = bool(cnt.min() < 10)
        if early_stopping and not small_class:
            kw.update(early_stopping=True, n_iter_no_change=early_stopping, validation_fraction=0.1)
        else:
            kw.update(early_stopping=False, max_iter=min(self.n_estimators, 200))
        if self.task == "regression":
            model = HistGradientBoostingRegressor(**kw)
        else:
            model = HistGradientBoostingClassifier(**kw)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model.fit(_sk_frame(X, categorical), y)
        self.model = model
        self.best_iteration = int(model.n_iter_)
        self._cats = categorical
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        """회귀: 값, 이진: 양성 확률, 다중: (n, K) 확률"""
        Xc = _lgb_frame(X, self._cats) if self.engine == "lightgbm" else _sk_frame(X, self._cats)
        if self.task == "regression":
            return np.asarray(self.model.predict(Xc), dtype="float64")
        proba = np.asarray(self.model.predict_proba(Xc), dtype="float64")
        if self.task == "binary":
            return proba[:, 1]
        if proba.shape[1] < self.n_classes:  # 학습 폴드에 없던 클래스가 있으면 0으로 채움
            full = np.zeros((proba.shape[0], self.n_classes))
            full[:, self.model.classes_.astype(int)] = proba
            proba = full
        return proba

    def importance(self) -> dict[str, float] | None:
        """LightGBM gain 중요도(합이 1이 되게). sklearn 엔진은 None (호출 측에서 순열 중요도)."""
        if self.engine != "lightgbm":
            return None
        gain = self.model.booster_.feature_importance(importance_type="gain")
        total = gain.sum() or 1.0
        return {f: float(g / total) for f, g in zip(self.features, gain)}


def _lgb_frame(X: pd.DataFrame, categorical: list[str]) -> pd.DataFrame:
    # 범주 코드는 float(NaN=결측) 그대로 두면 LightGBM이 결측으로 처리한다.
    return X


def _sk_frame(X: pd.DataFrame, categorical: list[str]) -> pd.DataFrame:
    return X


def permutation_importance(model: GBM, X: pd.DataFrame, y: np.ndarray, score_fn, n_rows: int = 20_000,
                           seed: int = 0) -> dict[str, float]:
    """중요도를 직접 안 주는 엔진용: 컬럼 하나씩 섞었을 때 점수가 얼마나 떨어지는지."""
    rng = np.random.default_rng(seed)
    if len(X) > n_rows:
        idx = rng.choice(len(X), n_rows, replace=False)
        X, y = X.iloc[idx].reset_index(drop=True), y[idx]
    base = score_fn(y, model.predict(X))
    drops = {}
    for c in X.columns:
        Xp = X.copy()
        Xp[c] = rng.permutation(Xp[c].to_numpy())
        drops[c] = max(0.0, base - score_fn(y, model.predict(Xp)))
    total = sum(drops.values()) or 1.0
    return {c: d / total for c, d in drops.items()}
