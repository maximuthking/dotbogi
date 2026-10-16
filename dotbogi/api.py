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

from . import __version__
from . import metrics as M
from .analysis import gbm
from .analysis.adversarial import run_adversarial
from .analysis.baseline import run_baseline
from .analysis.checks import run_checks
from .analysis.cv import STRATEGIES, fold_summary, make_folds, recommend
from .analysis.features import build_matrix
from .analysis.profile import profile_column
from .experiments import (Ledger, cv_lb_analysis, frame_pred, lb_noise, make_submission, oof_frame,
                          suggest_final)
from .io import TABLE_EXTS, LoadError, file_signature, read_table
from .jobs import JobManager
from .project import PLATFORMS, Project, find_data_files
from .schema import KINDS, to_datetime_safe
from .submission import check_submission, compare_submissions, fix_submission
from .utils import as_label, jsonable, sample_index, to_float

HOME = Path(os.environ.get("DOTBOGI_HOME", Path.home() / ".dotbogi"))


class App:
    def __init__(self):
        self.project: Project | None = None
        self.jobs = JobManager(workers=2)
        self.started = time.time()

    # ═════════════════════════════════════════ 공통
    def require(self) -> Project:
        if self.project is None or not self.project.loaded:
            raise LoadError("먼저 대회 폴더를 여세요.")
        return self.project

    def ledger(self) -> Ledger:
        return Ledger(self.require().dir)

    def state(self) -> dict:
        p = self.project
        out = {
            "version": __version__, "lightgbm": gbm.HAS_LGB, "platform": sys.platform,
            "recent": self.recent(), "kinds": list(KINDS), "strategies": STRATEGIES,
            "platforms": PLATFORMS, "home": str(Path.home()),
            "jobs": [j.to_dict(False) for j in self.jobs.running()],
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
            }
        return out

    # ═════════════════════════════════════════ 최근 프로젝트 / 폴더 고르기
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
        found = find_data_files(pth, max_depth=2) if len(files) < 200 else {}
        parent = str(pth.parent) if pth.parent != pth else None
        return {"path": str(pth), "parent": parent, "dirs": dirs[:500], "files": files[:500], "drives": drives,
                "detected": {k: found.get(k) for k in ("train", "test", "sample_submission")}}

    def open_project(self, path: str) -> dict:
        pth = Path(path).expanduser()
        if pth.is_file():
            pth = pth.parent
        project = Project(pth)
        job = self.jobs.submit("load", "데이터 불러오기", self._load_job, project)
        return {"job": job.to_dict(False)}

    def _load_job(self, job, project: Project):
        project.load(progress=job.update)
        self.project = project
        self._remember(project)
        return {"ok": True}

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
        job = self.jobs.submit("load", "데이터 불러오기", self._load_job, p)
        return {"job": job.to_dict(False)}

    def reload(self) -> dict:
        p = self.project
        if p is None:
            raise LoadError("먼저 대회 폴더를 여세요.")
        job = self.jobs.submit("load", "데이터 다시 불러오기", self._load_job, p)
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
        if "name" in patch and patch["name"]:
            s["name"] = str(patch["name"])[:80]
        if heavy:
            p.invalidate()
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
                  json.dumps(s["kinds"], sort_keys=True), s["submission_format"], "v3"]
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
            ex = [as_label(v) for v in p.train[name].dropna().head(400).drop_duplicates().head(8).tolist()]
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
                           y, mask, p.cache.get("profiles"), progress=job.update)
        rec = recommend(s["task"], items, len(p.train), y)
        counts = {lv: sum(1 for it in items if it["level"] == lv) for lv in ("danger", "warn", "info", "ok")}
        p.cache["checks"] = jsonable({"items": items, "counts": counts, "recommend": rec})
        return {"ok": True}

    # ═════════════════════════════════════════ 적대적 검증
    def adversarial(self, exclude: list[str] | None = None, rerun: bool = False) -> dict:
        p = self.require()
        if p.test is None:
            raise LoadError("test 파일이 있어야 train과 test를 비교할 수 있습니다.")
        key = "adv:" + ",".join(sorted(exclude or []))
        if key in p.cache and not rerun:
            return {"ready": True, "result": p.cache[key], "exclude": exclude or []}
        if exclude is None and not rerun:
            # 아직 안 돌렸으면 결과 없음을 알려 준다 (버튼으로 시작)
            last = p.cache.get("adv:last")
            if last and last in p.cache:
                return {"ready": True, "result": p.cache[last], "exclude": p.cache.get("adv:last_ex", [])}
            return {"ready": False, "job": None}
        job = self.jobs.submit("adversarial", "적대적 검증", self._adv_job, p, list(exclude or []), key)
        return {"ready": False, "job": job.to_dict(False)}

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
        n_splits = int(params.get("n_splits") or 5)
        if not 2 <= n_splits <= 20:
            raise LoadError("폴드 수는 2~20 사이로 정하세요.")
        seed = int(params.get("seed") if params.get("seed") not in (None, "") else 42)
        group_col = params.get("group_col") or None
        time_col = params.get("time_col") or None
        if strategy in ("group", "stratified_group") and not group_col:
            raise LoadError("그룹 컬럼을 고르세요.")
        if strategy == "time" and not time_col:
            raise LoadError("날짜 컬럼을 고르세요.")
        if strategy in ("stratified", "stratified_group") and s["task"] == "regression":
            pass  # 회귀는 구간으로 나눠 층화
        y, mask, classes = p.encoded_target()
        fold = make_folds(p.train, strategy, n_splits, seed, y, mask, group_col, time_col)
        path = p.save_folds(fold)
        s["cv"] = {"strategy": strategy, "n_splits": n_splits, "seed": seed, "group_col": group_col,
                   "time_col": time_col, "created_at": time.strftime("%Y-%m-%d %H:%M")}
        p.save_settings()
        return {"ok": True, "path": str(path), "summary": jsonable(fold_summary(p.train, fold, s["task"], y, classes,
                                                                                 group_col, time_col))}

    def baseline(self, params: dict) -> dict:
        p = self.require()
        if not p.target_col():
            raise LoadError("타깃 컬럼을 먼저 정하세요.")
        job = self.jobs.submit("baseline", "기본 모델 교차검증", self._baseline_job, p, params or {})
        return {"job": job.to_dict(False)}

    def _baseline_job(self, job, p: Project, params: dict):
        s = p.settings
        y, mask, classes = p.encoded_target()
        fold = p.load_folds()
        if fold is None or not s.get("cv"):
            job.update(0.02, "추천 검증 방법으로 폴드를 만드는 중")
            chk = p.cache.get("checks")
            if chk is None:
                self._profiles_job_if_needed(job, p)
                self._checks_job(job, p)
                chk = p.cache["checks"]
            rec = chk["recommend"]
            self.make_folds({"strategy": rec["strategy"], "n_splits": rec["n_splits"], "seed": 42,
                             "group_col": rec.get("group_col"), "time_col": rec.get("time_col")})
            fold = p.load_folds()
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
        lr = float(params.get("learning_rate") or 0.05)
        n_classes = len(classes) if s["task"] == "multiclass" else 2
        res = run_baseline(mat, y, mask, s["task"], n_classes, fold, s["metric"], cv["strategy"],
                           engine=engine, learning_rate=lr, progress=lambda f, m: job.update(0.05 + f * 0.85, m))
        job.update(0.92, "결과 저장 중")
        ids = p.train[s["id_col"]].to_numpy() if s["id_col"] in p.train.columns else None
        oof = oof_frame(res["_oof"], s["task"], classes, ids, fold)
        test_df = sub = None
        if res["_test"] is not None:
            tid = p.test[s["id_col"]].to_numpy() if (s["id_col"] and s["id_col"] in p.test.columns) else None
            test_df = oof_frame(res["_test"], s["task"], classes, tid)
            if p.sample is not None:
                try:
                    sub = make_submission(res["_test"], p.sample, p.test, s["id_col"], s["task"], classes,
                                          s["submission_format"], s["metric"])
                except ValueError:
                    sub = None
        n_prev = sum(1 for e in self.ledger().load() if e.get("source") == "baseline")
        name = params.get("name") or f"기본 {'LightGBM' if res['engine'] == 'lightgbm' else 'HistGB'} #{n_prev + 1}"
        e = self.ledger().add(
            name, s["metric"], res["cv"], res["cv_std"], jsonable(res["fold_scores"]), source="baseline",
            params={"engine": res["engine"], "learning_rate": lr, "n_features": res["n_features"],
                    "strategy": cv["strategy"], "n_splits": cv["n_splits"], "excluded": sorted(exclude),
                    "mean_best_iteration": res["mean_best_iteration"]},
            notes=params.get("notes", ""), oof=oof, test_pred=test_df, submission=sub,
            extra={"importance": jsonable(res["importance"][:60])})
        out = {k: v for k, v in res.items() if not k.startswith("_")}
        out["experiment"] = e
        out["skipped"] = mat.skipped
        return jsonable(out)

    def _profiles_job_if_needed(self, job, p):
        if "profiles" not in p.cache:
            st = self.profiles_status()
            if not st["ready"]:
                self._profiles_job(job, p)

    # ═════════════════════════════════════════ 실험 대장
    def experiments(self) -> dict:
        p = self.require()
        s = p.settings
        exps = self.ledger().load()
        metric = s["metric"]
        hib = M.METRICS[metric].higher_is_better if metric in M.METRICS else True
        comp = s["competition"]
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
            y, mask, classes = p.encoded_target()
            pred = frame_pred(oof, p.settings["task"])
            ok = mask & (~np.isnan(pred).any(axis=1) if pred.ndim == 2 else ~np.isnan(pred))
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
        else:
            if not cand:
                raise LoadError("OOF 파일에서 숫자 예측 컬럼을 찾지 못했습니다.")
            pick = "pred" if "pred" in cand else ("oof" if "oof" in cand else cand[-1])
            pred = df[pick].to_numpy(dtype="float64")
        how = "행 순서"
        key_col = id_col if id_col and id_col in df.columns else ("id" if "id" in df.columns else None)
        if key_col and id_col and id_col in p.train.columns:
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
        return oof_frame(pred, task, classes, ids, fold), how

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
        if s["task"] == "multiclass":
            if s["submission_format"] != "proba_columns":
                return None
            arr = sub[cols].apply(pd.to_numeric, errors="coerce").to_numpy(dtype="float64")
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
        y, mask, classes = p.encoded_target()
        pred = frame_pred(oof, s["task"])
        ok = mask & (~np.isnan(pred).any(axis=1) if pred.ndim == 2 else ~np.isnan(pred))
        pred_b = None
        if params.get("id_b"):
            eb = led.get(params["id_b"])
            ob = led.read_oof(eb) if eb else None
            if ob is None:
                raise LoadError("비교할 실험에 OOF 예측이 없습니다.")
            pred_b = frame_pred(ob, s["task"])
            ok &= ~np.isnan(pred_b).any(axis=1) if pred_b.ndim == 2 else ~np.isnan(pred_b)
        n_test = len(p.test) if p.test is not None else len(p.train)
        share = s["competition"].get("public_share") or 0.3
        public_rows = int(params.get("public_rows") or round(n_test * float(share)))
        res = lb_noise(y[ok], pred[ok], s["metric"], public_rows,
                       pred_b=pred_b[ok] if pred_b is not None else None)
        res["public_share"] = share
        res["share_assumed"] = not s["competition"].get("public_share")
        return jsonable(res)

    def ensemble(self, params: dict) -> dict:
        self.require()
        job = self.jobs.submit("ensemble", "앙상블 가중치 찾기", self._ensemble_job, params)
        return {"job": job.to_dict(False)}

    def _ensemble_job(self, job, params: dict):
        from .ensemble import run_ensemble
        p = self.require()
        s = p.settings
        led = self.ledger()
        ids = params.get("ids") or []
        exps = [led.get(i) for i in ids]
        exps = [e for e in exps if e is not None]
        if len(exps) < 2:
            raise LoadError("OOF가 있는 실험을 2개 이상 고르세요.")
        y, mask, classes = p.encoded_target()
        preds, names = [], []
        ok = mask.copy()
        for e in exps:
            o = led.read_oof(e)
            if o is None:
                raise LoadError(f"'{e['name']}'에는 OOF가 없습니다.")
            pr = frame_pred(o, s["task"])
            preds.append(pr)
            names.append(e["name"])
            ok &= ~np.isnan(pr).any(axis=1) if pr.ndim == 2 else ~np.isnan(pr)
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
        w = np.asarray(last["_weights"], float)
        y, mask, classes = p.encoded_target()
        oofs = [frame_pred(led.read_oof(e), s["task"]) for e in exps]
        blend_oof = blend_test(oofs, w, last["use_rank"])
        ids = p.train[s["id_col"]].to_numpy() if s["id_col"] in p.train.columns else None
        oof_df = oof_frame(blend_oof, s["task"], classes, ids, p.load_folds())
        test_df = sub = None
        if last["has_all_tests"]:
            tests = [frame_pred(led.read_test(e), s["task"]) for e in exps]
            if len({t.shape for t in tests}) == 1:
                bt = blend_test(tests, w, last["use_rank"])
                tid = (led.read_test(exps[0]).get("id").to_numpy()
                       if "id" in led.read_test(exps[0]).columns else None)
                test_df = oof_frame(bt, s["task"], classes, tid)
                if p.sample is not None:
                    # test 예측이 제출 파일에서 왔으면 이미 sample 순서, 기본 모델에서 왔으면 test 순서
                    try:
                        sub = make_submission(bt, p.sample, _test_like(p, tid), s["id_col"], s["task"], classes,
                                              s["submission_format"], s["metric"])
                    except ValueError:
                        sub = None
        cv = last["honest"]["score"] if last.get("honest") else last["score"]
        name = params.get("name") or "앙상블 (" + " + ".join(
            f"{wt['name']} {wt['weight']:.2f}" for wt in last["weights"] if wt["weight"] > 0) + ")"
        e = led.add(name[:120], s["metric"], cv, None, source="ensemble",
                    params={"weights": last["weights"], "use_rank": last["use_rank"], "method": last["method"],
                            "in_sample_score": last["score"]},
                    notes="CV는 폴드 교차로 잰 정직한 점수입니다." if last.get("honest") else "",
                    oof=oof_df, test_pred=test_df, submission=sub)
        return jsonable({"experiment": e, "has_submission": sub is not None})

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
        if r.returncode != 0 or not out:
            msg = (r.stderr or out or "").strip().splitlines()[-1:] or ["알 수 없는 오류"]
            hint = ""
            low = (r.stderr + out).lower()
            if "401" in low or "unauthorized" in low or "credentials" in low or "kaggle.json" in low:
                hint = " Kaggle API 토큰(kaggle.json 등)이 설정돼 있는지 확인하세요."
            elif "403" in low:
                hint = " 대회 규칙에 동의했는지, 대회 주소가 맞는지 확인하세요."
            raise LoadError(f"Kaggle CLI 오류: {msg[0][:300]}{hint}")
        lines = out.splitlines()
        start = next((i for i, ln in enumerate(lines) if "," in ln and "date" in ln.lower()), 0)
        df = pd.read_csv(StringIO("
".join(lines[start:])))
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
            fields = {"lb_public": float(pub), "kaggle_key": key,
                      "submitted_at": pd.to_datetime(date, errors="coerce").strftime("%Y-%m-%dT%H:%M:%S")
                      if pd.notna(pd.to_datetime(date, errors="coerce")) else None}
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
        from .report import build_report
        p = self.require()
        out = Path(params.get("path") or (p.dir / f"report-{time.strftime('%Y%m%d-%H%M')}.html"))
        job = self.jobs.submit("report", "보고서 만들기", lambda job: build_report(self, out, job))
        return {"job": job.to_dict(False)}

    # ═════════════════════════════════════════ 제출 파일
    def submission_check(self, path: str) -> dict:
        p = self.require()
        s = p.settings
        if not Path(path).exists():
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
        feats.sort(key=lambda c: -((prof.get(c.name) or {}).get("power") or {}).get("power", 0) or 0)
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
                                 "sampled": len(idx) < n, "n": n})
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
        offset = max(0, int(params.get("offset") or 0))
        limit = min(500, max(1, int(params.get("limit") or 100)))
        page = view.iloc[offset: offset + limit]
        return {"columns": [str(c) for c in view.columns], "total": int(len(df)), "matched": int(len(view)),
                "offset": offset,
                "index": [int(i) for i in page.index],
                "rows": [[_cell(v) for v in r] for r in page.itertuples(index=False)]}


# ═════════════════════════════════════════ 도우미
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
    from .io import _read_csv  # noqa: 내부 함수 재사용
    pth = Path(path)
    if pth.suffix.lower() in (".csv", ".tsv", ".txt"):
        # ID 앞자리 0 보존을 위해 첫 컬럼은 문자열로 읽어 본다
        from .io import detect_encoding
        enc = detect_encoding(pth)
        head = pd.read_csv(pth, nrows=5, encoding=enc)
        dtypes = {head.columns[0]: "string"} if len(head.columns) else None
        df = pd.read_csv(pth, encoding=enc, dtype=dtypes, low_memory=False)
        first = df.columns[0]
        # 숫자로만 된 ID면 숫자로 되돌린다 (앞자리 0이 없을 때만)
        s = df[first]
        if s.notna().all() and s.str.fullmatch(r"-?\d+").all() and not s.str.match(r"0\d").any():
            df[first] = pd.to_numeric(s)
        return df
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
    lines = ["import pandas as pd", "", f'folds = pd.read_csv(r"{path}")',
             "train = train.reset_index(drop=True)"]
    if id_col and p.train is not None and id_col in p.train.columns:
        lines += [f'assert (train["{id_col}"].values == folds["{id_col}"].values).all()  # 행 순서 확인']
    lines += ['train["fold"] = folds["fold"].values', "",
              "for k in sorted(train.loc[train.fold >= 0, 'fold'].unique()):",
              "    trn, val = train[train.fold != k], train[train.fold == k]",
              "    # 시간 검증이면: trn = train[train.fold < k]",
              "    ..."]
    return "\n".join(lines)


def _log_snippet(p: Project) -> str:
    root = str(p.root).replace("\\", "/")
    return "\n".join([
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
