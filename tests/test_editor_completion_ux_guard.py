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
        self.assertIn("function clampPopupToViewport()", _SCRIPT)
        self.assertIn("const maximumLeft=Math.max", _SCRIPT)
        self.assertIn("const maximumTop=Math.max", _SCRIPT)
        self.assertIn("Math.min(baseTop,maximumTop)", _SCRIPT)
        self.assertIn('popup.style.setProperty("max-height"', _SCRIPT)
        self.assertIn("viewportClamps", _SCRIPT)
        self.assertIn('window.addEventListener("resize",scheduleViewportClamp', _SCRIPT)

    def test_completion_options_stay_out_of_tab_order_and_publish_status(self) -> None:
        self.assertIn("option.tabIndex=-1", _SCRIPT)
        self.assertIn('editor.setAttribute("aria-haspopup","listbox")', _SCRIPT)
        self.assertIn('status.setAttribute("aria-live","polite")', _SCRIPT)
        self.assertIn("completion candidate", _SCRIPT)

    def test_document_completion_publication_requires_exact_lexical_revision(self) -> None:
        self.assertIn("function exactSnapshot()", _SCRIPT)
        self.assertIn("function publicationNeedsExactSnapshot()", _SCRIPT)
        self.assertIn('candidate?.origin==="document"', _SCRIPT)
        self.assertIn("function blockStalePublication()", _SCRIPT)
        self.assertIn("if(popup.hidden||!publicationNeedsExactSnapshot()||exactSnapshot())return false", _SCRIPT)
        self.assertIn("metrics.stalePublicationBlocks+=1", _SCRIPT)
        self.assertIn("hideStalePublication()", _SCRIPT)
        self.assertIn("if(blockStalePublication())return", _SCRIPT)

    def test_static_candidates_are_not_coupled_to_lexical_worker_revision(self) -> None:
        self.assertIn("!publicationNeedsExactSnapshot()", _SCRIPT)
        self.assertNotIn("if(popup.hidden||exactSnapshot())return false", _SCRIPT)

    def test_escape_dismissal_survives_caret_navigation_until_input_or_explicit_open(self) -> None:
        self.assertIn("suppressAutomaticReopen=true", _SCRIPT)
        self.assertIn('event.code==="Space"', _SCRIPT)
        self.assertIn('editor.addEventListener("input",()=>{suppressAutomaticReopen=false}', _SCRIPT)
        self.assertIn("blockSuppressedReopen", _SCRIPT)
        self.assertIn("completion.close()", _SCRIPT)

    def test_worker_recovery_is_bounded_per_failure_cycle_and_exact_success_resets_budget(self) -> None:
        self.assertIn("const MAX_RECOVERY_ATTEMPTS=3", _SCRIPT)
        self.assertIn("recoveryFailures=0", _SCRIPT)
        self.assertIn("recoveryAttempts=0", _SCRIPT)
        self.assertIn("recoveryAttempts>=MAX_RECOVERY_ATTEMPTS", _SCRIPT)
        self.assertIn("recoveryAttempts+=1", _SCRIPT)
        self.assertIn("metrics.recoveryExhausted+=1", _SCRIPT)
        self.assertNotIn("recoveryFailures===1", _SCRIPT)
        self.assertIn("lexicalIndex.invalidate?.()", _SCRIPT)
        self.assertIn('document.addEventListener("glyph-editor-lexical-index-updated"', _SCRIPT)
        self.assertIn("if(event.detail?.exact)resetRecovery()", _SCRIPT)

    def test_visual_viewport_changes_relay_reposition_without_sync_loop(self) -> None:
        self.assertIn("window.visualViewport", _SCRIPT)
        self.assertIn('window.visualViewport.addEventListener("resize"', _SCRIPT)
        self.assertIn('window.visualViewport.addEventListener("scroll"', _SCRIPT)
        self.assertIn("requestAnimationFrame", _SCRIPT)
        self.assertIn('window.dispatchEvent(new Event("resize"))', _SCRIPT)
        self.assertIn("scheduleViewportClamp()", _SCRIPT)

    def test_enhancer_is_idempotent(self) -> None:
        html = "<html><head></head><body><textarea id='editor'></textarea></body></html>"
        once = enhance_editor_completion_ux_guard_html(html)
        twice = enhance_editor_completion_ux_guard_html(once)
        self.assertEqual(once, twice)


if __name__ == "__main__":
    unittest.main()
