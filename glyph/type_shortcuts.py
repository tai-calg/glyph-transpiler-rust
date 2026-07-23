from __future__ import annotations

import re


_TYPE_SHORTCUTS = {
    "F": "f32",
    "D": "f64",
    "U": "u16",
    "I": "i32",
    "B": "bool",
}
_SHORTCUT_TOKEN = re.compile(r"\b(?:F|D|U|I|B)\b")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def expand_type_name(name: str) -> str:
    """Expand one canonical Glyph shortcut without touching user-defined names."""

    return _TYPE_SHORTCUTS.get(name, name)


def expand_type_tokens(text: str) -> str:
    """Expand shortcut tokens in a type expression while preserving surrounding syntax."""

    return _SHORTCUT_TOKEN.sub(
        lambda match: _TYPE_SHORTCUTS[match.group(0)],
        text,
    )


def expand_type_words(text: str) -> str:
    """Expand shortcut words in a Protocol body without rewriting punctuation."""

    return _WORD.sub(
        lambda match: _TYPE_SHORTCUTS.get(match.group(0), match.group(0)),
        text,
    )
