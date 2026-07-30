from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ..artifacts import CompilationModel
from ..compiler import CallExpr, Expr, ExternDecl, NameExpr
from .effect_contract import VerifiedEffectContractRegistry
from .lowering import LoweringIssue, lower_compilation_model_report
from .teir import Assign, Branch, EffectCall, PropagateFailure, Return, TransitionCall


EFFECT_CONTRACT_AUDIT_VERSION = 2


@dataclass(frozen=True)
class EffectContractEntryCoverage:
    entry: str
    reachable_functions: tuple[str, ...]
    required_operations: tuple[str, ...]
    covered_operations: tuple[str, ...]
    missing_operations: tuple[str, ...]
    lowering_issues: tuple[LoweringIssue, ...]

    @property
    def complete(self) -> bool:
        return not self.missing_operations and not self.lowering_issues

    def to_ir(self) -> dict[str, object]:
        return {
            "entry": self.entry,
            "complete": self.complete,
            "reachable_functions": list(self.reachable_functions),
            "required_operations": list(self.required_operations),
            "covered_operations": list(self.covered_operations),
            "missing_operations": list(self.missing_operations),
            "lowering_issues": [item.to_ir() for item in self.lowering_issues],
        }


@dataclass(frozen=True)
class EffectContractCoverageReport:
    entries: tuple[EffectContractEntryCoverage, ...]

    @property
    def complete(self) -> bool:
        return bool(self.entries) and all(item.complete for item in self.entries)

    @property
    def missing_operations(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    operation
                    for entry in self.entries
                    for operation in entry.missing_operations
                }
            )
        )

    def to_ir(self) -> dict[str, object]:
        return {
            "version": EFFECT_CONTRACT_AUDIT_VERSION,
            "complete": self.complete,
            "missing_operations": list(self.missing_operations),
            "entries": [item.to_ir() for item in self.entries],
        }


def audit_effect_contract_coverage(
    model: CompilationModel,
    entries: Iterable[str],
    contracts: VerifiedEffectContractRegistry,
) -> EffectContractCoverageReport:
    """Audit every outbound Effect reachable from each System entry.

    Glyph uses the same internal declaration node for ``ext`` inputs and ``!``
    Effects. The public source spelling remains authoritative here: inbound
    ``ext`` calls are not Effect contracts and therefore must not be accepted as
    outbound Effect coverage.

    The audit is structural and conservative. A reachable Effect call requires an
    explicit entry-visible contract even when a branch later proves unreachable.
    This avoids treating solver precision as permission to omit an external
    boundary contract.
    """

    lowering = lower_compilation_model_report(model)
    functions = dict(lowering.functions)
    function_names = frozenset(functions)
    external_inputs = _source_external_input_names(model)
    effect_names = frozenset(
        declaration.name
        for declaration in model.program.declarations
        if isinstance(declaration, ExternDecl)
        and declaration.name not in external_inputs
    )
    facts = {
        name: _function_facts(function, function_names, effect_names)
        for name, function in functions.items()
    }
    issues_by_function: dict[str, list[LoweringIssue]] = {}
    for issue in lowering.issues:
        issues_by_function.setdefault(issue.function, []).append(issue)

    results: list[EffectContractEntryCoverage] = []
    for entry in sorted(set(entries)):
        reachable: set[str] = set()
        required: set[str] = set()
        queue = [entry]
        while queue:
            function_name = queue.pop()
            if function_name in reachable:
                continue
            reachable.add(function_name)
            called_functions, called_effects = facts.get(
                function_name,
                (frozenset(), frozenset()),
            )
            required.update(called_effects)
            queue.extend(sorted(called_functions - reachable))

        available = frozenset(contracts.resolve(entry))
        reachable_issues = tuple(
            issue
            for function_name in sorted(reachable)
            for issue in issues_by_function.get(function_name, ())
        )
        results.append(
            EffectContractEntryCoverage(
                entry=entry,
                reachable_functions=tuple(sorted(reachable)),
                required_operations=tuple(sorted(required)),
                covered_operations=tuple(sorted(required & available)),
                missing_operations=tuple(sorted(required - available)),
                lowering_issues=reachable_issues,
            )
        )
    return EffectContractCoverageReport(tuple(results))


def _source_external_input_names(model: CompilationModel) -> frozenset[str]:
    names: set[str] = set()
    for original in model.preprocess.source.splitlines():
        code = original.split("#", 1)[0].rstrip()
        stripped = code.strip()
        if not stripped or code[:1].isspace() or not stripped.startswith("ext "):
            continue
        signature = stripped[len("ext ") :].strip()
        open_pos = signature.find("(")
        if open_pos > 0:
            names.add(signature[:open_pos].strip())
    return frozenset(names)


def _function_facts(
    function: object,
    function_names: frozenset[str],
    effect_names: frozenset[str],
) -> tuple[frozenset[str], frozenset[str]]:
    calls: set[str] = set()
    effects: set[str] = set()
    for block in getattr(function, "blocks", ()):
        for instruction in block.instructions:
            if isinstance(instruction, EffectCall):
                if instruction.operation in effect_names:
                    effects.add(instruction.operation)
                expressions = instruction.arguments
            elif isinstance(instruction, Assign):
                expressions = (instruction.expression,)
            elif isinstance(instruction, TransitionCall):
                expressions = instruction.arguments
            else:
                expressions = ()
            for expression in expressions:
                _collect_expression_calls(expression, calls)

        terminator = block.terminator
        if isinstance(terminator, Branch):
            _collect_expression_calls(terminator.condition, calls)
        elif isinstance(terminator, Return) and terminator.value is not None:
            _collect_expression_calls(terminator.value, calls)
        elif isinstance(terminator, PropagateFailure):
            _collect_expression_calls(terminator.error, calls)

    effects.update(calls & effect_names)
    return frozenset(calls & function_names), frozenset(effects)


def _collect_expression_calls(expression: Expr, calls: set[str]) -> None:
    if isinstance(expression, CallExpr) and isinstance(expression.callee, NameExpr):
        calls.add(expression.callee.name)
    for child in vars(expression).values() if hasattr(expression, "__dict__") else ():
        if isinstance(child, Expr):
            _collect_expression_calls(child, calls)
        elif isinstance(child, tuple):
            for item in child:
                if isinstance(item, Expr):
                    _collect_expression_calls(item, calls)


__all__ = [
    "EFFECT_CONTRACT_AUDIT_VERSION",
    "EffectContractCoverageReport",
    "EffectContractEntryCoverage",
    "audit_effect_contract_coverage",
]
