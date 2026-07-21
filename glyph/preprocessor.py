from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass, replace
import re
from typing import Any, Mapping, Sequence, TypeVar

from .compiler import GlyphError


_RAW_NAME_RE = re.compile(r"[A-Z][A-Z0-9_]*\Z")
_IDENTIFIER_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_MAX_EXPANSION_DEPTH = 64
_MAX_EXPANDED_LINES = 50_000
_MAX_EXPANDED_CHARS = 2_000_000


@dataclass(frozen=True)
class RawMacroDef:
    name: str
    body: tuple[str, ...]
    line: int
    end_line: int
    multiline: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "body": list(self.body),
            "line": self.line,
            "end_line": self.end_line,
            "multiline": self.multiline,
        }


@dataclass(frozen=True)
class PreprocessorLine:
    expanded_line: int
    source_line: int
    macro_stack: tuple[str, ...] = ()
    definition_lines: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class PreprocessResult:
    source: str
    macros: tuple[RawMacroDef, ...]
    lines: tuple[PreprocessorLine, ...]

    @property
    def changed(self) -> bool:
        return bool(self.macros)

    def source_line(self, expanded_line: int) -> int:
        if 1 <= expanded_line <= len(self.lines):
            return self.lines[expanded_line - 1].source_line
        return expanded_line

    def remap_error(self, error: GlyphError) -> GlyphError:
        def substitute(match: re.Match[str]) -> str:
            return f"{self.source_line(int(match.group(1)))}行目"

        message = re.sub(r"(?<![A-Za-z0-9_])(\d+)行目", substitute, str(error))
        return GlyphError(message)

    def map_dict(self, source_name: str = "input.glyph") -> dict[str, object]:
        return {
            "schema": "glyph.preprocessor-map",
            "version": 1,
            "source": source_name,
            "macros": [macro.to_dict() for macro in self.macros],
            "expanded_lines": [line.to_dict() for line in self.lines],
        }


@dataclass(frozen=True)
class _SourceLine:
    text: str
    source_line: int


@dataclass(frozen=True)
class _ResolvedLine:
    text: str
    macro_stack: tuple[str, ...]
    definition_lines: tuple[int, ...]


def _split_comment(line: str) -> tuple[str, str]:
    marker = line.find("#")
    if marker < 0:
        return line, ""
    return line[:marker], line[marker:]


def _dedent(lines: Sequence[str]) -> tuple[str, ...]:
    nonempty = [line for line in lines if line.strip()]
    if not nonempty:
        return tuple("" for _ in lines)
    width = min(len(line) - len(line.lstrip(" \t")) for line in nonempty)
    return tuple(line[width:] if line.strip() else "" for line in lines)


def _raw_name(name: str, line: int) -> str:
    if not _RAW_NAME_RE.fullmatch(name):
        raise GlyphError(
            f"{line}行目: rawマクロ名は大文字で始まり、"
            "大文字・数字・'_'だけを使う: "
            f"'{name}'"
        )
    return name


def _function_like_name(body: str) -> str | None:
    open_pos = body.find("(")
    eq_pos = body.find("=")
    if open_pos <= 0 or eq_pos < open_pos:
        return None
    name = body[:open_pos].strip()
    return name if name.isidentifier() else None


def _collect_definitions(source: str) -> tuple[dict[str, RawMacroDef], list[_SourceLine]]:
    raw_lines = source.splitlines()
    definitions: dict[str, RawMacroDef] = {}
    ast_macro_lines: dict[str, int] = {}
    remaining: list[_SourceLine] = []
    index = 0

    while index < len(raw_lines):
        original = raw_lines[index]
        code, _ = _split_comment(original)
        stripped = code.strip()
        if code[:1].isspace() or not stripped.startswith("@"):
            remaining.append(_SourceLine(original, index + 1))
            index += 1
            continue

        body = stripped[1:].strip()
        if body == "end":
            raise GlyphError(f"{index + 1}行目: 対応する複数行rawマクロのない '@end'")

        function_name = _function_like_name(body)
        if function_name is not None:
            if function_name in definitions:
                raise GlyphError(
                    f"{index + 1}行目: ASTマクロ '{function_name}' は"
                    f"{definitions[function_name].line}行目のrawマクロと衝突"
                )
            ast_macro_lines.setdefault(function_name, index + 1)
            remaining.append(_SourceLine(original, index + 1))
            index += 1
            continue

        equal = body.find("=")
        if equal >= 0:
            name = _raw_name(body[:equal].strip(), index + 1)
            replacement = body[equal + 1 :].strip()
            if not replacement:
                raise GlyphError(f"{index + 1}行目: rawマクロ '{name}' の置換文字列が空")
            if name in definitions:
                raise GlyphError(
                    f"{index + 1}行目: rawマクロ '{name}' は"
                    f"{definitions[name].line}行目で既に定義済み"
                )
            if name in ast_macro_lines:
                raise GlyphError(
                    f"{index + 1}行目: rawマクロ '{name}' は"
                    f"{ast_macro_lines[name]}行目のASTマクロと衝突"
                )
            definitions[name] = RawMacroDef(
                name, (replacement,), index + 1, index + 1, False
            )
            index += 1
            continue

        name = _raw_name(body, index + 1)
        if name in definitions:
            raise GlyphError(
                f"{index + 1}行目: rawマクロ '{name}' は"
                f"{definitions[name].line}行目で既に定義済み"
            )
        if name in ast_macro_lines:
            raise GlyphError(
                f"{index + 1}行目: rawマクロ '{name}' は"
                f"{ast_macro_lines[name]}行目のASTマクロと衝突"
            )

        start = index + 1
        cursor = start
        body_lines: list[str] = []
        while cursor < len(raw_lines):
            candidate_code, _ = _split_comment(raw_lines[cursor])
            if not candidate_code[:1].isspace() and candidate_code.strip() == "@end":
                break
            body_lines.append(raw_lines[cursor])
            cursor += 1
        if cursor >= len(raw_lines):
            raise GlyphError(
                f"{index + 1}行目: 複数行rawマクロ '{name}' を '@end' で閉じる"
            )
        if not any(line.strip() for line in body_lines):
            raise GlyphError(f"{index + 1}行目: 複数行rawマクロ '{name}' の本体が空")
        definitions[name] = RawMacroDef(
            name,
            _dedent(body_lines),
            index + 1,
            cursor + 1,
            True,
        )
        index = cursor + 1

    return definitions, remaining


class _Expander:
    def __init__(self, definitions: Mapping[str, RawMacroDef]):
        self.definitions = definitions
        self.resolved: dict[str, tuple[_ResolvedLine, ...]] = {}

    def resolve(self, name: str, stack: tuple[str, ...]) -> tuple[_ResolvedLine, ...]:
        cached = self.resolved.get(name)
        if cached is not None:
            return cached
        if name in stack:
            start = stack.index(name)
            cycle = (*stack[start:], name)
            raise GlyphError(f"raw macro cycle: {' -> '.join(cycle)}")
        if len(stack) >= _MAX_EXPANSION_DEPTH:
            raise GlyphError(
                f"rawマクロ展開の深さが上限{_MAX_EXPANSION_DEPTH}を超えた: "
                + " -> ".join((*stack, name))
            )

        definition = self.definitions[name]
        current_stack = (*stack, name)
        output: list[_ResolvedLine] = []
        for offset, line in enumerate(definition.body):
            output.extend(
                self.expand_line(
                    line,
                    definition.line + offset + (1 if definition.multiline else 0),
                    current_stack,
                )
            )
        self._check_size(output, definition.line)
        result = tuple(output)
        self.resolved[name] = result
        return result

    def expand_line(
        self, line: str, line_number: int, stack: tuple[str, ...]
    ) -> list[_ResolvedLine]:
        code, comment = _split_comment(line)
        stripped = code.strip()
        leading = code[: len(code) - len(code.lstrip(" \t"))]

        if stripped in self.definitions:
            name = stripped
            replacement = self.resolve(name, stack)
            combined_stack = list(stack)
            combined_definitions = [
                self.definitions[item].line
                for item in stack
                if item in self.definitions
            ]
            result: list[_ResolvedLine] = []
            if comment:
                result.append(
                    _ResolvedLine(
                        leading + comment,
                        tuple(combined_stack),
                        tuple(combined_definitions),
                    )
                )
            for item in replacement:
                for macro_name in item.macro_stack:
                    if macro_name not in combined_stack:
                        combined_stack.append(macro_name)
                for definition_line in item.definition_lines:
                    if definition_line not in combined_definitions:
                        combined_definitions.append(definition_line)
                text = leading + item.text if item.text else ""
                result.append(
                    _ResolvedLine(
                        text,
                        tuple(combined_stack),
                        tuple(combined_definitions),
                    )
                )
            return result

        stacks: list[str] = list(stack)
        definition_lines: list[int] = [
            self.definitions[item].line
            for item in stack
            if item in self.definitions
        ]
        output: list[str] = []
        cursor = 0
        for match in _IDENTIFIER_RE.finditer(code):
            output.append(code[cursor : match.start()])
            token = match.group(0)
            if token not in self.definitions:
                output.append(token)
                cursor = match.end()
                continue
            definition = self.definitions[token]
            replacement = self.resolve(token, stack)
            if definition.multiline or len(replacement) != 1:
                raise GlyphError(
                    f"{line_number}行目: 複数行rawマクロ '{token}' は"
                    "インデントされた行に単独で置く"
                )
            item = replacement[0]
            output.append(item.text)
            for macro_name in item.macro_stack:
                if macro_name not in stacks:
                    stacks.append(macro_name)
            for definition_line in item.definition_lines:
                if definition_line not in definition_lines:
                    definition_lines.append(definition_line)
            cursor = match.end()
        output.append(code[cursor:])

        for macro_name in stacks:
            definition = self.definitions.get(macro_name)
            if definition is not None and definition.line not in definition_lines:
                definition_lines.append(definition.line)
        return [
            _ResolvedLine(
                "".join(output) + comment,
                tuple(stacks),
                tuple(definition_lines),
            )
        ]

    @staticmethod
    def _check_size(lines: Sequence[_ResolvedLine], line: int) -> None:
        if len(lines) > _MAX_EXPANDED_LINES:
            raise GlyphError(
                f"{line}行目: rawマクロ展開が{_MAX_EXPANDED_LINES}行を超えた"
            )
        if sum(len(item.text) for item in lines) > _MAX_EXPANDED_CHARS:
            raise GlyphError(
                f"{line}行目: rawマクロ展開が{_MAX_EXPANDED_CHARS}文字を超えた"
            )


def preprocess_source(source: str) -> PreprocessResult:
    """Expand uppercase raw macros before every Glyph parser and lowering pass."""

    definitions, remaining = _collect_definitions(source)
    expander = _Expander(definitions)

    # Resolve unused definitions too, so cycles and illegal nested block placement are
    # deterministic and independent of which compiler path references a macro.
    for name in definitions:
        expander.resolve(name, ())

    output: list[str] = []
    mappings: list[PreprocessorLine] = []
    for item in remaining:
        expanded = expander.expand_line(item.text, item.source_line, ())
        for line in expanded:
            output.append(line.text)
            mappings.append(
                PreprocessorLine(
                    len(output),
                    item.source_line,
                    line.macro_stack,
                    line.definition_lines,
                )
            )
            if len(output) > _MAX_EXPANDED_LINES:
                raise GlyphError(
                    f"{item.source_line}行目: プリプロセス結果が"
                    f"{_MAX_EXPANDED_LINES}行を超えた"
                )
    if sum(len(line) for line in output) > _MAX_EXPANDED_CHARS:
        raise GlyphError(
            f"プリプロセス結果が{_MAX_EXPANDED_CHARS}文字を超えた"
        )

    suffix = "\n" if source.endswith("\n") else ""
    return PreprocessResult(
        "\n".join(output) + suffix,
        tuple(definitions.values()),
        tuple(mappings),
    )


T = TypeVar("T")


def remap_source_lines(value: T, preprocess: PreprocessResult) -> T:
    """Recursively remap dataclass fields named `line` or `*_line` to source lines."""

    def visit(item: Any) -> Any:
        if is_dataclass(item) and not isinstance(item, type):
            updates: dict[str, Any] = {}
            for field in fields(item):
                current = getattr(item, field.name)
                if (
                    isinstance(current, int)
                    and (field.name == "line" or field.name.endswith("_line"))
                ):
                    updates[field.name] = preprocess.source_line(current)
                else:
                    updates[field.name] = visit(current)
            return replace(item, **updates)
        if isinstance(item, tuple):
            return tuple(visit(element) for element in item)
        if isinstance(item, list):
            return [visit(element) for element in item]
        if isinstance(item, dict):
            return {key: visit(element) for key, element in item.items()}
        return item

    return visit(value)
