from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest

from glyph.editor_completion import _SCRIPT as COMPLETION_SCRIPT
from glyph.editor_completion_context import _SCRIPT as CONTEXT_SCRIPT


def _javascript_from_script(source: str) -> str:
    match = re.search(r"<script[^>]*>\n(.*)\n</script>", source, re.DOTALL)
    return match.group(1) if match else source


class EditorReservedWordCompletionTests(unittest.TestCase):
    def test_static_reserved_words_bypass_only_the_static_prefix_gate(self) -> None:
        self.assertIn('const EXPRESSION_KEYWORDS=["as"]', CONTEXT_SCRIPT)
        self.assertIn('const BORROW_KEYWORDS=["mut"]', CONTEXT_SCRIPT)
        self.assertIn("const staticPrefixReady=", COMPLETION_SCRIPT)
        self.assertIn("context.prefix.length<MIN_PREFIX&&!staticPrefixReady", COMPLETION_SCRIPT)
        self.assertIn("const documentPrefixReady=force||allowEmpty||context.prefix.length>=MIN_PREFIX", COMPLETION_SCRIPT)
        self.assertIn("documentQueryAllowed&&documentPrefixReady&&exactLexicalSnapshot()", COMPLETION_SCRIPT)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_context_proposes_reserved_words_from_one_character_prefixes(self) -> None:
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
    candidates:service.staticCandidates(classification,prefix).map(row=>row.text),
  }};
}}
console.log(JSON.stringify({{
  expression:inspect(">convert(x:U):U\\n  y := x a"),
  borrow:inspect("*Probe(value:& m"),
  topLevel:inspect("s"),
}}));
"""
        result = subprocess.run(
            ["node", "-e", runner], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertIn("as", data["expression"]["candidates"])
        self.assertIn("mut", data["borrow"]["candidates"])
        self.assertIn("system", data["topLevel"]["candidates"])


if __name__ == "__main__":
    unittest.main()
