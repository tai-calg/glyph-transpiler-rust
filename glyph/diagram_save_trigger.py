from __future__ import annotations

import re


_MARKER = "glyph-save-triggered-rendering-v1"


def _replace_once(html: str, old: str, new: str, label: str) -> str:
    if old not in html:
        raise ValueError(f"save-triggered rendering anchor changed: {label}")
    return html.replace(old, new, 1)


def _replace_pattern_once(
    html: str,
    pattern: str,
    replacement: str,
    label: str,
) -> str:
    result, count = re.subn(
        pattern,
        replacement,
        html,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError(f"save-triggered rendering anchor changed: {label}")
    return result


def enhance_save_triggered_rendering_html(html: str) -> str:
    """Make save the only editor action that compiles and redraws diagrams."""

    if _MARKER in html:
        return html

    html = _replace_once(
        html,
        '  <button id="compile" class="primary">Compile</button>\n'
        '  <button id="save">Save</button>',
        '  <button id="save" class="primary" '
        'title="Save and render (Ctrl/Cmd+S)">Save & Render</button>\n'
        f'  <!-- {_MARKER} -->',
        "header controls",
    )
    html = _replace_once(
        html,
        "let snapshot=null,activeTab='io',systemIndex=0,machineIndex=0,dirty=false,previewTimer=null;",
        "let snapshot=null,activeTab='io',systemIndex=0,machineIndex=0,dirty=false;",
        "preview timer state",
    )
    html = _replace_once(
        html,
        "async function compile(){setStatus('busy');snapshot=await request('/api/preview',{method:'POST',body:JSON.stringify({source:editor.value})});render()}\n",
        "",
        "base preview request",
    )
    html = _replace_once(
        html,
        "document.getElementById('compile').onclick=compile;document.getElementById('save').onclick=save;",
        "document.getElementById('save').onclick=save;",
        "base compile button handler",
    )
    html = _replace_pattern_once(
        html,
        r"editor\.addEventListener\('input',\(\)=>\{.*?\}\);"
        r"(?=editor\.addEventListener\('scroll')",
        "editor.addEventListener('input',()=>{dirty=true;syncLines()});",
        "editor input preview",
    )
    html = _replace_once(
        html,
        "document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();compile()}if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();save()}});",
        "document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();save()}});",
        "compile keyboard shortcut",
    )

    html = _replace_pattern_once(
        html,
        r"\n  compile=async function stableCompile\(\)\{.*?\n  \};\n"
        r"  save=async function stableSave",
        "\n  save=async function stableSave",
        "stable preview",
    )
    html = _replace_once(
        html,
        '  document.getElementById("compile").onclick=()=>compile();\n',
        "",
        "stable compile button handler",
    )

    if "/api/preview" in html or "previewTimer" in html:
        raise ValueError("save-triggered rendering still contains preview execution")
    return html
