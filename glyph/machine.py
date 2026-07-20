from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

from .compiler import (
    CallExpr,
    Expr,
    FieldExpr,
    FunctionDecl,
    GlyphError,
    NameExpr,
    Param,
    ProductDecl,
    Program,
    SumDecl,
    TypeRef,
    _collect_macros,
    _find_matching,
    _parse_params,
    _resolve_macros,
    parse_expr,
)


_MACHINE_RE = re.compile(r"machine\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_SINGLE_EQUAL_RE = re.compile(r"(?<![<>=!])=(?!=)")
_REQUIRED_PROPERTIES = ("select", "init", "next", "success", "failure")


@dataclass(frozen=True)
class MachineDecl:
    name: str
    params: tuple[Param, ...]
    selector: Expr
    initial: Expr
    next_expr: Expr
    success: str
    failure: str
    line: int
    selector_line: int
    initial_line: int
    next_line: int
    success_line: int
    failure_line: int

    @property
    def state_param(self) -> Param:
        return self.params[0]

    @property
    def input_params(self) -> tuple[Param, ...]:
        return self.params[1:]


def _strip_comment(line: str) -> str:
    return line.split("#", 1)[0].rstrip()


def _reject_single_equal(expression: str, line: int) -> None:
    match = _SINGLE_EQUAL_RE.search(expression)
    if match is not None:
        raise GlyphError(
            f"{line}行目: machine式中の等値比較には '=' ではなく '==' を使う"
        )


def extract_machines(source: str) -> tuple[str, tuple[MachineDecl, ...]]:
    """`machine Name(params)`ブロックを抽出し、元の行番号を保つ空行へ置換する。"""

    raw_lines = source.splitlines()
    macros = _resolve_macros(_collect_macros(raw_lines))
    output = list(raw_lines)
    machines: list[MachineDecl] = []
    seen: dict[str, int] = {}
    i = 0

    while i < len(raw_lines):
        original = raw_lines[i]
        clean = _strip_comment(original)
        if not clean.strip() or clean[0].isspace() or not clean.startswith("machine "):
            i += 1
            continue

        line_no = i + 1
        match = _MACHINE_RE.match(clean)
        if match is None:
            raise GlyphError(f"{line_no}行目: machine Name(state:Type,input:Type) の形式が必要")

        name = match.group(1)
        if name in seen:
            raise GlyphError(
                f"{line_no}行目: machine '{name}' は{seen[name]}行目で既に定義済み"
            )

        open_pos = clean.find("(", match.start(1) + len(name))
        close_pos = _find_matching(clean, open_pos)
        if clean[close_pos + 1 :].strip():
            raise GlyphError(f"{line_no}行目: machine宣言の末尾に余分な文字がある")
        params = _parse_params(clean[open_pos + 1 : close_pos])
        if not params:
            raise GlyphError(f"{line_no}行目: machineには少なくとも状態引数が必要")

        properties: dict[str, tuple[str, int]] = {}
        output[i] = ""
        i += 1

        while i < len(raw_lines):
            body_original = raw_lines[i]
            body_clean = _strip_comment(body_original)
            if body_clean.strip() and not body_original[0].isspace():
                break
            output[i] = ""
            if not body_clean.strip():
                i += 1
                continue

            body_line = i + 1
            stripped = body_clean.strip()
            separator = stripped.find("=")
            if separator <= 0:
                raise GlyphError(
                    f"{body_line}行目: machineプロパティは name=expression で記述する"
                )
            key = stripped[:separator].strip()
            value = stripped[separator + 1 :].strip()
            if key not in _REQUIRED_PROPERTIES:
                raise GlyphError(
                    f"{body_line}行目: 不明なmachineプロパティ '{key}'。"
                    f"使用可能: {', '.join(_REQUIRED_PROPERTIES)}"
                )
            if key in properties:
                raise GlyphError(
                    f"{body_line}行目: machineプロパティ '{key}' は"
                    f"{properties[key][1]}行目で既に定義済み"
                )
            if not value:
                raise GlyphError(f"{body_line}行目: machineプロパティ '{key}' が空")
            properties[key] = (value, body_line)
            i += 1

        missing = [key for key in _REQUIRED_PROPERTIES if key not in properties]
        if missing:
            raise GlyphError(
                f"{line_no}行目: machine '{name}' に必須プロパティがない: "
                + ", ".join(missing)
            )

        for key in ("select", "init", "next"):
            _reject_single_equal(properties[key][0], properties[key][1])
        for key in ("success", "failure"):
            value, value_line = properties[key]
            if not value.isidentifier():
                raise GlyphError(
                    f"{value_line}行目: machineの{key}は終端variant名で記述する"
                )

        machine = MachineDecl(
            name=name,
            params=params,
            selector=parse_expr(properties["select"][0], macros),
            initial=parse_expr(properties["init"][0], macros),
            next_expr=parse_expr(properties["next"][0], macros),
            success=properties["success"][0],
            failure=properties["failure"][0],
            line=line_no,
            selector_line=properties["select"][1],
            initial_line=properties["init"][1],
            next_line=properties["next"][1],
            success_line=properties["success"][1],
            failure_line=properties["failure"][1],
        )
        machines.append(machine)
        seen[name] = line_no

    suffix = "\n" if source.endswith("\n") else ""
    return "\n".join(output) + suffix, tuple(machines)


def _same_type(left: TypeRef, right: TypeRef) -> bool:
    return left == right


def _unwrap_result(ty: TypeRef) -> TypeRef:
    if ty.name == "R" and len(ty.args) == 2:
        return ty.args[0]
    return ty


def _selector_field(machine: MachineDecl) -> str:
    selector = machine.selector
    if not (
        isinstance(selector, FieldExpr)
        and isinstance(selector.base, NameExpr)
        and selector.base.name == machine.state_param.name
    ):
        raise GlyphError(
            f"{machine.selector_line}行目: selectは"
            f" '{machine.state_param.name}.field' の形式で記述する"
        )
    return selector.field


def _direct_call(expr: Expr, line: int, label: str) -> CallExpr:
    if not isinstance(expr, CallExpr) or not isinstance(expr.callee, NameExpr):
        raise GlyphError(f"{line}行目: machineの{label}は名前付き関数呼出しで記述する")
    return expr


def validate_machines(program: Program, machines: Sequence[MachineDecl]) -> None:
    products = {
        decl.name: decl for decl in program.declarations if isinstance(decl, ProductDecl)
    }
    sums = {decl.name: decl for decl in program.declarations if isinstance(decl, SumDecl)}
    functions = {
        decl.name: decl for decl in program.declarations if isinstance(decl, FunctionDecl)
    }
    declared_names = {decl.name: decl.line for decl in program.declarations}

    for machine in machines:
        if machine.name in declared_names:
            raise GlyphError(
                f"{machine.line}行目: machine名 '{machine.name}' は"
                f"{declared_names[machine.name]}行目の宣言と衝突"
            )

        state_type = machine.state_param.ty
        state_decl = products.get(state_type.name)
        if state_decl is None or state_type.args:
            raise GlyphError(
                f"{machine.line}行目: machineの第1引数型 '{state_type.name}' は積型でなければならない"
            )

        selector_name = _selector_field(machine)
        selector_index = next(
            (index for index, field in enumerate(state_decl.fields) if field.name == selector_name),
            None,
        )
        if selector_index is None:
            raise GlyphError(
                f"{machine.selector_line}行目: 状態型 '{state_decl.name}' に"
                f"フィールド '{selector_name}' がない"
            )
        selector_type = state_decl.fields[selector_index].ty
        selector_sum = sums.get(selector_type.name)
        if selector_sum is None or selector_type.args:
            raise GlyphError(
                f"{machine.selector_line}行目: select対象 '{selector_name}' の型"
                f" '{selector_type.name}' は直和型でなければならない"
            )
        variants = {variant.name for variant in selector_sum.variants}

        initial_call = _direct_call(machine.initial, machine.initial_line, "init")
        if initial_call.callee.name != state_decl.name:
            raise GlyphError(
                f"{machine.initial_line}行目: initは状態型 '{state_decl.name}' を構築する"
            )
        if len(initial_call.args) != len(state_decl.fields):
            raise GlyphError(
                f"{machine.initial_line}行目: initの'{state_decl.name}'は"
                f"{len(state_decl.fields)}引数必要"
            )
        initial_selector = initial_call.args[selector_index]
        if not isinstance(initial_selector, NameExpr) or initial_selector.name not in variants:
            raise GlyphError(
                f"{machine.initial_line}行目: initの'{selector_name}'には"
                f" {selector_sum.name} のvariantを指定する"
            )

        if machine.success not in variants:
            raise GlyphError(
                f"{machine.success_line}行目: success variant '{machine.success}' は"
                f"型 '{selector_sum.name}' に存在しない"
            )
        if machine.failure not in variants:
            raise GlyphError(
                f"{machine.failure_line}行目: failure variant '{machine.failure}' は"
                f"型 '{selector_sum.name}' に存在しない"
            )
        if machine.success == machine.failure:
            raise GlyphError(
                f"{machine.failure_line}行目: successとfailureは異なるvariantにする"
            )

        next_call = _direct_call(machine.next_expr, machine.next_line, "next")
        next_decl = functions.get(next_call.callee.name)
        if next_decl is None:
            raise GlyphError(
                f"{machine.next_line}行目: next関数 '{next_call.callee.name}' が定義されていない"
            )
        if len(next_call.args) != len(next_decl.params):
            raise GlyphError(
                f"{machine.next_line}行目: next関数 '{next_decl.name}' は"
                f"{len(next_decl.params)}引数だが{len(next_call.args)}引数を受け取った"
            )
        if not _same_type(_unwrap_result(next_decl.return_type), state_type):
            raise GlyphError(
                f"{machine.next_line}行目: next関数 '{next_decl.name}' は"
                f"状態型 '{state_type.name}' またはそのResultを返す必要がある"
            )
        first_arg = next_call.args[0] if next_call.args else None
        if not isinstance(first_arg, NameExpr) or first_arg.name != machine.state_param.name:
            raise GlyphError(
                f"{machine.next_line}行目: nextの第1引数には状態変数"
                f" '{machine.state_param.name}' を渡す"
            )
