# Glyph v0.1 Acceptance Campaign

このcampaignは、Glyphが実システムの設計骨格を一つのsource of truthとして保持し、Rust・IR・図へ決定的に変換できることを固定する。

## 実行

```bash
python3 glyphc.py examples/acceptance/door_controller.glyph --check
python3 glyphc.py examples/acceptance/job_scheduler.glyph --check
python3 glyphc.py examples/acceptance/motor_safety.glyph --check
python3 -m unittest discover -s tests -p 'test_acceptance_*.py' -v
```

通常の全試験:

```bash
python3 -m unittest discover -s tests -v
```

## Door controller

`examples/acceptance/door_controller.glyph`

検証対象:

- `system DoorController`がentry、typed port、境界flowを先に示す
- caller stateと`ext sensor():Input|ControlError`を入力極性として区別する
- 認証、判断、状態遷移、作用選択を独立関数へ分離する
- `machine Door`が永続状態だけを表す
- 施錠期限とこじ開け安全条件
- `!lock`と`!alarm`の作用境界
- Alarm経路と通常経路で外部作用が排他的に一つだけ選択される
- 正常経路が確認済み`Receipt`へ、失敗経路が`ControlError`へ到達する

期待されるSystem Context:

```text
state  ──data──> control ──returns──> receipt
sensor ──data──> control
control ──effect──> lock
control ──effect──> alarm
```

`authenticate`、`decide`、`step`、`apply`は実装call graphには存在するが、公開境界へ自動混入させない。

## Compute batch runtime

`examples/acceptance/job_scheduler.glyph`

これは人員や雇用の割当ではなく、計算機上のbatchを空きlaneへ配置する例である。

検証対象:

- `system BatchRuntime`がinput、receipt、manual Rust依存、effectを明示する
- `/> validate?`と`/> build_batch?`のErr経路
- `~layout_lane`というRust実装の純粋境界
- `!submit_batch`という外部作用境界
- pipeline lambdaによるbatch size制限
- `manual.rs`のuser ownership

```text
layout_lane   rust / pure / manual.rs
submit_batch  effect / host adapter
ext           external input or provider / host adapter
```

`~`、`ext`、`!`を同じ設計境界として扱ってはならない。

## Motor safety

`examples/acceptance/motor_safety.glyph`

検証対象:

- `system MotorSafety`がstate、input、receipt、`write_motor`を明示する
- `normalize`を名前付き純粋helperとして分離する
- emergency/fault時の停止判断
- `machine Motor`による永続状態遷移
- 100ms以内の停止制約
- `!write_motor`だけが外部作用であること
- ファイル名、内容、Acceptance testが同じMotor Safety責務を持つこと

温度変換の純粋UI例は`examples/temperature_view.glyph`へ分離する。

## 固定する不変条件

自動試験は次を固定する。

1. 同一sourceからRust・typed design・全diagram artifactが決定的に生成される。
2. 公開JSONは`schema`と`version`を持つ。
3. `logic.mmd`と`algorithm-ir.json`へ`__glyph_*`が漏れない。
4. system endpointはportまたは宣言済みsymbolへ解決される。
5. system edgeにはentry parameter、external read、return type、call path、effect reachabilityの証拠がある。
6. 未宣言entry、未宣言call、架空edge、極性逆転はコンパイルエラーになる。
7. DoorのSystem Context、Machine、Temporal constraintsが同時に存在する。
8. Compute batch runtimeでRust境界、effect境界、Err経路が区別される。
9. `manual.rs`は再buildで上書きされない。
10. Motorの正規化はraw macroではなく明示helperとして生成Rustに残る。
11. Algorithm IRのbinding順と生成Rustの`let`順が一致する。
12. 明示systemのI/O viewと実装call graphを混同しない。
13. demo crateはHost実装と生成moduleを無条件にpublicへしない。
14. test用故障注入・call logをcrate外の本番APIへ公開しない。

## Machine-readable artifacts

各exampleから少なくとも次を生成する。

```text
preprocessor-map.json
architecture-ir.json
algorithm-ir.json
execution-ir.json
source-map.json
typed-ast.json
logic.mmd
machine-*.mmd
temporal.mmd
generated.rs
host.generated.rs
manual.rs scaffold
```

Golden file全文ではなく、schema、順序、境界、証拠、source ownershipなどの意味的不変条件を検査する。整形だけの変更で大量のsnapshot更新を発生させない。

## 完了条件

- 3 acceptance exampleが`glyphc --check`を通る
- acceptance testsが通る
- system/ext/effectのnegative testsが通る
- Chromium I/O検証が通る
- full Python suite、Rust tests、Clippyが成功する
- Draft解除とmergeは人間が明示的に判断する
