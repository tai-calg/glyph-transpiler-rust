from __future__ import annotations

import json
import shutil
import subprocess
import unittest

from glyph.editor_identifier_highlight import _SCRIPT as HIGHLIGHT_SCRIPT
from glyph.editor_lexical_index import LEXICAL_WORKER_JS


class EditorCompletionRemainingEdgeTests(unittest.TestCase):
    def test_identifier_highlight_bounds_token_discovery(self) -> None:
        self.assertIn("const MAX_IDENTIFIER_LENGTH=256", HIGHLIGHT_SCRIPT)
        self.assertIn("let left=start,right=start,budget=MAX_IDENTIFIER_LENGTH", HIGHLIGHT_SCRIPT)
        self.assertGreaterEqual(HIGHLIGHT_SCRIPT.count("if(budget===0)"), 2)
        self.assertIn("end-start>MAX_IDENTIFIER_LENGTH", HIGHLIGHT_SCRIPT)
        self.assertIn("boundedIdentifierRejects", HIGHLIGHT_SCRIPT)
        self.assertNotIn(
            "while(left>0&&/[A-Za-z0-9_]/.test(value[left-1]))left-=1",
            HIGHLIGHT_SCRIPT,
        )
        self.assertNotIn(
            "while(right<value.length&&/[A-Za-z0-9_]/.test(value[right]))right+=1",
            HIGHLIGHT_SCRIPT,
        )

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_identifier_highlight_rejects_oversized_tokens(self) -> None:
        start = HIGHLIGHT_SCRIPT.index("function identifierAt")
        end = HIGHLIGHT_SCRIPT.index("\nfunction renderHtml", start)
        identifier_at = HIGHLIGHT_SCRIPT[start:end]
        runner = f"""
const IDENTIFIER=/^[A-Za-z_][A-Za-z0-9_]*$/;
const IDENTIFIER_PART=/[A-Za-z0-9_]/;
const MAX_IDENTIFIER_LENGTH=256;
const metrics={{boundedIdentifierRejects:0}};
{identifier_at}
const shortToken="A".repeat(256);
const longToken="A".repeat(10000);
const shortResult=identifierAt(shortToken,128,128,true);
const longResult=identifierAt(longToken,5000,5000,true);
const selectedResult=identifierAt(longToken,0,10000,true);
console.log(JSON.stringify({{shortLength:shortResult.length,longResult,selectedResult,rejects:metrics.boundedIdentifierRejects}}));
"""
        result = subprocess.run(
            ["node", "-e", runner], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["shortLength"], 256)
        self.assertEqual(data["longResult"], "")
        self.assertEqual(data["selectedResult"], "")
        self.assertEqual(data["rejects"], 2)

    def test_worker_marks_delimited_declarations_only_after_closure(self) -> None:
        product_close = LEXICAL_WORKER_JS.index(
            'const close=findMatchingOnLine(codeSource,open);'
        )
        product_mark = LEXICAL_WORKER_JS.index('mark(name,"Type");', product_close)
        self.assertLess(product_close, product_mark)
        self.assertIn('if(close<0)continue;\n    mark(name,"Resource")', LEXICAL_WORKER_JS)
        self.assertIn('if(close<0)continue;\n    const kind=', LEXICAL_WORKER_JS)
        self.assertIn('if(close<0)continue;\n    mark(name,"Source")', LEXICAL_WORKER_JS)
        self.assertIn('if(close<0)continue;\n    mark(name,"Machine")', LEXICAL_WORKER_JS)
        self.assertIn("parts.some(part=>!part.match", LEXICAL_WORKER_JS)
        self.assertIn('const aliasRe=/^=\\s*', LEXICAL_WORKER_JS)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_worker_keeps_incomplete_declarations_as_identifiers(self) -> None:
        source = """*Broken(
resource BrokenResource[Ready
>brokenFunction(
ext brokenSource(
machine BrokenMachine(
+BrokenSum=Idle|
=BrokenAlias=

+Mode=Idle|Running
*Closed(mode:Mode)
resource GoodResource[Ready|Done]
>real(state:Closed):Closed=state
ext realSource()
machine GoodMachine(state:Closed,input:Input)
  select=state.mode
"""
        runner = f"""
const results=[];
global.self={{postMessage:value=>results.push(value)}};
{LEXICAL_WORKER_JS}
self.onmessage({{data:{{revision:1,source:{json.dumps(source)}}}}});
const snapshot=results.at(-1);
const rows=Object.fromEntries(snapshot.records.map(row=>[row.text,row]));
const pick=name=>rows[name]?.kinds||[];
console.log(JSON.stringify({{
  Broken:pick("Broken"),
  BrokenResource:pick("BrokenResource"),
  brokenFunction:pick("brokenFunction"),
  brokenSource:pick("brokenSource"),
  BrokenMachine:pick("BrokenMachine"),
  BrokenSum:pick("BrokenSum"),
  BrokenAlias:pick("BrokenAlias"),
  Closed:pick("Closed"),
  GoodResource:pick("GoodResource"),
  real:pick("real"),
  realSource:pick("realSource"),
  GoodMachine:pick("GoodMachine"),
}}));
"""
        result = subprocess.run(
            ["node", "-e", runner], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        for name in (
            "Broken",
            "BrokenResource",
            "brokenFunction",
            "brokenSource",
            "BrokenMachine",
            "BrokenSum",
            "BrokenAlias",
        ):
            self.assertEqual(data[name], ["Identifier"], name)
        self.assertIn("Type", data["Closed"])
        self.assertIn("Resource", data["GoodResource"])
        self.assertIn("EntryFunction", data["real"])
        self.assertIn("Source", data["realSource"])
        self.assertIn("Machine", data["GoodMachine"])


if __name__ == "__main__":
    unittest.main()
