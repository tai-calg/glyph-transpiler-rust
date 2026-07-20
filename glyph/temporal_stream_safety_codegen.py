from __future__ import annotations

from typing import Sequence

from .compiler import GlyphError, Program, RustGenerator
from .temporal import Always, And, Atom, Formula, Implies, Not, Or, SpecDecl


def _pascal_case(name: str) -> str:
    result = "".join(part[:1].upper() + part[1:] for part in name.split("_") if part)
    return result or "Temporal"


class TemporalSafetyStreamingRustGenerator:
    """`□P`のPが瞬時状態式なら定数状態の安全性モニタへ変換する。"""

    def __init__(self, program: Program, specs: Sequence[SpecDecl]):
        self.program = program
        self.specs = tuple(specs)
        self.base = RustGenerator(program)

    def _state_expr(self, formula: Formula) -> str | None:
        if isinstance(formula, Atom):
            return self.base._expr(formula.expr)
        if isinstance(formula, Not):
            value = self._state_expr(formula.value)
            return None if value is None else f"!({value})"
        if isinstance(formula, And):
            left = self._state_expr(formula.left)
            right = self._state_expr(formula.right)
            return None if left is None or right is None else f"({left}) && ({right})"
        if isinstance(formula, Or):
            left = self._state_expr(formula.left)
            right = self._state_expr(formula.right)
            return None if left is None or right is None else f"({left}) || ({right})"
        if isinstance(formula, Implies):
            left = self._state_expr(formula.premise)
            right = self._state_expr(formula.consequence)
            return None if left is None or right is None else f"!({left}) || ({right})"
        return None

    def generate(self) -> str:
        declared = {decl.name for decl in self.program.declarations}
        out: list[str] = []
        generated: set[str] = set()
        for spec in self.specs:
            formula = spec.formula
            if not isinstance(formula, Always) or isinstance(formula.value, Atom):
                continue
            expression = self._state_expr(formula.value)
            if expression is None:
                continue
            monitor = f"{_pascal_case(spec.name)}StreamingMonitor"
            if monitor in declared or monitor in generated:
                raise GlyphError(f"{spec.line}行目: 生成逐次モニタ名 '{monitor}' が衝突する")
            generated.add(monitor)
            out.extend(self._spec(spec, monitor, expression))
        return "\n".join(out).rstrip() + ("\n" if out else "")

    def _spec(self, spec: SpecDecl, monitor: str, expression: str) -> list[str]:
        params = ", ".join(
            [
                "at_ms: u64",
                *[
                    f"{param.name}: {self.base._type(param.ty)}"
                    for param in spec.params
                ],
            ]
        )
        return [
            "#[derive(Debug, Default)]",
            f"pub struct {monitor} {{",
            "    seen: bool,",
            "    last_at_ms: Option<u64>,",
            "    violated: bool,",
            "}",
            "",
            f"impl {monitor} {{",
            "    pub fn new() -> Self {",
            "        Self::default()",
            "    }",
            "",
            f"    pub fn step(&mut self, {params}) -> TemporalVerdict {{",
            "        if let Some(last) = self.last_at_ms {",
            '            assert!(at_ms >= last, "temporal observation time must be monotonic");',
            "        }",
            "        self.last_at_ms = Some(at_ms);",
            "        self.seen = true;",
            f"        if !({expression}) {{",
            "            self.violated = true;",
            "        }",
            "        self.verdict()",
            "    }",
            "",
            "    pub fn verdict(&self) -> TemporalVerdict {",
            "        if self.violated {",
            "            TemporalVerdict::Violated",
            "        } else {",
            "            TemporalVerdict::Pending",
            "        }",
            "    }",
            "",
            "    pub fn finish(&self) -> TemporalVerdict {",
            "        if !self.seen {",
            "            TemporalVerdict::Pending",
            "        } else if self.violated {",
            "            TemporalVerdict::Violated",
            "        } else {",
            "            TemporalVerdict::Satisfied",
            "        }",
            "    }",
            "",
            "    pub fn reset(&mut self) {",
            "        *self = Self::default();",
            "    }",
            "}",
            "",
        ]


def append_safety_streaming_temporal_rust(
    logic: str, program: Program, specs: Sequence[SpecDecl]
) -> str:
    streaming = TemporalSafetyStreamingRustGenerator(program, specs).generate()
    if not streaming:
        return logic
    return logic.rstrip() + "\n\n" + streaming
