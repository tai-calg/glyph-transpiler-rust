from __future__ import annotations

from .monoidal_ir import MonoidalIR, MonoidalSourceRef, TensorFactor


def _safe(text: str) -> str:
    value = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in text)
    return value or "node"


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "<br/>")


def _source_url(source_href: str, line: int) -> str:
    return f"{source_href}#L{line}"


def _factor_label(factor: TensorFactor) -> str:
    result = f"{factor.name}: {factor.type}"
    if factor.expression is not None:
        result += f"<br/>{factor.expression}"
    return result


def _click(
    lines: list[str],
    node_id: str,
    source: MonoidalSourceRef,
    source_href: str,
    source_name: str,
) -> None:
    lines.append(
        f'  click {node_id} "{_source_url(source_href, source.line)}" '
        f'"Open {source_name}:{source.line}"'
    )


def render_monoidal_mermaid(ir: MonoidalIR, source_href: str) -> str:
    lines = [
        "flowchart LR",
        "  classDef tensor fill:#eef4ff,stroke:#315a9b,stroke-width:2px;",
        "  classDef parallel fill:#f2ebff,stroke:#7450a8,stroke-width:2px;",
        "  classDef lane fill:#ffffff,stroke:#777;",
        "  classDef resource fill:#fff6df,stroke:#946f18;",
        "  classDef type fill:#edf8ef,stroke:#477a4d;",
        '  note["Parallel = structural independence, not a runtime scheduling promise"]',
        "  class note lane;",
    ]
    if not ir.tensors:
        lines.append('  empty["No product or resource tensor with two or more factors"]')
        return "\n".join(lines) + "\n"

    parallel_by_tensor = {item.tensor_id: item for item in ir.parallels}
    for tensor in ir.tensors:
        tensor_id = _safe(tensor.id)
        role = tensor.role.replace("_", " ")
        label = _escape(f"⊗ {tensor.label}<br/>{role} [L{tensor.source.line}]")
        lines.append(f'  {tensor_id}(("{label}"))')
        lines.append(
            f"  class {tensor_id} "
            + ("resource" if tensor.resource else "tensor")
            + ";"
        )
        _click(lines, tensor_id, tensor.source, source_href, ir.source_name)

        parallel = parallel_by_tensor.get(tensor.id)
        if parallel is not None:
            parallel_id = _safe(parallel.id)
            parallel_label = _escape(
                f"Parallel · {parallel.function}<br/>{parallel.semantics} [L{parallel.source.line}]"
            )
            lines.append(f'  {parallel_id}{{"{parallel_label}"}}')
            lines.append(f"  class {parallel_id} parallel;")
            _click(lines, parallel_id, parallel.source, source_href, ir.source_name)
            for lane in parallel.lanes:
                lane_id = f"{parallel_id}_lane_{lane.index}"
                calls = f"<br/>calls: {', '.join(lane.calls)}" if lane.calls else ""
                lane_label = _escape(
                    f"{lane.label}<br/>{lane.expression}{calls} [L{lane.source.line}]"
                )
                lines.append(f'  {lane_id}["{lane_label}"]')
                lines.append(f"  class {lane_id} lane;")
                lines.append(f"  {parallel_id} --> {lane_id} --> {tensor_id}")
                _click(lines, lane_id, lane.source, source_href, ir.source_name)
            continue

        for factor_index, factor in enumerate(tensor.factors):
            factor_id = f"{tensor_id}_factor_{factor_index}"
            factor_label = _escape(_factor_label(factor))
            lines.append(f'  {factor_id}["{factor_label}"]')
            lines.append(
                f"  class {factor_id} "
                + ("resource" if tensor.resource else "type")
                + ";"
            )
            lines.append(f"  {factor_id} --> {tensor_id}")
            _click(lines, factor_id, tensor.source, source_href, ir.source_name)

    return "\n".join(lines) + "\n"
