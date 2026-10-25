"""영어 화면 번역 사전 관리.

    python tools/i18n.py extract   # 소스에서 한국어 문구를 뽑아 dotbogi/i18n_en.json에 새 항목 추가, static/i18n/en.js 다시 쓰기
    python tools/i18n.py check     # 번역이 빠진 항목이 있으면 실패 (테스트에서 사용)
    python tools/i18n.py missing   # 빠진 항목만 JSON으로 출력

열쇠는 한국어 원문. 값이 끼워지는 자리는 {0}, {1}… (화면은 T("…{0}…", a), 서버는 f-문자열에서 자동으로 만든 틀).
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / "dotbogi"
CATALOG = PKG / "i18n_en.json"
JS_OUT = PKG / "static" / "i18n" / "en.js"
HANGUL = re.compile(r"[가-힣]")
# 화면에 나오지 않는 파이썬 파일 (명령줄 출력, 스크립트용 함수, 창 시작 문구)
PY_SKIP = {"cli.py", "__init__.py", "desktop.py", "__main__.py"}
JS_CALL = re.compile(r"""\bT\(\s*(["'])((?:\\.|(?!\1).)*)\1""", re.S)


def _js_unescape(body: str) -> str:
    return json.loads('"' + body.replace('\\\'', "'").replace('"', '\\"').replace('\\\\"', '\\"') + '"') \
        if "\\" in body else body


def js_keys() -> dict[str, str]:
    out = {}
    for f in sorted((PKG / "static" / "js").rglob("*.js")):
        if "vendor" in f.parts:
            continue
        src = f.read_text(encoding="utf-8")
        for m in JS_CALL.finditer(src):
            body = m.group(2)
            try:
                key = json.loads('"' + body.replace('"', '\\"') + '"') if m.group(1) == "'" else json.loads('"' + body + '"')
            except json.JSONDecodeError:
                key = body
            if HANGUL.search(key):
                out.setdefault(key, f"{f.relative_to(PKG).as_posix()}:{src.count(chr(10), 0, m.start()) + 1}")
    return out


def _fstring_key(node: ast.JoinedStr) -> str:
    parts, k = [], 0
    for v in node.values:
        if isinstance(v, ast.Constant):
            parts.append(str(v.value).replace("{", "{{").replace("}", "}}"))
        else:
            parts.append("{" + str(k) + "}")
            k += 1
    return "".join(parts)


def py_keys() -> dict[str, str]:
    out = {}
    for f in sorted(PKG.rglob("*.py")):
        if f.name in PY_SKIP:
            continue
        tree = ast.parse(f.read_text(encoding="utf-8"))
        docs, inside_f = set(), set()
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and body \
                    and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                docs.add(id(body[0].value))
            if isinstance(node, ast.JoinedStr):
                for v in node.values:
                    inside_f.add(id(v))
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                key = _fstring_key(node)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs \
                    and id(node) not in inside_f:
                key = node.value.replace("{", "{{").replace("}", "}}") if "{" in node.value else node.value
            else:
                continue
            if HANGUL.search(key):
                out.setdefault(key, f"{f.relative_to(PKG).as_posix()}:{node.lineno}")
    return out


def load_catalog() -> dict[str, str]:
    if CATALOG.exists():
        return json.loads(CATALOG.read_text(encoding="utf-8"))
    return {}


def write_js(cat: dict[str, str], keys: set[str]) -> None:
    JS_OUT.parent.mkdir(parents=True, exist_ok=True)
    data = {k: v for k, v in sorted(cat.items()) if v and k in keys}
    JS_OUT.write_text("/* 영어 화면 번역 (tools/i18n.py extract가 만듦, 직접 고치지 말 것: dotbogi/i18n_en.json을 고치세요) */\n"
                      "window.DOTBOGI_I18N_EN = " + json.dumps(data, ensure_ascii=False, indent=0) + ";\n",
                      encoding="utf-8", newline="\n")


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "check"
    js, py = js_keys(), py_keys()
    keys = {**py, **js}
    cat = load_catalog()
    missing = {k: where for k, where in keys.items() if not cat.get(k)}
    if cmd == "extract":
        for k in keys:
            cat.setdefault(k, "")
        unused = [k for k in cat if k not in keys]
        for k in unused:
            del cat[k]
        CATALOG.write_text(json.dumps(dict(sorted(cat.items())), ensure_ascii=False, indent=1) + "\n",
                           encoding="utf-8", newline="\n")
        write_js(cat, set(js))
        print(f"문구 {len(keys)}개 (화면 {len(js)}, 서버 {len(py)}), 번역 없음 {len(missing)}개, 지운 옛 항목 {len(unused)}개")
        return 0
    if cmd == "missing":
        print(json.dumps(missing, ensure_ascii=False, indent=1))
        return 0
    if missing:
        print(f"번역이 빠진 문구 {len(missing)}개:")
        for k, where in list(missing.items())[:30]:
            print(f"  {where}: {k[:80]}")
        return 1
    print(f"번역 {len(keys)}개 모두 있음")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
