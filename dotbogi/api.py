"""화면(브라우저)과 분석 엔진 사이의 기능 모음. HTTP와 무관하게 테스트할 수 있게 분리했다."""
from __future__ import annotations

import hashlib
import json
import os
import string
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from . import __version__, i18n
from . import metrics as M
from .analysis import gbm
from .analysis.adversarial import run_adversarial
from .analysis.baseline import run_baseline
from .analysis.checks import run_checks
from .analysis.cv import STRATEGIES, fold_summary, make_folds, recommend
from .analysis.features import build_matrix
from .analysis.profile import profile_column
from .experiments import (Ledger, cv_lb_analysis, frame_pred, lb_noise, make_submission, make_submission_multi,
                          oof_frame,
                          suggest_final)
from .io import TABLE_EXTS, LoadError, file_signature, read_table
from .jobs import JobManager
from .project import PLATFORMS, Project, find_data_files
from .schema import KINDS, to_datetime_safe
from .submission import check_submission, compare_submissions, fix_submission
from .utils import as_label, jsonable, sample_index, to_float

HOME = Path(os.environ.get("DOTBOGI_HOME", Path.home() / ".dotbogi"))
RELEASES_API = "https://api.github.com/repos/maximuthking/dotbogi/releases/latest"
RELEASES_PAGE = "https://github.com/maximuthking/dotbogi/releases/latest"
DEFAULT_PREFS = {"update_check": True, "lang": None}


def load_prefs() -> dict:
    """대회와 상관없는 앱 설정 (~/.dotbogi/prefs.json)"""
    try:
        data = json.loads((HOME / "prefs.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}
    return {**DEFAULT_PREFS, **{k: v for k, v in data.items() if k in DEFAULT_PREFS}}


def _version_tuple(v: str) -> tuple:
    parts = []
    for x in str(v).lstrip("vV").split("."):
        digits = "".join(ch for ch in x if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts + [0] * (3 - len(parts)))


class App:
    MAX_TABS = 8

    def __init__(self):
        self.project: Project | None = None          # 지금 보고 있는 대회 (활성 탭)
        self.projects: dict[str, Project] = {}       # 열어 둔 대회들 (탭 순서)
        self.jobs = JobManager(workers=2)
        self.started = time.time()

    # ═════════════════════════════════════════ 공통
    def require(self) -> Project:
        if self.project is None or not self.project.loaded:
            raise LoadError("먼저 대회 폴더를 여세요.")
        return self.project

    def ledger(self) -> Ledger:
        return Ledger(self.require().dir)

    def _for(self, p: Project) -> "App":
        """p를 '지금 대회'로 보는 App. 작업 도중 다른 탭으로 바꿔도 작업은 시작한 대회에만 쓴다."""
        a = object.__new__(App)
        a.__dict__ = dict(self.__dict__)
        a.project = p
        return a

    # ═════════════════════════════════════════ 탭 (대회 여러 개)
    def tabs(self) -> list[dict]:
        items = list(self.projects.values())
        if self.project is not None and str(self.project.root) not in self.projects:
            items.append(self.project)
        return [{"root": str(p.root), "name": p.settings.get("name") or p.root.name, "loaded": p.loaded,
                 "error": bool(getattr(p, "load_error", None)), "active": p is self.project} for p in items]

    def switch_project(self, path: str) -> dict:
        p = self.projects.get(str(Path(path)))
        if p is None:
            raise LoadError("열려 있지 않은 대회입니다.")
        self.project = p
        return self.state()

    def close_project(self, path: str) -> dict:
        key = str(Path(path))
        p = self.projects.pop(key, None)
        if p is None and not (self.project is not None and str(self.project.root) == key):
            raise LoadError("열려 있지 않은 대회입니다.")
        if self.project is p or (self.project is not None and str(self.project.root) == key):
            rest = list(self.projects.values())
            self.project = rest[-1] if rest else None
        return self.state()

    def _truth(self, p: Project) -> dict:
        """채점용 정답. 타깃이 여러 개이고 과제 유형이 같으면 (행, 타깃) 2차원, 아니면 첫 타깃 1차원."""
        if "truth" in p.cache:
            return p.cache["truth"]
        from .analysis.common import encode_target
        s = p.settings
        targets = [t for t in s["target"] if t in p.train.columns]
        y, mask, classes = p.encoded_target()
        out = {"y": y, "mask": mask, "classes": classes, "classes_by_target": [classes], "targets": targets[:1],
               "task": s["task"], "multi": False, "note": None}
        if len(targets) > 1 and y is not None:
            if s["task"] == "multiclass":
                out["note"] = "다중분류 타깃이 여러 개인 대회는 첫 타깃 기준으로 계산합니다."
            else:
                cols, cbt, mk, mixed = [np.asarray(y, dtype="float64")], [classes], mask.copy(), None
                for t in targets[1:]:
                    if s["task"] == "binary":
                        cl = _classes(p.train[t])
                        if len(cl) != 2:
                            mixed = t
                            break
                        yt, mt, cl = encode_target(p.train[t], "binary", cl)
                    else:
                        yt, mt, cl = encode_target(p.train[t], "regression", [])
                        if not mt.any():
                            mixed = t
                            break
                    cols.append(np.asarray(yt, dtype="float64"))
                    cbt.append(cl)
                    mk &= mt
                if mixed:
                    out["note"] = f"타깃 '{mixed}'의 과제 유형이 첫 타깃과 달라, 앙상블·흔들림 계산은 첫 타깃 기준입니다."
                else:
                    out.update({"y": np.column_stack(cols), "mask": mk, "classes_by_target": cbt, "targets": targets,
                                "multi": True})
        p.cache["truth"] = out
        return out

    def _pred(self, p: Project, frame: pd.DataFrame) -> np.ndarray:
        """저장된 OOF·test 예측 표를 정답과 같은 모양의 배열로."""
        return frame_pred(frame, p.settings["task"], self._truth(p)["targets"])

    def state(self) -> dict:
        p = self.project
        out = {
            "version": __version__, "lightgbm": gbm.HAS_LGB, "platform": sys.platform,
            "recent": self.recent(), "kinds": list(KINDS), "strategies": STRATEGIES,
            "platforms": PLATFORMS, "home": str(Path.home()),
            "jobs": [j.to_dict(False) for j in self.jobs.running()],
            "prefs": load_prefs(),
            "tabs": self.tabs(),
            "project": None,
        }
        if p is not None:
            s = p.settings
            out["project"] = {
                "root": str(p.root), "name": s["name"], "loaded": p.loaded, "settings": s,
                "metrics": M.metrics_for(s["task"]) if s.get("task") else [],
                "metric_info": _metric_info(s.get("metric")),
                "shapes": {k: (list(df.shape) if df is not None else None)
                           for k, df in (("train", p.train), ("test", p.test), ("sample_submission", p.sample))},
                "columns": [c.to_dict() for c in p.columns],
                "has_folds": p.folds_path().exists(),
                "store": str(p.dir),
                "custom_metric_error": p.cache.get("custom_metric_error"),
                "notices": list(getattr(p, "notices", []) or []),
                "load_error": getattr(p, "load_error", None),
            }
            if p.loaded and len(s.get("target") or []) > 1:
                try:
                    tr = self._truth(p)
                    out["project"]["multi_target"] = {"targets": list(s["target"]), "multi": tr["multi"], "note": tr["note"]}
                except Exception:
                    pass
        return out

    # ═════════════════════════════════════════ 최근 프로젝트 / 폴더 고르기
    # ═════════════════════════════════════════ 앱 설정·업데이트 알림
    def set_prefs(self, patch: dict) -> dict:
        prefs = load_prefs()
        if "update_check" in patch:
            prefs["update_check"] = bool(patch["update_check"])
        if "lang" in patch:
            if patch["lang"] not in (None, "ko", "en"):
                raise LoadError("화면 언어는 ko 또는 en입니다.")
            prefs["lang"] = patch["lang"]
        HOME.mkdir(parents=True, exist_ok=True)
        (HOME / "prefs.json").write_text(json.dumps(prefs, ensure_ascii=False, indent=1), encoding="utf-8")
        return prefs

    def check_update(self, force: bool = False) -> dict:
        """GitHub 최신 릴리스와 지금 버전을 비교한다. 하루에 한 번만 묻고, 인터넷이 없으면 조용히 넘어간다."""
        if not force and not load_prefs()["update_check"]:
            return {"enabled": False, "current": __version__}
        cache_f = HOME / "update.json"
        info = None
        try:
            info = json.loads(cache_f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        if force or not info or time.time() - float(info.get("checked_at", 0)) > 86400:
            import urllib.request
            try:
                req = urllib.request.Request(RELEASES_API, headers={"User-Agent": f"dotbogi/{__version__}",
                                                                    "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(req, timeout=5) as r:
                    rel = json.loads(r.read().decode("utf-8"))
                setup = next((x["browser_download_url"] for x in rel.get("assets", [])
                              if str(x.get("name", "")).lower().endswith(".exe")), None)
                info = {"checked_at": time.time(), "latest": str(rel.get("tag_name") or "").lstrip("vV"),
                        "url": rel.get("html_url") or RELEASES_PAGE, "setup_url": setup,
                        "published_at": rel.get("published_at")}
                try:
                    HOME.mkdir(parents=True, exist_ok=True)
                    cache_f.write_text(json.dumps(info), encoding="utf-8")
                except OSError:
                    pass
            except Exception as e:  # 인터넷이 없거나 GitHub가 응답하지 않음
                if not info:
                    return {"enabled": True, "current": __version__, "error": f"새 버전을 확인하지 못했습니다 ({type(e).__name__})."}
        latest = info.get("latest") or __version__
        return {"enabled": True, "current": __version__, "latest": latest, "url": info.get("url") or RELEASES_PAGE,
                "setup_url": info.get("setup_url"), "newer": _version_tuple(latest) > _version_tuple(__version__),
                "checked_at": info.get("checked_at")}

    def recent(self) -> list[dict]:
        f = HOME / "recent.json"
        try:
            items = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return [it for it in items if Path(it["path"]).is_dir()][:12]

    def _remember(self, p: Project) -> None:
        items = [it for it in self.recent() if it["path"] != str(p.root)]
        items.insert(0, {"path": str(p.root), "name": p.settings["name"], "opened_at": time.strftime("%Y-%m-%d %H:%M")})
        try:
            HOME.mkdir(parents=True, exist_ok=True)
            (HOME / "recent.json").write_text(json.dumps(items[:12], ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass

    def forget_recent(self, path: str) -> dict:
        items = [it for it in self.recent() if it["path"] != path]
        try:
            (HOME / "recent.json").write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        except OSError:
            pass
        return {"recent": items}

    def browse(self, path: str | None = None) -> dict:
        """폴더 고르기 창용 목록. 경로가 없으면 홈(윈도우는 드라이브 목록도)."""
        if not path:
            path = str(Path.home())
        pth = Path(path).expanduser()
        if pth.is_file():
            pth = pth.parent
        if not pth.is_dir():
            raise LoadError(f"폴더가 없습니다: {path}")
        dirs, files = [], []
        try:
            for e in sorted(os.scandir(pth), key=lambda e: e.name.lower()):
                if e.name.startswith(".") or e.name.startswith("$"):
                    continue
                try:
                    if e.is_dir():
                        dirs.append({"name": e.name, "path": e.path})
                    elif Path(e.name).suffix.lower() in TABLE_EXTS:
                        files.append({"name": e.name, "path": e.path, "size": e.stat().st_size})
                except OSError:
                    continue
        except PermissionError:
            raise LoadError(f"이 폴더는 열 권한이 없습니다: {pth}")
        drives = []
        if sys.platform == "win32":
            drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
        found = find_data_files(pth, max_depth=3) if len(files) < 200 else {}
        parent = str(pth.parent) if pth.parent != pth else None
        return {"path": str(pth), "parent": parent, "dirs": dirs[:500], "files": files[:500], "drives": drives,
                "detected": {k: found.get(k) for k in ("train", "test", "sample_submission")},
                "ambiguous": found.get("ambiguous", [])}

    def open_project(self, path: str) -> dict:
        pth = Path(path).expanduser()
        if pth.is_file():
            pth = pth.parent
        if not str(path).strip():
            raise LoadError("폴더 경로를 적거나 '찾아보기'로 고르세요.")
        project = Project(pth)
        key = str(project.root)
        if key in self.projects and self.projects[key].loaded:  # 이미 열린 대회: 다시 불러오지 않고 그 탭으로
            self.project = self.projects[key]
            return {"switched": True, "root": key}
        if key not in self.projects and len(self.projects) >= self.MAX_TABS:
            raise LoadError(f"대회를 {self.MAX_TABS}개까지 열어 둘 수 있습니다. 탭을 하나 닫고 다시 여세요.")
        job = self.jobs.submit("load", "데이터 불러오기", self._load_job, project, key=key)
        return {"job": job.to_dict(False)}

    def _load_job(self, job, project: Project):
        try:
            project.load(progress=job.update)
        except Exception as e:
            # 열지 못해도 이 폴더는 기억해 둔다 → 화면에서 파일을 직접 골라 다시 열 수 있게
            project.load_error = str(e) if isinstance(e, (LoadError, ValueError)) else f"{type(e).__name__}: {e}"
            self.projects[str(project.root)] = project  # 탭으로 남겨 두고, 화면에서 파일을 직접 골라 다시 열게
            self.project = project
            raise
        project.load_error = None
        self.projects[str(project.root)] = project
        self.project = project
        self._remember(project)
        return {"ok": True, "notices": list(project.notices)}

    def set_files(self, files: dict) -> dict:
        p = self.project
        if p is None:
            raise LoadError("먼저 대회 폴더를 여세요.")
        for k in ("train", "test", "sample_submission"):
            if k in files:
                v = files[k] or None
                if v and not Path(v).is_absolute():
                    v = str(p.root / v)
                if v and not Path(v).exists():
                    raise LoadError(f"파일이 없습니다: {v}")
                p.settings["files"][k] = p.rel(v) if v else None
        # 파일이 바뀌면 타깃·ID 추론을 다시
        p.settings["target"] = []
        p.settings["id_col"] = None
        p.settings["metric"] = None
        p.settings["kinds"] = {}
        p.settings["excluded"] = []
        p.settings["cv"] = None
        p.notices = []
        job = self.jobs.submit("load", "데이터 불러오기", self._load_job, p, key=str(p.root))
        return {"job": job.to_dict(False)}

    def reload(self) -> dict:
        p = self.project
        if p is None:
            raise LoadError("먼저 대회 폴더를 여세요.")
        p.notices = []
        job = self.jobs.submit("load", "데이터 다시 불러오기", self._load_job, p, key=str(p.root))
        return {"job": job.to_dict(False)}

    # ═════════════════════════════════════════ 설정
    def update_settings(self, patch: dict) -> dict:
        p = self.require()
        s = p.settings
        heavy = False
        if "target" in patch:
            t = patch["target"]
            t = [t] if isinstance(t, str) else list(t or [])
            for c in t:
                if c not in p.train.columns:
                    raise LoadError(f"train에 '{c}' 컬럼이 없습니다.")
            if t != s["target"]:
                s["target"] = t
                heavy = True
                if "task" not in patch and t:
                    from .schema import guess_competition
                    tmp = guess_competition(p.train, p.test, p.sample, p.columns)
                    s["task"] = tmp.task if tmp.target == t else _guess_task(p.train[t[0]])
                    s["classes"] = _classes(p.train[t[0]]) if s["task"] != "regression" else []
                    s["submission_format"] = tmp.submission_format if tmp.target == t else "value"
                    s["metric"] = M.default_metric(s["task"], p.sample, t[0], s["submission_format"])
        if "task" in patch and patch["task"] != s["task"]:
            if patch["task"] not in ("binary", "multiclass", "regression"):
                raise LoadError("과제 유형은 binary, multiclass, regression 중 하나입니다.")
            s["task"] = patch["task"]
            t = p.target_col()
            s["classes"] = _classes(p.train[t]) if (t and s["task"] != "regression") else []
            if s["task"] == "binary" and len(s["classes"]) != 2:
                raise LoadError(f"타깃 값이 {len(s['classes'])}가지라 이진분류로 둘 수 없습니다.")
            if s["submission_format"] == "proba_columns" and s["task"] != "multiclass":
                s["submission_format"] = "value"
            s["metric"] = M.default_metric(s["task"], p.sample, t, s["submission_format"])
            p.apply_custom_metric()
            heavy = True
        if "metric" in patch:
            if patch["metric"] not in M.METRICS:
                raise LoadError("알 수 없는 평가 지표입니다.")
            if s["task"] not in M.METRICS[patch["metric"]].tasks:
                raise LoadError("이 과제 유형에 쓸 수 없는 지표입니다.")
            s["metric"] = patch["metric"]
        if "id_col" in patch:
            v = patch["id_col"] or None
            if v and v not in p.train.columns and (p.test is None or v not in p.test.columns):
                raise LoadError(f"'{v}' 컬럼이 없습니다.")
            if v != s["id_col"]:
                s["id_col"] = v
                p.invalidate("checks", "adv", "recommend")
        if "kinds" in patch:
            for name, kind in (patch["kinds"] or {}).items():
                if kind not in KINDS:
                    raise LoadError(f"알 수 없는 종류: {kind}")
                col = p.column(name)
                if col is None:
                    raise LoadError(f"'{name}' 컬럼이 없습니다.")
                col.kind = kind
                s["kinds"][name] = kind
                heavy = True
        if "excluded" in patch:
            ex = [c for c in (patch["excluded"] or []) if p.column(c) is not None]
            if ex != s["excluded"]:
                s["excluded"] = ex
                p.invalidate("checks", "adv", "recommend")
        if "competition" in patch:
            comp = s["competition"]
            for k in ("platform", "public_share", "daily_limit", "final_picks", "end_date", "url", "rules_note",
                      "slug"):
                if k in patch["competition"]:
                    comp[k] = patch["competition"][k]
            if comp.get("public_share") not in (None, ""):
                ps = float(comp["public_share"])
                comp["public_share"] = ps / 100 if ps > 1 else ps
        if "custom_metric" in patch:
            cm = patch["custom_metric"]
            if cm and cm.get("path"):
                path = str(cm["path"]).strip()
                if not Path(path).is_absolute():
                    path = str(p.root / path)
                prev_cm, prev_metric = s.get("custom_metric"), s.get("metric")
                s["custom_metric"] = {"path": p.rel(path), "higher_is_better": bool(cm.get("higher_is_better", True)),
                                      "needs": cm.get("needs") or "proba", "label": (cm.get("label") or "").strip() or None}
                err = p.apply_custom_metric()
                if err:
                    s["custom_metric"], s["metric"] = prev_cm, prev_metric  # 이전 상태로 되돌림
                    p.apply_custom_metric()
                    if s.get("metric") is None:
                        s["metric"] = prev_metric if prev_metric in M.METRICS else M.default_metric(
                            s["task"], p.sample, p.target_col(), s["submission_format"])
                    p.save_settings()
                    raise LoadError(err)
                s["metric"] = M.CUSTOM_KEY
            else:
                s["custom_metric"] = None
                p.apply_custom_metric()
                if not s.get("metric"):
                    s["metric"] = M.default_metric(s["task"], p.sample, p.target_col(), s["submission_format"])
        if "name" in patch and patch["name"]:
            s["name"] = str(patch["name"])[:80]
        if heavy:
            p.invalidate()
        p.invalidate("sheet")  # 데이터 표의 예측·오차 열은 타깃·지표 설정에 따라 달라진다
        p.save_settings()
        return self.state()

    # ═════════════════════════════════════════ 개요
    def overview(self) -> dict:
        p = self.require()
        s = p.settings
        kinds: dict[str, int] = {}
        for c in p.columns:
            kinds[c.kind] = kinds.get(c.kind, 0) + 1
        files = {}
        for k, df in (("train", p.train), ("test", p.test), ("sample_submission", p.sample)):
            path = p.resolve(s["files"].get(k))
            files[k] = None if df is None else {
                "path": s["files"].get(k), "rows": len(df), "cols": df.shape[1],
                "memory_mb": float(df.memory_usage(deep=False).sum() / 1e6),
                "file_mb": path.stat().st_size / 1e6 if path and path.exists() else None,
            }
        out = {"files": files, "kinds": kinds, "target": None, "reasons": p.guess.reasons if p.guess else [],
               "task": s["task"], "metric": s["metric"], "id_col": s["id_col"]}
        t = p.target_col()
        if t:
            out["target"] = self._target_summary(p, t)
        return out

    def _target_summary(self, p: Project, t: str) -> dict:
        s = p.settings
        y = p.train[t]
        res = {"name": t, "missing": int(y.isna().sum()), "task": s["task"]}
        if s["task"] == "regression":
            v = to_float(y)
            f = v[np.isfinite(v)]
            if f.size:
                lo, hi = np.quantile(f, [0.0, 1.0])
                edges = np.linspace(lo, hi if hi > lo else lo + 1, 41)
                c, _ = np.histogram(f, edges)
                res.update({"hist": {"edges": edges.tolist(), "counts": c.tolist()},
                            "mean": float(f.mean()), "std": float(f.std()), "min": float(lo), "max": float(hi),
                            "median": float(np.median(f)), "skew": float(pd.Series(f[:500_000]).skew())})
                if f.min() > -1:
                    lf = np.log1p(np.clip(f, 0, None))
                    e2 = np.linspace(lf.min(), lf.max() if lf.max() > lf.min() else lf.min() + 1, 41)
                    res["log_hist"] = {"edges": e2.tolist(), "counts": np.histogram(lf, e2)[0].tolist()}
        else:
            vc = y.value_counts(dropna=True)
            res["classes"] = [{"value": as_label(k), "count": int(v), "rate": float(v / len(y))}
                              for k, v in vc.head(50).items()]
            res["n_classes"] = int(vc.size)
        if len(p.target_col() and s["target"]) > 1:
            res["other_targets"] = s["target"][1:]
        return res

    # ═════════════════════════════════════════ 컬럼 프로필
    def _profile_key(self, p: Project) -> str:
        s = p.settings
        parts = [file_signature(p.resolve(s["files"][k])) if s["files"].get(k) else "-"
                 for k in ("train", "test")]
        parts += [json.dumps(s["target"]), s["task"] or "", json.dumps(s["classes"], default=str),
                  json.dumps(s["kinds"], sort_keys=True), s["submission_format"], "v4"]
        return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]

    def profiles_status(self) -> dict:
        p = self.require()
        if "profiles" in p.cache:
            return {"ready": True}
        f = p.dir / "cache" / f"profiles-{self._profile_key(p)}.json"
        if f.exists():
            try:
                p.cache["profiles"] = json.loads(f.read_text(encoding="utf-8"))
                return {"ready": True}
            except (OSError, json.JSONDecodeError):
                pass
        job = self.jobs.submit("profiles", "컬럼 분석", self._profiles_job, p)
        return {"ready": False, "job": job.to_dict(False)}

    def _profiles_job(self, job, p: Project):
        s = p.settings
        y, mask, classes = p.encoded_target()
        out = {}
        cols = p.columns
        t0 = time.time()
        for i, c in enumerate(cols):
            if i % 2 == 0:
                left = ""
                if i > 2:
                    eta = (time.time() - t0) / i * (len(cols) - i)
                    left = f" · 약 {int(eta)}초 남음" if eta >= 1 else ""
                job.update(i / len(cols), f"컬럼 분석 중 {i + 1}/{len(cols)}: {c.name}{left}")
            is_target = c.name in s["target"]
            prof = profile_column(c.name, c.kind, c.discrete,
                                  p.train[c.name] if c.in_train else None,
                                  p.test[c.name] if (c.in_test and p.test is not None) else None,
                                  None if is_target else y, None if is_target else mask,
                                  s["task"], classes)
            prof["role"] = "target" if is_target else ("id" if c.name == s["id_col"] else "feature")
            prof["note"] = c.note
            out[c.name] = jsonable(prof)
        p.cache["profiles"] = out
        try:
            (p.dir / "cache").mkdir(parents=True, exist_ok=True)
            f = p.dir / "cache" / f"profiles-{self._profile_key(p)}.json"
            f.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return {"ok": True, "seconds": time.time() - t0}

    def _profiles(self, p: Project) -> dict:
        st = self.profiles_status()
        if not st["ready"]:
            raise LoadError("컬럼 분석이 아직 끝나지 않았습니다.")
        return p.cache["profiles"]

    def columns(self) -> dict:
        p = self.require()
        st = self.profiles_status()
        if not st["ready"]:
            return st
        prof = p.cache["profiles"]
        s = p.settings
        rows = []
        for c in p.columns:
            pr = prof.get(c.name) or {}
            tr = pr.get("train") or {}
            te = pr.get("test") or {}
            d = pr.get("drift") or {}
            pw = pr.get("power") or {}
            rows.append({
                "name": c.name, "kind": c.kind, "discrete": c.discrete, "dtype": c.dtype,
                "n_unique": c.n_unique, "in_train": c.in_train, "in_test": c.in_test,
                "missing_train": tr.get("missing_rate"), "missing_test": te.get("missing_rate"),
                "psi": d.get("psi"), "drift": d.get("level"), "unseen_rate": d.get("unseen_rate"),
                "drift_basis": d.get("level_basis", "psi"),
                "power": pw.get("power"), "power_metric": pw.get("metric"), "power_value": pw.get("value"),
                "role": pr.get("role", "feature"), "excluded": c.name in s["excluded"],
                "kind_overridden": c.name in s["kinds"], "note": c.note,
            })
        return {"ready": True, "columns": rows}

    def column(self, name: str) -> dict:
        p = self.require()
        prof = self._profiles(p)
        if name not in prof:
            raise LoadError(f"'{name}' 컬럼이 없습니다.")
        out = dict(prof[name])
        out["excluded"] = name in p.settings["excluded"]
        out["kind_overridden"] = name in p.settings["kinds"]
        c = p.column(name)
        out["dtype"] = c.dtype if c else None
        out["n_unique"] = c.n_unique if c else None
        out["in_train"], out["in_test"] = (c.in_train, c.in_test) if c else (False, False)
        # 값 예시
        ex = []
        if c and c.in_train:
            vals = p.train[name].dropna().head(400).drop_duplicates().head(8).tolist()
            ex = [(f"{v:.6g}" if isinstance(v, float) else as_label(v)) for v in vals]
        out["examples"] = ex
        return out

    # ═════════════════════════════════════════ 데이터 점검
    def checks(self) -> dict:
        p = self.require()
        if "checks" in p.cache:
            return {"ready": True, **p.cache["checks"]}
        st = self.profiles_status()
        if not st["ready"]:
            return st
        job = self.jobs.submit("checks", "데이터 점검", self._checks_job, p)
        return {"ready": False, "job": job.to_dict(False)}

    def _checks_job(self, job, p: Project):
        s = p.settings
        y, mask, classes = p.encoded_target()
        items = run_checks(p.train, p.test, p.sample, p.columns, s["target"], s["id_col"], s["task"],
                           y, mask, p.cache.get("profiles"), progress=job.update, excluded=s.get("excluded"))
        rec = recommend(s["task"], items, len(p.train), y)
        counts = {lv: sum(1 for it in items if it["level"] == lv) for lv in ("danger", "warn", "info", "ok")}
        p.cache["checks"] = jsonable({"items": items, "counts": counts, "recommend": rec})
        return {"ok": True}

    # ═════════════════════════════════════════ 적대적 검증
    def _adv_sig(self, p: Project) -> str:
        st = p.settings
        parts = [self._profile_key(p), json.dumps(st.get("excluded") or []), st.get("id_col") or ""]
        return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]

    def adversarial(self, exclude: list[str] | None = None, rerun: bool = False) -> dict:
        """exclude가 None이면 마지막 결과 조회, 목록이면 그 컬럼을 빼고 실행(같은 조건 결과가 있으면 재사용)."""
        p = self.require()
        if p.test is None:
            raise LoadError("test 파일이 있어야 train과 test를 비교할 수 있습니다.")
        if exclude is None:
            last = p.cache.get("adv:last")
            if last and last in p.cache:
                return {"ready": True, "result": p.cache[last], "exclude": p.cache.get("adv:last_ex", [])}
            saved = self._adv_load(p)  # 프로그램을 다시 켜도 마지막 결과를 보여 준다
            if saved:
                return {"ready": True, "result": saved["result"], "exclude": saved["exclude"]}
            job = self.jobs.get_running("adversarial")
            return {"ready": False, "job": job.to_dict(False) if job else None}
        exclude = sorted(set(exclude))
        key = "adv:" + ",".join(exclude)
        if key in p.cache and not rerun:
            p.cache["adv:last"], p.cache["adv:last_ex"] = key, exclude
            return {"ready": True, "result": p.cache[key], "exclude": exclude}
        job = self.jobs.submit("adversarial", "적대적 검증", self._adv_job, p, exclude, key, key=key)
        return {"ready": False, "job": job.to_dict(False)}

    def _adv_load(self, p: Project):
        f = p.dir / "cache" / "adversarial.json"
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if d.get("sig") != self._adv_sig(p):
            return None
        key = "adv:" + ",".join(d["exclude"])
        p.cache[key], p.cache["adv:last"], p.cache["adv:last_ex"] = d["result"], key, d["exclude"]
        return d

    def _adv_job(self, job, p: Project, exclude: list[str], key: str):
        cols = [c for c in p.feature_columns() if c.name not in set(exclude)]
        mat = build_matrix(p.train, p.test, cols)
        res = run_adversarial(mat, progress=job.update)
        scores = res.pop("_train_scores")
        try:
            p.dir.mkdir(exist_ok=True)
            df = pd.DataFrame({"row": np.arange(len(scores)), "test_likeness": scores})
            idc = p.settings["id_col"]
            if idc and idc in p.train.columns:
                df.insert(0, idc, p.train[idc].to_numpy())
            df.to_csv(p.dir / "test_likeness.csv", index=False, encoding="utf-8")
            res["scores_file"] = str(p.dir / "test_likeness.csv")
        except OSError:
            pass
        res = jsonable(res)
        p.cache[key] = res
        p.cache["adv:last"] = key
        p.cache["adv:last_ex"] = exclude
        try:
            (p.dir / "cache").mkdir(parents=True, exist_ok=True)
            (p.dir / "cache" / "adversarial.json").write_text(json.dumps(
                {"sig": self._adv_sig(p), "exclude": exclude, "result": res}, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        return {"ok": True}

    # ═════════════════════════════════════════ 검증 설계
    def cv_info(self) -> dict:
        p = self.require()
        chk = self.checks()
        if not chk.get("ready"):
            return chk
        s = p.settings
        rec = chk["recommend"]
        fold = p.load_folds()
        current = s.get("cv")
        out = {"ready": True, "recommend": rec, "current": current, "has_folds": fold is not None,
               "folds_path": str(p.folds_path()), "group_candidates": [], "time_columns": [],
               "strategies": STRATEGIES}
        from .analysis.checks import find_group_candidates
        out["group_candidates"] = find_group_candidates(p.train, p.test, p.feature_columns())
        out["time_columns"] = [c.name for c in p.columns if c.kind == "datetime" and c.in_train]
        out["all_columns"] = [c.name for c in p.columns if c.in_train and c.name not in s["target"]]
        n = len(p.train)
        out["groupable_columns"] = [
            c.name for c in p.columns
            if c.in_train and c.name not in s["target"] and c.name != s["id_col"]
            and c.kind in ("categorical", "numeric", "binary") and not (c.kind == "numeric" and not _int_like(p.train[c.name]))
            and 2 <= c.n_unique <= max(2, n // 2)]
        if fold is not None and current:
            y, mask, classes = p.encoded_target()
            out["summary"] = jsonable(fold_summary(p.train, fold, s["task"], y, classes,
                                                   current.get("group_col"), current.get("time_col")))
        out["snippet"] = _fold_snippet(p)
        return out

    def make_folds(self, params: dict) -> dict:
        p = self.require()
        s = p.settings
        strategy = params.get("strategy") or "kfold"
        if strategy not in STRATEGIES:
            raise LoadError("알 수 없는 검증 방법입니다.")
        try:
            n_splits = int(params.get("n_splits") or 5)
            seed = int(params.get("seed") if params.get("seed") not in (None, "") else 42)
        except (TypeError, ValueError):
            raise LoadError("폴드 수와 시드는 정수로 적으세요.")
        if not 2 <= n_splits <= 20:
            raise LoadError("폴드 수는 2~20 사이로 정하세요.")
        group_col = (params.get("group_col") or None) if strategy in ("group", "stratified_group") else None
        time_col = (params.get("time_col") or None) if strategy == "time" else None
        if strategy in ("group", "stratified_group") and not group_col:
            raise LoadError("그룹 컬럼을 고르세요.")
        if strategy == "time" and not time_col:
            raise LoadError("날짜 컬럼을 고르세요.")
        for c in (group_col, time_col):
            if c and c not in p.train.columns:
                raise LoadError(f"train에 '{c}' 컬럼이 없습니다.")
        y, mask, classes = p.encoded_target()
        fold = make_folds(p.train, strategy, n_splits, seed, y, mask, group_col, time_col)
        actual = len({int(k) for k in fold if k >= 0})
        if actual < 2:
            raise LoadError("폴드를 2개 이상 만들 수 없습니다. 날짜·그룹 종류가 너무 적은지 확인하세요.")
        notice = None
        if actual < n_splits:
            why = "날짜 종류" if strategy == "time" else "그룹 수" if group_col else "행 수"
            notice = f"{why}가 적어 폴드가 {n_splits}개가 아니라 {actual}개만 만들어졌습니다."
        path = p.save_folds(fold)
        s["cv"] = {"strategy": strategy, "n_splits": actual, "requested_splits": n_splits, "seed": seed,
                   "group_col": group_col, "time_col": time_col, "created_at": time.strftime("%Y-%m-%d %H:%M")}
        p.save_settings()
        return {"ok": True, "path": str(path), "notice": notice,
                "summary": jsonable(fold_summary(p.train, fold, s["task"], y, classes, group_col, time_col))}

    def baseline(self, params: dict) -> dict:
        p = self.require()
        if not p.target_col():
            raise LoadError("타깃 컬럼을 먼저 정하세요.")
        y, mask, _ = p.encoded_target()
        if y is None or mask.sum() == 0:
            raise LoadError("타깃 값이 모두 비어 있어 학습할 수 없습니다.")
        if len(np.unique(y[mask])) <= 1:
            raise LoadError("타깃 값이 하나뿐이라 학습할 수 없습니다. 개요에서 타깃이 맞는지 확인하세요.")
        params = {**(params or {}), "_lang": i18n.current()}
        job = self.jobs.submit("baseline", "기본 모델 교차검증", self._baseline_job, p, params,
                               key=json.dumps({k: v for k, v in params.items() if k != "_lang"}, sort_keys=True, default=str))
        return {"job": job.to_dict(False)}

    def _baseline_job(self, job, p: Project, params: dict):
        s = p.settings
        y, mask, classes = p.encoded_target()
        fold = p.load_folds()
        if fold is None or not s.get("cv"):
            job.update(0.01, "추천 검증 방법을 찾는 중")
            chk = p.cache.get("checks")
            if chk is None:
                self._profiles_job_if_needed(_SubProgress(job, 0.0, 0.3), p)
                self._checks_job(_SubProgress(job, 0.3, 0.38), p)
                chk = p.cache["checks"]
            rec = chk["recommend"]
            job.update(0.39, "추천 방법으로 폴드를 만드는 중")
            self._for(p).make_folds({"strategy": rec["strategy"], "n_splits": rec["n_splits"], "seed": 42,
                             "group_col": rec.get("group_col"), "time_col": rec.get("time_col")})
            fold = p.load_folds()
        lo = 0.4 if job.progress >= 0.39 else 0.05
        cv = s["cv"]
        exclude = set(params.get("exclude") or [])
        if cv.get("group_col") and params.get("drop_group", True):
            exclude.add(cv["group_col"])
        cols = [c for c in p.feature_columns() if c.name not in exclude]
        if not cols:
            raise LoadError("학습에 쓸 컬럼이 없습니다.")
        mat = build_matrix(p.train, p.test, cols)
        if not mat.features:
            raise LoadError("학습에 쓸 수 있는 컬럼이 없습니다 (모두 ID·상수이거나 한쪽 파일에만 있음).")
        engine = params.get("engine") or "auto"
        try:
            lr = float(params.get("learning_rate") or 0.05)
        except (TypeError, ValueError):
            raise LoadError("학습률은 숫자로 적으세요.")
        if not 0 < lr <= 1:
            raise LoadError("학습률은 0보다 크고 1 이하여야 합니다.")
        targets = list(s["target"])
        span = (0.92 - lo) / len(targets)
        per_target, primary = [], None
        for ti, t in enumerate(targets):
            if ti == 0:
                yt, mt, cl, task_t, metric_t = y, mask, classes, s["task"], s["metric"]
            else:
                from .analysis.common import encode_target
                tr0 = self._truth(p)
                if tr0["multi"]:  # 다중 타깃: 첫 타깃과 같은 과제·지표
                    task_t, cl = s["task"], tr0["classes_by_target"][ti]
                    yt, mt = tr0["y"][:, ti], np.isfinite(tr0["y"][:, ti])
                    if task_t == "binary":
                        _, mt, _ = encode_target(p.train[t], "binary", cl)
                    metric_t = s["metric"]
                else:
                    task_t = _guess_task(p.train[t])
                    cl = _classes(p.train[t]) if task_t != "regression" else []
                    yt, mt, cl = encode_target(p.train[t], task_t, cl)
                    metric_t = s["metric"] if (s["metric"] in M.METRICS and task_t in M.METRICS[s["metric"]].tasks) \
                        else M.DEFAULT_METRIC[task_t]
            if len(np.unique(yt[mt])) <= 1:
                raise LoadError(f"타깃 '{t}'의 값이 하나뿐이라 학습할 수 없습니다.")
            n_cls = len(cl) if task_t == "multiclass" else 2
            prefix = f"[{t}] " if len(targets) > 1 else ""
            res = run_baseline(mat, yt, mt, task_t, n_cls, fold, metric_t, cv["strategy"], engine=engine,
                               learning_rate=lr,
                               progress=lambda f, m, a=lo + ti * span: job.update(a + f * span, prefix + m))
            per_target.append({"target": t, "task": task_t, "classes": cl, "metric": metric_t, "res": res})
        primary = per_target[0]
        res = primary["res"]
        job.update(0.93, "결과 저장 중")
        tr = self._truth(p)
        multi = tr["multi"] and len(per_target) == len(tr["targets"])
        ids = p.train[s["id_col"]].to_numpy() if s["id_col"] in p.train.columns else None
        oof_arr = np.column_stack([pt["res"]["_oof"] for pt in per_target]) if multi else res["_oof"]
        oof = oof_frame(oof_arr, s["task"], classes, ids, fold, tr["targets"] if multi else None)
        test_df = sub = None
        sub_note = ""
        if res["_test"] is not None:
            tid = p.test[s["id_col"]].to_numpy() if (s["id_col"] and s["id_col"] in p.test.columns) else None
            test_arr = np.column_stack([pt["res"]["_test"] for pt in per_target]) if multi else res["_test"]
            test_df = oof_frame(test_arr, s["task"], classes, tid, targets=tr["targets"] if multi else None)
            if p.sample is not None:
                try:
                    if multi:
                        sub = make_submission_multi(test_arr, p.sample, p.test, s["id_col"], s["task"], tr["targets"],
                                                    tr["classes_by_target"], s["metric"])
                    else:
                        sub = make_submission(res["_test"], p.sample, p.test, s["id_col"], s["task"], classes,
                                              s["submission_format"], s["metric"])
                    for pt in ([] if multi else per_target[1:]):
                        if pt["target"] in p.sample.columns:
                            cols_ = [c for c in (s["id_col"], pt["target"]) if c and c in p.sample.columns]
                            st_ = make_submission(pt["res"]["_test"], p.sample[cols_], p.test, s["id_col"],
                                                  pt["task"], pt["classes"], "value", pt["metric"])
                            sub[pt["target"]] = st_[pt["target"]].to_numpy()
                except ValueError as ex:
                    sub, sub_note = None, f"제출 파일을 만들지 못했습니다: {ex}"
        n_prev = sum(1 for e in Ledger(p.dir).load() if e.get("source") == "baseline")
        name = (params.get("name") or "").strip() or (f"Baseline #{n_prev + 1}" if params.get("_lang") == "en"
                                                       else f"기본 모델 #{n_prev + 1}")
        notes = params.get("notes", "") or ""
        cv_value, cv_std = res["cv"], res["cv_std"]
        extra_params = {}
        if len(per_target) > 1:
            same_metric = len({pt["metric"] for pt in per_target}) == 1
            extra_params["cv_by_target"] = {pt["target"]: pt["res"]["cv"] for pt in per_target}
            if same_metric:
                cv_value = float(np.mean([pt["res"]["cv"] for pt in per_target]))
                cv_std = None
            notes = (notes + " " if notes else "") + (
                f"타깃 {len(per_target)}개를 따로 학습했습니다. CV는 타깃별 점수의 평균입니다."
                + ("" if multi else f" OOF(앙상블·흔들림 계산)는 첫 타깃 '{targets[0]}' 기준입니다."))
        e = Ledger(p.dir).add(
            name, s["metric"], cv_value, cv_std, jsonable(res["fold_scores"]), source="baseline",
            params={"engine": res["engine"], "learning_rate": lr, "n_features": res["n_features"],
                    "strategy": cv["strategy"], "n_splits": cv["n_splits"],
                    "excluded": sorted(exclude | set(s.get("excluded") or [])),
                    "mean_best_iteration": res["mean_best_iteration"], **extra_params},
            notes=notes, oof=oof, test_pred=test_df, submission=sub,
            extra={"importance": jsonable(res["importance"][:60])})
        out = {k: v for k, v in res.items() if not k.startswith("_")}
        out["cv"], out["cv_std"] = cv_value, cv_std
        out["experiment"] = e
        out["skipped"] = mat.skipped
        out["targets"] = [{"target": pt["target"], "cv": pt["res"]["cv"], "metric": pt["metric"]} for pt in per_target]
        out["notice"] = sub_note or None
        return jsonable(out)

    def _profiles_job_if_needed(self, job, p):
        if "profiles" not in p.cache:
            st = self._for(p).profiles_status()
            if not st["ready"]:
                self._profiles_job(job, p)

    # ═════════════════════════════════════════ 실험 대장
    def experiments(self) -> dict:
        p = self.require()
        s = p.settings
        led = self.ledger()
        exps = led.load()
        metric = s["metric"]
        hib = M.METRICS[metric].higher_is_better if metric in M.METRICS else True
        comp = s["competition"]
        exps = [self._rescore(p, led, e, metric) for e in exps]
        today = time.strftime("%Y-%m-%d")
        sub_today = sum(1 for e in exps if (e.get("submitted_at") or "").startswith(today))
        best = None
        for e in exps:
            if e.get("cv") is None or (e.get("metric") and e["metric"] != metric):
                continue
            if best is None or (e["cv"] > best["cv"] if hib else e["cv"] < best["cv"]):
                best = e
        rows = []
        for e in exps:
            r = {k: v for k, v in e.items() if k not in ("importance",)}
            r["has_oof"] = bool((e.get("files") or {}).get("oof"))
            r["has_test"] = bool((e.get("files") or {}).get("test"))
            r["has_submission"] = bool((e.get("files") or {}).get("submission"))
            r["metric_mismatch"] = bool(e.get("metric") and e["metric"] != metric)
            r["metric_label"] = (M.METRICS[e["metric"]].label if e.get("metric") in M.METRICS else e.get("metric"))
            rows.append(r)
        picks = int(comp.get("final_picks") or 2)
        return jsonable({
            "experiments": rows, "metric": metric, "higher_is_better": hib,
            "cv_lb": cv_lb_analysis([e for e in exps if not e.get("metric") or e["metric"] == metric], metric),
            "suggest": suggest_final([e for e in exps if not e.get("metric") or e["metric"] == metric],
                                     metric, picks),
            "best_cv_id": best["id"] if best else None,
            "submissions_today": sub_today, "daily_limit": comp.get("daily_limit"),
            "platform": comp.get("platform"), "final_picks": picks,
            "snippet": _log_snippet(p),
        })

    def _rescore(self, p: Project, led: Ledger, e: dict, metric: str) -> dict:
        """다른 지표로 기록된 실험은 OOF가 있으면 지금 지표로 다시 계산해 보여 준다 (원래 값은 cv_original)."""
        if not e.get("metric") or e["metric"] == metric or metric not in M.METRICS:
            return e
        if not (e.get("files") or {}).get("oof"):
            return e
        cache = p.cache.setdefault("rescore", {})
        key = (e["id"], metric)
        if key not in cache:
            try:
                o = led.read_oof(e)
                tr = self._truth(p)
                y, mask = tr["y"], tr["mask"]
                pred = self._pred(p, o)
                ok = mask & _valid(pred)
                cache[key] = float(M.score(metric, y[ok], pred[ok])) if ok.sum() > 1 else None
            except Exception:
                cache[key] = None
        val = cache[key]
        if val is None or not np.isfinite(val):
            return e
        e = dict(e)
        e.update({"cv_original": e.get("cv"), "metric_original": e["metric"], "cv": val, "cv_std": None,
                  "metric": metric, "rescored": True})
        return e

    def experiment_detail(self, exp_id: str) -> dict:
        e = self.ledger().get(exp_id)
        if e is None:
            raise LoadError("실험을 찾을 수 없습니다.")
        return jsonable(e)

    def add_experiment(self, data: dict) -> dict:
        p = self.require()
        name = (data.get("name") or "").strip()
        if not name:
            raise LoadError("실험 이름을 적어 주세요.")
        oof = test = sub = None
        info = {}
        if data.get("oof_path"):
            oof, info["oof"] = self._read_oof_file(p, data["oof_path"])
        if data.get("submission_path"):
            sub = read_table(data["submission_path"])
            test = self._sub_to_test_frame(p, sub)
        e = self.ledger().add(name, data.get("metric") or p.settings["metric"], data.get("cv"), data.get("cv_std"),
                              lb_public=data.get("lb_public"), lb_private=data.get("lb_private"),
                              notes=data.get("notes", ""), tags=data.get("tags") or [], source="manual",
                              oof=oof, test_pred=test, submission=sub)
        if oof is not None and e.get("cv") is None:
            tr = self._truth(p)
            y, mask = tr["y"], tr["mask"]
            pred = self._pred(p, oof)
            ok = mask & _valid(pred)
            try:
                cv = M.score(p.settings["metric"], y[ok], pred[ok])
                e = self.ledger().update(e["id"], cv=cv)
                info["cv_computed"] = True
            except Exception:
                pass
        return jsonable({"experiment": e, "info": info})

    def _read_oof_file(self, p: Project, path: str):
        """사용자 OOF 파일(csv/parquet)을 train 행 순서에 맞춘다. id 컬럼이나 행 순서로 맞춘다."""
        s = p.settings
        df = read_table(path)
        task = s["task"]
        classes = s["classes"]
        id_col = s["id_col"]
        n = len(p.train)
        # 예측 컬럼 고르기
        cand = [c for c in df.columns if c not in (id_col, "id", "row", "fold", "index", "Unnamed: 0")
                and c not in s["target"] and pd.api.types.is_numeric_dtype(df[c])]
        if task == "multiclass":
            want = [str(c) for c in classes]
            names = [c for c in df.columns if str(c) in want or str(c).replace("p_", "", 1) in want]
            if len(names) < len(classes):
                if len(cand) == len(classes):
                    names = cand
                else:
                    raise LoadError(f"다중분류 OOF에는 클래스별 확률 컬럼 {len(classes)}개가 필요합니다.")
            pred = df[names].to_numpy(dtype="float64")
        elif self._truth(p)["multi"]:
            targets = self._truth(p)["targets"]
            names = []
            for t in targets:
                hit = next((c for c in (f"pred:{t}", t, f"pred_{t}", f"{t}_pred") if c in df.columns), None)
                names.append(hit)
            if None in names:
                num = [c for c in df.columns if c not in (id_col, "id", "row", "fold", "index", "Unnamed: 0")
                       and pd.api.types.is_numeric_dtype(df[c])]
                if len(num) != len(targets):
                    raise LoadError(f"다중 타깃 OOF에는 타깃마다 예측 열이 필요합니다 ({', '.join(targets)}). "
                                    "열 이름을 타깃 이름으로 맞춰 주세요.")
                names = num
            pred = df[names].to_numpy(dtype="float64")
        else:
            if not cand:
                raise LoadError("OOF 파일에서 숫자 예측 컬럼을 찾지 못했습니다.")
            pick = "pred" if "pred" in cand else ("oof" if "oof" in cand else cand[-1])
            pred = df[pick].to_numpy(dtype="float64")
        how = "행 순서"
        key_col = id_col if id_col and id_col in df.columns else ("id" if "id" in df.columns else None)
        id_unique = bool(id_col and id_col in p.train.columns and p.train[id_col].is_unique)
        if key_col and id_unique and not ("row" in df.columns and not df[key_col].is_unique):
            k_tr = p.train[id_col].astype("string").to_numpy()
            k_df = df[key_col].astype("string").to_numpy()
            pos = pd.Series(np.arange(len(k_df)), index=k_df)
            if pos.index.has_duplicates:
                raise LoadError("OOF 파일에 중복된 ID가 있습니다.")
            idx = pos.reindex(k_tr).to_numpy()
            ok = ~pd.isna(idx)
            full = np.full((n, pred.shape[1]) if pred.ndim == 2 else n, np.nan)
            full[ok] = pred[idx[ok].astype(int)]
            pred = full
            how = f"ID '{key_col}'로 맞춤 ({int(ok.sum()):,}/{n:,}행)"
        elif "row" in df.columns:
            full = np.full((n, pred.shape[1]) if pred.ndim == 2 else n, np.nan)
            r = df["row"].to_numpy(dtype=int)
            if r.max() >= n:
                raise LoadError("OOF의 row 번호가 train 행 수보다 큽니다.")
            full[r] = pred
            pred = full
            how = "row 번호로 맞춤"
        elif len(df) != n:
            raise LoadError(f"OOF 행 수({len(df):,})가 train({n:,})과 다르고, 맞출 ID 컬럼도 없습니다.")
        fold = p.load_folds()
        ids = p.train[id_col].to_numpy() if id_col and id_col in p.train.columns else None
        return oof_frame(pred, task, classes, ids, fold, self._truth(p)["targets"]), how

    def _sub_to_test_frame(self, p: Project, sub: pd.DataFrame) -> pd.DataFrame | None:
        """제출 파일에서 앙상블용 test 예측을 뽑는다 (sample_submission 순서)."""
        s = p.settings
        id_col = s["id_col"]
        cols = [c for c in sub.columns if c != id_col and not str(c).startswith("Unnamed")]
        if not cols:
            return None
        if p.sample is not None and id_col and id_col in sub.columns and id_col in p.sample.columns:
            k_s = p.sample[id_col].astype("string").to_numpy()
            pos = pd.Series(np.arange(len(sub)), index=sub[id_col].astype("string").to_numpy())
            if pos.index.has_duplicates or set(k_s) - set(pos.index):
                return None
            sub = sub.iloc[pos.loc[k_s].to_numpy()].reset_index(drop=True)
        tr = self._truth(p)
        if s["task"] == "multiclass":
            if s["submission_format"] != "proba_columns":
                return None
            arr = sub[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype="float64")
        elif tr["multi"]:
            if not all(t in sub.columns for t in tr["targets"]):
                return None
            arr = sub[tr["targets"]].apply(pd.to_numeric, errors="coerce").to_numpy(dtype="float64")
            ids = sub[id_col].to_numpy() if id_col in sub.columns else None
            return oof_frame(arr, s["task"], s["classes"], ids, targets=tr["targets"])
        else:
            v = pd.to_numeric(sub[cols[0]], errors="coerce")
            if v.isna().all():
                return None
            arr = v.to_numpy(dtype="float64")
        ids = sub[id_col].to_numpy() if id_col in sub.columns else None
        return oof_frame(arr, s["task"], s["classes"], ids)

    def update_experiment(self, exp_id: str, fields: dict) -> dict:
        self.require()
        return jsonable({"experiment": self.ledger().update(exp_id, **fields)})

    def delete_experiment(self, exp_id: str) -> dict:
        self.require()
        self.ledger().delete(exp_id)
        return {"ok": True}

    def experiment_file(self, exp_id: str, kind: str) -> Path:
        led = self.ledger()
        e = led.get(exp_id)
        if e is None:
            raise LoadError("실험을 찾을 수 없습니다.")
        f = led.file_path(e, kind)
        if f is None or not f.exists():
            raise LoadError("파일이 없습니다.")
        return f

    def lb_noise(self, params: dict) -> dict:
        p = self.require()
        s = p.settings
        led = self.ledger()
        e = led.get(params.get("id", ""))
        if e is None:
            raise LoadError("실험을 찾을 수 없습니다.")
        oof = led.read_oof(e)
        if oof is None:
            raise LoadError("이 실험에는 OOF 예측이 없어 계산할 수 없습니다.")
        tr = self._truth(p)
        y, mask = tr["y"], tr["mask"]
        pred = self._pred(p, oof)
        ok = mask & _valid(pred)
        pred_b = None
        if params.get("id_b"):
            eb = led.get(params["id_b"])
            ob = led.read_oof(eb) if eb else None
            if ob is None:
                raise LoadError("비교할 실험에 OOF 예측이 없습니다.")
            pred_b = self._pred(p, ob)
            ok &= _valid(pred_b)
        n_test = len(p.test) if p.test is not None else len(p.train)
        share = s["competition"].get("public_share") or 0.3
        public_rows = int(params.get("public_rows") or round(n_test * float(share)))
        res = lb_noise(y[ok], pred[ok], s["metric"], public_rows,
                       pred_b=pred_b[ok] if pred_b is not None else None)
        res["public_share"] = share
        res["share_assumed"] = not s["competition"].get("public_share")
        res["targets"] = tr["targets"] if tr["multi"] else None
        return jsonable(res)

    def ensemble(self, params: dict) -> dict:
        p = self.require()
        job = self.jobs.submit("ensemble", "앙상블 가중치 찾기", self._ensemble_job, p, params)
        return {"job": job.to_dict(False)}

    def _ensemble_job(self, job, p: Project, params: dict):
        from .ensemble import run_ensemble
        s = p.settings
        led = Ledger(p.dir)
        ids = params.get("ids") or []
        exps = [led.get(i) for i in ids]
        exps = [e for e in exps if e is not None]
        if len(exps) < 2:
            raise LoadError("OOF가 있는 실험을 2개 이상 고르세요.")
        tr = self._truth(p)
        y, mask = tr["y"], tr["mask"]
        preds, names = [], []
        ok = mask.copy()
        for e in exps:
            o = led.read_oof(e)
            if o is None:
                raise LoadError(f"'{e['name']}'에는 OOF가 없습니다.")
            pr = self._pred(p, o)
            if tr["multi"] and np.isnan(pr).all(axis=0).any():
                raise LoadError(f"'{e['name']}'의 OOF에는 일부 타깃의 예측이 없습니다 (예전 버전에서 첫 타깃만 저장한 기록).")
            preds.append(pr)
            names.append(e["name"])
            ok &= _valid(pr)
        if ok.sum() < 20:
            raise LoadError("고른 실험들이 공통으로 가진 OOF 행이 너무 적습니다.")
        job.update(0.1, "가중치 찾는 중")
        fold = p.load_folds()
        fold_ok = None
        if fold is not None:
            fold_ok = fold[ok]
        use_rank = bool(params.get("use_rank")) and s["metric"] in ("auc", "macro_auc", "ap")
        res = run_ensemble(names, [pr[ok] for pr in preds], y[ok], s["metric"], fold_ok,
                           method=params.get("method") or "hill", use_rank=use_rank)
        res["rows_used"] = int(ok.sum())
        res["ids"] = [e["id"] for e in exps]
        if tr["multi"]:  # 타깃별 점수 (섞은 결과 기준)
            from .ensemble import blend_test
            bl = blend_test([pr[ok] for pr in preds], res["_weights"], use_rank)
            res["by_target"] = [{"target": t, "score": float(M.score(s["metric"], y[ok][:, j], bl[:, j]))}
                                for j, t in enumerate(tr["targets"])]
        res["has_all_tests"] = all((e.get("files") or {}).get("test") for e in exps)
        res["_weights"] = res["_weights"].tolist()
        p.cache["ensemble:last"] = res
        out = {k: v for k, v in res.items() if not k.startswith("_")}
        out["weights_raw"] = res["_weights"]
        return jsonable(out)

    def ensemble_save(self, params: dict) -> dict:
        from .ensemble import blend_test
        p = self.require()
        s = p.settings
        last = p.cache.get("ensemble:last")
        if not last:
            raise LoadError("먼저 앙상블을 실행하세요.")
        led = self.ledger()
        exps = [led.get(i) for i in last["ids"]]
        if any(e is None for e in exps):
            raise LoadError("앙상블에 쓴 실험 중 지워진 것이 있습니다. 다시 실행하세요.")
        w = np.asarray(last["_weights"], float)
        tr = self._truth(p)
        classes = tr["classes"]
        oofs = [self._pred(p, led.read_oof(e)) for e in exps]
        blend_oof = blend_test(oofs, w, last["use_rank"])
        ids = p.train[s["id_col"]].to_numpy() if s["id_col"] in p.train.columns else None
        oof_df = oof_frame(blend_oof, s["task"], classes, ids, p.load_folds(), tr["targets"])
        test_df = sub = None
        note = ""
        if last["has_all_tests"]:
            aligned, ref_ids, why = self._aligned_tests(p, led, exps)
            if aligned is None:
                note = why
            else:
                bt = blend_test(aligned, w, last["use_rank"])
                test_df = oof_frame(bt, s["task"], classes, ref_ids, targets=tr["targets"])
                if p.sample is not None and ref_ids is not None:
                    try:  # aligned는 sample_submission 순서
                        if tr["multi"]:
                            sub = make_submission_multi(bt, p.sample, None, s["id_col"], s["task"], tr["targets"],
                                                        tr["classes_by_target"], s["metric"])
                        else:
                            sub = make_submission(bt, p.sample, None, s["id_col"], s["task"], classes,
                                                  s["submission_format"], s["metric"])
                    except ValueError as ex:
                        note = f"제출 파일을 만들지 못했습니다: {ex}"
        cv = last["honest"]["score"] if last.get("honest") else last["score"]
        n_prev = sum(1 for e in led.load() if e.get("source") == "ensemble")
        used = [wt for wt in last["weights"] if wt["weight"] > 0]
        name = (params.get("name") or "").strip() or (
            f"Ensemble #{n_prev + 1} ({len(used)} models)" if i18n.current() == "en" else f"앙상블 #{n_prev + 1} ({len(used)}개 모델)")
        weights_txt = ", ".join(f"{wt['name']} {wt['weight']:.0%}" for wt in used)
        notes = (i18n.tr("CV는 폴드 교차로 잰 정직한 점수입니다. ") if last.get("honest") else "") + \
            i18n.tr(f"가중치: {weights_txt}") + (f" · {i18n.tr(note)}" if note else "")  # 요청 언어로 저장
        e = led.add(name[:120], s["metric"], cv, None, source="ensemble",
                    params={"weights": last["weights"], "use_rank": last["use_rank"], "method": last["method"],
                            "in_sample_score": last["score"]},
                    notes=notes, oof=oof_df, test_pred=test_df, submission=sub)
        return jsonable({"experiment": e, "has_submission": sub is not None, "notice": note or None})

    def _aligned_tests(self, p: Project, led: Ledger, exps: list[dict]):
        """실험마다 test 예측의 행 순서가 다를 수 있어(test 순서 / 제출 파일 순서) ID로 같은 순서에 맞춘다.
        반환: (예측 배열 목록, 기준 ID, 실패 이유)"""
        s = p.settings
        id_col = s["id_col"]
        frames = [led.read_test(e) for e in exps]
        if p.sample is not None and id_col and id_col in p.sample.columns:
            ref = p.sample[id_col]
        elif p.test is not None and id_col and id_col in p.test.columns:
            ref = p.test[id_col]
        else:
            ref = None
        if ref is not None and all("id" in f.columns for f in frames):
            key = ref.astype("string").str.strip().to_numpy()
            out = []
            for e, f in zip(exps, frames):
                pos = pd.Series(np.arange(len(f)), index=f["id"].astype("string").str.strip().to_numpy())
                if pos.index.has_duplicates:
                    return None, None, f"'{e['name']}'의 test 예측에 중복 ID가 있어 섞을 수 없습니다."
                missing = set(key) - set(pos.index)
                if missing:
                    return None, None, f"'{e['name']}'의 test 예측에 없는 ID가 {len(missing):,}개 있어 제출 파일을 만들지 않았습니다."
                out.append(self._pred(p, f.iloc[pos.loc[key].to_numpy()]))
            return out, ref.to_numpy(), ""
        preds = [self._pred(p, f) for f in frames]
        if len({pr.shape for pr in preds}) == 1:
            return preds, None, "ID가 없어 행 순서가 같다고 보고 섞었습니다. 제출 파일은 만들지 않았습니다."
        return None, None, "실험마다 test 예측 행 수가 달라 섞을 수 없습니다."

    def kaggle_import(self, params: dict) -> dict:
        """Kaggle 공식 CLI로 제출 기록(Public/Private 점수)을 가져와 실험에 붙인다."""
        import shutil
        import subprocess
        from io import StringIO
        p = self.require()
        comp = p.settings["competition"]
        slug = (params.get("slug") or comp.get("slug") or "").strip()
        if not slug and comp.get("url"):
            parts = [x for x in str(comp["url"]).split("/") if x]
            if "competitions" in parts and parts.index("competitions") + 1 < len(parts):
                slug = parts[parts.index("competitions") + 1]
        if not slug:
            raise LoadError("설정에서 Kaggle 대회 주소(예: https://www.kaggle.com/competitions/titanic)를 먼저 적어 주세요.")
        exe = shutil.which("kaggle")
        if exe is None:
            scripts = Path(sys.executable).parent / ("Scripts" if sys.platform == "win32" else "")
            cand = scripts / ("kaggle.exe" if sys.platform == "win32" else "kaggle")
            exe = str(cand) if cand.exists() else None
        if exe is None:
            raise LoadError("Kaggle CLI를 찾지 못했습니다. 'pip install kaggle' 후 API 토큰을 설정하세요.")
        try:
            r = subprocess.run([exe, "competitions", "submissions", slug, "-v", "--page-size", "200"],
                               capture_output=True, text=True, timeout=90, encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired:
            raise LoadError("Kaggle 응답이 90초 안에 오지 않았습니다. 잠시 후 다시 해 보세요.")
        out = (r.stdout or "").strip()
        lines = out.splitlines()

        def is_header(ln: str) -> bool:
            fields = {f.strip().strip('"').lower().replace("_", "") for f in ln.split(",")}
            return "date" in fields and ("filename" in fields or "publicscore" in fields)
        start = next((i for i, ln in enumerate(lines) if is_header(ln)), None)
        if r.returncode != 0 or start is None:
            low = ((r.stderr or "") + out).lower()
            if "kaggle.json" in low or "could not find" in low or "401" in low or "unauthorized" in low or "credentials" in low:
                raise LoadError("Kaggle API 토큰을 찾지 못했습니다. kaggle.com 계정 설정에서 API 토큰을 받아 "
                                f"{Path.home() / '.kaggle' / 'kaggle.json'}에 두거나, KAGGLE_USERNAME·KAGGLE_KEY 환경 변수를 설정하세요.")
            if "403" in low or "forbidden" in low:
                raise LoadError("Kaggle이 거부했습니다. 대회 규칙에 동의했는지, 대회 주소가 맞는지 확인하세요.")
            if "404" in low or "not found" in low:
                raise LoadError(f"Kaggle에서 대회 '{slug}'를 찾지 못했습니다. 설정의 대회 주소를 확인하세요.")
            if start is None and r.returncode == 0:
                if "no submissions" in low or not out:
                    return {"ok": True, "matched": 0, "created": 0, "skipped": 0, "total": 0}
                raise LoadError("Kaggle CLI 출력 형식을 알아보지 못했습니다. Kaggle CLI를 최신으로 업데이트해 보세요.")
            last = ((r.stderr or out or "").strip().splitlines() or ["알 수 없는 오류"])[-1]
            raise LoadError(f"Kaggle CLI가 실패했습니다: {last[:300]}")
        df = pd.read_csv(StringIO(chr(10).join(lines[start:])))
        cols = {c.lower().replace("_", ""): c for c in df.columns}

        def col(*names):
            for n in names:
                if n in cols:
                    return cols[n]
            return None
        c_file, c_date, c_desc = col("filename"), col("date"), col("description")
        c_status, c_pub, c_priv = col("status"), col("publicscore"), col("privatescore")
        if c_date is None or c_pub is None:
            raise LoadError("Kaggle CLI 출력 형식을 알아보지 못했습니다.")
        led = self.ledger()
        exps = led.load()
        by_key = {e.get("kaggle_key"): e for e in exps if e.get("kaggle_key")}
        matched, created, skipped = 0, 0, 0
        for _, r_ in df.iterrows():
            status = str(r_.get(c_status, "")).lower() if c_status else "complete"
            pub = pd.to_numeric(r_.get(c_pub), errors="coerce")
            priv = pd.to_numeric(r_.get(c_priv), errors="coerce") if c_priv else np.nan
            if "error" in status or pd.isna(pub):
                skipped += 1
                continue
            fname = str(r_.get(c_file, "") or "") if c_file else ""
            desc = str(r_.get(c_desc, "") or "") if c_desc else ""
            date = str(r_.get(c_date, ""))
            key = f"{date}|{fname}"
            target = by_key.get(key)
            if target is None:
                for e in exps:
                    if e.get("kaggle_key"):
                        continue
                    if e["id"] in fname or e["id"] in desc or (e["name"] and len(e["name"]) >= 3 and e["name"] in desc):
                        target = e
                        break
            fields = {"lb_public": float(pub), "kaggle_key": key, "submitted_at": _local_time(date)}
            if pd.notna(priv):
                fields["lb_private"] = float(priv)
            if target is not None:
                led.update(target["id"], **fields)
                target["kaggle_key"] = key
                matched += 1
            else:
                e = led.add(desc or fname or "Kaggle 제출", p.settings["metric"], None, lb_public=float(pub),
                            lb_private=float(priv) if pd.notna(priv) else None, source="kaggle",
                            notes=f"Kaggle 제출 파일: {fname}", submitted_at=fields["submitted_at"],
                            extra={"kaggle_key": key})
                exps.append(e)
                created += 1
        comp["slug"] = slug
        p.save_settings()
        return {"ok": True, "matched": matched, "created": created, "skipped": skipped, "total": len(df)}

    def report(self, params: dict) -> dict:
        from .htmlreport import build_report
        p = self.require()
        out = Path(params.get("path") or (p.dir / f"report-{time.strftime('%Y%m%d-%H%M')}.html"))
        pinned = self._for(p)
        lang = i18n.current()
        job = self.jobs.submit("report", "보고서 만들기", lambda job: build_report(pinned, out, job, lang=lang),
                               project=str(p.root))
        return {"job": job.to_dict(False)}

    # ═════════════════════════════════════════ 제출 파일
    def submission_check(self, path: str, exp: str | None = None) -> dict:
        p = self.require()
        s = p.settings
        if exp:
            path = str(self.experiment_file(exp, "submission"))
        if not path or not Path(path).exists():
            raise LoadError(f"파일이 없습니다: {path}")
        sub = _read_sub(path)
        t = p.target_col()
        res = check_submission(sub, p.sample, s["id_col"], s["task"], s["metric"], s["classes"],
                               s["submission_format"], p.train[t] if t else None)
        enc_item = _encoding_item(path)
        if enc_item:
            res["items"].append(enc_item)
        res["preview"] = {"columns": [str(c) for c in sub.columns],
                          "rows": [[as_label(v) for v in r] for r in sub.head(8).itertuples(index=False)]}
        if p.sample is None:
            res["items"].insert(0, {"level": "info", "title": "sample_submission이 없어 형식 비교는 못 했습니다",
                                    "detail": "설정에서 sample_submission 파일을 지정하면 더 꼼꼼히 봅니다.",
                                    "fixable": False})
        res["path"] = path
        return jsonable(res)

    def submission_fix(self, path: str, out_path: str | None = None) -> dict:
        p = self.require()
        s = p.settings
        if p.sample is None:
            raise LoadError("sample_submission이 있어야 고칠 수 있습니다.")
        sub = _read_sub(path)
        t = p.target_col()
        fixed, done = fix_submission(sub, p.sample, s["id_col"], s["task"], s["submission_format"],
                                     p.train[t] if t else None)
        if _encoding_item(path):
            done.append("UTF-8(BOM 없음)로 다시 저장")
        if not done:
            return {"ok": True, "done": [], "path": None}
        src = Path(path)
        out = Path(out_path) if out_path else src.with_name(src.stem + "_fixed" + ".csv")
        if out.resolve() == src.resolve():
            raise LoadError("원본 파일을 덮어쓰지 않습니다. 다른 이름을 고르세요.")
        fixed.to_csv(out, index=False, encoding="utf-8")
        return {"ok": True, "done": done, "path": str(out)}

    def submission_compare(self, a: str, b: str) -> dict:
        p = self.require()
        s = p.settings
        da, db = _read_sub(a), _read_sub(b)
        id_col = s["id_col"] if s["id_col"] in da.columns and s["id_col"] in db.columns else None
        cols = [c for c in da.columns if c in db.columns and c != id_col and not str(c).startswith("Unnamed")]
        if not cols:
            raise LoadError("두 파일에 공통 예측 컬럼이 없습니다.")
        return jsonable(compare_submissions(da, db, id_col, cols))

    # ═════════════════════════════════════════ 관계·그래프·표
    def correlation(self, method: str = "spearman", limit: int = 30) -> dict:
        p = self.require()
        prof = p.cache.get("profiles") or {}
        feats = [c for c in p.feature_columns() if c.in_train and c.kind in ("numeric", "binary", "datetime")]
        feats.sort(key=lambda c: -(((prof.get(c.name) or {}).get("power") or {}).get("power") or 0.0))
        feats = feats[:limit]
        if len(feats) < 2:
            return {"names": [], "matrix": [], "pairs": []}
        idx = sample_index(len(p.train), 30_000, 0)
        cols = {}
        for c in feats:
            s = p.train[c.name].iloc[idx]
            if c.kind == "datetime":
                s = to_datetime_safe(s)
            elif c.kind == "binary" and not pd.api.types.is_numeric_dtype(s):
                s = pd.Series(pd.factorize(s)[0], dtype="float64").where(s.notna().to_numpy())
            cols[c.name] = to_float(s) if not isinstance(s, np.ndarray) else s
        df = pd.DataFrame(cols)
        t = p.target_col()
        if t and p.settings["task"] != "multiclass":
            y, mask, _ = p.encoded_target()
            df["__target__"] = np.where(mask[idx], y[idx], np.nan)
        m = df.corr(method="spearman" if method != "pearson" else "pearson")
        names = list(m.columns)
        pairs = []
        mv = m.to_numpy()
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                if names[i] == "__target__" or names[j] == "__target__":
                    continue
                if np.isfinite(mv[i, j]) and abs(mv[i, j]) >= 0.8:
                    pairs.append({"a": names[i], "b": names[j], "r": float(mv[i, j])})
        pairs.sort(key=lambda d: -abs(d["r"]))
        names = [("타깃: " + t) if n == "__target__" else n for n in names]
        return jsonable({"names": names, "matrix": np.round(np.nan_to_num(mv, nan=0.0), 3).tolist(),
                         "pairs": pairs[:30], "method": method, "rows": len(idx)})

    def explore(self, params: dict) -> dict:
        """그래프 만들기: x(필수), y(선택), color(선택: 'target' 또는 컬럼). 표본만 보낸다."""
        p = self.require()
        x, ycol, color = params.get("x"), params.get("y") or None, params.get("color") or None
        which = params.get("which") or "train"
        df = p.train if which == "train" else p.test
        if df is None:
            raise LoadError("test 파일이 없습니다.")
        for c in (x, ycol):
            if c and c not in df.columns:
                raise LoadError(f"'{c}' 컬럼이 {which}에 없습니다.")
        cx = p.column(x)
        if cx is None:
            raise LoadError("x 컬럼을 고르세요.")
        cy = p.column(ycol) if ycol else None
        t = p.target_col()
        col_series = None
        if color == "target" and t and which == "train":
            col_series, color_name = p.train[t], t
        elif color and color in df.columns:
            col_series, color_name = df[color], color
        else:
            color_name = None
        n = len(df)
        idx = sample_index(n, int(params.get("max_points") or 4000), 1)
        num_kinds = ("numeric", "datetime")

        def vals(c, info):
            s = df[c].iloc[idx]
            if info.kind == "text":
                return s.astype("string").str.len().astype("float64").to_numpy(), False
            if info.kind == "datetime":
                return to_float(to_datetime_safe(s)), True
            if info.kind == "numeric" or (info.kind == "binary" and pd.api.types.is_numeric_dtype(s)):
                return to_float(s), False
            return None, False

        groups = None
        if col_series is not None:
            g = col_series.iloc[idx]
            cinfo = p.column(color_name)
            if cinfo and cinfo.kind in num_kinds and g.nunique() > 12:
                q = pd.qcut(to_float(g), 5, duplicates="drop")
                groups = pd.Series(q).astype(str).replace("nan", "(결측)").to_numpy()
            else:
                top = g.value_counts().index[:10]
                groups = np.where(g.isin(top), g.map(as_label), "(기타)")
                groups = np.where(g.isna(), "(결측)", groups)

        if cy is not None:
            xv, xdate = vals(x, cx)
            yv, ydate = vals(ycol, cy)
            if xv is not None and yv is not None:
                pts = [[float(a), float(b)] for a, b in zip(xv, yv) if np.isfinite(a) and np.isfinite(b)]
                gl = None
                if groups is not None:
                    keep = np.isfinite(xv) & np.isfinite(yv)
                    gl = [str(gg) for gg in groups[keep]]
                return jsonable({"type": "scatter", "x": x, "y": ycol, "points": pts, "groups": gl,
                                 "color": color_name, "x_date": xdate, "y_date": ydate, "sampled": len(idx) < n,
                                 "n": n})
            note = None
            if xv is not None and yv is None:  # x 숫자, y 범주 → 축을 바꿔 상자 그림
                x, ycol, xv, yv, ydate = ycol, x, None, xv, xdate
                note = "숫자를 세로축에 두고 범주별 상자 그림으로 그렸습니다."
            if yv is not None:  # x 범주, y 숫자 → 상자 그림
                cat = df[x].iloc[idx]
                top = cat.value_counts().index[:20]
                boxes = []
                for k in top:
                    v = yv[(cat == k).to_numpy()]
                    v = v[np.isfinite(v)]
                    if v.size:
                        q = np.quantile(v, [0, 0.25, 0.5, 0.75, 1])
                        iqr = q[3] - q[1]
                        lo, hi = max(q[0], q[1] - 1.5 * iqr), min(q[4], q[3] + 1.5 * iqr)
                        boxes.append({"label": as_label(k), "stats": [float(lo), float(q[1]), float(q[2]),
                                                                       float(q[3]), float(hi)], "n": int(v.size)})
                return jsonable({"type": "box", "x": x, "y": ycol, "boxes": boxes, "y_date": ydate,
                                 "sampled": len(idx) < n, "n": n, "note": note})
            # 둘 다 범주 → 교차표
            a, b = df[x].iloc[idx], df[ycol].iloc[idx]
            ta, tb = a.value_counts().index[:15], b.value_counts().index[:10]
            ct = pd.crosstab(a.where(a.isin(ta)), b.where(b.isin(tb)))
            return jsonable({"type": "heat", "x": x, "y": ycol, "xs": [as_label(v) for v in ct.index],
                             "ys": [as_label(v) for v in ct.columns], "values": ct.to_numpy().tolist(),
                             "sampled": len(idx) < n, "n": n})
        # y 없음: 분포 (색 그룹별)
        xv, xdate = vals(x, cx)
        if xv is not None:
            f = xv[np.isfinite(xv)]
            if f.size == 0:
                raise LoadError("값이 모두 비어 있습니다.")
            lo, hi = np.quantile(f, [0.005, 0.995]) if not xdate else (f.min(), f.max())
            if lo == hi:
                lo, hi = f.min(), f.max() + (1 if f.max() == f.min() else 0)
            edges = np.linspace(lo, hi, 31)
            series = []
            labels = ["전체"] if groups is None else list(pd.Series(groups).value_counts().index[:10])
            for lab in labels:
                sel = np.isfinite(xv) if groups is None else (np.isfinite(xv) & (groups == lab))
                c, _ = np.histogram(np.clip(xv[sel], lo, hi), edges)
                series.append({"name": str(lab), "counts": c.tolist()})
            return jsonable({"type": "hist", "x": x, "edges": edges.tolist(), "series": series, "x_date": xdate,
                             "color": color_name, "sampled": len(idx) < n, "n": n})
        cat = df[x].iloc[idx]
        top = list(cat.value_counts(dropna=False).index[:25])
        cats = [as_label(k) for k in top]
        series = []
        labels = ["전체"] if groups is None else list(pd.Series(groups).value_counts().index[:10])
        for lab in labels:
            sel = np.ones(len(cat), bool) if groups is None else (groups == lab)
            vc = cat[sel].value_counts(dropna=False)
            series.append({"name": str(lab), "counts": [int(vc.get(k, 0)) for k in top]})
        return jsonable({"type": "bar", "x": x, "categories": cats, "series": series, "color": color_name,
                         "sampled": len(idx) < n, "n": n})

    def rows(self, params: dict) -> dict:
        p = self.require()
        which = params.get("which") or "train"
        df = {"train": p.train, "test": p.test, "sample_submission": p.sample}.get(which)
        if df is None:
            raise LoadError(f"{which} 데이터가 없습니다.")
        view = df
        for f in params.get("filters") or []:
            view = _apply_filter(view, f)
        sort = params.get("sort")
        if sort and sort in view.columns:
            view = view.sort_values(sort, ascending=bool(params.get("asc", True)), na_position="last", kind="stable")
        try:
            offset = max(0, int(params.get("offset") or 0))
            limit = min(500, max(1, int(params.get("limit") or 100)))
        except (TypeError, ValueError):
            raise LoadError("offset·limit은 정수여야 합니다.")
        page = view.iloc[offset: offset + limit]
        return {"columns": [str(c) for c in view.columns], "total": int(len(df)), "matched": int(len(view)),
                "offset": offset,
                "index": [int(i) for i in page.index],
                "rows": [[_cell(v) for v in r] for r in page.itertuples(index=False)]}

    # ═════════════════════════════════════════ 데이터 표
    def _sheet_frame(self, p: Project, which: str, exp_id: str | None):
        """표로 볼 데이터와 덧붙인 열 이름. train에는 실험의 OOF 예측·오차 열을 붙일 수 있다."""
        df = {"train": p.train, "test": p.test, "sample_submission": p.sample}.get(which)
        if df is None:
            raise LoadError(f"{which} 데이터가 없습니다.")
        if not (isinstance(df.index, pd.RangeIndex) and df.index.start == 0 and df.index.step == 1):
            df = df.reset_index(drop=True)
        if not exp_id or which != "train":
            return df, []
        key = f"sheet:aug:{exp_id}"
        if key not in p.cache:
            for k in [k for k in p.cache if k.startswith("sheet:aug:")]:
                del p.cache[k]  # 큰 표 사본은 하나만 들고 있는다
            p.cache[key] = self._with_prediction(p, df, exp_id)
        return p.cache[key]

    def _with_prediction(self, p: Project, df: pd.DataFrame, exp_id: str):
        led = self.ledger()
        e = led.get(exp_id)
        if e is None:
            raise LoadError("실험을 찾을 수 없습니다.")
        o = led.read_oof(e)
        if o is None:
            raise LoadError("이 실험에는 OOF 예측이 없습니다.")
        s = p.settings
        task = s["task"]
        truth = self._truth(p)
        pred = self._pred(p, o)
        y, mask = truth["y"], truth["mask"]
        if len(pred) != len(df):
            raise LoadError("OOF 행 수가 train과 달라 붙일 수 없습니다.")
        add: dict[str, object] = {}
        if task == "multiclass":
            cls = np.asarray(truth["classes"], dtype=object)
            ok = ~np.isnan(pred).any(axis=1)
            top = np.nan_to_num(pred, nan=-1.0).argmax(axis=1)
            add["예측"] = pd.Series(np.where(ok, cls[top] if len(cls) else top, None), dtype="object")
            p_true = np.full(len(df), np.nan)
            v = ok & mask
            p_true[v] = pred[v, y[v].astype(int)]
            add["정답 확률"] = p_true
            add["오차"] = 1.0 - p_true
        else:
            targets = truth["targets"]
            P2 = pred if pred.ndim == 2 else pred[:, None]
            Y2 = y if y.ndim == 2 else y[:, None]
            for j, t in enumerate(targets):
                sfx = f" · {t}" if len(targets) > 1 else ""
                pj = P2[:, j]
                add["예측" + sfx] = pj
                err = np.full(len(df), np.nan)
                v = mask & ~np.isnan(pj)
                if task == "regression":
                    err[v] = pj[v] - Y2[v, j]
                    add["오차" + sfx] = err
                    add["|오차|" + sfx] = np.abs(err)
                else:
                    err[v] = np.abs(Y2[v, j] - pj[v])
                    add["오차" + sfx] = err
        names = []
        extra = {}
        for k, v in add.items():
            name = f"{k} ({e['name']})"
            while name in df.columns or name in extra:
                name += "'"
            extra[name] = v
            names.append(name)
        aug = pd.concat([df, pd.DataFrame(extra, index=df.index)], axis=1)
        return aug, names

    def _sheet_view(self, p: Project, params: dict):
        which = params.get("which") or "train"
        exp_id = params.get("exp") or None
        df, extra = self._sheet_frame(p, which, exp_id)
        filters = params.get("filters") or []
        search = str(params.get("search") or "").strip()
        sort = params.get("sort")
        asc = bool(params.get("asc", True))
        key = json.dumps([which, exp_id, filters, search, sort, asc], ensure_ascii=False, sort_keys=True, default=str)
        cached = p.cache.get("sheet:view")
        if not cached or cached[0] != key:
            view = df
            for f in filters:
                view = _apply_filter(view, f)
            if search:
                view = view[_search_mask(view, search)]
            if sort and sort in view.columns:
                view = view.sort_values(sort, ascending=asc, na_position="last", kind="stable")
            cached = (key, view.index.to_numpy())
            p.cache["sheet:view"] = cached
        return df, extra, cached[1], which

    def sheet(self, params: dict) -> dict:
        """데이터 표: 필터·검색·정렬한 결과에서 offset부터 limit행. 스크롤하면 필요한 구간만 다시 부른다."""
        p = self.require()
        df, extra, order, which = self._sheet_view(p, params)
        try:
            offset = max(0, int(params.get("offset") or 0))
            limit = min(500, max(1, int(params.get("limit") or 200)))
        except (TypeError, ValueError):
            raise LoadError("offset·limit은 정수여야 합니다.")
        idx = order[offset: offset + limit]
        page = df.iloc[idx]
        cols = []
        for c in df.columns:
            ci = p.column(str(c))
            cols.append({"name": str(c), "kind": ci.kind if ci else ("pred" if c in extra else "other"),
                         "numeric": bool(pd.api.types.is_numeric_dtype(df[c]) and not pd.api.types.is_bool_dtype(df[c])),
                         "extra": c in extra,
                         "role": "target" if c in p.settings["target"] else ("id" if c == p.settings["id_col"] else None)})
        return {"which": which, "columns": cols, "total": int(len(df)), "matched": int(len(order)), "offset": offset,
                "positions": [int(i) for i in idx],
                "rows": [[_cell(v) for v in r] for r in page.itertuples(index=False)]}

    def sheet_export(self, params: dict) -> dict:
        """지금 표에 보이는 결과(필터·정렬·보이는 열)를 CSV로 저장한다. 엑셀에서 한글이 깨지지 않게 BOM을 붙인다."""
        p = self.require()
        df, _, order, which = self._sheet_view(p, params)
        cols = [c for c in (params.get("columns") or []) if c in df.columns] or list(df.columns)
        out_dir = p.dir / "exports"
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{which}-{time.strftime('%Y%m%d-%H%M%S')}.csv"
        df.iloc[order][cols].to_csv(path, index=False, encoding="utf-8-sig")
        return {"path": str(path), "rows": int(len(order)), "columns": len(cols)}


# ═════════════════════════════════════════ 도우미
def _valid(pred: np.ndarray) -> np.ndarray:
    """예측이 있는 행 (2차원이면 모든 열이 있는 행)"""
    return ~np.isnan(pred).any(axis=1) if pred.ndim == 2 else ~np.isnan(pred)


def _search_mask(df: pd.DataFrame, text: str) -> np.ndarray:
    """모든 열에서 찾기: 글자 열은 포함, 숫자 열은 같은 값."""
    out = np.zeros(len(df), dtype=bool)
    try:
        num = float(text.replace(",", ""))
    except ValueError:
        num = None
    for c in df.columns:
        col = df[c]
        if pd.api.types.is_numeric_dtype(col) and not pd.api.types.is_bool_dtype(col):
            if num is not None:
                out |= (col.to_numpy(dtype="float64", na_value=np.nan) == num)
        else:
            out |= col.astype("string").str.contains(text, case=False, regex=False, na=False).to_numpy(dtype=bool)
    return out


class _SubProgress:
    """안쪽 작업의 진행률(0~1)을 바깥 작업의 일부 구간으로 바꿔 진행률이 뒤로 가지 않게 한다."""

    def __init__(self, job, lo: float, hi: float):
        self.job, self.lo, self.hi = job, lo, hi
        self.progress = lo

    def update(self, frac, msg=None):
        self.progress = self.lo + (self.hi - self.lo) * float(frac)
        self.job.update(self.progress, msg)


def _int_like(s: pd.Series) -> bool:
    from .schema import integer_valued
    return pd.api.types.is_integer_dtype(s) or integer_valued(s.dropna().head(100_000))


def _local_time(text: str) -> str | None:
    """Kaggle이 주는 UTC 시각을 이 컴퓨터의 현지 시각 문자열로"""
    ts = pd.to_datetime(text, errors="coerce", utc=True)
    if pd.isna(ts):
        return None
    return ts.to_pydatetime().astimezone().strftime("%Y-%m-%dT%H:%M:%S")


def _metric_info(key):
    if key in M.METRICS:
        m = M.METRICS[key]
        return {"key": m.key, "label": m.label, "higher_is_better": m.higher_is_better, "needs": m.needs}
    return None


def _guess_task(y: pd.Series) -> str:
    from .schema import infer_kind, integer_valued
    k = infer_kind(y.dropna(), str(y.name))[0]
    if k == "binary":
        return "binary"
    if k == "categorical" or (k == "numeric" and integer_valued(y.dropna()) and y.nunique() <= 10):
        return "multiclass"
    return "regression"


def _classes(y: pd.Series) -> list:
    from .schema import plain
    return sorted((plain(v) for v in pd.unique(y.dropna())), key=lambda v: (str(type(v)), v))


def _test_like(p: Project, tid):
    """블렌딩된 test 예측의 행 순서를 맞추기 위한 가짜 test 표 (ID만)."""
    id_col = p.settings["id_col"]
    if tid is None or not id_col:
        return p.test
    return pd.DataFrame({id_col: tid})


def _read_sub(path: str) -> pd.DataFrame:
    """제출 파일 읽기: 앞자리 0이 있는 ID는 문자열로 보존 (io.read_table과 같은 규칙)."""
    pth = Path(path)
    if not pth.exists():
        raise LoadError(f"파일이 없습니다: {path}")
    return read_table(pth)


def _encoding_item(path: str):
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
    except OSError:
        return None
    if head.startswith(b"\xef\xbb\xbf"):
        return {"level": "info", "title": "파일이 UTF-8 BOM으로 저장돼 있습니다",
                "detail": "대부분 문제없지만, 첫 컬럼 이름 앞에 보이지 않는 문자가 붙어 오류가 나는 대회도 있습니다. "
                          "encoding='utf-8'로 다시 저장하면 안전합니다.", "fixable": True}
    try:
        head.decode("utf-8")
    except UnicodeDecodeError:
        return {"level": "warn", "title": "UTF-8이 아닌 인코딩(cp949 등)으로 저장돼 있습니다",
                "detail": "한글이 들어 있으면 채점 서버에서 깨질 수 있습니다. 고친 파일 저장을 누르면 UTF-8로 저장합니다.",
                "fixable": True}
    return None


def _apply_filter(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    col, op, val = f.get("col"), f.get("op"), f.get("value")
    if col not in df.columns:
        return df
    s = df[col]
    if op == "isnull":
        return df[s.isna()]
    if op == "notnull":
        return df[s.notna()]
    if op == "contains":
        return df[s.astype("string").str.contains(str(val), case=False, regex=False, na=False)]
    if pd.api.types.is_numeric_dtype(s) and op in ("==", "!=", ">", ">=", "<", "<="):
        try:
            v = float(val)
        except (TypeError, ValueError):
            raise LoadError(f"'{col}'은 숫자 컬럼이라 숫자로 비교해야 합니다.")
    else:
        v = str(val)
        s = s.astype("string")
    ops = {"==": s == v, "!=": s != v, ">": s > v, ">=": s >= v, "<": s < v, "<=": s <= v}
    if op not in ops:
        return df
    return df[ops[op].fillna(False).to_numpy(dtype=bool)]


def _cell(v):
    if v is None:
        return None
    if isinstance(v, float):
        return None if not np.isfinite(v) else v
    if isinstance(v, (np.floating,)):
        f = float(v)
        return None if not np.isfinite(f) else f
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (int, str)):
        return v if not isinstance(v, str) or len(v) < 300 else v[:300] + "…"
    return str(v)


def _fold_snippet(p: Project) -> str:
    path = str(p.folds_path()).replace("\\", "/")
    id_col = p.settings.get("id_col")
    strategy = ((p.settings.get("cv") or {}).get("strategy")) or ""
    lines = ["import pandas as pd", "", f'folds = pd.read_csv(r"{path}")',
             "train = train.reset_index(drop=True)"]
    if id_col and p.train is not None and id_col in p.train.columns:
        lines += [f'assert (train["{id_col}"].astype(str).values == folds["{id_col}"].astype(str).values).all()  # 행 순서 확인']
    lines += ['train["fold"] = folds["fold"].values', ""]
    if strategy == "time":
        lines += ["# 시간 순서 검증: 각 폴드는 그보다 앞선 기간 전부로 학습하고 그 기간으로 검증합니다 (fold -1은 학습에만 씀)",
                  "for k in sorted(train.loc[train.fold >= 0, 'fold'].unique()):",
                  "    trn, val = train[train.fold < k], train[train.fold == k]",
                  "    ..."]
    else:
        lines += ["for k in sorted(train.loc[train.fold >= 0, 'fold'].unique()):",
                  "    trn, val = train[(train.fold != k) & (train.fold >= 0)], train[train.fold == k]",
                  "    ..."]
    return "\n".join(i18n.tr(line) for line in lines)  # 주석은 요청 언어로


def _log_snippet(p: Project) -> str:
    root = str(p.root).replace("\\", "/")
    return "\n".join(i18n.tr(line) for line in [  # 주석은 요청 언어로
        "import dotbogi",
        "",
        "# 학습 스크립트 끝에서 한 줄로 기록 (oof: train 행 순서의 예측, test_pred: test 행 순서의 예측)",
        "dotbogi.log(",
        f'    r"{root}",',
        '    name="lgbm_v3",',
        "    cv=cv_score,           # 생략하면 oof로 자동 계산",
        "    oof=oof,               # numpy 배열 또는 Series",
        "    test_pred=test_pred,   # 넣으면 제출 파일도 만들어 둡니다",
        '    params=params, notes="피처 12개 추가")',
    ])
