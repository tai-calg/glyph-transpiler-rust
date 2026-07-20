from __future__ import annotations

from typing import Sequence

from .compiler import GlyphError, Program, RustGenerator
from .temporal import Always, Atom, Implies, SpecDecl


def _pascal_case(name: str) -> str:
    result = "".join(part[:1].upper() + part[1:] for part in name.split("_") if part)
    return result or "Temporal"


class TemporalSafetyStreamingRustGenerator:
    """`□(P>>Q)`を定数状態の安全性モニタへ変換する。"""

    def __init__(self, program: Program, specs: Sequence[SpecDecl]):
        self.program = program
        self.specs = tuple(specs)
        self.base = RustGenerator(program)

    def generate(self) -> str:
        declared = {decl.name for decl in self.program.declarations}
        out: list[str] = []
        generated: set[str] = set()
        for spec in self.specs:
            formula = spec.formula
            if not (
                isinstance(formula, Always)
                and isinstance(formula.value, Implies)
                and isinstance(formula.value.premise, Atom)
                and isinstance(formula.value.consequence, Atom)
            ):
                continue
            monitor = f"{_pascal_case(spec.name)}StreamingMonitor"
            if monitor in declared or monitor in generated:
                raise GlyphError(f"{spec.line}行目: 生成逐次モニタ名 '{monitor}' が衝突する")
            generated.add(monitor)
            out.extend(self._spec(spec, monitor))
        return "\n".join(out).rstrip() + ("\n" if out else "")

    def _spec(self, spec: SpecDecl, monitor: str) -> list[str]:
        formula = spec.formula
        assert isinstance(formula, Always)
        implication = formula.value
        assert isinstance(implication, Implies)
        assert isinstance(implication.premise, Atom)
        assert isinstance(implication.consequence, Atom)
        premise = self.base._expr(implication.premise.expr)
        consequence = self.base._expr(implication.consequence.expr)
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
            f"        if ({premise}) && !({consequence}) {{",
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
