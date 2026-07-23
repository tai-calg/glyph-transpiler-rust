from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any

from .artifacts import CompilationModel
from .compiler import AliasDecl, FunctionDecl, ProductDecl, SumDecl, TypeRef


UI_IR_SCHEMA = "glyph.ui-ir"
UI_IR_VERSION = 1


class UiIrError(ValueError):
    """Raised when a validated Glyph model cannot be projected into UI IR."""


@dataclass(frozen=True)
class UiNode:
    id: str
    path: tuple[str, ...]
    label: str
    type_name: str
    kind: str
    role: str
    required: bool = True
    default: Any = None
    minimum: int | float | None = None
    maximum: int | float | None = None
    choices: tuple[str, ...] = ()
    children: tuple["UiNode", ...] = ()
    description: str = ""

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "path": list(self.path),
            "label": self.label,
            "type": self.type_name,
            "kind": self.kind,
            "role": self.role,
            "required": self.required,
        }
        if self.default is not None:
            data["default"] = self.default
        if self.minimum is not None:
            data["minimum"] = self.minimum
        if self.maximum is not None:
            data["maximum"] = self.maximum
        if self.choices:
            data["choices"] = list(self.choices)
        if self.children:
            data["children"] = [child.to_dict() for child in self.children]
        if self.description:
            data["description"] = self.description
        return data


@dataclass(frozen=True)
class UiAction:
    id: str
    name: str
    label: str
    source_line: int
    inputs: tuple[UiNode, ...]
    output: UiNode

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "name": self.name,
            "label": self.label,
            "source_line": self.source_line,
            "inputs": [node.to_dict() for node in self.inputs],
            "output": self.output.to_dict(),
        }


@dataclass(frozen=True)
class UiApplication:
    source_name: str
    title: str
    action: UiAction
    candidates: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": UI_IR_SCHEMA,
            "version": UI_IR_VERSION,
            "source": self.source_name,
            "title": self.title,
            "action": self.action.to_dict(),
            "candidates": list(self.candidates),
        }

    def to_json(self) -> str:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"


_FLOAT_TYPES = {"F", "D", "f32", "f64"}
_BOOL_TYPES = {"B", "bool"}
_TEXT_TYPES = {"S", "String", "str"}
_INTEGER_RANGES: dict[str, tuple[int, int]] = {
    "U": (0, 2**16 - 1),
    "I": (-(2**31), 2**31 - 1),
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
}


def _humanize(name: str) -> str:
    text = re.sub(r"(?<!^)(?=[A-Z])", " ", name.replace("_", " "))
    return " ".join(part for part in text.split() if part).strip().title() or name


def _type_text(type_ref: TypeRef) -> str:
    if type_ref.name == "tuple":
        return "(" + ", ".join(_type_text(item) for item in type_ref.args) + ")"
    if type_ref.args:
        return f"{type_ref.name}<{', '.join(_type_text(item) for item in type_ref.args)}>"
    return type_ref.name


def _node_id(role: str, path: tuple[str, ...]) -> str:
    return f"{role}:" + ".".join(path)


class UiIrBuilder:
    """Project one validated CompilationModel into conservative, library-neutral UI IR."""

    def __init__(self, model: CompilationModel):
        self.model = model
        self.products = {
            declaration.name: declaration
            for declaration in model.program.declarations
            if isinstance(declaration, ProductDecl)
        }
        self.sums = {
            declaration.name: declaration
            for declaration in model.program.declarations
            if isinstance(declaration, SumDecl)
        }
        self.aliases = {
            declaration.name: declaration
            for declaration in model.program.declarations
            if isinstance(declaration, AliasDecl)
        }
        self.functions = {
            declaration.name: declaration
            for declaration in model.program.declarations
            if isinstance(declaration, FunctionDecl)
            and not declaration.name.startswith("__glyph_")
        }

    @property
    def candidates(self) -> tuple[str, ...]:
        return tuple(sorted(self.functions))

    def choose_action(self, requested: str | None) -> FunctionDecl:
        if requested is not None:
            declaration = self.functions.get(requested)
            if declaration is None:
                available = ", ".join(self.candidates) or "none"
                raise UiIrError(
                    f"pure Glyph function '{requested}' is not available; candidates: {available}"
                )
            return declaration

        for conventional in ("render", "main"):
            declaration = self.functions.get(conventional)
            if declaration is not None:
                return declaration
        if len(self.functions) == 1:
            return next(iter(self.functions.values()))
        available = ", ".join(self.candidates) or "none"
        raise UiIrError(
            "UI action is ambiguous; pass --function. " f"Candidates: {available}"
        )

    def build(
        self,
        *,
        function_name: str | None = None,
        source_name: str = "input.glyph",
        title: str | None = None,
    ) -> UiApplication:
        declaration = self.choose_action(function_name)
        inputs = tuple(
            self._node_for_type(
                parameter.ty,
                path=(parameter.name,),
                role="input",
                label=_humanize(parameter.name),
                stack=(),
            )
            for parameter in declaration.params
        )
        output = self._node_for_type(
            declaration.return_type,
            path=("return",),
            role="output",
            label="Result",
            stack=(),
        )
        action = UiAction(
            id=f"action:{declaration.name}",
            name=declaration.name,
            label=_humanize(declaration.name),
            source_line=declaration.line,
            inputs=inputs,
            output=output,
        )
        app_title = title or f"{_humanize(declaration.name)} · Glyph App"
        return UiApplication(source_name, app_title, action, self.candidates)

    def _resolve_alias(self, type_ref: TypeRef) -> TypeRef:
        current = type_ref
        visited: set[str] = set()
        while current.name in self.aliases:
            if current.name in visited:
                raise UiIrError(f"type alias cycle at '{current.name}'")
            visited.add(current.name)
            current = self.aliases[current.name].target
        return current

    def _node_for_type(
        self,
        type_ref: TypeRef,
        *,
        path: tuple[str, ...],
        role: str,
        label: str,
        stack: tuple[str, ...],
    ) -> UiNode:
        resolved = self._resolve_alias(type_ref)
        name = resolved.name
        type_name = _type_text(resolved)
        node_id = _node_id(role, path)

        if name in _FLOAT_TYPES:
            return UiNode(
                node_id,
                path,
                label,
                type_name,
                "number" if role == "input" else "metric",
                role,
                default=0.0 if role == "input" else None,
            )
        if name in _INTEGER_RANGES:
            minimum, maximum = _INTEGER_RANGES[name]
            return UiNode(
                node_id,
                path,
                label,
                type_name,
                "integer" if role == "input" else "metric",
                role,
                default=0 if role == "input" else None,
                minimum=minimum,
                maximum=maximum,
            )
        if name in _BOOL_TYPES:
            return UiNode(
                node_id,
                path,
                label,
                type_name,
                "checkbox" if role == "input" else "status",
                role,
                default=False if role == "input" else None,
            )
        if name in _TEXT_TYPES:
            return UiNode(
                node_id,
                path,
                label,
                type_name,
                "text",
                role,
                default="" if role == "input" else None,
            )
        if name == "()":
            return UiNode(node_id, path, label, type_name, "unit", role, required=False)

        product = self.products.get(name)
        if product is not None:
            if name in stack:
                return UiNode(
                    node_id,
                    path,
                    label,
                    type_name,
                    "json",
                    role,
                    default={} if role == "input" else None,
                    description="Recursive product is represented as JSON.",
                )
            children = tuple(
                self._node_for_type(
                    field.ty,
                    path=(*path, field.name),
                    role=role,
                    label=_humanize(field.name),
                    stack=(*stack, name),
                )
                for field in product.fields
            )
            return UiNode(
                node_id,
                path,
                label,
                type_name,
                "object",
                role,
                children=children,
            )

        sum_type = self.sums.get(name)
        if sum_type is not None:
            choices = tuple(variant.name for variant in sum_type.variants)
            unit_only = all(
                not variant.tuple_types and not variant.fields
                for variant in sum_type.variants
            )
            if unit_only:
                return UiNode(
                    node_id,
                    path,
                    label,
                    type_name,
                    "select" if role == "input" else "badge",
                    role,
                    default=choices[0] if role == "input" and choices else None,
                    choices=choices,
                )
            return UiNode(
                node_id,
                path,
                label,
                type_name,
                "json",
                role,
                default={"variant": choices[0]} if role == "input" and choices else None,
                choices=choices,
                description=(
                    "Payload variants require an explicit JSON value with variant, values, "
                    "or fields."
                ),
            )

        if name == "tuple":
            children = tuple(
                self._node_for_type(
                    item,
                    path=(*path, str(index)),
                    role=role,
                    label=f"Item {index + 1}",
                    stack=stack,
                )
                for index, item in enumerate(resolved.args)
            )
            return UiNode(
                node_id,
                path,
                label,
                type_name,
                "tuple" if role == "output" else "json",
                role,
                default=[] if role == "input" else None,
                children=children,
            )

        if name in {"R", "Result"} and len(resolved.args) == 2:
            children = (
                self._node_for_type(
                    resolved.args[0],
                    path=(*path, "ok"),
                    role=role,
                    label="Success",
                    stack=stack,
                ),
                self._node_for_type(
                    resolved.args[1],
                    path=(*path, "error"),
                    role=role,
                    label="Error",
                    stack=stack,
                ),
            )
            return UiNode(
                node_id,
                path,
                label,
                type_name,
                "result" if role == "output" else "json",
                role,
                default={} if role == "input" else None,
                children=children,
            )

        if name in {"O", "Option"} and len(resolved.args) == 1:
            child = self._node_for_type(
                resolved.args[0],
                path=(*path, "value"),
                role=role,
                label="Value",
                stack=stack,
            )
            return UiNode(
                node_id,
                path,
                label,
                type_name,
                "option" if role == "output" else "json",
                role,
                required=False,
                default=None,
                children=(child,),
            )

        return UiNode(
            node_id,
            path,
            label,
            type_name,
            "json",
            role,
            default={} if role == "input" else None,
            description="No safe default widget exists for this Glyph type.",
        )


def build_ui_application(
    model: CompilationModel,
    *,
    function_name: str | None = None,
    source_name: str = "input.glyph",
    title: str | None = None,
) -> UiApplication:
    return UiIrBuilder(model).build(
        function_name=function_name,
        source_name=source_name,
        title=title,
    )
