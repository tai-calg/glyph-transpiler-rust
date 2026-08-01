from __future__ import annotations

import unittest

from glyph.io_state_views import empty_io_state_views
from glyph.state_transition_contract import (
    RAW_STATE_TRANSITION_IR_VERSION,
    STATE_TRANSITION_IR_SCHEMA,
    raw_transition_ir_marker,
)


class StateTransitionContractOwnershipTests(unittest.TestCase):
    def test_empty_views_use_the_central_raw_ir_marker(self) -> None:
        marker = empty_io_state_views()["state_transition_ir"]

        self.assertEqual(marker, raw_transition_ir_marker())
        self.assertEqual(marker["schema"], STATE_TRANSITION_IR_SCHEMA)
        self.assertEqual(marker["version"], RAW_STATE_TRANSITION_IR_VERSION)
        self.assertEqual(marker["stage"], "normalized-machine")


if __name__ == "__main__":
    unittest.main()
