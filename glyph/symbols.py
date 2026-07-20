from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, order=True)
class SymbolId:
    value: int

    def __int__(self) -> int:
        return self.value


@dataclass(frozen=True)
class SymbolRecord:
    id: SymbolId
    name: str
    kind: str
    line: int
    type_name: str | None = None


class SymbolInterner:
    """Deterministic source-order symbol interner."""

    def __init__(self) -> None:
        self._by_name: dict[tuple[str, str], SymbolId] = {}
        self._records: list[SymbolRecord] = []

    def intern(
        self,
        name: str,
        kind: str,
        line: int,
        type_name: str | None = None,
    ) -> SymbolId:
        key = (kind, name)
        existing = self._by_name.get(key)
        if existing is not None:
            return existing
        symbol_id = SymbolId(len(self._records))
        self._by_name[key] = symbol_id
        self._records.append(SymbolRecord(symbol_id, name, kind, line, type_name))
        return symbol_id

    def lookup(self, name: str, kinds: tuple[str, ...] | None = None) -> SymbolId | None:
        if kinds is not None:
            for kind in kinds:
                found = self._by_name.get((kind, name))
                if found is not None:
                    return found
            return None
        for record in self._records:
            if record.name == name:
                return record.id
        return None

    def record(self, symbol_id: SymbolId) -> SymbolRecord:
        return self._records[symbol_id.value]

    @property
    def records(self) -> tuple[SymbolRecord, ...]:
        return tuple(self._records)

    def to_dict(self) -> list[dict[str, object]]:
        return [
            {
                **asdict(record),
                "id": record.id.value,
            }
            for record in self._records
        ]
