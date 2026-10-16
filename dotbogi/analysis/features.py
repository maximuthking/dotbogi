"""모델용 숫자 행렬 만들기 (적대적 검증·기본 모델 공용). train/test를 같은 규칙으로 인코딩한다."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from ..schema import to_datetime_safe
from ..utils import to_float

HIGH_CARD = 200  # 이보다 고유값이 많은 범주형은 빈도 인코딩


@dataclass
class Matrix:
    train: pd.DataFrame
    test: pd.DataFrame | None
    features: list[str]
    categorical: list[str] = field(default_factory=list)
    encodings: dict = field(default_factory=dict)   # 컬럼 → 어떻게 바꿨는지 (화면 표시용)
    skipped: dict = field(default_factory=dict)     # 컬럼 → 왜 뺐는지


def build_matrix(train: pd.DataFrame, test: pd.DataFrame | None, columns: list,
                 exclude: set[str] | None = None) -> Matrix:
    """columns: schema.ColumnInfo 목록. exclude: 타깃·ID 등 빼야 할 컬럼."""
    exclude = set(exclude or [])
    tr_out, te_out = {}, {}
    feats, cats, enc, skipped = [], [], {}, {}
    for ci in columns:
        c = ci.name
        if c in exclude:
            continue
        if not ci.in_train or (test is not None and not ci.in_test):
            skipped[c] = "train과 test 중 한쪽에만 있음"
            continue
        if ci.kind == "id":
            skipped[c] = "ID 컬럼"
            continue
        if ci.kind == "constant":
            skipped[c] = "값이 하나뿐"
            continue
        a = train[c]
        b = test[c] if test is not None else None
        if ci.kind == "numeric":
            tr_out[c] = to_float(a)
            if b is not None:
                te_out[c] = to_float(b)
            enc[c] = "숫자 그대로"
        elif ci.kind == "datetime":
            tr_out[c] = to_float(to_datetime_safe(a))  # 1970년 기준 일 수
            if b is not None:
                te_out[c] = to_float(to_datetime_safe(b))
            enc[c] = "날짜 → 일 단위 숫자"
        elif ci.kind == "text":
            tr_out[c] = a.astype("string").str.len().astype("float64").to_numpy()
            if b is not None:
                te_out[c] = b.astype("string").str.len().astype("float64").to_numpy()
            enc[c] = "문장 길이"
        else:  # categorical, binary
            both = pd.concat([a, b], ignore_index=True) if b is not None else a.reset_index(drop=True)
            both = both.astype("string") if not pd.api.types.is_numeric_dtype(both) else both
            n_unique = both.nunique(dropna=True)
            if n_unique > HIGH_CARD:
                freq = both.map(both.value_counts(dropna=True)).astype("float64").to_numpy()
                tr_out[c] = freq[: len(a)]
                if b is not None:
                    te_out[c] = freq[len(a):]
                enc[c] = f"빈도 인코딩 (고유값 {n_unique:,}개)"
            else:
                codes, _ = pd.factorize(both, use_na_sentinel=True)
                codes = codes.astype("float64")
                codes[codes < 0] = np.nan
                tr_out[c] = codes[: len(a)]
                if b is not None:
                    te_out[c] = codes[len(a):]
                cats.append(c)
                enc[c] = "범주 코드"
        feats.append(c)
    tr_df = pd.DataFrame(tr_out, columns=feats)
    te_df = pd.DataFrame(te_out, columns=feats) if test is not None else None
    return Matrix(tr_df, te_df, feats, cats, enc, skipped)
