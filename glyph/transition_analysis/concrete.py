from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from ..artifacts import CompilationModel
from ..compiler import (
    BinaryExpr,
    BoolExpr,
    CallExpr,
    Expr,
    FieldExpr,
    NameExpr,
    NumberExpr,
    ProductDecl,
    SumDecl,
    TryExpr,
    UnaryExpr,
)
from .lowering import lower_compilation_model
from .machine_relation import MachineRelation, relation_by_transition_function
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


@dataclass(frozen=True)
class ConstructorValue:
    type_name: str
    fields: tuple[tuple[str, object], ...]

    def field(self, name: str) -> object:
        for field_name, value in self.fields:
            if field_name == name:
                return value
        raise ConcreteExecutionError(f"constructor {self.type_name} has no field {name}")


@dataclass(frozen=True)
class VariantValue:
    name: str
    arguments: tuple[object, ...] = ()


@dataclass(frozen=True)
class ResultValue:
    success: bool
    value: object


@dataclass(frozen=True)
class TransitionEvent:
    machine: str
    function: str
    edge_id: str
    arguments: tuple[object, ...]
    result: object | None
    completion: str


@dataclass(frozen=True)
class EffectEvent:
    operation: str
    arguments: tuple[object, ...]
    result: object


@dataclass(frozen=True)
class ConcreteExecutionResult:
    return_value: object | None
    transition_trace: tuple[TransitionEvent, ...]
    effect_trace: tuple[EffectEvent, ...]
    completion: str
    error: object | None = None


class ConcreteExecutionError(RuntimeError):
    pass


class _PropagatedFailure(Exception):
    def __init__(self, error: object) -> None:
        super().__init__(repr(error))
        self.error = error


EffectHandler = Callable[[tuple[object, ...]], object]


class ConcreteInterpreter:
    """Execute TEIR without reusing the legacy System Action evaluator.

    Inputs are concrete Python values represented by ``ConstructorValue``,
    ``VariantValue``, booleans and numbers.  The interpreter records selected
    Machine edges and Effect calls, providing the independent oracle required by
    RTAI's later abstract transfer implementation.
    """

    def __init__(
        self,
        model: CompilationModel,
        *,
        effect_handlers: Mapping[str, EffectHandler] = {},
        max_steps: int = 10_000,
        max_call_depth: int = 128,
    ) -> None:
        self.model = model
        self.functions = lower_compilation_model(model)
        self.relations = relation_by_transition_function(model)
        self.effect_handlers = dict(effect_handlers)
        self.max_steps = max_steps
        self.max_call_depth = max_call_depth
        self.products = {
            declaration.name: declaration
            for declaration in model.program.declarations
            if isinstance(declaration, ProductDecl)
        }
        self.variants = {
            variant.name: variant
            for declaration in model.program.declarations
            if isinstance(declaration, SumDecl)
            for variant in declaration.variants
        }
        self._steps = 0
        self._transitions: list[TransitionEvent] = []
        self._effects: list[EffectEvent] = []

    def run(
        self,
        function_name: str,
        arguments: Mapping[str, object] | Sequence[object],
    ) -> ConcreteExecutionResult:
        self._steps = 0
        self._transitions = []
        self._effects = []
        function = self.functions.get(function_name)
        if function is None:
            raise ConcreteExecutionError(f"unknown TEIR function {function_name}")
        values = self._bind_arguments(function, arguments)
        try:
            returned = self._execute_function(function, values, depth=0)
            return ConcreteExecutionResult(
                returned,
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

    def _bind_arguments(
        self,
        function: Function,
        arguments: Mapping[str, object] | Sequence[object],
    ) -> dict[str, object]:
        if isinstance(arguments, Mapping):
            missing = [item.name for item in function.parameters if item.name not in arguments]
            if missing:
                raise ConcreteExecutionError(
                    f"missing arguments for {function.function_id}: {', '.join(missing)}"
                )
            return {item.name: arguments[item.name] for item in function.parameters}
        values = tuple(arguments)
        if len(values) != len(function.parameters):
            raise ConcreteExecutionError(
                f"{function.function_id} expects {len(function.parameters)} arguments, got {len(values)}"
            )
        return {
            parameter.name: value
            for parameter, value in zip(function.parameters, values, strict=True)
        }

    def _execute_function(
        self,
        function: Function,
        environment: dict[str, object],
        *,
        depth: int,
    ) -> object | None:
        if depth > self.max_call_depth:
            raise ConcreteExecutionError("TEIR call depth limit exceeded")
        blocks = function.block_map
        block_id = function.entry_block
        while True:
            self._tick()
            block = blocks.get(block_id)
            if block is None:
                raise ConcreteExecutionError(
                    f"function {function.function_id} references unknown block {block_id}"
                )
            for instruction in block.instructions:
                self._tick()
                if isinstance(instruction, Assign):
                    environment[instruction.target] = self._eval_expr(
                        instruction.expression,
                        environment,
                        depth=depth,
                    )
                elif isinstance(instruction, TransitionCall):
                    arguments = tuple(
                        self._eval_expr(argument, environment, depth=depth)
                        for argument in instruction.arguments
                    )
                    value = self._invoke_transition(
                        instruction.function,
                        arguments,
                        depth=depth,
                    )
                    environment[instruction.target] = self._unwrap_try_result(
                        value,
                        instruction.propagate_failure,
                    )
                elif isinstance(instruction, EffectCall):
                    arguments = tuple(
                        self._eval_expr(argument, environment, depth=depth)
                        for argument in instruction.arguments
                    )
                    value = self._invoke_effect(instruction.operation, arguments)
                    value = self._unwrap_try_result(value, instruction.propagate_failure)
                    if instruction.target is not None:
                        environment[instruction.target] = value
                else:  # pragma: no cover - closed TEIR instruction union
                    raise ConcreteExecutionError(f"unsupported TEIR instruction {instruction!r}")

            terminator = block.terminator
            if isinstance(terminator, Jump):
                block_id = terminator.target
                continue
            if isinstance(terminator, Branch):
                condition = self._eval_expr(terminator.condition, environment, depth=depth)
                if not isinstance(condition, bool):
                    raise ConcreteExecutionError(
                        f"branch condition at line {terminator.line} is not Boolean: {condition!r}"
                    )
                block_id = terminator.true_block if condition else terminator.false_block
                continue
            if isinstance(terminator, Return):
                return (
                    None
                    if terminator.value is None
                    else self._eval_expr(terminator.value, environment, depth=depth)
                )
            if isinstance(terminator, PropagateFailure):
                raise _PropagatedFailure(
                    self._eval_expr(terminator.error, environment, depth=depth)
                )
            raise ConcreteExecutionError(f"unsupported TEIR terminator {terminator!r}")

    def _eval_expr(
        self,
        expression: Expr,
        environment: Mapping[str, object],
        *,
        depth: int,
    ) -> object:
        self._tick()
        if isinstance(expression, BoolExpr):
            return expression.value
        if isinstance(expression, NumberExpr):
            return float(expression.value) if "." in expression.value else int(expression.value)
        if isinstance(expression, NameExpr):
            if expression.name in environment:
                return environment[expression.name]
            if expression.name in self.variants:
                return VariantValue(expression.name)
            raise ConcreteExecutionError(f"unbound name {expression.name}")
        if isinstance(expression, FieldExpr):
            base = self._eval_expr(expression.base, environment, depth=depth)
            if isinstance(base, ConstructorValue):
                return base.field(expression.field)
            raise ConcreteExecutionError(
                f"field access {expression.field} requires constructor, got {base!r}"
            )
        if isinstance(expression, TryExpr):
            value = self._eval_expr(expression.expr, environment, depth=depth)
            return self._unwrap_try_result(value, True)
        if isinstance(expression, UnaryExpr):
            value = self._eval_expr(expression.expr, environment, depth=depth)
            if expression.op == "!":
                if not isinstance(value, bool):
                    raise ConcreteExecutionError(f"! requires Boolean, got {value!r}")
                return not value
            if expression.op == "-":
                return -value  # type: ignore[operator]
            raise ConcreteExecutionError(f"unsupported unary operator {expression.op}")
        if isinstance(expression, BinaryExpr):
            return self._eval_binary(expression, environment, depth=depth)
        if isinstance(expression, CallExpr):
            if not isinstance(expression.callee, NameExpr):
                raise ConcreteExecutionError("concrete TEIR supports named calls only")
            name = expression.callee.name
            arguments = tuple(
                self._eval_expr(argument, environment, depth=depth)
                for argument in expression.args
            )
            return self._invoke_named(name, arguments, depth=depth)
        raise ConcreteExecutionError(f"unsupported expression {expression!r}")

    def _eval_binary(
        self,
        expression: BinaryExpr,
        environment: Mapping[str, object],
        *,
        depth: int,
    ) -> object:
        left = self._eval_expr(expression.left, environment, depth=depth)
        if expression.op == "&":
            if not isinstance(left, bool):
                raise ConcreteExecutionError("& requires Boolean operands")
            return left and bool(self._eval_expr(expression.right, environment, depth=depth))
        if expression.op == "|":
            if not isinstance(left, bool):
                raise ConcreteExecutionError("| requires Boolean operands")
            return left or bool(self._eval_expr(expression.right, environment, depth=depth))
        right = self._eval_expr(expression.right, environment, depth=depth)
        operations: dict[str, Callable[[object, object], object]] = {
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "+": lambda a, b: a + b,  # type: ignore[operator]
            "-": lambda a, b: a - b,  # type: ignore[operator]
            "*": lambda a, b: a * b,  # type: ignore[operator]
            "/": lambda a, b: a / b,  # type: ignore[operator]
            "<": lambda a, b: a < b,  # type: ignore[operator]
            "<=": lambda a, b: a <= b,  # type: ignore[operator]
            ">": lambda a, b: a > b,  # type: ignore[operator]
            ">=": lambda a, b: a >= b,  # type: ignore[operator]
        }
        operation = operations.get(expression.op)
        if operation is None:
            raise ConcreteExecutionError(f"unsupported binary operator {expression.op}")
        return operation(left, right)

    def _invoke_named(
        self,
        name: str,
        arguments: tuple[object, ...],
        *,
        depth: int,
    ) -> object:
        product = self.products.get(name)
        if product is not None:
            if len(arguments) != len(product.fields):
                raise ConcreteExecutionError(
                    f"constructor {name} expects {len(product.fields)} values"
                )
            return ConstructorValue(
                name,
                tuple(
                    (field.name, value)
                    for field, value in zip(product.fields, arguments, strict=True)
                ),
            )
        if name in self.variants:
            return VariantValue(name, arguments)
        if name == "Ok":
            if len(arguments) != 1:
                raise ConcreteExecutionError("Ok expects one argument")
            return ResultValue(True, arguments[0])
        if name == "Err":
            if len(arguments) != 1:
                raise ConcreteExecutionError("Err expects one argument")
            return ResultValue(False, arguments[0])
        if name in self.relations:
            return self._invoke_transition(name, arguments, depth=depth)
        if name in self.effect_handlers:
            return self._invoke_effect(name, arguments)
        function = self.functions.get(name)
        if function is None:
            raise ConcreteExecutionError(f"unknown call target {name}")
        values = self._bind_arguments(function, arguments)
        return self._execute_function(function, values, depth=depth + 1)

    def _invoke_transition(
        self,
        function_name: str,
        arguments: tuple[object, ...],
        *,
        depth: int,
    ) -> object:
        relation = self.relations.get(function_name)
        if relation is None:
            raise ConcreteExecutionError(f"no Machine relation for {function_name}")
        if len(arguments) != len(relation.formals):
            raise ConcreteExecutionError(
                f"transition {function_name} expects {len(relation.formals)} arguments"
            )
        environment = dict(zip(relation.formals, arguments, strict=True))
        for edge in relation.edges:
            guard = self._eval_expr(edge.effective_guard, environment, depth=depth + 1)
            if not isinstance(guard, bool):
                raise ConcreteExecutionError(
                    f"Machine guard {edge.edge_id} is not Boolean: {guard!r}"
                )
            if not guard:
                continue
            try:
                result = self._eval_expr(
                    edge.result_expression,
                    environment,
                    depth=depth + 1,
                )
            except _PropagatedFailure as failure:
                self._transitions.append(
                    TransitionEvent(
                        relation.machine_id,
                        function_name,
                        edge.edge_id,
                        arguments,
                        None,
                        "propagated-failure",
                    )
                )
                raise failure
            self._transitions.append(
                TransitionEvent(
                    relation.machine_id,
                    function_name,
                    edge.edge_id,
                    arguments,
                    result,
                    "returned",
                )
            )
            return result
        raise ConcreteExecutionError(
            f"Machine relation {relation.machine_id} has no matching edge"
        )

    def _invoke_effect(
        self,
        operation: str,
        arguments: tuple[object, ...],
    ) -> object:
        handler = self.effect_handlers.get(operation)
        if handler is None:
            raise ConcreteExecutionError(
                f"Effect {operation} requires an explicit concrete handler"
            )
        result = handler(arguments)
        self._effects.append(EffectEvent(operation, arguments, result))
        return result

    @staticmethod
    def _unwrap_try_result(value: object, propagate: bool) -> object:
        if not propagate:
            return value
        if not isinstance(value, ResultValue):
            raise ConcreteExecutionError(f"? requires Result value, got {value!r}")
        if not value.success:
            raise _PropagatedFailure(value.value)
        return value.value

    def _tick(self) -> None:
        self._steps += 1
        if self._steps > self.max_steps:
            raise ConcreteExecutionError("TEIR step limit exceeded")
