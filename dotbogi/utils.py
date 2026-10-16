"""여러 모듈이 같이 쓰는 작은 도구들."""
from __future__ import annotations

import datetime as _dt
import math

import numpy as np
import pandas as pd


def jsonable(obj):
    """NaN/inf → None, numpy/pandas 값 → 파이썬 기본형. 브라우저로 보내기 전에 통과시킨다."""
    if obj is None or isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, (int,)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [jsonable(v) for v in obj.tolist()]
    if isinstance(obj, (pd.Timestamp, _dt.datetime, _dt.date)):
        return None if pd.isna(obj) else obj.isoformat()
    if isinstance(obj, pd.Timedelta):
        return str(obj)
    if obj is pd.NA or obj is pd.NaT:
        return None
    if hasattr(obj, "to_dict"):
        return jsonable(obj.to_dict())
    try:
        if pd.isna(obj):
            return None
    except (TypeError, ValueError):
        pass
    return str(obj)


def to_float(s: pd.Series) -> np.ndarray:
    """숫자/불리언/날짜 컬럼을 float64 배열로 (결측은 NaN, 날짜는 1970-01-01 기준 일 수)."""
    if pd.api.types.is_bool_dtype(s):
        return s.astype("float64").to_numpy()
    if pd.api.types.is_datetime64_any_dtype(s):
        # 날짜는 1970-01-01 기준 '일' 수 (pandas 버전마다 다른 내부 단위에 영향받지 않게)
        d = s.dt.tz_localize(None) if getattr(s.dt, "tz", None) is not None else s
        return ((d - pd.Timestamp("1970-01-01")) / pd.Timedelta(days=1)).to_numpy(
            dtype="float64", na_value=np.nan)
    return pd.to_numeric(s, errors="coerce").to_numpy(dtype="float64", na_value=np.nan)


def as_label(v) -> str:
    """카테고리 값을 화면용 문자열로."""
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "(결측)"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def sample_index(n: int, k: int, seed: int = 0) -> np.ndarray:
    if n <= k:
        return np.arange(n)
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(n, size=k, replace=False))


def fmt_num(x: float | None, digits: int = 4) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "-"
    if abs(x) >= 1e6 or (abs(x) < 1e-3 and x != 0):
        return f"{x:.3e}"
    return f"{x:.{digits}g}"
