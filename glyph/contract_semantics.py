from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, Mapping, Sequence

from .capabilities import (
    CapabilityFunction,
    CapabilityKind,
    CapabilityModel,
    CapabilityType,
)
from .compiler import (
    BinaryExpr,
    CallExpr,
    Expr,
    ExternDecl,
    FieldExpr,
    FunctionDecl,
    GlyphError,
    NameExpr,
    Program,
    TryExpr,
    TypeRef,
    UnaryExpr,
    _find_matching,
    _split_top_level,
)
from .contracts import ContractDecl, ContractKind, ContractModel, ContractRef
from .semantic import render_type
from .temporal import (
    Always,
    And,
    Atom,
    Eventually,
    Formula,
    Implies,
    Not,
    Or,
    Until,
    Within,
    parse_formula,
)


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_WORLD_RE = re.compile(
    rf"^(?P<locus>{_IDENT})\s*\*\s*"
    rf"(?P<region>{_IDENT}(?:/{_IDENT})*)$"
)
_DURATION_RE = re.compile(r"^[1-9][0-9]*(?:ms|s|m)$")
_INTEGER_RE = re.compile(r"^[0-9]+$")


@dataclass(frozen=True)
class WorldContract:
    name: str
    locus: str
    region: tuple[str, ...]
    line: int

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "locus": self.locus,
            "region": list(self.region),
            "line": self.line,
        }


@dataclass(frozen=True)
class ProtocolNode:
    kind: str
    type_name: str | None = None
    children: tuple["ProtocolNode", ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "type": self.type_name,
            "children": [child.to_dict() for child in self.children],
        }

    def first_send(self) -> str | None:
        if self.kind == "send":
            return self.type_name
        for child in self.children:
            value = child.first_send()
            if value is not None:
                return value
        return None

    def first_receive(self) -> str | None:
        if self.kind == "receive":
            return self.type_name
        for child in self.children:
            value = child.first_receive()
            if value is not None:
                return value
        return None


@dataclass(frozen=True)
class ProtocolContract:
    name: str
    root: ProtocolNode
    line: int

    def to_dict(self) -> dict[str, object]:
        return {"name": self.name, "root": self.root.to_dict(), "line": self.line}


@dataclass(frozen=True)
class HandlerStep:
    operation: str
    arguments: tuple[str, ...]
    verification: str
    line: int

    def to_dict(self) -> dict[str, object]:
        return {
            "operation": self.operation,
            "arguments": list(self.arguments),
            "verification": self.verification,
            "line": self.line,
        }


@dataclass(frozen=True)
class HandlerContract:
    name: str
    steps: tuple[HandlerStep, ...]
    line: int

    @property
    def retries(self) -> bool:
        return any(step.operation == "retry" for step in self.steps)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "steps": [step.to_dict() for step in self.steps],
            "line": self.line,
        }


@dataclass(frozen=True)
class LawContract:
    name: str
    formula: dict[str, object]
    verification: str
    line: int

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "formula": self.formula,
            "verification": self.verification,
            "line": self.line,
        }


@dataclass(frozen=True)
class ContractRow:
    world: str | None = None
    protocol: str | None = None
    handler: str | None = None
    laws: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "world": self.world,
            "protocol": self.protocol,
            "handler": self.handler,
            "laws": list(self.laws),
        }


@dataclass(frozen=True)
class AppliedContract:
    target: str
    target_kind: str
    row: ContractRow
    line: int

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "target_kind": self.target_kind,
            "row": self.row.to_dict(),
            "line": self.line,
        }


@dataclass(frozen=True)
class ContractSemanticModel:
    worlds: tuple[WorldContract, ...] = ()
    protocols: tuple[ProtocolContract, ...] = ()
    handlers: tuple[HandlerContract, ...] = ()
    laws: tuple[LawContract, ...] = ()
    rows: tuple[tuple[str, ContractRow], ...] = ()
    applications: tuple[AppliedContract, ...] = ()

    @classmethod
    def empty(cls) -> "ContractSemanticModel":
        return cls()

    def row(self, name: str) -> ContractRow | None:
        return dict(self.rows).get(name)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": "glyph.runtime-contract-ir",
            "version": 1,
            "worlds": [item.to_dict() for item in self.worlds],
            "protocols": [item.to_dict() for item in self.protocols],
            "handlers": [item.to_dict() for item in self.handlers],
            "laws": [item.to_dict() for item in self.laws],
            "rows": [
                {"name": name, "row": row.to_dict()} for name, row in self.rows
            ],
            "applications": [item.to_dict() for item in self.applications],
        }


def _balanced_outer(text: str) -> bool:
    if not (text.startswith("(") and text.endswith(")")):
        return False
    try:
        return _find_matching(text, 0) == len(text) - 1
    except GlyphError:
        return False


def _find_protocol_operator(text: str, operator: str) -> int:
    round_depth = angle_depth = square_depth = 0
    index = 0
    while index <= len(text) - len(operator):
        char = text[index]
        if char == "(":
            round_depth += 1
        elif char == ")":
            round_depth -= 1
        elif char == "<" and not text.startswith("<-", index):
            angle_depth += 1
        elif char == ">" and angle_depth:
            angle_depth -= 1
        elif char == "[":
            square_depth += 1
        elif char == "]":
            square_depth -= 1
        if (
            round_depth == 0
            and angle_depth == 0
            and square_depth == 0
            and text.startswith(operator, index)
        ):
            if operator == "|" and text.startswith("||", index):
                index += 2
                continue
            return index
        index += 1
    return -1


def parse_protocol(text: str, line: int) -> ProtocolNode:
    value = text.strip()
    if not value:
        raise GlyphError(f"{line}行目: Protocol本体が空")
    while _balanced_outer(value):
        value = value[1:-1].strip()
    if value == "()":
        return ProtocolNode("end")

    for operator, kind in (("|", "choice"), ("||", "parallel"), (">>", "sequence")):
        index = _find_protocol_operator(value, operator)
        if index >= 0:
            left = parse_protocol(value[:index], line)
            right = parse_protocol(value[index + len(operator) :], line)
            return ProtocolNode(kind, children=(left, right))

    if value.startswith("*"):
        body = value[1:].strip()
        if not body:
            raise GlyphError(f"{line}行目: '*' の後ろにProtocolが必要")
        return ProtocolNode("repeat", children=(parse_protocol(body, line),))
    if value.startswith("->"):
        type_name = value[2:].strip()
        if not type_name:
            raise GlyphError(f"{line}行目: '->' の後ろに型が必要")
        return ProtocolNode("send", type_name=type_name)
    if value.startswith("<-"):
        type_name = value[2:].strip()
        if not type_name:
            raise GlyphError(f"{line}行目: '<-' の後ろに型が必要")
        return ProtocolNode("receive", type_name=type_name)
    raise GlyphError(
        f"{line}行目: Protocolは -> T / <- T / >> / | / || / * / () で記述する: {value}"
    )


def _base_type_name(text: str) -> str:
    value = text.strip()
    for prefix in ("own ", "share ", "link ", "&mut ", "&"):
        if value.startswith(prefix):
            value = value[len(prefix) :].strip()
            break
    result_index = _find_protocol_operator(value, "|")
    if result_index >= 0:
        value = value[:result_index].strip()
    state = value.rfind("[")
    if state > 0 and value.endswith("]"):
        value = value[:state].strip()
    generic = value.find("<")
    if generic > 0:
        value = value[:generic].strip()
    return value


def _call_arguments(call: str | None) -> tuple[str, ...]:
    if not call:
        return ()
    body = call[1:-1]
    return tuple(item.strip() for item in _split_top_level(body, ",") if item.strip())


def _external_step(ref: ContractRef) -> tuple[HandlerStep, ...]:
    operation = ref.name.rsplit(".", 1)[-1]
    args = _call_arguments(ref.call)
    if operation == "compose":
        steps: list[HandlerStep] = []
        for argument in args:
            match = re.fullmatch(
                rf"'(?P<name>{_IDENT}(?:\.{_IDENT})*)(?P<call>\(.*\))?",
                argument,
            )
            if match is None:
                raise GlyphError(
                    f"{ref.line}行目: std.composeの各要素はContract参照にする"
                )
            nested = ContractRef(
                match.group("name"),
                ref.line,
                ref.column,
                None,
                match.group("call"),
            )
            steps.extend(_external_step(nested))
        return tuple(steps)

    verification = "trusted"
    if operation in {"timeout", "cancel"}:
        verification = "runtime"
    elif operation in {"return_error", "fallback"}:
        verification = "static"
    elif operation in {"retry", "rollback", "compensate"}:
        verification = "static+trusted"

    if operation == "timeout":
        if len(args) != 1 or _DURATION_RE.fullmatch(args[0]) is None:
            raise GlyphError(f"{ref.line}行目: std.timeoutには正のDurationを1個渡す")
    elif operation == "retry":
        if len(args) != 3 or _INTEGER_RE.fullmatch(args[0]) is None:
            raise GlyphError(
                f"{ref.line}行目: std.retryは回数、backoff、idempotencyを受け取る"
            )
        idempotency = args[2].replace(" ", "")
        if not (
            idempotency.endswith("std.idempotent")
            or "std.key(" in idempotency
        ):
            raise GlyphError(
                f"{ref.line}行目: retryには 'std.idempotent または 'std.key(Type) が必要"
            )
    elif operation in {"rollback", "compensate", "fallback"}:
        if len(args) != 1:
            raise GlyphError(f"{ref.line}行目: std.{operation}には対象を1個渡す")
    elif operation in {"return_error", "cancel"}:
        if operation == "return_error" and args:
            raise GlyphError(f"{ref.line}行目: std.return_errorは引数を取らない")
    else:
        # Extension handlers remain typed external Contract operations. They are not
        # silently treated as language keywords and are verified by their library adapter.
        verification = "trusted"
    return (HandlerStep(operation, args, verification, ref.line),)


def _formula_dict(formula: Formula) -> dict[str, object]:
    if isinstance(formula, Atom):
        return {"kind": "atom", "expression": repr(formula.expr)}
    if isinstance(formula, Not):
        return {"kind": "not", "value": _formula_dict(formula.value)}
    if isinstance(formula, And):
        return {
            "kind": "and",
            "left": _formula_dict(formula.left),
            "right": _formula_dict(formula.right),
        }
    if isinstance(formula, Or):
        return {
            "kind": "or",
            "left": _formula_dict(formula.left),
            "right": _formula_dict(formula.right),
        }
    if isinstance(formula, Implies):
        return {
            "kind": "implies",
            "premise": _formula_dict(formula.premise),
            "consequence": _formula_dict(formula.consequence),
        }
    if isinstance(formula, Always):
        return {"kind": "always", "value": _formula_dict(formula.value)}
    if isinstance(formula, Eventually):
        return {"kind": "eventually", "value": _formula_dict(formula.value)}
    if isinstance(formula, Within):
        return {
            "kind": "within",
            "milliseconds": formula.milliseconds,
            "value": _formula_dict(formula.value),
        }
    if isinstance(formula, Until):
        return {
            "kind": "weak_until" if formula.weak else "until",
            "hold": _formula_dict(formula.hold),
            "target": _formula_dict(formula.target),
        }
    raise TypeError(f"unknown formula: {formula!r}")


def _law_formula(body: str, line: int) -> tuple[dict[str, object], str]:
    normalized = body.replace("@A", "□").replace("@E", "◇")
    formula = parse_formula(normalized)
    verification = "model"
    if isinstance(formula, (Always, Within)):
        verification = "model+runtime"
    return _formula_dict(formula), verification


def _merge_rows(left: ContractRow, right: ContractRow, line: int) -> ContractRow:
    def single(kind: str, a: str | None, b: str | None) -> str | None:
        if a is not None and b is not None and a != b:
            raise GlyphError(
                f"{line}行目: Bundle内で{kind} Contract '{a}' と '{b}' が競合"
            )
        return a or b

    return ContractRow(
        single("World", left.world, right.world),
        single("Protocol", left.protocol, right.protocol),
        single("Handler", left.handler, right.handler),
        tuple(dict.fromkeys((*left.laws, *right.laws))),
    )


def _declaration_targets(source: str) -> list[tuple[int, str, str]]:
    targets: list[tuple[int, str, str]] = []
    for line_no, original in enumerate(source.splitlines(), start=1):
        code = original.split("#", 1)[0].rstrip()
        if not code.strip() or code[:1].isspace():
            continue
        stripped = code.strip()
        if stripped.startswith("resource "):
            match = re.match(rf"resource\s+({_IDENT})", stripped)
            if match:
                targets.append((line_no, match.group(1), "resource"))
            continue
        marker = stripped[0]
        body = stripped[1:].strip()
        if marker in "*+=>!~":
            match = re.match(rf"({_IDENT})", body)
            if match:
                kind = {
                    "*": "product",
                    "+": "sum",
                    "=": "alias",
                    ">": "function",
                    "!": "effect",
                    "~": "opaque",
                }[marker]
                targets.append((line_no, match.group(1), kind))
    return targets


def _target_for_application(
    line: int,
    targets: Sequence[tuple[int, str, str]],
) -> tuple[str, str]:
    candidates = [item for item in targets if item[0] <= line]
    if not candidates:
        raise GlyphError(f"{line}行目: Contract適用対象の宣言がない")
    _, name, kind = candidates[-1]
    return name, kind


def _walk(expr: Expr) -> Iterable[Expr]:
    yield expr
    if isinstance(expr, UnaryExpr):
        yield from _walk(expr.expr)
    elif isinstance(expr, TryExpr):
        yield from _walk(expr.expr)
    elif isinstance(expr, BinaryExpr):
        yield from _walk(expr.left)
        yield from _walk(expr.right)
    elif isinstance(expr, FieldExpr):
        yield from _walk(expr.base)
    elif isinstance(expr, CallExpr):
        yield from _walk(expr.callee)
        for argument in expr.args:
            yield from _walk(argument)


def _function_roots(function: FunctionDecl) -> tuple[Expr, ...]:
    if function.expression is not None:
        return (function.expression,)
    roots: list[Expr] = []
    for guard in function.guards:
        if guard.condition is not None:
            roots.append(guard.condition)
        roots.append(guard.value)
    return tuple(roots)


def _plain_function_types(program: Program) -> dict[str, tuple[tuple[TypeRef, ...], TypeRef]]:
    result: dict[str, tuple[tuple[TypeRef, ...], TypeRef]] = {}
    for declaration in program.declarations:
        if isinstance(declaration, (FunctionDecl, ExternDecl)):
            result[declaration.name] = (
                tuple(param.ty for param in declaration.params),
                declaration.return_type,
            )
    return result


def _validate_protocol_signature(
    application: AppliedContract,
    protocol: ProtocolContract,
    capability_functions: Mapping[str, CapabilityFunction],
    plain_functions: Mapping[str, tuple[tuple[TypeRef, ...], TypeRef]],
) -> None:
    if application.target_kind not in {"function", "effect", "opaque"}:
        return
    send = protocol.root.first_send()
    receive = protocol.root.first_receive()
    capability = capability_functions.get(application.target)
    if capability is not None:
        if send is not None and capability.params:
            actual = _base_type_name(capability.params[0].type.raw)
            expected = _base_type_name(send)
            if actual != expected:
                raise GlyphError(
                    f"{application.line}行目: Protocol '{protocol.name}' は {expected} を送るが"
                    f" '{application.target}' の先頭引数は {actual}"
                )
        if receive is not None:
            actual = _base_type_name(capability.result.raw)
            expected = _base_type_name(receive)
            if actual != expected:
                raise GlyphError(
                    f"{application.line}行目: Protocol '{protocol.name}' は {expected} を返すが"
                    f" '{application.target}' の戻り型は {actual}"
                )
        return

    plain = plain_functions.get(application.target)
    if plain is None:
        return
    params, result = plain
    if send is not None and params:
        actual = params[0].name
        expected = _base_type_name(send)
        if actual != expected:
            raise GlyphError(
                f"{application.line}行目: Protocol '{protocol.name}' の送信型 {expected} と"
                f" '{application.target}' の先頭引数型 {actual} が一致しない"
            )
    if receive is not None:
        actual = result.name
        expected = _base_type_name(receive)
        if actual != expected:
            raise GlyphError(
                f"{application.line}行目: Protocol '{protocol.name}' の受信型 {expected} と"
                f" '{application.target}' の戻り型 {actual} が一致しない"
            )


def _validate_handler(
    application: AppliedContract,
    handler: HandlerContract,
    capability_functions: Mapping[str, CapabilityFunction],
    resources: set[str],
) -> None:
    function = capability_functions.get(application.target)
    if function is None:
        return
    for step in handler.steps:
        if step.operation == "retry":
            if function.result.name != "result":
                raise GlyphError(
                    f"{application.line}行目: retry対象 '{function.name}' はResultを返す必要がある"
                )
        if step.operation == "rollback":
            place = step.arguments[0].lstrip("'").strip()
            param = next((item for item in function.params if item.name == place), None)
            if (
                param is None
                or param.type.capability is not CapabilityKind.OWN
                or param.type.name not in resources
            ):
                raise GlyphError(
                    f"{application.line}行目: rollback対象 '{place}' はown resource引数でなければならない"
                )


def _validate_world_calls(
    program: Program,
    applications: Mapping[str, AppliedContract],
    worlds: Mapping[str, WorldContract],
    capability_functions: Mapping[str, CapabilityFunction],
) -> None:
    functions = {
        item.name: item for item in program.declarations if isinstance(item, FunctionDecl)
    }
    for caller_name, caller in functions.items():
        caller_application = applications.get(caller_name)
        if caller_application is None or caller_application.row.world is None:
            continue
        caller_world = worlds[caller_application.row.world]
        for root in _function_roots(caller):
            for expression in _walk(root):
                if not (
                    isinstance(expression, CallExpr)
                    and isinstance(expression.callee, NameExpr)
                ):
                    continue
                callee_name = expression.callee.name
                callee_application = applications.get(callee_name)
                if callee_application is None or callee_application.row.world is None:
                    continue
                callee_world = worlds[callee_application.row.world]
                if caller_world.locus == callee_world.locus:
                    continue
                if callee_application.row.protocol is None:
                    raise GlyphError(
                        f"{caller.line}行目: {caller_world.locus}から{callee_world.locus}の"
                        f" '{callee_name}' をProtocolなしで直接呼び出せない"
                    )
                capability = capability_functions.get(callee_name)
                if capability is not None and any(
                    param.type.borrowed for param in capability.params
                ):
                    raise GlyphError(
                        f"{caller.line}行目: 異なるWorldへ &T / &mut T を転送できない"
                    )


def build_contract_semantics(
    source: str,
    contracts: ContractModel,
    capabilities: CapabilityModel,
    program: Program,
) -> ContractSemanticModel:
    if not contracts.declarations and not contracts.applications:
        return ContractSemanticModel.empty()

    declarations = {item.name: item for item in contracts.declarations}
    worlds: dict[str, WorldContract] = {}
    protocols: dict[str, ProtocolContract] = {}
    handlers: dict[str, HandlerContract] = {}
    laws: dict[str, LawContract] = {}

    def handler_steps(declaration: ContractDecl, stack: tuple[str, ...]) -> tuple[HandlerStep, ...]:
        if declaration.name in stack:
            raise GlyphError(f"Handler cycle: {' -> '.join((*stack, declaration.name))}")
        steps: list[HandlerStep] = []
        for ref in declaration.refs:
            if ref.external:
                steps.extend(_external_step(ref))
                continue
            target = declarations[ref.name]
            if target.kind is not ContractKind.HANDLER:
                raise GlyphError(
                    f"{ref.line}行目: Handlerから{target.kind.value} Contractは参照できない"
                )
            steps.extend(handler_steps(target, (*stack, declaration.name)))
        if not steps:
            raise GlyphError(
                f"{declaration.line}行目: Handler '{declaration.name}' に処理がない"
            )
        return tuple(steps)

    for declaration in contracts.declarations:
        if declaration.kind is ContractKind.WORLD:
            match = _WORLD_RE.fullmatch(declaration.body.replace("\n", " ").strip())
            if match is None:
                raise GlyphError(
                    f"{declaration.line}行目: Worldは Locus * Region/Path で記述する"
                )
            worlds[declaration.name] = WorldContract(
                declaration.name,
                match.group("locus"),
                tuple(match.group("region").split("/")),
                declaration.line,
            )
        elif declaration.kind is ContractKind.PROTOCOL:
            protocols[declaration.name] = ProtocolContract(
                declaration.name,
                parse_protocol(declaration.body.replace("\n", " "), declaration.line),
                declaration.line,
            )
        elif declaration.kind is ContractKind.HANDLER:
            handlers[declaration.name] = HandlerContract(
                declaration.name,
                handler_steps(declaration, ()),
                declaration.line,
            )
        elif declaration.kind is ContractKind.LAW:
            formula, verification = _law_formula(declaration.body, declaration.line)
            laws[declaration.name] = LawContract(
                declaration.name,
                formula,
                verification,
                declaration.line,
            )

    rows: dict[str, ContractRow] = {}
    resolving: set[str] = set()

    def resolve(name: str) -> ContractRow:
        cached = rows.get(name)
        if cached is not None:
            return cached
        declaration = declarations[name]
        if declaration.kind is ContractKind.WORLD:
            row = ContractRow(world=name)
        elif declaration.kind is ContractKind.PROTOCOL:
            row = ContractRow(protocol=name)
        elif declaration.kind is ContractKind.HANDLER:
            row = ContractRow(handler=name)
        elif declaration.kind is ContractKind.LAW:
            row = ContractRow(laws=(name,))
        else:
            if name in resolving:
                raise GlyphError(f"Bundle cycle at '{name}'")
            resolving.add(name)
            row = ContractRow()
            for ref in declaration.refs:
                if ref.external:
                    raise GlyphError(
                        f"{ref.line}行目: Bundleにはkind付きローカルContractを含める"
                    )
                row = _merge_rows(row, resolve(ref.name), ref.line)
            resolving.remove(name)
        rows[name] = row
        return row

    for name in declarations:
        resolve(name)

    targets = _declaration_targets(source)
    applications: list[AppliedContract] = []
    for application in contracts.applications:
        target, target_kind = _target_for_application(application.line, targets)
        row = ContractRow()
        for ref in application.refs:
            if ref.external:
                raise GlyphError(
                    f"{ref.line}行目: Contract適用には定義済みContractを指定する"
                )
            row = _merge_rows(row, resolve(ref.name), ref.line)
        applications.append(AppliedContract(target, target_kind, row, application.line))

    capability_functions = {item.name: item for item in capabilities.functions}
    plain_functions = _plain_function_types(program)
    resources = {item.name for item in capabilities.resources}
    for application in applications:
        if application.row.protocol is not None:
            _validate_protocol_signature(
                application,
                protocols[application.row.protocol],
                capability_functions,
                plain_functions,
            )
        if application.row.handler is not None:
            _validate_handler(
                application,
                handlers[application.row.handler],
                capability_functions,
                resources,
            )

    application_map = {item.target: item for item in applications}
    _validate_world_calls(
        program,
        application_map,
        worlds,
        capability_functions,
    )

    return ContractSemanticModel(
        tuple(worlds.values()),
        tuple(protocols.values()),
        tuple(handlers.values()),
        tuple(laws.values()),
        tuple(rows.items()),
        tuple(applications),
    )
