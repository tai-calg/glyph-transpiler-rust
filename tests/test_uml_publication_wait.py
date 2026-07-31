from __future__ import annotations

import unittest
from pathlib import Path


class UmlPublicationWaitTests(unittest.TestCase):
    def test_browser_campaign_waits_for_final_certified_geometry(self) -> None:
        source = Path("tests/verify_uml_transition_semantics.mjs").read_text(encoding="utf-8")

        self.assertIn('stage?.dataset.initialRouteReady === "true"', source)
        self.assertIn('stage?.dataset.initialRouteCertificate === "valid"', source)
        self.assertIn('stage?.dataset.layoutCertificateState === "valid"', source)
        self.assertIn('stage?.dataset.transitionPublicationReady === "true"', source)


if __name__ == "__main__":
    unittest.main()
