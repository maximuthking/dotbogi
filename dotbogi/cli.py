"""명령줄: 화면 열기, 데이터 점검, 제출 파일 검사, 보고서 만들기.

  dotbogi [폴더]                          화면 열기 (폴더를 주면 바로 그 대회를 연다)
  dotbogi check <폴더> [--json]           데이터 점검 결과 출력
  dotbogi sub-check <파일> -p <폴더>      제출 파일 검사 (문제가 있으면 종료 코드 1)
  dotbogi report <폴더> [-o 파일]         HTML 보고서 만들기
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__

COMMANDS = {"check", "sub-check", "report", "serve"}
LEVEL_MARK = {"danger": "[위험]", "warn": "[주의]", "info": "[참고]", "ok": "[괜찮음]"}


def _utf8_stdout():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _app(folder: str):
    from .api import App
    from .project import Project
    app = App()
    p = Project(folder)
    p.load()
    app.project = p
    return app


def _wait(app, res):
    """api가 {ready: False, job}을 주면 그 작업이 끝날 때까지 기다린다."""
    import time
    info = res.get("job") if isinstance(res, dict) else None
    if not info:
        return
    job = app.jobs.get(info["id"])
    while job is not None and job.state == "running":
        time.sleep(0.2)
    if job is not None and job.state == "error":
        raise SystemExit(f"오류: {job.error}")


def cmd_check(args) -> int:
    app = _app(args.folder)
    for _ in range(3):
        r = app.checks()
        if r.get("ready"):
            break
        _wait(app, r)
    r = app.checks()
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0
    s = app.project.settings
    print(f"돋보기 {__version__} · {app.project.root}")
    print(f"타깃 {s['target']} · ID {s['id_col']} · {s['task']} · 지표 {s['metric']}")
    print(f"위험 {r['counts']['danger']} · 주의 {r['counts']['warn']} · 참고 {r['counts']['info']}\n")
    for it in r["items"]:
        print(f"{LEVEL_MARK[it['level']]} {it['title']}")
        print(f"    {it['detail']}")
        if it.get("action"):
            print(f"    할 일: {it['action']}")
        if it.get("columns"):
            print(f"    컬럼: {', '.join(it['columns'][:10])}")
    rec = r.get("recommend")
    if rec:
        print(f"\n추천 검증 방법: {rec['label']} {rec['n_splits']}폴드"
              + (f" (그룹 {rec['group_col']})" if rec.get("group_col") else "")
              + (f" (날짜 {rec['time_col']})" if rec.get("time_col") else ""))
        for reason in rec["reasons"]:
            print(f"  - {reason}")
    return 2 if r["counts"]["danger"] else 0


def cmd_sub_check(args) -> int:
    app = _app(args.project)
    r = app.submission_check(str(Path(args.file).resolve()))
    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(("통과: 올려도 되는 형식입니다." if r["ok"] else "실패: 고칠 문제가 있습니다.") + f" ({r['rows']:,}행)")
        for it in r["items"]:
            print(f"{LEVEL_MARK.get(it['level'], '')} {it['title']}" + (f" - {it['detail']}" if it.get("detail") else ""))
        if r.get("fixable") and args.fix:
            fx = app.submission_fix(r["path"])
            if fx.get("path"):
                print(f"\n고친 파일: {fx['path']} ({', '.join(fx['done'])})")
        elif r.get("fixable"):
            print("\n--fix 를 붙이면 안전하게 고친 파일을 따로 저장합니다.")
    return 0 if r["ok"] else 1


def cmd_report(args) -> int:
    from .report import build_report
    app = _app(args.folder)
    out = Path(args.output) if args.output else None
    res = build_report(app, out, None, run_adversarial=args.adversarial)
    print(f"보고서: {res['path']} ({res['bytes'] / 1e6:.1f} MB)")
    return 0


def main(argv: list[str] | None = None) -> int:
    _utf8_stdout()
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-V", "--version"):
        print(__version__)
        return 0
    if not argv or argv[0] not in COMMANDS:
        ap = argparse.ArgumentParser(prog="dotbogi", description="돋보기: 캐글·데이콘 정형 데이터 대회 분석 도구",
                                     epilog="다른 명령: check, sub-check, report (예: dotbogi check 대회폴더)")
        ap.add_argument("folder", nargs="?", help="열 대회 폴더 (생략하면 시작 화면)")
        ap.add_argument("--port", type=int, default=8765, help="포트 (기본 8765, 쓰는 중이면 다음 번호)")
        ap.add_argument("--no-browser", action="store_true", help="브라우저를 자동으로 열지 않기")
        a = ap.parse_args(argv)
        if a.folder and not Path(a.folder).is_dir():
            print(f"폴더가 없습니다: {a.folder}", file=sys.stderr)
            return 1
        from .server import serve
        serve(a.folder, port=a.port, open_browser=not a.no_browser)
        return 0

    ap = argparse.ArgumentParser(prog="dotbogi")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="데이터 점검")
    p.add_argument("folder")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("sub-check", help="제출 파일 검사")
    p.add_argument("file")
    p.add_argument("-p", "--project", required=True, help="대회 폴더")
    p.add_argument("--json", action="store_true")
    p.add_argument("--fix", action="store_true", help="안전하게 고친 파일을 따로 저장")
    p = sub.add_parser("report", help="HTML 보고서")
    p.add_argument("folder")
    p.add_argument("-o", "--output")
    p.add_argument("--adversarial", action="store_true", help="적대적 검증도 실행해서 넣기")
    p = sub.add_parser("serve", help="화면 열기")
    p.add_argument("folder", nargs="?")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--no-browser", action="store_true")
    a = ap.parse_args(argv)
    from .io import LoadError
    try:
        if a.cmd == "check":
            return cmd_check(a)
        if a.cmd == "sub-check":
            return cmd_sub_check(a)
        if a.cmd == "report":
            return cmd_report(a)
        from .server import serve
        serve(a.folder, port=a.port, open_browser=not a.no_browser)
        return 0
    except LoadError as e:
        print(f"오류: {e}", file=sys.stderr)
        return 1
