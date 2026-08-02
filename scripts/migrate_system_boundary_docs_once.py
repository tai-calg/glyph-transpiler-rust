from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
LANGUAGE = ROOT / "docs" / "LANGUAGE.md"
SELF = Path(__file__).resolve()


readme = README.read_text(encoding="utf-8")
readme_replacements = {
    "| `->` | `system`内 | 公開境界上のflow |\n": "",
    "| `system Name` | システム境界 | 公開I/Oと作用flowを宣言する |":
        "| `system Name` | システム境界 | `entry`、`source`、`sink`となる関数を宣言する |",
    """## 10. System Context

`system`は外部から見える入力、出力、作用の関係を宣言します。自由な作図命令ではありません。

```glyph
system MotorSafety
  entry cycle

  in state:MotorState
  in input:Input
  out receipt:Receipt

  state -> cycle
  input -> cycle
  cycle -> receipt
  cycle -> write_motor
```

コンパイラは次を確認します。

- endpointが宣言済みの型・関数・作用へ解決される
- port型が一致する
- edgeにコード上の根拠がある
- 到達可能な外部入力と作用が境界へ表れる

`System Context`と内部call graphは別の関係です。

```text
System Context: input -> cycle -> receipt / write_motor
Call graph:     cycle -> step -> decide -> normalize
```
""": """## 10. System境界

`system`は値や型や矢印を再宣言せず、外部境界となる関数名だけを宣言します。

```glyph
system MotorSafety
  entry cycle
  source sensor
  sink write_motor
```

- `entry`は外部からinvokeされるSystem内部の`>`関数
- `source`はSystemが呼び出して値を取得する`ext`関数
- `sink`はSystemが呼び出して外部作用を要求する`!`関数

関数の引数と完全な戻り型がSystemの入出力契約です。`Receipt|ControlError`の失敗側を境界から落としません。

```glyph
ext sensor():Input|SensorError
!write_motor(command:Command):Receipt|MotorError

>cycle(state:MotorState):Receipt|ControlError
  input := sensor()?
  command := decide(state,input)
  write_motor(command)
```

コンパイラは`entry`から実コードのcall graphを辿り、次を検査します。

- entry、source、sinkが宣言種別と一致する
- 宣言したsourceとsinkへentryから到達できる
- 到達可能なsourceとsinkの宣言漏れがない
- 未宣言関数への呼出しがない
- 正常型と失敗型を含む完全な関数シグネチャが保持される

System図のノードは関数だけ、矢印は常に関数呼出しだけです。値と型は関数ノードの引数・戻り値として表示します。通常の`>`関数と`~`のRust実装純粋関数は、entryから到達すれば`INTERNAL`として自動収集されます。

```text
[ENTRY] cycle(state: MotorState) -> Receipt | ControlError
    calls -> [SOURCE] sensor() -> Input | SensorError
    calls -> [INTERNAL] decide(state, input) -> Command
    calls -> [SINK] write_motor(command) -> Receipt | MotorError
```

旧`in`、`out`、System内の`a -> b`は移行用に読み込める場合がありますが、正規のArchitecture IRや図を定義しません。
""",
    "| System Context | typed architecture / data-flow | endpoint解決、型整合、code evidence、図生成 | 外部装置・network・driverの正しさ |":
        "| System境界 | typed call graph / effect boundary | entry/source/sink検査、到達可能call graph、完全な関数signature、図生成 | 外部装置・network・driverの正しさ |",
    "- コード根拠を要求するSystem Context":
        "- entryから導出した完全な関数実行境界",
    """### `system`の矢印を自由な作図として使う

`system`のedgeは、実際の型、戻り値、呼出し、外部作用と一致する必要があります。
""": """### `system`へ値や手書き矢印を書く

```glyph
system Wrong
  in input:Input
  out receipt:Receipt
  input -> control
  control -> receipt
```

Systemには関数境界だけを書きます。

```glyph
system Correct
  entry control
  source sensor
  sink actuator
```

値、型、正常・失敗戻り、関数呼出しは実コードから導出されます。
""",
}
for old, new in readme_replacements.items():
    count = readme.count(old)
    if count != 1:
        raise SystemExit(f"README replacement count {count}: {old[:80]!r}")
    readme = readme.replace(old, new)
README.write_text(readme, encoding="utf-8")

language = LANGUAGE.read_text(encoding="utf-8")
old_effect = """### External effect boundary

```glyph
!send(x:u8):u8|Error
```

A prototype implementation may be attached:

```glyph
!send(x:u8):u8|Error=Ok(x)
```
"""
new_effect = """### External input and effect boundaries

```glyph
ext sensor():Input|SensorError
!send(x:u8):u8|Error
```

`ext` is a pull-style external source called by the System. `!` is an outbound external effect. A prototype implementation may be attached to an effect:

```glyph
!send(x:u8):u8|Error=Ok(x)
```

### System boundary

```glyph
system Controller
  entry control
  source sensor
  sink send
```

`entry` names a `>` function invoked from outside. `source` names a reachable `ext` function. `sink` names a reachable `!` function. Function signatures define all request, response, success, and failure types. System edges are derived calls; values and types are not System nodes. Reachable `>` and `~` functions are internal nodes and are not listed in the System block.
"""
if language.count(old_effect) != 1:
    raise SystemExit("LANGUAGE external-boundary section did not match")
language = language.replace(old_effect, new_effect)

old_compat = "Existing macros, types, functions, guards, effects, systems, machines, diagrams, and temporal syntax remain valid."
new_compat = "Existing macros, types, functions, guards, effects, machines, diagrams, and temporal syntax remain valid. Legacy System `in` / `out` / `->` blocks may be read during migration, but only `entry` / `source` / `sink` and the executable call graph define the canonical System architecture."
if language.count(old_compat) != 1:
    raise SystemExit("LANGUAGE compatibility sentence did not match")
language = language.replace(old_compat, new_compat)

old_grammar = """program              := (macro | declaration | temporal-spec | resource | contract)*
macro                := "@" Name "=" expr
declaration          := product | sum | alias | function | extern
product              := "*" Name "(" compact-fields? ")" contract-application?
sum                  := "+" Name "=" variant ("|" variant)*
alias                := "=" Name "=" compact-type
function             := ">" signature ("=" expr | NEWLINE block) contract-application?
extern               := "!" signature ("=" expr)? contract-application?
"""
new_grammar = """program              := (macro | declaration | system | temporal-spec | resource | contract)*
macro                := "@" Name "=" expr
declaration          := product | sum | alias | function | opaque | source | effect
product              := "*" Name "(" compact-fields? ")" contract-application?
sum                  := "+" Name "=" variant ("|" variant)*
alias                := "=" Name "=" compact-type
function             := ">" signature ("=" expr | NEWLINE block) contract-application?
opaque               := "~" signature
source               := "ext" signature
effect               := "!" signature ("=" expr)? contract-application?
system               := "system" Name NEWLINE INDENT system-entry system-source* system-sink*
system-entry         := "entry" Name
system-source        := "source" Name
system-sink          := "sink" Name
"""
if language.count(old_grammar) != 1:
    raise SystemExit("LANGUAGE grammar section did not match")
language = language.replace(old_grammar, new_grammar)
LANGUAGE.write_text(language, encoding="utf-8")
SELF.unlink()
