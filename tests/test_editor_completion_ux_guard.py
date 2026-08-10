from __future__ import annotations

import unittest

from glyph.editor_completion_ux_guard import _SCRIPT, _STYLE, enhance_editor_completion_ux_guard_html
from glyph.readable_diagram_app import _presentation_pipeline


class EditorCompletionUxGuardTests(unittest.TestCase):
    def test_pipeline_installs_ux_guard_after_completion_before_global_gui_guards(self) -> None:
        names = [enhancer.__name__ for enhancer in _presentation_pipeline()]
        completion = names.index("enhance_editor_completion_html")
        ux_guard = names.index("enhance_editor_completion_ux_guard_html")
        gui_guard = names.index("enhance_diagram_gui_ux_guard_html")
        continuity = names.index("enhance_diagram_gui_ux_continuity_html")
        self.assertLess(completion, ux_guard)
        self.assertLess(ux_guard, gui_guard)
        self.assertLess(gui_guard, continuity)

    def test_compact_viewport_bounds_completion_popup(self) -> None:
        self.assertIn("max-height:min(260px,calc(100vh - 16px))", _STYLE)
        self.assertIn("min-width:min(210px,calc(100vw - 16px))", _STYLE)
        self.assertIn("max-width:min(440px,calc(100vw - 16px))", _STYLE)
        self.assertIn("overscroll-behavior:contain", _STYLE)

    def test_completion_options_stay_out_of_tab_order_and_publish_status(self) -> None:
        self.assertIn("option.tabIndex=-1", _SCRIPT)
        self.assertIn('editor.setAttribute("aria-haspopup","listbox")', _SCRIPT)
        self.assertIn('status.setAttribute("aria-live","polite")', _SCRIPT)
        self.assertIn("completion candidate", _SCRIPT)

    def test_escape_dismissal_survives_caret_navigation_until_input_or_explicit_open(self) -> None:
        self.assertIn("suppressAutomaticReopen=true", _SCRIPT)
        self.assertIn('event.code==="Space"', _SCRIPT)
        self.assertIn('editor.addEventListener("input",()=>{suppressAutomaticReopen=false}', _SCRIPT)
        self.assertIn("blockSuppressedReopen", _SCRIPT)
        self.assertIn("completion.close()", _SCRIPT)

    def test_worker_recovery_is_per_failure_cycle_not_page_lifetime(self) -> None:
        self.assertIn("recoveryFailures=0", _SCRIPT)
        self.assertIn("recoveryIssued=false", _SCRIPT)
        self.assertIn("if(recoveryFailures===1&&!recoveryIssued)", _SCRIPT)
        self.assertIn("lexicalIndex.invalidate?.()", _SCRIPT)
        self.assertIn('document.addEventListener("glyph-editor-lexical-index-updated"', _SCRIPT)
        self.assertIn("if(event.detail?.exact)resetRecovery()", _SCRIPT)

    def test_visual_viewport_changes_relay_reposition_without_sync_loop(self) -> None:
        self.assertIn("window.visualViewport", _SCRIPT)
        self.assertIn('window.visualViewport.addEventListener("resize"', _SCRIPT)
        self.assertIn('window.visualViewport.addEventListener("scroll"', _SCRIPT)
        self.assertIn("requestAnimationFrame", _SCRIPT)
        self.assertIn('window.dispatchEvent(new Event("resize"))', _SCRIPT)

    def test_enhancer_is_idempotent(self) -> None:
        html = "<html><head></head><body><textarea id='editor'></textarea></body></html>"
        once = enhance_editor_completion_ux_guard_html(html)
        twice = enhance_editor_completion_ux_guard_html(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
