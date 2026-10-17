"""화면 자동 둘러보기: 실제 브라우저(Edge/Chromium)로 모든 화면과 창을 눌러 보고 캡처한다.

실행: python tests/ui_tour.py <캡처 폴더> [msedge|chromium]
필요: pip install playwright (브라우저는 설치된 Edge를 쓰면 따로 받지 않아도 됨)
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import os  # noqa: E402
os.environ["DOTBOGI_HOME"] = tempfile.mkdtemp(prefix="dotbogi_home_")  # 사용자 최근 목록을 건드리지 않게
from conftest import make_groups, make_planted, make_time_group, write  # noqa: E402
from dotbogi import server as S  # noqa: E402

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else tempfile.mkdtemp())
CHANNEL = sys.argv[2] if len(sys.argv) > 2 else "msedge"
OUT.mkdir(parents=True, exist_ok=True)
DATA = Path(tempfile.mkdtemp(prefix="dotbogi_tour_"))
groups = write(DATA / "그룹_다중분류", *make_groups())
timeds = write(DATA / "시간_회귀", *make_time_group())
planted = write(DATA / "planted", *make_planted())

httpd, app, port = S.make_server(None, port=18800)
threading.Thread(target=httpd.serve_forever, daemon=True).start()
BASE = f"http://127.0.0.1:{port}/"

from playwright.sync_api import sync_playwright  # noqa: E402

errors: list[str] = []
log: list[str] = []


def step(msg):
    log.append(msg)
    print("·", msg, flush=True)


def settle(pg, ms=400):
    """작업 진행 표시와 로딩이 사라질 때까지 기다린다."""
    pg.wait_for_timeout(ms)
    for _ in range(600):
        busy = pg.evaluate("document.querySelectorAll('.job, .loading, .btn.busy').length")
        if not busy:
            break
        pg.wait_for_timeout(250)
    pg.wait_for_timeout(300)


def shot(pg, name, full=True):
    pg.screenshot(path=str(OUT / f"{name}.png"), full_page=full)


def open_folder(pg, folder):
    pg.goto(BASE + "#/home")
    settle(pg)
    pg.fill("input.input[placeholder^='대회 데이터 폴더']", str(folder))
    pg.click("button.btn.primary.lg")
    settle(pg, 800)


def nav(pg, name, params=""):
    pg.goto(BASE + f"#/{name}{params}")
    settle(pg)


with sync_playwright() as pw:
    browser = pw.chromium.launch(channel=CHANNEL, headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light", locale="ko-KR",
                              accept_downloads=True)
    pg = ctx.new_page()
    pg.on("console", lambda m: errors.append(f"[console] {m.text}") if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(f"[pageerror] {e}"))

    try:
        # ── 시작 화면 + 폴더 고르기 창
        pg.goto(BASE)
        settle(pg)
        shot(pg, "01_home_empty")
        pg.click("button:has-text('찾아보기')")
        settle(pg)
        pg.fill(".modal input.input", str(DATA))
        pg.keyboard.press("Enter")
        settle(pg)
        pg.click(f".browser-item:has-text('{groups.name}')")
        settle(pg)
        shot(pg, "02_browse_modal", full=False)
        pg.click(".modal button:has-text('이 폴더 열기')")
        settle(pg, 1000)
        step("다중분류(그룹) 대회를 폴더 고르기 창으로 열었다")

        # ── 개요·점검·컬럼
        shot(pg, "03_overview_multiclass")
        nav(pg, "checks")
        shot(pg, "04_checks_groups")
        nav(pg, "columns")
        pg.click("table.t tbody tr:has-text('feat')")
        settle(pg)
        shot(pg, "05_columns_feat")
        pg.fill("input[placeholder='컬럼 이름 검색']", "noi")
        settle(pg)
        assert pg.locator("table.t tbody tr").count() == 1, "검색이 안 됩니다"
        step("컬럼 검색 동작")

        # ── train vs test
        nav(pg, "drift")
        pg.click("button:has-text('실행하기')")
        settle(pg, 800)
        shot(pg, "06_drift_adversarial")
        pg.click("button:has-text('빼기') >> nth=0")
        pg.click("button:has-text('다시 실행')")
        settle(pg, 800)
        assert pg.locator("text=이번 결과에서 뺀 컬럼").count() == 1
        step("적대적 검증 + 컬럼 빼고 다시 실행")

        # ── 탐색 4개 탭
        for tab in ("power", "corr", "chart", "data"):
            nav(pg, "explore", f"?tab={tab}")
            shot(pg, f"07_explore_{tab}")
        nav(pg, "explore", "?tab=chart&x=feat&y=noise&color=target&which=train")
        shot(pg, "07_explore_scatter")
        nav(pg, "explore", "?tab=data")
        pg.select_option(".card select.select.sm >> nth=0", "feat")
        pg.select_option(".card select.select.sm >> nth=1", ">")
        pg.fill("input[placeholder='값']", "1")
        pg.click("button:has-text('필터 추가')")
        settle(pg)
        assert "전체" in pg.inner_text(".content"), "필터 결과 표시가 없습니다"
        step("데이터 보기 필터 동작")

        # ── 검증 설계 → 기본 모델 2번
        nav(pg, "cv")
        shot(pg, "08_cv_recommend")
        pg.click("button:has-text('추천대로 폴드 만들기')")
        settle(pg, 800)
        pg.click("button:has-text('교차검증 실행')")
        settle(pg, 1000)
        shot(pg, "09_cv_baseline")
        pg.fill("input[placeholder='비우면 자동 이름']", "두번째_학습률0.1")
        pg.fill(".field:has-text('학습률') input", "0.1")
        pg.click("button:has-text('교차검증 실행')")
        settle(pg, 1000)
        step("폴드 생성 + 기본 모델 2회")

        # ── 실험: 창들
        nav(pg, "experiments")
        shot(pg, "10_experiments")
        pg.click("button:has-text('실험 추가')")
        settle(pg)
        shot(pg, "11_add_modal", full=False)
        pg.fill(".modal input[placeholder^='예: lgbm']", "직접 적은 실험")
        pg.fill(".modal .field:has-text('Public LB') input", "1.05")
        pg.click(".modal button:has-text('추가')")
        settle(pg)
        pg.click("button:has-text('스크립트로 기록')")
        settle(pg)
        shot(pg, "12_snippet_modal", full=False)
        pg.keyboard.press("Escape")
        pg.click("table.t tbody tr >> nth=1")
        settle(pg)
        shot(pg, "13_detail_modal", full=False)
        pg.keyboard.press("Escape")
        step("실험 추가·스크립트 안내·상세 창")
        # 겹친 창에서 Esc는 맨 위 창만 닫는다
        pg.click("button:has-text('실험 추가')")
        settle(pg)
        pg.click(".modal .field:has-text('OOF') button:has-text('찾아보기')")
        settle(pg)
        assert pg.locator(".modal-back").count() == 2
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)
        assert pg.locator(".modal-back").count() == 1, "Esc 한 번에 창이 모두 닫혔습니다"
        pg.keyboard.press("Escape")
        pg.wait_for_timeout(300)
        # 실험 삭제
        before = pg.locator("table.t tbody tr").count()
        pg.click("button[title='삭제 (휴지통으로)'] >> nth=0")
        settle(pg)
        pg.click(".modal button:has-text('삭제')")
        settle(pg, 800)
        after = pg.locator("table.t tbody tr").count()
        assert after == before - 1, f"삭제가 안 됩니다 ({before} → {after})"
        step("겹친 창 Esc, 실험 삭제")

        # ── 앙상블
        nav(pg, "ensemble")
        pg.click("button:has-text('가중치 찾기')")
        settle(pg, 1000)
        shot(pg, "14_ensemble")
        pg.click("button:has-text('실험으로 저장')")
        settle(pg, 800)
        step("앙상블 실행·저장")

        # ── 제출 검사 (실험의 제출 파일)
        nav(pg, "submission")
        pg.select_option(".card select.select", index=1)
        settle(pg, 800)
        shot(pg, "15_submission")
        step("제출 검사")

        # ── 설정 + 보고서
        nav(pg, "settings")
        pg.click("button:has-text('HTML 보고서 만들기')")
        settle(pg, 1500)
        shot(pg, "16_settings")
        rep = pg.locator(".callout.ok code").first.inner_text()
        step(f"보고서: {rep}")

        # ── 보고서 파일을 서버 없이 열기
        rp = ctx.new_page()
        rp.on("pageerror", lambda e: errors.append(f"[report pageerror] {e}"))
        rp.on("console", lambda m: errors.append(f"[report console] {m.text}") if m.type == "error" else None)
        rp.goto(Path(rep).as_uri())
        settle(rp, 800)
        shot(rp, "17_report_overview")
        for pgname in ("checks", "columns", "drift", "explore", "cv", "experiments"):
            rp.goto(Path(rep).as_uri() + f"#/{pgname}")
            settle(rp, 500)
            shot(rp, f"18_report_{pgname}")
        rp.close()
        step("보고서 파일을 서버 없이 열어 모든 화면 확인")

        # ── 시간·회귀 대회, 어두운 테마, 좁은 화면
        open_folder(pg, timeds)
        pg.evaluate("localStorage.setItem('dotbogi-theme','dark')")
        nav(pg, "overview")
        pg.reload()
        settle(pg, 800)
        shot(pg, "20_dark_overview_regression")
        nav(pg, "columns", "?name=date")
        shot(pg, "21_dark_columns_date")
        nav(pg, "cv")
        shot(pg, "22_dark_cv_time")
        pg.click("button:has-text('추천대로 폴드 만들기')")
        settle(pg, 800)
        pg.click("button:has-text('교차검증 실행')")
        settle(pg, 1000)
        shot(pg, "23_dark_cv_time_baseline")
        pg.set_viewport_size({"width": 1100, "height": 900})
        nav(pg, "overview")
        shot(pg, "24_narrow_1100")
        pg.set_viewport_size({"width": 800, "height": 900})
        nav(pg, "columns")
        shot(pg, "25_narrow_800")
        step("회귀·날짜 대회, 어두운 테마, 좁은 화면")

        # ── 위험 많은 대회 점검 화면
        pg.set_viewport_size({"width": 1440, "height": 900})
        pg.evaluate("localStorage.setItem('dotbogi-theme','light')")
        open_folder(pg, planted)
        nav(pg, "checks")
        shot(pg, "26_checks_planted")

        # ── 서버 꺼짐 안내 (이 뒤의 연결 오류는 예상된 것)
        n_before = len(errors)
        httpd.shutdown()
        httpd.server_close()
        pg.click(".nav-item:has-text('개요')")
        pg.wait_for_timeout(1500)
        offline = pg.locator("#offline").count()
        shot(pg, "27_offline", full=False)
        step(f"서버 꺼짐 안내 표시: {bool(offline)}")
        assert offline, "서버가 꺼졌는데 안내가 없습니다"
        expected = errors[n_before:]
        del errors[n_before:]
        step(f"서버를 끈 뒤 예상된 연결 오류 {len(expected)}건은 제외")
    except Exception as ex:
        errors.append(f"[tour] {type(ex).__name__}: {str(ex)[:400]}")
        try:
            pg.screenshot(path=str(OUT / "zz_failure.png"), full_page=True)
            print(pg.inner_text(".content")[:1500])
        except Exception:
            pass
    finally:
        browser.close()

print("\n캡처:", OUT)
print("콘솔 오류:", len(errors))
for e in errors:
    print("  ", e)
sys.exit(1 if errors else 0)
