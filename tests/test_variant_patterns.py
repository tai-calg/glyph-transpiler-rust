from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from glyph import GlyphError, compile_source


SYSTEM_SOURCE = """
+C=Stop|Run(u)
+Mode=Idle|Running|Stopping
+Event=Fault{code:u,active:b}|Clear
+Pair=Both(u,u)
*System(mode:Mode,sequence:u,command:C)

>transition(system:System,command:C):System
  command=Run(system.sequence)>>System(Running,system.sequence+1,command)
  command=Run(speed)>>System(Running,system.sequence+1,Run(speed))
  command=Stop>>System(Stopping,system.sequence+1,Stop)
  _>>system

>fault_code(event:Event):u
  event=Fault(code,_)>>code
  _>>0

>same(x,y:u):b
  x=y>>true
  _>>false
""".lstrip()


class VariantPatternTests(unittest.TestCase):
    def test_value_binding_wildcard_and_unit_patterns_generate(self) -> None:
        generated = compile_source(SYSTEM_SOURCE)

        self.assertIn("if let C::Run(__glyph_match_7_0) = (command).clone()", generated)
        self.assertIn("__glyph_match_7_0 == system.sequence", generated)
        self.assertIn("let speed = __glyph_match_7_0;", generated)
        self.assertIn("if let C::Stop = (command).clone()", generated)
        self.assertIn("Event::Fault { code: __glyph_match_13_0, active: _ }", generated)
        self.assertIn("let code = __glyph_match_13_0;", generated)

    def test_non_variant_equality_remains_boolean_comparison(self) -> None:
        generated = compile_source(SYSTEM_SOURCE)
        self.assertIn("if x == y {", generated)

    def test_pattern_arity_is_checked(self) -> None:
        with self.assertRaisesRegex(GlyphError, "variant pattern Run は1引数"):
            compile_source(
                "+C=Stop|Run(u)\n"
                ">f(command:C):u\n"
                "  command=Run()>>1\n"
                "  _>>0\n"
            )

    def test_duplicate_binding_is_rejected(self) -> None:
        with self.assertRaisesRegex(GlyphError, "束縛名 'x' が重複"):
            compile_source(
                "+Pair=Both(u,u)\n"
                ">f(pair:Pair):u\n"
                "  pair=Both(x,x)>>x\n"
                "  _>>0\n"
            )

    @unittest.skipUnless(shutil.which("rustc"), "rustc is required for generated Rust validation")
    def test_generated_patterns_compile_and_preserve_subject_ownership(self) -> None:
        generated = compile_source(SYSTEM_SOURCE)
        main = generated + """

fn main() {
    let base = System {
        mode: Mode::Idle,
        sequence: 7,
        command: C::Stop,
    };

    let exact = transition(base.clone(), C::Run(7));
    assert_eq!(exact.mode, Mode::Running);
    assert_eq!(exact.command, C::Run(7));

    let bound = transition(base.clone(), C::Run(9));
    assert_eq!(bound.mode, Mode::Running);
    assert_eq!(bound.command, C::Run(9));

    let stopped = transition(base.clone(), C::Stop);
    assert_eq!(stopped.mode, Mode::Stopping);
    assert_eq!(stopped.command, C::Stop);

    assert_eq!(fault_code(Event::Fault { code: 42, active: true }), 42);
    assert!(same(3, 3));
    assert!(!same(3, 4));
}
"""

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "main.rs"
            binary = root / "pattern-test"
            source.write_text(main, encoding="utf-8")
            subprocess.run(
                ["rustc", "--edition=2021", str(source), "-o", str(binary)],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run([str(binary)], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
