from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .studio import GlyphStudio, StudioSnapshot, _atomic_write


class GlyphProjectStudio(GlyphStudio):
    """Glyph Studio with a stable, user-owned `manual.rs` extension point."""

    def rebuild(self, source: str | None = None) -> StudioSnapshot:
        snapshot = super().rebuild(source)
        if snapshot.status != "ready":
            return snapshot

        compilation = self.compiler.compile_text(
            snapshot.source,
            source_name=str(self.input_path),
            source_href=str(self.input_path),
        ).snapshot
        scaffold = compilation.artifacts.manual_scaffold
        if not scaffold:
            return snapshot

        manual_path = self.output_dir / "manual.rs"
        if not manual_path.exists():
            _atomic_write(manual_path, scaffold)
        manual = manual_path.read_text(encoding="utf-8")

        artifacts = dict(snapshot.artifacts)
        artifacts["manual.rs"] = manual
        updated = replace(snapshot, artifacts=artifacts)
        with self._lock:
            self._snapshot = updated
        return updated


def run_project_studio(input_path: str | Path) -> int:
    return GlyphProjectStudio(input_path).serve()
