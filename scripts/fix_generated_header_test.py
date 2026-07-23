from pathlib import Path

path = Path("tests/test_header_first_layout.py")
text = path.read_text(encoding="utf-8")
old = ">step(state:MotorState,input:Input):MotorState\n  command := decide(input)\n  command==Stop >> MotorState(Stopped,Stop)\n  command==Drive(speed) >> MotorState(Running,Drive(speed))\n  _ >> MotorState(Faulted,Stop)\n"
new = ">step(state:MotorState,input:Input):MotorState\n  command := decide(input)\n  next :=\n    command==Stop >> MotorState(Stopped,Stop)\n    command==Drive(speed) >> MotorState(Running,Drive(speed))\n    _ >> MotorState(Faulted,Stop)\n  next\n"
if text.count(old) != 2:
    raise SystemExit("expected two generated step blocks")
path.write_text(text.replace(old, new), encoding="utf-8")
Path(__file__).unlink()
