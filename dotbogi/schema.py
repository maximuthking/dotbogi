"""컬럼 종류 추론과 대회 구조(타깃·ID·과제 유형) 추측."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

KINDS = ("numeric", "categorical", "binary", "datetime", "text", "id", "constant")

_ID_NAME = re.compile(r"(^|[_\-\s])(id|idx|index|key|uid|uuid|no)$|^id[_\-\s]", re.I)
_TARGET_NAME = re.compile(r"^(target|label|labels|y|class|outcome|answer|result|정답|타깃|타겟)$", re.I)
_DATE_LIKE = re.compile(
    r"^\s*(\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}|\d{8}(\d{6})?)"
    r"([ T]\d{1,2}:\d{2}(:\d{2}(\.\d+)?)?)?\s*$"
)


@dataclass
class ColumnInfo:
    name: str
    kind: str
    dtype: str
    n_unique: int
    discrete: bool = False
    in_train: bool = True
    in_test: bool = True
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompetitionGuess:
    target: list[str] = field(default_factory=list)
    id_col: str | None = None
    task: str = "regression"          # binary | multiclass | regression
    submission_format: str = "value"  # value | proba_columns
    classes: list = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def is_id_name(name: str) -> bool:
    return bool(_ID_NAME.search(name.strip()))


def is_numeric(s: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)


def is_texty(s: pd.Series) -> bool:
    return (pd.api.types.is_string_dtype(s) or pd.api.types.is_object_dtype(s)
            or isinstance(s.dtype, pd.CategoricalDtype))


def integer_valued(s: pd.Series) -> bool:
    if pd.api.types.is_integer_dtype(s):
        return True
    if not is_numeric(s):
        return False
    v = s.to_numpy(dtype="float64", na_value=np.nan)
    v = v[np.isfinite(v)]
    if v.size == 0:
        return False
    v = v[:200_000]
    return bool(np.all(np.equal(np.mod(v, 1), 0)))


def looks_datetime(s: pd.Series) -> bool:
    """문자열 컬럼이 날짜인지: 형식이 날짜처럼 생겼고 실제로 파싱되는 비율이 높을 때만."""
    sample = s.dropna()
    if sample.empty:
        return False
    sample = sample.sample(min(len(sample), 400), random_state=0).astype(str)
    shape_ok = sample.str.match(_DATE_LIKE).mean()
    if shape_ok < 0.95:
        return False
    parsed = to_datetime_safe(sample)
    return parsed.notna().mean() >= 0.95


def to_datetime_safe(s: pd.Series) -> pd.Series:
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    st = s.astype("string")
    eight = st.str.fullmatch(r"\d{8}")
    if eight.fillna(False).astype(bool).mean() > 0.9:
        return pd.to_datetime(st, format="%Y%m%d", errors="coerce")
    try:
        return pd.to_datetime(st, errors="coerce", format="mixed")
    except (TypeError, ValueError):
        return pd.to_datetime(st, errors="coerce")


def infer_kind(s: pd.Series, name: str | None = None) -> tuple[str, bool, str]:
    """(종류, 이산형 숫자 여부, 메모)를 돌려준다."""
    name = name if name is not None else str(s.name)
    nonnull = s.dropna()
    n = len(nonnull)
    if n == 0:
        return "constant", False, "값이 전부 비어 있음"
    nunique = int(nonnull.nunique())
    if nunique <= 1:
        return "constant", False, "값이 하나뿐"
    uniq_ratio = nunique / n

    if pd.api.types.is_bool_dtype(s):
        return "binary", False, ""
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime", False, ""

    if is_numeric(s):
        if nunique == 2:
            return "binary", True, ""
        integer = integer_valued(nonnull)
        if integer and uniq_ratio > 0.98 and is_id_name(name):
            return "id", False, "이름과 고유값 비율로 ID로 판단"
        if integer and uniq_ratio > 0.999 and n > 50:
            v = nonnull.to_numpy()
            d = np.diff(np.sort(v.astype("int64")))
            if d.size and (d == 1).mean() > 0.98:
                return "id", False, "1씩 증가하는 고유 정수라 행 번호로 판단"
        return "numeric", bool(integer and nunique <= 25), ""

    if is_texty(s):
        if looks_datetime(nonnull):
            return "datetime", False, "날짜 형식 문자열"
        sample = nonnull.sample(min(n, 2000), random_state=0).astype(str)
        avg_len = float(sample.str.len().mean())
        avg_words = float(sample.str.count(r"\s+").mean()) + 1
        hangul = float(sample.str.count(r"[가-힣]").sum() / max(sample.str.len().sum(), 1))
        if nunique == 2:
            return "binary", False, ""
        # 문장: 대부분 다르고 여러 단어. 한글은 글자 수가 적어도 문장일 수 있어 기준을 따로 둔다.
        if uniq_ratio > 0.5 and ((avg_len >= 25 and avg_words >= 4) or (hangul > 0.3 and avg_len >= 8 and avg_words >= 2.5)):
            return "text", False, "길고 대부분 다른 문장"
        digits_only = sample.str.strip().str.fullmatch(r"\d+").mean()
        numeric_like = pd.to_numeric(sample.str.replace(",", "", regex=False).str.strip(), errors="coerce").notna().mean()
        if uniq_ratio > 0.98 and digits_only > 0.98:
            return "id", False, "숫자 코드 문자열(앞자리 0 등)이라 ID로 판단"
        if numeric_like >= 0.9:
            return "categorical", False, "숫자로 읽히는 문자 (숫자로 바꿀지 확인)"
        if uniq_ratio > 0.98 and (is_id_name(name) or (avg_words < 1.5 and n > 50)):
            return "id", False, "거의 모든 값이 달라 ID로 판단"
        return "categorical", False, "고유값이 많음" if nunique > 50 else ""

    return "categorical", False, ""


def infer_columns(train: pd.DataFrame, test: pd.DataFrame | None = None) -> list[ColumnInfo]:
    cols: list[ColumnInfo] = []
    test_cols = set(test.columns) if test is not None else set()
    extra = [c for c in (test.columns if test is not None else []) if c not in train.columns]
    for c in list(train.columns) + extra:
        parts = []
        if c in train.columns:
            parts.append(train[c])
        if test is not None and c in test_cols:
            parts.append(test[c])
        # 종류는 train+test를 합쳐서 본다 (dtype이 다르면 문자열로 맞춘다).
        if len(parts) == 2 and parts[0].dtype != parts[1].dtype and not (
                is_numeric(parts[0]) and is_numeric(parts[1])):
            parts = [p.astype("string") for p in parts]
        both = pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]
        kind, discrete, note = infer_kind(both, c)
        cols.append(ColumnInfo(
            name=c, kind=kind, dtype=str(parts[0].dtype), n_unique=int(both.nunique(dropna=True)),
            discrete=discrete, in_train=c in train.columns, in_test=c in test_cols, note=note,
        ))
    return cols


def guess_competition(train: pd.DataFrame, test: pd.DataFrame | None,
                      sample_sub: pd.DataFrame | None,
                      columns: list[ColumnInfo]) -> CompetitionGuess:
    g = CompetitionGuess()
    kinds = {c.name: c for c in columns}
    test_cols = set(test.columns) if test is not None else set()

    # ID: 제출 파일과 test에 둘 다 있고 고유한 컬럼
    if sample_sub is not None and test is not None:
        for c in sample_sub.columns:
            if c in test_cols and test[c].is_unique:
                g.id_col = c
                g.reasons.append(f"'{c}'는 sample_submission과 test에 모두 있고 값이 고유해서 ID로 봤습니다.")
                break
    if g.id_col is None:
        for c in train.columns:
            info = kinds.get(c)
            if info and info.kind == "id" and (test is None or c in test_cols):
                g.id_col = c
                g.reasons.append(f"'{c}'는 고유값 컬럼이라 ID로 봤습니다.")
                break

    # 타깃: train에만 있는 컬럼, 제출 파일에 있는 것을 우선
    only_train = [c for c in train.columns if test is not None and c not in test_cols and c != g.id_col]
    sub_cols = [c for c in (sample_sub.columns if sample_sub is not None else []) if c != g.id_col]
    proba_classes: list = []
    if sub_cols:
        direct = [c for c in sub_cols if c in train.columns]
        if direct:
            g.target = direct
            g.reasons.append(f"sample_submission의 예측 컬럼 {direct}이(가) train에도 있어 타깃으로 봤습니다.")
        elif len(only_train) >= 1 and len(sub_cols) > 1:
            # 클래스별 확률 컬럼 형식 (예: 제출 컬럼이 클래스 이름, 또는 'Status_C'처럼 접두사가 붙음)
            for t in only_train:
                matched = match_proba_columns(sub_cols, list(train[t].dropna().unique()))
                if matched is not None:
                    g.target = [t]
                    g.submission_format = "proba_columns"
                    proba_classes = matched
                    g.reasons.append(
                        f"제출 파일이 클래스별 확률 컬럼 {len(sub_cols)}개라서 '{t}'의 다중분류로 봤습니다.")
                    break
    if not g.target and only_train:
        named = [c for c in only_train if _TARGET_NAME.match(c)]
        pick = named[0] if named else only_train[-1]
        g.target = [pick]
        g.reasons.append(f"'{pick}'는 train에만 있는 컬럼이라 타깃으로 봤습니다.")
    if not g.target and test is None:
        named = [c for c in train.columns if _TARGET_NAME.match(c)]
        if named:
            g.target = [named[0]]
            g.reasons.append(f"이름이 '{named[0]}'라서 타깃으로 봤습니다.")

    # 과제 유형
    if g.target:
        t = g.target[0]
        y = train[t].dropna()
        k = kinds[t].kind if t in kinds else infer_kind(y, t)[0]
        nunq = int(y.nunique())
        if nunq <= 1:
            g.task = "binary"
            g.classes = [plain(v) for v in y.unique()]
            g.reasons.append(f"타깃 '{t}'의 값이 하나뿐입니다. 이대로는 모델을 학습할 수 없으니 타깃 컬럼이 맞는지 확인하세요.")
            return g
        if g.submission_format == "proba_columns":
            g.task = "multiclass"
        elif k == "binary":
            g.task = "binary"
        elif k == "categorical" or (k == "numeric" and integer_valued(y) and nunq <= 10
                                    and not _is_float_sub(sample_sub, t)):
            g.task = "multiclass"
        else:
            g.task = "regression"
        if g.task in ("binary", "multiclass"):
            g.classes = proba_classes or sorted(map(plain, y.unique()), key=lambda v: (str(type(v)), v))
        g.reasons.append({"binary": "타깃 값이 두 가지라 이진분류로 봤습니다.",
                          "multiclass": f"타깃 값이 {nunq}가지라 다중분류로 봤습니다.",
                          "regression": "타깃이 연속된 숫자라 회귀로 봤습니다."}[g.task])
    return g


def match_proba_columns(sub_cols: list, values: list) -> list | None:
    """제출 컬럼 이름을 타깃 값과 짝짓는다. 'C' ↔ 'C', 'Status_C' ↔ 'C', 'class_1' ↔ 1 처럼.
    모든 컬럼이 서로 다른 값과 짝지어지면 (제출 컬럼 순서의) 타깃 값 목록, 아니면 None."""
    if len(sub_cols) < 2 or len(values) > 500:
        return None
    norm = lambda x: str(plain(x)).strip().lower()
    by_norm = {}
    for v in values:
        by_norm.setdefault(norm(v), plain(v))

    def find(col):
        c = str(col).strip()
        cands = [c]
        for sep in ("_", "-", ".", " ", ":"):
            if sep in c:
                cands.append(c.split(sep, 1)[1])
                cands.append(c.rsplit(sep, 1)[1])
        for cand in cands:
            key = cand.strip().lower()
            if key in by_norm:
                return by_norm[key]
            try:  # '1.0' ↔ 1
                f = float(key)
                if f.is_integer() and str(int(f)) in by_norm:
                    return by_norm[str(int(f))]
            except ValueError:
                pass
        return None

    out = [find(c) for c in sub_cols]
    if any(v is None for v in out) or len({norm(v) for v in out}) != len(out):
        return None
    return out


def _is_float_sub(sample_sub: pd.DataFrame | None, t: str) -> bool:
    if sample_sub is None or t not in sample_sub.columns:
        return False
    s = sample_sub[t]
    return pd.api.types.is_float_dtype(s) and not integer_valued(s.dropna())


def plain(v):
    """numpy 스칼라를 JSON으로 보낼 수 있는 파이썬 값으로."""
    if isinstance(v, np.generic):
        return v.item()
    return v
