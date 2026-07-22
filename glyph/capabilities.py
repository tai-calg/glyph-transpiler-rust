from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import Iterable, Mapping, Sequence

from .compiler import GlyphError, _find_matching, _find_top_level_char, _split_top_level


class CapabilityKind(str, Enum):
    PLAIN = "plain"
    OWN = "own"
    SHARE = "share"
    LINK = "link"
    BORROW = "borrow"
    BORROW_MUT = "borrow_mut"


_AFFINE = {
    CapabilityKind.OWN,
    CapabilityKind.SHARE,
    CapabilityKind.LINK,
}
_TYPE_PREFIXES = ("own", "share", "link")
_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_RESOURCE_RE = re.compile(
    rf"^resource\s+(?P<name>{_IDENT})(?P<params><[^>]+>)?\s*"
    r"\[(?P<states>.*)\]\s*$"
)
_NAME_PATH_RE = re.compile(rf"{_IDENT}(?:\.{_IDENT})*")
_CALL_RE = re.compile(rf"(?P<callee>{_IDENT})\s*\((?P<args>.*)\)\s*\??\s*$")
_BIND_RE = re.compile(rf"^(?P<name>{_IDENT})\s*:=\s*(?P<value>.*)$")
_AS_RE = re.compile(
    rf"^(?P<borrow>&\s*)?(?P<source>{_IDENT}(?:\.{_IDENT})*)"
    r"\s+as\s+(?P<target>share|link)\s*\??$"
)
_BORROW_RE = re.compile(
    rf"^&\s*(?P<mutable>mut\s+)?(?P<source>{_IDENT}(?:\.{_IDENT})*)$"
)


@dataclass(frozen=True)
class CapabilityType:
    capability: CapabilityKind
    name: str
    args: tuple["CapabilityType", ...] = ()
    state: str | None = None
    raw: str = ""

    @property
    def affine(self) -> bool:
        return self.capability in _AFFINE

    @property
    def borrowed(self) -> bool:
        return self.capability in {
            CapabilityKind.BORROW,
            CapabilityKind.BORROW_MUT,
        }

    def plain(self, resources: set[str]) -> str:
        if self.name == "result" and len(self.args) == 2:
            return f"{self.args[0].plain(resources)}|{self.args[1].plain(resources)}"
        if self.name == "tuple":
            return "(" + ",".join(arg.plain(resources) for arg in self.args) + ")"
        if self.name in resources:
            return self.name
        if self.args:
            return f"{self.name}<" + ",".join(
                arg.plain(resources) for arg in self.args
            ) + ">"
        return self.name

    def to_dict(self) -> dict[str, object]:
        return {
            "capability": self.capability.value,
            "name": self.name,
            "args": [arg.to_dict() for arg in self.args],
            "state": self.state,
            "raw": self.raw,
        }


@dataclass(frozen=True)
class ResourceDecl:
    name: str
    type_parameters: tuple[str, ...]
    states: tuple[str, ...]
    line: int

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type_parameters": list(self.type_parameters),
            "states": list(self.states),
            "line": self.line,
        }


@dataclass(frozen=True)
class CapabilityParam:
    name: str
    type: CapabilityType
    line: int

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": self.type.to_dict(),
            "line": self.line,
        }


@dataclass(frozen=True)
class CapabilityFunction:
    name: str
    marker: str
    params: tuple[CapabilityParam, ...]
    result: CapabilityType
    line: int
    body_start: int
    body_end: int

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "marker": self.marker,
            "params": [param.to_dict() for param in self.params],
            "result": self.result.to_dict(),
            "line": self.line,
            "body_start": self.body_start,
            "body_end": self.body_end,
        }


@dataclass(frozen=True)
class AggregateType:
    name: str
    members: tuple[CapabilityType, ...]
    line: int

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "members": [member.to_dict() for member in self.members],
            "line": self.line,
        }


@dataclass(frozen=True)
class CapabilityOperation:
    function: str
    kind: str
    source: str | None
    target: str | None
    capability: str | None
    line: int

    def to_dict(self) -> dict[str, object]:
        return {
            "function": self.function,
            "kind": self.kind,
            "source": self.source,
            "target": self.target,
            "capability": self.capability,
            "line": self.line,
        }


@dataclass(frozen=True)
class CapabilityModel:
    resources: tuple[ResourceDecl, ...] = ()
    functions: tuple[CapabilityFunction, ...] = ()
    aggregates: tuple[AggregateType, ...] = ()
    operations: tuple[CapabilityOperation, ...] = ()

    @classmethod
    def empty(cls) -> "CapabilityModel":
        return cls()

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "glyph.capability-ir",
            "version": 1,
            "resources": [item.to_dict() for item in self.resources],
            "functions": [item.to_dict() for item in self.functions],
            "aggregates": [item.to_dict() for item in self.aggregates],
            "operations": [item.to_dict() for item in self.operations],
        }


@dataclass(frozen=True)
class CapabilityExtraction:
    source: str
    model: CapabilityModel


def _strip_comment(line: str) -> tuple[str, str]:
    marker = line.find("#")
    if marker < 0:
        return line.rstrip(), ""
    return line[:marker].rstrip(), line[marker:]


def _split_type_result(text: str) -> tuple[str, str] | None:
    index = _find_top_level_char(text, "|")
    if index < 0:
        return None
    return text[:index].strip(), text[index + 1 :].strip()


def parse_capability_type(text: str) -> CapabilityType:
    raw = text.strip()
    if not raw:
        raise GlyphError("能力型が空")

    result = _split_type_result(raw)
    if result is not None:
        success, error = result
        if not success or not error:
            raise GlyphError(f"結果型は T|E の形式で記述する: {raw}")
        return CapabilityType(
            CapabilityKind.PLAIN,
            "result",
            (parse_capability_type(success), parse_capability_type(error)),
            raw=raw,
        )

    capability = CapabilityKind.PLAIN
    body = raw
    if body.startswith("&mut "):
        capability = CapabilityKind.BORROW_MUT
        body = body[5:].strip()
    elif body.startswith("&"):
        capability = CapabilityKind.BORROW
        body = body[1:].strip()
    else:
        for prefix in _TYPE_PREFIXES:
            token = prefix + " "
            if body.startswith(token):
                capability = CapabilityKind(prefix)
                body = body[len(token) :].strip()
                break

    if body.startswith("("):
        close = _find_matching(body, 0)
        if close == len(body) - 1:
            return CapabilityType(
                capability,
                "tuple",
                tuple(
                    parse_capability_type(part)
                    for part in _split_top_level(body[1:-1], ",")
                    if part
                ),
                raw=raw,
            )

    state = None
    if body.endswith("]"):
        open_state = body.rfind("[")
        if open_state <= 0:
            raise GlyphError(f"resource stateの '[' が不正: {raw}")
        state = body[open_state + 1 : -1].strip()
        body = body[:open_state].strip()
        if not state or not re.fullmatch(_IDENT, state):
            raise GlyphError(f"不正なresource state: {state}")

    args: tuple[CapabilityType, ...] = ()
    angle = body.find("<")
    if angle > 0:
        close = _find_matching(body, angle, "<", ">")
        if close != len(body) - 1:
            raise GlyphError(f"型の末尾に余分な文字がある: {raw}")
        name = body[:angle].strip()
        args = tuple(
            parse_capability_type(part)
            for part in _split_top_level(body[angle + 1 : close], ",")
            if part
        )
    else:
        name = body

    if not re.fullmatch(_IDENT, name):
        raise GlyphError(f"不正な型名: {name}")
    return CapabilityType(capability, name, args, state, raw)


def _validate_type(
    ty: CapabilityType,
    resources: Mapping[str, ResourceDecl],
    *,
    line: int,
    allow_borrow: bool,
    storage: bool,
) -> None:
    resource = resources.get(ty.name)
    if resource is not None:
        if ty.capability is CapabilityKind.PLAIN:
            raise GlyphError(
                f"{line}行目: resource型 '{ty.name}' には own/share/link/&/&mut の"
                "いずれかを明示する"
            )
        if ty.state is None:
            raise GlyphError(
                f"{line}行目: resource型 '{ty.name}' には [State] を明示する"
            )
        if ty.state not in resource.states:
            raise GlyphError(
                f"{line}行目: resource '{ty.name}' にstate '{ty.state}' はない"
            )
    elif ty.state is not None:
        raise GlyphError(
            f"{line}行目: resourceでない型 '{ty.name}' にstateは付けられない"
        )

    if ty.borrowed and not allow_borrow:
        raise GlyphError(f"{line}行目: この型位置には一時借用を保存できない")
    if storage and ty.borrowed:
        raise GlyphError(f"{line}行目: &T / &mut T はfieldやvariantへ保存できない")
    for arg in ty.args:
        _validate_type(
            arg,
            resources,
            line=line,
            allow_borrow=allow_borrow,
            storage=storage,
        )


def _parse_resource(
    stripped: str,
    line: int,
) -> ResourceDecl | None:
    match = _RESOURCE_RE.fullmatch(stripped)
    if match is None:
        return None
    parameters = ()
    if match.group("params"):
        parameters = tuple(
            item.strip()
            for item in match.group("params")[1:-1].split(",")
            if item.strip()
        )
        if not parameters or any(not re.fullmatch(_IDENT, item) for item in parameters):
            raise GlyphError(f"{line}行目: resource型引数が不正")
    states = tuple(
        item.strip() for item in match.group("states").split("|") if item.strip()
    )
    if not states:
        raise GlyphError(f"{line}行目: resourceには1個以上のstateが必要")
    if len(states) != len(set(states)):
        raise GlyphError(f"{line}行目: resource stateが重複")
    if any(not re.fullmatch(_IDENT, state) for state in states):
        raise GlyphError(f"{line}行目: resource state名が不正")
    return ResourceDecl(match.group("name"), parameters, states, line)


def _rewrite_fields(
    text: str,
    resources: Mapping[str, ResourceDecl],
    line: int,
    *,
    storage: bool,
) -> tuple[str, tuple[CapabilityParam, ...]]:
    if not text.strip():
        return "", ()
    output: list[str] = []
    params: list[CapabilityParam] = []
    pending: list[str] = []
    for part in _split_top_level(text, ","):
        item = part.strip()
        colon = _find_top_level_char(item, ":")
        if colon < 0:
            pending.append(item)
            continue
        name = item[:colon].strip()
        if not re.fullmatch(_IDENT, name):
            raise GlyphError(f"{line}行目: 不正なfield/parameter名 '{name}'")
        ty = parse_capability_type(item[colon + 1 :])
        _validate_type(
            ty,
            resources,
            line=line,
            allow_borrow=not storage,
            storage=storage,
        )
        names = [*pending, name]
        pending.clear()
        for item_name in names:
            output.append(f"{item_name}:{ty.plain(set(resources))}")
            params.append(CapabilityParam(item_name, ty, line))
    output.extend(pending)
    return ",".join(output), tuple(params)


def _rewrite_signature(
    stripped: str,
    resources: Mapping[str, ResourceDecl],
    line: int,
) -> tuple[str, CapabilityFunction]:
    marker = stripped[0]
    body = stripped[1:].strip()
    open_pos = body.find("(")
    if open_pos <= 0:
        raise GlyphError(f"{line}行目: name(args):type の形式が必要")
    close_pos = _find_matching(body, open_pos)
    name = body[:open_pos].strip()
    if not re.fullmatch(_IDENT, name):
        raise GlyphError(f"{line}行目: 不正な関数名 '{name}'")
    params_text, params = _rewrite_fields(
        body[open_pos + 1 : close_pos],
        resources,
        line,
        storage=False,
    )
    rest = body[close_pos + 1 :].strip()
    if not rest.startswith(":"):
        raise GlyphError(f"{line}行目: 戻り型の前に ':' が必要")
    typed = rest[1:].strip()
    equal = _find_top_level_char(typed, "=")
    if equal >= 0:
        return_text = typed[:equal].strip()
        expression = typed[equal + 1 :]
    else:
        return_text = typed
        expression = None
    result = parse_capability_type(return_text)
    _validate_type(
        result,
        resources,
        line=line,
        allow_borrow=False,
        storage=False,
    )
    rewritten = (
        marker
        + name
        + "("
        + params_text
        + "):"
        + result.plain(set(resources))
    )
    if expression is not None:
        rewritten += "=" + _erase_expression(expression)
    function = CapabilityFunction(
        name,
        marker,
        params,
        result,
        line,
        line,
        line,
    )
    return rewritten, function


def _rewrite_product(
    stripped: str,
    resources: Mapping[str, ResourceDecl],
    line: int,
) -> tuple[str, AggregateType]:
    open_pos = stripped.find("(")
    close_pos = _find_matching(stripped, open_pos)
    fields_text, fields = _rewrite_fields(
        stripped[open_pos + 1 : close_pos],
        resources,
        line,
        storage=True,
    )
    rewritten = stripped[: open_pos + 1] + fields_text + stripped[close_pos:]
    return rewritten, AggregateType(
        stripped[1:open_pos].strip(),
        tuple(field.type for field in fields),
        line,
    )


def _rewrite_sum(
    stripped: str,
    resources: Mapping[str, ResourceDecl],
    line: int,
) -> tuple[str, AggregateType]:
    equal = _find_top_level_char(stripped[1:], "=")
    if equal < 0:
        raise GlyphError(f"{line}行目: +Name=... の形式が必要")
    equal += 1
    name = stripped[1:equal].strip()
    variants = []
    members: list[CapabilityType] = []
    for variant in _split_top_level(stripped[equal + 1 :], "|"):
        item = variant.strip()
        if "(" in item:
            open_pos = item.find("(")
            close_pos = _find_matching(item, open_pos)
            rendered_args = []
            for arg in _split_top_level(item[open_pos + 1 : close_pos], ","):
                if not arg:
                    continue
                ty = parse_capability_type(arg)
                _validate_type(
                    ty,
                    resources,
                    line=line,
                    allow_borrow=False,
                    storage=True,
                )
                members.append(ty)
                rendered_args.append(ty.plain(set(resources)))
            item = item[: open_pos + 1] + ",".join(rendered_args) + item[close_pos:]
        elif "{" in item:
            open_pos = item.find("{")
            close_pos = _find_matching(item, open_pos, "{", "}")
            rendered, fields = _rewrite_fields(
                item[open_pos + 1 : close_pos],
                resources,
                line,
                storage=True,
            )
            members.extend(field.type for field in fields)
            item = item[: open_pos + 1] + rendered + item[close_pos:]
        variants.append(item)
    return (
        stripped[: equal + 1] + "|".join(variants),
        AggregateType(name, tuple(members), line),
    )


def _erase_expression(text: str) -> str:
    output = text

    def erase_prefix(pattern: str, value: str) -> str:
        return re.sub(
            pattern,
            lambda match: match.group("prefix") + match.group("name"),
            value,
        )

    prefix = r"(?P<prefix>^|[(,=])\s*"
    name = rf"(?P<name>{_IDENT}(?:\.{_IDENT})*)"
    output = erase_prefix(prefix + r"&\s*mut\s+" + name, output)
    output = erase_prefix(
        prefix + r"&\s*" + name + r"\s+as\s+(?:share|link)",
        output,
    )
    output = re.sub(
        rf"\b({_IDENT}(?:\.{_IDENT})*)\s+as\s+(?:share|link)\b",
        r"\1",
        output,
    )
    output = erase_prefix(prefix + r"&\s*" + name, output)
    return output


def _line_function_spans(
    lines: Sequence[str],
    functions: Sequence[CapabilityFunction],
) -> dict[str, tuple[int, int]]:
    starts = sorted((function.line, function.name) for function in functions)
    spans: dict[str, tuple[int, int]] = {}
    for index, (line, name) in enumerate(starts):
        end = len(lines)
        for candidate in range(line, len(lines)):
            code, _ = _strip_comment(lines[candidate])
            if code.strip() and not code[:1].isspace():
                end = candidate
                break
        spans[name] = (line, end)
    return spans


def _names(text: str) -> Iterable[str]:
    return re.findall(_IDENT, text)


def _root_name(text: str) -> str | None:
    match = _NAME_PATH_RE.fullmatch(text.strip())
    if match is None:
        return None
    return text.strip().split(".", 1)[0]


def _call(text: str) -> tuple[str, list[str]] | None:
    match = _CALL_RE.fullmatch(text.strip())
    if match is None:
        return None
    try:
        args = [
            item.strip()
            for item in _split_top_level(match.group("args"), ",")
            if item.strip()
        ]
    except GlyphError:
        return None
    return match.group("callee"), args


def _contains_resource(
    ty: CapabilityType,
    expected: CapabilityType,
    aggregates: Mapping[str, AggregateType],
    seen: set[str] | None = None,
) -> bool:
    if (
        ty.capability is CapabilityKind.OWN
        and ty.name == expected.name
        and ty.state == expected.state
    ):
        return True
    if ty.name == "result":
        return any(_contains_resource(arg, expected, aggregates, seen) for arg in ty.args)
    if ty.args and any(
        _contains_resource(arg, expected, aggregates, seen) for arg in ty.args
    ):
        return True
    aggregate = aggregates.get(ty.name)
    if aggregate is None:
        return False
    visited = set() if seen is None else set(seen)
    if ty.name in visited:
        return False
    visited.add(ty.name)
    return any(
        _contains_resource(member, expected, aggregates, visited)
        for member in aggregate.members
    )


def _validate_failure_resources(model: CapabilityModel) -> None:
    aggregates = {item.name: item for item in model.aggregates}
    resources = {item.name for item in model.resources}
    for function in model.functions:
        own_resources = [
            param.type
            for param in function.params
            if param.type.capability is CapabilityKind.OWN
            and param.type.name in resources
        ]
        if not own_resources or function.result.name != "result":
            continue
        error_type = function.result.args[1]
        for resource in own_resources:
            if not _contains_resource(error_type, resource, aggregates):
                raise GlyphError(
                    f"{function.line}行目: '{function.name}' の失敗型は"
                    f" own {resource.name}[{resource.state}] を保持しなければならない"
                )


@dataclass
class _FlowValue:
    type: CapabilityType
    available: bool = True


class _FlowAnalyzer:
    def __init__(
        self,
        model: CapabilityModel,
        source: str,
    ):
        self.model = model
        self.lines = source.splitlines()
        self.signatures = {function.name: function for function in model.functions}
        self.resources = {resource.name for resource in model.resources}
        self.operations: list[CapabilityOperation] = []

    def analyze(self) -> tuple[CapabilityOperation, ...]:
        spans = _line_function_spans(self.lines, self.model.functions)
        for function in self.model.functions:
            start, end = spans.get(function.name, (function.line, function.line))
            self._function(function, start, end)
        return tuple(self.operations)

    def _use(self, values: Mapping[str, _FlowValue], name: str, line: int) -> None:
        value = values.get(name)
        if value is not None and not value.available:
            raise GlyphError(
                f"{line}行目: 能力値 '{name}' はmove後に使用できない"
            )

    def _move(
        self,
        values: dict[str, _FlowValue],
        name: str,
        line: int,
        function: str,
        target: str | None = None,
    ) -> CapabilityType | None:
        value = values.get(name)
        if value is None:
            return None
        self._use(values, name, line)
        if value.type.affine:
            value.available = False
            self.operations.append(
                CapabilityOperation(
                    function,
                    "move",
                    name,
                    target,
                    value.type.capability.value,
                    line,
                )
            )
        return value.type

    def _as(
        self,
        values: dict[str, _FlowValue],
        expression: str,
        line: int,
        function: str,
        target_name: str | None,
    ) -> CapabilityType | None:
        match = _AS_RE.fullmatch(expression.strip().strip("()"))
        if match is None:
            return None
        source = match.group("source").split(".", 1)[0]
        self._use(values, source, line)
        value = values.get(source)
        if value is None:
            return None
        target = CapabilityKind(match.group("target"))
        borrowed = match.group("borrow") is not None
        allowed = (
            (not borrowed and value.type.capability is CapabilityKind.OWN and target is CapabilityKind.SHARE)
            or (
                borrowed
                and value.type.capability is CapabilityKind.SHARE
                and target in {CapabilityKind.SHARE, CapabilityKind.LINK}
            )
            or (
                borrowed
                and value.type.capability is CapabilityKind.LINK
                and target in {CapabilityKind.SHARE, CapabilityKind.LINK}
            )
        )
        if not allowed:
            raise GlyphError(
                f"{line}行目: {value.type.capability.value} から"
                f" {'&' if borrowed else ''}as {target.value} へ変換できない"
            )
        if not borrowed:
            self._move(values, source, line, function, target_name)
        converted = CapabilityType(
            target,
            value.type.name,
            value.type.args,
            value.type.state,
            expression.strip(),
        )
        self.operations.append(
            CapabilityOperation(
                function,
                "capability_cast",
                source,
                target_name,
                target.value,
                line,
            )
        )
        return converted

    def _expression(
        self,
        values: dict[str, _FlowValue],
        expression: str,
        line: int,
        function: CapabilityFunction,
        *,
        consume_result: bool,
        target_name: str | None = None,
    ) -> CapabilityType | None:
        stripped = expression.strip()
        cast = self._as(values, stripped, line, function.name, target_name)
        if cast is not None:
            return cast

        borrow = _BORROW_RE.fullmatch(stripped.strip("()"))
        if borrow is not None:
            source = borrow.group("source").split(".", 1)[0]
            self._use(values, source, line)
            value = values.get(source)
            if value is None:
                return None
            mutable = borrow.group("mutable") is not None
            if mutable and value.type.capability in {
                CapabilityKind.SHARE,
                CapabilityKind.LINK,
            }:
                raise GlyphError(
                    f"{line}行目: {value.type.capability.value}値 '{source}' から"
                    " &mut を取得できない"
                )
            if target_name is not None:
                raise GlyphError(
                    f"{line}行目: 一時借用を中間値 '{target_name}' へ保存できない"
                )
            self.operations.append(
                CapabilityOperation(
                    function.name,
                    "borrow_mut" if mutable else "borrow",
                    source,
                    None,
                    None,
                    line,
                )
            )
            return CapabilityType(
                CapabilityKind.BORROW_MUT if mutable else CapabilityKind.BORROW,
                value.type.name,
                value.type.args,
                value.type.state,
                stripped,
            )

        call = _call(stripped.rstrip("?"))
        if call is not None:
            callee_name, args = call
            callee = self.signatures.get(callee_name)
            for index, argument in enumerate(args):
                borrowed_argument = _BORROW_RE.fullmatch(argument.strip())
                root = (
                    borrowed_argument.group("source").split(".", 1)[0]
                    if borrowed_argument is not None
                    else _root_name(argument)
                )
                if root is None:
                    for name in _names(argument):
                        self._use(values, name, line)
                    continue
                self._use(values, root, line)
                expected = (
                    callee.params[index].type
                    if callee is not None and index < len(callee.params)
                    else None
                )
                if expected is not None and expected.borrowed:
                    if borrowed_argument is None:
                        raise GlyphError(
                            f"{line}行目: '{callee_name}' の引数{index + 1}には"
                            f" {expected.capability.value} が必要"
                        )
                    mutable = borrowed_argument.group("mutable") is not None
                    if (
                        expected.capability is CapabilityKind.BORROW_MUT
                        and not mutable
                    ):
                        raise GlyphError(
                            f"{line}行目: '{callee_name}' の引数{index + 1}には &mut が必要"
                        )
                    source_value = values.get(root)
                    if (
                        mutable
                        and source_value is not None
                        and source_value.type.capability
                        in {CapabilityKind.SHARE, CapabilityKind.LINK}
                    ):
                        raise GlyphError(
                            f"{line}行目: {source_value.type.capability.value}値"
                            f" '{root}' から &mut を取得できない"
                        )
                    continue
                if expected is not None and expected.affine:
                    self._move(values, root, line, function.name)
            return None if callee is None else callee.result

        root = _root_name(stripped)
        if root is not None:
            self._use(values, root, line)
            value = values.get(root)
            if value is not None and consume_result:
                return self._move(
                    values,
                    root,
                    line,
                    function.name,
                    target_name,
                )
            return None if value is None else value.type

        for name in _names(stripped):
            self._use(values, name, line)
        return None

    def _function(
        self,
        function: CapabilityFunction,
        start: int,
        end: int,
    ) -> None:
        initial = {
            param.name: _FlowValue(param.type)
            for param in function.params
            if param.type.capability is not CapabilityKind.PLAIN
        }
        if not initial:
            return

        header = self.lines[function.line - 1]
        code, _ = _strip_comment(header)
        inline_equal = _find_top_level_char(code, "=")
        if inline_equal >= 0:
            values = {name: _FlowValue(value.type) for name, value in initial.items()}
            self._expression(
                values,
                code[inline_equal + 1 :],
                function.line,
                function,
                consume_result=True,
            )
            self._check_obligations(values, function, function.line)
            return

        body = [
            (index + 1, _strip_comment(self.lines[index])[0].strip())
            for index in range(start, end)
            if _strip_comment(self.lines[index])[0].strip()
            and self.lines[index][:1].isspace()
        ]
        if not body:
            return
        if all(">>" in text for _, text in body):
            for line, clause in body:
                _, value = clause.split(">>", 1)
                values = {
                    name: _FlowValue(item.type)
                    for name, item in initial.items()
                }
                self._expression(
                    values,
                    value,
                    line,
                    function,
                    consume_result=True,
                )
                self._check_obligations(values, function, line)
            return

        values = {name: _FlowValue(value.type) for name, value in initial.items()}
        for position, (line, statement) in enumerate(body):
            binding = _BIND_RE.fullmatch(statement)
            if binding is not None:
                target = binding.group("name")
                inferred = self._expression(
                    values,
                    binding.group("value"),
                    line,
                    function,
                    consume_result=True,
                    target_name=target,
                )
                if inferred is not None:
                    values[target] = _FlowValue(inferred)
                continue
            final = position == len(body) - 1
            self._expression(
                values,
                statement,
                line,
                function,
                consume_result=final,
            )
        self._check_obligations(values, function, body[-1][0])

    def _check_obligations(
        self,
        values: Mapping[str, _FlowValue],
        function: CapabilityFunction,
        line: int,
    ) -> None:
        for name, value in values.items():
            if (
                value.type.capability is CapabilityKind.OWN
                and value.type.name in self.resources
                and value.available
            ):
                raise GlyphError(
                    f"{line}行目: resource obligation '{name}:own "
                    f"{value.type.name}[{value.type.state}]' が未処理"
                )


def extract_capabilities(source: str) -> CapabilityExtraction:
    if not any(
        token in source
        for token in ("resource ", "own ", "share ", "link ", "&mut ", " as ")
    ):
        return CapabilityExtraction(source, CapabilityModel.empty())

    had_final_newline = source.endswith("\n")
    lines = source.splitlines()
    resources: list[ResourceDecl] = []
    resource_names: dict[str, ResourceDecl] = {}

    for index, original in enumerate(lines):
        code, _ = _strip_comment(original)
        if code[:1].isspace():
            continue
        declaration = _parse_resource(code.strip(), index + 1)
        if declaration is None:
            continue
        if declaration.name in resource_names:
            raise GlyphError(
                f"{index + 1}行目: resource '{declaration.name}' は"
                f"{resource_names[declaration.name].line}行目で既に定義済み"
            )
        resources.append(declaration)
        resource_names[declaration.name] = declaration

    output = list(lines)
    functions: list[CapabilityFunction] = []
    aggregates: list[AggregateType] = []

    for index, original in enumerate(lines):
        code, comment = _strip_comment(original)
        if not code.strip():
            continue
        indent = code[: len(code) - len(code.lstrip())]
        stripped = code.strip()
        declaration = _parse_resource(stripped, index + 1)
        if declaration is not None:
            output[index] = indent + f"*{declaration.name}()" + (
                (" " + comment) if comment else ""
            )
            continue
        if indent:
            output[index] = indent + _erase_expression(stripped) + (
                (" " + comment) if comment else ""
            )
            continue
        if stripped.startswith("*"):
            rewritten, aggregate = _rewrite_product(
                stripped,
                resource_names,
                index + 1,
            )
            aggregates.append(aggregate)
            output[index] = rewritten + ((" " + comment) if comment else "")
            continue
        if stripped.startswith("+"):
            rewritten, aggregate = _rewrite_sum(
                stripped,
                resource_names,
                index + 1,
            )
            aggregates.append(aggregate)
            output[index] = rewritten + ((" " + comment) if comment else "")
            continue
        if stripped.startswith((">", "!", "~")):
            rewritten, function = _rewrite_signature(
                stripped,
                resource_names,
                index + 1,
            )
            functions.append(function)
            output[index] = rewritten + ((" " + comment) if comment else "")
            continue
        if stripped.startswith("="):
            equal = _find_top_level_char(stripped[1:], "=")
            if equal >= 0:
                equal += 1
                ty = parse_capability_type(stripped[equal + 1 :])
                _validate_type(
                    ty,
                    resource_names,
                    line=index + 1,
                    allow_borrow=False,
                    storage=True,
                )
                output[index] = (
                    stripped[: equal + 1]
                    + ty.plain(set(resource_names))
                    + ((" " + comment) if comment else "")
                )
            continue
        output[index] = _erase_expression(stripped) + (
            (" " + comment) if comment else ""
        )

    preliminary = CapabilityModel(
        tuple(resources),
        tuple(functions),
        tuple(aggregates),
        (),
    )
    _validate_failure_resources(preliminary)
    operations = _FlowAnalyzer(preliminary, source).analyze()
    model = CapabilityModel(
        preliminary.resources,
        preliminary.functions,
        preliminary.aggregates,
        operations,
    )
    rendered = "\n".join(output)
    if had_final_newline:
        rendered += "\n"
    return CapabilityExtraction(rendered, model)
