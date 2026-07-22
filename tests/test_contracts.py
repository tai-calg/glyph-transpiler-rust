from __future__ import annotations

import unittest

from glyph import (
    ContractKind,
    GlyphError,
    compile_source,
    extract_contracts,
    parse_compilation_model,
)


class ContractTests(unittest.TestCase):
    def test_plain_source_is_returned_without_changes(self) -> None:
        source = ">double(x:I):I=x*2\n"
        extraction = extract_contracts(source)

        self.assertIs(extraction.source, source)
        self.assertEqual(extraction.model.declarations, ())
        self.assertEqual(extraction.model.applications, ())

    def test_contract_definitions_and_application_are_extracted(self) -> None:
        source = (
            "'@WorkerTask =\n"
            "  Worker * App/Window/Task\n"
            "\n"
            "'>ProcessImage =\n"
            "  -> Image >> <- ProcessResult\n"
            "\n"
            "'!SafeFailure =\n"
            "  'std.timeout(30s) >> 'std.return_error\n"
            "\n"
            "'?Complete30 =\n"
            "  @A(start >> @E 30s finish)\n"
            "\n"
            "'ImageWorker = {\n"
            "  'WorkerTask,\n"
            "  'ProcessImage,\n"
            "  'SafeFailure,\n"
            "  'Complete30\n"
            "}\n"
            "\n"
            ">double(x:I):I=x*2 @{'ImageWorker}\n"
        )

        extraction = extract_contracts(source)

        self.assertEqual(
            [declaration.kind for declaration in extraction.model.declarations],
            [
                ContractKind.WORLD,
                ContractKind.PROTOCOL,
                ContractKind.HANDLER,
                ContractKind.LAW,
                ContractKind.BUNDLE,
            ],
        )
        self.assertEqual(
            [reference.name for reference in extraction.model.applications[0].refs],
            ["ImageWorker"],
        )
        self.assertNotIn("'ImageWorker", extraction.source)
        self.assertNotIn("@{", extraction.source)
        self.assertIn(">double(x:I):I=x*2", extraction.source)
        self.assertEqual(
            len(extraction.source.splitlines()),
            len(source.splitlines()),
        )

    def test_contract_layer_does_not_change_generated_rust(self) -> None:
        plain = ">double(x:I):I=x*2\n"
        contracted = (
            "'@WorkerTask = Worker * App/Task\n"
            "'WorkerJob = {'WorkerTask}\n"
            ">double(x:I):I=x*2 @{'WorkerJob}\n"
        )

        self.assertEqual(compile_source(contracted), compile_source(plain))

    def test_compilation_model_exposes_remapped_contracts(self) -> None:
        model = parse_compilation_model(
            "'@WorkerTask = Worker * App/Task\n"
            "'WorkerJob = {'WorkerTask}\n"
            ">double(x:I):I=x*2 @{'WorkerJob}\n"
        )

        self.assertEqual(model.contracts.declarations[0].line, 1)
        self.assertEqual(model.contracts.applications[0].line, 3)
        self.assertEqual(model.expanded.contracts.declarations[1].name, "WorkerJob")

    def test_contract_and_object_names_are_lexically_distinct(self) -> None:
        source = (
            "+Failed=Temporary|Permanent\n"
            "'@Failed = Worker * App/Task\n"
            "'FailureWorld = {'Failed}\n"
            ">same(value:Failed):Failed=value @{'FailureWorld}\n"
        )

        generated = compile_source(source)

        self.assertIn("pub enum Failed", generated)
        self.assertIn("pub fn same", generated)

    def test_bare_name_cannot_be_used_as_contract(self) -> None:
        with self.assertRaisesRegex(GlyphError, "'Name"):
            compile_source(
                "'@WorkerTask = Worker * App/Task\n"
                ">double(x:I):I=x*2 @{WorkerTask}\n"
            )

    def test_undefined_contract_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "未定義Contract 'Missing'"):
            compile_source(">double(x:I):I=x*2 @{'Missing}\n")

    def test_duplicate_contract_name_is_rejected_across_kinds(self) -> None:
        with self.assertRaisesRegex(GlyphError, "既に定義済み"):
            compile_source(
                "'@Same = Worker * App/Task\n"
                "'>Same = -> I >> <- I\n"
                ">double(x:I):I=x*2\n"
            )

    def test_protocol_uses_unambiguous_arrows(self) -> None:
        valid = (
            "'>RequestReply = -> I >> <- I\n"
            "'Exchange = {'RequestReply}\n"
            ">double(x:I):I=x*2 @{'Exchange}\n"
        )
        self.assertIn("pub fn double", compile_source(valid))

        with self.assertRaisesRegex(GlyphError, "'-> T'"):
            compile_source(
                "'>RequestReply = >I >> <I\n"
                "'Exchange = {'RequestReply}\n"
                ">double(x:I):I=x*2 @{'Exchange}\n"
            )

    def test_contract_cycle_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "Contract cycle: A -> B -> A"):
            compile_source(
                "'A = {'B}\n"
                "'B = {'A}\n"
                ">double(x:I):I=x*2\n"
            )


if __name__ == "__main__":
    unittest.main()
