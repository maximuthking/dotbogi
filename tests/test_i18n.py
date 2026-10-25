"""영어 화면: 번역 사전이 빠짐없고, 서버가 보내는 문구가 영어로 바뀌며 데이터는 그대로인지."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from conftest import make_planted, wait, write
from dotbogi import i18n
from dotbogi.api import App
from dotbogi.experiments import Ledger

ROOT = Path(__file__).resolve().parents[1]
HANGUL = re.compile(r"[가-힣]")


def test_catalog_is_complete():
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "i18n.py"), "check"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stdout[-2000:]


def test_templates_and_nested_messages():
    cat = i18n.Catalog({"'{0}'은 숫자 컬럼이라 숫자로 비교해야 합니다.": "'{0}' is numeric, so compare it with a number.",
                        "제출 파일을 만들지 못했습니다: {0}": "Could not create the submission file: {0}",
                        "타깃 값이 하나뿐이라 학습할 수 없습니다.": "The target has only one value, so it cannot be trained.",
                        "데이터": "Data"})
    assert cat.tr("'나이'은 숫자 컬럼이라 숫자로 비교해야 합니다.") == "'나이' is numeric, so compare it with a number."
    assert cat.tr("제출 파일을 만들지 못했습니다: 타깃 값이 하나뿐이라 학습할 수 없습니다.") == \
        "Could not create the submission file: The target has only one value, so it cannot be trained."
    # 데이터 필드는 그대로, 문장 일부만 같다고 바꾸지 않음
    out = cat.translate({"name": "데이터", "message": "데이터", "cols": ["데이터"], "notes": "데이터 정리"})
    assert out == {"name": "데이터", "message": "Data", "cols": ["데이터"], "notes": "데이터 정리"}


def _leftovers(obj, path="", out=None):
    """번역 뒤에도 한국어가 남은 문구 (데이터 필드는 i18n이 건너뛰므로 여기서도 건너뜀)"""
    out = [] if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k not in i18n.SKIP_KEYS:
                _leftovers(v, f"{path}.{k}", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            _leftovers(v, f"{path}[{i}]", out)
    elif isinstance(obj, str) and HANGUL.search(obj):
        out.append(f"{path}: {obj[:120]}")
    return out


def test_server_responses_are_english(tmp_path):
    folder = write(tmp_path / "planted", *make_planted(n_train=900, n_test=400))
    app = App()
    i18n.set_lang("en")
    try:
        wait(app, app.open_project(str(folder)))
        p = app.project
        res = {"state": app.state(), "overview": app.overview()}
        res["columns_job"] = wait(app, app.columns()) or {}
        res["columns"] = app.columns()
        res["column"] = [app.column(c.name) for c in p.columns]
        res["checks_job"] = wait(app, app.checks()) or {}
        res["checks"] = app.checks()
        res["adv_job"] = wait(app, app.adversarial(None)) or {}
        res["adv"] = app.adversarial(None)
        res["cv"] = app.cv_info()
        res["baseline"] = wait(app, app.baseline({}))
        res["baseline2"] = wait(app, app.baseline({"learning_rate": 0.1}))
        res["experiments"] = app.experiments()
        ids = [e["id"] for e in res["experiments"]["experiments"]]
        res["noise"] = app.lb_noise({"id": ids[0], "id_b": ids[1]})
        res["ensemble"] = wait(app, app.ensemble({"ids": ids}))
        res["ensemble_save"] = app.ensemble_save({})
        sub = Ledger(p.dir).file_path(res["baseline"]["experiment"], "submission")
        res["sub_check"] = app.submission_check(str(sub))
        bad = tmp_path / "bad.csv"
        pd.read_csv(sub).iloc[:-5].to_csv(bad, index=False)
        res["sub_bad"] = app.submission_check(str(bad))
        res["sheet"] = app.sheet({"which": "train", "exp": ids[0], "limit": 3})
        translated = i18n.translate(res, "en")
    finally:
        i18n.set_lang("ko")
    left = _leftovers(translated)
    assert not left, f"{len(left)}개 남음:\n" + "\n".join(left[:40])
    # 기본 이름도 영어로
    assert res["baseline"]["experiment"]["name"].startswith("Baseline #")


@pytest.mark.parametrize("maker", ["groups", "time"])
def test_checks_english_other_structures(tmp_path, maker):
    """그룹·시간 구조 대회의 점검·검증 추천 문구도 영어로."""
    from conftest import make_groups, make_time_group
    data = make_groups() if maker == "groups" else make_time_group()
    folder = write(tmp_path / maker, *data)
    app = App()
    i18n.set_lang("en")
    try:
        wait(app, app.open_project(str(folder)))
        res = {"overview": app.overview()}
        wait(app, app.columns())
        res["columns"] = app.columns()
        res["column"] = [app.column(c.name) for c in app.project.columns]
        wait(app, app.checks())
        res["checks"] = app.checks()
        wait(app, app.adversarial(None))
        res["adv"] = app.adversarial(None)
        res["cv"] = app.cv_info()
        res["baseline"] = wait(app, app.baseline({}))
        res["cv_after"] = app.cv_info()
        translated = i18n.translate(res, "en")
    finally:
        i18n.set_lang("ko")
    left = _leftovers(translated)
    assert not left, f"{len(left)}개 남음:\n" + "\n".join(left[:40])


def test_report_in_english(tmp_path):
    from dotbogi.htmlreport import build_report
    folder = write(tmp_path / "rep", *make_planted(n_train=500, n_test=200))
    app = App()
    wait(app, app.open_project(str(folder)))
    out = tmp_path / "r.html"
    build_report(app, out, None, lang="en")
    html = out.read_text(encoding="utf-8")
    assert "<title>Dotbogi report" in html and '<html lang="en">' in html and '"lang":"en"' in html
    data = html.split("window.__DOTBOGI_STATIC__ = ", 1)[1].split(";</script>", 1)[0]
    import json
    payload = json.loads(data.replace("<\/", "</"))
    left = _leftovers(payload["responses"])
    assert not left, "\n".join(left[:20])
