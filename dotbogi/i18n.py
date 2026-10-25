"""영어 화면: 서버가 보내는 한국어 문구를 응답 직전에 번역한다.

번역 사전(i18n_en.json)의 열쇠는 한국어 원문이고, f-문자열에서 만든 틀은 값 자리가 {0}, {1}…이다.
- 문장이 통째로 일치할 때만 바꾼다 (사용자 데이터의 일부가 우연히 바뀌지 않게).
- 컬럼 이름·셀 값·경로처럼 데이터가 담기는 필드는 건드리지 않는다.
- 값 자리에 들어간 값에 한국어 문장이 있으면(예: 오류 메시지 안의 원인) 그것도 번역한다.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

CATALOG_PATH = Path(__file__).with_name("i18n_en.json")
HANGUL = re.compile(r"[가-힣]")
# 데이터가 담기는 필드: 번역하지 않는다
SKIP_KEYS = {
    "rows", "positions", "name", "names", "col", "cols", "column", "values", "value", "root", "path", "store",
    "files", "target", "targets", "id_col", "classes", "index", "id", "ids", "top", "examples", "sample",
    "x", "y", "color", "group_col", "time_col", "excluded", "kinds", "settings", "recent", "tabs", "categories",
    "levels", "train_values", "test_values", "dtype", "url", "setup_url", "home", "slug", "file",
    "submission_path", "oof_path",
}
_TOKEN = re.compile(r"\{\{|\}\}|\{(\d+)\}")
_local = threading.local()


def set_lang(lang: str | None) -> None:
    """요청을 처리하는 동안의 화면 언어 (서버가 요청마다 정한다)"""
    _local.lang = lang if lang in ("ko", "en") else "ko"


def current() -> str:
    return getattr(_local, "lang", "ko")


def _unescape(s: str) -> str:
    return s.replace("{{", "{").replace("}}", "}")


class Catalog:
    def __init__(self, data: dict[str, str]):
        self.exact: dict[str, str] = {}
        self.buckets: dict[str, list] = {}
        templates = []
        for ko, en in data.items():
            if not en:
                continue
            if re.search(r"\{\d+\}", ko):
                templates.append((ko, en))
            else:
                self.exact[_unescape(ko)] = _unescape(en)
        # 글자가 많이 고정된 틀부터 (더 구체적인 문장이 먼저 맞도록)
        templates.sort(key=lambda kv: -len(_TOKEN.sub("", kv[0])))
        self.affix = []  # (앞뒤에 다른 문장이 붙은 틀, 영어): 이어 붙인 문장을 풀 때
        for ko, en in templates:
            rx, first = self._compile(ko)
            self.buckets.setdefault(first, []).append((rx, en))
            if len(HANGUL.findall(_TOKEN.sub("", ko))) >= 4:
                core = rx.pattern
                self.affix.append((re.compile("(?P<_pre>.+?)" + core, re.S), re.compile(core + "(?P<_post>.+)", re.S), en))
        # 고정 문장: 긴 것부터 (끝·앞에 붙은 문장 찾기용)
        self.statics = sorted((k for k in self.exact if len(HANGUL.findall(k)) >= 4), key=len, reverse=True)

    def _fill(self, en: str, vals: dict, depth: int) -> str:
        def fill(t):
            tok = t.group(0)
            if tok == "{{":
                return "{"
            if tok == "}}":
                return "}"
            v = vals.get("p" + t.group(1), "")
            return self.tr(v, depth + 1) if depth < 4 else v
        return _TOKEN.sub(fill, en)

    def _affix(self, text: str, depth: int) -> str | None:
        """'앞부분 + 사전 문장' 또는 '사전 문장 + 뒷부분'으로 이어 붙인 문장. 모든 조각이 번역될 때만."""
        for k in self.statics:
            if len(k) >= len(text):
                continue
            if text.endswith(k):
                rest = self.tr(text[:-len(k)], depth + 1)
                if not HANGUL.search(rest):
                    return rest + self.exact[k]
            if text.startswith(k):
                rest = self.tr(text[len(k):], depth + 1)
                if not HANGUL.search(rest):
                    return self.exact[k] + rest
        for pre_rx, post_rx, en in self.affix:
            m = pre_rx.fullmatch(text)
            if m:
                rest = self.tr(m.group("_pre"), depth + 1)
                out = self._fill(en, m.groupdict(), depth)
                if not HANGUL.search(rest) and not HANGUL.search(out):
                    return rest + out
            m = post_rx.fullmatch(text)
            if m:
                rest = self.tr(m.group("_post"), depth + 1)
                out = self._fill(en, m.groupdict(), depth)
                if not HANGUL.search(rest) and not HANGUL.search(out):
                    return out + rest
        return None

    @staticmethod
    def _compile(ko: str):
        parts, seen, pos, first = [], set(), 0, "*"
        for m in _TOKEN.finditer(ko):
            lit = ko[pos:m.start()]
            if lit and pos == 0:
                first = lit[0]
            parts.append(re.escape(lit))
            tok = m.group(0)
            if tok == "{{":
                parts.append(r"\{"); first = first if pos else "{"
            elif tok == "}}":
                parts.append(r"\}")
            else:
                k = m.group(1)
                parts.append(f"(?P=p{k})" if k in seen else f"(?P<p{k}>.*?)")
                seen.add(k)
            pos = m.end()
        tail = ko[pos:]
        if pos == 0 and tail:
            first = tail[0]
        parts.append(re.escape(tail))
        return re.compile("".join(parts), re.S), first

    def tr(self, text: str, depth: int = 0) -> str:
        if not HANGUL.search(text):
            return text
        hit = self.exact.get(text)
        if hit is not None:
            return hit
        if depth < 4:  # 이어 붙인 문장·목록이면 조각마다 (값 자리가 쉼표를 넘어 엉뚱하게 맞는 일을 막음)
            split = self._split(text, depth)
            if split is not text:
                return split
        for bucket in (self.buckets.get(text[:1], ()), self.buckets.get("*", ())):
            for rx, en in bucket:
                m = rx.fullmatch(text)
                if m:
                    return self._fill(en, m.groupdict(), depth)
        if depth < 4:
            aff = self._affix(text, depth)
            if aff is not None:
                return aff
        return text

    @staticmethod
    def _parts(text: str, sep: str) -> list[str]:
        """괄호·따옴표 밖의 sep로만 나눈다"""
        out, buf, depth, i = [], [], 0, 0
        while i < len(text):
            c = text[i]
            if c in "([{":
                depth += 1
            elif c in ")]}":
                depth = max(0, depth - 1)
            if depth == 0 and text.startswith(sep, i):
                out.append("".join(buf)); buf = []; i += len(sep); continue
            buf.append(c); i += 1
        out.append("".join(buf))
        return out

    def _split(self, text: str, depth: int) -> str:
        """통째로 맞는 틀이 없을 때: 이어 붙인 문장을 문장·쉼표 단위로 나눠 각각 번역 (모두 번역될 때만)."""
        for sep, keep in ((". ", "."), (" · ", ""), (", ", ""), (": ", ""), ("\n", "")):
            parts = self._parts(text, sep)
            if len(parts) < 2:
                continue
            out = []
            for i, part in enumerate(parts):
                piece = part + (keep if keep and i < len(parts) - 1 else "")
                tr = self.tr(piece, depth + 1)
                if HANGUL.search(tr) and piece != part:  # 마침표를 뗀 채로 한 번 더
                    tr = self.tr(part, depth + 1) + keep
                if HANGUL.search(tr):
                    break
                out.append(tr[:-len(keep)] if keep and i < len(parts) - 1 and tr.endswith(keep) else tr)
            else:
                return sep.join(out)
        return text

    def translate(self, obj, key: str | None = None):
        if isinstance(obj, dict):
            return {k: (v if self._skip(k, v) else self.translate(v, k)) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.translate(v, key) for v in obj]
        if isinstance(obj, str):
            return self.tr(obj)
        return obj

    @staticmethod
    def _skip(key: str, value) -> bool:
        if key == "rows":  # 셀 값 격자(목록의 목록)만 데이터, 결과 표(목록의 사전)는 번역
            return isinstance(value, list) and bool(value) and isinstance(value[0], list)
        return key in SKIP_KEYS


_catalog: Catalog | None = None
_lock = threading.Lock()


def catalog() -> Catalog:
    global _catalog
    with _lock:
        if _catalog is None:
            try:
                data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                data = {}
            _catalog = Catalog(data)
        return _catalog


def tr(text: str) -> str:
    """지금 언어가 영어면 번역한 문장, 아니면 그대로."""
    return catalog().tr(text) if current() == "en" else text


def translate(obj, lang: str | None = None):
    """응답 전체를 번역 (데이터 필드는 그대로)."""
    if (lang or current()) != "en":
        return obj
    return catalog().translate(obj)
