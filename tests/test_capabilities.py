from __future__ import annotations

import json
import unittest

from glyph import GlyphError, compile_outputs, compile_source, parse_compilation_model


class CapabilityTests(unittest.TestCase):
    def test_plain_source_keeps_public_ir_shape(self) -> None:
        outputs = compile_outputs(">double(x:I):I=x*2\n")
        design = json.loads(outputs.design_json)

        self.assertNotIn("capabilities", design)
        self.assertNotIn("capability-ir.json", outputs.diagrams.files)

    def test_resource_and_capability_types_are_erased_for_legacy_codegen(self) -> None:
        source = (
            "resource Buffer[Ready|Used]\n"
            "!consume(buffer:own Buffer[Ready]):own Buffer[Used]\n"
        )

        generated = compile_source(source)
        model = parse_compilation_model(source)

        self.assertIn("pub struct Buffer", generated)
        self.assertEqual(model.capabilities.resources[0].states, ("Ready", "Used"))
        self.assertEqual(
            model.capabilities.functions[0].params[0].type.capability.value,
            "own",
        )

    def test_resource_requires_capability_and_state(self) -> None:
        with self.assertRaisesRegex(GlyphError, "own/share/link"):
            compile_source(
                "resource Buffer[Ready|Used]\n"
                "!bad(buffer:Buffer[Ready]):U\n"
            )

        with self.assertRaisesRegex(GlyphError, r"\[State\]"):
            compile_source(
                "resource Buffer[Ready|Used]\n"
                "!bad(buffer:own Buffer):U\n"
            )

    def test_unknown_resource_state_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "state 'Missing'"):
            compile_source(
                "resource Buffer[Ready|Used]\n"
                "!bad(buffer:own Buffer[Missing]):U\n"
            )

    def test_failure_path_must_keep_owned_resource(self) -> None:
        with self.assertRaisesRegex(GlyphError, "失敗型"):
            compile_source(
                "resource Buffer[Ready|Used]\n"
                "+E=Bad\n"
                "!bad(buffer:own Buffer[Ready]):own Buffer[Used]|E\n"
            )

        generated = compile_source(
            "resource Buffer[Ready|Used]\n"
            "+E=Bad\n"
            "*WriteError(buffer:own Buffer[Ready],cause:E)\n"
            "!write(buffer:own Buffer[Ready]):own Buffer[Used]|WriteError\n"
        )
        self.assertIn("pub struct WriteError", generated)

    def test_move_after_use_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "move後"):
            compile_source(
                "resource Buffer[Ready]\n"
                ">bad(buffer:own Buffer[Ready]):own Buffer[Ready]\n"
                "  next := buffer\n"
                "  inspect(&buffer)\n"
                "  next\n"
            )

    def test_borrow_cannot_escape_into_binding(self) -> None:
        with self.assertRaisesRegex(GlyphError, "一時借用"):
            compile_source(
                "resource Buffer[Ready]\n"
                ">bad(buffer:own Buffer[Ready]):own Buffer[Ready]\n"
                "  saved := &buffer\n"
                "  buffer\n"
            )

    def test_share_cannot_be_mutably_borrowed(self) -> None:
        with self.assertRaisesRegex(GlyphError, "share値"):
            compile_source(
                ">bad(state:share State):share State\n"
                "  update(&mut state)\n"
                "  state\n"
            )

    def test_capability_casts_are_checked(self) -> None:
        generated = compile_source(
            ">publish(owner:own Service):share Service\n"
            "  shared := owner as share\n"
            "  shared\n"
        )
        self.assertIn("pub fn publish", generated)

        with self.assertRaisesRegex(GlyphError, "変換できない"):
            compile_source(
                ">bad(shared:share Service):own Service\n"
                "  owner := shared as own\n"
                "  owner\n"
            )

    def test_capability_ir_is_emitted_only_when_used(self) -> None:
        outputs = compile_outputs(
            "resource Buffer[Ready|Used]\n"
            "!consume(buffer:own Buffer[Ready]):own Buffer[Used]\n"
        )
        payload = json.loads(outputs.diagrams.files["capability-ir.json"])

        self.assertEqual(payload["schema"], "glyph.capability-ir")
        self.assertEqual(payload["resources"][0]["name"], "Buffer")


if __name__ == "__main__":
    unittest.main()
