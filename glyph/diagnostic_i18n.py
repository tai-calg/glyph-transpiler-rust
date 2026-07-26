from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any


_LINE_PREFIX = re.compile(r"^(?:line\s+)?(\d+)(?::|\s+-)\s*(.+)$", re.IGNORECASE)
_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^unexpected\s+(.+)$", re.IGNORECASE), "予期しない {0}"),
    (re.compile(r"^expected\s+(.+?),\s*(?:but\s+)?got\s+(.+)$", re.IGNORECASE), "{0} が必要だが、{1} が指定されている"),
    (re.compile(r"^expected\s+(.+)$", re.IGNORECASE), "{0} が必要"),
    (re.compile(r"^missing\s+(.+)$", re.IGNORECASE), "{0} が不足している"),
    (re.compile(r"^unknown\s+(.+)$", re.IGNORECASE), "未定義の {0}"),
    (re.compile(r"^invalid\s+(.+)$", re.IGNORECASE), "不正な {0}"),
    (re.compile(r"^unsupported\s+(.+)$", re.IGNORECASE), "未対応の {0}"),
    (re.compile(r"^duplicate\s+(.+)$", re.IGNORECASE), "{0} が重複している"),
    (re.compile(r"^(.+?)\s+not\s+found$", re.IGNORECASE), "{0} が見つからない"),
    (re.compile(r"^no\s+(.+?)\s+found$", re.IGNORECASE), "{0} が見つからない"),
    (re.compile(r"^(.+?)\s+is\s+not\s+defined$", re.IGNORECASE), "{0} は定義されていない"),
    (re.compile(r"^(.+?)\s+is\s+already\s+defined$", re.IGNORECASE), "{0} はすでに定義されている"),
    (re.compile(r"^(.+?)\s+already\s+exists$", re.IGNORECASE), "{0} はすでに存在する"),
    (re.compile(r"^(.+?)\s+is\s+unreachable$", re.IGNORECASE), "{0} は到達不能"),
    (re.compile(r"^unreachable\s+(.+)$", re.IGNORECASE), "到達不能な {0}"),
    (re.compile(r"^(.+?)\s+is\s+required$", re.IGNORECASE), "{0} が必要"),
    (re.compile(r"^(.+?)\s+must\s+be\s+(.+)$", re.IGNORECASE), "{0} は {1} でなければならない"),
    (re.compile(r"^(.+?)\s+must\s+contain\s+(.+)$", re.IGNORECASE), "{0} には {1} が必要"),
    (re.compile(r"^(.+?)\s+has\s+no\s+(.+)$", re.IGNORECASE), "{0} に {1} がない"),
    (re.compile(r"^(.+?)\s+conflicts\s+with\s+(.+)$", re.IGNORECASE), "{0} は {1} と競合する"),
    (re.compile(r"^cannot\s+(.+)$", re.IGNORECASE), "{0} できない"),
    (re.compile(r"^failed\s+to\s+(.+)$", re.IGNORECASE), "{0} に失敗した"),
)

_PHRASES: tuple[tuple[str, str], ...] = (
    ("closing parenthesis", "閉じ丸括弧"),
    ("opening parenthesis", "開き丸括弧"),
    ("closing brace", "閉じ波括弧"),
    ("opening brace", "開き波括弧"),
    ("closing bracket", "閉じ角括弧"),
    ("opening bracket", "開き角括弧"),
    ("state transition", "状態遷移"),
    ("state machine", "状態機械"),
    ("initial state", "初期状態"),
    ("reachable state", "到達可能状態"),
    ("unreachable state", "到達不能状態"),
    ("source state", "遷移元状態"),
    ("target state", "遷移先状態"),
    ("return type", "戻り値型"),
    ("argument type", "引数型"),
    ("type annotation", "型注釈"),
    ("system declaration", "system 宣言"),
    ("machine declaration", "machine 宣言"),
    ("function declaration", "関数宣言"),
    ("resource declaration", "resource 宣言"),
    ("external declaration", "external 宣言"),
    ("fallthrough branch", "フォールスルー分岐"),
    ("fallthrough", "フォールスルー"),
    ("wildcard", "ワイルドカード"),
    ("identifier", "識別子"),
    ("expression", "式"),
    ("statement", "文"),
    ("declaration", "宣言"),
    ("transition", "遷移"),
    ("condition", "条件"),
    ("action", "アクション"),
    ("handler", "ハンドラ"),
    ("resource", "資源"),
    ("capability", "能力"),
    ("protocol", "プロトコル"),
    ("contract", "契約"),
    ("function", "関数"),
    ("machine", "machine"),
    ("system", "system"),
    ("type", "型"),
    ("value", "値"),
    ("branch", "分岐"),
    ("warning", "警告"),
    ("error", "エラー"),
)


def _translate_fragment(value: str) -> str:
    translated = value
    for source, target in _PHRASES:
        translated = re.sub(re.escape(source), target, translated, flags=re.IGNORECASE)
    return translated


def translate_diagnostic_message(message: str) -> str:
    """Translate a compiler or analysis diagnostic while preserving identifiers.

    The translator is deterministic and intentionally conservative. Backtick-
    delimited identifiers, source fragments, and numeric values remain unchanged.
    Unmatched messages keep their original text rather than inventing a meaning.
    """

    original = str(message)
    stripped = original.strip()
    if not stripped:
        return original
    if re.search(r"[ぁ-んァ-ヶ一-龠]", stripped):
        return original

    line_match = _LINE_PREFIX.fullmatch(stripped)
    if line_match:
        line, body = line_match.groups()
        return f"{line}行目: {translate_diagnostic_message(body)}"

    for pattern, template in _PATTERNS:
        match = pattern.fullmatch(stripped)
        if not match:
            continue
        fragments = tuple(_translate_fragment(group.strip()) for group in match.groups())
        return template.format(*fragments)

    translated = _translate_fragment(stripped)
    return translated if translated != stripped else original


def localize_diagnostic(item: Mapping[str, Any]) -> dict[str, Any]:
    """Return one diagnostic with stable English and Japanese message fields."""

    result = dict(item)
    message = str(result.get("message", ""))
    result.setdefault("message_en", message)
    result.setdefault("message_ja", translate_diagnostic_message(message))
    return result


def localize_diagnostics(items: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [localize_diagnostic(item) for item in items]


def localize_message_payload(value: Any) -> Any:
    """Recursively add bilingual fields to mappings that contain ``message``."""

    if isinstance(value, Mapping):
        localized = {key: localize_message_payload(item) for key, item in value.items()}
        if "message" in localized and isinstance(localized["message"], str):
            localized = localize_diagnostic(localized)
        return localized
    if isinstance(value, list):
        return [localize_message_payload(item) for item in value]
    if isinstance(value, tuple):
        return [localize_message_payload(item) for item in value]
    return value
