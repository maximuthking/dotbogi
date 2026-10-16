"""파일 불러오기: CSV 인코딩 자동 감지(utf-8/cp949), parquet/feather/xlsx, 파케이 캐시."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pandas as pd

TABLE_EXTS = {".csv", ".tsv", ".txt", ".parquet", ".pq", ".feather", ".xlsx", ".xls"}

_ENCODINGS = ("utf-8-sig", "cp949", "latin-1")


class LoadError(Exception):
    """사용자에게 그대로 보여줄 수 있는 불러오기 오류."""


def detect_encoding(path: str | os.PathLike, probe_bytes: int = 2_000_000) -> str:
    """앞부분을 읽어서 utf-8로 안 풀리면 cp949(한글 윈도우 엑셀 CSV), 그래도 안 되면 latin-1."""
    with open(path, "rb") as f:
        head = f.read(probe_bytes)
    # 잘린 멀티바이트 문자 때문에 오판하지 않도록 마지막 줄바꿈까지만 본다.
    cut = head.rfind(b"\n")
    if cut > 0 and len(head) == probe_bytes:
        head = head[:cut]
    for enc in _ENCODINGS:
        try:
            head.decode(enc)
            return "utf-8" if enc == "utf-8-sig" else enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def _sniff_sep(path: str | os.PathLike, encoding: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".tsv":
        return "\t"
    with open(path, "r", encoding=encoding, errors="replace") as f:
        first = f.readline()
    counts = {sep: first.count(sep) for sep in (",", "\t", ";", "|")}
    best = max(counts, key=counts.get)
    return best if counts[best] > 0 else ","


def file_signature(path: str | os.PathLike) -> str:
    st = os.stat(path)
    raw = f"{os.path.abspath(path)}|{st.st_size}|{st.st_mtime_ns}".encode()
    return hashlib.sha1(raw).hexdigest()[:16]


def read_table(path: str | os.PathLike, nrows: int | None = None,
               cache_dir: str | os.PathLike | None = None) -> pd.DataFrame:
    """표 파일 하나를 DataFrame으로. cache_dir가 있으면 큰 CSV를 parquet으로 캐시해 두 번째부터 빠르게."""
    path = Path(path)
    if not path.exists():
        raise LoadError(f"파일이 없습니다: {path}")
    ext = path.suffix.lower()
    if ext not in TABLE_EXTS:
        raise LoadError(f"지원하지 않는 형식입니다: {path.name} (csv, tsv, parquet, feather, xlsx 지원)")

    cache_path = None
    if cache_dir is not None and nrows is None and ext in {".csv", ".tsv", ".txt"} \
            and path.stat().st_size > 5_000_000:
        cache_path = Path(cache_dir) / f"{path.stem}-{file_signature(path)}.parquet"
        if cache_path.exists():
            try:
                return pd.read_parquet(cache_path)
            except Exception:  # 캐시가 깨졌으면 원본에서 다시 읽는다
                cache_path.unlink(missing_ok=True)

    try:
        if ext in {".parquet", ".pq"}:
            df = pd.read_parquet(path)
            if nrows is not None:
                df = df.head(nrows)
        elif ext == ".feather":
            df = pd.read_feather(path)
            if nrows is not None:
                df = df.head(nrows)
        elif ext in {".xlsx", ".xls"}:
            try:
                df = pd.read_excel(path, nrows=nrows)
            except ImportError as e:
                raise LoadError("엑셀 파일을 읽으려면 openpyxl이 필요합니다: pip install openpyxl") from e
        else:
            df = _read_csv(path, nrows)
    except LoadError:
        raise
    except MemoryError as e:
        raise LoadError(f"메모리가 부족해 {path.name}을(를) 다 읽지 못했습니다.") from e
    except Exception as e:
        raise LoadError(f"{path.name}을(를) 읽는 중 오류: {e}") from e

    df.columns = [str(c) for c in df.columns]
    _dedupe_columns(df)

    if cache_path is not None:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(cache_path, index=False)
        except Exception:
            pass  # 캐시는 있으면 좋은 것일 뿐
    return df


def _read_csv(path: Path, nrows: int | None) -> pd.DataFrame:
    enc = detect_encoding(path)
    sep = _sniff_sep(path, enc)
    if enc == "utf-8" and nrows is None and sep == ",":
        try:
            return pd.read_csv(path, engine="pyarrow")
        except Exception:
            pass  # pyarrow 엔진이 못 읽는 파일(따옴표 줄바꿈 등)은 기본 엔진으로
    return pd.read_csv(path, encoding=enc, sep=sep, nrows=nrows, low_memory=False,
                       encoding_errors="replace")


def _dedupe_columns(df: pd.DataFrame) -> None:
    seen: dict[str, int] = {}
    cols = []
    for c in df.columns:
        if c in seen:
            seen[c] += 1
            cols.append(f"{c}.{seen[c]}")
        else:
            seen[c] = 0
            cols.append(c)
    df.columns = cols
