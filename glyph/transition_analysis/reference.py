from __future__ import annotations

from collections.abc import Mapping, Sequence

from ..compiler import FunctionDecl, parse_expr
from ..function_blocks import FunctionBlockLowering
from .concrete import (
    ConcreteExecutionError,
    ConcreteExecutionResult,
    ConcreteInterpreter,
    _PropagatedFailure,
)


class ReferenceInterpreter(ConcreteInterpreter):
    """Execute source AST and original ``:=`` blocks without TEIR CFGs.

    Expression value semantics are shared with the concrete runtime, while
    function control flow is interpreted directly from ``FunctionDecl`` and
    ``FunctionBlockLowering``.  This makes AST-vs-TEIR comparison sensitive to
    lowering errors without duplicating constructor and primitive semantics.
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        self.declarations = {
            declaration.name: declaration
            for declaration in self.model.program.declarations
            if isinstance(declaration, FunctionDecl)
            and not declaration.name.startswith("__glyph_block_")
        }
        self.source_blocks = {block.name: block for block in self.model.blocks}

    def run(
        self,
        function_name: str,
        arguments: Mapping[str, object] | Sequence[object],
    ) -> ConcreteExecutionResult:
        self._steps = 0
        self._transitions = []
        self._effects = []
        declaration = self.declarations.get(function_name)
        if declaration is None:
            raise ConcreteExecutionError(f"unknown source function {function_name}")
        environment = self._bind_decl_arguments(declaration, arguments)
        try:
            value = self._execute_declaration(declaration, environment, depth=0)
            return ConcreteExecutionResult(
                value,
                tuple(self._transitions),
                tuple(self._effects),
                "returned",
            )
        except _PropagatedFailure as failure:
            return ConcreteExecutionResult(
                None,
                tuple(self._transitions),
                tuple(self._effects),
                "propagated-failure",
                failure.error,
            )

    def _invoke_named(
        self,
        name: str,
        arguments: tuple[object, ...],
        *,
        depth: int,
    ) -> object:
        if name in self.relations:
            return self._invoke_transition(name, arguments, depth=depth)
        if name in self.effect_handlers:
            return self._invoke_effect(name, arguments)
        declaration = self.declarations.get(name)
        if declaration is not None:
            environment = self._bind_decl_arguments(declaration, arguments)
            return self._execute_declaration(declaration, environment, depth=depth + 1)
        return super()._invoke_named(name, arguments, depth=depth)

    def _bind_decl_arguments(
        self,
        declaration: FunctionDecl,
        arguments: Mapping[str, object] | Sequence[object],
    ) -> dict[str, object]:
        if isinstance(arguments, Mapping):
            missing = [item.name for item in declaration.params if item.name not in arguments]
            if missing:
                raise ConcreteExecutionError(
                    f"missing arguments for {declaration.name}: {', '.join(missing)}"
                )
            return {item.name: arguments[item.name] for item in declaration.params}
        values = tuple(arguments)
        if len(values) != len(declaration.params):
            raise ConcreteExecutionError(
                f"{declaration.name} expects {len(declaration.params)} arguments, got {len(values)}"
            )
        return {
            parameter.name: value
            for parameter, value in zip(declaration.params, values, strict=True)
        }

    def _execute_declaration(
        self,
        declaration: FunctionDecl,
        environment: dict[str, object],
        *,
        depth: int,
    ) -> object:
        if depth > self.max_call_depth:
            raise ConcreteExecutionError("source call depth limit exceeded")
        block = self.source_blocks.get(declaration.name)
        if block is not None:
            return self._execute_source_block(block, environment, depth=depth)
        if declaration.expression is not None:
            return self._eval_expr(declaration.expression, environment, depth=depth)
        for clause in declaration.guards:
            if clause.condition is None:
                return self._eval_expr(clause.value, environment, depth=depth)
            condition = self._eval_expr(clause.condition, environment, depth=depth)
            if not isinstance(condition, bool):
                raise ConcreteExecutionError(
                    f"guard at line {clause.line} is not Boolean: {condition!r}"
                )
            if condition:
                return self._eval_expr(clause.value, environment, depth=depth)
        raise ConcreteExecutionError(f"function {declaration.name} has no matching guard")

    def _execute_source_block(
        self,
        block: FunctionBlockLowering,
        environment: dict[str, object],
        *,
        depth: int,
    ) -> object:
        for binding in block.bindings:
            if binding.kind == "conditional":
                environment[binding.name] = self._evaluate_conditional(
                    binding.source,
                    binding.line,
                    environment,
                    depth=depth,
                )
            else:
                environment[binding.name] = self._eval_expr(
                    parse_expr(binding.source),
                    environment,
                    depth=depth,
                )
        return self._eval_expr(parse_expr(block.final_source), environment, depth=depth)

    def _evaluate_conditional(
        self,
        source: str,
        line: int,
        environment: Mapping[str, object],
        *,
        depth: int,
    ) -> object:
        for offset, original in enumerate(source.splitlines()):
            condition_text, separator, value_text = original.partition("=>")
            if not separator or not value_text.strip():
                raise ConcreteExecutionError(
                    f"invalid conditional binding at line {line + offset}"
                )
            condition_text = condition_text.strip()
            if condition_text == "_":
                return self._eval_expr(
                    parse_expr(value_text.strip()),
                    environment,
                    depth=depth,
                )
            condition = self._eval_expr(
                parse_expr(condition_text),
                environment,
                depth=depth,
            )
            if not isinstance(condition, bool):
                raise ConcreteExecutionError(
                    f"conditional guard at line {line + offset} is not Boolean"
                )
            if condition:
                return self._eval_expr(
                    parse_expr(value_text.strip()),
                    environment,
                    depth=depth,
                )
        raise ConcreteExecutionError(f"conditional binding at line {line} has no fallback")
