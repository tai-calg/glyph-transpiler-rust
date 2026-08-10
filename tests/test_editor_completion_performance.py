from __future__ import annotations

import json
import shutil
import subprocess
import unittest

import glyph
from glyph import editor_completion, editor_lexical_index, studio
from glyph.editor_lexical_worker_fast import FAST_LEXICAL_WORKER_JS


class EditorCompletionPerformanceTests(unittest.TestCase):
    def test_fast_worker_is_the_served_worker_payload(self) -> None:
        self.assertIs(editor_lexical_index.LEXICAL_WORKER_JS, FAST_LEXICAL_WORKER_JS)
        self.assertNotIn("stripComments(source)", FAST_LEXICAL_WORKER_JS)
        self.assertIn('for(const rawLine of source.split("\\n"))', FAST_LEXICAL_WORKER_JS)
        self.assertIn("Pass 1: collect every identifier position", FAST_LEXICAL_WORKER_JS)
        self.assertIn("Pass 2: classify declarations line-by-line", FAST_LEXICAL_WORKER_JS)

    def test_adaptive_scheduler_is_present_without_taking_recovery_ownership(self) -> None:
        html = studio.STUDIO_HTML
        self.assertIn("glyph-editor-completion-performance-v1", html)
        self.assertIn("if(burst>=3)return 20", html)
        self.assertIn("if(burst>=1)return 12", html)
        self.assertIn("return 6", html)
        self.assertIn("lexicalIndex.refresh?.()", html)
        self.assertNotIn("new Worker", html.split("glyph-editor-completion-performance-v1-script", 1)[1].split("</script>", 1)[0])

    def test_exact_snapshot_publication_does_not_wait_for_another_frame(self) -> None:
        script = editor_completion._SCRIPT
        self.assertIn("function updateExact(options={})", script)
        self.assertIn("if(frame){cancelAnimationFrame(frame);frame=0}", script)
        self.assertIn("metrics.fastExactUpdates", script)
        self.assertIn("if(event.detail?.exact)updateExact({allowEmpty:explicit})", script)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_fast_worker_preserves_core_semantic_records(self) -> None:
        source = """\
+Mode=Idle|Faulted
*Controller(state:Mode, count:Int)
resource Door<State>[Closed|Open]
>step(state:Mode):Mode
!emit(value:Mode):Void
?clock():Time
ext sensor(value:Mode):Mode
@NORMALIZE value
@ast(value)
system Control
'check
machine ControllerMachine(state:Controller)
  select=state.state
  local := state
# CommentOnly HiddenState
"""
        runner = f"""
const vm=require('vm');
const source={json.dumps(source)};
const worker={json.dumps(FAST_LEXICAL_WORKER_JS)};
let posted=null;
const context={{Int32Array,console,self:{{postMessage:value=>{{posted=value}}}}}};
vm.runInNewContext(worker,context);
context.self.onmessage({{data:{{revision:7,source}}}});
const normalizeRow=row=>({{
 text:row.text,kind:row.kind,kinds:[...row.kinds].sort(),owners:[...row.owners].sort(),
 ownerKinds:Object.fromEntries(Object.entries(row.ownerKinds).map(([owner,kinds])=>[owner,[...kinds].sort()])),
 codeCount:row.codeCount,
}});
const byText=Object.fromEntries(posted.records.map(row=>[row.text,normalizeRow(row)]));
console.log(JSON.stringify({{
 revision:posted.revision,sourceLength:posted.sourceLength,
 mode:byText.Mode,faulted:byText.Faulted,state:byText.state,step:byText.step,emit:byText.emit,
 clock:byText.clock,sensor:byText.sensor,door:byText.Door,closed:byText.Closed,
 normalize:byText.NORMALIZE,ast:byText.ast,control:byText.Control,check:byText.check,
 local:byText.local,commentOnly:byText.CommentOnly,machines:posted.machineRecords,
}}));
"""
        result = subprocess.run(["node", "-e", runner], capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["revision"], 7)
        self.assertEqual(data["sourceLength"], len(source))
        self.assertIn("Type", data["mode"]["kinds"])
        self.assertIn("State", data["faulted"]["kinds"])
        self.assertIn("Field", data["state"]["kinds"])
        self.assertIn("StateField", data["state"]["kinds"])
        self.assertIn("EntryFunction", data["step"]["kinds"])
        self.assertIn("Sink", data["emit"]["kinds"])
        self.assertIn("Temporal", data["clock"]["kinds"])
        self.assertIn("Source", data["sensor"]["kinds"])
        self.assertIn("Resource", data["door"]["kinds"])
        self.assertEqual(data["closed"]["owners"], ["Door"])
        self.assertIn("Macro", data["normalize"]["kinds"])
        self.assertIn("Macro", data["ast"]["kinds"])
        self.assertIn("System", data["control"]["kinds"])
        self.assertIn("Contract", data["check"]["kinds"])
        self.assertIn("Binding", data["local"]["kinds"])
        self.assertEqual(data["commentOnly"]["codeCount"], 0)
        self.assertEqual(data["machines"][0]["name"], "ControllerMachine")
        self.assertEqual(data["machines"][0]["stateType"], "Controller")
        self.assertEqual(data["machines"][0]["selectorField"], "state")
        self.assertEqual(data["machines"][0]["selectorType"], "Mode")


if __name__ == "__main__":
    unittest.main()
