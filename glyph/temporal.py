from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

from .compiler import (
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    FieldExpr,
    GlyphError,
    NameExpr,
    NumberExpr,
    Param,
    Program,
    RustGenerator,
    TryExpr,
    UnaryExpr,
    _PRECEDENCE,
    _collect_macros,
    _find_matching,
    _find_top_level_char,
    _parse_params,
    _split_top_level,
    _resolve_macros,
    parse_expr,
)


class Formula:
    """状態列に対して評価する時相論理式。"""


@dataclass(frozen=True)
class Atom(Formula):
    expr: Expr


@dataclass(frozen=True)
class Not(Formula):
    value: Formula


@dataclass(frozen=True)
class And(Formula):
    left: Formula
    right: Formula


@dataclass(frozen=True)
class Or(Formula):
    left: Formula
    right: Formula


@dataclass(frozen=True)
class Implies(Formula):
    premise: Formula
    consequence: Formula


@dataclass(frozen=True)
class Always(Formula):
    value: Formula


@dataclass(frozen=True)
class Eventually(Formula):
    value: Formula


@dataclass(frozen=True)
class Within(Formula):
    milliseconds: int
    value: Formula


@dataclass(frozen=True)
class Until(Formula):
    hold: Formula
    target: Formula
    weak: bool = False


@dataclass(frozen=True)
class SpecDecl:
    name: str
    params: tuple[Param, ...]
    formula: Formula
    line: int


@dataclass(frozen=True)
class _FormulaToken:
    kind: str
    value: str
    start: int
    end: int


_DURATION_RE = re.compile(r"([0-9]+)(ms|s|m)\Z")
_SPEC_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


_TYPE_SHORTCUTS = {"f": "f32", "d": "f64", "u": "u16", "i": "i32", "b": "bool"}


def _product_rows(raw_lines: Sequence[str]) -> dict[str, tuple[str, ...]]:
    rows: dict[str, tuple[str, ...]] = {}
    for original in raw_lines:
        clean = original.split("#", 1)[0].strip()
        if not clean.startswith("*"):
            continue
        body = clean[1:]
        open_pos = body.find("(")
        if open_pos <= 0:
            continue
        close_pos = _find_matching(body, open_pos)
        if body[close_pos + 1 :].strip():
            continue
        name = body[:open_pos].strip()
        fields = tuple(
            part.strip()
            for part in _split_top_level(body[open_pos + 1 : close_pos], ",")
            if part.strip()
        )
        rows[name] = fields
    return rows


def _expand_spec_params(text: str, products: dict[str, tuple[str, ...]]) -> str:
    output: list[str] = []
    for part in _split_top_level(text, ","):
        item = part.strip()
        if item.startswith("*") and item[1:].isidentifier():
            name = item[1:]
            if name not in products:
                raise GlyphError(f"展開する積型 '*{name}' が定義されていない")
            output.extend(products[name])
            continue
        colon = _find_top_level_char(item, ":")
        if colon >= 0:
            name = item[:colon].strip()
            ty = item[colon + 1 :].strip()
            item = f"{name}:{_TYPE_SHORTCUTS.get(ty, ty)}"
        output.append(item)
    return ",".join(output)


def _lex_formula(text: str) -> list[_FormulaToken]:
    tokens: list[_FormulaToken] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if text.startswith(">>", i):
            tokens.append(_FormulaToken("IMPLIES", ">>", i, i + 2))
            i += 2
            continue
        if i + 1 < len(text) and text[i : i + 2] in {"<=", ">=", "!=", "=="}:
            tokens.append(_FormulaToken("RAW", text[i : i + 2], i, i + 2))
            i += 2
            continue
        if ch == "□":
            tokens.append(_FormulaToken("ALWAYS", ch, i, i + 1))
            i += 1
            continue
        if ch == "◇":
            tokens.append(_FormulaToken("EVENTUALLY", ch, i, i + 1))
            i += 1
            continue
        if ch == "(":
            tokens.append(_FormulaToken("LPAREN", ch, i, i + 1))
            i += 1
            continue
        if ch == ")":
            tokens.append(_FormulaToken("RPAREN", ch, i, i + 1))
            i += 1
            continue
        if ch == "!":
            tokens.append(_FormulaToken("NOT", ch, i, i + 1))
            i += 1
            continue
        if ch == "&":
            tokens.append(_FormulaToken("AND", ch, i, i + 1))
            i += 1
            continue
        if ch == "|":
            tokens.append(_FormulaToken("OR", ch, i, i + 1))
            i += 1
            continue
        if ch.isalpha() or ch == "_":
            start = i
            i += 1
            while i < len(text) and (text[i].isalnum() or text[i] == "_"):
                i += 1
            value = text[start:i]
            kind = {"U": "UNTIL", "W": "WEAK_UNTIL"}.get(value, "RAW")
            tokens.append(_FormulaToken(kind, value, start, i))
            continue
        if ch.isdigit():
            start = i
            i += 1
            while i < len(text) and text[i].isdigit():
                i += 1
            for unit in ("ms", "s", "m"):
                if text.startswith(unit, i):
                    i += len(unit)
                    tokens.append(_FormulaToken("DURATION", text[start:i], start, i))
                    break
            else:
                if i < len(text) and text[i] == ".":
                    i += 1
                    while i < len(text) and text[i].isdigit():
                        i += 1
                tokens.append(_FormulaToken("RAW", text[start:i], start, i))
            continue
        if ch in ",.?+-*/<>=":
            tokens.append(_FormulaToken("RAW", ch, i, i + 1))
            i += 1
            continue
        raise GlyphError(f"時相式に使えない文字 '{ch}' at {i}: {text}")
    tokens.append(_FormulaToken("EOF", "", len(text), len(text)))
    return tokens


def _duration_ms(value: str) -> int:
    match = _DURATION_RE.fullmatch(value)
    if match is None:
        raise GlyphError(f"時間は整数と ms/s/m で記述する: {value}")
    count = int(match.group(1))
    if count <= 0:
        raise GlyphError("時間境界は0より大きくする")
    factor = {"ms": 1, "s": 1000, "m": 60_000}[match.group(2)]
    milliseconds = count * factor
    if milliseconds > 2**64 - 1:
        raise GlyphError(f"時間境界がu64ミリ秒を超える: {value}")
    return milliseconds


class FormulaParser:
    def __init__(
        self,
        text: str,
        macros: dict[str, tuple[object, ...]] | None = None,
    ):
        self.text = text
        self.tokens = _lex_formula(text)
        self.index = 0
        self.macros = macros

    def parse(self) -> Formula:
        formula = self._parse_implication()
        token = self._peek()
        if token.kind != "EOF":
            raise GlyphError(
                f"時相式の末尾に余分なトークン '{token.value}' at {token.start}: {self.text}"
            )
        return formula

    def _peek(self) -> _FormulaToken:
        return self.tokens[self.index]

    def _take(self, kind: str | None = None) -> _FormulaToken:
        token = self._peek()
        if kind is not None and token.kind != kind:
            raise GlyphError(
                f"時相式で {kind} が必要だが '{token.value}' を検出 at {token.start}: {self.text}"
            )
        self.index += 1
        return token

    def _parse_implication(self) -> Formula:
        left = self._parse_or()
        if self._peek().kind == "IMPLIES":
            self._take()
            return Implies(left, self._parse_implication())
        return left

    def _parse_or(self) -> Formula:
        left = self._parse_and()
        while self._peek().kind == "OR":
            self._take()
            left = Or(left, self._parse_and())
        return left

    def _parse_and(self) -> Formula:
        left = self._parse_until()
        while self._peek().kind == "AND":
            self._take()
            left = And(left, self._parse_until())
        return left

    def _parse_until(self) -> Formula:
        left = self._parse_unary()
        while self._peek().kind in {"UNTIL", "WEAK_UNTIL"}:
            weak = self._take().kind == "WEAK_UNTIL"
            left = Until(left, self._parse_unary(), weak=weak)
        return left

    def _parse_unary(self) -> Formula:
        token = self._peek()
        if token.kind == "NOT":
            self._take()
            return Not(self._parse_unary())
        if token.kind == "ALWAYS":
            self._take()
            return Always(self._parse_unary())
        if token.kind == "EVENTUALLY":
            self._take()
            if self._peek().kind == "DURATION":
                duration = _duration_ms(self._take().value)
                return Within(duration, self._parse_unary())
            return Eventually(self._parse_unary())
        if token.kind == "LPAREN":
            self._take()
            value = self._parse_implication()
            self._take("RPAREN")
            return value
        return self._parse_atom()

    def _parse_atom(self) -> Formula:
        first = self._peek()
        if first.kind in {
            "EOF",
            "RPAREN",
            "IMPLIES",
            "AND",
            "OR",
            "UNTIL",
            "WEAK_UNTIL",
        }:
            raise GlyphError(
                f"時相式に状態述語が必要 at {first.start}: {self.text}"
            )

        start = first.start
        end = first.end
        depth = 0
        consumed = False
        while True:
            token = self._peek()
            if token.kind == "EOF":
                break
            if token.kind == "LPAREN":
                depth += 1
                end = token.end
                self._take()
                consumed = True
                continue
            if token.kind == "RPAREN":
                if depth == 0:
                    break
                depth -= 1
                end = token.end
                self._take()
                consumed = True
                continue
            if depth == 0 and token.kind in {
                "IMPLIES",
                "AND",
                "OR",
                "UNTIL",
                "WEAK_UNTIL",
            }:
                break
            if depth == 0 and token.kind in {"ALWAYS", "EVENTUALLY"}:
                break
            end = token.end
            self._take()
            consumed = True

        if not consumed or depth != 0:
            raise GlyphError(f"不正な状態述語 at {start}: {self.text}")
        atom_text = self.text[start:end].strip()
        try:
            return Atom(parse_expr(atom_text, self.macros))
        except GlyphError as exc:
            raise GlyphError(f"状態述語 '{atom_text}': {exc}") from exc


def parse_formula(
    text: str,
    macros: dict[str, tuple[object, ...]] | None = None,
) -> Formula:
    return FormulaParser(text.strip(), macros).parse()


def extract_specs(source: str) -> tuple[str, tuple[SpecDecl, ...]]:
    """トップレベルの`?name(params)=formula`を抽出し、行数を保った本体を返す。"""
    raw_lines = source.splitlines()
    macros = _resolve_macros(_collect_macros(raw_lines))
    products = _product_rows(raw_lines)
    specs: list[SpecDecl] = []
    names: dict[str, int] = {}
    output: list[str] = []

    for line_no, original in enumerate(raw_lines, start=1):
        clean = original.split("#", 1)[0].rstrip()
        if not clean or clean[0].isspace() or not clean.startswith("?"):
            output.append(original)
            continue

        body = clean[1:].strip()
        open_pos = body.find("(")
        if open_pos <= 0:
            raise GlyphError(f"{line_no}行目: ?name(params)=formula の形式が必要")
        name = body[:open_pos].strip()
        if _SPEC_NAME_RE.fullmatch(name) is None:
            raise GlyphError(f"{line_no}行目: 不正な制約名 '{name}'")
        if name in names:
            raise GlyphError(
                f"{line_no}行目: 制約 '{name}' は{names[name]}行目で既に定義済み"
            )
        close_pos = _find_matching(body, open_pos)
        rest = body[close_pos + 1 :].strip()
        if not rest.startswith("="):
            raise GlyphError(f"{line_no}行目: 制約本体の前に '=' が必要")
        formula_text = rest[1:].strip()
        if not formula_text:
            raise GlyphError(f"{line_no}行目: 制約式が空")

        params_text = _expand_spec_params(body[open_pos + 1 : close_pos], products)
        params = _parse_params(params_text)
        param_names = [param.name for param in params]
        if len(param_names) != len(set(param_names)):
            raise GlyphError(f"{line_no}行目: 制約引数が重複")
        specs.append(SpecDecl(name, params, parse_formula(formula_text, macros), line_no))
        names[name] = line_no
        output.append("")

    suffix = "\n" if source.endswith("\n") else ""
    return "\n".join(output) + suffix, tuple(specs)
