from __future__ import annotations

from collections.abc import Callable, Mapping
from importlib import metadata
import threading
from typing import Any, Protocol, TYPE_CHECKING, runtime_checkable

if TYPE_CHECKING:
    from .ui import UiProject


BACKEND_API_VERSION = 1
BACKEND_ENTRY_POINT_GROUP = "glyph.ui_backends"


class UiBackendError(RuntimeError):
    """Base error for public UI backend registration and execution."""


class UiBackendUnavailable(UiBackendError):
    """Raised when a requested backend is absent or its optional dependency is missing."""


@runtime_checkable
class UiBackend(Protocol):
    """Public backend contract for projecting glyph.ui-ir into a concrete UI library."""

    name: str
    api_version: int

    def build(self, project: "UiProject", **options: Any) -> Any:
        """Build and return a backend-native application object."""

    def launch(self, project: "UiProject", **options: Any) -> Any:
        """Build and launch an application, returning the backend launch result."""


BackendFactory = Callable[[], UiBackend]


class BackendRegistry:
    """Thread-safe registry for built-in and third-party UI backend factories."""

    def __init__(self) -> None:
        self._factories: dict[str, BackendFactory] = {}
        self._lock = threading.RLock()
        self._discovered = False

    @staticmethod
    def _normalize_name(name: str) -> str:
        normalized = name.strip().lower().replace("_", "-")
        if not normalized or any(character.isspace() for character in normalized):
            raise UiBackendError("backend name must be a non-empty token")
        return normalized

    def register(
        self,
        name: str,
        factory: BackendFactory,
        *,
        replace: bool = False,
    ) -> None:
        normalized = self._normalize_name(name)
        if not callable(factory):
            raise TypeError("backend factory must be callable")
        with self._lock:
            if normalized in self._factories and not replace:
                raise UiBackendError(f"backend '{normalized}' is already registered")
            self._factories[normalized] = factory

    def unregister(self, name: str) -> None:
        normalized = self._normalize_name(name)
        with self._lock:
            self._factories.pop(normalized, None)

    def names(self, *, discover: bool = True) -> tuple[str, ...]:
        if discover:
            self.discover()
        with self._lock:
            return tuple(sorted(self._factories))

    def create(self, name: str) -> UiBackend:
        normalized = self._normalize_name(name)
        self.discover()
        with self._lock:
            factory = self._factories.get(normalized)
        if factory is None:
            available = ", ".join(self.names(discover=False)) or "none"
            raise UiBackendUnavailable(
                f"UI backend '{normalized}' is not registered; available: {available}"
            )
        try:
            backend = factory()
        except ImportError as exc:
            raise UiBackendUnavailable(
                f"UI backend '{normalized}' is unavailable: {exc}"
            ) from exc
        if not isinstance(backend, UiBackend):
            raise UiBackendError(
                f"backend factory '{normalized}' did not return a UiBackend implementation"
            )
        if backend.api_version != BACKEND_API_VERSION:
            raise UiBackendError(
                f"backend '{normalized}' uses API version {backend.api_version}; "
                f"this SDK requires {BACKEND_API_VERSION}"
            )
        return backend

    def discover(self) -> None:
        """Load third-party factories from the glyph.ui_backends entry-point group once."""

        with self._lock:
            if self._discovered:
                return
            self._discovered = True
        try:
            selected = metadata.entry_points(group=BACKEND_ENTRY_POINT_GROUP)
        except TypeError:  # Python/importlib compatibility for older entry_points APIs.
            selected = metadata.entry_points().get(BACKEND_ENTRY_POINT_GROUP, ())
        for entry_point in selected:
            normalized = self._normalize_name(entry_point.name)

            def factory(ep: Any = entry_point) -> UiBackend:
                loaded = ep.load()
                candidate = loaded() if callable(loaded) and not isinstance(loaded, UiBackend) else loaded
                if callable(candidate) and not isinstance(candidate, UiBackend):
                    candidate = candidate()
                return candidate

            with self._lock:
                self._factories.setdefault(normalized, factory)

    def snapshot(self) -> Mapping[str, BackendFactory]:
        with self._lock:
            return dict(self._factories)


def _gradio_factory() -> UiBackend:
    try:
        from .gradio_backend import GradioBackend
    except ImportError as exc:
        raise ImportError(
            "install the optional UI dependencies with 'pip install glyph-rust[ui]'"
        ) from exc
    return GradioBackend()


def create_default_registry() -> BackendRegistry:
    registry = BackendRegistry()
    registry.register("gradio", _gradio_factory)
    return registry


_default_registry: BackendRegistry | None = None
_default_registry_lock = threading.Lock()


def default_backend_registry() -> BackendRegistry:
    global _default_registry
    with _default_registry_lock:
        if _default_registry is None:
            _default_registry = create_default_registry()
        return _default_registry
