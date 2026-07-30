from __future__ import annotations

from collections import deque
from dataclasses import replace
from typing import Mapping, Sequence

from .._transition_branch_semantics import simplify_expr, substitute_expr
from ..artifacts import CompilationModel
from ..compiler import (
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    ExternDecl,
    FunctionDecl,
    NameExpr,
    ProductDecl,
    SumDecl,
    TryExpr,
    UnaryExpr,
)
from .abstract_state import (
    AbstractAnalysisResult,
    AbstractTransitionEvent,
    AnalysisBudget,
    GuardedAlternative,
    deduplicate_alternatives,
    initial_alternative,
    widen_alternatives,
)
from .abstract_store import AbstractStore
from .abstract_value import (
    AbstractValue,
    ApplicationValue,
    TopValue,
    value_from_expr,
)
from .effect_summary import (
    EffectSummary,
    apply_effect_summary,
    unknown_effect_summary,
)
from .exactness import (
    Approximation,
    ApproximationCause,
    ExactnessProof,
    ExactnessProofKind,
    ExactnessProofScope,
)
from .lowering import lower_compilation_model
from .preimage import PreimageStatus, compute_transition_call_preimage
from .teir import (
    Assign,
    Branch,
    EffectCall,
    Function,
    Jump,
    PropagateFailure,
    Return,
    TransitionCall,
)


class AbstractInterpreter:
    """Path-partitioned RTAI transfer engine for TEIR.

    The implementation is deliberately conservative: unsupported calls and
    Effect contracts become ``Unknown``; loop or path budgets widen traces and
    completion instead of dropping executions.
    """

    def __init__(
        self,
        model: CompilationModel,
        *,
        effect_summaries: Mapping[str, EffectSummary] | None = None,
        budget: AnalysisBudget = AnalysisBudget(),
    ) -> None:
        self.model = model
        self.functions = lower_compilation_model(model)
        self.effect_summaries = dict(effect_summaries or {})
        self.budget = budget
        self.products = {
            declaration.name: declaration
            for declaration in model.program.declarations
            if isinstance(declaration, ProductDecl)
        }
        self.product_fields = {
            name: tuple(field.name for field in declaration.fields)
            for name, declaration in self.products.items()
        }
        self.sums = {
            declaration.name: declaration
            for declaration in model.program.declarations
            if isinstance(declaration, SumDecl)
        }
        self.constants = frozenset(
            variant.name
            for declaration in self.sums.values()
            for variant in declaration.variants
        )
        self.effects = {
            declaration.name: declaration
            for declaration in model.program.declarations
            if isinstance(declaration, ExternDecl)
        }
        self.pure_functions = {
            declaration.name: declaration
            for declaration in model.program.declarations
            if isinstance(declaration, FunctionDecl)
            and not declaration.name.startswith("__glyph_block_")
        }
        self._steps = 0

    def analyze(self, function_name: str) -> AbstractAnalysisResult:
        function = self.functions.get(function_name)
        if function is None:
            raise ValueError(f"unknown TEIR function {function_name}")
        proof = ExactnessProof(
            ExactnessProofKind.STRUCTURAL_IDENTITY,
            ExactnessProofScope.TEIR_EXECUTION,
            f"symbolic entry state for {function_name}",
        )
        initial = initial_alternative(
            function.function_id,
            tuple(parameter.name for parameter in function.parameters),
            store=AbstractStore.empty(),
            approximation=Approximation.exact(proof),
        )
        queue: deque[tuple[str, GuardedAlternative]] = deque(
            [(function.entry_block, initial)]
        )
        block_states: dict[str, list[GuardedAlternative]] = {
            function.entry_block: [initial]
        }
        block_iterations: dict[str, int] = {}
        completed: list[GuardedAlternative] = []
        blocks = function.block_map
        self._steps = 0

        while queue:
            block_id, incoming = queue.popleft()
            self._steps += 1
            if self._steps > self.budget.max_steps:
                pending = [incoming, *(item for _, item in queue)]
                completed.append(
                    widen_alternatives(
                        pending,
                        max_phi_values=self.budget.max_phi_values,
                    ).degrade(
                        ApproximationCause.RESOURCE_LIMIT,
                        unknown=True,
                        transition_trace_top=True,
                        effect_trace_top=True,
                    )
                )
                break

            terminal_kinds = incoming.completion - {"running"}
            if terminal_kinds:
                completed.append(replace(incoming, completion=frozenset(terminal_kinds)))
            if "running" not in incoming.completion:
                continue
            alternative = replace(incoming, completion=frozenset({"running"}))
            block = blocks.get(block_id)
            if block is None:
                completed.append(
                    alternative.degrade(
                        "unknown-cfg-block",
                        unknown=True,
                        transition_trace_top=True,
                        effect_trace_top=True,
                    )
                )
                continue

            active = [alternative]
            for instruction in block.instructions:
                next_active: list[GuardedAlternative] = []
                for item in active:
                    transferred, terminals = self._transfer_instruction(
                        instruction,
                        item,
                    )
                    next_active.extend(transferred)
                    completed.extend(terminals)
                active = next_active
                if not active:
                    break

            for item in active:
                self._transfer_terminator(
                    function,
                    block.terminator,
                    item,
                    queue,
                    block_states,
                    block_iterations,
                    completed,
                )

        completed_values = deduplicate_alternatives(completed)
        if completed_values:
            approximation = Approximation.combine(
                item.approximation for item in completed_values
            )
        else:
            approximation = Approximation.unknown("no-completed-abstract-execution")
        reasons = tuple(
            sorted(
                {
                    reason
                    for item in completed_values
                    for reason in item.unknown_reasons
                }
            )
        )
        return AbstractAnalysisResult(
            function_name,
            completed_values,
            tuple(
                (block_id, deduplicate_alternatives(values))
                for block_id, values in sorted(block_states.items())
            ),
            approximation,
            reasons,
        )

    def _transfer_instruction(
        self,
        instruction: object,
        alternative: GuardedAlternative,
    ) -> tuple[list[GuardedAlternative], list[GuardedAlternative]]:
        if isinstance(instruction, Assign):
            symbolic, value, approximation = self._evaluate_expression(
                instruction.expression,
                alternative,
            )
            return [
                alternative.bind(
                    instruction.target,
                    value,
                    symbolic,
                    approximation=approximation,
                )
            ], []
        if isinstance(instruction, TransitionCall):
            return self._transfer_transition(instruction, alternative)
        if isinstance(instruction, EffectCall):
            return self._transfer_effect(instruction, alternative)
        unknown = alternative.degrade(
            "unsupported-teir-instruction",
            unknown=True,
            transition_trace_top=True,
            effect_trace_top=True,
        )
        return [], [replace(unknown, completion=frozenset({"unknown"}))]

    def _transfer_transition(
        self,
        instruction: TransitionCall,
        alternative: GuardedAlternative,
    ) -> tuple[list[GuardedAlternative], list[GuardedAlternative]]:
        symbolic_arguments = tuple(
            self._symbolic(argument, alternative)
            for argument in instruction.arguments
        )
        abstract_arguments = tuple(
            self._evaluate_expression(argument, alternative)[1]
            for argument in instruction.arguments
        )
        preimage = compute_transition_call_preimage(
            self.model,
            instruction.machine,
            symbolic_arguments,
            caller_condition=alternative.path_condition,
        )
        if preimage is None or not preimage.edges:
            unknown = alternative.bind(
                instruction.target,
                TopValue("transition-preimage-unavailable"),
                NameExpr(instruction.target),
            ).degrade(
                "transition-preimage-unavailable",
                unknown=True,
                transition_trace_top=True,
            )
            return [unknown], []

        running: list[GuardedAlternative] = []
        terminals: list[GuardedAlternative] = []
        for edge in preimage.edges:
            if edge.status is PreimageStatus.PROVEN_FALSE:
                continue
            approximation = Approximation.combine(
                (alternative.approximation, edge.approximation)
            )
            symbolic_result = edge.result_expression
            result_value = value_from_expr(
                symbolic_result,
                alternative.environment_map,
                context=instruction.function,
                product_fields=self.product_fields,
                constants=self.constants,
            )
            base = replace(
                alternative,
                path_condition=edge.condition,
                approximation=approximation,
                transition_trace=(
                    *alternative.transition_trace,
                    AbstractTransitionEvent(
                        instruction.machine,
                        instruction.function,
                        edge.edge_id,
                        abstract_arguments,
                        result_value,
                    ),
                ),
            )
            if not instruction.propagate_failure:
                running.append(
                    base.bind(
                        instruction.target,
                        result_value,
                        symbolic_result,
                        approximation=approximation,
                    )
                )
                continue

            result_kind, payload = _result_expression(symbolic_result)
            if result_kind == "ok" and payload is not None:
                payload_value = value_from_expr(
                    payload,
                    alternative.environment_map,
                    context=instruction.function,
                    product_fields=self.product_fields,
                    constants=self.constants,
                )
                running.append(
                    base.bind(
                        instruction.target,
                        payload_value,
                        payload,
                        approximation=approximation,
                    )
                )
                continue
            if result_kind == "err":
                terminals.append(
                    replace(
                        base,
                        completion=frozenset({"propagated-failure"}),
                        return_value=(
                            None
                            if payload is None
                            else value_from_expr(
                                payload,
                                alternative.environment_map,
                                context=instruction.function,
                                product_fields=self.product_fields,
                                constants=self.constants,
                            )
                        ),
                    )
                )
                continue

            uncertain = base.degrade(
                "transition-result-kind-unknown",
                unknown=True,
            )
            running.append(
                uncertain.bind(
                    instruction.target,
                    TopValue("transition-success-value-unknown"),
                    NameExpr(instruction.target),
                )
            )
            terminals.append(
                replace(
                    uncertain,
                    completion=frozenset({"propagated-failure"}),
                    return_value=TopValue("transition-failure-value-unknown"),
                )
            )
        return running, terminals

    def _transfer_effect(
        self,
        instruction: EffectCall,
        alternative: GuardedAlternative,
    ) -> tuple[list[GuardedAlternative], list[GuardedAlternative]]:
        abstract_arguments = tuple(
            self._evaluate_expression(argument, alternative)[1]
            for argument in instruction.arguments
        )
        symbolic_arguments = tuple(
            self._symbolic(argument, alternative)
            for argument in instruction.arguments
        )
        summary = self.effect_summaries.get(instruction.operation)
        if summary is None:
            summary = unknown_effect_summary(
                instruction.operation,
                tuple(f"arg{index}" for index in range(len(abstract_arguments))),
            )
        application = apply_effect_summary(summary, abstract_arguments, alternative.store)
        approximation = Approximation.combine(
            (alternative.approximation, application.approximation)
        )
        base = replace(
            alternative,
            store=application.store,
            effect_trace=(*alternative.effect_trace, application.event),
            approximation=approximation,
        )
        completions = set(application.completions)
        running: list[GuardedAlternative] = []
        terminals: list[GuardedAlternative] = []

        if instruction.propagate_failure:
            result_kind = _result_value_kind(application.result)
            if result_kind == "ok":
                payload = application.result.arguments[0]  # type: ignore[union-attr]
                if instruction.target is not None:
                    base = base.bind(
                        instruction.target,
                        payload,
                        NameExpr(instruction.target),
                        approximation=approximation,
                    )
                running.append(base)
                return running, terminals
            if result_kind == "err":
                payload = application.result.arguments[0]  # type: ignore[union-attr]
                terminals.append(
                    replace(
                        base,
                        completion=frozenset({"propagated-failure"}),
                        return_value=payload,
                    )
                )
                return running, terminals
            completions.update({"normal", "propagated-failure"})
            base = base.degrade("effect-result-kind-unknown", unknown=True)

        if "normal" in completions or "unknown" in completions:
            running_value = base
            if instruction.target is not None:
                running_value = running_value.bind(
                    instruction.target,
                    application.result,
                    (
                        symbolic_arguments[0]
                        if len(symbolic_arguments) == 1
                        else NameExpr(instruction.target)
                    ),
                    approximation=running_value.approximation,
                )
            running.append(running_value)
        terminal_kinds = {
            item
            for item in completions
            if item in {"propagated-failure", "terminated", "diverged", "unknown"}
        }
        if terminal_kinds:
            terminals.append(
                replace(
                    base,
                    completion=frozenset(terminal_kinds),
                    return_value=TopValue("effect-terminal-value"),
                )
            )
        return running, terminals

    def _transfer_terminator(
        self,
        function: Function,
        terminator: object,
        alternative: GuardedAlternative,
        queue: deque[tuple[str, GuardedAlternative]],
        block_states: dict[str, list[GuardedAlternative]],
        block_iterations: dict[str, int],
        completed: list[GuardedAlternative],
    ) -> None:
        if isinstance(terminator, Jump):
            self._enqueue(
                terminator.target,
                alternative,
                queue,
                block_states,
                block_iterations,
                completed,
            )
            return
        if isinstance(terminator, Branch):
            condition = self._symbolic(terminator.condition, alternative)
            if isinstance(condition, BoolExpr):
                self._enqueue(
                    terminator.true_block if condition.value else terminator.false_block,
                    alternative,
                    queue,
                    block_states,
                    block_iterations,
                    completed,
                )
                return
            self._enqueue(
                terminator.true_block,
                replace(
                    alternative,
                    path_condition=self._conjoin(
                        alternative.path_condition,
                        condition,
                    ),
                ),
                queue,
                block_states,
                block_iterations,
                completed,
            )
            self._enqueue(
                terminator.false_block,
                replace(
                    alternative,
                    path_condition=self._conjoin(
                        alternative.path_condition,
                        UnaryExpr("!", condition),
                    ),
                ),
                queue,
                block_states,
                block_iterations,
                completed,
            )
            return
        if isinstance(terminator, Return):
            if terminator.value is None:
                completed.append(
                    replace(
                        alternative,
                        completion=frozenset({"returned"}),
                        return_value=None,
                    )
                )
                return
            symbolic, value, approximation = self._evaluate_expression(
                terminator.value,
                alternative,
            )
            if self._contains_effectful_call(symbolic):
                completed.append(
                    replace(
                        alternative,
                        completion=frozenset({"returned", "propagated-failure", "unknown"}),
                        return_value=TopValue("effectful-return-expression"),
                        approximation=approximation.degrade(
                            "effectful-return-expression",
                            unknown=True,
                        ),
                        effect_trace_top=True,
                        unknown_reasons=tuple(
                            sorted(
                                set(
                                    (*alternative.unknown_reasons, "effectful-return-expression")
                                )
                            )
                        ),
                    )
                )
                return
            completed.append(
                replace(
                    alternative,
                    completion=frozenset({"returned"}),
                    return_value=value,
                    approximation=approximation,
                )
            )
            return
        if isinstance(terminator, PropagateFailure):
            _, value, approximation = self._evaluate_expression(
                terminator.error,
                alternative,
            )
            completed.append(
                replace(
                    alternative,
                    completion=frozenset({"propagated-failure"}),
                    return_value=value,
                    approximation=approximation,
                )
            )
            return
        completed.append(
            alternative.degrade(
                "unsupported-teir-terminator",
                unknown=True,
                transition_trace_top=True,
                effect_trace_top=True,
            )
        )

    def _enqueue(
        self,
        block_id: str,
        alternative: GuardedAlternative,
        queue: deque[tuple[str, GuardedAlternative]],
        block_states: dict[str, list[GuardedAlternative]],
        block_iterations: dict[str, int],
        completed: list[GuardedAlternative],
    ) -> None:
        values = block_states.setdefault(block_id, [])
        if any(alternative == existing for existing in values):
            return
        block_iterations[block_id] = block_iterations.get(block_id, 0) + 1
        if block_iterations[block_id] > self.budget.max_block_iterations:
            widened = widen_alternatives(
                (*values, alternative),
                max_phi_values=self.budget.max_phi_values,
            ).degrade(
                "block-fixpoint-budget",
                unknown=True,
                transition_trace_top=True,
                effect_trace_top=True,
            )
            block_states[block_id] = [widened]
            completed.append(
                replace(
                    widened,
                    completion=frozenset(
                        {
                            "returned",
                            "propagated-failure",
                            "terminated",
                            "diverged",
                            "unknown",
                        }
                    ),
                )
            )
            return
        values.append(alternative)
        if len(values) > self.budget.max_alternatives_per_block:
            widened = widen_alternatives(
                values,
                max_phi_values=self.budget.max_phi_values,
            )
            block_states[block_id] = [widened]
            queue.append((block_id, widened))
            return
        queue.append((block_id, alternative))

    def _evaluate_expression(
        self,
        expression: Expr,
        alternative: GuardedAlternative,
    ) -> tuple[Expr, AbstractValue, Approximation]:
        symbolic = self._symbolic(expression, alternative)
        value = value_from_expr(
            symbolic,
            alternative.environment_map,
            context="rtai",
            product_fields=self.product_fields,
            constants=self.constants,
        )
        approximation = alternative.approximation
        if isinstance(value, TopValue):
            approximation = approximation.degrade(value.reason, unknown=True)
        elif self._contains_unmodeled_call(symbolic):
            value = TopValue("unmodeled-call")
            approximation = approximation.degrade("unmodeled-call", unknown=True)
        return symbolic, value, approximation

    def _symbolic(
        self,
        expression: Expr,
        alternative: GuardedAlternative,
    ) -> Expr:
        substituted = substitute_expr(expression, alternative.symbolic_map)
        return simplify_expr(
            substituted,
            products=self.products,
            constants=self.constants,
        )

    def _conjoin(self, left: Expr, right: Expr) -> Expr:
        return simplify_expr(
            BinaryExpr("&", left, right),
            products=self.products,
            constants=self.constants,
        )

    def _contains_unmodeled_call(self, expression: Expr) -> bool:
        if isinstance(expression, CallExpr) and isinstance(expression.callee, NameExpr):
            name = expression.callee.name
            if name in self.product_fields or name in self.constants or name in {"Ok", "Err"}:
                return any(self._contains_unmodeled_call(item) for item in expression.args)
            if name in self.effects:
                return True
            if name in self.pure_functions:
                declaration = self.pure_functions[name]
                if declaration.expression is not None and not declaration.guards:
                    return any(self._contains_unmodeled_call(item) for item in expression.args)
            return True
        for value in vars(expression).values() if hasattr(expression, "__dict__") else ():
            if isinstance(value, Expr) and self._contains_unmodeled_call(value):
                return True
            if isinstance(value, tuple) and any(
                isinstance(item, Expr) and self._contains_unmodeled_call(item)
                for item in value
            ):
                return True
        return False

    def _contains_effectful_call(self, expression: Expr) -> bool:
        if isinstance(expression, CallExpr) and isinstance(expression.callee, NameExpr):
            if expression.callee.name in self.effects:
                return True
        for value in vars(expression).values() if hasattr(expression, "__dict__") else ():
            if isinstance(value, Expr) and self._contains_effectful_call(value):
                return True
            if isinstance(value, tuple) and any(
                isinstance(item, Expr) and self._contains_effectful_call(item)
                for item in value
            ):
                return True
        return False


def _result_expression(expression: Expr) -> tuple[str, Expr | None]:
    if (
        isinstance(expression, CallExpr)
        and isinstance(expression.callee, NameExpr)
        and expression.callee.name in {"Ok", "Err"}
        and len(expression.args) == 1
    ):
        return expression.callee.name.lower(), expression.args[0]
    return "unknown", None


def _result_value_kind(value: AbstractValue) -> str:
    if (
        isinstance(value, ApplicationValue)
        and value.operation in {"Ok", "Err"}
        and len(value.arguments) == 1
    ):
        return value.operation.lower()
    return "unknown"
