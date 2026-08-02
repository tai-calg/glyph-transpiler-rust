from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "glyph" / "transition_io_clusters.py"
TEST = ROOT / "tests" / "test_transition_io_clusters.py"
SELF = Path(__file__).resolve()

source = SOURCE.read_text(encoding="utf-8")
old = '  if(cluster.dataset.ioValue!==value)cluster.innerHTML=clusterMarkup(value,input,guard,action);\n'
new = '  if(cluster.dataset.ioValue!==value||!cluster.querySelector(".transition-semantic-line"))cluster.innerHTML=clusterMarkup(value,input,guard,action);\n'
if source.count(old) != 1:
    raise SystemExit(f"transition cluster refresh site count={source.count(old)}")
SOURCE.write_text(source.replace(old, new), encoding="utf-8")

test = TEST.read_text(encoding="utf-8")
needle = '        self.assertIn("semanticLines(input,guard,action)", html)\n'
addition = '        self.assertIn(\'!cluster.querySelector(".transition-semantic-line")\', html)\n'
if test.count(needle) != 1:
    raise SystemExit("transition cluster test insertion point missing")
TEST.write_text(test.replace(needle, needle + addition), encoding="utf-8")
SELF.unlink()
