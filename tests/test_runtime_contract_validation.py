from __future__ import annotations

import unittest

from glyph import GlyphError, parse_compilation_model


class RuntimeContractValidationTests(unittest.TestCase):
    def test_field_world_application_targets_place(self) -> None:
        model = parse_compilation_model(
            "'@UiWindow = Ui * App/Window\n"
            "*App(\n"
            "  state:own UiState @{'UiWindow},\n"
            "  worker:share Worker\n"
            ")\n"
        )
        application = model.runtime_contracts.applications[0]
        self.assertEqual(application.target, "App.state")
        self.assertEqual(application.target_kind, "field")

    def test_field_rejects_protocol_and_handler(self) -> None:
        with self.assertRaisesRegex(GlyphError, "field"):
            parse_compilation_model(
                "'>Exchange = -> UiState\n"
                "'Bad = {'Exchange}\n"
                "*App(\n"
                "  state:own UiState @{'Bad}\n"
                ")\n"
            )

    def test_handler_has_only_one_recovery_action(self) -> None:
        with self.assertRaisesRegex(GlyphError, "最終復旧"):
            parse_compilation_model(
                "resource Tx[Open]\n"
                "'!Bad = 'std.rollback(tx) >> 'std.return_error\n"
                "'Use = {'Bad}\n"
                "+E=Bad\n"
                "*RunError(tx:own Tx[Open],cause:E)\n"
                "!run(tx:own Tx[Open]):I|RunError @{'Use}\n"
            )

    def test_retry_count_must_be_positive(self) -> None:
        with self.assertRaisesRegex(GlyphError, "0より大きく"):
            parse_compilation_model(
                "'!Bad = 'std.retry(0,'std.exponential,'std.idempotent)\n"
                "'Use = {'Bad}\n"
                "+E=Bad\n"
                ">run(x:own I):I|E=Ok(x) @{'Use}\n"
            )

    def test_compensation_must_reference_effect_boundary(self) -> None:
        with self.assertRaisesRegex(GlyphError, "作用境界"):
            parse_compilation_model(
                "'!Bad = 'std.compensate(undo)\n"
                "'Use = {'Bad}\n"
                ">undo(x:I):I=x\n"
                ">run(x:own I):I=x @{'Use}\n"
            )

    def test_fallback_signature_must_match(self) -> None:
        with self.assertRaisesRegex(GlyphError, "同じ入出力型"):
            parse_compilation_model(
                "'!Policy = 'std.fallback(backup)\n"
                "'Use = {'Policy}\n"
                ">backup(x:own Text):Text=x\n"
                ">run(x:own I):I=x @{'Use}\n"
            )


if __name__ == "__main__":
    unittest.main()
