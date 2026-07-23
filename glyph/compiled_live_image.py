from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from typing import Any

from .artifacts import CompilationModel
from .live_definition_builder import build_compilation_definitions
from .live_image import LiveImage, LiveWorld, build_world_patch


def _semantic_digest(design: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        design,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CompiledLiveImage(LiveImage):
    """LiveImage adapter that consumes the compiler-internal definition manifest.

    This class is package-internal. It uses LiveImage's protected transaction hooks so
    the public LiveImage remains usable with typed-design-only tooling, while Studio can
    detect legacy product/sum/alias shape without reparsing source or changing Public IR.
    """

    def stage_compilation(
        self,
        model: CompilationModel,
        design: dict[str, object],
        *,
        source_digest: str,
        generated_code: str,
    ) -> dict[str, object]:
        definitions = build_compilation_definitions(model, design)
        semantic_digest = _semantic_digest(design)
        code_digest = hashlib.sha256(generated_code.encode("utf-8")).hexdigest()
        with self._lock:
            active = (
                None
                if self._active_version is None
                else self._worlds[self._active_version]
            )
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
