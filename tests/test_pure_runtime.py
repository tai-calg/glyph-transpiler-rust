from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from glyph.compilation import CompilationPipeline
from glyph.pure_runtime import (
    LivePureGlyphRuntime,
    PureGlyphProgram,
    PureRuntimeError,
    glyph_to_python,
)


TEMPERATURE_SOURCE = """\
+TemperatureBand=Invalid|Freezing|Cold|Comfortable|Warm|Hot
*TemperatureInput(celsius:F)
*TemperatureView(celsius:F,fahrenheit:F,kelvin:F,count:U,valid:B,band:TemperatureBand)
*Session(count:U)
>to_fahrenheit(celsius:F):F=celsius*1.8+32.0
>to_kelvin(celsius:F):F=celsius+273.15
>next_count(count:U):U=count+1
>is_valid(celsius:F):B=celsius>=-273.15
>classify(celsius:F):TemperatureBand
  !is_valid(celsius) >> Invalid
  celsius<=0.0 >> Freezing
  celsius<18.0 >> Cold
  celsius<27.0 >> Comfortable
  celsius<35.0 >> Warm
  _ >> Hot
>render(input:TemperatureInput,session:Session):TemperatureView=TemperatureView(input.celsius,to_fahrenheit(input.celsius),to_kelvin(input.celsius),next_count(session.count),is_valid(input.celsius),classify(input.celsius))
"""


class PureGlyphProgramTests(unittest.TestCase):
    def test_executes_nested_pure_calls_products_guards_and_variants(self) -> None:
        compilation = CompilationPipeline().compile_text(TEMPERATURE_SOURCE)
        program = PureGlyphProgram(compilation.model)

        result = program.invoke(
            "render",
            {
                "input": {"celsius": 20.0},
                "session": {"count": 2},
            },
        )
        value = glyph_to_python(result)

        self.assertEqual(value["celsius"], 20.0)
        self.assertAlmostEqual(value["fahrenheit"], 68.0)
        self.assertAlmostEqual(value["kelvin"], 293.15)
        self.assertEqual(value["count"], 3)
        self.assertTrue(value["valid"])
        self.assertEqual(value["band"]["variant"], "Comfortable")

    def test_rejects_effect_boundary_instead_of_guessing_a_host(self) -> None:
        source = "!read_sensor():U\n>run():U=read_sensor()\n"
        compilation = CompilationPipeline().compile_text(source)
        program = PureGlyphProgram(compilation.model)

        with self.assertRaisesRegex(PureRuntimeError, "effect boundary"):
            program.invoke("run", {})

    def test_rejects_missing_and_unknown_product_fields(self) -> None:
        compilation = CompilationPipeline().compile_text(TEMPERATURE_SOURCE)
        program = PureGlyphProgram(compilation.model)

        with self.assertRaisesRegex(PureRuntimeError, "missing: celsius"):
            program.invoke(
                "render",
                {"input": {}, "session": {"count": 0}},
            )
        with self.assertRaisesRegex(PureRuntimeError, "unknown: extra"):
            program.invoke(
                "render",
                {
                    "input": {"celsius": 20.0, "extra": 1},
                    "session": {"count": 0},
                },
            )


class LivePureGlyphRuntimeTests(unittest.TestCase):
    def test_hot_swap_changes_executable_world_without_python_formula_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "temperature.glyph"
            source_path.write_text(TEMPERATURE_SOURCE, encoding="utf-8")
            runtime = LivePureGlyphRuntime(source_path)
            try:
                first = runtime.invoke(
                    "render",
                    {
                        "input": {"celsius": 20.0},
                        "session": {"count": 0},
                    },
                    refresh=False,
                )
                self.assertEqual(first.world_version, 1)
                self.assertAlmostEqual(first.to_python()["fahrenheit"], 68.0)

                changed = TEMPERATURE_SOURCE.replace(
                    "celsius*1.8+32.0",
                    "celsius*2.0+30.0",
                )
                source_path.write_text(changed, encoding="utf-8")
                self.assertTrue(runtime.refresh(force=True))

                second = runtime.invoke(
                    "render",
                    {
                        "input": {"celsius": 20.0},
                        "session": {"count": 1},
                    },
                    refresh=False,
                )
                self.assertEqual(second.world_version, 2)
                self.assertAlmostEqual(second.to_python()["fahrenheit"], 70.0)
                self.assertIsNone(runtime.state_dict()["pending_patch"])
            finally:
                runtime.stop()

    def test_compile_error_keeps_last_executable_world(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "temperature.glyph"
            source_path.write_text(TEMPERATURE_SOURCE, encoding="utf-8")
            runtime = LivePureGlyphRuntime(source_path)
            try:
                source_path.write_text(
                    "*TemperatureView(\n",
                    encoding="utf-8",
                )
                self.assertFalse(runtime.refresh(force=True))
                self.assertIsNotNone(runtime.last_error)
                self.assertIn("閉じられていない", runtime.last_error or "")

                result = runtime.invoke(
                    "render",
                    {
                        "input": {"celsius": 0.0},
                        "session": {"count": 0},
                    },
                    refresh=False,
                )
                self.assertEqual(result.world_version, 1)
                self.assertAlmostEqual(result.to_python()["fahrenheit"], 32.0)
            finally:
                runtime.stop()


if __name__ == "__main__":
    unittest.main()
