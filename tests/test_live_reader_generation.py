from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glyph.live_studio import LiveGlyphStudio


class LiveReaderGenerationTests(unittest.TestCase):
    def test_ast_macro_change_requires_reader_generation_acknowledgement(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "macro.glyph"
            source.write_text(
                "@twice(x)=x+x\n>run(x:U):U=twice(x)\n",
                encoding="utf-8",
            )
            studio = LiveGlyphStudio(source)
            first = studio.rebuild()
            self.assertEqual(first.status, "ready")

            second = studio.preview_source(
                "@twice(x)=x+x+x\n>run(x:U):U=twice(x)\n"
            )

            self.assertEqual(second.status, "ready")
            state = studio.state_dict()["live_image"]
            self.assertEqual(state["active_world"]["version"], 1)
            patch = state["pending_patch"]
            self.assertIsNotNone(patch)
            change = next(
                item
                for item in patch["changes"]
                if item["definition_id"] == "reader:twice"
            )
            self.assertEqual(change["safety"], "reader")
            self.assertIn(
                "reader-generation-acknowledgement-required",
                patch["blockers"],
            )

            committed = studio.commit_live_patch(reader_acknowledged=True)
            self.assertEqual(
                committed["live_image"]["active_world"]["version"],
                2,
            )


if __name__ == "__main__":
    unittest.main()
