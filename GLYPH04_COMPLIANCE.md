# Glyph 0.4 Compliance and Stabilization Gate

この文書は、Glyph 0.4の実装完了を機能数ではなく、**要件・実装・試験・保証強度の対応**によって判定する。

## Gate

CIは次を実行する。

```bash
python3 scripts/verify_glyph04_stabilization.py \
  --output build/glyph04-stabilization.json

python3 scripts/verify_glyph04_compat.py \
  --base-ref origin/main \
  --output build/glyph04-compatibility.json
```

一つでも不一致があればPRを通さない。

## Machine-readable requirement manifest

`glyph/compliance.py`の`REQUIREMENTS`が正本である。各要件は次を持つ。

```text
id
axis
statement
verification_classes
implementation
positive_tests
negative_tests
static_rule
```

静的規則にはnegative testが必須である。test参照は

```text
tests/file.py::TestClass::test_method
```

の形で記述し、監査時にPython ASTから実在を確認する。単に文書へtest名を書いただけではcoveredと判定しない。

## Requirement axes

現在のmanifestは次を覆う。

| Axis | Main obligation |
|---|---|
| Contract namespace | `Name`と`'Name`の字句分離、bare適用拒否 |
| Capability | move、borrow、`as`変換、共有変更制約 |
| Capability place | aggregate field単位のpartial moveとobligation |
| Resource | state、失敗出口、symbolic identity |
| World / Region | cross-locus call、borrow転送、Region escape |
| Protocol | `->` / `<-`、合成、関数署名整合 |
| Handler | retry、idempotency、rollback、compensation、fallback |
| Law | temporal monitorとruntime obligation |
| Bundle | kind別の直交合成と競合拒否 |
| Public IR | schema、version、条件付き出力 |
| Compatibility | mainとのRust・JSON・diagram・diagnostic一致 |

Host Requirement層は`tests/test_host_requirements.py`とstabilization gateによって追加検証する。これは既存静的規則の置換ではなく、静的に検証済みの意味をHostへ渡す境界の検査である。

詳細な行単位対応は、CI生成物`glyph04-stabilization.json`の`compliance.requirements`に出力する。

## Frozen Glyph 0.4 schemas

0.4 release lineでは次をversion 1として固定する。

```text
glyph.capability-ir
glyph.resource-flow-ir
glyph.contracts
glyph.runtime-contract-ir
glyph.verification-report
glyph.host-requirements
```

正本は`glyph/schema.py::GLYPH04_PUBLIC_SCHEMAS`である。

`tests/test_glyph04_compliance.py`はschema名、version、top-level field集合、resource identity endpointのfield集合を固定する。互換性のないfield変更は、既存version 1を書き換えずversion 2として導入する。

## Host Requirement verification

stabilization gateは次を検査する。

```text
host-requirements-ir.jsonがversion 1の固定shapeを持つ
host-binding.generated.rsが決定的に生成される
生成traitがstandalone rustcを通る
同じGlyph型を異なるWorldで別representation slotにできる
生成traitが特定のownership・runtime・transport・device実装を選ばない
plain sourceではHost Requirement artifactを生成しない
```

Host Requirement層の意味と非目標は`HOST_BINDING_DESIGN.md`を正本とする。

## Legacy main compatibility

`scripts/verify_glyph04_compat.py`は`origin/main`を一時worktreeへ展開し、同じlegacy sourceをmain compilerとPR compilerへ入力する。

比較対象:

```text
generated Rust
host generated Rust
typed design JSON
diagram/IR file集合
各生成fileのbyte列
invalid sourceのexit status
invalid sourceのstdout/stderr diagnostic
```

Glyph 0.4専用sourceは比較対象から除外する。比較対象は0.4導入前から有効なsourceだけである。

## Release metadata

stabilization gateは次の一致も検査する。

```text
VERSION == 0.4.0
pyproject.toml project.version == VERSION
README.md identifies Glyph 0.4
LANGUAGE.md identifies Glyph Language 0.4
CONTRACTS.md identifies Glyph 0.4
HOST_BINDING_DESIGN.md identifies Glyph 0.4
IMPLEMENTATION_STATUS.md identifies Glyph 0.4
```

## Guarantee classes

```text
static   compilerが決定的に検査
model    時相式・有限modelで検査
runtime  生成monitorまたはHost event monitorで検査
trusted  Host Bindingまたは設計者が満たす証明義務
```

`verification-report.json`とcompliance manifestは同じ4分類だけを使用する。新しい曖昧な保証分類を追加しない。

## Release decision

Glyph 0.4 compilerは次の全条件を満たした場合だけrelease candidateとする。

```text
[ ] requirement manifestに未解決errorがない
[ ] 全static ruleにnegative evidenceがある
[ ] complete Glyph 0.4 exampleが決定的に生成される
[ ] complete exampleのRustがrustcを通る
[ ] generated Host Binding traitがrustcを通る
[ ] 6個のPublic IR schemaがversion 1のまま一致する
[ ] legacy sourceがmainとbyte-for-byte一致する
[ ] legacy diagnosticとexit statusがmainと一致する
[ ] release metadataと文書versionが一致する
[ ] trusted Host obligationがverification reportとHost Requirement IRへ残る
```

このgateは、PRをReady化またはmergeする操作ではない。PR #10は明示指示があるまでDraft・未マージを維持する。
