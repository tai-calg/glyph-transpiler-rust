from __future__ import annotations

import argparse
from html import escape
from pathlib import Path
import sys
from typing import Any

import gradio as gr
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from glyph.pure_runtime import LivePureGlyphRuntime, PureRuntimeError


DEFAULT_SOURCE = ROOT / "examples" / "gradio_temperature.glyph"

BAND_PRESENTATION: dict[str, tuple[str, str, str]] = {
    "Invalid": (
        "物理的に無効",
        "invalid",
        "Glyphが入力を有効範囲外と判定しました。直前の有効Worldは維持されます。",
    ),
    "Freezing": ("氷点下", "freezing", "凍結域です。低温環境として扱ってください。"),
    "Cold": ("低温", "cold", "冷涼な温度帯です。"),
    "Comfortable": ("快適", "comfortable", "Glyphが快適域として分類しました。"),
    "Warm": ("高め", "warm", "やや高い温度帯です。"),
    "Hot": ("高温", "hot", "高温域です。安全上の注意が必要です。"),
}

CSS = r"""
.gradio-container {
  max-width: 1440px !important;
  margin: 0 auto !important;
  padding: 22px 22px 72px !important;
}
body {
  background:
    radial-gradient(circle at 10% 4%, rgba(37, 99, 235, .16), transparent 30%),
    radial-gradient(circle at 92% 10%, rgba(13, 148, 136, .14), transparent 27%),
    var(--body-background-fill);
}
#glyph-hero {
  position: relative;
  overflow: hidden;
  margin-bottom: 22px;
  padding: clamp(30px, 5vw, 56px);
  border: 1px solid rgba(255,255,255,.14);
  border-radius: 30px;
  background:
    radial-gradient(circle at 84% 16%, rgba(45,212,191,.27), transparent 27%),
    linear-gradient(135deg, #071426 0%, #12345d 58%, #0f766e 150%);
  color: #f8fafc;
  box-shadow: 0 30px 90px rgba(15,23,42,.28);
}
#glyph-hero::after {
  content: "";
  position: absolute;
  width: 330px;
  height: 330px;
  right: -115px;
  top: -190px;
  border: 1px solid rgba(255,255,255,.12);
  border-radius: 50%;
}
.hero-kicker {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 7px 12px;
  border: 1px solid rgba(255,255,255,.17);
  border-radius: 999px;
  background: rgba(255,255,255,.08);
  color: rgba(255,255,255,.83);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .14em;
}
.hero-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #5eead4;
  box-shadow: 0 0 16px rgba(94,234,212,.95);
}
#glyph-hero h1 {
  margin: 20px 0 12px;
  font-size: clamp(40px, 6vw, 76px);
  line-height: .94;
  letter-spacing: -.055em;
}
#glyph-hero p {
  max-width: 760px;
  margin: 0;
  color: rgba(248,250,252,.68);
  font-size: 16px;
  line-height: 1.75;
}
.panel {
  padding: 22px !important;
  border: 1px solid var(--border-color-primary) !important;
  border-radius: 24px !important;
  background: var(--block-background-fill) !important;
  box-shadow: 0 18px 55px rgba(15,23,42,.08);
}
.panel-title {
  margin-bottom: 4px;
  font-size: 22px;
  font-weight: 780;
  letter-spacing: -.025em;
}
.panel-description {
  margin-bottom: 18px;
  color: var(--body-text-color-subdued);
  font-size: 13px;
  line-height: 1.6;
}
.preset-row button {
  min-height: 54px !important;
  border-radius: 15px !important;
  font-weight: 720 !important;
}
#convert-button {
  min-height: 58px !important;
  margin-top: 8px;
  border-radius: 17px !important;
  font-size: 16px !important;
  font-weight: 780 !important;
  box-shadow: 0 13px 30px rgba(37,99,235,.24);
}
#result-card { min-height: 470px; }
.result-card {
  min-height: 430px;
  padding: 30px;
  border: 1px solid rgba(255,255,255,.13);
  border-radius: 28px;
  background:
    radial-gradient(circle at 84% 13%, rgba(96,165,250,.26), transparent 28%),
    linear-gradient(145deg, #071426, #12243f);
  color: #f8fafc;
  box-shadow: 0 24px 72px rgba(15,23,42,.27);
}
.result-card.comfortable {
  background:
    radial-gradient(circle at 84% 13%, rgba(45,212,191,.30), transparent 29%),
    linear-gradient(145deg, #071a22, #115e59);
}
.result-card.freezing, .result-card.cold {
  background:
    radial-gradient(circle at 84% 13%, rgba(56,189,248,.31), transparent 29%),
    linear-gradient(145deg, #071426, #075985);
}
.result-card.warm, .result-card.hot {
  background:
    radial-gradient(circle at 84% 13%, rgba(251,146,60,.34), transparent 29%),
    linear-gradient(145deg, #1c1510, #9a3412);
}
.result-card.invalid {
  background:
    radial-gradient(circle at 84% 13%, rgba(244,63,94,.34), transparent 29%),
    linear-gradient(145deg, #1c1018, #881337);
}
.result-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
}
.eyebrow {
  color: rgba(248,250,252,.53);
  font-size: 10px;
  font-weight: 850;
  letter-spacing: .16em;
}
.main-number {
  margin-top: 8px;
  font-size: clamp(64px, 8vw, 100px);
  font-weight: 800;
  line-height: .91;
  letter-spacing: -.07em;
}
.main-number span {
  margin-left: 8px;
  color: rgba(248,250,252,.58);
  font-size: 24px;
  font-weight: 600;
  letter-spacing: -.02em;
}
.band-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 13px;
  border: 1px solid rgba(255,255,255,.16);
  border-radius: 999px;
  background: rgba(255,255,255,.08);
  font-size: 12px;
  font-weight: 760;
}
.band-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #f8fafc;
  box-shadow: 0 0 14px rgba(248,250,252,.7);
}
.result-body {
  display: grid;
  grid-template-columns: minmax(0,1fr) 88px;
  gap: 24px;
  align-items: end;
  margin-top: 36px;
}
.metrics {
  display: grid;
  grid-template-columns: repeat(3,minmax(0,1fr));
  gap: 11px;
}
.metric {
  padding: 16px;
  border: 1px solid rgba(255,255,255,.11);
  border-radius: 17px;
  background: rgba(255,255,255,.055);
}
.metric-label {
  margin-bottom: 8px;
  color: rgba(248,250,252,.52);
  font-size: 11px;
}
.metric-value { font-size: 23px; font-weight: 750; }
.metric-value small {
  margin-left: 3px;
  color: rgba(248,250,252,.55);
  font-size: 12px;
}
.thermometer {
  position: relative;
  width: 42px;
  height: 190px;
  margin: 0 auto 14px;
  border: 4px solid rgba(255,255,255,.22);
  border-radius: 24px 24px 18px 18px;
  background: rgba(2,6,23,.32);
}
.thermometer::after {
  content: "";
  position: absolute;
  left: 50%;
  bottom: -18px;
  width: 62px;
  height: 62px;
  transform: translateX(-50%);
  border: 4px solid rgba(255,255,255,.22);
  border-radius: 50%;
  background: #fb7185;
  box-shadow: inset 0 0 0 9px rgba(2,6,23,.22);
}
.thermometer-fill {
  position: absolute;
  left: 8px;
  right: 8px;
  bottom: 8px;
  height: var(--gauge);
  max-height: calc(100% - 16px);
  border-radius: 999px;
  background: linear-gradient(to top,#fb7185,#fbbf24);
  transition: height .35s ease;
}
.message {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-top: 16px;
  padding: 14px 16px;
  border-radius: 16px;
  background: rgba(255,255,255,.07);
}
.message-mark {
  display: grid;
  width: 30px;
  height: 30px;
  flex: 0 0 30px;
  place-items: center;
  border-radius: 50%;
  background: rgba(255,255,255,.12);
  font-weight: 800;
}
.message p {
  margin: 3px 0 0;
  color: rgba(248,250,252,.60);
  font-size: 12px;
}
.empty-result {
  display: grid;
  min-height: 430px;
  place-items: center;
  align-content: center;
  padding: 30px;
  border: 1px dashed var(--border-color-primary);
  border-radius: 28px;
  background: var(--block-background-fill);
  text-align: center;
}
.empty-orbit {
  display: grid;
  width: 92px;
  height: 92px;
  place-items: center;
  border-radius: 50%;
  background: linear-gradient(135deg,rgba(59,130,246,.18),rgba(20,184,166,.18));
  font-size: 36px;
}
.empty-result h2 { margin: 19px 0 7px; font-size: 23px; }
.empty-result p {
  max-width: 390px;
  margin: 0;
  color: var(--body-text-color-subdued);
  line-height: 1.65;
}
.runtime-card {
  display: grid;
  grid-template-columns: auto minmax(0,1fr) auto;
  gap: 17px;
  align-items: center;
  margin: 18px 0;
  padding: 19px 21px;
  border: 1px solid var(--border-color-primary);
  border-radius: 21px;
  background: var(--block-background-fill);
  box-shadow: 0 15px 45px rgba(15,23,42,.07);
}
.runtime-mark {
  display: grid;
  width: 52px;
  height: 52px;
  place-items: center;
  border-radius: 15px;
  background: linear-gradient(135deg,#2563eb,#0f766e);
  color: white;
  font-size: 22px;
  font-weight: 850;
}
.runtime-kicker {
  color: var(--body-text-color-subdued);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: .14em;
}
.runtime-title { margin-top: 3px; font-size: 19px; font-weight: 780; }
.runtime-detail { color: var(--body-text-color-subdued); font-size: 12px; }
.runtime-stats { display: flex; gap: 24px; text-align: right; }
.runtime-stat { display: flex; flex-direction: column; }
.runtime-stat strong { font-size: 16px; }
.runtime-stat span {
  color: var(--body-text-color-subdued);
  font-size: 9px;
  font-weight: 750;
  letter-spacing: .10em;
  text-transform: uppercase;
}
.runtime-warning {
  grid-column: 1/-1;
  padding: 11px 13px;
  border-radius: 13px;
  background: rgba(245,158,11,.12);
  color: #b45309;
  font-size: 12px;
}
.runtime-error { background: rgba(244,63,94,.11); color: #be123c; }
@media (max-width: 780px) {
  .gradio-container { padding: 12px 12px 52px !important; }
  #glyph-hero { padding: 29px 23px; border-radius: 23px; }
  .result-head { flex-direction: column; }
  .result-body { grid-template-columns: 1fr; }
  .metrics { grid-template-columns: 1fr; }
  .thermometer { display: none; }
  .runtime-card { grid-template-columns: auto 1fr; }
  .runtime-stats { grid-column: 1/-1; justify-content: space-between; text-align: left; }
}
"""


def empty_history() -> pd.DataFrame:
    return pd.DataFrame(columns=["step", "scale", "value"])


def history_frame(history: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in history:
        rows.append({"step": item["step"], "scale": "Celsius", "value": item["celsius"]})
        rows.append(
            {"step": item["step"], "scale": "Fahrenheit", "value": item["fahrenheit"]}
        )
    return pd.DataFrame(rows, columns=["step", "scale", "value"])


def initial_result_html() -> str:
    return """
    <div class="empty-result">
      <div class="empty-orbit">°</div>
      <h2>Glyphへ温度を送信</h2>
      <p>スライダーまたはプリセットを選び、変換を実行してください。計算式と温度帯判定はGlyph側にあります。</p>
    </div>
    """


def error_result_html(message: str) -> str:
    return f"""
    <div class="result-card invalid">
      <div class="eyebrow">GLYPH INVOCATION ERROR</div>
      <div class="main-number" style="font-size:42px;line-height:1.1">実行できません</div>
      <div class="message"><div class="message-mark">!</div><div><strong>Pure Host境界で停止しました</strong><p>{escape(message)}</p></div></div>
    </div>
    """


def result_html(payload: dict[str, Any], world_version: int) -> str:
    band_value = payload.get("band")
    band = str(band_value.get("variant")) if isinstance(band_value, dict) else "Invalid"
    label, css_class, description = BAND_PRESENTATION.get(
        band, (band, "invalid", "未知のTemperatureBandです。")
    )
    celsius = float(payload["celsius"])
    fahrenheit = float(payload["fahrenheit"])
    kelvin = float(payload["kelvin"])
    count = int(payload["count"])
    gauge = max(0.0, min(100.0, (celsius + 50.0) / 1.5))
    return f"""
    <div class="result-card {escape(css_class)}">
      <div class="result-head">
        <div><div class="eyebrow">GLYPH RESULT · WORLD {world_version}</div><div class="main-number">{fahrenheit:.1f}<span>°F</span></div></div>
        <div class="band-badge"><span class="band-dot"></span>{escape(label)}</div>
      </div>
      <div class="result-body">
        <div>
          <div class="metrics">
            <div class="metric"><div class="metric-label">入力</div><div class="metric-value">{celsius:.1f}<small>°C</small></div></div>
            <div class="metric"><div class="metric-label">華氏</div><div class="metric-value">{fahrenheit:.1f}<small>°F</small></div></div>
            <div class="metric"><div class="metric-label">絶対温度</div><div class="metric-value">{kelvin:.2f}<small>K</small></div></div>
          </div>
          <div class="message"><div class="message-mark">i</div><div><strong>{escape(label)}</strong><p>{escape(description)} · invocation {count}</p></div></div>
        </div>
        <div class="thermometer"><div class="thermometer-fill" style="--gauge:{gauge:.1f}%"></div></div>
      </div>
    </div>
    """


def runtime_html(runtime: LivePureGlyphRuntime) -> str:
    state = runtime.state_dict()
    active = state.get("active_world")
    pending = state.get("pending_patch")
    runtime_state = state.get("runtime")
    last_error = runtime_state.get("last_error") if isinstance(runtime_state, dict) else None
    if not isinstance(active, dict):
        return """
        <div class="runtime-card"><div class="runtime-mark">G</div><div><div class="runtime-kicker">GLYPH LIVE IMAGE</div><div class="runtime-title">No active World</div></div></div>
        """
    version = int(active.get("version", 0))
    definitions = len(active.get("definitions") or [])
    code_digest = str(active.get("code_digest") or "")[:12]
    pending_label = "None"
    warning = ""
    if isinstance(pending, dict):
        pending_label = str(pending.get("maximum_safety") or "pending")
        blockers = ", ".join(str(item) for item in pending.get("blockers") or [])
        warning = (
            '<div class="runtime-warning"><strong>Pending patch:</strong> '
            + escape(pending_label)
            + (" · " + escape(blockers) if blockers else "")
            + "</div>"
        )
    if last_error:
        warning += (
            '<div class="runtime-warning runtime-error"><strong>Source error:</strong> '
            + escape(str(last_error))
            + " · 直前のWorldを継続しています。</div>"
        )
    return f"""
    <div class="runtime-card">
      <div class="runtime-mark">G</div>
      <div><div class="runtime-kicker">GLYPH LIVE IMAGE</div><div class="runtime-title">Active World {version}</div><div class="runtime-detail">Interpreter Definition Cell · code {escape(code_digest)}</div></div>
      <div class="runtime-stats"><div class="runtime-stat"><strong>{definitions}</strong><span>Definitions</span></div><div class="runtime-stat"><strong>{escape(pending_label)}</strong><span>Pending</span></div></div>
      {warning}
    </div>
    """


def convert_temperature(
    runtime: LivePureGlyphRuntime,
    celsius: float,
    session: dict[str, Any] | None,
) -> tuple[str, pd.DataFrame, dict[str, Any], str, str]:
    current = dict(session or {})
    history = list(current.get("history") or [])
    count = int(current.get("count", 0))
    try:
        invocation = runtime.invoke(
            "render",
            {"input": {"celsius": float(celsius)}, "session": {"count": count}},
        )
        payload = invocation.to_python()
        if not isinstance(payload, dict):
            raise PureRuntimeError("render did not return TemperatureView")
        next_count = int(payload["count"])
        history.append(
            {
                "step": next_count,
                "celsius": float(payload["celsius"]),
                "fahrenheit": float(payload["fahrenheit"]),
            }
        )
        history = history[-24:]
        next_session = {"count": next_count, "history": history}
        card = result_html(payload, invocation.world_version)
    except (PureRuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
        next_session = current
        card = error_result_html(str(exc))
    return (
        card,
        history_frame(list(next_session.get("history") or [])),
        next_session,
        runtime_html(runtime),
        runtime.source_text,
    )


def preset_handler(runtime: LivePureGlyphRuntime, preset: float):
    def handle(session: dict[str, Any] | None):
        card, chart, next_session, status, source = convert_temperature(
            runtime, preset, session
        )
        return preset, card, chart, next_session, status, source

    return handle


def reset_application(runtime: LivePureGlyphRuntime):
    return (
        22.0,
        initial_result_html(),
        empty_history(),
        {"count": 0, "history": []},
        runtime_html(runtime),
        runtime.source_text,
    )


def poll_runtime(runtime: LivePureGlyphRuntime) -> tuple[str, str]:
    try:
        runtime.refresh()
    except OSError:
        pass
    return runtime_html(runtime), runtime.source_text


def build_demo(runtime: LivePureGlyphRuntime) -> gr.Blocks:
    with gr.Blocks(title="Glyph Temperature Studio") as demo:
        session = gr.State({"count": 0, "history": []})
        gr.HTML(
            """
            <section id="glyph-hero">
              <div class="hero-kicker"><span class="hero-dot"></span>GLYPH × GRADIO LIVE HOST</div>
              <h1>Temperature<br>Studio</h1>
              <p>検証済みGlyphをLive Worldとして実行し、Gradioは入力・可視化・履歴だけを担当します。Glyphファイルを保存すると、署名互換な変更は次の操作から反映されます。</p>
            </section>
            """
        )
        with gr.Row(equal_height=False):
            with gr.Column(scale=4, elem_classes=["panel"]):
                gr.HTML(
                    '<div class="panel-title">温度を入力</div><div class="panel-description">任意の値またはプリセットを選び、Glyphのrender関数へ送信します。</div>'
                )
                celsius = gr.Slider(
                    minimum=-300.0,
                    maximum=150.0,
                    value=22.0,
                    step=0.1,
                    label="摂氏温度",
                    info="Glyphが有効性と温度帯を判定します",
                )
                with gr.Row(elem_classes=["preset-row"]):
                    ice = gr.Button("氷点 0°C")
                    room = gr.Button("室温 22°C")
                with gr.Row(elem_classes=["preset-row"]):
                    body = gr.Button("体温 36.5°C")
                    boiling = gr.Button("沸点 100°C")
                convert = gr.Button(
                    "Glyphで変換する", variant="primary", elem_id="convert-button"
                )
                reset = gr.Button("履歴をリセット")
            with gr.Column(scale=7):
                result = gr.HTML(initial_result_html(), elem_id="result-card")
        world_status = gr.HTML(runtime_html(runtime), elem_id="world-status")
        with gr.Row(equal_height=False):
            with gr.Column(scale=7, elem_classes=["panel"]):
                history_plot = gr.LinePlot(
                    value=empty_history(),
                    x="step",
                    y="value",
                    color="scale",
                    title="変換履歴",
                    x_title="Invocation",
                    y_title="Temperature",
                )
            with gr.Column(scale=5, elem_classes=["panel"]):
                with gr.Accordion("実行中のGlyphソース", open=True):
                    source_code = gr.Code(
                        value=runtime.source_text,
                        interactive=False,
                        label="gradio_temperature.glyph",
                    )

        outputs = [result, history_plot, session, world_status, source_code]
        convert.click(
            fn=lambda value, state: convert_temperature(runtime, value, state),
            inputs=[celsius, session],
            outputs=outputs,
            api_name="convert_temperature",
        )
        preset_outputs = [
            celsius,
            result,
            history_plot,
            session,
            world_status,
            source_code,
        ]
        for button, value in (
            (ice, 0.0),
            (room, 22.0),
            (body, 36.5),
            (boiling, 100.0),
        ):
            button.click(
                fn=preset_handler(runtime, value),
                inputs=[session],
                outputs=preset_outputs,
            )
        reset.click(
            fn=lambda: reset_application(runtime),
            inputs=[],
            outputs=preset_outputs,
        )
        timer = gr.Timer(1.0)
        timer.tick(
            fn=lambda: poll_runtime(runtime),
            inputs=[],
            outputs=[world_status, source_code],
        )
    return demo


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the graphical Glyph Gradio Host")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--no-browser", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runtime = LivePureGlyphRuntime(args.source)
    runtime.start_watching()
    demo = build_demo(runtime)
    try:
        demo.launch(
            server_name=args.host,
            server_port=args.port,
            inbrowser=not args.no_browser,
            theme=gr.themes.Ocean(),
            css=CSS,
        )
    finally:
        runtime.stop()


if __name__ == "__main__":
    main()
