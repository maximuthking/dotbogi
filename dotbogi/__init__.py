"""돋보기(Dotbogi): 캐글·데이콘 정형 데이터 대회용 로컬 분석 도구.

화면:      python -m dotbogi [대회폴더]
스크립트:  dotbogi.log(대회폴더, name=..., oof=..., test_pred=...)
"""
from __future__ import annotations

__version__ = "1.0.0"

__all__ = ["__version__", "log", "folds", "serve", "check_submission_file"]


def _load_project(project: str):
    from .project import Project
    p = Project(project)
    p.load()
    return p


def log(project: str, name: str, cv: float | None = None, oof=None, test_pred=None, lb: float | None = None,
        params: dict | None = None, notes: str = "", tags: list[str] | None = None,
        metric: str | None = None, submission=None) -> dict:
    """학습 스크립트에서 실험 하나를 대장에 기록한다.

    oof:       train 행 순서의 OOF 예측 (1차원, 다중분류는 (행, 클래스) 2차원). 결측 행은 NaN.
    test_pred: test 파일 행 순서의 예측. sample_submission이 있으면 제출 파일도 만들어 둔다.
    cv:        생략하고 oof를 주면 설정된 지표로 자동 계산한다.
    """
    import numpy as np
    import pandas as pd

    from . import metrics as M
    from .experiments import Ledger, make_submission, oof_frame

    p = _load_project(project)
    s = p.settings
    y, mask, classes = p.encoded_target()
    task = s["task"]
    metric = metric or s["metric"]
    if metric not in M.METRICS:
        raise ValueError(f"알 수 없는 지표: {metric}")
    oof_df = test_df = sub = None
    ids = p.train[s["id_col"]].to_numpy() if s["id_col"] and s["id_col"] in p.train.columns else None

    def as_array(v):
        arr = np.asarray(v.values if isinstance(v, (pd.Series, pd.DataFrame)) else v, dtype="float64")
        if task == "binary" and arr.ndim == 2 and arr.shape[1] == 2:
            arr = arr[:, 1]
        if task != "multiclass" and arr.ndim == 2 and arr.shape[1] == 1:
            arr = arr[:, 0]
        return arr

    if oof is not None:
        arr = as_array(oof)
        if arr.shape[0] != len(p.train):
            raise ValueError(f"oof 길이({arr.shape[0]})가 train 행 수({len(p.train)})와 다릅니다.")
        oof_df = oof_frame(arr, task, classes, ids, p.load_folds())
        if cv is None:
            ok = mask & (~np.isnan(arr).any(axis=1) if arr.ndim == 2 else ~np.isnan(arr))
            cv = M.score(metric, y[ok], arr[ok])
    if test_pred is not None:
        arr = as_array(test_pred)
        tid = None
        if p.test is not None:
            if arr.shape[0] != len(p.test):
                raise ValueError(f"test_pred 길이({arr.shape[0]})가 test 행 수({len(p.test)})와 다릅니다.")
            if s["id_col"] and s["id_col"] in p.test.columns:
                tid = p.test[s["id_col"]].to_numpy()
        test_df = oof_frame(arr, task, classes, tid)
        if submission is None and p.sample is not None:
            sub = make_submission(arr, p.sample, p.test, s["id_col"], task, classes, s["submission_format"], metric)
    if submission is not None:
        sub = submission if isinstance(submission, pd.DataFrame) else pd.read_csv(submission)
    return Ledger(p.dir).add(name, metric, cv, lb_public=lb, notes=notes, tags=tags, params=params or {},
                             source="script", oof=oof_df, test_pred=test_df, submission=sub)


def folds(project: str):
    """화면에서 만든 폴드 번호 배열 (train 행 순서, 검증에 안 쓰는 행은 -1). 없으면 None."""
    return _load_project(project).load_folds()


def serve(path: str | None = None, port: int = 8765, open_browser: bool = True):
    from .server import serve as _serve
    return _serve(path, port=port, open_browser=open_browser)


def check_submission_file(project: str, path: str) -> dict:
    """제출 파일 검사 결과(dict). 'ok'가 False면 고칠 문제가 있다."""
    from .api import App
    app = App()
    app.project = _load_project(project)
    return app.submission_check(path)
