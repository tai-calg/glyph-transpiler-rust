from __future__ import annotations

import json
import shutil
import subprocess
import unittest

from glyph.editor_completion import _SCRIPT as COMPLETION_SCRIPT
from glyph.editor_completion_context import _SCRIPT as CONTEXT_SCRIPT
from glyph.editor_lexical_runtime import _SCRIPT as LEXICAL_RUNTIME_SCRIPT


class EditorCompletionFuzzyTests(unittest.TestCase):
    def test_lexical_refresh_is_low_latency_and_query_is_bounded(self) -> None:
        self.assertIn("const DEBOUNCE_MS=32", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("function insertBounded(rows,candidate,limit)", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("if(rows.length>=rowLimit)return rows", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("metrics.fuzzyRowsScanned+=1", LEXICAL_RUNTIME_SCRIPT)
        query_start = LEXICAL_RUNTIME_SCRIPT.index("function query(prefix,caret")
        query_end = LEXICAL_RUNTIME_SCRIPT.index("\ndocument.addEventListener", query_start)
        self.assertNotIn("rows.sort(", LEXICAL_RUNTIME_SCRIPT[query_start:query_end])

    def test_generic_matcher_covers_bounded_edit_and_subsequence_classes(self) -> None:
        self.assertIn("function fuzzyEditBudget(length)", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("if(length<=4)return 1", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("if(length<=8)return 2", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("return 3", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("previousPrevious[targetIndex-2]+1", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("function subsequenceMatch(source,target,foldedSource,foldedTarget)", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("while(searchStart<foldedTarget.length)", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn('kind:"case-prefix"', LEXICAL_RUNTIME_SCRIPT)
        self.assertIn('kind:"fuzzy"', LEXICAL_RUNTIME_SCRIPT)
        self.assertIn('kind:"subsequence"', LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("MAX_FUZZY_PREFIX=48", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("const maxGaps=Math.min(24,Math.max(4,source.length*2))", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("return subsequenceMatch(source,target,foldedSource,foldedTarget)", LEXICAL_RUNTIME_SCRIPT)

    def test_static_and_document_acceptance_share_the_same_matcher(self) -> None:
        self.assertIn("lexicalIndex.matchText?.(text,row.text)", CONTEXT_SCRIPT)
        self.assertIn("function candidateMatchesPrefix(text,prefix)", COMPLETION_SCRIPT)
        self.assertIn("lexicalIndex.matchText?.(prefix,text)?.matched", COMPLETION_SCRIPT)
        self.assertIn("!candidateMatchesPrefix(pending.text,context.prefix)", COMPLETION_SCRIPT)
        self.assertIn("!exactPrefix&&!candidateMatchesPrefix(candidate.text,context.prefix)", COMPLETION_SCRIPT)
        self.assertNotIn("!pending.text.startsWith(context.prefix)", COMPLETION_SCRIPT)
        self.assertNotIn("!candidate.text.startsWith(context.prefix)", COMPLETION_SCRIPT)

    def test_match_quality_precedes_semantic_preference_in_final_ranking(self) -> None:
        self.assertIn("function matchTier(candidate)", COMPLETION_SCRIPT)
        self.assertIn("const leftTier=matchTier(left),rightTier=matchTier(right)", COMPLETION_SCRIPT)
        self.assertIn("if(leftTier!==rightTier)return leftTier-rightTier", COMPLETION_SCRIPT)
        self.assertIn("const leftMatch=Number(left.matchScore||0),rightMatch=Number(right.matchScore||0)", COMPLETION_SCRIPT)
        self.assertIn("if(leftMatch!==rightMatch)return leftMatch-rightMatch", COMPLETION_SCRIPT)
        tier_position = COMPLETION_SCRIPT.index("if(leftTier!==rightTier)return leftTier-rightTier")
        preference_position = COMPLETION_SCRIPT.index("const leftPref=preferenceIndex")
        self.assertLess(tier_position, preference_position)
        self.assertIn("QUERY_POOL=32", COMPLETION_SCRIPT)

    def test_snapshot_payload_is_validated_against_the_inflight_request(self) -> None:
        self.assertIn("function validSnapshotMessage(result,completed)", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("revision!==Number(completed.revision)", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn('sourceLength!==String(completed.source??"").length', LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("result.positions instanceof Int32Array", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("result.codePositions instanceof Int32Array", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("Number(row.allOffset)!==expectedAllOffset", LEXICAL_RUNTIME_SCRIPT)
        self.assertIn("metrics.invalidMessages+=1", LEXICAL_RUNTIME_SCRIPT)

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_matcher_handles_edit_distance_and_non_contiguous_intellisense_queries(self) -> None:
        start = LEXICAL_RUNTIME_SCRIPT.index("function fuzzyEditBudget")
        end = LEXICAL_RUNTIME_SCRIPT.index("\nfunction clearTimer", start)
        matcher_source = LEXICAL_RUNTIME_SCRIPT[start:end]
        runner = f"""
const MAX_FUZZY_PREFIX=48;
{matcher_source}
const cases={{
  exact:matchText("Fau","Faulted"),
  omission:matchText("Fal","Faulted"),
  multipleOmissions:matchText("Flted","Faulted"),
  substitution:matchText("Fauxt","Faulted"),
  insertion:matchText("Fauult","Faulted"),
  transposition:matchText("Fual","Faulted"),
  caseOmission:matchText("fal","Faulted"),
  sparse:matchText("Ftd","Faulted"),
  camel:matchText("MC","MotorCommand"),
  repeatedStart:matchText("MC","MegaMotorCommand"),
  unrelated:matchText("zzz","Faulted"),
}};
console.log(JSON.stringify(cases));
"""
        result = subprocess.run(
            ["node", "-e", runner], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["exact"]["kind"], "prefix")
        for key in (
            "omission",
            "multipleOmissions",
            "substitution",
            "insertion",
            "transposition",
            "caseOmission",
        ):
            self.assertEqual(data[key]["kind"], "fuzzy", key)
            self.assertLessEqual(data[key]["edits"], 3, key)
        self.assertEqual(data["sparse"]["kind"], "subsequence")
        self.assertEqual(data["camel"]["kind"], "subsequence")
        self.assertEqual(data["repeatedStart"]["kind"], "subsequence")
        self.assertIsNone(data["unrelated"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_prefix_match_outranks_fuzzy_preferred_kind(self) -> None:
        start = COMPLETION_SCRIPT.index("function preferenceIndex")
        end = COMPLETION_SCRIPT.index("\nfunction exactLexicalSnapshot", start)
        ranking_source = COMPLETION_SCRIPT[start:end]
        runner = f"""
const MAX_RESULTS=8;
{ranking_source}
const classification={{exactText:null,preferredKinds:["Function","Type"],scopeStart:-1,excludeText:null}};
const base={{owners:[],origin:"document",count:1,recent:10,added:1}};
const prefixType={{...base,text:"FaultType",kind:"Type",kinds:["Type"],matchKind:"prefix",matchScore:0}};
const fuzzyFunction={{...base,text:"FaultHandler",kind:"Function",kinds:["Function"],matchKind:"fuzzy",matchScore:124}};
const prefixFunction={{...base,text:"FaultFn",kind:"Function",kinds:["Function"],matchKind:"prefix",matchScore:0}};
const merged=mergeCandidates([fuzzyFunction,prefixType],[],classification,{{current:"Fau"}});
const sameTier=mergeCandidates([prefixType,prefixFunction],[],classification,{{current:"Fau"}});
console.log(JSON.stringify({{merged:merged.map(row=>row.text),sameTier:sameTier.map(row=>row.text)}}));
"""
        result = subprocess.run(
            ["node", "-e", runner], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data["merged"][0], "FaultType")
        self.assertEqual(data["sameTier"][0], "FaultFn")

    @unittest.skipUnless(shutil.which("node"), "Node.js is not installed")
    def test_snapshot_validator_rejects_shape_revision_length_and_offset_corruption(self) -> None:
        start = LEXICAL_RUNTIME_SCRIPT.index("function nonNegativeInteger")
        end = LEXICAL_RUNTIME_SCRIPT.index("\nfunction clearTimer", start)
        validator_source = LEXICAL_RUNTIME_SCRIPT[start:end]
        runner = f"""
{validator_source}
const completed={{revision:7,source:"Alpha"}};
const valid={{
  type:"snapshot",revision:7,sourceLength:5,
  records:[{{text:"Alpha",allOffset:0,allCount:1,codeOffset:0,codeCount:1,kinds:["Identifier"],owners:[],ownerKinds:{{}},kind:"Identifier"}}],
  positions:new Int32Array([0]),codePositions:new Int32Array([0]),machineRecords:[],
}};
const malformed={{...valid,records:null}};
const future={{...valid,revision:8}};
const wrongLength={{...valid,sourceLength:4}};
const badOffset={{...valid,records:[{{...valid.records[0],allOffset:1}}]}};
console.log(JSON.stringify({{
  valid:validSnapshotMessage(valid,completed),
  malformed:validSnapshotMessage(malformed,completed),
  future:validSnapshotMessage(future,completed),
  wrongLength:validSnapshotMessage(wrongLength,completed),
  badOffset:validSnapshotMessage(badOffset,completed),
}}));
"""
        result = subprocess.run(
            ["node", "-e", runner], capture_output=True, text=True, check=False
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data["valid"])
        self.assertFalse(data["malformed"])
        self.assertFalse(data["future"])
        self.assertFalse(data["wrongLength"])
        self.assertFalse(data["badOffset"])


if __name__ == "__main__":
    unittest.main()
