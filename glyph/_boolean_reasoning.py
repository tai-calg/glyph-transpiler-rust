from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .compiler import BinaryExpr, BoolExpr, Expr, UnaryExpr
from .execution_ir import render_expr


_FALSE = 0
_TRUE = 1
_MAX_ATOMS = 96
_MAX_NODES = 50_000


class _BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class _Node:
    variable: int
    low: int
    high: int


class _Bdd:
    def __init__(self, variables: tuple[str, ...]) -> None:
        self._indices = {name: index for index, name in enumerate(variables)}
        self._nodes: dict[int, _Node] = {}
        self._unique: dict[tuple[int, int, int], int] = {}
        self._next = 2
        self._not_cache: dict[int, int] = {_FALSE: _TRUE, _TRUE: _FALSE}
        self._apply_cache: dict[tuple[str, int, int], int] = {}

    def atom(self, name: str) -> int:
        return self._make(self._indices[name], _FALSE, _TRUE)

    def negate(self, node: int) -> int:
        cached = self._not_cache.get(node)
        if cached is not None:
            return cached
        value = self._nodes[node]
        result = self._make(
            value.variable,
            self.negate(value.low),
            self.negate(value.high),
        )
        self._not_cache[node] = result
        return result

    def combine(self, operation: str, left: int, right: int) -> int:
        if operation not in {"and", "or"}:
            raise ValueError(operation)
        if left > right:
            left, right = right, left
        key = (operation, left, right)
        cached = self._apply_cache.get(key)
        if cached is not None:
            return cached

        if operation == "and":
            if left == _FALSE or right == _FALSE:
                return _FALSE
            if left == _TRUE:
                return right
            if right == _TRUE or left == right:
                return left
        else:
            if left == _TRUE or right == _TRUE:
                return _TRUE
            if left == _FALSE:
                return right
            if right == _FALSE or left == right:
                return left

        left_node = self._nodes[left]
        right_node = self._nodes[right]
        variable = min(left_node.variable, right_node.variable)
        left_low, left_high = (
            (left_node.low, left_node.high)
            if left_node.variable == variable
            else (left, left)
        )
        right_low, right_high = (
            (right_node.low, right_node.high)
            if right_node.variable == variable
            else (right, right)
        )
        result = self._make(
            variable,
            self.combine(operation, left_low, right_low),
            self.combine(operation, left_high, right_high),
        )
        self._apply_cache[key] = result
        return result

    def _make(self, variable: int, low: int, high: int) -> int:
        if low == high:
            return low
        key = (variable, low, high)
        existing = self._unique.get(key)
        if existing is not None:
            return existing
        if self._next >= _MAX_NODES:
            raise _BudgetExceeded
        identifier = self._next
        self._next += 1
        self._nodes[identifier] = _Node(variable, low, high)
        self._unique[key] = identifier
        return identifier


def _atom_key(expression: Expr) -> str:
    if isinstance(expression, BinaryExpr) and expression.op in {"==", "!="}:
        left = render_expr(expression.left)
        right = render_expr(expression.right)
        first, second = sorted((left, right))
        return f"{first}=={second}"
    return render_expr(expression)


def _atoms(expression: Expr, output: set[str]) -> None:
    if isinstance(expression, BoolExpr):
        return
    if isinstance(expression, UnaryExpr) and expression.op == "!":
        _atoms(expression.expr, output)
        return
    if isinstance(expression, BinaryExpr) and expression.op in {"&", "|"}:
        _atoms(expression.left, output)
        _atoms(expression.right, output)
        return
    output.add(_atom_key(expression))


def _compile(expression: Expr, bdd: _Bdd) -> int:
    if isinstance(expression, BoolExpr):
        return _TRUE if expression.value else _FALSE
    if isinstance(expression, UnaryExpr) and expression.op == "!":
        return bdd.negate(_compile(expression.expr, bdd))
    if isinstance(expression, BinaryExpr):
        if expression.op == "&":
            return bdd.combine(
                "and",
                _compile(expression.left, bdd),
                _compile(expression.right, bdd),
            )
        if expression.op == "|":
            return bdd.combine(
                "or",
                _compile(expression.left, bdd),
                _compile(expression.right, bdd),
            )
        if expression.op == "!=":
            return bdd.negate(bdd.atom(_atom_key(expression)))
    return bdd.atom(_atom_key(expression))


def propositional_truth(expression: Expr) -> bool | None:
    """Return exact propositional truth when the expression is constant.

    Non-boolean subexpressions are treated as stable atoms. Equality is
    canonicalized symmetrically and inequality is represented as the negation of
    the same equality atom. The reduced ordered BDD proves tautologies and
    contradictions such as ``x | !x`` and ``x & !x`` without enumerating every
    assignment. A bounded node budget converts pathological inputs to unknown
    rather than making compilation unbounded.
    """

    atoms: set[str] = set()
    _atoms(expression, atoms)
    if not atoms:
        return expression.value if isinstance(expression, BoolExpr) else None
    if len(atoms) > _MAX_ATOMS:
        return None
    try:
        root = _compile(expression, _Bdd(tuple(sorted(atoms))))
    except _BudgetExceeded:
        return None
    if root == _TRUE:
        return True
    if root == _FALSE:
        return False
    return None
