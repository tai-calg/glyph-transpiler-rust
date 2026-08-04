from __future__ import annotations


_MARKER = "glyph-save-presentation-v1"


def _replace_once(html: str, old: str, new: str, label: str) -> str:
    if old not in html:
        raise ValueError(f"save presentation anchor changed: {label}")
    return html.replace(old, new, 1)


def enhance_save_presentation_html(html: str) -> str:
    """Finalize localized labels and accessibility for save-triggered rendering."""

    if _MARKER in html:
        return html
    html = _replace_once(
        html,
        'save:"保存"',
        'save:"保存して描画"',
        "Japanese save label",
    )
    html = _replace_once(
        html,
        'save:"Save"',
        'save:"Save & Render"',
        "English save label",
    )
    html = _replace_once(
        html,
        '  button.title=t("saveTitle");\n'
        '  button.setAttribute("aria-busy",saveInFlight?"true":"false");',
        '  button.title=t("saveTitle");\n'
        '  button.setAttribute("aria-label",t("saveTitle"));\n'
        '  button.setAttribute("aria-busy",saveInFlight?"true":"false");',
        "save accessibility",
    )
    return html.replace("</body>", f"<!-- {_MARKER} -->\n</body>", 1)
