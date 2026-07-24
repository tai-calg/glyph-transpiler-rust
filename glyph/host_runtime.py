from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import inspect
import threading
from typing import Any

from .artifacts import CompilationModel
from .compiler import CallExpr, ExternDecl, FieldExpr, NameExpr
from .execution_ir import render_expr
from .host_invocation_ir import HostInvocationPlan, render_type, split_result_type
from .pure_runtime import (
    ProductValue,
    PureGlyphProgram,
    PureRuntimeError,
    ResultValue,
    VariantValue,
    glyph_to_python,
)


class HostBindingError(PureRuntimeError):
    """Invalid or incomplete Host binding configuration."""


class HostInvocationError(PureRuntimeError):
    """A registered Host binding violated its declared Glyph contract."""


@dataclass(frozen=True)
class HostInvocationTrace:
    invocation_id: str | None
    effect: str
    caller: str
    arguments: tuple[Any, ...]
    result: Any

    @property
    def succeeded(self) -> bool:
        return not isinstance(self.result, ResultValue) or self.result.ok

    def to_python(self) -> dict[str, Any]:
        return {
            "invocation_id": self.invocation_id,
            "effect": self.effect,
            "caller": self.caller,
            "arguments": [glyph_to_python(item) for item in self.arguments],
            "result": glyph_to_python(self.result),
            "succeeded": self.succeeded,
        }


@dataclass(frozen=True)
class MachineInvocationResult:
    machine: str
    source_state: str
    target_state: str
    outcome: str
    failure_type: str | None
    value: Any
    invocations: tuple[HostInvocationTrace, ...]

    @property
    def invocation_ids(self) -> tuple[str, ...]:
        return tuple(
            item.invocation_id
            for item in self.invocations
            if item.invocation_id is not None
        )

    def to_python(self) -> dict[str, Any]:
        return {
            "machine": self.machine,
            "source_state": self.source_state,
            "target_state": self.target_state,
            "outcome": self.outcome,
            "failure_type": self.failure_type,
            "value": glyph_to_python(self.value),
            "invocations": [item.to_python() for item in self.invocations],
        }


class HostBindingRegistry:
    """Explicit mapping from Glyph effect declarations to Host callables."""

    def __init__(self, model: CompilationModel):
        self.model = model
        self.externs = {
            declaration.name: declaration
            for declaration in model.program.declarations
            if isinstance(declaration, ExternDecl)
        }
        self._bindings: dict[str, Callable[..., Any]] = {}

    @classmethod
    def from_mapping(
        cls,
        model: CompilationModel,
        bindings: Mapping[str, Callable[..., Any]],
    ) -> "HostBindingRegistry":
        registry = cls(model)
        for name, handler in bindings.items():
            registry.bind(name, handler)
        return registry

    def bind(
        self,
        effect: str,
        handler: Callable[..., Any],
        *,
        replace: bool = False,
    ) -> None:
        declaration = self.externs.get(effect)
        if declaration is None:
            raise HostBindingError(f"unknown Glyph effect boundary '{effect}'")
        if effect in self._bindings and not replace:
            raise HostBindingError(f"Host binding for '{effect}' is already registered")
        if not callable(handler):
            raise HostBindingError(f"Host binding for '{effect}' must be callable")
        self._validate_callable_arity(declaration, handler)
        self._bindings[effect] = handler

    def validate_required(self, plan: HostInvocationPlan | None = None) -> None:
        required = (
            {site.effect for site in plan.sites}
            if plan is not None
            else set(self.externs)
        )
        missing = sorted(required - set(self._bindings))
        if missing:
            raise HostBindingError(
                "missing Host binding(s): " + ", ".join(missing)
            )

    def invoke(
        self,
        program: "HostGlyphProgram",
        declaration: ExternDecl,
        arguments: Sequence[Any],
    ) -> Any:
        handler = self._bindings.get(declaration.name)
        if handler is None:
            raise HostBindingError(
                f"effect boundary '{declaration.name}' has no registered Host binding"
            )
        if len(arguments) != len(declaration.params):
            raise HostInvocationError(
                f"effect '{declaration.name}' expects {len(declaration.params)} argument(s), "
                f"received {len(arguments)}"
            )
        coerced = tuple(
            program._coerce(value, parameter.ty)
            for parameter, value in zip(declaration.params, arguments, strict=True)
        )
        try:
            returned = handler(*coerced)
        except Exception as exc:
            raise HostInvocationError(
                f"Host binding '{declaration.name}' raised {type(exc).__name__}; "
                "Python exceptions are not converted into Glyph failure values"
            ) from exc

        _, failure_type = split_result_type(declaration.return_type, {
            name: alias.target for name, alias in program.aliases.items()
        })
        if failure_type is not None and not isinstance(returned, ResultValue):
            raise HostInvocationError(
                f"Host binding '{declaration.name}' must return ResultValue for "
                f"declared type {render_type(declaration.return_type)}"
            )
        if failure_type is None and isinstance(returned, ResultValue):
            raise HostInvocationError(
                f"Host binding '{declaration.name}' returned ResultValue but its "
                "Glyph declaration is not a Result"
            )
        try:
            return program._coerce(returned, declaration.return_type)
        except PureRuntimeError as exc:
            raise HostInvocationError(
                f"Host binding '{declaration.name}' returned a value outside its "
                f"declared type {render_type(declaration.return_type)}: {exc}"
            ) from exc

    @staticmethod
    def _validate_callable_arity(
        declaration: ExternDecl,
        handler: Callable[..., Any],
    ) -> None:
        try:
            signature = inspect.signature(handler)
        except (TypeError, ValueError) as exc:
            raise HostBindingError(
                f"cannot inspect Host binding for '{declaration.name}'"
            ) from exc
        parameters = list(signature.parameters.values())
        if any(item.kind == inspect.Parameter.VAR_POSITIONAL for item in parameters):
            raise HostBindingError(
                f"Host binding '{declaration.name}' may not use variadic positional arguments"
            )
        positional = [
            item
            for item in parameters
            if item.kind
            in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
        ]
        required_keyword_only = [
            item.name
            for item in parameters
            if item.kind == inspect.Parameter.KEYWORD_ONLY
            and item.default is inspect.Parameter.empty
        ]
        if required_keyword_only:
            raise HostBindingError(
                f"Host binding '{declaration.name}' has required keyword-only arguments: "
                + ", ".join(required_keyword_only)
            )
        if len(positional) != len(declaration.params):
            raise HostBindingError(
                f"Host binding '{declaration.name}' must accept exactly "
                f"{len(declaration.params)} positional argument(s); accepts {len(positional)}"
            )


class HostGlyphProgram(PureGlyphProgram):
    """Execute validated Glyph functions with explicitly registered effect bindings."""

    def __init__(
        self,
        model: CompilationModel,
        *,
        bindings: Mapping[str, Callable[..., Any]] | HostBindingRegistry | None = None,
        max_call_depth: int = 256,
    ):
        super().__init__(model, max_call_depth=max_call_depth)
        self.host_plan = HostInvocationPlan.from_model(model)
        self.bindings = (
            bindings
            if isinstance(bindings, HostBindingRegistry)
            else HostBindingRegistry.from_mapping(model, bindings or {})
        )
        self._trace_local = threading.local()
        self._last_invocations: tuple[HostInvocationTrace, ...] = ()

    @property
    def last_invocations(self) -> tuple[HostInvocationTrace, ...]:
        return self._last_invocations

    def bind(
        self,
        effect: str,
        handler: Callable[..., Any],
        *,
        replace: bool = False,
    ) -> None:
        self.bindings.bind(effect, handler, replace=replace)

    def invoke(self, function: str, arguments: Mapping[str, Any]) -> Any:
        return self._run_traced(lambda: super(HostGlyphProgram, self).invoke(function, arguments))

    def invoke_machine(
        self,
        machine_name: str,
        arguments: Mapping[str, Any],
    ) -> MachineInvocationResult:
        machine = next(
            (item for item in self.model.machines if item.name == machine_name),
            None,
        )
        if machine is None:
            raise HostInvocationError(f"unknown Glyph machine '{machine_name}'")
        expected = [parameter.name for parameter in machine.params]
        missing = [name for name in expected if name not in arguments]
        extra = sorted(set(arguments) - set(expected))
        if missing or extra:
            details = []
            if missing:
                details.append("missing: " + ", ".join(missing))
            if extra:
                details.append("unknown: " + ", ".join(extra))
            raise HostInvocationError(
                f"arguments for machine '{machine_name}' do not match ({'; '.join(details)})"
            )

        def execute():
            environment = {
                parameter.name: self._coerce(arguments[parameter.name], parameter.ty)
                for parameter in machine.params
            }
            source_value = environment[machine.state_param.name]
            source_state = self._machine_selector(machine, source_value)
            value = self._evaluate(
                machine.next_expr,
                environment,
                (f"machine:{machine.name}",),
                0,
            )
            failure_type = None
            if isinstance(value, ResultValue):
                next_decl = self._machine_next_declaration(machine)
                _, error_type = split_result_type(
                    next_decl.return_type,
                    {name: alias.target for name, alias in self.aliases.items()},
                )
                if not value.ok:
                    failure_type = None if error_type is None else render_type(error_type)
                    return (
                        source_state,
                        machine.failure,
                        "failure",
                        failure_type,
                        value,
                    )
                state_value = value.value
            else:
                state_value = value

            state_value = self._coerce(state_value, machine.state_param.ty)
            target_state = self._machine_selector(machine, state_value)
            outcome = (
                "failure"
                if target_state == machine.failure
                else "success"
                if target_state == machine.success
                else "normal"
            )
            return source_state, target_state, outcome, failure_type, state_value

        payload = self._run_traced(execute)
        source_state, target_state, outcome, failure_type, value = payload
        return MachineInvocationResult(
            machine=machine.name,
            source_state=source_state,
            target_state=target_state,
            outcome=outcome,
            failure_type=failure_type,
            value=value,
            invocations=self.last_invocations,
        )

    def _call_expression(
        self,
        expression: CallExpr,
        environment: Mapping[str, Any],
        call_stack: tuple[str, ...],
        depth: int,
    ) -> Any:
        if isinstance(expression.callee, NameExpr):
            declaration = self.externs.get(expression.callee.name)
            if declaration is not None:
                arguments = [
                    self._evaluate(argument, environment, call_stack, depth)
                    for argument in expression.args
                ]
                caller = call_stack[-1] if call_stack else "<root>"
                site = self.host_plan.resolve_site(caller, render_expr(expression))
                result = self.bindings.invoke(self, declaration, arguments)
                self._active_trace().append(
                    HostInvocationTrace(
                        invocation_id=None if site is None else site.id,
                        effect=declaration.name,
                        caller=caller,
                        arguments=tuple(arguments),
                        result=result,
                    )
                )
                return result
        return super()._call_expression(expression, environment, call_stack, depth)

    def _run_traced(self, operation):
        previous = getattr(self._trace_local, "current", None)
        current: list[HostInvocationTrace] = []
        self._trace_local.current = current
        try:
            return operation()
        finally:
            self._last_invocations = tuple(current)
            if previous is None:
                del self._trace_local.current
            else:
                self._trace_local.current = previous

    def _active_trace(self) -> list[HostInvocationTrace]:
        current = getattr(self._trace_local, "current", None)
        if current is None:
            current = []
            self._trace_local.current = current
        return current

    def _machine_selector(self, machine, state_value: Any) -> str:
        if not isinstance(machine.selector, FieldExpr):
            raise HostInvocationError(
                f"machine '{machine.name}' selector is not a field expression"
            )
        if not isinstance(state_value, ProductValue):
            raise HostInvocationError(
                f"machine '{machine.name}' state did not evaluate to a product"
            )
        selected = state_value[machine.selector.field]
        if not isinstance(selected, VariantValue):
            raise HostInvocationError(
                f"machine '{machine.name}' selector field did not evaluate to a sum variant"
            )
        return selected.variant

    def _machine_next_declaration(self, machine):
        expression = machine.next_expr
        if not isinstance(expression, CallExpr) or not isinstance(expression.callee, NameExpr):
            raise HostInvocationError(
                f"machine '{machine.name}' next expression is not a named function call"
            )
        declaration = self.functions.get(expression.callee.name)
        if declaration is None:
            raise HostInvocationError(
                f"machine '{machine.name}' next function '{expression.callee.name}' is missing"
            )
        return declaration
