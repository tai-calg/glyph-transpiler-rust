from __future__ import annotations

import unittest

from glyph.editor_document_runtime import _SCRIPT as DOCUMENT_SCRIPT
from glyph.editor_identifier_highlight import _SCRIPT as HIGHLIGHT_SCRIPT


class EditorRuntimeEdgeTests(unittest.TestCase):
    def test_native_set_range_text_is_tracked_without_double_revision(self) -> None:
        self.assertIn("const nativeSetRangeText=HTMLTextAreaElement.prototype.setRangeText", DOCUMENT_SCRIPT)
        self.assertIn('Object.defineProperty(editor,"setRangeText"', DOCUMENT_SCRIPT)
        self.assertIn("metrics.programmaticRangeEdits+=1", DOCUMENT_SCRIPT)
        self.assertIn('dispatch("glyph-editor-source-replaced",{sourceLength:value.length,rangeEdit:true})', DOCUMENT_SCRIPT)
        self.assertIn("if(suppressTrackedInput){suppressTrackedInput=false;beforePlan=null;syntheticPlan=null;return}", DOCUMENT_SCRIPT)
        self.assertIn("try{editor.dispatchEvent(event)}finally{suppressTrackedInput=false}", DOCUMENT_SCRIPT)

    def test_highlight_cache_preserves_match_count_and_avoids_geometry_rebuilds(self) -> None:
        self.assertIn('let renderedRevision=-1,renderedIdentifier="",renderedMatchCount=0', HIGHLIGHT_SCRIPT)
        self.assertIn("renderedMatchCount=matchCount", HIGHLIGHT_SCRIPT)
        self.assertIn("matchCount=renderedMatchCount", HIGHLIGHT_SCRIPT)
        self.assertIn("metrics.htmlRebuilds+=1", HIGHLIGHT_SCRIPT)
        self.assertIn("metrics.htmlReuses+=1", HIGHLIGHT_SCRIPT)
        self.assertIn("new ResizeObserver(syncGeometry).observe(sourceEditor)", HIGHLIGHT_SCRIPT)
        self.assertNotIn("new ResizeObserver(()=>schedule(true))", HIGHLIGHT_SCRIPT)


if __name__ == "__main__":
    unittest.main()
