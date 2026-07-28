from __future__ import annotations

from pathlib import Path
import re


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise RuntimeError(f"missing patch anchor in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_projection() -> None:
    path = Path("glyph/transition_action_projection.py")
    text = path.read_text(encoding="utf-8")
    old = """    TryExpr,
    TypeRef,
)
"""
    new = """    TryExpr,
    TypeRef,
    parse_expr,
)
"""
    if old not in text:
        raise RuntimeError("parse_expr import anchor missing")
    text = text.replace(old, new, 1)

    anchor = """def _warning(message: str, line: int) -> dict[str, object]:
"""
    helpers = """def _conditional_block_values(
    model: CompilationModel,
    function_name: str | None,
) -> tuple[tuple[int, str, Expr], ...]:
    if function_name is None:
        return ()
    block = next((item for item in model.blocks if item.name == function_name), None)
    if block is None:
        return ()
    values: list[tuple[int, str, Expr]] = []
    for binding in block.bindings:
        if binding.kind != "conditional":
            continue
        for offset, original in enumerate(binding.source.splitlines(), start=1):
            stripped = original.strip()
            arrow = stripped.find("=>")
            if arrow < 0:
                continue
            condition_text = stripped[:arrow].strip()
            value_text = stripped[arrow + 2 :].strip()
            if not value_text:
                continue
            try:
                value = parse_expr(value_text)
                condition = (
                    "otherwise"
                    if condition_text == "_"
                    else render_expr(parse_expr(condition_text))
                )
            except Exception:
                continue
            values.append((binding.line + offset, condition, value))
    return tuple(values)


def _block_value_for_transition(
    values: Sequence[tuple[int, str, Expr]],
    transition: Mapping[str, object],
) -> Expr | None:
    source = transition.get("source", {})
    line = int(source.get("line", 0)) if isinstance(source, Mapping) else 0
    raw = str(transition.get("condition_raw") or transition.get("condition") or "")
    condition = "otherwise" if raw in {"", "otherwise", "next"} else raw
    exact = [
        value
        for candidate_line, candidate_condition, value in values
        if candidate_line == line and candidate_condition == condition
    ]
    if exact:
        return exact[0]
    matching = [
        value
        for _, candidate_condition, value in values
        if candidate_condition == condition
    ]
    return matching[0] if len(matching) == 1 else None


"""
    if anchor not in text:
        raise RuntimeError("block helper insertion anchor missing")
    text = text.replace(anchor, helpers + anchor, 1)

    old = """    branches = (
        _root_branches(
            next_name,
            functions=functions,
            state_decl=state_decl,
            selector_index=selector_index,
            variants={item.name for item in selector_sum.variants},
            root_state_param=machine.state_param.name,
        )
        if next_name is not None
        else ()
    )

    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
"""
    new = """    branches = (
        _root_branches(
            next_name,
            functions=functions,
            state_decl=state_decl,
            selector_index=selector_index,
            variants={item.name for item in selector_sum.variants},
            root_state_param=machine.state_param.name,
        )
        if next_name is not None
        else ()
    )
    block_values = _conditional_block_values(model, next_name)

    diagnostics = [dict(item) for item in result.get("diagnostics", [])]
"""
    if old not in text:
        raise RuntimeError("block values initialization anchor missing")
    text = text.replace(old, new, 1)

    old = """        branch = _branch_for_transition(branches, transition)
        branch_value = getattr(branch, "value", None) if branch is not None else None
        source = transition.get("source", {})
"""
    new = """        branch = _branch_for_transition(branches, transition)
        branch_value = getattr(branch, "value", None) if branch is not None else None
        if branch_value is None:
            branch_value = _block_value_for_transition(block_values, transition)
        source = transition.get("source", {})
"""
    if old not in text:
        raise RuntimeError("branch fallback anchor missing")
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


def patch_consumers() -> None:
    roles = "glyph/transition_condition_roles.py"
    replace_once(roles, "STATE_TRANSITION_IR_VERSION = 3\n", "STATE_TRANSITION_IR_VERSION = 4\n")
    replace_once(
        roles,
        "def _display_label(\n",
        "def _action_display(action: object) -> str:\n"
        "    if isinstance(action, Mapping):\n"
        "        return str(action.get(\"display\") or action.get(\"expression\") or \"\")\n"
        "    return \"\" if action is None else str(action)\n\n\n"
        "def _display_label(\n",
    )
    replace_once(roles, "    action: str | None,\n", "    action: object,\n")
    replace_once(roles, "    label = \"\"\n", "    label = \"\"\n    action_text = _action_display(action)\n")
    replace_once(
        roles,
        "    if action:\n        label += f\" / {action}\" if label else f\"/ {action}\"\n",
        "    if action_text:\n        label += f\" / {action_text}\" if label else f\"/ {action_text}\"\n",
    )

    renderer = "glyph/state_transition_ir_renderer.py"
    replace_once(
        renderer,
        "  function actionOf(transition) {\n"
        "    const action = text(transition?.action) || \"—\";\n"
        "    const failure = text(transition?.failure_type);\n"
        "    return failure ? `${action} | ${failure}` : action;\n"
        "  }\n",
        "  function actionOf(transition) {\n"
        "    const raw = transition?.action;\n"
        "    const action = typeof raw === \"string\"\n"
        "      ? text(raw)\n"
        "      : text(raw?.display) || text(raw?.expression);\n"
        "    const failure = text(transition?.failure_type);\n"
        "    if (action && failure) return `${action} | ${failure}`;\n"
        "    return action || (failure ? `| ${failure}` : \"—\");\n"
        "  }\n",
    )
    replace_once(
        renderer,
        '        transition.action ?? "",\n',
        '        JSON.stringify(transition.action ?? null),\n',
    )
    replace_once(
        renderer,
        '    """Render v3 trigger/guard/effect roles without reclassifying compiler semantics."""\n',
        '    """Render trigger/guard/Action roles without reclassifying compiler semantics."""\n',
    )


def patch_semantic_tests() -> None:
    path = Path("tests/test_transition_semantics.py")
    text = path.read_text(encoding="utf-8")
    text = text.replace("def assert_v3", "def assert_v4")
    text = text.replace("self.assert_v3", "self.assert_v4")
    text = text.replace(
        '{"schema": "glyph.state-transition-ir", "version": 3}',
        '{"schema": "glyph.state-transition-ir", "version": 4}',
    )
    text = text.replace(
        'self.assertEqual(machine["transition_ir"]["version"], 3)',
        'self.assertEqual(machine["transition_ir"]["version"], 4)',
    )
    text = text.replace(
        'self.assertEqual(machine["analysis"]["transition_ir_version"], 3)',
        'self.assertEqual(machine["analysis"]["transition_ir_version"], 4)',
    )
    text = text.replace(
        '                "action",\n                "failure_type",',
        '                "action",\n                "effect_invocations",\n                "failure_type",',
    )

    text = text.replace(
        '        self.assertEqual(normal["action"], "write_pump(true)")\n',
        '        self.assertIsNone(normal["action"])\n'
        '        self.assertEqual(\n'
        '            [item["expression"] for item in normal["effect_invocations"]],\n'
        '            ["write_pump(true)"],\n'
        '        )\n',
        1,
    )
    text = text.replace(
        '        self.assertEqual(normal["display_label"], "PumpStart / write_pump(true)")\n',
        '        self.assertEqual(normal["display_label"], "PumpStart")\n',
        1,
    )
    text = text.replace(
        '        self.assertEqual(failure["action"], "write_pump(true)")\n',
        '        self.assertIsNone(failure["action"])\n'
        '        self.assertEqual(\n'
        '            [item["expression"] for item in failure["effect_invocations"]],\n'
        '            ["write_pump(true)"],\n'
        '        )\n',
        1,
    )
    text, count = re.subn(
        r'        self\.assertEqual\(\s*failure\["display_label"\],\s*"PumpStart / write_pump\(true\) \| WriteError",\s*\)\n',
        '        self.assertEqual(failure["display_label"], "PumpStart | WriteError")\n',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("pump failure display assertion missing")

    text = text.replace(
        '        self.assertEqual(start["action"], "set_conveyor(input.speed)")\n',
        '        self.assertIsNone(start["action"])\n'
        '        self.assertEqual(\n'
        '            [item["expression"] for item in start["effect_invocations"]],\n'
        '            ["set_conveyor(input.speed)"],\n'
        '        )\n',
        1,
    )
    text, count = re.subn(
        r'        self\.assertEqual\(\s*start\["display_label"\],\s*"ConveyorStart \[input\.clear\] / set_conveyor\(input\.speed\)",\s*\)\n',
        '        self.assertEqual(start["display_label"], "ConveyorStart [input.clear]")\n',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("conveyor display assertion missing")
    text = text.replace(
        '        self.assertEqual(failure["action"], "set_conveyor(input.speed)")\n',
        '        self.assertIsNone(failure["action"])\n'
        '        self.assertEqual(\n'
        '            [item["expression"] for item in failure["effect_invocations"]],\n'
        '            ["set_conveyor(input.speed)"],\n'
        '        )\n',
        1,
    )

    text = text.replace(
        '        self.assertEqual(opened["action"], "write_valve(true)")\n',
        '        self.assertIsNone(opened["action"])\n'
        '        self.assertEqual(\n'
        '            [item["expression"] for item in opened["effect_invocations"]],\n'
        '            ["write_valve(true)"],\n'
        '        )\n',
        1,
    )
    text, count = re.subn(
        r'        self\.assertEqual\(\s*opened\["display_label"\],\s*"ValveOpenRequest / write_valve\(true\)",\s*\)\n',
        '        self.assertEqual(opened["display_label"], "ValveOpenRequest")\n',
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("valve display assertion missing")
    text = text.replace(
        '        self.assertEqual(failure["action"], "write_valve(true)")\n',
        '        self.assertIsNone(failure["action"])\n'
        '        self.assertEqual(\n'
        '            [item["expression"] for item in failure["effect_invocations"]],\n'
        '            ["write_valve(true)"],\n'
        '        )\n',
        1,
    )
    text = text.replace(
        '            and item.get("action") == "write_fan(0.0)"\n',
        '            and any(\n'
        '                effect.get("expression") == "write_fan(0.0)"\n'
        '                for effect in item.get("effect_invocations", [])\n'
        '            )\n',
        1,
    )
    text = text.replace(
        '        self.assertEqual(alarm["event"], "RaiseAlarm")\n',
        '        self.assertEqual(alarm["event"], "RaiseAlarm")\n'
        '        self.assertEqual(alarm["target_state"], "Alarmed")\n'
        '        self.assertEqual(alarm["action"]["display"], "RaiseAlarm")\n'
        '        self.assertEqual(alarm["action"]["provenance"], "machine-action-projection")\n'
        '        self.assertNotEqual(alarm["action"]["display"], alarm["target_state"])\n'
        '        self.assertEqual(alarm["effect_invocations"], [])\n',
        1,
    )
    path.write_text(text, encoding="utf-8")

    path = Path("tests/test_nested_transition_repair.py")
    text = path.read_text(encoding="utf-8").replace(
        '                and transition.get("action") == "write_valve(true)"\n',
        '                and any(\n'
        '                    effect.get("expression") == "write_valve(true)"\n'
        '                    for effect in transition.get("effect_invocations", [])\n'
        '                )\n',
        1,
    )
    path.write_text(text, encoding="utf-8")

    path = Path("tests/test_guard_distinct_failure_repair.py")
    text = path.read_text(encoding="utf-8").replace(
        '            and transition.get("action") == "write_fan(0.0)"\n',
        '            and any(\n'
        '                effect.get("expression") == "write_fan(0.0)"\n'
        '                for effect in transition.get("effect_invocations", [])\n'
        '            )\n',
        1,
    )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_projection()
    patch_consumers()
    patch_semantic_tests()


if __name__ == "__main__":
    main()
