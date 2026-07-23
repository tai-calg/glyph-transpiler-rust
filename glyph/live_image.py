from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import threading
from typing import Any


LIVE_IMAGE_SCHEMA = "glyph.live-image"
LIVE_IMAGE_VERSION = 1


class ReloadSafety(str, Enum):
    HOT_SWAP = "hot-swap"
    QUIESCENCE = "quiescence"
    MIGRATION = "migration"
    READER = "reader"


_SAFETY_ORDER = {
    ReloadSafety.HOT_SWAP: 0,
    ReloadSafety.QUIESCENCE: 1,
    ReloadSafety.MIGRATION: 2,
    ReloadSafety.READER: 3,
}


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _records(value: object) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _text(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _line(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _definition_id(kind: str, name: str) -> str:
    normalized_kind = kind.strip().lower().replace("_", "-")
    normalized_name = name.strip()
    if not normalized_kind or not normalized_name:
        raise ValueError("live definition requires a non-empty kind and name")
    return f"{normalized_kind}:{normalized_name}"


def _walk_expr(expr: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    values = [expr]
    for child in _records(expr.get("children")):
        values.extend(_walk_expr(child))
    return values


@dataclass(frozen=True)
class DefinitionVersion:
    id: str
    kind: str
    name: str
    line: int | None
    signature_digest: str
    implementation_digest: str
    content_digest: str
    dependencies: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "line": self.line,
            "signature_digest": self.signature_digest,
            "implementation_digest": self.implementation_digest,
            "content_digest": self.content_digest,
            "dependencies": list(self.dependencies),
        }


@dataclass(frozen=True)
class DefinitionChange:
    definition_id: str
    kind: str
    name: str
    change: str
    safety: ReloadSafety
    reason: str
    line: int | None
    affected: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "definition_id": self.definition_id,
            "kind": self.kind,
            "name": self.name,
            "change": self.change,
            "safety": self.safety.value,
            "reason": self.reason,
            "line": self.line,
            "affected": list(self.affected),
        }


@dataclass(frozen=True)
class LiveWorld:
    version: int
    parent_version: int | None
    source_digest: str
    semantic_digest: str
    code_digest: str
    definitions: tuple[DefinitionVersion, ...]

    def by_id(self) -> dict[str, DefinitionVersion]:
        return {item.id: item for item in self.definitions}

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "parent_version": self.parent_version,
            "source_digest": self.source_digest,
            "semantic_digest": self.semantic_digest,
            "code_digest": self.code_digest,
            "definitions": [item.to_dict() for item in self.definitions],
        }


@dataclass(frozen=True)
class WorldPatch:
    id: str
    base_world: int
    target_world: int
    source_digest: str
    semantic_digest: str
    code_digest: str
    definitions: tuple[DefinitionVersion, ...]
    changes: tuple[DefinitionChange, ...]
    blockers: tuple[str, ...]

    @property
    def maximum_safety(self) -> ReloadSafety:
        return max(
            (change.safety for change in self.changes),
            key=lambda item: _SAFETY_ORDER[item],
            default=ReloadSafety.HOT_SWAP,
        )

    def to_world(self) -> LiveWorld:
        return LiveWorld(
            version=self.target_world,
            parent_version=self.base_world,
            source_digest=self.source_digest,
            semantic_digest=self.semantic_digest,
            code_digest=self.code_digest,
            definitions=self.definitions,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "base_world": self.base_world,
            "target_world": self.target_world,
            "source_digest": self.source_digest,
            "semantic_digest": self.semantic_digest,
            "code_digest": self.code_digest,
            "maximum_safety": self.maximum_safety.value,
            "changes": [item.to_dict() for item in self.changes],
            "blockers": list(self.blockers),
        }


def _function_definitions(design: Mapping[str, Any]) -> list[DefinitionVersion]:
    symbols = {
        _text(item.get("id")): item
        for item in _records(design.get("symbols"))
        if _text(item.get("id"))
    }
    symbol_to_definition: dict[str, str] = {}
    for function in _records(design.get("functions")):
        symbol_id = _text(function.get("symbol_id"))
        name = _text(function.get("name"))
        if symbol_id and name:
            symbol_to_definition[symbol_id] = _definition_id("function", name)

    definitions: list[DefinitionVersion] = []
    for function in _records(design.get("functions")):
        name = _text(function.get("name"))
        if not name:
            continue
        raw_params = function.get("params")
        parameter_symbols = (
            [_text(item) for item in raw_params if isinstance(item, str)]
            if isinstance(raw_params, list)
            else []
        )
        parameter_types = [
            _text(symbols.get(symbol_id, {}).get("type"), "unknown")
            for symbol_id in parameter_symbols
        ]
        signature = {
            "params": parameter_types,
            "return": _text(function.get("return_type"), "unknown"),
        }
        body = _mapping(function.get("body"))
        definition_id = _definition_id("function", name)
        dependencies = sorted(
            {
                symbol_to_definition[symbol_id]
                for node in _walk_expr(body)
                for symbol_id in (_text(node.get("symbol_id")),)
                if symbol_id in symbol_to_definition
                and symbol_to_definition[symbol_id] != definition_id
            }
        )
        content = {
            "signature": signature,
            "body": body,
            "recursion": function.get("recursion"),
        }
        definitions.append(
            DefinitionVersion(
                id=definition_id,
                kind="function",
                name=name,
                line=_line(function.get("line")),
                signature_digest=_digest(signature),
                implementation_digest=_digest(body),
                content_digest=_digest(content),
                dependencies=tuple(dependencies),
            )
        )
    return definitions


def _symbol_definitions(design: Mapping[str, Any]) -> list[DefinitionVersion]:
    function_names = {
        _text(item.get("name"))
        for item in _records(design.get("functions"))
        if _text(item.get("name"))
    }
    definitions: list[DefinitionVersion] = []
    for symbol in _records(design.get("symbols")):
        kind = _text(symbol.get("kind"))
        name = _text(symbol.get("name"))
        if not name or kind in {"parameter", "variant", "macro", "temporal"}:
            continue
        if kind == "function" and name in function_names:
            continue
        normalized_kind = "function" if kind in {"effect", "opaque"} else "type"
        signature = {
            "symbol_kind": kind,
            "type": _text(symbol.get("type"), "unknown"),
        }
        definitions.append(
            DefinitionVersion(
                id=_definition_id(normalized_kind, name),
                kind=normalized_kind,
                name=name,
                line=_line(symbol.get("line")),
                signature_digest=_digest(signature),
                implementation_digest=_digest({"external": kind in {"effect", "opaque"}}),
                content_digest=_digest(signature),
            )
        )
    return definitions


def _named_section_definitions(
    values: list[Mapping[str, Any]],
    kind: str,
    *,
    implementation_keys: tuple[str, ...] = (),
) -> list[DefinitionVersion]:
    definitions: list[DefinitionVersion] = []
    for value in values:
        name = _text(value.get("name"))
        if not name:
            continue
        signature = {
            key: item
            for key, item in value.items()
            if key not in implementation_keys
            and key not in {"line", "body_start", "body_end"}
        }
        implementation = {key: value.get(key) for key in implementation_keys}
        definitions.append(
            DefinitionVersion(
                id=_definition_id(kind, name),
                kind=kind,
                name=name,
                line=_line(value.get("line")),
                signature_digest=_digest(signature),
                implementation_digest=_digest(implementation),
                content_digest=_digest(value),
            )
        )
    return definitions


def build_live_definitions(
    design: Mapping[str, Any],
) -> tuple[DefinitionVersion, ...]:
    definitions: dict[str, DefinitionVersion] = {}

    def add(items: list[DefinitionVersion]) -> None:
        for item in items:
            current = definitions.get(item.id)
            if current is not None:
                if current.kind == "function" and item.kind == "function":
                    continue
                if current.content_digest != item.content_digest:
                    raise ValueError(f"conflicting live definition: {item.id}")
            definitions[item.id] = item

    add(_function_definitions(design))
    add(_symbol_definitions(design))

    capabilities = _mapping(design.get("capabilities"))
    add(_named_section_definitions(_records(capabilities.get("resources")), "resource"))
    add(_named_section_definitions(_records(capabilities.get("aggregates")), "aggregate"))

    runtime = _mapping(design.get("runtime_contracts"))
    for section, kind, implementation_keys in (
        ("worlds", "world", ()),
        ("protocols", "protocol", ("root",)),
        ("handlers", "handler", ("steps",)),
        ("laws", "law", ("formula",)),
    ):
        add(
            _named_section_definitions(
                _records(runtime.get(section)),
                kind,
                implementation_keys=implementation_keys,
            )
        )

    add(
        _named_section_definitions(
            _records(design.get("machines")),
            "machine",
            implementation_keys=("selector", "initial", "next"),
        )
    )
    add(
        _named_section_definitions(
            _records(design.get("raw_macros")),
            "reader",
            implementation_keys=("body", "replacement"),
        )
    )

    return tuple(sorted(definitions.values(), key=lambda item: item.id))


def _reverse_dependencies(
    definitions: Mapping[str, DefinitionVersion],
) -> dict[str, set[str]]:
    reverse: dict[str, set[str]] = {
        definition_id: set() for definition_id in definitions
    }
    for definition in definitions.values():
        for dependency in definition.dependencies:
            reverse.setdefault(dependency, set()).add(definition.id)
    return reverse


def _affected(
    definition_id: str,
    reverse: Mapping[str, set[str]],
) -> tuple[str, ...]:
    found: set[str] = set()
    queue = list(sorted(reverse.get(definition_id, ())))
    while queue:
        current = queue.pop(0)
        if current in found:
            continue
        found.add(current)
        queue.extend(sorted(reverse.get(current, ())))
    return tuple(sorted(found))


def _classify_change(
    previous: DefinitionVersion | None,
    candidate: DefinitionVersion | None,
) -> tuple[ReloadSafety, str]:
    value = candidate or previous
    if value is None:
        raise ValueError("change classification requires a definition")
    if previous is None:
        if value.kind == "function":
            return ReloadSafety.HOT_SWAP, "new definition cell can be published atomically"
        if value.kind == "reader":
            return ReloadSafety.READER, "reader or macro changes start at the next read transaction"
        if value.kind in {"resource", "aggregate", "type"}:
            return ReloadSafety.MIGRATION, "new data definition requires an explicit state boundary"
        return ReloadSafety.QUIESCENCE, "new runtime contract becomes active at a quiescent boundary"
    if candidate is None:
        return ReloadSafety.MIGRATION, "removing a definition may invalidate live references"
    if value.kind == "function":
        if previous.signature_digest == candidate.signature_digest:
            return ReloadSafety.HOT_SWAP, "function body changed without changing its typed boundary"
        return ReloadSafety.MIGRATION, "function signature changed"
    if value.kind == "reader":
        return ReloadSafety.READER, "reader or macro generation changed"
    if value.kind in {"resource", "aggregate", "type"}:
        return ReloadSafety.MIGRATION, "data shape or resource contract changed"
    return ReloadSafety.QUIESCENCE, f"{value.kind} semantics changed"


def build_world_patch(
    active: LiveWorld,
    *,
    source_digest: str,
    semantic_digest: str,
    code_digest: str,
    definitions: tuple[DefinitionVersion, ...],
) -> WorldPatch | None:
    previous = active.by_id()
    candidate = {item.id: item for item in definitions}
    reverse = _reverse_dependencies(candidate)
    changes: list[DefinitionChange] = []
    for definition_id in sorted(set(previous) | set(candidate)):
        old = previous.get(definition_id)
        new = candidate.get(definition_id)
        if old is not None and new is not None and old.content_digest == new.content_digest:
            continue
        safety, reason = _classify_change(old, new)
        value = new or old
        if value is None:
            continue
        change = "added" if old is None else "removed" if new is None else "modified"
        changes.append(
            DefinitionChange(
                definition_id=definition_id,
                kind=value.kind,
                name=value.name,
                change=change,
                safety=safety,
                reason=reason,
                line=value.line,
                affected=_affected(definition_id, reverse),
            )
        )
    if not changes:
        return None
    target_world = active.version + 1
    blockers = []
    safety_values = {item.safety for item in changes}
    if ReloadSafety.MIGRATION in safety_values:
        blockers.append("migration-plan-required")
    if ReloadSafety.READER in safety_values:
        blockers.append("reader-generation-acknowledgement-required")
    patch_key = {
        "base": active.version,
        "target": target_world,
        "source": source_digest,
        "changes": [item.to_dict() for item in changes],
    }
    return WorldPatch(
        id=f"patch:{_digest(patch_key)[:16]}",
        base_world=active.version,
        target_world=target_world,
        source_digest=source_digest,
        semantic_digest=semantic_digest,
        code_digest=code_digest,
        definitions=definitions,
        changes=tuple(changes),
        blockers=tuple(blockers),
    )


class WorldLease(AbstractContextManager[LiveWorld]):
    def __init__(self, image: "LiveImage", world: LiveWorld):
        self._image = image
        self.world = world
        self._released = False

    def __enter__(self) -> LiveWorld:
        return self.world

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._image._release(self.world.version)


class LiveImage:
    """Versioned transactional live-definition image used by Glyph Studio.

    The image stores compiler metadata and generated-code handles, not concrete
    runtime objects. Old executions may retain a WorldLease while new executions
    observe a newer world.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._worlds: dict[int, LiveWorld] = {}
        self._active_version: int | None = None
        self._pending: WorldPatch | None = None
        self._leases: Counter[int] = Counter()
        self._cells: dict[str, list[tuple[int, str]]] = {}

    @property
    def active_world(self) -> LiveWorld | None:
        with self._lock:
            if self._active_version is None:
                return None
            return self._worlds[self._active_version]

    @property
    def pending_patch(self) -> WorldPatch | None:
        with self._lock:
            return self._pending

    def acquire(self) -> WorldLease:
        with self._lock:
            if self._active_version is None:
                raise RuntimeError("live image has no active world")
            self._leases[self._active_version] += 1
            return WorldLease(self, self._worlds[self._active_version])

    def _release(self, version: int) -> None:
        with self._lock:
            if self._leases[version] <= 0:
                raise RuntimeError(f"world {version} lease underflow")
            self._leases[version] -= 1
            if self._leases[version] == 0:
                del self._leases[version]
            self._try_auto_commit_locked()

    def stage(
        self,
        design: Mapping[str, Any],
        *,
        source_digest: str,
        generated_code: str,
    ) -> dict[str, object]:
        definitions = build_live_definitions(design)
        semantic_digest = _digest(design)
        code_digest = hashlib.sha256(generated_code.encode("utf-8")).hexdigest()
        with self._lock:
            active = self.active_world
            if active is None:
                world = LiveWorld(
                    version=1,
                    parent_version=None,
                    source_digest=source_digest,
                    semantic_digest=semantic_digest,
                    code_digest=code_digest,
                    definitions=definitions,
                )
                self._commit_world_locked(world)
                return self.to_dict()
            patch = build_world_patch(
                active,
                source_digest=source_digest,
                semantic_digest=semantic_digest,
                code_digest=code_digest,
                definitions=definitions,
            )
            if patch is None:
                self._pending = None
                return self.to_dict()
            self._pending = patch
            self._try_auto_commit_locked()
            return self.to_dict()

    def commit_pending(
        self,
        *,
        migration_plan: str | None = None,
        reader_acknowledged: bool = False,
    ) -> dict[str, object]:
        with self._lock:
            patch = self._pending
            if patch is None:
                return self.to_dict()
            active_leases = self._leases.get(patch.base_world, 0)
            if active_leases:
                raise RuntimeError(
                    f"world {patch.base_world} still has {active_leases} active lease(s)"
                )
            safety = {item.safety for item in patch.changes}
            if ReloadSafety.MIGRATION in safety and not (migration_plan or "").strip():
                raise RuntimeError("pending patch requires an explicit migration plan")
            if ReloadSafety.READER in safety and not reader_acknowledged:
                raise RuntimeError("pending patch changes the reader or macro generation")
            self._commit_world_locked(patch.to_world())
            self._pending = None
            return self.to_dict()

    def discard_pending(self) -> dict[str, object]:
        with self._lock:
            self._pending = None
            return self.to_dict()

    def _try_auto_commit_locked(self) -> None:
        patch = self._pending
        if patch is None or patch.blockers:
            return
        if patch.maximum_safety is ReloadSafety.HOT_SWAP:
            self._commit_world_locked(patch.to_world())
            self._pending = None
            return
        if self._leases.get(patch.base_world, 0) == 0:
            self._commit_world_locked(patch.to_world())
            self._pending = None

    def _commit_world_locked(self, world: LiveWorld) -> None:
        if self._active_version is not None and world.parent_version != self._active_version:
            raise RuntimeError("live world commit is not based on the active generation")
        self._worlds[world.version] = world
        self._active_version = world.version
        for definition in world.definitions:
            history = self._cells.setdefault(definition.id, [])
            if not history or history[-1][1] != definition.content_digest:
                history.append((world.version, definition.content_digest))

    def to_dict(self) -> dict[str, object]:
        with self._lock:
            active = (
                None
                if self._active_version is None
                else self._worlds[self._active_version]
            )
            active_definitions = {} if active is None else active.by_id()
            cells = []
            for definition_id in sorted(self._cells):
                history = self._cells[definition_id]
                active_definition = active_definitions.get(definition_id)
                cells.append(
                    {
                        "id": definition_id,
                        "active_world": None if active_definition is None else active.version,
                        "active_digest": (
                            None
                            if active_definition is None
                            else active_definition.content_digest
                        ),
                        "history": [
                            {"world": version, "digest": digest}
                            for version, digest in history
                        ],
                    }
                )
            return {
                "schema": LIVE_IMAGE_SCHEMA,
                "version": LIVE_IMAGE_VERSION,
                "active_world": None if active is None else active.to_dict(),
                "pending_patch": (
                    None if self._pending is None else self._pending.to_dict()
                ),
                "leases": [
                    {"world": version, "count": count}
                    for version, count in sorted(self._leases.items())
                ],
                "definition_cells": cells,
                "world_history": [
                    {
                        "version": version,
                        "parent_version": world.parent_version,
                        "source_digest": world.source_digest,
                    }
                    for version, world in sorted(self._worlds.items())
                ],
            }
