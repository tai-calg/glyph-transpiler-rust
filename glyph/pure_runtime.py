from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import threading
from typing import Any

from .artifacts import CompilationModel
from .compiled_live_image import CompiledLiveImage
from .compiler import (
    AliasDecl,
    BinaryExpr,
    BoolExpr,
    CallExpr,
    ExternDecl,
    FieldExpr,
    FunctionDecl,
    GlyphError,
    NameExpr,
    NumberExpr,
    ProductDecl,
    SumDecl,
    TryExpr,
    TypeRef,
    UnaryExpr,
    Variant,
)
from .incremental import IncrementalCompiler


class PureRuntimeError(RuntimeError):
    """Raised when validated Glyph cannot be executed by the pure runtime subset."""


@dataclass(frozen=True)
class ProductValue(Mapping[str, Any]):
    """Immutable runtime representation of one Glyph product value."""

    type_name: str
    fields: tuple[tuple[str, Any], ...]

    def __getitem__(self, key: str) -> Any:
        for name, value in self.fields:
            if name == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (name for name, _ in self.fields)

    def __len__(self) -> int:
        return len(self.fields)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc

    def to_dict(self) -> dict[str, Any]:
        return {name: glyph_to_python(value) for name, value in self.fields}


@dataclass(frozen=True)
class VariantValue:
    """Immutable runtime representation of one Glyph sum variant."""

    enum_name: str
    variant: str
    values: tuple[Any, ...] = ()
    fields: tuple[tuple[str, Any], ...] = ()

    def field(self, name: str) -> Any:
        for field_name, value in self.fields:
            if field_name == name:
                return value
        raise KeyError(name)


@dataclass(frozen=True)
class ResultValue:
    ok: bool
    value: Any


@dataclass(frozen=True)
class OptionValue:
    present: bool
    value: Any = None


@dataclass(frozen=True)
class InvocationResult:
    world_version: int
    function: str
    value: Any

    def to_python(self) -> Any:
        return glyph_to_python(self.value)


def glyph_to_python(value: Any) -> Any:
    """Convert runtime values into JSON- and UI-friendly Python values."""

    if isinstance(value, ProductValue):
        return value.to_dict()
    if isinstance(value, VariantValue):
        payload: dict[str, Any] = {
            "type": value.enum_name,
            "variant": value.variant,
        }
        if value.values:
            payload["values"] = [glyph_to_python(item) for item in value.values]
        if value.fields:
            payload["fields"] = {
                name: glyph_to_python(item) for name, item in value.fields
            }
        return payload
    if isinstance(value, ResultValue):
        return {
            "status": "ok" if value.ok else "error",
            "value": glyph_to_python(value.value),
        }
    if isinstance(value, OptionValue):
        return None if not value.present else glyph_to_python(value.value)
    if isinstance(value, Mapping):
        return {str(key): glyph_to_python(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [glyph_to_python(item) for item in value]
    if isinstance(value, list):
        return [glyph_to_python(item) for item in value]
    return value


class _PropagateResult(Exception):
    def __init__(self, result: ResultValue):
        super().__init__("propagate Glyph Result")
        self.result = result


_FLOAT_TYPES = {"F", "D", "f32", "f64"}
_BOOL_TYPES = {"B", "bool"}
_STRING_TYPES = {"S", "String", "str"}
_INTEGER_RANGES: dict[str, tuple[int, int]] = {
    "u8": (0, 2**8 - 1),
    "u16": (0, 2**16 - 1),
    "u32": (0, 2**32 - 1),
    "u64": (0, 2**64 - 1),
    "usize": (0, 2**64 - 1),
    "i8": (-(2**7), 2**7 - 1),
    "i16": (-(2**15), 2**15 - 1),
    "i32": (-(2**31), 2**31 - 1),
    "i64": (-(2**63), 2**63 - 1),
    "isize": (-(2**63), 2**63 - 1),
    "U": (0, 2**16 - 1),
    "I": (-(2**31), 2**31 - 1),
}


class PureGlyphProgram:
    """Execute the side-effect-free subset of one validated CompilationModel.

    The runtime interprets the compiler AST directly. It never reparses source and it
    never duplicates application formulas in a Host adapter. Effect boundaries,
    opaque Rust implementations, dynamic function values, and arbitrary native code
    are rejected rather than guessed.
    """

    def __init__(self, model: CompilationModel, *, max_call_depth: int = 256):
        if max_call_depth < 1:
            raise ValueError("max_call_depth must be positive")
        self.model = model
        self.max_call_depth = max_call_depth
        self.products = {
            item.name: item
            for item in model.program.declarations
            if isinstance(item, ProductDecl)
        }
        self.sums = {
            item.name: item
            for item in model.program.declarations
            if isinstance(item, SumDecl)
        }
        self.aliases = {
            item.name: item
            for item in model.program.declarations
            if isinstance(item, AliasDecl)
        }
        self.functions = {
            item.name: item
            for item in model.program.declarations
            if isinstance(item, FunctionDecl)
        }
        self.externs = {
            item.name: item
            for item in model.program.declarations
            if isinstance(item, ExternDecl)
        }
        self.variants: dict[str, tuple[SumDecl, Variant]] = {
            variant.name: (sum_type, variant)
            for sum_type in self.sums.values()
            for variant in sum_type.variants
        }

    def invoke(self, function: str, arguments: Mapping[str, Any]) -> Any:
        declaration = self.functions.get(function)
        if declaration is None:
            if function in self.externs:
                raise PureRuntimeError(
                    f"'{function}' is a Glyph effect boundary and requires a Host"
                )
            raise PureRuntimeError(f"unknown pure Glyph function '{function}'")

        expected = [parameter.name for parameter in declaration.params]
        missing = [name for name in expected if name not in arguments]
        extra = sorted(set(arguments) - set(expected))
        if missing or extra:
            details = []
            if missing:
                details.append("missing: " + ", ".join(missing))
            if extra:
                details.append("unknown: " + ", ".join(extra))
            raise PureRuntimeError(
                f"arguments for '{function}' do not match its signature ({'; '.join(details)})"
            )

        values = [arguments[name] for name in expected]
        return self._call_function(declaration, values, (), 0)

    def _call_function(
        self,
        declaration: FunctionDecl,
        arguments: Sequence[Any],
        call_stack: tuple[str, ...],
        depth: int,
    ) -> Any:
        if depth >= self.max_call_depth:
            chain = " -> ".join((*call_stack, declaration.name))
            raise PureRuntimeError(
                f"pure Glyph call depth exceeded {self.max_call_depth}: {chain}"
            )
        if len(arguments) != len(declaration.params):
            raise PureRuntimeError(
                f"'{declaration.name}' expects {len(declaration.params)} argument(s), "
                f"received {len(arguments)}"
            )

        environment = {
            parameter.name: self._coerce(value, parameter.ty)
            for parameter, value in zip(declaration.params, arguments)
        }
        next_stack = (*call_stack, declaration.name)
        try:
            if declaration.expression is not None:
                value = self._evaluate(
                    declaration.expression,
                    environment,
                    next_stack,
                    depth + 1,
                )
            else:
                value = self._evaluate_guards(
                    declaration,
                    environment,
                    next_stack,
                    depth + 1,
                )
        except _PropagateResult as propagated:
            value = propagated.result
        return self._coerce(value, declaration.return_type)

    def _evaluate_guards(
        self,
        declaration: FunctionDecl,
        environment: Mapping[str, Any],
        call_stack: tuple[str, ...],
        depth: int,
    ) -> Any:
        for clause in declaration.guards:
            if clause.condition is None:
                return self._evaluate(clause.value, environment, call_stack, depth)
            condition = self._evaluate(
                clause.condition,
                environment,
                call_stack,
                depth,
            )
            if not isinstance(condition, bool):
                raise PureRuntimeError(
                    f"guard in '{declaration.name}' did not evaluate to bool; "
                    "variant-pattern guards are not in the pure interpreter subset"
                )
            if condition:
                return self._evaluate(clause.value, environment, call_stack, depth)
        raise PureRuntimeError(f"'{declaration.name}' has no matching guard")

    def _evaluate(
        self,
        expression: object,
        environment: Mapping[str, Any],
        call_stack: tuple[str, ...],
        depth: int,
    ) -> Any:
        if isinstance(expression, NameExpr):
            if expression.name in environment:
                return environment[expression.name]
            variant = self.variants.get(expression.name)
            if variant is not None:
                sum_type, declaration = variant
                if declaration.tuple_types or declaration.fields:
                    raise PureRuntimeError(
                        f"variant '{expression.name}' requires constructor arguments"
                    )
                return VariantValue(sum_type.name, declaration.name)
            if expression.name == "None":
                return OptionValue(False)
            if expression.name in self.functions:
                raise PureRuntimeError(
                    "dynamic function values are not executable in PureGlyphProgram"
                )
            raise PureRuntimeError(f"unresolved runtime name '{expression.name}'")

        if isinstance(expression, NumberExpr):
            return float(expression.value) if "." in expression.value else int(expression.value)
        if isinstance(expression, BoolExpr):
            return expression.value
        if isinstance(expression, FieldExpr):
            base = self._evaluate(expression.base, environment, call_stack, depth)
            return self._field(base, expression.field)
        if isinstance(expression, TryExpr):
            result = self._evaluate(expression.expr, environment, call_stack, depth)
            if not isinstance(result, ResultValue):
                raise PureRuntimeError("'?' requires a Glyph Result value")
            if result.ok:
                return result.value
            raise _PropagateResult(result)
        if isinstance(expression, UnaryExpr):
            value = self._evaluate(expression.expr, environment, call_stack, depth)
            if expression.op == "!":
                if not isinstance(value, bool):
                    raise PureRuntimeError("logical '!' requires bool")
                return not value
            if expression.op == "-":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise PureRuntimeError("unary '-' requires a number")
                return -value
            raise PureRuntimeError(f"unsupported unary operator '{expression.op}'")
        if isinstance(expression, BinaryExpr):
            return self._binary(expression, environment, call_stack, depth)
        if isinstance(expression, CallExpr):
            return self._call_expression(expression, environment, call_stack, depth)
        raise PureRuntimeError(
            f"unsupported pure Glyph expression {type(expression).__name__}"
        )

    def _binary(
        self,
        expression: BinaryExpr,
        environment: Mapping[str, Any],
        call_stack: tuple[str, ...],
        depth: int,
    ) -> Any:
        left = self._evaluate(expression.left, environment, call_stack, depth)
        if expression.op == "|":
            if not isinstance(left, bool):
                raise PureRuntimeError("logical '|' requires bool operands")
            return left or self._require_bool(
                self._evaluate(expression.right, environment, call_stack, depth),
                "logical '|' requires bool operands",
            )
        if expression.op == "&":
            if not isinstance(left, bool):
                raise PureRuntimeError("logical '&' requires bool operands")
            return left and self._require_bool(
                self._evaluate(expression.right, environment, call_stack, depth),
                "logical '&' requires bool operands",
            )

        right = self._evaluate(expression.right, environment, call_stack, depth)
        if expression.op in {"=", "=="}:
            return left == right
        if expression.op == "!=":
            return left != right
        if expression.op == "<":
            return left < right
        if expression.op == ">":
            return left > right
        if expression.op == "<=":
            return left <= right
        if expression.op == ">=":
            return left >= right
        if expression.op == "+":
            return left + right
        if expression.op == "-":
            return left - right
        if expression.op == "*":
            return left * right
        if expression.op == "/":
            if isinstance(left, int) and not isinstance(left, bool) and isinstance(
                right, int
            ) and not isinstance(right, bool):
                if right == 0:
                    raise ZeroDivisionError("integer division by zero")
                quotient = abs(left) // abs(right)
                return -quotient if (left < 0) != (right < 0) else quotient
            return left / right
        raise PureRuntimeError(f"unsupported binary operator '{expression.op}'")

    def _call_expression(
        self,
        expression: CallExpr,
        environment: Mapping[str, Any],
        call_stack: tuple[str, ...],
        depth: int,
    ) -> Any:
        if not isinstance(expression.callee, NameExpr):
            raise PureRuntimeError(
                "dynamic call targets are not executable in PureGlyphProgram"
            )
        name = expression.callee.name
        arguments = [
            self._evaluate(argument, environment, call_stack, depth)
            for argument in expression.args
        ]

        product = self.products.get(name)
        if product is not None:
            if len(arguments) != len(product.fields):
                raise PureRuntimeError(
                    f"product '{name}' expects {len(product.fields)} argument(s), "
                    f"received {len(arguments)}"
                )
            return ProductValue(
                name,
                tuple(
                    (field.name, self._coerce(value, field.ty))
                    for field, value in zip(product.fields, arguments)
                ),
            )

        variant = self.variants.get(name)
        if variant is not None:
            sum_type, declaration = variant
            if declaration.fields:
                if len(arguments) != len(declaration.fields):
                    raise PureRuntimeError(
                        f"variant '{name}' expects {len(declaration.fields)} argument(s)"
                    )
                return VariantValue(
                    sum_type.name,
                    name,
                    fields=tuple(
                        (field.name, self._coerce(value, field.ty))
                        for field, value in zip(declaration.fields, arguments)
                    ),
                )
            if len(arguments) != len(declaration.tuple_types):
                raise PureRuntimeError(
                    f"variant '{name}' expects {len(declaration.tuple_types)} argument(s)"
                )
            return VariantValue(
                sum_type.name,
                name,
                values=tuple(
                    self._coerce(value, ty)
                    for value, ty in zip(arguments, declaration.tuple_types)
                ),
            )

        if name == "Ok" or name == "Err":
            if len(arguments) != 1:
                raise PureRuntimeError(f"{name} expects one argument")
            return ResultValue(name == "Ok", arguments[0])
        if name == "Some":
            if len(arguments) != 1:
                raise PureRuntimeError("Some expects one argument")
            return OptionValue(True, arguments[0])
        if name in {"min", "max"}:
            if len(arguments) != 2:
                raise PureRuntimeError(f"{name} expects two arguments")
            return min(arguments) if name == "min" else max(arguments)
        if name == "finite":
            if len(arguments) != 1:
                raise PureRuntimeError("finite expects one argument")
            value = arguments[0]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PureRuntimeError("finite expects a number")
            return math.isfinite(value)

        function = self.functions.get(name)
        if function is not None:
            return self._call_function(function, arguments, call_stack, depth)
        if name in self.externs:
            raise PureRuntimeError(
                f"effect boundary '{name}' cannot run in PureGlyphProgram"
            )
        raise PureRuntimeError(f"unknown Glyph call target '{name}'")

    def _coerce(self, value: Any, type_ref: TypeRef) -> Any:
        resolved = self._resolve_alias(type_ref)
        name = resolved.name

        product = self.products.get(name)
        if product is not None:
            if isinstance(value, ProductValue):
                if value.type_name != name:
                    raise PureRuntimeError(
                        f"expected product '{name}', received '{value.type_name}'"
                    )
                return value
            if not isinstance(value, Mapping):
                raise PureRuntimeError(f"product '{name}' requires a mapping value")
            expected = [field.name for field in product.fields]
            missing = [field for field in expected if field not in value]
            extra = sorted(set(value) - set(expected))
            if missing or extra:
                details = []
                if missing:
                    details.append("missing: " + ", ".join(missing))
                if extra:
                    details.append("unknown: " + ", ".join(extra))
                raise PureRuntimeError(
                    f"product '{name}' fields do not match ({'; '.join(details)})"
                )
            return ProductValue(
                name,
                tuple(
                    (field.name, self._coerce(value[field.name], field.ty))
                    for field in product.fields
                ),
            )

        if name in self.sums:
            if not isinstance(value, VariantValue) or value.enum_name != name:
                raise PureRuntimeError(f"expected a '{name}' variant value")
            return value
        if name in _FLOAT_TYPES:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PureRuntimeError(f"type '{name}' requires a number")
            return float(value)
        if name in _INTEGER_RANGES:
            if isinstance(value, bool) or not isinstance(value, int):
                raise PureRuntimeError(f"type '{name}' requires an integer")
            minimum, maximum = _INTEGER_RANGES[name]
            if not minimum <= value <= maximum:
                raise PureRuntimeError(
                    f"integer {value} is outside {name} range [{minimum}, {maximum}]"
                )
            return value
        if name in _BOOL_TYPES:
            if not isinstance(value, bool):
                raise PureRuntimeError(f"type '{name}' requires bool")
            return value
        if name in _STRING_TYPES:
            if not isinstance(value, str):
                raise PureRuntimeError(f"type '{name}' requires text")
            return value
        if name == "()":
            if value is not None:
                raise PureRuntimeError("unit type requires None")
            return None
        if name == "tuple":
            if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
                raise PureRuntimeError("tuple type requires a sequence")
            if len(value) != len(resolved.args):
                raise PureRuntimeError(
                    f"tuple expects {len(resolved.args)} value(s), received {len(value)}"
                )
            return tuple(
                self._coerce(item, ty) for item, ty in zip(value, resolved.args)
            )
        if name in {"R", "Result"}:
            if len(resolved.args) != 2 or not isinstance(value, ResultValue):
                raise PureRuntimeError("Result<T,E> requires a ResultValue")
            target = resolved.args[0] if value.ok else resolved.args[1]
            return ResultValue(value.ok, self._coerce(value.value, target))
        if name in {"O", "Option"}:
            if len(resolved.args) != 1 or not isinstance(value, OptionValue):
                raise PureRuntimeError("Option<T> requires an OptionValue")
            if not value.present:
                return value
            return OptionValue(True, self._coerce(value.value, resolved.args[0]))
        raise PureRuntimeError(f"unsupported pure runtime type '{name}'")

    def _resolve_alias(self, type_ref: TypeRef) -> TypeRef:
        current = type_ref
        visited: set[str] = set()
        while current.name in self.aliases:
            if current.name in visited:
                raise PureRuntimeError(f"type alias cycle at '{current.name}'")
            visited.add(current.name)
            current = self.aliases[current.name].target
        return current

    @staticmethod
    def _field(value: Any, field: str) -> Any:
        if isinstance(value, ProductValue):
            try:
                return value[field]
            except KeyError as exc:
                raise PureRuntimeError(
                    f"product '{value.type_name}' has no field '{field}'"
                ) from exc
        if isinstance(value, VariantValue) and value.fields:
            try:
                return value.field(field)
            except KeyError as exc:
                raise PureRuntimeError(
                    f"variant '{value.variant}' has no field '{field}'"
                ) from exc
        if isinstance(value, Mapping) and field in value:
            return value[field]
        raise PureRuntimeError(f"value has no field '{field}'")

    @staticmethod
    def _require_bool(value: Any, message: str) -> bool:
        if not isinstance(value, bool):
            raise PureRuntimeError(message)
        return value


class LivePureGlyphRuntime:
    """File-backed pure runtime connected to the transactional Live Image.

    A successful source edit installs a new executable program keyed by the same source
    digest as its LiveWorld. Function-body-only edits hot-swap immediately. Changes that
    require quiescence, migration, or reader acknowledgement obey CompiledLiveImage's
    transaction rules. Failed compilations retain the last executable world.
    """

    def __init__(
        self,
        source_path: str | Path,
        *,
        compiler: IncrementalCompiler | None = None,
    ) -> None:
        self.source_path = Path(source_path).resolve()
        self.compiler = compiler or IncrementalCompiler()
        self.image = CompiledLiveImage()
        self._lock = threading.RLock()
        self._programs: dict[str, PureGlyphProgram] = {}
        self._last_file_digest = ""
        self._last_source = ""
        self._last_error: str | None = None
        self._stop = threading.Event()
        self._watcher: threading.Thread | None = None
        source = self.source_path.read_text(encoding="utf-8")
        self._last_file_digest = self._digest(source)
        self.stage_text(source)

    @staticmethod
    def _digest(source: str) -> str:
        return hashlib.sha256(source.encode("utf-8")).hexdigest()

    @property
    def last_error(self) -> str | None:
        with self._lock:
            return self._last_error

    @property
    def source_text(self) -> str:
        with self._lock:
            return self._last_source

    def stage_text(self, source: str) -> dict[str, object]:
        result = self.compiler.compile_text(
            source,
            source_name=str(self.source_path),
            source_href=str(self.source_path),
        )
        snapshot = result.snapshot
        design = json.loads(snapshot.semantic_json)
        program = PureGlyphProgram(snapshot.model)
        with self._lock:
            self._programs[snapshot.digest] = program
            self._last_source = source
        state = self.image.stage_compilation(
            snapshot.model,
            design,
            source_digest=snapshot.digest,
            generated_code=snapshot.artifacts.logic,
        )
        with self._lock:
            self._last_error = None
        return state

    def try_stage_text(self, source: str) -> bool:
        try:
            self.stage_text(source)
        except (GlyphError, OSError, PureRuntimeError, ValueError) as exc:
            with self._lock:
                self._last_source = source
                self._last_error = str(exc)
            return False
        return True

    def refresh(self, *, force: bool = False) -> bool:
        source = self.source_path.read_text(encoding="utf-8")
        digest = self._digest(source)
        with self._lock:
            if not force and digest == self._last_file_digest:
                return False
            self._last_file_digest = digest
        return self.try_stage_text(source)

    def invoke(
        self,
        function: str,
        arguments: Mapping[str, Any],
        *,
        refresh: bool = True,
    ) -> InvocationResult:
        if refresh:
            self.refresh()
        with self.image.acquire() as world:
            with self._lock:
                program = self._programs.get(world.source_digest)
            if program is None:
                raise PureRuntimeError(
                    f"no executable program is registered for World {world.version}"
                )
            value = program.invoke(function, arguments)
            return InvocationResult(world.version, function, value)

    def commit_pending(
        self,
        *,
        migration_plan: str | None = None,
        reader_acknowledged: bool = False,
    ) -> dict[str, object]:
        return self.image.commit_pending(
            migration_plan=migration_plan,
            reader_acknowledged=reader_acknowledged,
        )

    def discard_pending(self) -> dict[str, object]:
        return self.image.discard_pending()

    def state_dict(self) -> dict[str, object]:
        state = self.image.to_dict()
        state["runtime"] = {
            "source_path": str(self.source_path),
            "last_error": self.last_error,
        }
        return state

    def start_watching(self, interval: float = 0.35) -> None:
        if interval < 0.1:
            raise ValueError("watch interval must be at least 0.1 seconds")
        if self._watcher is not None and self._watcher.is_alive():
            return
        self._stop.clear()

        def watch() -> None:
            while not self._stop.wait(interval):
                try:
                    self.refresh()
                except OSError as exc:
                    with self._lock:
                        self._last_error = str(exc)

        self._watcher = threading.Thread(
            target=watch,
            name="glyph-pure-runtime-watch",
            daemon=True,
        )
        self._watcher.start()

    def stop(self) -> None:
        self._stop.set()
        if self._watcher is not None:
            self._watcher.join(timeout=1.0)
