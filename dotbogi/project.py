"""대회 프로젝트: 폴더 하나 = 대회 하나. 설정과 실험 기록은 <폴더>/.dotbogi/ 에 저장한다."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

import numpy as np
import pandas as pd

from .io import TABLE_EXTS, LoadError, read_table
from .schema import ColumnInfo, CompetitionGuess, guess_competition, infer_columns

STORE = ".dotbogi"
_SKIP_DIRS = {STORE, ".git", ".venv", "venv", "node_modules", "__pycache__", ".ipynb_checkpoints",
              "catboost_info", "mlruns", "wandb"}

PLATFORMS = {
    "kaggle": {"label": "Kaggle", "final_picks": 2, "daily_limit": 5, "public_share": None},
    "dacon": {"label": "DACON", "final_picks": 2, "daily_limit": 3, "public_share": None},
    "other": {"label": "기타", "final_picks": 2, "daily_limit": None, "public_share": None},
}

DEFAULT_SETTINGS = {
    "version": 1,
    "name": "",
    "files": {"train": None, "test": None, "sample_submission": None},
    "target": [],
    "id_col": None,
    "task": None,
    "classes": [],
    "submission_format": "value",
    "metric": None,
    "custom_metric": None,          # {"path": "metric.py", "higher_is_better": true, "needs": "proba"}
    "kinds": {},                    # 사용자가 바꾼 컬럼 종류 {컬럼: 종류}
    "excluded": [],                 # 분석·모델에서 뺄 컬럼
    "cv": None,                     # {"strategy", "n_splits", "seed", "group_col", "time_col"}
    "competition": {"platform": "other", "public_share": None, "daily_limit": None, "final_picks": 2,
                    "end_date": None, "url": "", "rules_note": ""},
    "created_at": None,
}


def find_data_files(root: Path, max_depth: int = 3) -> dict:
    """폴더 안에서 train/test/sample_submission 후보를 찾는다. 이름이 정확할수록 우선."""
    found: list[Path] = []
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root):
        rel_depth = len(Path(dirpath).relative_to(root).parts)
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.startswith(".")]
        if rel_depth >= max_depth:
            dirnames[:] = []
        for f in filenames:
            if Path(f).suffix.lower() in TABLE_EXTS:
                found.append(Path(dirpath) / f)

    def pick(patterns):
        best, best_rank = None, None
        for p in found:
            stem = p.stem.lower()
            for rank, pat in enumerate(patterns):
                if re.fullmatch(pat, stem):
                    key = (rank, len(p.relative_to(root).parts), p.suffix.lower() not in (".parquet", ".csv"))
                    if best_rank is None or key < best_rank:
                        best, best_rank = p, key
                    break
        return best

    train = pick([r"train", r"train[_\-.]?(data|set|df)?", r"train.*"])
    test = pick([r"test", r"test[_\-.]?(data|set|df)?", r"test.*"])
    sample = pick([r"sample[_\-]?submission", r"sample[_\-]?sub.*", r".*submission.*", r"sample.*"])
    if sample is not None and sample in (train, test):
        sample = None
    return {
        "train": str(train) if train else None,
        "test": str(test) if test else None,
        "sample_submission": str(sample) if sample else None,
        "all": [str(p) for p in sorted(found)][:200],
    }


class Project:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise LoadError(f"폴더가 없습니다: {self.root}")
        self.dir = self.root / STORE
        self.lock = threading.RLock()
        self.settings = self._load_settings()
        self.train: pd.DataFrame | None = None
        self.test: pd.DataFrame | None = None
        self.sample: pd.DataFrame | None = None
        self.columns: list[ColumnInfo] = []
        self.guess: CompetitionGuess | None = None
        self.cache: dict = {}
        self.loaded_at: float | None = None

    # ─────────────────────────── 설정
    def _load_settings(self) -> dict:
        p = self.dir / "project.json"
        s = json.loads(json.dumps(DEFAULT_SETTINGS))
        if p.exists():
            try:
                saved = json.loads(p.read_text(encoding="utf-8"))
                _deep_update(s, saved)
            except (OSError, json.JSONDecodeError):
                pass
        if not s["name"]:
            s["name"] = self.root.name
        return s

    def save_settings(self) -> None:
        self.dir.mkdir(exist_ok=True)
        if not self.settings.get("created_at"):
            self.settings["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        tmp = self.dir / "project.json.tmp"
        tmp.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.dir / "project.json")

    @property
    def is_new(self) -> bool:
        return not (self.dir / "project.json").exists()

    def resolve(self, p: str | None) -> Path | None:
        if not p:
            return None
        pp = Path(p)
        return pp if pp.is_absolute() else self.root / pp

    def rel(self, p: str | os.PathLike | None) -> str | None:
        if not p:
            return None
        try:
            return str(Path(p).resolve().relative_to(self.root))
        except ValueError:
            return str(Path(p).resolve())

    # ─────────────────────────── 데이터
    def load(self, progress=None) -> None:
        """설정에 적힌 파일을 읽고 컬럼 종류·대회 구조를 추론한다. 처음이면 파일을 찾아서 채운다."""
        with self.lock:
            files = self.settings["files"]
            if not files.get("train"):
                found = find_data_files(self.root)
                for k in ("train", "test", "sample_submission"):
                    if found[k]:
                        files[k] = self.rel(found[k])
            if not files.get("train"):
                raise LoadError("train 파일을 찾지 못했습니다. 파일을 직접 골라 주세요.")
            cache_dir = self.dir / "cache"
            if progress:
                progress(0.1, "train 읽는 중")
            self.train = read_table(self.resolve(files["train"]), cache_dir=cache_dir)
            if progress:
                progress(0.5, "test 읽는 중")
            self.test = read_table(self.resolve(files["test"]), cache_dir=cache_dir) if files.get("test") else None
            self.sample = read_table(self.resolve(files["sample_submission"])) if files.get("sample_submission") else None
            if progress:
                progress(0.7, "컬럼 종류 추론 중")
            self.columns = infer_columns(self.train, self.test)
            for c in self.columns:  # 사용자가 바꾼 종류 적용
                if c.name in self.settings["kinds"]:
                    c.kind = self.settings["kinds"][c.name]
            self.guess = guess_competition(self.train, self.test, self.sample, self.columns)
            s = self.settings
            if not s["target"] or any(t not in self.train.columns for t in s["target"]):
                s["target"] = list(self.guess.target)
                s["task"] = self.guess.task
                s["classes"] = list(self.guess.classes)
                s["submission_format"] = self.guess.submission_format
                s["metric"] = None
            if s["id_col"] is None or (s["id_col"] not in self.train.columns
                                       and (self.test is None or s["id_col"] not in self.test.columns)):
                s["id_col"] = self.guess.id_col
            if not s["task"]:
                s["task"] = self.guess.task
            if not s["metric"]:
                from .metrics import default_metric
                s["metric"] = default_metric(s["task"] or "regression", self.sample, self.target_col(),
                                             s["submission_format"])
            self.cache.clear()
            self.loaded_at = time.time()
            self.save_settings()

    @property
    def loaded(self) -> bool:
        return self.train is not None

    def target_col(self) -> str | None:
        t = self.settings["target"]
        return t[0] if t else None

    def column(self, name: str) -> ColumnInfo | None:
        for c in self.columns:
            if c.name == name:
                return c
        return None

    def feature_columns(self) -> list[ColumnInfo]:
        skip = set(self.settings["target"]) | {self.settings["id_col"]} | set(self.settings["excluded"])
        return [c for c in self.columns if c.name not in skip]

    def encoded_target(self):
        """(y, mask, classes) 캐시"""
        if "y" not in self.cache:
            from .analysis.common import encode_target
            t = self.target_col()
            if t is None or t not in self.train.columns:
                self.cache["y"] = (None, None, [])
            else:
                task = self.settings["task"]
                classes = self.settings["classes"] if task != "regression" else []
                if self.settings["submission_format"] == "proba_columns":
                    classes = _align_proba_classes(self.train[t], classes)
                self.cache["y"] = encode_target(self.train[t], task, classes)
        return self.cache["y"]

    def invalidate(self, *keys: str) -> None:
        if not keys:
            self.cache.clear()
            return
        for k in list(self.cache):
            if any(k == key or k.startswith(key + ":") for key in keys):
                del self.cache[k]

    # ─────────────────────────── 폴드
    def folds_path(self) -> Path:
        return self.dir / "folds.csv"

    def save_folds(self, fold: np.ndarray) -> Path:
        self.dir.mkdir(exist_ok=True)
        id_col = self.settings["id_col"]
        df = pd.DataFrame({"row": np.arange(len(fold)), "fold": fold})
        if id_col and id_col in self.train.columns:
            df.insert(0, id_col, self.train[id_col].to_numpy())
        df.to_csv(self.folds_path(), index=False, encoding="utf-8")
        return self.folds_path()

    def load_folds(self) -> np.ndarray | None:
        p = self.folds_path()
        if not p.exists() or self.train is None:
            return None
        df = pd.read_csv(p)
        if len(df) != len(self.train):
            return None
        return df["fold"].to_numpy(dtype=np.int64)


def _align_proba_classes(y: pd.Series, sub_cols: list) -> list:
    """제출 컬럼 이름(문자열)과 타깃 값을 맞춘다. 순서는 제출 파일 컬럼 순서를 따른다."""
    values = {str(v): v for v in pd.unique(y.dropna())}
    out = []
    for c in sub_cols:
        out.append(values.get(str(c), c))
    return out


def _deep_update(base: dict, new: dict) -> None:
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
