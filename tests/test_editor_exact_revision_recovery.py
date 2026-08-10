from __future__ import annotations

import unittest

from glyph.editor_exact_revision_guard import _SCRIPT as EXACT_GUARD_SCRIPT
from glyph.editor_lexical_runtime import _SCRIPT as LEXICAL_RUNTIME_SCRIPT
from glyph.readable_diagram_app import _presentation_pipeline


class EditorExactRevisionRecoveryTests(unittest.TestCase):
    def test_pipeline_prefers_bounded_runtime_before_legacy_compatibility_enhancer(self) -> None:
        names = [enhancer.__name__ for enhancer in _presentation_pipeline()]
        document = names.index("enhance_editor_document_runtime_html")
        runtime = names.index("enhance_editor_lexical_runtime_html")
        legacy = names.index("enhance_editor_lexical_index_html")
        highlight = names.index("enhance_editor_identifier_highlight_html")
        completion = names.index("enhance_editor_completion_html")
        exact = names.index("enhance_editor_exact_revision_guard_html")
        ux = names.index("enhance_editor_completion_ux_guard_html")
        self.assertLess(document, runtime)
        self.assertLess(runtime, legacy)
        self.assertLess(legacy, highlight)
        self.assertLess(highlight, completion)
        self.assertLess(completion, exact)
        self.assertLess(exact, ux)

    def test_worker_recovery_has_one_bounded_runtime_owner(self) -> None:
        self.assertIn("const MAX_RECOVERY_ATTEMPTS=3", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("function handleWorkerFailure", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("function scheduleRecovery", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("recoveryAttempts+=1", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("if(recoveryAttempts>=MAX_RECOVERY_ATTEMPTS)markRecoveryExhausted()", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("if(recoveryExhausted||recoveryFailures>0){pending=request", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("if(recoveryExhausted||recoveryFailures>0){pending=buildRequest()", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("if(exact)resetRecoveryAfterExact()", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn('emit("glyph-editor-lexical-index-recovery-exhausted"', LEXICAL_RUNTIME_SCRIPT)
        self.assertNotIn("restartCount<1", LEXICAL_RUNTIME_SCRIPT)

    def test_exact_guard_synchronously_invalidates_all_document_derived_ui(self) -> None:
        for event_name in (
            "glyph-editor-document-changed",
            "glyph-editor-source-replaced",
            "glyph-editor-lexical-index-invalidated",
            "glyph-editor-lexical-index-error",
            "glyph-editor-lexical-index-recovery-exhausted",
        ):
            self.assertIn(event_name, EXACT_GUARD_SCRIPT)
        self.assertIn("completionNeedsExactSnapshot", EXACT_GUARD_SCRIPT)
        self.assertIn("completion.close()", EXACT_GUARD_SCRIPT)
        self.assertIn('editor.dataset.activeIdentifier=""', EXACT_GUARD_SCRIPT)
        self.assertIn('parent?.classList.remove("identifier-highlight-active")', EXACT_GUARD_SCRIPT)
        self.assertIn("highlightApi.identifier=()=>exactSnapshot()?originalIdentifier():\"\"", EXACT_GUARD_SCRIPT)
        self.assertIn("highlightApi.matchCount=()=>exactSnapshot()?originalMatchCount():0", EXACT_GUARD_SCRIPT)


if __name__ == "__main__":
    unittest.main()
