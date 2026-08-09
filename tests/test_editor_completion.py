from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from glyph.editor_completion import _SCRIPT as COMPLETION_SCRIPT
from glyph.editor_completion import enhance_editor_completion_html
from glyph.editor_document_runtime import _SCRIPT as DOCUMENT_SCRIPT
from glyph.editor_document_runtime import enhance_editor_document_runtime_html
from glyph.editor_identifier_highlight import _SCRIPT as HIGHLIGHT_SCRIPT
from glyph.editor_lexical_index import LEXICAL_WORKER_JS
from glyph.editor_lexical_index import _SCRIPT as INDEX_SCRIPT
from glyph.editor_lexical_index import enhance_editor_lexical_index_html
from glyph.readable_diagram_app import _presentation_pipeline


class EditorCompletionTests(unittest.TestCase):
    def test_editor_pipeline_installs_runtime_before_consumers(self) -> None:
        names = [enhancer.__name__ for enhancer in _presentation_pipeline()]
        document = names.index("enhance_editor_document_runtime_html")
        index = names.index("enhance_editor_lexical_index_html")
        highlight = names.index("enhance_editor_identifier_highlight_html")
        completion = names.index("enhance_editor_completion_html")
        save = names.index("enhance_save_controller_html")
        self.assertLess(save, document)
        self.assertLess(document, index)
        self.assertLess(index, highlight)
        self.assertLess(highlight, completion)

    def test_document_runtime_replaces_legacy_line_sync(self) -> None:
        self.assertIn("globalThis.syncLines=()=>renderLines()", DOCUMENT_SCRIPT)
        self.assertIn('document.addEventListener("glyph-editor-source-replaced"', INDEX_SCRIPT)
        self.assertIn("scheduleFullLineRecount", DOCUMENT_SCRIPT)
        self.assertIn("scheduleCaretReconcile", DOCUMENT_SCRIPT)
        self.assertIn("selectionStart===knownCaret?caretLine:null", DOCUMENT_SCRIPT)
        self.assertNotIn("selectionStart===knownCaret?caretLine:lineAt(selectionStart)", DOCUMENT_SCRIPT)
        self.assertNotIn("split('\\n')", DOCUMENT_SCRIPT)

    def test_lexical_index_coalesces_and_rejects_pre_replacement_results(self) -> None:
        self.assertIn("pending=request", INDEX_SCRIPT)
        self.assertIn("minimumRevision=documentRuntime.revision()", INDEX_SCRIPT)
        self.assertIn("Number(result.revision)<minimumRevision", INDEX_SCRIPT)
        self.assertIn("maxPendingDepth", INDEX_SCRIPT)

    def test_highlight_uses_exact_shared_revision(self) -> None:
        self.assertIn("Number(snapshot.revision)!==revision", HIGHLIGHT_SCRIPT)
        self.assertIn("lexicalIndex.allPositions", HIGHLIGHT_SCRIPT)
        self.assertNotIn("SOURCE_IDENTIFIER", HIGHLIGHT_SCRIPT)

    def test_completion_has_accept_revalidation_and_ime_guard(self) -> None:
        self.assertIn("inCodeOccurrence", COMPLETION_SCRIPT)
        self.assertIn("candidate.text.startsWith(context.prefix)", COMPLETION_SCRIPT)
        self.assertIn("event.isComposing", COMPLETION_SCRIPT)
        self.assertIn("documentRuntime.replaceRange", COMPLETION_SCRIPT)

    def test_enhancers_are_idempotent(self) -> None:
        html = "<html><head></head><body><textarea id='editor'></textarea></body></html>"
        for enhancer in (
            enhance_editor_document_runtime_html,
            enhance_editor_lexical_index_html,
            enhance_editor_completion_html,
        ):
            once = enhancer(html)
            twice = enhancer(once)
            self.assertEqual(once, twice)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_new_javascript_is_syntactically_valid(self) -> None:
        scripts = {
            "document.js": DOCUMENT_SCRIPT,
            "index.js": INDEX_SCRIPT,
            "highlight.js": HIGHLIGHT_SCRIPT,
            "completion.js": COMPLETION_SCRIPT,
            "worker.js": LEXICAL_WORKER_JS,
        }
        with tempfile.TemporaryDirectory() as directory:
            for filename, source in scripts.items():
                match = re.search(r"<script[^>]*>\n(.*)\n</script>", source, re.DOTALL)
                javascript = match.group(1) if match else source
                path = Path(directory) / filename
                path.write_text(javascript, encoding="utf-8")
                result = subprocess.run(
                    ["node", "--check", str(path)],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, f"{filename}: {result.stderr}")


if __name__ == "__main__":
    unittest.main()
