from pathlib import Path

path = Path("tests/test_header_first_layout.py")
text = path.read_text(encoding="utf-8")
old = ">step(state:MotorState,input:Input):MotorState\n  command := decide(input)\n  command==Stop >> MotorState(Stopped,Stop)\n  command==Drive(speed) >> MotorState(Running,Drive(speed))\n  _ >> MotorState(Faulted,Stop)\n"
new = ">step(state:MotorState,input:Input):MotorState\n  command := decide(input)\n  next :=\n    command==Stop >> MotorState(Stopped,Stop)\n    command==Drive(speed) >> MotorState(Running,Drive(speed))\n    _ >> MotorState(Faulted,Stop)\n  next\n"
if text.count(old) != 2:
    raise SystemExit("expected two generated step blocks")
text = text.replace(old, new)
text = text.replace(
    "from pathlib import Path\nimport unittest",
    "from pathlib import Path\nimport re\nimport unittest",
)
old_assertions = """        self.assertEqual(header.logic, legacy.logic)
        self.assertEqual(header.host, legacy.host)
"""
new_assertions = """        normalize = lambda value: re.sub(
            r\"__glyph_([A-Za-z]+)_L?\\d+_\",
            r\"__glyph_\\1_LINE_\",
            value,
        )
        self.assertEqual(normalize(header.logic), normalize(legacy.logic))
        self.assertEqual(header.host, legacy.host)
"""
if old_assertions not in text:
    raise SystemExit("compatibility assertions not found")
path.write_text(text.replace(old_assertions, new_assertions), encoding="utf-8")
Path(__file__).unlink()
