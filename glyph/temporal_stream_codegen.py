from __future__ import annotations

from typing import Sequence

from .compiler import GlyphError, Program, RustGenerator
from .temporal import Always, Atom, Eventually, Implies, SpecDecl, Until, Within


def _pascal_case(name: str) -> str:
    result = "".join(part[:1].upper() + part[1:] for part in name.split("_") if part)
    return result or "Temporal"


class TemporalStreamingRustGenerator:
    """頻出時相式を全履歴なしの専用状態機械へ変換する。"""

    def __init__(self, program: Program, specs: Sequence[SpecDecl]):
        self.program = program
        self.specs = tuple(specs)
        self.base = RustGenerator(program)

    def generate(self) -> str:
        declared = {decl.name for decl in self.program.declarations}
        out: list[str] = []
        generated: set[str] = set()
        for spec in self.specs:
            monitor = f"{_pascal_case(spec.name)}StreamingMonitor"
            if monitor in declared or monitor in generated:
                raise GlyphError(f"{spec.line}行目: 生成逐次モニタ名 '{monitor}' が衝突する")
            lines = self._spec(spec, monitor)
            if lines:
                generated.add(monitor)
                out.extend(lines)
        return "\n".join(out).rstrip() + ("\n" if out else "")

    def _spec(self, spec: SpecDecl, monitor: str) -> list[str]:
        formula = spec.formula
        if isinstance(formula, Always) and isinstance(formula.value, Atom):
            return self._always_atom(spec, monitor, formula.value)
        if isinstance(formula, Eventually) and isinstance(formula.value, Atom):
            return self._eventually_atom(spec, monitor, formula.value)
        if isinstance(formula, Within) and isinstance(formula.value, Atom):
            return self._within_atom(spec, monitor, formula)
        if (
            isinstance(formula, Until)
            and isinstance(formula.hold, Atom)
            and isinstance(formula.target, Atom)
        ):
            return self._until_atoms(spec, monitor, formula)
        if isinstance(formula, Always):
            inner = formula.value
            if isinstance(inner, Implies) and isinstance(inner.premise, Atom):
                consequence = inner.consequence
                if isinstance(consequence, Within) and isinstance(consequence.value, Atom):
                    return self._bounded_response(
                        spec,
                        monitor,
                        inner.premise,
                        consequence.value,
                        consequence.milliseconds,
                    )
                if isinstance(consequence, Eventually) and isinstance(consequence.value, Atom):
                    return self._unbounded_response(
                        spec, monitor, inner.premise, consequence.value
                    )
            if isinstance(inner, Within) and isinstance(inner.value, Atom):
                return self._periodic_within(
                    spec, monitor, inner.value, inner.milliseconds
                )
            if isinstance(inner, Eventually) and isinstance(inner.value, Atom):
                return self._finite_last_value(spec, monitor, inner.value)
        if (
            isinstance(formula, Eventually)
            and isinstance(formula.value, Always)
            and isinstance(formula.value.value, Atom)
        ):
            return self._finite_last_value(spec, monitor, formula.value.value)
        return []

    def _args(self, spec: SpecDecl) -> str:
        params = [f"{param.name}: {self.base._type(param.ty)}" for param in spec.params]
        return ", ".join(["at_ms: u64", *params])

    @staticmethod
    def _common_fields(extra: Sequence[str]) -> list[str]:
        return [
            "    seen: bool,",
            "    last_at_ms: Option<u64>,",
            *extra,
        ]

    @staticmethod
    def _step_prefix() -> list[str]:
        return [
            "        if let Some(last) = self.last_at_ms {",
            '            assert!(at_ms >= last, "temporal observation time must be monotonic");',
            "        }",
            "        self.last_at_ms = Some(at_ms);",
            "        self.seen = true;",
        ]

    @staticmethod
    def _reset() -> list[str]:
        return [
            "    pub fn reset(&mut self) {",
            "        *self = Self::default();",
            "    }",
            "}",
            "",
        ]

    def _header(self, monitor: str, extra: Sequence[str]) -> list[str]:
        return [
            "#[derive(Debug, Default)]",
            f"pub struct {monitor} {{",
            *self._common_fields(extra),
            "}",
            "",
            f"impl {monitor} {{",
            "    pub fn new() -> Self {",
            "        Self::default()",
            "    }",
            "",
        ]

    def _expr(self, atom: Atom) -> str:
        return self.base._expr(atom.expr)

    def _always_atom(self, spec: SpecDecl, monitor: str, atom: Atom) -> list[str]:
        expr = self._expr(atom)
        lines = self._header(monitor, ["    violated: bool,"])
        lines.extend([f"    pub fn step(&mut self, {self._args(spec)}) -> TemporalVerdict {{"])
        lines.extend(self._step_prefix())
        lines.extend(
            [
                f"        if !({expr}) {{",
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
            ]
        )
        lines.extend(self._reset())
        return lines

    def _eventually_atom(self, spec: SpecDecl, monitor: str, atom: Atom) -> list[str]:
        expr = self._expr(atom)
        lines = self._header(monitor, ["    satisfied: bool,"])
        lines.extend([f"    pub fn step(&mut self, {self._args(spec)}) -> TemporalVerdict {{"])
        lines.extend(self._step_prefix())
        lines.extend(
            [
                f"        if {expr} {{",
                "            self.satisfied = true;",
                "        }",
                "        self.verdict()",
                "    }",
                "",
                "    pub fn verdict(&self) -> TemporalVerdict {",
                "        if self.satisfied {",
                "            TemporalVerdict::Satisfied",
                "        } else {",
                "            TemporalVerdict::Pending",
                "        }",
                "    }",
                "",
                "    pub fn finish(&self) -> TemporalVerdict {",
                "        if !self.seen {",
                "            TemporalVerdict::Pending",
                "        } else if self.satisfied {",
                "            TemporalVerdict::Satisfied",
                "        } else {",
                "            TemporalVerdict::Violated",
                "        }",
                "    }",
                "",
            ]
        )
        lines.extend(self._reset())
        return lines

    def _within_atom(self, spec: SpecDecl, monitor: str, formula: Within) -> list[str]:
        expr = self._expr(formula.value)
        lines = self._header(
            monitor,
            [
                "    start_ms: Option<u64>,",
                "    satisfied: bool,",
                "    violated: bool,",
            ],
        )
        lines.extend([f"    pub fn step(&mut self, {self._args(spec)}) -> TemporalVerdict {{"])
        lines.extend(self._step_prefix())
        lines.extend(
            [
                "        let start = *self.start_ms.get_or_insert(at_ms);",
                f"        let deadline = start.saturating_add({formula.milliseconds});",
                "        if at_ms > deadline {",
                "            self.violated = true;",
                f"        }} else if {expr} {{",
                "            self.satisfied = true;",
                "        }",
                "        self.verdict()",
                "    }",
                "",
                "    pub fn verdict(&self) -> TemporalVerdict {",
                "        if self.violated {",
                "            TemporalVerdict::Violated",
                "        } else if self.satisfied {",
                "            TemporalVerdict::Satisfied",
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
                "        } else if self.satisfied {",
                "            TemporalVerdict::Satisfied",
                "        } else {",
                "            TemporalVerdict::Violated",
                "        }",
                "    }",
                "",
            ]
        )
        lines.extend(self._reset())
        return lines

    def _until_atoms(self, spec: SpecDecl, monitor: str, formula: Until) -> list[str]:
        hold = self._expr(formula.hold)
        target = self._expr(formula.target)
        weak_finish = "TemporalVerdict::Satisfied" if formula.weak else "TemporalVerdict::Violated"
        lines = self._header(
            monitor,
            ["    satisfied: bool,", "    violated: bool,"],
        )
        lines.extend([f"    pub fn step(&mut self, {self._args(spec)}) -> TemporalVerdict {{"])
        lines.extend(self._step_prefix())
        lines.extend(
            [
                "        if self.satisfied || self.violated {",
                "            return self.verdict();",
                "        }",
                f"        if {target} {{",
                "            self.satisfied = true;",
                f"        }} else if !({hold}) {{",
                "            self.violated = true;",
                "        }",
                "        self.verdict()",
                "    }",
                "",
                "    pub fn verdict(&self) -> TemporalVerdict {",
                "        if self.violated {",
                "            TemporalVerdict::Violated",
                "        } else if self.satisfied {",
                "            TemporalVerdict::Satisfied",
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
                "        } else if self.satisfied {",
                "            TemporalVerdict::Satisfied",
                "        } else {",
                f"            {weak_finish}",
                "        }",
                "    }",
                "",
            ]
        )
        lines.extend(self._reset())
        return lines

    def _bounded_response(
        self,
        spec: SpecDecl,
        monitor: str,
        trigger: Atom,
        target: Atom,
        duration: int,
    ) -> list[str]:
        trigger_expr = self._expr(trigger)
        target_expr = self._expr(target)
        lines = self._header(
            monitor,
            ["    pending_deadline_ms: Option<u64>,", "    violated: bool,"],
        )
        lines.extend([f"    pub fn step(&mut self, {self._args(spec)}) -> TemporalVerdict {{"])
        lines.extend(self._step_prefix())
        lines.extend(
            [
                "        if let Some(deadline) = self.pending_deadline_ms {",
                "            if at_ms > deadline {",
                "                self.violated = true;",
                "            }",
                "        }",
                "        if !self.violated {",
                f"            if {target_expr} {{",
                "                self.pending_deadline_ms = None;",
                f"            }} else if {trigger_expr} && self.pending_deadline_ms.is_none() {{",
                f"                self.pending_deadline_ms = Some(at_ms.saturating_add({duration}));",
                "            }",
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
                "        } else if self.violated || self.pending_deadline_ms.is_some() {",
                "            TemporalVerdict::Violated",
                "        } else {",
                "            TemporalVerdict::Satisfied",
                "        }",
                "    }",
                "",
            ]
        )
        lines.extend(self._reset())
        return lines

    def _unbounded_response(
        self,
        spec: SpecDecl,
        monitor: str,
        trigger: Atom,
        target: Atom,
    ) -> list[str]:
        trigger_expr = self._expr(trigger)
        target_expr = self._expr(target)
        lines = self._header(monitor, ["    pending: bool,"])
        lines.extend([f"    pub fn step(&mut self, {self._args(spec)}) -> TemporalVerdict {{"])
        lines.extend(self._step_prefix())
        lines.extend(
            [
                f"        if {target_expr} {{",
                "            self.pending = false;",
                f"        }} else if {trigger_expr} {{",
                "            self.pending = true;",
                "        }",
                "        TemporalVerdict::Pending",
                "    }",
                "",
                "    pub fn verdict(&self) -> TemporalVerdict {",
                "        TemporalVerdict::Pending",
                "    }",
                "",
                "    pub fn finish(&self) -> TemporalVerdict {",
                "        if !self.seen {",
                "            TemporalVerdict::Pending",
                "        } else if self.pending {",
                "            TemporalVerdict::Violated",
                "        } else {",
                "            TemporalVerdict::Satisfied",
                "        }",
                "    }",
                "",
            ]
        )
        lines.extend(self._reset())
        return lines

    def _periodic_within(
        self,
        spec: SpecDecl,
        monitor: str,
        target: Atom,
        duration: int,
    ) -> list[str]:
        target_expr = self._expr(target)
        lines = self._header(
            monitor,
            ["    pending_deadline_ms: Option<u64>,", "    violated: bool,"],
        )
        lines.extend([f"    pub fn step(&mut self, {self._args(spec)}) -> TemporalVerdict {{"])
        lines.extend(self._step_prefix())
        lines.extend(
            [
                "        if let Some(deadline) = self.pending_deadline_ms {",
                "            if at_ms > deadline {",
                "                self.violated = true;",
                "            }",
                "        }",
                "        if !self.violated {",
                f"            if {target_expr} {{",
                "                self.pending_deadline_ms = None;",
                "            } else if self.pending_deadline_ms.is_none() {",
                f"                self.pending_deadline_ms = Some(at_ms.saturating_add({duration}));",
                "            }",
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
                "        } else if self.violated || self.pending_deadline_ms.is_some() {",
                "            TemporalVerdict::Violated",
                "        } else {",
                "            TemporalVerdict::Satisfied",
                "        }",
                "    }",
                "",
            ]
        )
        lines.extend(self._reset())
        return lines

    def _finite_last_value(self, spec: SpecDecl, monitor: str, atom: Atom) -> list[str]:
        expr = self._expr(atom)
        lines = self._header(monitor, ["    last_value: bool,"])
        lines.extend([f"    pub fn step(&mut self, {self._args(spec)}) -> TemporalVerdict {{"])
        lines.extend(self._step_prefix())
        lines.extend(
            [
                f"        self.last_value = {expr};",
                "        TemporalVerdict::Pending",
                "    }",
                "",
                "    pub fn verdict(&self) -> TemporalVerdict {",
                "        TemporalVerdict::Pending",
                "    }",
                "",
                "    pub fn finish(&self) -> TemporalVerdict {",
                "        if !self.seen {",
                "            TemporalVerdict::Pending",
                "        } else if self.last_value {",
                "            TemporalVerdict::Satisfied",
                "        } else {",
                "            TemporalVerdict::Violated",
                "        }",
                "    }",
                "",
            ]
        )
        lines.extend(self._reset())
        return lines


def append_streaming_temporal_rust(
    logic: str, program: Program, specs: Sequence[SpecDecl]
) -> str:
    streaming = TemporalStreamingRustGenerator(program, specs).generate()
    if not streaming:
        return logic
    return logic.rstrip() + "\n\n" + streaming
