from __future__ import annotations

import re


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_OWNER_RE = re.compile(rf"^[*+]\s*(?P<name>{_IDENT})")
_FIELD_RE = re.compile(rf"(?P<name>{_IDENT})\s*:")


def bind_field_applications_for_semantics(source: str) -> str:
    """Bind indented field Contract applications to synthetic top-level places.

    The first Contract pass historically associated every application with the nearest
    top-level declaration. For a field application that made a product constructor appear
    to execute in the field World. Synthetic place declarations prevent that false
    cross-World call; the post-pass later refines them to `Product.field`.
    """

    lines = source.splitlines()
    output = list(lines)
    owner: str | None = None
    for index, original in enumerate(lines):
        code = original.split("#", 1)[0].rstrip()
        stripped = code.strip()
        if not stripped:
            continue
        if not code[:1].isspace():
            match = _OWNER_RE.match(stripped)
            owner = match.group("name") if match is not None else None
            continue
        if owner is None or "@{" not in code:
            continue
        prefix = code[: code.index("@{")]
        matches = list(_FIELD_RE.finditer(prefix))
        if not matches:
            continue
        field = matches[-1].group("name")
        application = code[code.index("@{") :]
        output[index] = f">__glyph_place_{owner}_{field}():() {application}"

    suffix = "\n" if source.endswith("\n") else ""
    return "\n".join(output) + suffix
