from pathlib import Path


def replace_all(path: str, old: str, new: str, expected: int) -> None:
    file_path = Path(path)
    content = file_path.read_text(encoding="utf-8")
    count = content.count(old)
    if count != expected:
        raise SystemExit(f"{path}: expected {expected} matches for {old!r}, found {count}")
    file_path.write_text(content.replace(old, new), encoding="utf-8")


replace_all(
    "tests/verify_transition_layout_transaction.mjs",
    'assert.equal(current.workspaceVersion, 2, JSON.stringify(current));',
    'assert.equal(current.workspaceVersion, 3, JSON.stringify(current));',
    1,
)
replace_all(
    "tests/verify_transition_layout_transaction.mjs",
    'assert.equal(current.initialCertificate, "ordinary-follow", JSON.stringify(current));',
    'assert.equal(current.initialCertificate, "ordinary-obstacle-free", JSON.stringify(current));',
    1,
)
replace_all(
    "tests/verify_node_drag_layout.mjs",
    'current.workspaceVersion === 2',
    'current.workspaceVersion === 3',
    1,
)
replace_all(
    "tests/verify_node_drag_layout.mjs",
    'current.initialRouteCertificate === "ordinary-follow"',
    'current.initialRouteCertificate === "ordinary-obstacle-free"',
    1,
)

Path(__file__).unlink()
