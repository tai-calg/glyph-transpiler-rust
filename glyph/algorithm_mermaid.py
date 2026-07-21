from __future__ import annotations

from .algorithm_ir import AlgorithmIR, AlgorithmSourceRef, AlgorithmValue


def _safe(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in text)


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "<br/>")


def _source_url(source_href: str, line: int) -> str:
    return f"{source_href}#L{line}"


def _node(
    lines: list[str],
    node_id: str,
    label: str,
    kind: str,
    source: AlgorithmSourceRef,
    source_href: str,
    source_name: str,
    *,
    shape: str = "box",
) -> None:
    escaped = _escape(f"{label} [L{source.line}]")
    if shape == "decision":
        lines.append(f'    {node_id}{{"{escaped}"}}')
    elif shape == "effect":
        lines.append(f'    {node_id}[/"{escaped}"/]')
    elif shape == "terminal":
        lines.append(f'    {node_id}(["{escaped}"])')
    else:
        lines.append(f'    {node_id}["{escaped}"]')
    lines.append(f"    class {node_id} {kind};")
    lines.append(
        f'    click {node_id} "{_source_url(source_href, source.line)}" '
        f'"Open {source_name}:{source.line}"'
    )


def _value_flow(
    lines: list[str],
    prefix: str,
    value: AlgorithmValue,
    current: str,
    target: str,
    source_href: str,
    source_name: str,
) -> None:
    if value.kind == "conditional":
        decision = f"{prefix}_decision"
        _node(
            lines,
            decision,
            "choose",
            "decision",
            value.source,
            source_href,
            source_name,
            shape="decision",
        )
        lines.append(f"    {current} --> {decision}")
        for index, branch in enumerate(value.branches):
            branch_id = f"{prefix}_branch_{index}"
            binders = f" · bind {', '.join(branch.binders)}" if branch.binders else ""
            _node(
                lines,
                branch_id,
                branch.value + binders,
                "branch",
                branch.source,
                source_href,
                source_name,
            )
            label = _escape("otherwise" if branch.condition == "_" else branch.condition)
            lines.append(f'    {decision} -->|"{label}"| {branch_id}')
            lines.append(f"    {branch_id} --> {target}")
        return

    if value.kind == "pipeline":
        input_id = f"{prefix}_input"
        input_label = value.input_text or value.source_text
        if value.input_type:
            input_label += f" : {value.input_type}"
        _node(
            lines,
            input_id,
            input_label,
            "value",
            value.source,
            source_href,
            source_name,
        )
        lines.append(f"    {current} --> {input_id}")
        previous = input_id
        for index, stage in enumerate(value.stages):
            stage_id = f"{prefix}_stage_{index}"
            type_text = ""
            if stage.input_type or stage.output_type:
                type_text = f"<br/>{stage.input_type or '?'} → {stage.output_type or '?'}"
            shape = "effect" if stage.kind == "effect" else "box"
            _node(
                lines,
                stage_id,
                stage.label + type_text,
                stage.kind,
                stage.source,
                source_href,
                source_name,
                shape=shape,
            )
            lines.append(f"    {previous} --> {stage_id}")
            if stage.propagates:
                error_id = f"{stage_id}_error"
                _node(
                    lines,
                    error_id,
                    "Err",
                    "error",
                    stage.source,
                    source_href,
                    source_name,
                    shape="terminal",
                )
                lines.append(f'    {stage_id} -->|"Err"| {error_id}')
            previous = stage_id
        lines.append(f"    {previous} --> {target}")
        return

    expression = f"{prefix}_expression"
    _node(
        lines,
        expression,
        value.source_text,
        "value",
        value.source,
        source_href,
        source_name,
    )
    lines.append(f"    {current} --> {expression}")
    lines.append(f"    {expression} --> {target}")


def render_algorithm_mermaid(ir: AlgorithmIR, source_href: str) -> str:
    lines = [
        "flowchart TD",
        "  classDef function fill:#eef,stroke:#446;",
        "  classDef binding fill:#e8f4ff,stroke:#357;",
        "  classDef decision fill:#ffd,stroke:#884;",
        "  classDef branch fill:#fff8d8,stroke:#997;",
        "  classDef value fill:#f7f7f7,stroke:#777;",
        "  classDef lambda fill:#f2ebff,stroke:#7461a8;",
        "  classDef rust fill:#f4e5ff,stroke:#8050a0;",
        "  classDef effect fill:#fee,stroke:#844;",
        "  classDef error fill:#fdd,stroke:#a33;",
        "  classDef result fill:#efe,stroke:#484;",
    ]
    if not ir.functions:
        lines.append('  empty["No := algorithm blocks"]')
        return "\n".join(lines) + "\n"

    for function_index, function in enumerate(ir.functions):
        function_id = f"algorithm_{_safe(function.name)}_{function_index}"
        lines.append(f'  subgraph {function_id}["{_escape(function.name)}"]')
        entry = f"{function_id}_entry"
        _node(
            lines,
            entry,
            f"{function.name} → {function.return_type}",
            "function",
            function.source,
            source_href,
            ir.source_name,
        )
        current = entry
        for step_index, step in enumerate(function.steps):
            prefix = f"{function_id}_step_{step_index}"
            if step.kind == "binding":
                target = f"{prefix}_binding"
                _node(
                    lines,
                    target,
                    f"{step.name} : {step.type}",
                    "binding",
                    step.source,
                    source_href,
                    ir.source_name,
                )
            else:
                target = f"{prefix}_return"
                _node(
                    lines,
                    target,
                    f"return : {step.type}",
                    "result",
                    step.source,
                    source_href,
                    ir.source_name,
                    shape="terminal",
                )
            _value_flow(
                lines,
                prefix,
                step.value,
                current,
                target,
                source_href,
                ir.source_name,
            )
            current = target
        lines.append("  end")
    return "\n".join(lines) + "\n"


def algorithm_source_entries(ir: AlgorithmIR) -> list[tuple[int, str, str]]:
    entries: list[tuple[int, str, str]] = []
    for function in ir.functions:
        entries.append((function.source.line, "algorithm-function", function.name))
        for step in function.steps:
            item_id = step.name or "return"
            entries.append((step.source.line, f"algorithm-{step.kind}", item_id))
            for branch in step.value.branches:
                entries.append(
                    (branch.source.line, "algorithm-branch", branch.condition)
                )
            for stage in step.value.stages:
                entries.append(
                    (stage.source.line, f"algorithm-{stage.kind}", stage.label)
                )
    return entries
