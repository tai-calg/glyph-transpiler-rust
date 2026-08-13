from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest

from glyph.capabilities import _TYPE_PREFIXES
from glyph.editor_completion import _SCRIPT as COMPLETION_SCRIPT
from glyph.editor_completion_context import CANONICAL_RESERVED_WORDS
from glyph.editor_completion_context import _SCRIPT as CONTEXT_SCRIPT
from glyph.machine import _ALLOWED_PROPERTIES
from glyph.temporal_sigils import _RESERVED_TEMPORAL_NAMES


def _javascript_from_script(source: str) -> str:
    match = re.search(r"<script[^>]*>\n(.*)\n</script>", source, re.DOTALL)
    return match.group(1) if match else source


class EditorReservedWordCompletionTests(unittest.TestCase):
    def test_canonical_reserved_word_inventory_is_complete(self) -> None:
        expected = {
            "system",
            "machine",
            "assembly",
            "resource",
            "ext",
            "entry",
            "source",
            "sink",
            "select",
            "action",
            "init",
            "next",
            "success",
            "failure",
            "own",
            "share",
            "link",
            "mut",
            "as",
            "true",
            "false",
            "A",
            "E",
            "U",
            "W",
            "end",
        }
        self.assertEqual(CANONICAL_RESERVED_WORDS, expected)
        self.assertEqual(
            set(_ALLOWED_PROPERTIES),
            {"select", "action", "init", "next", "success", "failure"},
        )
        self.assertEqual(set(_TYPE_PREFIXES), {"own", "share", "link"})
        self.assertEqual(_RESERVED_TEMPORAL_NAMES, {"A", "E"})
        self.assertNotIn("in", CANONICAL_RESERVED_WORDS)
        self.assertNotIn("out", CANONICAL_RESERVED_WORDS)

    def test_static_reserved_words_bypass_only_the_static_prefix_gate(self) -> None:
        self.assertIn('const TOP_LEVEL_KEYWORDS=["system","machine","assembly","resource","ext"]', CONTEXT_SCRIPT)
        self.assertIn('const EXPRESSION_KEYWORDS=["as","true","false"]', CONTEXT_SCRIPT)
        self.assertIn('const BORROW_KEYWORDS=["mut"]', CONTEXT_SCRIPT)
        self.assertIn('const TEMPORAL_WORD_OPERATORS=["U","W"]', CONTEXT_SCRIPT)
        self.assertIn('const TEMPORAL_SIGILS=["A","E"]', CONTEXT_SCRIPT)
        self.assertIn('const PREPROCESSOR_DIRECTIVES=["end"]', CONTEXT_SCRIPT)
        self.assertIn("classification.allowEmptyStatic===true", COMPLETION_SCRIPT)
        self.assertIn("context.prefix.length<MIN_PREFIX&&!staticPrefixReady", COMPLETION_SCRIPT)
        self.assertIn(
            "const documentPrefixReady=force||allowEmpty||context.prefix.length>=MIN_PREFIX",
            COMPLETION_SCRIPT,
        )
        self.assertIn(
            "documentQueryAllowed&&documentPrefixReady&&exactLexicalSnapshot()",
            COMPLETION_SCRIPT,
        )

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_context_proposes_every_reserved_word_family(self) -> None:
        javascript = _javascript_from_script(CONTEXT_SCRIPT)
        runner = f"""
global.window={{GlyphEditorLexicalIndex:{{
  machineInfo:()=>null,
  matchText:(prefix,text)=>{{
    if(!prefix||text.startsWith(prefix))return{{matched:true,kind:"prefix",score:0,edits:0}};
    return null;
  }},
}}}};
{javascript}
const service=window.GlyphEditorCompletionContext;
function inspect(source){{
  const caret=source.length;
  const lineStart=service.boundedLineStart(source,caret);
  let left=caret;
  while(left>lineStart&&/[A-Za-z0-9_]/.test(source[left-1]))left-=1;
  const prefix=source.slice(left,caret);
  const context={{source,caret,left,right:caret,prefix,current:prefix,lineStart}};
  const classification=service.classify(context);
  return{{
    id:classification.id,
    allowEmptyStatic:Boolean(classification.allowEmptyStatic),
    candidates:service.staticCandidates(classification,prefix).map(row=>row.text),
  }};
}}
console.log(JSON.stringify({{
  assembly:inspect("a"),
  system:inspect("system Controller\\n  e"),
  machine:inspect("machine Flow(state:S)\\n  a"),
  capability:inspect("*Probe(value:o"),
  typeBorrow:inspect("*Probe(value:& m"),
  valueBorrow:inspect(">borrow(x:S):S\\n  y := &m"),
  asKeyword:inspect(">convert(x:U):U\\n  y := x a"),
  trueKeyword:inspect(">truth(x:B):B\\n  t"),
  falseKeyword:inspect(">truth(x:B):B\\n  f"),
  temporalOperator:inspect("?Safe(x:B)=ready U"),
  temporalSigil:inspect("?Safe(x:B)=@"),
  preprocessorEnd:inspect("@"),
  assemblyBody:inspect("assembly App\\n  a"),
}}));
"""
        result = subprocess.run(
            ["node", "-e", runner], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)

        self.assertIn("assembly", data["assembly"]["candidates"])
        self.assertIn("entry", data["system"]["candidates"])
        self.assertIn("action", data["machine"]["candidates"])
        self.assertIn("own", data["capability"]["candidates"])
        self.assertIn("mut", data["typeBorrow"]["candidates"])
        self.assertIn("mut", data["valueBorrow"]["candidates"])
        self.assertIn("as", data["asKeyword"]["candidates"])
        self.assertIn("true", data["trueKeyword"]["candidates"])
        self.assertIn("false", data["falseKeyword"]["candidates"])
        self.assertIn("U", data["temporalOperator"]["candidates"])
        self.assertCountEqual(data["temporalSigil"]["candidates"], ["A", "E"])
        self.assertTrue(data["temporalSigil"]["allowEmptyStatic"])
        self.assertEqual(data["preprocessorEnd"]["candidates"], ["end"])
        self.assertTrue(data["preprocessorEnd"]["allowEmptyStatic"])
        self.assertEqual(data["assemblyBody"]["id"], "assembly-body")
        self.assertNotIn("as", data["assemblyBody"]["candidates"])


if __name__ == "__main__":
    unittest.main()
