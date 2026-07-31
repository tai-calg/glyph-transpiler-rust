from __future__ import annotations

import unittest

from glyph.readable_diagram_app import _presentation_pipeline
from glyph.state_viewport_reservation import enhance_state_viewport_reservation_html


class StateViewportReservationTests(unittest.TestCase):
    def test_enhancer_is_idempotent_and_reserves_state_canvas(self) -> None:
        source = "<html><head></head><body><div id='view'></div></body></html>"
        enhanced = enhance_state_viewport_reservation_html(source)

        self.assertIn("glyph-state-viewport-reservation-v1-style", enhanced)
        self.assertIn("glyph-state-viewport-reservation-v1-script", enhanced)
        self.assertIn("max-height:min(220px,28dvh)", enhanced)
        self.assertIn("stateViewportReserved", enhanced)
        self.assertIn("window.innerHeight - visibleTop - BOTTOM_MARGIN", enhanced)
        self.assertEqual(
            enhance_state_viewport_reservation_html(enhanced),
            enhanced,
        )

    def test_reservation_is_state_only_and_fail_closed(self) -> None:
        source = "<html><head></head><body><div id='view'></div></body></html>"
        enhanced = enhance_state_viewport_reservation_html(source)

        self.assertIn(
            'document.querySelector(".tab.active")?.dataset.tab !== "state"',
            enhanced,
        )
        self.assertIn('document.querySelector(".state-node")', enhanced)
        self.assertIn("MIN_VISIBLE_HEIGHT = 240", enhanced)
        self.assertIn('reason: "inactive-state-view"', enhanced)

    def test_reservation_precedes_viewport_and_fit_certification(self) -> None:
        names = [enhancer.__name__ for enhancer in _presentation_pipeline()]

        reservation = names.index("enhance_state_viewport_reservation_html")
        viewport = names.index("enhance_diagram_canvas_viewport_html")
        fit = names.index("enhance_diagram_fit_stability_html")

        self.assertLess(reservation, viewport)
        self.assertLess(viewport, fit)


if __name__ == "__main__":
    unittest.main()
