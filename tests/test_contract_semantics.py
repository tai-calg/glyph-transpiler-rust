from __future__ import annotations

import json
import unittest

from glyph import GlyphError, compile_outputs, compile_source, parse_compilation_model


class ContractSemanticTests(unittest.TestCase):
    def test_world_protocol_handler_law_bundle_is_canonicalized(self) -> None:
        source = (
            "'@WorkerTask = Worker * App/Window/Task\n"
            "'>RequestReply = -> I >> <- I\n"
            "'!Safe = 'std.timeout(2s) >> 'std.retry(2,'std.exponential,'std.idempotent) >> 'std.return_error\n"
            "'?Done = @A(start >> @E 2s finish)\n"
            "'WorkerCall = {'WorkerTask,'RequestReply,'Safe,'Done}\n"
            ">double(x:I):I=x*2 @{'WorkerCall}\n"
        )

        outputs = compile_outputs(source)
        payload = json.loads(outputs.diagrams.files["runtime-contract-ir.json"])

        self.assertEqual(payload["worlds"][0]["locus"], "Worker")
        self.assertEqual(payload["protocols"][0]["root"]["kind"], "sequence")
        self.assertEqual(
            [item["operation"] for item in payload["handlers"][0]["steps"]],
            ["timeout", "retry", "return_error"],
        )
        self.assertEqual(payload["laws"][0]["verification"], "model+runtime")
        self.assertEqual(payload["applications"][0]["target"], "double")

    def test_protocol_signature_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "送信型|先頭引数"):
            compile_source(
                "'>Wrong = -> Text >> <- I\n"
                "'Use = {'Wrong}\n"
                ">double(x:I):I=x*2 @{'Use}\n"
            )

    def test_bundle_rejects_two_worlds(self) -> None:
        with self.assertRaisesRegex(GlyphError, "World.*競合"):
            compile_source(
                "'@Ui = Ui * App/Window\n"
                "'@Worker = Worker * App/Task\n"
                "'Bad = {'Ui,'Worker}\n"
                ">double(x:I):I=x*2 @{'Bad}\n"
            )

    def test_retry_requires_idempotency(self) -> None:
        with self.assertRaisesRegex(GlyphError, "idempotent"):
            compile_source(
                "'!Unsafe = 'std.retry(2,'std.exponential,'std.none)\n"
                "'Use = {'Unsafe}\n"
                "+E=Bad\n"
                ">fetch(x:I):I|E=Ok(x) @{'Use}\n"
            )

    def test_retry_target_must_return_result(self) -> None:
        with self.assertRaisesRegex(GlyphError, "Result"):
            compile_source(
                "'!Retry = 'std.retry(2,'std.exponential,'std.idempotent)\n"
                "'Use = {'Retry}\n"
                ">double(x:own I):I=x*2 @{'Use}\n"
            )

    def test_rollback_requires_owned_resource_parameter(self) -> None:
        with self.assertRaisesRegex(GlyphError, "own resource"):
            compile_source(
                "resource Tx[Open|RolledBack]\n"
                "'!Rollback = 'std.rollback(tx)\n"
                "'Use = {'Rollback}\n"
                "+E=Bad\n"
                ">run(tx:share Tx[Open]):I|E=Err(Bad) @{'Use}\n"
            )

    def test_cross_world_direct_call_requires_protocol(self) -> None:
        with self.assertRaisesRegex(GlyphError, "Protocolなし"):
            compile_source(
                "'@Worker = Worker * App/Task\n"
                "'@Ui = Ui * App/Window\n"
                "'WorkerOnly = {'Worker}\n"
                "'UiOnly = {'Ui}\n"
                ">work(x:I):I=x @{'WorkerOnly}\n"
                ">run(x:I):I=work(x) @{'UiOnly}\n"
            )

    def test_cross_world_call_with_protocol_is_allowed(self) -> None:
        generated = compile_source(
            "'@Worker = Worker * App/Task\n"
            "'@Ui = Ui * App/Window\n"
            "'>Exchange = -> I >> <- I\n"
            "'WorkerCall = {'Worker,'Exchange}\n"
            "'UiOnly = {'Ui}\n"
            ">work(x:I):I=x @{'WorkerCall}\n"
            ">run(x:I):I=work(x) @{'UiOnly}\n"
        )
        self.assertIn("pub fn run", generated)

    def test_cross_world_borrow_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "異なるWorld"):
            compile_source(
                "'@Worker = Worker * App/Task\n"
                "'@Ui = Ui * App/Window\n"
                "'>Exchange = -> State >> <- I\n"
                "'WorkerCall = {'Worker,'Exchange}\n"
                "'UiOnly = {'Ui}\n"
                ">work(state:&mut State):I=read(&state) @{'WorkerCall}\n"
                ">run(state:own State):I=work(&mut state) @{'UiOnly}\n"
            )

    def test_plain_source_does_not_emit_runtime_contract_ir(self) -> None:
        outputs = compile_outputs(">double(x:I):I=x*2\n")
        self.assertNotIn("runtime-contract-ir.json", outputs.diagrams.files)
        self.assertEqual(model := parse_compilation_model(">double(x:I):I=x*2\n").runtime_contracts.applications, ())


if __name__ == "__main__":
    unittest.main()
