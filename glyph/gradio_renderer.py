from __future__ import annotations

from dataclasses import dataclass
from html import escape
import json
from typing import Any

import gradio as gr
import pandas as pd

from .pure_runtime import (
    LivePureGlyphRuntime,
    OptionValue,
    PureRuntimeError,
    ResultValue,
    VariantValue,
)
from .ui_ir import UiAction, UiApplication, UiNode


GENERIC_GRADIO_CSS = r"""
.gradio-container {
  max-width: 1420px !important;
  margin: 0 auto !important;
  padding: 22px 22px 72px !important;
}
body {
  background:
    radial-gradient(circle at 8% 4%, rgba(37,99,235,.16), transparent 30%),
    radial-gradient(circle at 92% 10%, rgba(13,148,136,.13), transparent 28%),
    var(--body-background-fill);
}
#glyph-auto-hero {
  position: relative;
  overflow: hidden;
  margin-bottom: 22px;
  padding: clamp(30px, 5vw, 58px);
  border: 1px solid rgba(255,255,255,.14);
  border-radius: 30px;
  background:
    radial-gradient(circle at 82% 16%, rgba(45,212,191,.25), transparent 28%),
    linear-gradient(135deg, #071426 0%, #173b69 60%, #0f766e 150%);
  color: #f8fafc;
  box-shadow: 0 30px 90px rgba(15,23,42,.28);
}
#glyph-auto-hero::after {
  content: "";
  position: absolute;
  width: 340px;
  height: 340px;
  right: -120px;
  top: -190px;
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 50%;
}
.auto-kicker {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 7px 12px;
  border: 1px solid rgba(255,255,255,.17);
  border-radius: 999px;
  background: rgba(255,255,255,.08);
  color: rgba(255,255,255,.84);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .14em;
}
.auto-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #5eead4;
  box-shadow: 0 0 16px rgba(94,234,212,.95);
}
#glyph-auto-hero h1 {
  max-width: 900px;
  margin: 19px 0 12px;
  font-size: clamp(36px, 6vw, 70px);
  line-height: .98;
  letter-spacing: -.05em;
}
#glyph-auto-hero p {
  max-width: 800px;
  margin: 0;
  color: rgba(248,250,252,.69);
  font-size: 16px;
  line-height: 1.75;
}
.auto-panel {
  padding: 22px !important;
  border: 1px solid var(--border-color-primary) !important;
  border-radius: 24px !important;
  background: color-mix(in srgb, var(--block-background-fill) 95%, transparent) !important;
  box-shadow: 0 18px 55px rgba(15,23,42,.08);
}
.auto-panel-title {
  margin-bottom: 4px;
  font-size: 22px;
  font-weight: 780;
  letter-spacing: -.025em;
}
.auto-panel-description {
  margin-bottom: 18px;
  color: var(--body-text-color-subdued);
  font-size: 13px;
  line-height: 1.65;
}
#glyph-auto-run {
  min-height: 58px !important;
  margin-top: 10px;
  border-radius: 17px !important;
  font-size: 16px !important;
  font-weight: 780 !important;
  box-shadow: 0 13px 30px rgba(37,99,235,.24);
}
.auto-result {
  min-height: 330px;
  padding: 28px;
  border: 1px solid rgba(255,255,255,.13);
  border-radius: 26px;
  background:
    radial-gradient(circle at 85% 12%, rgba(45,212,191,.24), transparent 29%),
    linear-gradient(145deg, #071426, #173153);
  color: #f8fafc;
  box-shadow: 0 24px 72px rgba(15,23,42,.25);
}
.auto-result.error {
  background:
    radial-gradient(circle at 85% 12%, rgba(244,63,94,.30), transparent 29%),
    linear-gradient(145deg, #1c1018, #881337);
}
.auto-result-kicker {
  color: rgba(248,250,252,.54);
  font-size: 10px;
  font-weight: 850;
  letter-spacing: .16em;
}
.auto-result h2 {
  margin: 8px 0 22px;
  font-size: 30px;
  letter-spacing: -.035em;
}
.auto-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
}
.auto-card {
  padding: 16px;
  border: 1px solid rgba(255,255,255,.11);
  border-radius: 17px;
  background: rgba(255,255,255,.06);
}
.auto-card-label {
  margin-bottom: 8px;
  color: rgba(248,250,252,.55);
  font-size: 11px;
}
.auto-card-value {
  overflow-wrap: anywhere;
  font-size: 22px;
  font-weight: 740;
}
.auto-card-value.compact {
  font-size: 15px;
  font-weight: 620;
  line-height: 1.55;
}
.auto-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border: 1px solid rgba(255,255,255,.15);
  border-radius: 999px;
  background: rgba(255,255,255,.08);
  font-size: 13px;
  font-weight: 760;
}
.auto-badge::before {
  content: "";
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #5eead4;
  box-shadow: 0 0 13px rgba(94,234,212,.8);
}
.auto-subsection {
  margin-top: 16px;
  padding: 16px;
  border: 1px solid rgba(255,255,255,.10);
  border-radius: 18px;
  background: rgba(2,6,23,.18);
}
.auto-subsection-title {
  margin-bottom: 12px;
  color: rgba(248,250,252,.66);
  font-size: 12px;
  font-weight: 780;
  letter-spacing: .06em;
  text-transform: uppercase;
}
.auto-pre {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: rgba(248,250,252,.82);
  font: 12px/1.6 ui-monospace, SFMono-Regular, Menlo, monospace;
}
.auto-runtime {
  display: grid;
  grid-template-columns: auto minmax(0,1fr) auto;
  gap: 16px;
  align-items: center;
  padding: 19px 22px;
  border: 1px solid var(--border-color-primary);
  border-radius: 21px;
  background: var(--block-background-fill);
}
.auto-runtime-mark {
  display: grid;
  width: 50px;
  height: 50px;
  place-items: center;
  border-radius: 15px;
  background: linear-gradient(135deg, #2563eb, #0d9488);
  color: white;
  font-size: 21px;
  font-weight: 850;
}
.auto-runtime-title { font-size: 19px; font-weight: 760; }
.auto-runtime-detail { color: var(--body-text-color-subdued); font-size: 11px; }
.auto-runtime-warning {
  grid-column: 1 / -1;
  padding: 11px 13px;
  border-radius: 12px;
  background: color-mix(in srgb, #f59e0b 13%, transparent);
  font-size: 12px;
}
.auto-runtime-error { background: color-mix(in srgb, #ef4444 14%, transparent); }
@media (max-width: 760px) {
  .gradio-container { padding: 12px 12px 48px !important; }
  #glyph-auto-hero { border-radius: 23px; }
  .auto-runtime { grid-template-columns: auto 1fr; }
}
"""


class UiBindingError(ValueError):
    """Raised when a browser value cannot be reconstructed as a Glyph argument."""


@dataclass(frozen=True)
class InputBinding:
    node: UiNode
    component: Any


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def empty_history() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["invocation", "world", "action", "summary"]
    )


def _initial_result(app: UiApplication) -> str:
    return f"""
    <div class="auto-result">
      <div class="auto-result-kicker">GLYPH AUTO UI</div>
      <h2>{escape(app.action.label)}</h2>
      <div class="auto-card"><div class="auto-card-label">Ready</div><div class="auto-card-value compact">型付き入力フォームは <code>{escape(app.action.name)}</code> のシグネチャから生成されています。</div></div>
    </div>
    """


def runtime_html(runtime: LivePureGlyphRuntime) -> str:
    state = runtime.state_dict()
    active = state.get("active_world")
    pending = state.get("pending_patch")
    runtime_state = state.get("runtime")
    last_error = runtime_state.get("last_error") if isinstance(runtime_state, dict) else None
    if not isinstance(active, dict):
        return '<div class="auto-runtime"><div class="auto-runtime-mark">G</div><div><div class="auto-runtime-title">No active World</div></div></div>'
    version = int(active.get("version", 0))
    code_digest = str(active.get("code_digest") or "")[:12]
    definitions = len(active.get("definitions") or [])
    warnings = ""
    if isinstance(pending, dict):
        safety = escape(str(pending.get("maximum_safety") or "pending"))
        blockers = ", ".join(str(item) for item in pending.get("blockers") or [])
        warnings += (
            '<div class="auto-runtime-warning"><strong>Pending patch:</strong> '
            + safety
            + (" · " + escape(blockers) if blockers else "")
            + "</div>"
        )
    if last_error:
        warnings += (
            '<div class="auto-runtime-warning auto-runtime-error"><strong>Source error:</strong> '
            + escape(str(last_error))
            + " · 最後の有効Worldを継続しています。</div>"
        )
    return f"""
    <div class="auto-runtime">
      <div class="auto-runtime-mark">G</div>
      <div><div class="auto-result-kicker">GLYPH LIVE IMAGE</div><div class="auto-runtime-title">Active World {version}</div><div class="auto-runtime-detail">{definitions} definitions · code {escape(code_digest)}</div></div>
      <div class="auto-badge">Ready</div>
      {warnings}
    </div>
    """


def _create_input(node: UiNode, bindings: list[InputBinding]) -> None:
    label = f"{node.label} · {node.type_name}"
    if node.kind == "object":
        with gr.Accordion(label, open=True):
            for child in node.children:
                _create_input(child, bindings)
        return
    if node.kind == "number":
        component = gr.Number(value=node.default, label=label)
    elif node.kind == "integer":
        component = gr.Number(value=node.default, label=label, precision=0)
    elif node.kind == "checkbox":
        component = gr.Checkbox(value=bool(node.default), label=label)
    elif node.kind == "text":
        component = gr.Textbox(value=str(node.default or ""), label=label)
    elif node.kind == "select":
        component = gr.Dropdown(
            choices=list(node.choices),
            value=node.default,
            label=label,
        )
    elif node.kind == "unit":
        component = gr.State(None)
    else:
        component = gr.JSON(value=node.default, label=label)
    bindings.append(InputBinding(node, component))


def _decode_variant(node: UiNode, raw: Any) -> VariantValue:
    if node.kind == "select":
        variant = str(raw)
        if variant not in node.choices:
            raise UiBindingError(
                f"{node.label}: variant '{variant}' is not one of {', '.join(node.choices)}"
            )
        return VariantValue(node.type_name, variant)
    if not isinstance(raw, dict):
        raise UiBindingError(
            f"{node.label}: payload sum input requires a JSON object"
        )
    variant = str(raw.get("variant") or "")
    if variant not in node.choices:
        raise UiBindingError(
            f"{node.label}: JSON field 'variant' must be one of {', '.join(node.choices)}"
        )
    values = raw.get("values") or []
    fields = raw.get("fields") or {}
    if not isinstance(values, list) or not isinstance(fields, dict):
        raise UiBindingError(
            f"{node.label}: 'values' must be an array and 'fields' must be an object"
        )
    return VariantValue(
        node.type_name,
        variant,
        values=tuple(values),
        fields=tuple((str(name), value) for name, value in fields.items()),
    )


def _decode_input(node: UiNode, raw: Any) -> Any:
    if node.kind == "integer":
        if raw is None:
            raw = node.default
        number = float(raw)
        if not number.is_integer():
            raise UiBindingError(f"{node.label} requires an integer")
        return int(number)
    if node.kind == "number":
        if raw is None:
            raw = node.default
        return float(raw)
    if node.kind == "checkbox":
        return bool(raw)
    if node.kind == "text":
        return "" if raw is None else str(raw)
    if node.kind == "select" or node.choices:
        return _decode_variant(node, raw)
    if node.kind == "unit":
        return None
    if node.type_name.startswith(("Result<", "R<")):
        if not isinstance(raw, dict):
            raise UiBindingError(f"{node.label}: Result input requires JSON")
        status = str(raw.get("status") or "")
        if status not in {"ok", "error"}:
            raise UiBindingError(f"{node.label}: Result status must be 'ok' or 'error'")
        return ResultValue(status == "ok", raw.get("value"))
    if node.type_name.startswith(("Option<", "O<")):
        return OptionValue(False) if raw is None else OptionValue(True, raw)
    return raw


def _assign_path(arguments: dict[str, Any], path: tuple[str, ...], value: Any) -> None:
    if not path:
        raise UiBindingError("empty input path")
    cursor = arguments
    for segment in path[:-1]:
        existing = cursor.get(segment)
        if existing is None:
            nested: dict[str, Any] = {}
            cursor[segment] = nested
            cursor = nested
        elif isinstance(existing, dict):
            cursor = existing
        else:
            raise UiBindingError(f"input path collision at '{segment}'")
    cursor[path[-1]] = value


def build_arguments(bindings: list[InputBinding], raw_values: list[Any]) -> dict[str, Any]:
    if len(bindings) != len(raw_values):
        raise UiBindingError(
            f"UI supplied {len(raw_values)} values for {len(bindings)} bindings"
        )
    arguments: dict[str, Any] = {}
    for binding, raw in zip(bindings, raw_values):
        _assign_path(arguments, binding.node.path, _decode_input(binding.node, raw))
    return arguments


def _value_at(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return None


def _render_node(node: UiNode, value: Any) -> str:
    label = escape(node.label)
    if node.kind == "object":
        cards = "".join(
            _render_node(child, _value_at(value, child.path[-1]))
            for child in node.children
        )
        return f'<div class="auto-subsection"><div class="auto-subsection-title">{label}</div><div class="auto-grid">{cards}</div></div>'
    if node.kind == "badge":
        variant = value.get("variant") if isinstance(value, dict) else value
        return f'<div class="auto-card"><div class="auto-card-label">{label}</div><div class="auto-badge">{escape(str(variant))}</div></div>'
    if node.kind == "status":
        shown = "True" if value is True else "False"
        return f'<div class="auto-card"><div class="auto-card-label">{label}</div><div class="auto-badge">{shown}</div></div>'
    if node.kind in {"metric", "text", "unit"}:
        shown = "—" if value is None else str(value)
        compact = " compact" if node.kind == "text" or len(shown) > 18 else ""
        return f'<div class="auto-card"><div class="auto-card-label">{label}</div><div class="auto-card-value{compact}">{escape(shown)}</div></div>'
    if node.kind == "result" and isinstance(value, dict):
        status = str(value.get("status") or "unknown")
        child = node.children[0] if status == "ok" else node.children[1]
        return f'<div class="auto-subsection"><div class="auto-badge">{escape(status)}</div>{_render_node(child, value.get("value"))}</div>'
    if node.kind == "option":
        if value is None:
            return f'<div class="auto-card"><div class="auto-card-label">{label}</div><div class="auto-card-value">None</div></div>'
        child = node.children[0] if node.children else node
        return _render_node(child, value)
    if node.kind == "tuple" and isinstance(value, list):
        rendered = "".join(
            _render_node(child, item)
            for child, item in zip(node.children, value)
        )
        return f'<div class="auto-subsection"><div class="auto-subsection-title">{label}</div><div class="auto-grid">{rendered}</div></div>'
    return f'<div class="auto-subsection"><div class="auto-subsection-title">{label}</div><pre class="auto-pre">{escape(_json_text(value))}</pre></div>'


def render_result(app: UiApplication, payload: Any, world_version: int) -> str:
    content = _render_node(app.action.output, payload)
    return f"""
    <div class="auto-result">
      <div class="auto-result-kicker">GLYPH RESULT · WORLD {world_version}</div>
      <h2>{escape(app.action.label)}</h2>
      <div class="auto-grid">{content}</div>
    </div>
    """


def render_error(message: str) -> str:
    return f"""
    <div class="auto-result error">
      <div class="auto-result-kicker">INVOCATION ERROR</div>
      <h2>Glyph execution stopped</h2>
      <pre class="auto-pre">{escape(message)}</pre>
    </div>
    """


def _summary(payload: Any) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return text if len(text) <= 180 else text[:177] + "..."


def invoke_action(
    runtime: LivePureGlyphRuntime,
    app: UiApplication,
    bindings: list[InputBinding],
    raw_values: list[Any],
    session: dict[str, Any] | None,
) -> tuple[str, Any, pd.DataFrame, dict[str, Any], str, str]:
    current = dict(session or {})
    history = list(current.get("history") or [])
    invocation_count = int(current.get("count", 0))
    payload: Any = {}
    try:
        arguments = build_arguments(bindings, raw_values)
        result = runtime.invoke(app.action.name, arguments)
        payload = result.to_python()
        invocation_count += 1
        history.append(
            {
                "invocation": invocation_count,
                "world": result.world_version,
                "action": app.action.name,
                "summary": _summary(payload),
            }
        )
        history = history[-40:]
        result_html = render_result(app, payload, result.world_version)
    except (UiBindingError, PureRuntimeError, OSError, ValueError, TypeError) as exc:
        result_html = render_error(str(exc))
    next_session = {"count": invocation_count, "history": history}
    return (
        result_html,
        payload,
        pd.DataFrame(history, columns=empty_history().columns),
        next_session,
        runtime_html(runtime),
        runtime.source_text,
    )


def poll_runtime(runtime: LivePureGlyphRuntime) -> tuple[str, str]:
    try:
        runtime.refresh()
    except OSError:
        pass
    return runtime_html(runtime), runtime.source_text


def build_gradio_app(
    runtime: LivePureGlyphRuntime,
    app: UiApplication,
) -> gr.Blocks:
    with gr.Blocks(title=app.title) as demo:
        session = gr.State({"count": 0, "history": []})
        gr.HTML(
            f"""
            <section id="glyph-auto-hero">
              <div class="auto-kicker"><span class="auto-dot"></span>GLYPH UI IR → GRADIO</div>
              <h1>{escape(app.title)}</h1>
              <p><code>{escape(app.action.name)}</code> の型付きシグネチャから入力フォームと結果表示を生成しています。型だけで決められない装飾は推測せず、安全な既定widgetへ投影します。</p>
            </section>
            """
        )
        bindings: list[InputBinding] = []
        with gr.Row(equal_height=False):
            with gr.Column(scale=4, elem_classes=["auto-panel"]):
                gr.HTML(
                    '<div class="auto-panel-title">Inputs</div><div class="auto-panel-description">Glyphの引数型を再帰的に展開したフォームです。</div>'
                )
                for node in app.action.inputs:
                    _create_input(node, bindings)
                run = gr.Button(
                    f"Run {app.action.label}",
                    variant="primary",
                    elem_id="glyph-auto-run",
                )
                reset = gr.Button("Reset history")
            with gr.Column(scale=7):
                result_html = gr.HTML(_initial_result(app))
        world_status = gr.HTML(runtime_html(runtime))
        with gr.Row(equal_height=False):
            with gr.Column(scale=6, elem_classes=["auto-panel"]):
                result_json = gr.JSON(value={}, label="Structured result")
            with gr.Column(scale=6, elem_classes=["auto-panel"]):
                history = gr.Dataframe(
                    value=empty_history(),
                    interactive=False,
                    label="Invocation history",
                )
        with gr.Row(equal_height=False):
            with gr.Column(scale=7, elem_classes=["auto-panel"]):
                with gr.Accordion("Active Glyph source", open=True):
                    source_code = gr.Code(
                        value=runtime.source_text,
                        interactive=False,
                        label=app.source_name,
                    )
            with gr.Column(scale=5, elem_classes=["auto-panel"]):
                with gr.Accordion("Generated glyph.ui-ir", open=True):
                    gr.JSON(value=app.to_dict(), label="glyph.ui-ir v1")

        input_components = [binding.component for binding in bindings]

        def handle(*values: Any):
            raw_values = list(values[:-1])
            state = values[-1]
            return invoke_action(runtime, app, bindings, raw_values, state)

        run.click(
            fn=handle,
            inputs=[*input_components, session],
            outputs=[
                result_html,
                result_json,
                history,
                session,
                world_status,
                source_code,
            ],
            api_name=app.action.name,
        )
        reset.click(
            fn=lambda: (
                _initial_result(app),
                {},
                empty_history(),
                {"count": 0, "history": []},
                runtime_html(runtime),
                runtime.source_text,
            ),
            inputs=[],
            outputs=[
                result_html,
                result_json,
                history,
                session,
                world_status,
                source_code,
            ],
        )
        timer = gr.Timer(1.0)
        timer.tick(
            fn=lambda: poll_runtime(runtime),
            inputs=[],
            outputs=[world_status, source_code],
        )
    return demo
