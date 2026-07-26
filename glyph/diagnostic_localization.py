from __future__ import annotations

from copy import deepcopy
import re
from typing import Mapping


_BACKTICK = re.compile(r"`([^`]+)`")
_UNREACHABLE_STATE = re.compile(
    r"state\s+(?P<state>\S+)\s+is unreachable from initial state\s+(?P<initial>\S+)"
)
_LINE_PREFIX = re.compile(r"^(?:line\s+)?(?P<line>\d+)(?::(?P<column>\d+))?:\s*(?P<body>.*)$", re.IGNORECASE)


def _quoted(message: str) -> str:
    match = _BACKTICK.search(message)
    return match.group(1) if match else "この条件"


def _compile_error_ja(message: str) -> str:
    """Translate stable compiler-error shapes and preserve unknown technical detail."""

    prefix = ""
    body = message.strip()
    line = _LINE_PREFIX.match(body)
    if line:
        location = f"{line.group('line')}行目"
        if line.group("column"):
            location += f"・{line.group('column')}列目"
        prefix = location + ": "
        body = line.group("body")

    replacements: tuple[tuple[str, str], ...] = (
        ("unexpected end of input", "入力の途中でコードが終了しています"),
        ("unexpected token", "予期しない記号があります"),
        ("unknown declaration", "認識できない宣言があります"),
        ("unknown name", "未定義の名前が参照されています"),
        ("is not defined", "が定義されていません"),
        ("expected expression", "式が必要です"),
        ("expected type", "型が必要です"),
        ("expected identifier", "名前が必要です"),
        ("missing fallback", "default節がありません"),
        ("missing default", "default節がありません"),
        ("unterminated", "閉じられていない構文があります"),
        ("cannot infer", "型または意味を推論できません"),
        ("type mismatch", "型が一致しません"),
        ("duplicate", "重複した定義があります"),
    )
    lowered = body.lower()
    for needle, translated in replacements:
        if needle in lowered:
            return f"{prefix}{translated}。詳細: {body}"
    return f"{prefix}Glyphコードをコンパイルできません。詳細: {body}"


def _messages(code: str, message: str) -> tuple[str, str, str | None, str | None]:
    expression = _quoted(message)
    if code == "GLYPH_COMPILE_ERROR":
        return (
            _compile_error_ja(message),
            message,
            "エラー位置の周辺で、括弧、型、名前、分岐の`>>`、default節を確認してください。",
            "Check brackets, types, names, branch `>>` syntax, and the default branch near the reported location.",
        )
    if code == "GLYPH_SOURCE_READ_ERROR":
        return (
            f"Glyphファイルを読み込めません。詳細: {message}",
            message,
            "ファイルの存在、アクセス権、他のアプリによるロックを確認してください。",
            "Check that the file exists, is readable, and is not locked by another application.",
        )
    if code == "STIR_TRIGGER_AMBIGUOUS_FALLBACK":
        return (
            f"`{expression}` が出来事なのか継続中の条件なのか、コードだけでは確定できません。図では暫定的に入力として表示します。",
            message,
            "出来事を明確にする場合は、Boolではなく有限の直和型でイベントを表してください。",
            "Represent occurrences with a finite sum type instead of a Boolean value.",
        )
    if code == "STIR_MULTIPLE_TRIGGER_CANDIDATES":
        return (
            "複数の入力由来条件がありますが、どれが遷移を開始する出来事か確定できません。ひとつの暫定入力として表示します。",
            message,
            "出来事をevent型へまとめ、追加条件をBoolとして分離すると警告を解消できます。",
            "Model the occurrence as one event value and keep additional conditions as Booleans.",
        )
    if code == "STIR_MIXED_TRIGGER_GUARD_PREDICATE":
        return (
            f"`{expression}` は入力と状態または未解決値の両方に依存しています。図では暫定的に入力として表示します。",
            message,
            "入力イベントの判別と、状態に対する許可条件を別の論理項へ分けてください。",
            "Separate the input event discriminator from state-dependent permission conditions.",
        )
    if code == "STIR_CONDITION_PROVENANCE_UNKNOWN":
        return (
            f"`{expression}` の型またはデータの由来を追跡できないため、入力とガード条件を分類できません。",
            message,
            "引数、局所値、またはpure関数の戻り型が明確か確認してください。",
            "Check that the parameter, local value, or pure function return type is resolvable.",
        )
    if code == "STIR_MULTIPLE_CONFIRMED_TRIGGERS":
        return (
            "ひとつの遷移条件に複数のイベント判別が含まれています。複合した暫定入力として表示します。",
            message,
            "同時イベントが必要なら複合イベント型として表し、それ以外は状態またはBool条件へ分離してください。",
            "Use one composite event type for simultaneous occurrences, or move the other condition into state/guard data.",
        )
    if code == "unreachable-state":
        match = _UNREACHABLE_STATE.search(message)
        if match:
            state = match.group("state")
            initial = match.group("initial")
            return (
                f"状態 `{state}` は初期状態 `{initial}` から到達できません。",
                message,
                "遷移条件または初期状態を確認してください。",
                "Check the transition conditions or the initial state.",
            )
        return (
            "初期状態から到達できない状態があります。",
            message,
            "遷移条件または初期状態を確認してください。",
            "Check the transition conditions or the initial state.",
        )
    if code in {"unreachable-branch", "unreachable-guard-branch"}:
        return (
            "それより前の分岐ですでに条件が網羅されているため、この分岐には到達できません。",
            message,
            "分岐の順序、重複条件、またはdefault節を確認してください。",
            "Check branch order, duplicate conditions, or the default branch.",
        )
    if code in {"missing-default", "missing-fallback"}:
        return (
            "条件分岐にdefault節がありません。入力によっては結果が決まりません。",
            message,
            "最後に `_` 節を追加してください。",
            "Add a final `_` branch.",
        )
    return (message, message, None, None)


def localize_diagnostic(diagnostic: Mapping[str, object]) -> dict[str, object]:
    """Attach Japanese and English presentation text without changing semantics."""

    result = dict(diagnostic)
    code = str(result.get("code", ""))
    original = str(result.get("message", ""))
    ja, en, help_ja, help_en = _messages(code, original)
    result["message_ja"] = ja
    result["message_en"] = en
    if help_ja:
        result["help_ja"] = help_ja
    if help_en:
        result["help_en"] = help_en
    return result


def localize_state_views(views: Mapping[str, object]) -> dict[str, object]:
    """Return a copy whose machine diagnostics carry both supported locales."""

    result = deepcopy(dict(views))
    state = dict(result.get("state", {}))
    machines = []
    for original in state.get("machines", []):
        machine = dict(original)
        machine["diagnostics"] = [
            localize_diagnostic(item) for item in machine.get("diagnostics", [])
        ]
        transitions = []
        for original_transition in machine.get("transitions", []):
            transition = dict(original_transition)
            transition["diagnostics"] = [
                localize_diagnostic(item)
                for item in transition.get("diagnostics", [])
            ]
            transitions.append(transition)
        machine["transitions"] = transitions
        machines.append(machine)
    state["machines"] = machines
    result["state"] = state
    result["locales"] = {
        "default": "ja",
        "supported": ["ja", "en"],
    }
    return result
