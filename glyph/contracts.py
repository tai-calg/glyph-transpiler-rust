from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Callable

from .compiler import GlyphError


class ContractKind(str, Enum):
    WORLD = "world"
    PROTOCOL = "protocol"
    HANDLER = "handler"
    LAW = "law"
    BUNDLE = "bundle"


_KIND_MARKERS = {
    "@": ContractKind.WORLD,
    ">": ContractKind.PROTOCOL,
    "!": ContractKind.HANDLER,
    "?": ContractKind.LAW,
    "": ContractKind.BUNDLE,
}
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
_PATH_PART_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DECL_RE = re.compile(
    r"^'(?P<marker>[@>!?]?)(?P<name>[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?P<body>.*)$"
)
_APPLICATION_RE = re.compile(r"@\{(?P<body>.*?)\}", re.DOTALL)


@dataclass(frozen=True)
class ContractRef:
    name: str
    line: int
    column: int
    arguments: str | None = None
    call: str | None = None

    @property
    def external(self) -> bool:
        return "." in self.name

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "line": self.line,
            "column": self.column,
            "arguments": self.arguments,
            "call": self.call,
            "external": self.external,
        }


@dataclass(frozen=True)
class ContractDecl:
    name: str
    kind: ContractKind
    body: str
    refs: tuple[ContractRef, ...]
    line: int
    end_line: int

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "body": self.body,
            "refs": [ref.to_dict() for ref in self.refs],
            "line": self.line,
            "end_line": self.end_line,
        }


@dataclass(frozen=True)
class ContractApplication:
    refs: tuple[ContractRef, ...]
    line: int
    end_line: int

    def to_dict(self) -> dict[str, object]:
        return {
            "refs": [ref.to_dict() for ref in self.refs],
            "line": self.line,
            "end_line": self.end_line,
        }


@dataclass(frozen=True)
class ContractModel:
    declarations: tuple[ContractDecl, ...] = ()
    applications: tuple[ContractApplication, ...] = ()

    @classmethod
    def empty(cls) -> "ContractModel":
        return cls()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "glyph.contracts",
            "version": 1,
            "declarations": [decl.to_dict() for decl in self.declarations],
            "applications": [application.to_dict() for application in self.applications],
        }


@dataclass(frozen=True)
class ContractExtraction:
    source: str
    model: ContractModel


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].rstrip()


def _line_column(text: str, offset: int, base_line: int) -> tuple[int, int]:
    prefix = text[:offset]
    line = base_line + prefix.count("\n")
    last_newline = prefix.rfind("\n")
    column = offset + 1 if last_newline < 0 else offset - last_newline
    return line, column


def _take_balanced(
    text: str,
    start: int,
    left: str,
    right: str,
    line: int,
) -> tuple[str, int]:
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == left:
            depth += 1
        elif char == right:
            depth -= 1
            if depth == 0:
                return text[start : index + 1], index + 1
    raise GlyphError(
        f"{line}行目: Contract参照の '{left}' が '{right}' で閉じられていない"
    )


def _scan_refs(
    text: str,
    base_line: int,
) -> tuple[tuple[ContractRef, ...], tuple[tuple[int, int], ...]]:
    refs: list[ContractRef] = []
    spans: list[tuple[int, int]] = []
    index = 0
    while index < len(text):
        if text[index] != "'":
            index += 1
            continue

        start = index
        line, column = _line_column(text, start, base_line)
        index += 1
        if index >= len(text) or not (text[index].isalpha() or text[index] == "_"):
            raise GlyphError(f"{line}行目: Contract参照は 'Name の形式で記述する")

        parts: list[str] = []
        while True:
            match = _PATH_PART_RE.match(text, index)
            if match is None:
                raise GlyphError(f"{line}行目: 不正なContract名")
            parts.append(match.group(0))
            index = match.end()
            if index < len(text) and text[index] == ".":
                index += 1
                continue
            break

        arguments = None
        if index < len(text) and text[index] == "<":
            arguments, index = _take_balanced(text, index, "<", ">", line)

        call = None
        if index < len(text) and text[index] == "(":
            call, index = _take_balanced(text, index, "(", ")", line)

        refs.append(ContractRef(".".join(parts), line, column, arguments, call))
        spans.append((start, index))

    return tuple(refs), tuple(spans)


def _mask_spans(text: str, spans: tuple[tuple[int, int], ...]) -> str:
    chars = list(text)
    for start, end in spans:
        for index in range(start, end):
            if chars[index] != "\n":
                chars[index] = " "
    return "".join(chars)


def _validate_ref_list(
    text: str,
    base_line: int,
    context: str,
) -> tuple[ContractRef, ...]:
    refs, spans = _scan_refs(text, base_line)
    if not refs:
        raise GlyphError(
            f"{base_line}行目: {context}には少なくとも1個のContract参照が必要"
        )
    remainder = _mask_spans(text, spans)
    invalid = re.sub(r"[\s,{}]", "", remainder)
    if invalid:
        raise GlyphError(
            f"{base_line}行目: {context}には 'Name 形式のContract参照だけを記述する: "
            f"{invalid}"
        )
    return refs


def _reject_legacy_protocol_directions(body: str, line: int) -> None:
    if re.search(r"(?<![-=<>A-Za-z0-9_'])>\s*[A-Za-z_(]", body):
        raise GlyphError(
            f"{line}行目: Protocol送信は '>T' ではなく '-> T' と記述する"
        )
    if re.search(r"(?<![-=<>A-Za-z0-9_'])<\s*[A-Za-z_(]", body):
        raise GlyphError(
            f"{line}行目: Protocol受信は '<T' ではなく '<- T' と記述する"
        )


def _definition_block(lines: list[str], start: int) -> tuple[int, str]:
    header_code = _strip_comment(lines[start])
    match = _DECL_RE.match(header_code.strip())
    if match is None:
        raise GlyphError(
            f"{start + 1}行目: Contract定義は '@Name、'>Name、'!Name、'?Name、"
            "'Name のいずれかで始める"
        )

    first_body = match.group("body")
    body_lines = [first_body]
    cursor = start + 1
    brace_depth = first_body.count("{") - first_body.count("}")

    if brace_depth > 0:
        while cursor < len(lines) and brace_depth > 0:
            code = _strip_comment(lines[cursor])
            body_lines.append(code.strip())
            brace_depth += code.count("{") - code.count("}")
            cursor += 1
        if brace_depth != 0:
            raise GlyphError(f"{start + 1}行目: Bundle Contractの '}}' が不足している")
    else:
        while cursor < len(lines):
            candidate = lines[cursor]
            code = _strip_comment(candidate)
            if code.strip() and not code[:1].isspace():
                break
            if code[:1].isspace():
                body_lines.append(code.strip())
                cursor += 1
                continue
            break

    body = "\n".join(body_lines).strip()
    if not body:
        raise GlyphError(f"{start + 1}行目: Contract本体が空")
    return cursor, body


def _parse_declarations(source: str) -> tuple[str, tuple[ContractDecl, ...]]:
    had_final_newline = source.endswith("\n")
    lines = source.splitlines()
    declarations: list[ContractDecl] = []
    output = list(lines)
    index = 0

    while index < len(lines):
        original = lines[index]
        code = _strip_comment(original)
        stripped = code.strip()
        if not stripped.startswith("'"):
            index += 1
            continue
        if code[:1].isspace():
            raise GlyphError(f"{index + 1}行目: Contract定義はトップレベルに記述する")

        match = _DECL_RE.match(stripped)
        if match is None:
            raise GlyphError(
                f"{index + 1}行目: 不正なContract定義。'Name = ... の形式で記述する"
            )
        name = match.group("name")
        if not _NAME_RE.fullmatch(name):
            raise GlyphError(f"{index + 1}行目: 不正なContract名 '{name}'")
        kind = _KIND_MARKERS[match.group("marker")]
        end, body = _definition_block(lines, index)
        if kind is ContractKind.BUNDLE:
            if not (body.startswith("{") and body.endswith("}")):
                raise GlyphError(
                    f"{index + 1}行目: Bundle Contractは {{ 'Contract,... }} で記述する"
                )
            refs = _validate_ref_list(body, index + 1, "Bundle Contract")
        else:
            refs, _ = _scan_refs(body, index + 1)
            if kind is ContractKind.PROTOCOL:
                _reject_legacy_protocol_directions(body, index + 1)

        declarations.append(ContractDecl(name, kind, body, refs, index + 1, end))
        for line_index in range(index, end):
            output[line_index] = ""
        index = end

    rendered = "\n".join(output)
    if had_final_newline:
        rendered += "\n"
    return rendered, tuple(declarations)


def _parse_applications(source: str) -> tuple[str, tuple[ContractApplication, ...]]:
    applications: list[ContractApplication] = []
    chars = list(source)
    for match in _APPLICATION_RE.finditer(source):
        body = match.group("body")
        line = source.count("\n", 0, match.start()) + 1
        end_line = source.count("\n", 0, match.end()) + 1
        refs = _validate_ref_list(body, line, "Contract適用")
        applications.append(ContractApplication(refs, line, end_line))
        for index in range(match.start(), match.end()):
            if chars[index] != "\n":
                chars[index] = " "
    return "".join(chars), tuple(applications)


def _validate_model(model: ContractModel) -> None:
    symbols: dict[str, ContractDecl] = {}
    for declaration in model.declarations:
        previous = symbols.get(declaration.name)
        if previous is not None:
            raise GlyphError(
                f"{declaration.line}行目: Contract '{declaration.name}' は"
                f"{previous.line}行目で既に定義済み"
            )
        symbols[declaration.name] = declaration

    def require_reference(ref: ContractRef) -> ContractDecl | None:
        if ref.external:
            return None
        declaration = symbols.get(ref.name)
        if declaration is None:
            raise GlyphError(f"{ref.line}行目: 未定義Contract '{ref.name}'")
        return declaration

    for declaration in model.declarations:
        for ref in declaration.refs:
            target = require_reference(ref)
            if target is None or declaration.kind is ContractKind.BUNDLE:
                continue
            if target.kind is not declaration.kind:
                raise GlyphError(
                    f"{ref.line}行目: {declaration.kind.value} Contract "
                    f"'{declaration.name}' から{target.kind.value} Contract "
                    f"'{target.name}' は参照できない"
                )

    for application in model.applications:
        for ref in application.refs:
            require_reference(ref)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(name: str, stack: tuple[str, ...]) -> None:
        if name in visited:
            return
        if name in visiting:
            start = stack.index(name) if name in stack else 0
            cycle = (*stack[start:], name)
            raise GlyphError(f"Contract cycle: {' -> '.join(cycle)}")
        visiting.add(name)
        declaration = symbols[name]
        for ref in declaration.refs:
            if not ref.external and ref.name in symbols:
                visit(ref.name, (*stack, name))
        visiting.remove(name)
        visited.add(name)

    for name in symbols:
        visit(name, ())


def extract_contracts(source: str) -> ContractExtraction:
    if "'" not in source and "@{" not in source:
        return ContractExtraction(source, ContractModel.empty())
    without_declarations, declarations = _parse_declarations(source)
    stripped, applications = _parse_applications(without_declarations)
    model = ContractModel(declarations, applications)
    _validate_model(model)
    return ContractExtraction(stripped, model)


def remap_contract_lines(
    model: ContractModel,
    mapper: Callable[[int], int],
) -> ContractModel:
    def map_ref(ref: ContractRef) -> ContractRef:
        return ContractRef(ref.name, mapper(ref.line), ref.column, ref.arguments, ref.call)

    declarations = tuple(
        ContractDecl(
            declaration.name,
            declaration.kind,
            declaration.body,
            tuple(map_ref(ref) for ref in declaration.refs),
            mapper(declaration.line),
            mapper(declaration.end_line),
        )
        for declaration in model.declarations
    )
    applications = tuple(
        ContractApplication(
            tuple(map_ref(ref) for ref in application.refs),
            mapper(application.line),
            mapper(application.end_line),
        )
        for application in model.applications
    )
    return ContractModel(declarations, applications)
