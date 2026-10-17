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


TRAIN_PATTERNS = [r"train", r"train[_\-.]?(data|set|df)?", r"train.*"]
TEST_PATTERNS = [r"test", r"test[_\-.]?(data|set|df)?", r"test.*"]
SAMPLE_PATTERNS = [r"sample[_\-]?submission", r"sample[_\-]?sub.*", r"gender[_\-]?submission", r".*submission.*", r"sample.*"]


def _rank(stem: str, patterns: list[str]) -> int | None:
    for i, pat in enumerate(patterns):
        if re.fullmatch(pat, stem.lower()):
            return i
    return None


def find_data_files(root: Path, max_depth: int = 3) -> dict:
    """폴더 안에서 train/test/sample_submission 후보를 찾는다.
    - 이름이 정확할수록, 얕은 폴더일수록 우선
    - 가장 좋은 train 후보가 서로 다른 폴더에 여러 개면(대회 여러 개가 든 상위 폴더) 고르지 않고 후보를 돌려준다
    - test·제출 양식은 train과 같은 폴더(또는 가까운 폴더)에 있는 것을 우선
    - 제출 양식 후보가 여럿이면 'sample'이 든 이름 → 가장 먼저 만들어진 파일(대회에서 받은 원본) 순"""
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

    def depth(p: Path) -> int:
        return len(p.relative_to(root).parts)

    def ext_penalty(p: Path) -> int:
        return 0 if p.suffix.lower() in (".csv", ".parquet") else 1

    trains = [(r, depth(p), ext_penalty(p), str(p), p) for p in found if (r := _rank(p.stem, TRAIN_PATTERNS)) is not None]
    trains.sort()
    out = {"train": None, "test": None, "sample_submission": None, "sample_candidates": [], "ambiguous": [],
           "all": [str(p) for p in sorted(found)][:200]}
    if not trains:
        return out
    best_r, best_d = trains[0][0], trains[0][1]
    top = [t for t in trains if t[0] == best_r and t[1] == best_d]
    dirs = sorted({str(t[4].parent) for t in top})
    if len(dirs) > 1:
        out["ambiguous"] = dirs
        return out
    train = top[0][4]
    out["train"] = str(train)
    tdir = train.parent

    def closeness(p: Path) -> int:
        """train 폴더와 얼마나 가까운가 (같은 폴더 0, 부모·형제 1, 그 밖 2)"""
        if p.parent == tdir:
            return 0
        if p.parent == tdir.parent or p.parent.parent == tdir or p.parent.parent == tdir.parent:
            return 1
        return 2

    tests = [(closeness(p), r, ext_penalty(p), str(p), p) for p in found
             if p != train and (r := _rank(p.stem, TEST_PATTERNS)) is not None]
    tests.sort()
    test = tests[0][4] if tests else None
    out["test"] = str(test) if test else None
    samples = []
    for p in found:
        if p in (train, test):
            continue
        r = _rank(p.stem, SAMPLE_PATTERNS)
        if r is None:
            continue
        try:
            mtime = p.stat().st_mtime
        except OSError:
            mtime = 0
        samples.append((closeness(p), r, mtime, str(p), p))
    samples.sort()
    out["sample_candidates"] = [t[3] for t in samples[:8]]
    out["sample_submission"] = samples[0][3] if samples else None
    return out


class Project:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise LoadError(f"폴더가 없습니다: {self.root}")
        self.dir = _pick_store(self.root)
        self.lock = threading.RLock()
        self.settings = self._load_settings()
        self.train: pd.DataFrame | None = None
        self.test: pd.DataFrame | None = None
        self.sample: pd.DataFrame | None = None
        self.columns: list[ColumnInfo] = []
        self.guess: CompetitionGuess | None = None
        self.cache: dict = {}
        self.loaded_at: float | None = None
        self.load_error: str | None = None

    # ─────────────────────────── 설정
    def _load_settings(self) -> dict:
        p = self.dir / "project.json"
        s = json.loads(json.dumps(DEFAULT_SETTINGS))
        self.notices: list[str] = []
        if p.exists():
            try:
                saved = json.loads(p.read_text(encoding="utf-8"))
                if not isinstance(saved, dict):
                    raise ValueError("설정 형식이 아님")
                _deep_update(s, saved)
            except (OSError, ValueError, json.JSONDecodeError):
                bak = p.with_name(f"project.broken-{time.strftime('%Y%m%d%H%M%S')}.json")
                try:
                    os.replace(p, bak)
                    self.notices.append(f"설정 파일이 깨져 있어 {bak.name}로 옮기고 새로 시작했습니다.")
                except OSError:
                    self.notices.append("설정 파일을 읽지 못해 기본 설정으로 시작했습니다.")
        if not s["name"]:
            s["name"] = self.root.name
        return s

    def save_settings(self) -> None:
        self.dir.mkdir(exist_ok=True)
        if not self.settings.get("created_at"):
            self.settings["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        tmp = self.dir / f"project.json.{os.getpid()}.{threading.get_ident()}.tmp"
        tmp.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")
        _replace_retry(tmp, self.dir / "project.json")

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
            # 저장된 파일이 없어졌으면(이름 변경 등) 다시 찾는다
            for k in ("train", "test", "sample_submission"):
                if files.get(k) and not self.resolve(files[k]).exists():
                    self.notices.append(f"{k} 파일({files[k]})이 없어져서 다시 찾았습니다.")
                    files[k] = None
                    if k == "train":
                        files["test"] = files["test"] if files.get("test") and self.resolve(files["test"]).exists() else None
            found = None
            if not files.get("train"):
                found = find_data_files(self.root)
                if found["ambiguous"]:
                    names = ", ".join(self.rel(d) or d for d in found["ambiguous"][:8])
                    raise LoadError(f"이 폴더 아래에 대회가 여러 개 있는 것 같습니다 ({names}). "
                                    "대회 폴더 하나를 열거나, 파일을 직접 고르세요.")
                for k in ("train", "test", "sample_submission"):
                    if found[k] and not files.get(k):
                        files[k] = self.rel(found[k])
            if not files.get("train"):
                raise LoadError("train 파일을 찾지 못했습니다. 파일 이름에 train이 들어간 파일이 있는 폴더를 열거나, 파일을 직접 고르세요.")
            cache_dir = self.dir / "cache"
            if progress:
                progress(0.1, "train 읽는 중")
            self.train = read_table(self.resolve(files["train"]), cache_dir=cache_dir)
            if len(self.train) == 0:
                raise LoadError("train 파일에 데이터 행이 없습니다 (머리글만 있음).")
            if progress:
                progress(0.5, "test 읽는 중")
            self.test = read_table(self.resolve(files["test"]), cache_dir=cache_dir) if files.get("test") else None
            if self.test is not None and len(self.test) == 0:
                self.notices.append("test 파일에 데이터 행이 없어 test 없이 엽니다.")
                self.test = None
                files["test"] = None
            self.sample = read_table(self.resolve(files["sample_submission"])) if files.get("sample_submission") else None
            # 처음 찾은 제출 양식이 test와 행 수가 다르면 다른 후보 중 맞는 것을 쓴다
            if found and self.sample is not None and self.test is not None and len(self.sample) != len(self.test):
                for cand in found["sample_candidates"][1:]:
                    try:
                        alt = read_table(cand)
                    except LoadError:
                        continue
                    if len(alt) == len(self.test):
                        self.sample, files["sample_submission"] = alt, self.rel(cand)
                        break
            if progress:
                progress(0.7, "컬럼 종류 추론 중")
            self.columns = infer_columns(self.train, self.test)
            for c in self.columns:  # 사용자가 바꾼 종류 적용
                if c.name in self.settings["kinds"]:
                    c.kind = self.settings["kinds"][c.name]
            self.guess = guess_competition(self.train, self.test, self.sample, self.columns)
            self.apply_custom_metric()
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
            if self.guess is not None:
                from .metrics import METRICS
                m = METRICS.get(s["metric"])
                if m is not None:
                    why = {"proba": "제출 양식이 확률(소수)을 받는 것 같아", "label": "제출 양식이 라벨(정수·클래스)을 받는 것 같아",
                           "value": "값을 예측하는 회귀라"}[m.needs]
                    self.guess.reasons.append(f"{why} 평가 지표를 '{m.label}'(으)로 골랐습니다. 대회 안내와 다르면 바꾸세요.")
            self.cache.clear()
            self.loaded_at = time.time()
            self.save_settings()

    def apply_custom_metric(self) -> str | None:
        """설정에 사용자 지표 파일이 있으면 등록한다. 실패하면 이유를 돌려주고 기본 지표로 돌아간다."""
        from . import metrics as M
        cm = self.settings.get("custom_metric")
        self.cache.pop("custom_metric_error", None)
        if not cm or not cm.get("path"):
            M.unregister_custom()
            if self.settings.get("metric") == M.CUSTOM_KEY:
                self.settings["metric"] = None
            return None
        try:
            M.register_custom(str(self.resolve(cm["path"])), self.settings.get("task") or "regression",
                              bool(cm.get("higher_is_better", True)), cm.get("needs") or "proba", cm.get("label"))
            return None
        except ValueError as e:
            M.unregister_custom()
            if self.settings.get("metric") == M.CUSTOM_KEY:
                self.settings["metric"] = None
            self.cache["custom_metric_error"] = str(e)
            return str(e)

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


def _replace_retry(src: Path, dst: Path, tries: int = 20) -> None:
    """윈도우에서 다른 프로세스가 잠깐 파일을 열고 있으면 os.replace가 실패하므로 잠시 뒤 다시 시도"""
    for i in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == tries - 1:
                raise
            time.sleep(0.05 * (i + 1))


def _pick_store(root: Path) -> Path:
    """대회 폴더에 쓸 수 있으면 <폴더>/.dotbogi, 읽기 전용(캐글 입력 폴더 등)이면 사용자 홈 아래."""
    import hashlib
    d = root / STORE
    try:
        d.mkdir(exist_ok=True)
        probe = d / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return d
    except OSError:
        home = Path(os.environ.get("DOTBOGI_HOME", Path.home() / ".dotbogi"))
        h = hashlib.sha1(str(root).encode()).hexdigest()[:10]
        alt = home / "projects" / f"{root.name}-{h}"
        alt.mkdir(parents=True, exist_ok=True)
        return alt


def _align_proba_classes(y: pd.Series, classes: list) -> list:
    """저장된 클래스 목록을 실제 타깃 값의 자료형에 맞춘다 (순서는 제출 파일 컬럼 순서)."""
    from .schema import match_proba_columns
    values = list(pd.unique(y.dropna()))
    matched = match_proba_columns(classes, values)
    return matched if matched is not None else list(classes)


def _deep_update(base: dict, new: dict) -> None:
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_update(base[k], v)
        else:
            base[k] = v
