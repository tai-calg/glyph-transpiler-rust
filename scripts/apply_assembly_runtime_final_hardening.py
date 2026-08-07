from __future__ import annotations

from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise RuntimeError(f"missing patch anchor: {label}")
    print(f"patch: {label}")
    return text.replace(old, new, 1)


runtime_path = Path("glyph/assembly_runtime.py")
text = runtime_path.read_text(encoding="utf-8")
text = replace_once(text, "from copy import deepcopy\n", "", "remove deepcopy import")

text = replace_once(
    text,
    '''    def __init__(self, cause: BaseException, audit: ImmediateReactionFailureAudit):
        super().__init__(f"Assembly reaction failed: {cause}")
        self.cause = cause
        self.audit = audit
''',
    '''    def __init__(self, cause: BaseException, audit: ImmediateReactionFailureAudit):
        super().__init__(f"Assembly reaction failed: {_error_text(cause)}")
        self.cause = cause
        self.audit = audit
''',
    "safe fallback failure message",
)

text = replace_once(
    text,
    '''def _error_text(error: BaseException) -> str:
    return f"{type(error).__name__}: {error}"
''',
    '''def _error_text(error: BaseException) -> str:
    try:
        message = str(error)
    except BaseException:
        message = "<message unavailable>"
    try:
        type_name = type(error).__name__
    except BaseException:
        type_name = "<unknown exception>"
    return f"{type_name}: {message}"
''',
    "safe exception rendering",
)

text = replace_once(
    text,
    "def _public_snapshot(value: object, active: set[int] | None = None) -> object:\n",
    "def _public_snapshot_impl(value: object, active: set[int] | None = None) -> object:\n",
    "split snapshot implementation",
)

snapshot_wrapper = '''

def _public_snapshot(value: object, active: set[int] | None = None) -> object:
    """Create a detached immutable audit snapshot without masking execution errors."""

    try:
        return _public_snapshot_impl(value, active)
    except BaseException as snapshot_error:
        try:
            type_name = f"{type(value).__module__}.{type(value).__qualname__}"
        except BaseException:
            type_name = "<unknown value>"
        return FrozenObjectSnapshot(
            type_name=type_name,
            attributes=MappingProxyType(
                {"$snapshot_error": _error_text(snapshot_error)}
            ),
        )
'''
text = replace_once(
    text,
    "\n\nclass ImmediateAssemblyRuntime:\n",
    snapshot_wrapper + "\n\nclass ImmediateAssemblyRuntime:\n",
    "no-throw snapshot wrapper",
)

text = replace_once(
    text,
    '''    Internal state and routed values are always copied with trusted ``deepcopy``.
    The complete top-level causal reaction commits only on success. Host effects
    remain externally observable and are attached to failure audit metadata.
''',
    '''    Internal state and routed values are structurally cloned from validated Glyph
    type metadata and never invoke Python copy protocols. The complete top-level
    causal reaction commits only on success. Host effects remain externally
    observable and are attached to failure audit metadata.
''',
    "runtime clone contract docstring",
)

text = replace_once(
    text,
    '''    def _validate_type_definitions(self) -> None:
        for name, definition in self._types.items():
            kind = definition.get("kind")
            path = f"type {name}"
''',
    '''    def _validate_type_definitions(self) -> None:
        reserved_type_names = _PRIMITIVE_TYPE_NAMES | set(_GENERIC_ARITY) | {"Tuple"}
        for name, definition in self._types.items():
            path = f"type {name}"
            if name in reserved_type_names:
                raise GlyphError(f"{path}: 予約型名はユーザー定義できない")
            kind = definition.get("kind")
''',
    "reject reserved type definitions",
)

text = replace_once(
    text,
    '''        cloned = self._clone(dict(initial_states), "initial Assembly state")
        if not isinstance(cloned, dict):
            raise GlyphError("deepcopyはAssembly stateのdictを保持する必要がある")
        self._states = cloned
''',
    '''        self._states = self._clone_state_map(
            initial_states, "initial Assembly state"
        )
''',
    "initial structural clone",
)

old_clone = '''    @staticmethod
    def _clone(value: object, context: str) -> object:
        try:
            return deepcopy(value)
        except Exception as exc:
            raise GlyphError(f"{context}を安全に複製できない: {exc}") from exc

    @property
    def states(self) -> dict[str, object]:
        cloned = self._clone(self._states, "Assembly state snapshot")
        if not isinstance(cloned, dict):
            raise GlyphError("deepcopyはAssembly stateのdictを保持する必要がある")
        return cloned
'''
new_clone = '''    def _clone_typed(
        self,
        type_ref: Mapping[str, object],
        value: object,
        path: str,
        alias_stack: tuple[str, ...] = (),
    ) -> object:
        """Clone a validated Glyph value without invoking Python copy protocols."""

        name = str(type_ref.get("name") or "")
        arguments = self._type_arguments(type_ref)
        definition = self._types.get(name)
        if definition is not None and definition.get("kind") == "alias":
            if name in alias_stack:
                raise GlyphError(
                    f"{path}: 型alias循環がある: {' -> '.join((*alias_stack, name))}"
                )
            target = definition.get("target")
            if not isinstance(target, Mapping):
                raise GlyphError(f"{path}: alias '{name}' の型IRが壊れている")
            return self._clone_typed(target, value, path, (*alias_stack, name))

        if name == "()" or name in _BOOL_TYPES or name in _INT_TYPES or name in _FLOAT_TYPES:
            return value
        if name in _STRING_TYPES:
            return str(value)
        if name == "Option":
            if value is None:
                return None
            if isinstance(value, (tuple, list)) and len(value) == 2 and value[0] == "Some":
                return (
                    "Some",
                    self._clone_typed(arguments[0], value[1], f"{path}.Some"),
                )
            return self._clone_typed(arguments[0], value, f"{path}.Some")
        if name == "Vec":
            return [
                self._clone_typed(arguments[0], item, f"{path}[{index}]")
                for index, item in enumerate(value)
            ]
        if name == "Tuple":
            return tuple(
                self._clone_typed(item_type, item, f"{path}[{index}]")
                for index, (item_type, item) in enumerate(zip(arguments, value))
            )
        if name == "Result":
            tag = value[0]
            branch = 0 if tag == "Ok" else 1
            return (
                tag,
                self._clone_typed(arguments[branch], value[1], f"{path}.{tag}"),
            )

        if definition is not None and definition.get("kind") == "product":
            fields_value = tuple(
                item
                for item in definition.get("fields", ())
                if isinstance(item, Mapping)
            )
            cloned: dict[str, object] = {}
            for field in fields_value:
                field_name = str(field["name"])
                field_type = field.get("type")
                if not isinstance(field_type, Mapping):
                    raise GlyphError(f"{path}.{field_name}: 型IRが壊れている")
                cloned[field_name] = self._clone_typed(
                    field_type,
                    value[field_name],
                    f"{path}.{field_name}",
                )
            return cloned

        if definition is not None and definition.get("kind") == "sum":
            variants = {
                str(item["name"]): item
                for item in definition.get("variants", ())
                if isinstance(item, Mapping)
            }
            if isinstance(value, str):
                return str(value)
            if isinstance(value, (tuple, list)) and value:
                variant_name = str(value[0])
                variant = variants[variant_name]
                tuple_types = tuple(
                    item
                    for item in variant.get("tuple_types", ())
                    if isinstance(item, Mapping)
                )
                return (
                    variant_name,
                    *(
                        self._clone_typed(
                            item_type,
                            item,
                            f"{path}.{variant_name}[{index}]",
                        )
                        for index, (item_type, item) in enumerate(
                            zip(tuple_types, value[1:])
                        )
                    ),
                )
            if isinstance(value, Mapping) and "$variant" in value:
                variant_name = str(value["$variant"])
                variant = variants[variant_name]
                cloned_record: dict[str, object] = {"$variant": variant_name}
                for field in variant.get("fields", ()):
                    if not isinstance(field, Mapping):
                        continue
                    field_name = str(field["name"])
                    field_type = field.get("type")
                    if not isinstance(field_type, Mapping):
                        raise GlyphError(f"{path}.{field_name}: 型IRが壊れている")
                    cloned_record[field_name] = self._clone_typed(
                        field_type,
                        value[field_name],
                        f"{path}.{variant_name}.{field_name}",
                    )
                return cloned_record

        raise GlyphError(f"{path}: 型 '{name}' をstructural cloneできない")

    def _clone_state_map(
        self,
        states: Mapping[str, object],
        context: str,
    ) -> dict[str, object]:
        return {
            instance: self._clone_typed(
                self._state_type(instance),
                states[instance],
                f"{context}.{instance}",
            )
            for instance in self._instances
        }

    @property
    def states(self) -> dict[str, object]:
        return self._clone_state_map(self._states, "Assembly state snapshot")
'''
text = replace_once(text, old_clone, new_clone, "typed structural clone")

text = replace_once(
    text,
    '''        working_value = self._clone(self._states, "reaction working state")
        if not isinstance(working_value, dict):
            raise GlyphError("deepcopyはAssembly stateのdictを保持する必要がある")
        working: dict[str, object] = working_value
''',
    '''        working: dict[str, object] = self._clone_state_map(
            self._states, "reaction working state"
        )
''',
    "working structural clone",
)

text = replace_once(
    text,
    '''                            routed_payload = self._clone(
                                invocation.arguments[0],
                                f"route payload {target}.{invocation.effect}",
                            )
''',
    '''                            payload_type = parameters[0].get("type_ref")
                            if not isinstance(payload_type, Mapping):
                                raise GlyphError(
                                    f"effect '{target}.{invocation.effect}' のpayload型IRが壊れている"
                                )
                            routed_payload = self._clone_typed(
                                payload_type,
                                invocation.arguments[0],
                                f"route payload {target}.{invocation.effect}",
                            )
''',
    "route structural clone",
)

text = replace_once(
    text,
    '''                            host_arguments = tuple(
                                self._clone(
                                    argument,
                                    f"Host argument {target}.{invocation.effect}",
                                )
                                for argument in invocation.arguments
                            )
''',
    '''                            host_arguments_list: list[object] = []
                            for parameter, argument in zip(
                                parameters, invocation.arguments
                            ):
                                parameter_type = parameter.get("type_ref")
                                if not isinstance(parameter_type, Mapping):
                                    raise GlyphError(
                                        f"effect '{target}.{invocation.effect}' の引数型IRが壊れている"
                                    )
                                host_arguments_list.append(
                                    self._clone_typed(
                                        parameter_type,
                                        argument,
                                        f"Host argument {target}.{invocation.effect}",
                                    )
                                )
                            host_arguments = tuple(host_arguments_list)
''',
    "Host argument structural clone",
)

text = replace_once(
    text,
    '''                            try:
                                raw_result = host_executor(
                                    target,
                                    invocation.effect,
                                    host_arguments,
                                )
                            except BaseException as host_error:
                                external.append(
                                    ExternalEffect(
                                        instance=target,
                                        effect=invocation.effect,
                                        arguments=audit_arguments,
                                        result=None,
                                        status="raised",
                                        error=_error_text(host_error),
                                    )
                                )
                                raise

                            result_snapshot = _public_snapshot(raw_result)
''',
    '''                            audit_index = len(external)
                            external.append(
                                ExternalEffect(
                                    instance=target,
                                    effect=invocation.effect,
                                    arguments=audit_arguments,
                                    result=None,
                                    status="attempted",
                                )
                            )
                            try:
                                raw_result = host_executor(
                                    target,
                                    invocation.effect,
                                    host_arguments,
                                )
                            except BaseException as host_error:
                                external[audit_index] = ExternalEffect(
                                    instance=target,
                                    effect=invocation.effect,
                                    arguments=audit_arguments,
                                    result=None,
                                    status="raised",
                                    error=_error_text(host_error),
                                )
                                raise

                            result_snapshot = _public_snapshot(raw_result)
''',
    "pre-Host attempted audit",
)

text = replace_once(
    text,
    '''                                external.append(
                                    ExternalEffect(
                                        instance=target,
                                        effect=invocation.effect,
                                        arguments=audit_arguments,
                                        result=result_snapshot,
                                        status="invalid-result",
                                        error=_error_text(definition_error),
                                    )
                                )
''',
    '''                                external[audit_index] = ExternalEffect(
                                    instance=target,
                                    effect=invocation.effect,
                                    arguments=audit_arguments,
                                    result=result_snapshot,
                                    status="invalid-result",
                                    error=_error_text(definition_error),
                                )
''',
    "definition failure audit update",
)

text = replace_once(
    text,
    '''                                external.append(
                                    ExternalEffect(
                                        instance=target,
                                        effect=invocation.effect,
                                        arguments=audit_arguments,
                                        result=result_snapshot,
                                        status="invalid-result",
                                        error=_error_text(validation_error),
                                    )
                                )
''',
    '''                                external[audit_index] = ExternalEffect(
                                    instance=target,
                                    effect=invocation.effect,
                                    arguments=audit_arguments,
                                    result=result_snapshot,
                                    status="invalid-result",
                                    error=_error_text(validation_error),
                                )
''',
    "validation failure audit update",
)

text = replace_once(
    text,
    '''                            effect_result = self._clone(
                                raw_result,
                                f"Host result {target}.{invocation.effect}",
                            )
                            external.append(
                                ExternalEffect(
                                    instance=target,
                                    effect=invocation.effect,
                                    arguments=audit_arguments,
                                    result=result_snapshot,
                                    status="validated",
                                )
                            )
''',
    '''                            effect_result = self._clone_typed(
                                result_type,
                                raw_result,
                                f"Host result {target}.{invocation.effect}",
                            )
                            external[audit_index] = ExternalEffect(
                                instance=target,
                                effect=invocation.effect,
                                arguments=audit_arguments,
                                result=result_snapshot,
                                status="validated",
                            )
''',
    "Host result structural clone",
)

text = replace_once(
    text,
    '                working[target] = self._clone(next_state, f"next state {target}")\n',
    '''                working[target] = self._clone_typed(
                    self._state_type(target),
                    next_state,
                    f"next state {target}",
                )
''',
    "next-state structural clone",
)

text = replace_once(
    text,
    'phase="commit",',
    'phase="stage",',
    "trace stage semantics",
)

text = replace_once(
    text,
    '            top_payload = self._clone(value, f"input {instance}.{input_name}")\n',
    '''            top_payload = self._clone_typed(
                input_type,
                value,
                f"input {instance}.{input_name}",
            )
''',
    "top input structural clone",
)

text = replace_once(
    text,
    '''            committed = self._clone(working, "committed Assembly state")
            if not isinstance(committed, dict):
                raise GlyphError("deepcopyはAssembly stateのdictを保持する必要がある")
            self._states = committed
''',
    '''            self._states = self._clone_state_map(
                working, "committed Assembly state"
            )
''',
    "atomic committed-state structural clone",
)

if "self._clone(" in text:
    raise RuntimeError("legacy self._clone call remains")
if "from copy import deepcopy" in text:
    raise RuntimeError("deepcopy import remains")
runtime_path.write_text(text, encoding="utf-8")

assembly_path = Path("glyph/assembly.py")
text = assembly_path.read_text(encoding="utf-8")
text = replace_once(
    text,
    '''    def __new__(cls, values: Mapping[str, object]):
        if not isinstance(values, Mapping):
            raise TypeError("FrozenMappingにはMappingが必要")
        return tuple.__new__(
            cls,
            tuple((str(key), _freeze(value)) for key, value in values.items()),
        )
''',
    '''    def __new__(cls, values: Mapping[str, object]):
        if not isinstance(values, Mapping):
            raise TypeError("FrozenMappingにはMappingが必要")
        pairs: list[tuple[str, object]] = []
        seen: set[str] = set()
        for key, value in values.items():
            if type(key) is not str:
                raise TypeError("Assembly IR mapping keyはstrのみ許可する")
            if key in seen:
                raise TypeError(f"Assembly IR mapping keyが重複している: {key}")
            seen.add(key)
            pairs.append((key, _freeze(value)))
        return tuple.__new__(cls, tuple(pairs))
''',
    "strict FrozenMapping keys",
)
assembly_path.write_text(text, encoding="utf-8")

print("Assembly runtime final hardening patch applied")
