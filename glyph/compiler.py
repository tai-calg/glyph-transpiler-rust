from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


class GlyphError(Exception):
    """DSLの字句・構文・生成エラー。"""


@dataclass(frozen=True)
class TypeRef:
    name: str
    args: tuple["TypeRef", ...] = ()


@dataclass(frozen=True)
class Field:
    name: str
    ty: TypeRef


@dataclass(frozen=True)
class ProductDecl:
    name: str
    fields: tuple[Field, ...]
    line: int


@dataclass(frozen=True)
class Variant:
    name: str
    tuple_types: tuple[TypeRef, ...] = ()
    fields: tuple[Field, ...] = ()


@dataclass(frozen=True)
class SumDecl:
    name: str
    variants: tuple[Variant, ...]
    line: int


@dataclass(frozen=True)
class AliasDecl:
    name: str
    target: TypeRef
    line: int


@dataclass(frozen=True)
class Param:
    name: str
    ty: TypeRef


@dataclass(frozen=True)
class ExternDecl:
    name: str
    params: tuple[Param, ...]
    return_type: TypeRef
    line: int


class Expr:
    pass


@dataclass(frozen=True)
class NameExpr(Expr):
    name: str


@dataclass(frozen=True)
class NumberExpr(Expr):
    value: str


@dataclass(frozen=True)
class BoolExpr(Expr):
    value: bool


@dataclass(frozen=True)
class UnaryExpr(Expr):
    op: str
    expr: Expr


@dataclass(frozen=True)
class BinaryExpr(Expr):
    op: str
    left: Expr
    right: Expr


@dataclass(frozen=True)
class CallExpr(Expr):
    callee: Expr
    args: tuple[Expr, ...]


@dataclass(frozen=True)
class FieldExpr(Expr):
    base: Expr
    field: str


@dataclass(frozen=True)
class TryExpr(Expr):
    expr: Expr


@dataclass(frozen=True)
class GuardClause:
    condition: Expr | None
    value: Expr
    line: int


@dataclass(frozen=True)
class FunctionDecl:
    name: str
    params: tuple[Param, ...]
    return_type: TypeRef
    expression: Expr | None
    guards: tuple[GuardClause, ...]
    line: int


Decl = ProductDecl | SumDecl | AliasDecl | ExternDecl | FunctionDecl


@dataclass(frozen=True)
class Program:
    declarations: tuple[Decl, ...]


@dataclass(frozen=True)
class MacroDef:
    """式中の識別子を別の式トークン列へ置換する単語マクロ。"""

    name: str
    body: str
    line: int


# ---------- 共通文字列処理 ----------


def _strip_comment(line: str) -> str:
    # DSL MVPでは文字列リテラルを扱わないため、#以降をコメントとして安全に除去できる。
    return line.split("#", 1)[0].rstrip()


def _split_top_level(text: str, separator: str) -> list[str]:
    """括弧・波括弧・山括弧の外側だけで分割する。"""
    parts: list[str] = []
    start = 0
    round_depth = 0
    brace_depth = 0
    angle_depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            round_depth += 1
        elif ch == ")":
            round_depth -= 1
        elif ch == "{":
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
        elif ch == "<":
            # 型の山括弧と比較演算子は行ヘッダでのみ区別が必要。
            # split_top_levelは宣言解析で使うため、山括弧として扱う。
            angle_depth += 1
        elif ch == ">":
            angle_depth = max(0, angle_depth - 1)
        elif (
            ch == separator
            and round_depth == 0
            and brace_depth == 0
            and angle_depth == 0
        ):
            parts.append(text[start:i].strip())
            start = i + 1
        i += 1
    parts.append(text[start:].strip())
    return parts


def _find_matching(text: str, start: int, left: str = "(", right: str = ")") -> int:
    if start >= len(text) or text[start] != left:
        raise GlyphError(f"'{left}' が必要: {text}")
    depth = 0
    for i in range(start, len(text)):
        if text[i] == left:
            depth += 1
        elif text[i] == right:
            depth -= 1
            if depth == 0:
                return i
    raise GlyphError(f"'{right}' が閉じられていない: {text}")


def _find_top_level_char(text: str, target: str) -> int:
    round_depth = brace_depth = angle_depth = 0
    for i, ch in enumerate(text):
        if ch == "(":
            round_depth += 1
        elif ch == ")":
            round_depth -= 1
        elif ch == "{":
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
        elif ch == "<":
            angle_depth += 1
        elif ch == ">":
            angle_depth = max(0, angle_depth - 1)
        elif ch == target and round_depth == 0 and brace_depth == 0 and angle_depth == 0:
            return i
    return -1


# ---------- 型パーサー ----------


@dataclass(frozen=True)
class _TypeToken:
    value: str
    pos: int


def _lex_type(text: str) -> list[_TypeToken]:
    tokens: list[_TypeToken] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isalpha() or ch == "_":
            start = i
            i += 1
            while i < len(text) and (text[i].isalnum() or text[i] == "_"):
                i += 1
            tokens.append(_TypeToken(text[start:i], start))
            continue
        if ch in "<>,()":
            tokens.append(_TypeToken(ch, i))
            i += 1
            continue
        raise GlyphError(f"型に使えない文字 '{ch}': {text}")
    return tokens


class _TypeParser:
    def __init__(self, text: str):
        self.text = text
        self.tokens = _lex_type(text)
        self.index = 0

    def parse(self) -> TypeRef:
        ty = self._parse_type()
        if self.index != len(self.tokens):
            tok = self.tokens[self.index]
            raise GlyphError(f"型の末尾に余分なトークン '{tok.value}': {self.text}")
        return ty

    def _peek(self, value: str | None = None) -> bool:
        if self.index >= len(self.tokens):
            return False
        return value is None or self.tokens[self.index].value == value

    def _take(self, value: str | None = None) -> _TypeToken:
        if self.index >= len(self.tokens):
            raise GlyphError(f"型が途中で終了: {self.text}")
        tok = self.tokens[self.index]
        if value is not None and tok.value != value:
            raise GlyphError(f"型で '{value}' が必要だが '{tok.value}' を検出: {self.text}")
        self.index += 1
        return tok

    def _parse_type(self) -> TypeRef:
        if self._peek("("):
            self._take("(")
            if self._peek(")"):
                self._take(")")
                return TypeRef("()")
            args = [self._parse_type()]
            while self._peek(","):
                self._take(",")
                args.append(self._parse_type())
            self._take(")")
            return TypeRef("tuple", tuple(args))

        name = self._take().value
        args: list[TypeRef] = []
        if self._peek("<"):
            self._take("<")
            if not self._peek(">"):
                args.append(self._parse_type())
                while self._peek(","):
                    self._take(",")
                    args.append(self._parse_type())
            self._take(">")
        return TypeRef(name, tuple(args))


def parse_type(text: str) -> TypeRef:
    return _TypeParser(text.strip()).parse()


def _parse_fields(text: str) -> tuple[Field, ...]:
    if not text.strip():
        return ()
    fields: list[Field] = []
    for part in _split_top_level(text, ","):
        colon = _find_top_level_char(part, ":")
        if colon < 0:
            raise GlyphError(f"フィールドは name:type で記述する: {part}")
        name = part[:colon].strip()
        if not name.isidentifier():
            raise GlyphError(f"不正なフィールド名: {name}")
        fields.append(Field(name, parse_type(part[colon + 1 :])))
    return tuple(fields)


def _parse_params(text: str) -> tuple[Param, ...]:
    return tuple(Param(field.name, field.ty) for field in _parse_fields(text))


# ---------- 式字句解析・Prattパーサー ----------


@dataclass(frozen=True)
class Token:
    kind: str
    value: str
    pos: int


_TWO_CHAR = {"<=", ">=", "!=", "=="}
_SINGLE = set("(),.?+-*/<>=!|&")


def lex_expr(text: str) -> list[Token]:
    tokens: list[Token] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch.isalpha() or ch == "_":
            start = i
            i += 1
            while i < len(text) and (text[i].isalnum() or text[i] == "_"):
                i += 1
            value = text[start:i]
            kind = "BOOL" if value in {"true", "false"} else "IDENT"
            tokens.append(Token(kind, value, start))
            continue
        if ch.isdigit():
            start = i
            i += 1
            while i < len(text) and text[i].isdigit():
                i += 1
            if i < len(text) and text[i] == ".":
                i += 1
                while i < len(text) and text[i].isdigit():
                    i += 1
            tokens.append(Token("NUMBER", text[start:i], start))
            continue
        if i + 1 < len(text) and text[i : i + 2] in _TWO_CHAR:
            tokens.append(Token("OP", text[i : i + 2], i))
            i += 2
            continue
        if ch in _SINGLE:
            kind = "OP" if ch in "+-*/<>=!|&" else "PUNCT"
            tokens.append(Token(kind, ch, i))
            i += 1
            continue
        raise GlyphError(f"式に使えない文字 '{ch}' at {i}: {text}")
    tokens.append(Token("EOF", "", len(text)))
    return tokens


_PRECEDENCE = {
    "|": 10,
    "&": 20,
    "=": 30,
    "==": 30,
    "!=": 30,
    "<": 30,
    ">": 30,
    "<=": 30,
    ">=": 30,
    "+": 40,
    "-": 40,
    "*": 50,
    "/": 50,
}


class ExprParser:
    def __init__(self, text: str, tokens: Sequence[Token] | None = None):
        self.text = text
        self.tokens = list(tokens) if tokens is not None else lex_expr(text)
        self.index = 0

    def parse(self) -> Expr:
        expr = self._parse_expr(0)
        if self._peek().kind != "EOF":
            tok = self._peek()
            raise GlyphError(f"式の末尾に余分なトークン '{tok.value}' at {tok.pos}: {self.text}")
        return expr

    def _peek(self) -> Token:
        return self.tokens[self.index]

    def _take(self) -> Token:
        tok = self.tokens[self.index]
        self.index += 1
        return tok

    def _expect(self, value: str) -> Token:
        tok = self._take()
        if tok.value != value:
            raise GlyphError(f"'{value}' が必要だが '{tok.value}' を検出 at {tok.pos}: {self.text}")
        return tok

    def _parse_expr(self, min_precedence: int) -> Expr:
        left = self._parse_prefix()
        left = self._parse_postfix(left)

        while True:
            tok = self._peek()
            if tok.kind != "OP" or tok.value not in _PRECEDENCE:
                break
            precedence = _PRECEDENCE[tok.value]
            if precedence < min_precedence:
                break
            op = self._take().value
            right = self._parse_expr(precedence + 1)
            left = BinaryExpr(op, left, right)
        return left

    def _parse_prefix(self) -> Expr:
        tok = self._take()
        if tok.kind == "IDENT":
            return NameExpr(tok.value)
        if tok.kind == "NUMBER":
            return NumberExpr(tok.value)
        if tok.kind == "BOOL":
            return BoolExpr(tok.value == "true")
        if tok.value in {"!", "-"}:
            return UnaryExpr(tok.value, self._parse_expr(60))
        if tok.value == "(":
            expr = self._parse_expr(0)
            self._expect(")")
            return expr
        raise GlyphError(f"式の先頭として不正なトークン '{tok.value}' at {tok.pos}: {self.text}")

    def _parse_postfix(self, expr: Expr) -> Expr:
        while True:
            tok = self._peek()
            if tok.value == "(":
                self._take()
                args: list[Expr] = []
                if self._peek().value != ")":
                    args.append(self._parse_expr(0))
                    while self._peek().value == ",":
                        self._take()
                        args.append(self._parse_expr(0))
                self._expect(")")
                expr = CallExpr(expr, tuple(args))
                continue
            if tok.value == ".":
                self._take()
                field = self._take()
                if field.kind != "IDENT":
                    raise GlyphError(f"'.' の後ろにはフィールド名が必要: {self.text}")
                expr = FieldExpr(expr, field.value)
                continue
            if tok.value == "?":
                self._take()
                expr = TryExpr(expr)
                continue
            break
        return expr


_MAX_MACRO_DEPTH = 64
_MAX_EXPANDED_TOKENS = 4096


def _without_eof(tokens: Sequence[Token]) -> list[Token]:
    return [token for token in tokens if token.kind != "EOF"]


def _with_eof(tokens: Sequence[Token], text: str) -> list[Token]:
    return [*tokens, Token("EOF", "", len(text))]


def _collect_macros(raw_lines: Sequence[str]) -> dict[str, MacroDef]:
    """トップレベルの `@NAME=expr` を収集する。

    マクロはファイル全体で有効にする。宣言順へ依存させないことで、
    同じ入力に対する展開を単純かつ決定的に保つ。
    """

    macros: dict[str, MacroDef] = {}
    for index, original in enumerate(raw_lines):
        clean = _strip_comment(original)
        if not clean.strip():
            continue
        if clean[0].isspace() or not clean.startswith("@"):
            continue

        line = index + 1
        body = clean[1:].strip()
        eq = body.find("=")
        if eq <= 0:
            raise GlyphError(f"{line}行目: @NAME=expression の形式が必要")

        name = body[:eq].strip()
        replacement = body[eq + 1 :].strip()
        if not name.isidentifier() or name in {"_", "true", "false"}:
            raise GlyphError(f"{line}行目: 不正なマクロ名 '{name}'")
        if not replacement:
            raise GlyphError(f"{line}行目: マクロ '{name}' の置換式が空")
        if name in macros:
            raise GlyphError(
                f"{line}行目: マクロ '{name}' は{macros[name].line}行目で既に定義済み"
            )
        macros[name] = MacroDef(name, replacement, line)
    return macros


def _resolve_macros(macros: dict[str, MacroDef]) -> dict[str, tuple[Token, ...]]:
    """マクロ参照を再帰的に解決し、循環と過大展開を拒否する。"""

    resolved: dict[str, tuple[Token, ...]] = {}

    def resolve(name: str, stack: tuple[str, ...]) -> tuple[Token, ...]:
        if name in resolved:
            return resolved[name]
        if name in stack:
            start = stack.index(name)
            cycle = (*stack[start:], name)
            raise GlyphError(f"macro cycle: {' -> '.join(cycle)}")
        if len(stack) >= _MAX_MACRO_DEPTH:
            raise GlyphError(
                f"マクロ展開の深さが上限{_MAX_MACRO_DEPTH}を超えた: {' -> '.join((*stack, name))}"
            )

        definition = macros[name]
        try:
            source_tokens = _without_eof(lex_expr(definition.body))
        except GlyphError as exc:
            raise GlyphError(f"{definition.line}行目: マクロ '{name}': {exc}") from exc

        output: list[Token] = []
        for token in source_tokens:
            if token.kind == "IDENT" and token.value in macros:
                nested = resolve(token.value, (*stack, name))
                # 置換式を括弧で囲み、呼出し側の演算子優先順位を変えない。
                output.append(Token("PUNCT", "(", token.pos))
                output.extend(nested)
                output.append(Token("PUNCT", ")", token.pos))
            else:
                output.append(token)
            if len(output) > _MAX_EXPANDED_TOKENS:
                raise GlyphError(
                    f"{definition.line}行目: マクロ '{name}' の展開が"
                    f"{_MAX_EXPANDED_TOKENS}トークンを超えた"
                )

        # 未使用マクロでも、置換後の式が文法的に正しいことを検査する。
        try:
            ExprParser(definition.body, _with_eof(output, definition.body)).parse()
        except GlyphError as exc:
            raise GlyphError(f"{definition.line}行目: マクロ '{name}': {exc}") from exc

        resolved[name] = tuple(output)
        return resolved[name]

    for macro_name in macros:
        resolve(macro_name, ())
    return resolved


def _expand_expression_tokens(
    tokens: Sequence[Token], macros: dict[str, tuple[Token, ...]]
) -> list[Token]:
    output: list[Token] = []
    for token in tokens:
        if token.kind == "IDENT" and token.value in macros:
            output.append(Token("PUNCT", "(", token.pos))
            output.extend(macros[token.value])
            output.append(Token("PUNCT", ")", token.pos))
        else:
            output.append(token)
        if len(output) > _MAX_EXPANDED_TOKENS:
            raise GlyphError(f"式のマクロ展開が{_MAX_EXPANDED_TOKENS}トークンを超えた")
    return output


def parse_expr(text: str, macros: dict[str, tuple[Token, ...]] | None = None) -> Expr:
    stripped = text.strip()
    tokens = _without_eof(lex_expr(stripped))
    if macros:
        tokens = _expand_expression_tokens(tokens, macros)
    return ExprParser(stripped, _with_eof(tokens, stripped)).parse()


# ---------- 行指向プログラムパーサー ----------


def _parse_named_signature(text: str, line: int) -> tuple[str, tuple[Param, ...], TypeRef, str | None]:
    """name(args):Ret または name(args):Ret=expr を解析する。"""
    open_pos = text.find("(")
    if open_pos <= 0:
        raise GlyphError(f"{line}行目: name(args):type の形式が必要")
    name = text[:open_pos].strip()
    if not name.isidentifier():
        raise GlyphError(f"{line}行目: 不正な名前 '{name}'")
    close_pos = _find_matching(text, open_pos)
    params = _parse_params(text[open_pos + 1 : close_pos])
    rest = text[close_pos + 1 :].strip()
    if not rest.startswith(":"):
        raise GlyphError(f"{line}行目: 戻り型の前に ':' が必要")
    rest = rest[1:].strip()

    eq_pos = _find_top_level_char(rest, "=")
    if eq_pos >= 0:
        return_type_text = rest[:eq_pos].strip()
        body = rest[eq_pos + 1 :].strip()
        if not body:
            raise GlyphError(f"{line}行目: '=' の後ろに式が必要")
    else:
        return_type_text = rest
        body = None
    return name, params, parse_type(return_type_text), body


def parse_program(source: str) -> Program:
    raw_lines = source.splitlines()
    macro_defs = _collect_macros(raw_lines)
    macros = _resolve_macros(macro_defs)
    declarations: list[Decl] = []
    i = 0

    while i < len(raw_lines):
        original = raw_lines[i]
        clean = _strip_comment(original)
        if not clean.strip():
            i += 1
            continue
        line_no = i + 1
        if clean[0].isspace():
            raise GlyphError(f"{line_no}行目: トップレベル宣言は行頭から開始する")
        marker = clean[0]
        body = clean[1:].strip()

        if marker == "@":
            # マクロ定義は先行パスで収集・検査済み。ASTには残さない。
            i += 1
            continue

        if marker == "*":
            open_pos = body.find("(")
            if open_pos <= 0:
                raise GlyphError(f"{line_no}行目: *Name(field:type,...) の形式が必要")
            name = body[:open_pos].strip()
            close_pos = _find_matching(body, open_pos)
            if body[close_pos + 1 :].strip():
                raise GlyphError(f"{line_no}行目: 積型宣言の末尾に余分な文字がある")
            declarations.append(ProductDecl(name, _parse_fields(body[open_pos + 1 : close_pos]), line_no))
            i += 1
            continue

        if marker == "+":
            eq = _find_top_level_char(body, "=")
            if eq <= 0:
                raise GlyphError(f"{line_no}行目: +Name=Variant|Variant(type) の形式が必要")
            name = body[:eq].strip()
            variants_text = body[eq + 1 :].strip()
            variants: list[Variant] = []
            for item in _split_top_level(variants_text, "|"):
                if not item:
                    raise GlyphError(f"{line_no}行目: 空のvariant")
                if "(" in item:
                    open_pos = item.find("(")
                    vname = item[:open_pos].strip()
                    close_pos = _find_matching(item, open_pos)
                    if item[close_pos + 1 :].strip():
                        raise GlyphError(f"{line_no}行目: variant末尾に余分な文字: {item}")
                    inner = item[open_pos + 1 : close_pos]
                    tuple_types = tuple(parse_type(x) for x in _split_top_level(inner, ",") if x)
                    variants.append(Variant(vname, tuple_types=tuple_types))
                elif "{" in item:
                    open_pos = item.find("{")
                    vname = item[:open_pos].strip()
                    close_pos = _find_matching(item, open_pos, "{", "}")
                    if item[close_pos + 1 :].strip():
                        raise GlyphError(f"{line_no}行目: variant末尾に余分な文字: {item}")
                    variants.append(Variant(vname, fields=_parse_fields(item[open_pos + 1 : close_pos])))
                else:
                    variants.append(Variant(item.strip()))
            declarations.append(SumDecl(name, tuple(variants), line_no))
            i += 1
            continue

        if marker == "=":
            eq = _find_top_level_char(body, "=")
            if eq <= 0:
                raise GlyphError(f"{line_no}行目: =Alias=Type の形式が必要")
            name = body[:eq].strip()
            declarations.append(AliasDecl(name, parse_type(body[eq + 1 :]), line_no))
            i += 1
            continue

        if marker == "!":
            name, params, return_type, expr = _parse_named_signature(body, line_no)
            if expr is not None:
                raise GlyphError(f"{line_no}行目: 外部関数宣言には本体を書かない")
            declarations.append(ExternDecl(name, params, return_type, line_no))
            i += 1
            continue

        if marker == ">":
            name, params, return_type, expression_text = _parse_named_signature(body, line_no)
            if expression_text is not None:
                declarations.append(
                    FunctionDecl(
                        name,
                        params,
                        return_type,
                        parse_expr(expression_text, macros),
                        (),
                        line_no,
                    )
                )
                i += 1
                continue

            guards: list[GuardClause] = []
            i += 1
            while i < len(raw_lines):
                next_original = raw_lines[i]
                next_clean = _strip_comment(next_original)
                if not next_clean.strip():
                    i += 1
                    continue
                if not next_original[0].isspace():
                    break
                guard_line = i + 1
                stripped = next_clean.strip()
                arrow = stripped.find("=>")
                if arrow < 0:
                    raise GlyphError(f"{guard_line}行目: ガードは condition => expression で記述する")
                cond_text = stripped[:arrow].strip()
                value_text = stripped[arrow + 2 :].strip()
                if not value_text:
                    raise GlyphError(f"{guard_line}行目: '=>' の後ろに式が必要")
                condition = None if cond_text == "_" else parse_expr(cond_text, macros)
                guards.append(GuardClause(condition, parse_expr(value_text, macros), guard_line))
                i += 1
            if not guards:
                raise GlyphError(f"{line_no}行目: 関数本体またはガード節が必要")
            declarations.append(FunctionDecl(name, params, return_type, None, tuple(guards), line_no))
            continue

        raise GlyphError(f"{line_no}行目: 不明な宣言記号 '{marker}'")

    program = Program(tuple(declarations))
    validate_program(program)
    _validate_macro_collisions(macro_defs, program)
    return program


# ---------- 静的検査 ----------


def validate_program(program: Program) -> None:
    names: dict[str, int] = {}
    variants: dict[str, str] = {}
    for decl in program.declarations:
        name = decl.name
        if name in names:
            raise GlyphError(f"{decl.line}行目: '{name}' は{names[name]}行目で既に定義済み")
        names[name] = decl.line
        if isinstance(decl, ProductDecl):
            _check_unique([f.name for f in decl.fields], decl.line, "フィールド")
        elif isinstance(decl, SumDecl):
            _check_unique([v.name for v in decl.variants], decl.line, "variant")
            for variant in decl.variants:
                if variant.name in variants:
                    raise GlyphError(
                        f"{decl.line}行目: variant '{variant.name}' は型 '{variants[variant.name]}' と衝突"
                    )
                variants[variant.name] = decl.name
                _check_unique([f.name for f in variant.fields], decl.line, "variantフィールド")
        elif isinstance(decl, FunctionDecl) and decl.guards:
            fallback_positions = [idx for idx, clause in enumerate(decl.guards) if clause.condition is None]
            if len(fallback_positions) != 1 or fallback_positions[0] != len(decl.guards) - 1:
                raise GlyphError(
                    f"{decl.line}行目: ガード関数は最後にちょうど1個の '_' 節を持つ必要がある"
                )


def _validate_macro_collisions(macros: dict[str, MacroDef], program: Program) -> None:
    """宣言名と同名のマクロによる暗黙の呼出し書換えを禁止する。"""

    symbols: dict[str, int] = {}
    for decl in program.declarations:
        symbols[decl.name] = decl.line
        if isinstance(decl, SumDecl):
            for variant in decl.variants:
                symbols[variant.name] = decl.line

    for name, macro in macros.items():
        if name in symbols:
            raise GlyphError(
                f"{macro.line}行目: マクロ '{name}' は"
                f"{symbols[name]}行目の宣言またはvariant名と衝突"
            )


def _check_unique(values: Iterable[str], line: int, label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise GlyphError(f"{line}行目: {label} '{value}' が重複")
        seen.add(value)


# ---------- Rust生成 ----------


@dataclass
class Symbols:
    products: dict[str, ProductDecl]
    sums: dict[str, SumDecl]
    variants: dict[str, tuple[str, Variant]]
    externs: dict[str, ExternDecl]

    @classmethod
    def from_program(cls, program: Program) -> "Symbols":
        products: dict[str, ProductDecl] = {}
        sums: dict[str, SumDecl] = {}
        variants: dict[str, tuple[str, Variant]] = {}
        externs: dict[str, ExternDecl] = {}
        for decl in program.declarations:
            if isinstance(decl, ProductDecl):
                products[decl.name] = decl
            elif isinstance(decl, SumDecl):
                sums[decl.name] = decl
                for variant in decl.variants:
                    variants[variant.name] = (decl.name, variant)
            elif isinstance(decl, ExternDecl):
                externs[decl.name] = decl
        return cls(products, sums, variants, externs)


_TYPE_ALIASES = {
    "R": "Result",
    "O": "Option",
    "V": "Vec",
    "S": "String",  # 引数なしのSだけ。ユーザー定義型が同名ならユーザー定義を優先する。
}


class RustGenerator:
    def __init__(self, program: Program):
        self.program = program
        self.symbols = Symbols.from_program(program)

    def generate(self) -> str:
        out: list[str] = [
            "// @generated by glyphc. Do not edit by hand.",
            "#![allow(dead_code)]",
            "",
        ]
        for decl in self.program.declarations:
            if isinstance(decl, ProductDecl):
                out.extend(self._product(decl))
            elif isinstance(decl, SumDecl):
                out.extend(self._sum(decl))
            elif isinstance(decl, AliasDecl):
                out.extend(self._alias(decl))
            elif isinstance(decl, ExternDecl):
                out.extend(
                    [
                        f"// effect boundary: {decl.name}{self._signature_tail(decl.params, decl.return_type)}",
                        "",
                    ]
                )
            elif isinstance(decl, FunctionDecl):
                out.extend(self._function(decl))
        return "\n".join(out).rstrip() + "\n"

    def _product(self, decl: ProductDecl) -> list[str]:
        lines = ["#[derive(Debug, Clone, PartialEq)]", f"pub struct {decl.name} {{"]
        for field in decl.fields:
            lines.append(f"    pub {field.name}: {self._type(field.ty)},")
        lines.extend(["}", ""])
        return lines

    def _sum(self, decl: SumDecl) -> list[str]:
        lines = ["#[derive(Debug, Clone, PartialEq)]", f"pub enum {decl.name} {{"]
        for variant in decl.variants:
            if variant.tuple_types:
                args = ", ".join(self._type(t) for t in variant.tuple_types)
                lines.append(f"    {variant.name}({args}),")
            elif variant.fields:
                lines.append(f"    {variant.name} {{")
                for field in variant.fields:
                    lines.append(f"        {field.name}: {self._type(field.ty)},")
                lines.append("    },")
            else:
                lines.append(f"    {variant.name},")
        lines.extend(["}", ""])
        return lines

    def _alias(self, decl: AliasDecl) -> list[str]:
        return [f"pub type {decl.name} = {self._type(decl.target)};", ""]

    def _function(self, decl: FunctionDecl) -> list[str]:
        signature = f"pub fn {decl.name}{self._signature_tail(decl.params, decl.return_type)} {{"
        lines = [signature]
        if decl.expression is not None:
            lines.append(f"    {self._expr(decl.expression)}")
        else:
            assert decl.guards
            for idx, clause in enumerate(decl.guards):
                if clause.condition is None:
                    if idx == 0:
                        lines.append(f"    {self._expr(clause.value)}")
                    else:
                        lines.append("    else {")
                        lines.append(f"        {self._expr(clause.value)}")
                        lines.append("    }")
                else:
                    prefix = "if" if idx == 0 else "else if"
                    lines.append(f"    {prefix} {self._expr(clause.condition)} {{")
                    lines.append(f"        {self._expr(clause.value)}")
                    lines.append("    }")
        lines.extend(["}", ""])
        return lines

    def _signature_tail(self, params: Sequence[Param], return_type: TypeRef) -> str:
        args = ", ".join(f"{p.name}: {self._type(p.ty)}" for p in params)
        return f"({args}) -> {self._type(return_type)}"

    def _type(self, ty: TypeRef) -> str:
        if ty.name == "()":
            return "()"
        if ty.name == "tuple":
            inner = ", ".join(self._type(a) for a in ty.args)
            if len(ty.args) == 1:
                inner += ","
            return f"({inner})"
        name = ty.name
        if name not in self.symbols.products and name not in self.symbols.sums:
            name = _TYPE_ALIASES.get(name, name)
        if ty.args:
            return f"{name}<{', '.join(self._type(a) for a in ty.args)}>"
        return name

    def _expr(self, expr: Expr, parent_prec: int = 0) -> str:
        if isinstance(expr, NameExpr):
            if expr.name in self.symbols.variants:
                enum_name, variant = self.symbols.variants[expr.name]
                if variant.tuple_types or variant.fields:
                    raise GlyphError(f"variant '{expr.name}' には引数が必要")
                return f"{enum_name}::{expr.name}"
            if expr.name == "None":
                return "None"
            return expr.name
        if isinstance(expr, NumberExpr):
            return expr.value
        if isinstance(expr, BoolExpr):
            return "true" if expr.value else "false"
        if isinstance(expr, FieldExpr):
            return f"{self._expr(expr.base, 80)}.{expr.field}"
        if isinstance(expr, TryExpr):
            return f"{self._expr(expr.expr, 80)}?"
        if isinstance(expr, UnaryExpr):
            text = f"{expr.op}{self._expr(expr.expr, 60)}"
            return f"({text})" if parent_prec > 60 else text
        if isinstance(expr, BinaryExpr):
            rust_op = {"|": "||", "&": "&&", "=": "=="}.get(expr.op, expr.op)
            prec = _PRECEDENCE[expr.op]
            text = f"{self._expr(expr.left, prec)} {rust_op} {self._expr(expr.right, prec + 1)}"
            return f"({text})" if parent_prec > prec else text
        if isinstance(expr, CallExpr):
            if not isinstance(expr.callee, NameExpr):
                callee = self._expr(expr.callee, 80)
                return f"{callee}({', '.join(self._expr(a) for a in expr.args)})"
            name = expr.callee.name
            args = [self._expr(a) for a in expr.args]

            if name in self.symbols.products:
                product = self.symbols.products[name]
                if len(args) != len(product.fields):
                    raise GlyphError(
                        f"積型 {name} は{len(product.fields)}引数だが{len(args)}引数を受け取った"
                    )
                fields = ", ".join(f"{field.name}: {arg}" for field, arg in zip(product.fields, args))
                return f"{name} {{ {fields} }}"

            if name in self.symbols.variants:
                enum_name, variant = self.symbols.variants[name]
                if variant.fields:
                    if len(args) != len(variant.fields):
                        raise GlyphError(
                            f"variant {name} は{len(variant.fields)}引数だが{len(args)}引数を受け取った"
                        )
                    fields = ", ".join(
                        f"{field.name}: {arg}" for field, arg in zip(variant.fields, args)
                    )
                    return f"{enum_name}::{name} {{ {fields} }}"
                if len(args) != len(variant.tuple_types):
                    raise GlyphError(
                        f"variant {name} は{len(variant.tuple_types)}引数だが{len(args)}引数を受け取った"
                    )
                return f"{enum_name}::{name}({', '.join(args)})"

            if name in {"Ok", "Err", "Some"}:
                if len(args) != 1:
                    raise GlyphError(f"{name} は1引数")
                return f"{name}({args[0]})"
            if name in {"min", "max"}:
                if len(args) != 2:
                    raise GlyphError(f"{name} は2引数")
                return f"std::cmp::{name}({args[0]}, {args[1]})"
            if name == "finite":
                if len(args) != 1:
                    raise GlyphError("finite は1引数")
                return f"{args[0]}.is_finite()"
            if name in self.symbols.externs:
                return f"crate::host::{name}({', '.join(args)})"
            return f"{name}({', '.join(args)})"
        raise TypeError(f"unknown expression: {expr!r}")


def compile_source(source: str) -> str:
    return RustGenerator(parse_program(source)).generate()


def compile_file(input_path: str | Path, output_path: str | Path) -> None:
    source = Path(input_path).read_text(encoding="utf-8")
    generated = compile_source(source)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(generated, encoding="utf-8")
