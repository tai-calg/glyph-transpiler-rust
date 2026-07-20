from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glyph.incremental import IncrementalCompiler, watch_file
from glyph.repl import ReplSession


class IncrementalAndReplTests(unittest.TestCase):
    def test_unchanged_source_uses_cached_snapshot(self) -> None:
        compiler = IncrementalCompiler()
        source = ">inc(x:U):U=x+1\n"
        first = compiler.compile_text(source)
        second = compiler.compile_text(source)
        self.assertTrue(first.changed)
        self.assertFalse(second.changed)
        self.assertIs(first.snapshot, second.snapshot)

    def test_watch_once_writes_ast_and_live_diagrams(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "sample.glyph"
            source.write_text(">inc(x:U):U=x+1\n", encoding="utf-8")
            diagrams = root / "diagrams"
            ast = root / "typed-ast.json"
            watch_file(
                IncrementalCompiler(),
                source,
                diagram_dir=diagrams,
                ast_output=ast,
                once=True,
            )
            self.assertTrue((diagrams / "execution.mmd").exists())
            self.assertTrue(ast.exists())
            self.assertIn('"symbols"', ast.read_text(encoding="utf-8"))

    def test_repl_inspects_types_and_ast(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "sample.glyph"
            source.write_text(">inc(x:U):U=x+1\n", encoding="utf-8")
            session = ReplSession(source)
            output, done = session.execute(":type inc")
            self.assertFalse(done)
            self.assertIn("Fn", output)
            output, _ = session.execute(":ast inc")
            self.assertIn('"body"', output)
            output, _ = session.execute(":symbols")
            self.assertIn("function", output)


if __name__ == "__main__":
    unittest.main()
