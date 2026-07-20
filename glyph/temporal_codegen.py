from __future__ import annotations

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
    Program,
    RustGenerator,
    TryExpr,
    UnaryExpr,
    _PRECEDENCE,
)
from .temporal import (
    Always,
    And,
    Atom,
    Eventually,
    Formula,
    Implies,
    Not,
    Or,
    SpecDecl,
    Until,
    Within,
)


def _pascal_case(name: str) -> str:
    result = "".join(part[:1].upper() + part[1:] for part in name.split("_") if part)
    return result or "Temporal"


class TemporalRustGenerator:
    def __init__(self, program: Program, specs: Sequence[SpecDecl]):
        self.program = program
        self.specs = tuple(specs)
        self.base = RustGenerator(program)

    def generate(self) -> str:
        if not self.specs:
            return ""
        declared = {decl.name for decl in self.program.declarations}
        if "TemporalVerdict" in declared:
            raise GlyphError("宣言名 'TemporalVerdict' は時相制約ランタイムと衝突する")

        monitor_names: dict[str, str] = {}
        for spec in self.specs:
            monitor = f"{_pascal_case(spec.name)}Monitor"
            if monitor in declared or monitor in monitor_names:
                raise GlyphError(f"{spec.line}行目: 生成モニタ名 '{monitor}' が衝突する")
            monitor_names[monitor] = spec.name

        out = [
            "#[derive(Debug, Clone, Copy, PartialEq, Eq)]",
            "pub enum TemporalVerdict {",
            "    Satisfied,",
            "    Violated,",
            "    Pending,",
            "}",
            "",
            "fn temporal_not(value: TemporalVerdict) -> TemporalVerdict {",
            "    match value {",
            "        TemporalVerdict::Satisfied => TemporalVerdict::Violated,",
            "        TemporalVerdict::Violated => TemporalVerdict::Satisfied,",
            "        TemporalVerdict::Pending => TemporalVerdict::Pending,",
            "    }",
            "}",
            "",
            "fn temporal_and(left: TemporalVerdict, right: TemporalVerdict) -> TemporalVerdict {",
            "    match (left, right) {",
            "        (TemporalVerdict::Violated, _) | (_, TemporalVerdict::Violated) => TemporalVerdict::Violated,",
            "        (TemporalVerdict::Satisfied, TemporalVerdict::Satisfied) => TemporalVerdict::Satisfied,",
            "        _ => TemporalVerdict::Pending,",
            "    }",
            "}",
            "",
            "fn temporal_or(left: TemporalVerdict, right: TemporalVerdict) -> TemporalVerdict {",
            "    match (left, right) {",
            "        (TemporalVerdict::Satisfied, _) | (_, TemporalVerdict::Satisfied) => TemporalVerdict::Satisfied,",
            "        (TemporalVerdict::Violated, TemporalVerdict::Violated) => TemporalVerdict::Violated,",
            "        _ => TemporalVerdict::Pending,",
            "    }",
            "}",
            "",
        ]
        for spec in self.specs:
            out.extend(self._spec(spec))
        return "\n".join(out).rstrip() + "\n"

    def _spec(self, spec: SpecDecl) -> list[str]:
        monitor = f"{_pascal_case(spec.name)}Monitor"
        observation = f"{_pascal_case(spec.name)}Observation"
        params = {param.name for param in spec.params}
        nodes: list[Formula] = []
        ids: dict[int, int] = {}

        def register(formula: Formula) -> int:
            key = id(formula)
            if key in ids:
                return ids[key]
            children: tuple[Formula, ...]
            if isinstance(formula, (Not, Always, Eventually, Within)):
                children = (formula.value,)
            elif isinstance(formula, (And, Or)):
                children = (formula.left, formula.right)
            elif isinstance(formula, Implies):
                children = (formula.premise, formula.consequence)
            elif isinstance(formula, Until):
                children = (formula.hold, formula.target)
            else:
                children = ()
            for child in children:
                register(child)
            ids[key] = len(nodes)
            nodes.append(formula)
            return ids[key]

        root = register(spec.formula)
        lines = ["#[derive(Debug, Clone)]", f"struct {observation} {{", "    at_ms: u64,"]
        for param in spec.params:
            lines.append(f"    {param.name}: {self.base._type(param.ty)},")
        lines.extend(
            [
                "}",
                "",
                "#[derive(Debug, Default)]",
                f"pub struct {monitor} {{",
                f"    trace: Vec<{observation}>,",
                "}",
                "",
                f"impl {monitor} {{",
                "    pub fn new() -> Self {",
                "        Self::default()",
                "    }",
                "",
            ]
        )
        args = ", ".join(
            ["at_ms: u64", *[f"{p.name}: {self.base._type(p.ty)}" for p in spec.params]]
        )
        fields = ", ".join(["at_ms", *[p.name for p in spec.params]])
        lines.extend(
            [
                f"    pub fn step(&mut self, {args}) -> TemporalVerdict {{",
                "        if let Some(last) = self.trace.last() {",
                '            assert!(at_ms >= last.at_ms, "temporal observation time must be monotonic");',
                "        }",
                f"        self.trace.push({observation} {{ {fields} }});",
                f"        self.eval_{root}(0, false)",
                "    }",
                "",
                "    pub fn verdict(&self) -> TemporalVerdict {",
                "        if self.trace.is_empty() {",
                "            TemporalVerdict::Pending",
                "        } else {",
                f"            self.eval_{root}(0, false)",
                "        }",
                "    }",
                "",
                "    pub fn finish(&self) -> TemporalVerdict {",
                "        if self.trace.is_empty() {",
                "            TemporalVerdict::Pending",
                "        } else {",
                f"            self.eval_{root}(0, true)",
                "        }",
                "    }",
                "",
                "    pub fn reset(&mut self) {",
                "        self.trace.clear();",
                "    }",
                "",
            ]
        )
        for node_id, formula in enumerate(nodes):
            lines.extend(self._eval_method(node_id, formula, ids, params))
        lines.extend(["}", ""])
        return lines

    def _eval_method(
        self,
        node_id: int,
        formula: Formula,
        ids: dict[int, int],
        params: set[str],
    ) -> list[str]:
        head = f"    fn eval_{node_id}(&self, i: usize, closed: bool) -> TemporalVerdict {{"
        if isinstance(formula, Atom):
            expression = self._expr(formula.expr, params)
            return [
                head,
                "        if i >= self.trace.len() {",
                "            return TemporalVerdict::Pending;",
                "        }",
                f"        if {expression} {{",
                "            TemporalVerdict::Satisfied",
                "        } else {",
                "            TemporalVerdict::Violated",
                "        }",
                "    }",
                "",
            ]
        if isinstance(formula, Not):
            child = ids[id(formula.value)]
            return [head, f"        temporal_not(self.eval_{child}(i, closed))", "    }", ""]
        if isinstance(formula, And):
            left, right = ids[id(formula.left)], ids[id(formula.right)]
            return [
                head,
                f"        temporal_and(self.eval_{left}(i, closed), self.eval_{right}(i, closed))",
                "    }",
                "",
            ]
        if isinstance(formula, Or):
            left, right = ids[id(formula.left)], ids[id(formula.right)]
            return [
                head,
                f"        temporal_or(self.eval_{left}(i, closed), self.eval_{right}(i, closed))",
                "    }",
                "",
            ]
        if isinstance(formula, Implies):
            left, right = ids[id(formula.premise)], ids[id(formula.consequence)]
            return [
                head,
                f"        temporal_or(temporal_not(self.eval_{left}(i, closed)), self.eval_{right}(i, closed))",
                "    }",
                "",
            ]
        if isinstance(formula, Always):
            child = ids[id(formula.value)]
            return [
                head,
                "        let mut all_satisfied = true;",
                "        for j in i..self.trace.len() {",
                f"            match self.eval_{child}(j, closed) {{",
                "                TemporalVerdict::Violated => return TemporalVerdict::Violated,",
                "                TemporalVerdict::Pending => all_satisfied = false,",
                "                TemporalVerdict::Satisfied => {}",
                "            }",
                "        }",
                "        if closed && all_satisfied {",
                "            TemporalVerdict::Satisfied",
                "        } else {",
                "            TemporalVerdict::Pending",
                "        }",
                "    }",
                "",
            ]
        if isinstance(formula, Eventually):
            child = ids[id(formula.value)]
            return [
                head,
                "        for j in i..self.trace.len() {",
                f"            if self.eval_{child}(j, closed) == TemporalVerdict::Satisfied {{",
                "                return TemporalVerdict::Satisfied;",
                "            }",
                "        }",
                "        if closed {",
                "            TemporalVerdict::Violated",
                "        } else {",
                "            TemporalVerdict::Pending",
                "        }",
                "    }",
                "",
            ]
        if isinstance(formula, Within):
            child = ids[id(formula.value)]
            return [
                head,
                "        if i >= self.trace.len() {",
                "            return TemporalVerdict::Pending;",
                "        }",
                f"        let deadline = self.trace[i].at_ms.saturating_add({formula.milliseconds});",
                "        for j in i..self.trace.len() {",
                "            if self.trace[j].at_ms > deadline {",
                "                break;",
                "            }",
                f"            if self.eval_{child}(j, closed) == TemporalVerdict::Satisfied {{",
                "                return TemporalVerdict::Satisfied;",
                "            }",
                "        }",
                "        if closed || self.trace.last().is_some_and(|last| last.at_ms > deadline) {",
                "            TemporalVerdict::Violated",
                "        } else {",
                "            TemporalVerdict::Pending",
                "        }",
                "    }",
                "",
            ]
        if isinstance(formula, Until):
            hold, target = ids[id(formula.hold)], ids[id(formula.target)]
            weak_finish = "TemporalVerdict::Satisfied" if formula.weak else "TemporalVerdict::Violated"
            return [
                head,
                "        let mut hold_satisfied = true;",
                "        for j in i..self.trace.len() {",
                f"            if self.eval_{target}(j, closed) == TemporalVerdict::Satisfied {{",
                "                return if hold_satisfied {",
                "                    TemporalVerdict::Satisfied",
                "                } else {",
                "                    TemporalVerdict::Pending",
                "                };",
                "            }",
                f"            match self.eval_{hold}(j, closed) {{",
                "                TemporalVerdict::Violated => return TemporalVerdict::Violated,",
                "                TemporalVerdict::Pending => hold_satisfied = false,",
                "                TemporalVerdict::Satisfied => {}",
                "            }",
                "        }",
                "        if closed {",
                f"            if hold_satisfied {{ {weak_finish} }} else {{ TemporalVerdict::Pending }}",
                "        } else {",
                "            TemporalVerdict::Pending",
                "        }",
                "    }",
                "",
            ]
        raise TypeError(f"unknown temporal formula: {formula!r}")

    def _expr(self, expr: Expr, params: set[str], parent_prec: int = 0) -> str:
        if isinstance(expr, NameExpr):
            if expr.name in params:
                return f"self.trace[i].{expr.name}"
            return self.base._expr(expr, parent_prec)
        if isinstance(expr, NumberExpr):
            return expr.value
        if isinstance(expr, BoolExpr):
            return "true" if expr.value else "false"
        if isinstance(expr, FieldExpr):
            return f"{self._expr(expr.base, params, 80)}.{expr.field}"
        if isinstance(expr, TryExpr):
            return f"{self._expr(expr.expr, params, 80)}?"
        if isinstance(expr, UnaryExpr):
            text = f"{expr.op}{self._expr(expr.expr, params, 60)}"
            return f"({text})" if parent_prec > 60 else text
        if isinstance(expr, BinaryExpr):
            rust_op = {"|": "||", "&": "&&", "=": "=="}.get(expr.op, expr.op)
            precedence = _PRECEDENCE[expr.op]
            text = (
                f"{self._expr(expr.left, params, precedence)} {rust_op} "
                f"{self._expr(expr.right, params, precedence + 1)}"
            )
            return f"({text})" if parent_prec > precedence else text
        if isinstance(expr, CallExpr):
            if not isinstance(expr.callee, NameExpr):
                callee = self._expr(expr.callee, params, 80)
                args = ", ".join(self._expr(arg, params) for arg in expr.args)
                return f"{callee}({args})"
            name = expr.callee.name
            args = [self._expr(arg, params) for arg in expr.args]
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
            if name in self.base.symbols.externs:
                return f"crate::host::{name}({', '.join(args)})"
            return f"{name}({', '.join(args)})"
        raise TypeError(f"unknown expression: {expr!r}")


def append_temporal_rust(logic: str, program: Program, specs: Sequence[SpecDecl]) -> str:
    temporal = TemporalRustGenerator(program, specs).generate()
    if not temporal:
        return logic
    return logic.rstrip() + "\n\n" + temporal
