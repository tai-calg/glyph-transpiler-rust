from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from glyph import compile_outputs  # noqa: E402
from glyph.compliance import build_compliance_report  # noqa: E402
from glyph.schema import (  # noqa: E402
    GLYPH04_PUBLIC_SCHEMAS,
    IR_SCHEMA_VERSION,
    STABILIZATION_REPORT_SCHEMA,
)


_FROZEN_TOP_LEVEL_KEYS: dict[str, frozenset[str]] = {
    "capability-ir.json": frozenset(
        {"schema", "version", "resources", "functions", "aggregates", "operations"}
    ),
    "resource-flow-ir.json": frozenset({"schema", "version", "transitions"}),
    "contracts-ir.json": frozenset(
        {"schema", "version", "declarations", "applications"}
    ),
    "runtime-contract-ir.json": frozenset(
        {
            "schema",
            "version",
            "worlds",
            "protocols",
            "handlers",
            "laws",
            "rows",
            "applications",
        }
    ),
    "verification-report.json": frozenset(
        {"schema", "version", "summary", "items"}
    ),
}


def _check_public_schemas(files: dict[str, str]) -> tuple[list[dict[str, object]], list[str]]:
    results: list[dict[str, object]] = []
    errors: list[str] = []
    for filename, (schema, version) in GLYPH04_PUBLIC_SCHEMAS.items():
        text = files.get(filename)
        if text is None:
            errors.append(f"missing Glyph 0.4 artifact: {filename}")
            continue
        payload = json.loads(text)
        actual_schema = payload.get("schema")
        actual_version = payload.get("version")
        actual_keys = frozenset(payload)
        expected_keys = _FROZEN_TOP_LEVEL_KEYS[filename]
        result = {
            "file": filename,
            "schema": actual_schema,
            "version": actual_version,
            "top_level_keys": sorted(actual_keys),
        }
        results.append(result)
        if actual_schema != schema:
            errors.append(
                f"{filename}: schema changed from {schema!r} to {actual_schema!r}"
            )
        if actual_version != version:
            errors.append(
                f"{filename}: version changed from {version} to {actual_version!r}"
            )
        if actual_keys != expected_keys:
            errors.append(
                f"{filename}: top-level shape changed; expected {sorted(expected_keys)}, "
                f"got {sorted(actual_keys)}"
            )
    return results, errors


def _check_release_metadata(root: Path) -> tuple[dict[str, object], list[str]]:
    errors: list[str] = []
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    package_version = project["project"]["version"]
    if version != "0.4.0":
        errors.append(f"VERSION must be 0.4.0, got {version!r}")
    if package_version != version:
        errors.append(
            f"pyproject version {package_version!r} does not match VERSION {version!r}"
        )

    documents = ("README.md", "LANGUAGE.md", "CONTRACTS.md", "IMPLEMENTATION_STATUS.md")
    document_status: dict[str, bool] = {}
    for relative in documents:
        text = (root / relative).read_text(encoding="utf-8")
        present = "Glyph 0.4" in text or "Glyph Language 0.4" in text
        document_status[relative] = present
        if not present:
            errors.append(f"{relative} does not identify Glyph 0.4")

    return {
        "version": version,
        "package_version": package_version,
        "documents": document_status,
    }, errors


def _compile_acceptance(root: Path) -> tuple[dict[str, object], list[str]]:
    errors: list[str] = []
    source_path = root / "examples" / "acceptance" / "glyph04_system.glyph"
    source = source_path.read_text(encoding="utf-8")
    first = compile_outputs(source, source_path.name)
    second = compile_outputs(source, source_path.name)
    deterministic = (
        first.artifacts == second.artifacts
        and first.design_json == second.design_json
        and first.diagrams.files == second.diagrams.files
    )
    if not deterministic:
        errors.append("Glyph 0.4 complete example is not deterministic")

    schema_results, schema_errors = _check_public_schemas(first.diagrams.files)
    errors.extend(schema_errors)

    design = json.loads(first.design_json)
    for key in ("capabilities", "contracts", "runtime_contracts", "verification"):
        if key not in design:
            errors.append(f"typed design is missing Glyph 0.4 section {key!r}")

    rustc_ok = False
    with tempfile.TemporaryDirectory(prefix="glyph04-stabilization-") as directory:
        generated = Path(directory) / "generated.rs"
        library = Path(directory) / "libglyph04.rlib"
        generated.write_text(first.artifacts.logic, encoding="utf-8")
        result = subprocess.run(
            [
                "rustc",
                "--edition",
                "2021",
                "--crate-type",
                "lib",
                str(generated),
                "-o",
                str(library),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        rustc_ok = result.returncode == 0
        if not rustc_ok:
            errors.append("generated Glyph 0.4 Rust does not compile:\n" + result.stderr)

    return {
        "source": str(source_path.relative_to(root)),
        "deterministic": deterministic,
        "rustc": rustc_ok,
        "schemas": schema_results,
        "artifact_files": sorted(first.diagrams.files),
    }, errors


def build_stabilization_report(root: Path) -> dict[str, object]:
    compliance = build_compliance_report(root)
    release, release_errors = _check_release_metadata(root)
    acceptance, acceptance_errors = _compile_acceptance(root)
    errors = [*compliance.errors, *release_errors, *acceptance_errors]
    return {
        "schema": STABILIZATION_REPORT_SCHEMA,
        "version": IR_SCHEMA_VERSION,
        "status": "passed" if not errors else "failed",
        "compliance": compliance.to_dict(),
        "release": release,
        "acceptance": acceptance,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Glyph 0.4 stabilization gate")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "build" / "glyph04-stabilization.json",
    )
    args = parser.parse_args()

    report = build_stabilization_report(ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if report["status"] != "passed":
        for error in report["errors"]:
            print(f"glyph04-stabilization: {error}", file=sys.stderr)
        return 1
    print(
        f"Glyph 0.4 stabilization passed: "
        f"{report['compliance']['summary']['requirements']} requirements, "
        f"{len(report['acceptance']['schemas'])} frozen schemas"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
