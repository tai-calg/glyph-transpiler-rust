from __future__ import annotations

from enum import Enum


class VerificationClass(str, Enum):
    STATIC = "static"
    MODEL = "model"
    RUNTIME = "runtime"
    TRUSTED = "trusted"


VERIFICATION_CLASS_VALUES = frozenset(item.value for item in VerificationClass)


def split_verification_classes(
    value: str,
    *,
    default: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Parse, validate, and de-duplicate a `+`-separated class list."""

    parts = tuple(part for part in value.split("+") if part)
    if not parts:
        return default
    unknown = set(parts) - VERIFICATION_CLASS_VALUES
    if unknown:
        raise ValueError(
            "unknown verification classes: " + ", ".join(sorted(unknown))
        )
    return tuple(dict.fromkeys(parts))
