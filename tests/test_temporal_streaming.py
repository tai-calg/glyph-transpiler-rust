from __future__ import annotations

import unittest

from glyph import GlyphError, compile_source


class TemporalStreamingTests(unittest.TestCase):
    def test_supported_shapes_generate_streaming_monitors(self) -> None:
        generated = compile_source(
            "*O(a,b:B)\n"
            "?always(*O)=@A a\n"
            "?eventually(*O)=@E a\n"
            "?within(*O)=@E 5s a\n"
            "?until(*O)=a U b\n"
            "?weak(*O)=a W b\n"
            "?response(*O)=@A(a>>@E 5s b)\n"
            "?live(*O)=@A@E 1s a\n"
            "?converge(*O)=@E@A a\n"
        )
        for name in (
            "AlwaysStreamingMonitor",
            "EventuallyStreamingMonitor",
            "WithinStreamingMonitor",
            "UntilStreamingMonitor",
            "WeakStreamingMonitor",
            "ResponseStreamingMonitor",
            "LiveStreamingMonitor",
            "ConvergeStreamingMonitor",
        ):
            self.assertIn(f"pub struct {name}", generated)

    def test_streaming_monitor_does_not_store_trace(self) -> None:
        generated = compile_source("?safe(p:B)=@A p\n")
        start = generated.index("pub struct SafeStreamingMonitor")
        body = generated[start : generated.index("impl SafeStreamingMonitor", start)]
        self.assertNotIn("Vec<", body)
        self.assertNotIn("trace", body)

    def test_unsupported_general_formula_keeps_reference_only(self) -> None:
        generated = compile_source("?x(a:B,b:B)=@A(a|@E b)\n")
        self.assertIn("pub struct XMonitor", generated)
        self.assertNotIn("pub struct XStreamingMonitor", generated)

    def test_streaming_monitor_name_collision_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "逐次モニタ名"):
            compile_source("*XStreamingMonitor(v:B)\n?x(v:B)=@A v\n")


if __name__ == "__main__":
    unittest.main()
