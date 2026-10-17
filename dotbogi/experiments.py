"""실험 대장: CV·Public/Private LB·메모·OOF·제출 파일을 한 곳에 기록하고 비교한다.

저장 위치: <프로젝트>/.dotbogi/experiments.json, .dotbogi/runs/<id>/(oof.parquet, test.parquet, submission.csv)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import threading
import uuid
from pathlib import Path

import numpy as np
import pandas as pd

from . import metrics as M

_LOCK = threading.RLock()


def now_iso() -> str:
    return dt.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def slug(name: str) -> str:
    s = re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.UNICODE).strip("_")
    return s[:40] or "exp"


class LedgerLock:
    """여러 프로세스(화면 서버와 학습 스크립트)가 같은 대장을 동시에 고쳐도 기록이 사라지지 않게 하는 잠금 파일."""

    def __init__(self, path: Path, timeout: float = 30.0, stale: float = 60.0):
        self.path, self.timeout, self.stale = path, timeout, stale
        self.fd = None

    def __enter__(self):
        import time
        self.path.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.time()
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:  # 죽은 프로세스가 남긴 오래된 잠금은 치운다
                    if time.time() - self.path.stat().st_mtime > self.stale:
                        self.path.unlink()
                        continue
                except OSError:
                    pass
                if time.time() - t0 > self.timeout:
                    raise TimeoutError("실험 대장을 다른 프로그램이 쓰고 있어 기다리다 멈췄습니다. 잠시 뒤 다시 해 보세요.")
                time.sleep(0.02)
            except PermissionError:
                if time.time() - t0 > self.timeout:
                    raise
                time.sleep(0.02)

    def __exit__(self, *exc):
        try:
            if self.fd is not None:
                os.close(self.fd)
            self.path.unlink()
        except OSError:
            pass


class Ledger:
    def __init__(self, store_dir: str | os.PathLike):
        self.dir = Path(store_dir)
        self.path = self.dir / "experiments.json"
        self.runs = self.dir / "runs"
        self.lockfile = self.dir / "experiments.lock"

    # ─────────────────────────── 읽기/쓰기
    def load(self) -> list[dict]:
        import time
        with _LOCK:
            if not self.path.exists():
                return []
            raw = None
            for i in range(30):  # 윈도우에서 다른 프로세스가 바꾸는 순간에는 잠깐 못 읽을 수 있다
                try:
                    raw = self.path.read_bytes()
                    break
                except PermissionError:
                    time.sleep(0.02 * (i + 1))
            if raw is None:
                raise OSError("실험 대장 파일을 읽지 못했습니다. 다른 프로그램이 잡고 있는지 확인하세요.")
            try:
                data = json.loads(raw.decode("utf-8"))
                exps = data.get("experiments") if isinstance(data, dict) else data
                if not isinstance(exps, list):
                    raise ValueError("목록이 아님")
            except (UnicodeDecodeError, json.JSONDecodeError, ValueError, AttributeError):
                # 깨진 파일은 보존하고 빈 목록으로 시작 (다음 저장 때 새 파일이 된다)
                bak = self.path.with_name(f"experiments.broken-{dt.datetime.now():%Y%m%d%H%M%S%f}.json")
                try:
                    shutil.copy(self.path, bak)
                except OSError:
                    pass
                return []
            return [_clean(e) for e in exps if isinstance(e, dict) and e.get("id")]

    def save(self, exps: list[dict]) -> None:
        with _LOCK:
            self.dir.mkdir(parents=True, exist_ok=True)
            tmp = self.dir / f"experiments.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp"
            tmp.write_text(json.dumps({"version": 1, "experiments": exps}, ensure_ascii=False, indent=1,
                                      default=_json_default), encoding="utf-8")
            from .project import _replace_retry
            _replace_retry(tmp, self.path)

    def get(self, exp_id: str) -> dict | None:
        for e in self.load():
            if e["id"] == exp_id:
                return e
        return None

    def add(self, name: str, metric: str | None = None, cv: float | None = None, cv_std: float | None = None,
            fold_scores: list | None = None, lb_public: float | None = None, lb_private: float | None = None,
            notes: str = "", tags: list[str] | None = None, params: dict | None = None,
            source: str = "manual", oof: pd.DataFrame | None = None, test_pred: pd.DataFrame | None = None,
            submission: pd.DataFrame | None = None, submitted_at: str | None = None,
            extra: dict | None = None) -> dict:
        exp_id = f"{dt.datetime.now():%m%d%H%M%S}-{uuid.uuid4().hex[:4]}"
        run_dir = self.runs / exp_id
        e = {
            "id": exp_id, "name": (name or "").strip() or exp_id, "created_at": now_iso(), "source": source,
            "metric": metric, "cv": _num(cv, "CV"), "cv_std": _num(cv_std, "CV 편차"), "fold_scores": fold_scores or [],
            "lb_public": _num(lb_public, "Public LB"), "lb_private": _num(lb_private, "Private LB"),
            "submitted_at": submitted_at or (now_iso() if lb_public not in (None, "") else None),
            "notes": notes or "", "tags": tags or [], "params": params or {},
            "final": False, "files": {}, **(extra or {}),
        }
        # 큰 파일은 잠금 밖에서 먼저 쓴다
        if oof is not None or test_pred is not None or submission is not None:
            run_dir.mkdir(parents=True, exist_ok=True)
        if oof is not None:
            oof.to_parquet(run_dir / "oof.parquet", index=False)
            e["files"]["oof"] = "oof.parquet"
        if test_pred is not None:
            test_pred.to_parquet(run_dir / "test.parquet", index=False)
            e["files"]["test"] = "test.parquet"
        if submission is not None:
            submission.to_csv(run_dir / "submission.csv", index=False, encoding="utf-8")
            e["files"]["submission"] = "submission.csv"
        with _LOCK, LedgerLock(self.lockfile):
            exps = self.load()
            exps.append(e)
            self.save(exps)
        return e

    def update(self, exp_id: str, **fields) -> dict:
        allowed = {"name", "cv", "cv_std", "lb_public", "lb_private", "notes", "tags", "final", "submitted_at",
                   "metric", "params", "kaggle_key"}
        labels = {"cv": "CV", "cv_std": "CV 편차", "lb_public": "Public LB", "lb_private": "Private LB"}
        clean = {}
        for k, v in fields.items():
            if k not in allowed:
                continue
            if k in labels:
                v = _num(v, labels[k])
            if k == "name":
                v = str(v or "").strip()
                if not v:
                    raise ValueError("실험 이름을 비울 수 없습니다.")
            if k == "final":
                v = bool(v)
            clean[k] = v
        with _LOCK, LedgerLock(self.lockfile):
            exps = self.load()
            for e in exps:
                if e["id"] == exp_id:
                    for k, v in clean.items():
                        if k == "lb_public" and v is not None and not e.get("submitted_at") and "submitted_at" not in clean:
                            e["submitted_at"] = now_iso()
                        e[k] = v
                    e["updated_at"] = now_iso()
                    self.save(exps)
                    return e
        raise KeyError(exp_id)

    def delete(self, exp_id: str) -> None:
        """기록에서 빼고 파일은 .dotbogi/trash 로 옮긴다 (되살릴 수 있게)."""
        with _LOCK, LedgerLock(self.lockfile):
            exps = self.load()
            keep = [e for e in exps if e["id"] != exp_id]
            if len(keep) == len(exps):
                raise KeyError(exp_id)
            gone = next(e for e in exps if e["id"] == exp_id)
            trash = self.dir / "trash"
            trash.mkdir(parents=True, exist_ok=True)
            (trash / f"{exp_id}.json").write_text(json.dumps(gone, ensure_ascii=False, indent=1,
                                                             default=_json_default), encoding="utf-8")
            if (self.runs / exp_id).exists():
                shutil.move(str(self.runs / exp_id), str(trash / exp_id))
            self.save(keep)

    def file_path(self, e: dict, kind: str) -> Path | None:
        f = (e.get("files") or {}).get(kind)
        if not f:
            return None
        p = Path(f)
        return p if p.is_absolute() else self.runs / e["id"] / f

    def read_oof(self, e: dict) -> pd.DataFrame | None:
        p = self.file_path(e, "oof")
        return pd.read_parquet(p) if p and p.exists() else None

    def read_test(self, e: dict) -> pd.DataFrame | None:
        p = self.file_path(e, "test")
        return pd.read_parquet(p) if p and p.exists() else None


def _f(v):
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if np.isfinite(f) else None


def _num(v, label: str = "값"):
    """사용자가 넣은 점수: 비었으면 None, 숫자가 아니면 오류 (조용히 지우지 않게)"""
    if v is None or (isinstance(v, str) and v.strip() == ""):
        return None
    try:
        f = float(str(v).strip().replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        raise ValueError(f"{label}에는 숫자를 적으세요: {v!r}")
    if not np.isfinite(f):
        raise ValueError(f"{label}에 무한대나 NaN은 쓸 수 없습니다.")
    return f


def _clean(e: dict) -> dict:
    """손으로 고친 기록 등 모양이 조금 틀린 항목도 화면이 깨지지 않게 다듬는다."""
    for k in ("cv", "cv_std", "lb_public", "lb_private"):
        e[k] = _f(e.get(k))
    e["name"] = str(e.get("name") or e["id"])
    e.setdefault("files", {})
    if not isinstance(e["files"], dict):
        e["files"] = {}
    e.setdefault("params", {})
    e.setdefault("notes", "")
    e.setdefault("fold_scores", [])
    if not isinstance(e["fold_scores"], list):
        e["fold_scores"] = []
    e.setdefault("final", False)
    e.setdefault("source", "manual")
    return e


def _json_default(o):
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


# ─────────────────────────────────────────── 예측 ↔ 표 변환
def pred_columns(task: str, classes: list) -> list[str]:
    if task == "multiclass":
        return [f"p_{c}" for c in classes]
    return ["pred"]


def oof_frame(pred: np.ndarray, task: str, classes: list, ids: np.ndarray | None,
              fold: np.ndarray | None = None) -> pd.DataFrame:
    df = pd.DataFrame({"row": np.arange(len(pred))})
    if ids is not None:
        df["id"] = ids
    if fold is not None:
        df["fold"] = fold
    cols = pred_columns(task, classes)
    arr = np.asarray(pred, dtype="float64")
    if arr.ndim == 1:
        df[cols[0]] = arr
    else:
        for i, c in enumerate(cols):
            df[c] = arr[:, i]
    return df


def frame_pred(df: pd.DataFrame, task: str) -> np.ndarray:
    cols = [c for c in df.columns if c == "pred" or c.startswith("p_")]
    if task == "multiclass":
        return df[[c for c in cols if c.startswith("p_")]].to_numpy(dtype="float64")
    return df[cols[0]].to_numpy(dtype="float64")


def make_submission(test_pred: np.ndarray, sample: pd.DataFrame, test: pd.DataFrame | None, id_col: str | None,
                    task: str, classes: list, submission_format: str, metric: str | None,
                    threshold: float = 0.5) -> pd.DataFrame:
    """test 예측을 sample_submission 모양으로. test와 sample의 순서가 다르면 ID로 맞춘다."""
    sub = sample.copy()
    pred_cols = [c for c in sample.columns if c != id_col]
    p = np.asarray(test_pred)
    if test is not None and id_col and id_col in test.columns and id_col in sample.columns:
        key_t = test[id_col].astype("string").to_numpy()
        key_s = sample[id_col].astype("string").to_numpy()
        if len(key_t) != len(key_s) or not (key_t == key_s).all():
            pos = pd.Series(np.arange(len(key_t)), index=key_t)
            missing = set(key_s) - set(key_t)
            if missing:
                raise ValueError(f"sample_submission의 ID {len(missing)}개가 test에 없습니다.")
            p = p[pos.loc[key_s].to_numpy()]
    elif len(p) != len(sample):
        raise ValueError(f"예측 행 수({len(p)})와 sample_submission 행 수({len(sample)})가 다릅니다.")

    needs = M.METRICS[metric].needs if metric in M.METRICS else "proba"
    if task == "regression":
        sub[pred_cols[0]] = p
    elif task == "binary":
        col = pred_cols[0]
        sample_is_label = not pd.api.types.is_float_dtype(sample[col]) or needs == "label"
        if needs == "proba" and pd.api.types.is_numeric_dtype(sample[col]):
            sample_is_label = False
        if sample_is_label:
            lab = np.where(p >= threshold, 1, 0)
            cls = classes if classes and len(classes) == 2 else [0, 1]
            sub[col] = np.array(cls, dtype=object)[lab]
            if pd.api.types.is_numeric_dtype(sample[col]):
                sub[col] = pd.to_numeric(sub[col])
            elif pd.api.types.is_bool_dtype(sample[col]):
                sub[col] = sub[col].astype(bool)
        else:
            sub[col] = p
    else:  # multiclass
        if submission_format == "proba_columns" and len(pred_cols) > 1:
            for i, c in enumerate(pred_cols):
                sub[c] = p[:, i] if i < p.shape[1] else 0.0
        else:
            lab = p.argmax(axis=1)
            sub[pred_cols[0]] = np.array(classes, dtype=object)[lab]
            if pd.api.types.is_numeric_dtype(sample[pred_cols[0]]):
                sub[pred_cols[0]] = pd.to_numeric(sub[pred_cols[0]])
    return sub


# ─────────────────────────────────────────── CV ↔ LB 분석
def cv_lb_analysis(exps: list[dict], metric: str | None) -> dict:
    pts = [e for e in exps if e.get("cv") is not None and e.get("lb_public") is not None]
    out = {"n": len(pts), "points": [{"id": e["id"], "name": e["name"], "cv": e["cv"], "lb": e["lb_public"],
                                      "private": e.get("lb_private")} for e in pts]}
    if len(pts) >= 3:
        cv = np.array([e["cv"] for e in pts])
        lb = np.array([e["lb_public"] for e in pts])
        out["pearson"] = float(np.corrcoef(cv, lb)[0, 1]) if cv.std() > 0 and lb.std() > 0 else None
        out["spearman"] = float(pd.Series(cv).corr(pd.Series(lb), method="spearman")) if len(pts) > 2 else None
        if cv.std() > 0:
            slope, icpt = np.polyfit(cv, lb, 1)
            out["fit"] = {"slope": float(slope), "intercept": float(icpt)}
            resid = lb - (slope * cv + icpt)
            sd = resid.std() or 1e-12
            hib = M.METRICS[metric].higher_is_better if metric in M.METRICS else True
            outl = []
            for e, r in zip(pts, resid):
                z = r / sd
                if abs(z) > 1.8:
                    better_lb = (z > 0) == hib
                    outl.append({"id": e["id"], "name": e["name"], "z": float(z),
                                 "kind": "lb_lucky" if better_lb else "lb_unlucky"})
            out["outliers"] = outl
        sp = out.get("spearman")
        out["tentative"] = len(pts) < 5
        if sp is None:
            out["verdict"] = "unknown"
        elif sp >= 0.7:
            out["verdict"] = "aligned"
        elif sp >= 0.3:
            out["verdict"] = "weak"
        else:
            out["verdict"] = "mismatch"
    else:
        out["verdict"] = "not_enough"
    return out


def lb_noise(y: np.ndarray, pred: np.ndarray, metric: str, public_rows: int, n_boot: int = 200,
             seed: int = 0, pred_b: np.ndarray | None = None) -> dict:
    """OOF로 'public LB 크기만큼 무작위로 뽑은 행'의 점수를 여러 번 재서, LB 점수가 우연히 얼마나 흔들리는지 본다.
    pred_b가 있으면 같은 표본에서 두 실험의 점수 차이 분포도 준다."""
    n = len(y)
    k = int(min(max(public_rows, 10), n))
    rng = np.random.default_rng(seed)
    scores, diffs, wins = [], [], 0
    for _ in range(n_boot):
        idx = rng.choice(n, k, replace=False)
        try:
            sa = M.score(metric, y[idx], pred[idx])
        except Exception:
            continue
        if not np.isfinite(sa):
            continue
        scores.append(sa)
        if pred_b is not None:
            sb = M.score(metric, y[idx], pred_b[idx])
            diffs.append(sa - sb)
            if M.better(metric, sa, sb):
                wins += 1
    if not scores:
        return {"ok": False}
    sc = np.array(scores)
    out = {"ok": True, "rows": k, "std": float(sc.std()), "p05": float(np.quantile(sc, 0.05)),
           "p95": float(np.quantile(sc, 0.95)), "full": float(M.score(metric, y, pred))}
    if pred_b is not None and diffs:
        d = np.array(diffs)
        out.update({"diff_mean": float(d.mean()), "diff_std": float(d.std()), "win_rate": wins / len(diffs),
                    "full_b": float(M.score(metric, y, pred_b))})
    return out


def suggest_final(exps: list[dict], metric: str | None, picks: int = 2, noise: float | None = None) -> dict:
    """최종 제출 고르기 도움: CV 최고 1개 + (가능하면) CV가 비슷하면서 LB도 좋은 다른 1개."""
    if metric not in M.METRICS:
        return {"picks": [], "reasons": ["평가 지표를 먼저 정하세요."]}
    hib = M.METRICS[metric].higher_is_better
    with_cv = [e for e in exps if e.get("cv") is not None]
    if not with_cv:
        return {"picks": [], "reasons": ["CV 점수가 기록된 실험이 없습니다."]}
    key = (lambda e: -e["cv"]) if hib else (lambda e: e["cv"])
    ranked = sorted(with_cv, key=key)
    first = ranked[0]
    out = {"picks": [{"id": first["id"], "name": first["name"], "why": "CV가 가장 좋습니다. 셰이크업에 가장 강한 선택입니다."}],
           "reasons": []}
    if picks < 2:
        return out
    tol = noise if noise else abs(first["cv"]) * 0.002
    near = [e for e in ranked[1:] if abs(e["cv"] - first["cv"]) <= max(tol, 1e-12)]
    with_lb = [e for e in near if e.get("lb_public") is not None]
    if with_lb:
        lb_key = (lambda e: -e["lb_public"]) if hib else (lambda e: e["lb_public"])
        second = sorted(with_lb, key=lb_key)[0]
        out["picks"].append({"id": second["id"], "name": second["name"],
                             "why": "CV가 최고와 거의 같으면서 Public LB가 좋은 실험입니다. 두 번째 보험으로 좋습니다."})
    elif len(ranked) > 1:
        second = ranked[1]
        out["picks"].append({"id": second["id"], "name": second["name"],
                             "why": "CV 2위입니다. 첫 번째와 다른 모델이면 더 좋은 보험이 됩니다."})
    out["tolerance"] = tol
    return out
