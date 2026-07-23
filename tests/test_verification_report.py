from __future__ import annotations

import json
import unittest

from glyph import compile_outputs


class VerificationReportTests(unittest.TestCase):
    def test_plain_source_keeps_old_artifact_set(self) -> None:
        outputs = compile_outputs(">double(x:I):I=x*2\n")
        design = json.loads(outputs.design_json)

        self.assertNotIn("verification", design)
        self.assertNotIn("verification-report.json", outputs.diagrams.files)

    def test_glyph04_reports_static_runtime_and_trusted_boundaries(self) -> None:
        source = (
            "'@Worker = Worker * App/Task\n"
            "'>Exchange = -> I >> <- I\n"
            "'!Policy = 'std.timeout(2s) >> 'std.return_error\n"
            "'Use = {'Worker,'Exchange,'Policy}\n"
            ">run(x:own I):I=x @{'Use}\n"
        )
        outputs = compile_outputs(source)
        report = json.loads(outputs.diagrams.files["verification-report.json"])

        self.assertGreater(report["summary"]["static"], 0)
        self.assertGreater(report["summary"]["runtime"], 0)
        self.assertGreater(report["summary"]["trusted"], 0)
        self.assertIn("verification", json.loads(outputs.design_json))


if __name__ == "__main__":
    unittest.main()
