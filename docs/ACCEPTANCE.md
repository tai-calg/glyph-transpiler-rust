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

- `system DoorController=control`から実呼出しだけを導出する
- `ext sensor():Input`が型付き外部componentとして解決される
- 認証と判断を分離した`:=`アルゴリズム
- 状態機械
- 施錠期限とこじ開け安全条件
- `!lock`と`!alarm`の作用境界
- raw macro `DOOR_FLOW`が実行式へ展開される

期待される設計view:

```text
control -> sensor
control -> step -> decide -> authenticate
control -> apply -> lock
                 -> alarm
```

図中のすべてのnodeとedgeは実際の宣言とcall siteを持つ。未宣言名をexternalとして補うことはない。

## Compute batch runtime

`examples/acceptance/job_scheduler.glyph`

これは人員や雇用の割当ではなく、計算機上のbatchを空きlaneへ配置する例である。

検証対象:

- `system BatchRuntime=run`から実呼出しを導出する
- `/> validate?`と`/> build_batch?`のErr経路
- `~layout_lane`というRust実装の純粋境界
- `!submit_batch`という外部作用境界
- pipeline lambdaによるbatch size制限
- `manual.rs`のuser ownership

`~`、`ext`、`!`は同じ設計境界として扱ってはならない。

```text
layout_lane   rust / pure / manual.rs
submit_batch  effect / host adapter
ext           external component / host adapter
```

## Motor safety

`examples/acceptance/motor_safety.glyph`

検証対象:

- `system MotorSafety=cycle`から`cycle -> step -> decide`を導出する
- `@NORMALIZE ... @end`による複数行アルゴリズム展開
- lambda pipeline
- emergency/fault時の停止判断
- Motor state machine
- 100ms以内の停止制約
- `!write_motor`だけが外部作用であること
- 展開後の`normalized`が元の`NORMALIZE`呼出し行へmapされること

## 固定する不変条件

自動試験は次を固定する。

1. 同一sourceからRust・typed design・全diagram artifactが決定的に生成される。
2. 公開JSONは`schema`と`version`を持つ。
3. `logic.mmd`と`algorithm-ir.json`へ`__glyph_*`が漏れない。
4. system nodeはすべて宣言済みcallableへ解決される。
5. system edgeはentryから到達する実call siteだけで構成される。
6. 未宣言entry、未宣言call、架空assertion edgeはコンパイルエラーになる。
7. DoorのArchitecture、Machine、Temporal constraintsが同時に存在する。
8. Compute batch runtimeでRust境界、effect境界、Err経路が区別される。
9. `manual.rs`は再buildで上書きされない。
10. Motorの複数行macroは元の呼出し行へremapされる。
11. Algorithm IRのbinding順と生成Rustの`let`順が一致する。

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

Golden fileの全文を固定するのではなく、schema、順序、境界、source ownershipなどの意味的不変条件を検査する。整形だけの変更で大量のsnapshot更新を発生させないためである。

## 完了条件

- 3 exampleが`glyphc --check`を通る
- acceptance testsが通る
- system/extのnegative testsが通る
- Chromium I/O検証が通る
- 全CIが成功する
- Draft解除とmergeは人間が明示的に判断する
