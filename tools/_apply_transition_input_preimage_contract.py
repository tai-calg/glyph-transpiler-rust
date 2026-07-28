from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one patch anchor, found {count}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "tests/test_transition_semantics.py",
    '''        alarm = next(
            item
            for item in machine["transitions"]
            if item["target_state"] == "Alarmed"
            and (item.get("trigger") or {}).get("display") == "RaiseAlarm"
        )
        self.assertEqual(alarm["trigger"]["role"], "inferred-trigger")
        self.assertEqual(alarm["trigger"]["confidence"], "dataflow-inferred")
        self.assertEqual(alarm["event"], "RaiseAlarm")
        self.assertEqual(alarm["target_state"], "Alarmed")
        self.assertEqual(alarm["action"]["display"], "RaiseAlarm")
        self.assertEqual(alarm["action"]["provenance"], "machine-action-projection")
        self.assertNotEqual(alarm["action"]["display"], alarm["target_state"])
        self.assertEqual(alarm["effect_invocations"], [])
        self.assertNotIn("[action==RaiseAlarm]", alarm["display_label"])
        self.assertIn("input:input", alarm["trigger"]["provenance_roots"])
''',
    '''        alarm = next(
            item
            for item in machine["transitions"]
            if item["target_state"] == "Alarmed"
            and (item.get("action") or {}).get("display") == "RaiseAlarm"
            and item.get("input_preimage")
        )
        self.assertEqual(alarm["trigger"]["role"], "inferred-trigger")
        self.assertEqual(alarm["trigger"]["confidence"], "dataflow-expanded")
        self.assertEqual(alarm["trigger"]["provenance"], "decision-output-preimage")
        self.assertIn("input.forced_open", alarm["trigger"]["display"])
        self.assertEqual(alarm["event"], alarm["trigger"]["display"])
        self.assertEqual(alarm["target_state"], "Alarmed")
        self.assertEqual(alarm["action"]["display"], "RaiseAlarm")
        self.assertEqual(alarm["action"]["provenance"], "machine-action-projection")
        self.assertNotEqual(alarm["trigger"]["display"], alarm["action"]["display"])
        self.assertNotEqual(alarm["action"]["display"], alarm["target_state"])
        self.assertEqual(alarm["effect_invocations"], [])
        self.assertNotIn("[action==RaiseAlarm]", alarm["display_label"])
        self.assertIn("input:input", alarm["trigger"]["provenance_roots"])
''',
)

replace_once(
    "tests/verify_state_diagram_rendering.mjs",
    '''      warnings: ["state-independent-transition", "unreachable-branch", "unreachable-state"],
    }],
''',
    '''      warnings: ["state-independent-transition", "unreachable-branch", "unreachable-state"],
      requireInputAction: true,
    }],
''',
)

replace_once(
    "tests/verify_state_diagram_rendering.mjs",
    '''          return {
            id: cluster?.dataset.transitionId || "",
            value: element.querySelector(".transition-io-value")?.textContent || "",
            action: cluster?.dataset.actionValue || "",
          };
''',
    '''          return {
            id: cluster?.dataset.transitionId || "",
            value: element.querySelector(".transition-io-value")?.textContent || "",
            input: cluster?.dataset.inputValue || "",
            action: cluster?.dataset.actionValue || "",
          };
''',
)

replace_once(
    "tests/verify_state_diagram_rendering.mjs",
    '''        if (expected.provisionalTriggers !== undefined) {
''',
    '''        if (expected.requireInputAction) {
          const semanticPairs = combinedValues.filter(({input, action, value}) => (
            input.trim().length > 0
            && action.trim().length > 0
            && value.includes(" ➞ ")
          ));
          assert(
            semanticPairs.length > 0,
            `${testCase.slug}/${expected.name}: README candidate has no Input ➞ Action transition`,
          );
          for (const rendered of semanticPairs) {
            const transition = machine.transitions.find(item => item.id === rendered.id);
            assert(transition, `${testCase.slug}/${expected.name}: missing transition ${rendered.id}`);
            assert.notEqual(
              rendered.input,
              rendered.action,
              `${testCase.slug}/${expected.name}/${rendered.id}: intermediate Action repeated as Input`,
            );
            assert.notEqual(
              rendered.action,
              String(transition.target_state || ""),
              `${testCase.slug}/${expected.name}/${rendered.id}: Target State repeated as Action`,
            );
            assert.equal(
              transition.trigger?.provenance,
              "decision-output-preimage",
              `${testCase.slug}/${expected.name}/${rendered.id}: Input lacks proven decision preimage`,
            );
            assert(
              rendered.value.includes(` ➞ ${rendered.action}`),
              `${testCase.slug}/${expected.name}/${rendered.id}: rendered join is not Input ➞ Action`,
            );
          }
        }

        if (expected.provisionalTriggers !== undefined) {
''',
)

print("updated transition Input preimage contracts")
