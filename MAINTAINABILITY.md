# Glyph Maintainability Boundaries

この文書はGlyph 0.4実装の責務境界と、将来の変更で守るべき保守性規則を定める。

## 1. Stable package facade

`glyph/__init__.py`は利用者向けの安定facadeである。

- 0.4内部IR、validator、builder、code generatorを再exportしない。
- 新機能は責務別moduleから明示importする。
- package rootの公開集合は`tests/test_public_api.py`で固定する。
- 内部構造を公開APIへ昇格する場合は、独立した互換性判断を行う。

## 2. Dependency direction

依存は次の方向だけを許可する。

```text
shared constants / lexical utilities
    ↓
IR data models
    ↓
parsers / semantic builders / validators
    ↓
derived-model facade
    ↓
JSON / Rust / diagram projections
    ↓
compilation orchestration / CLI
```

禁止する依存:

- IR modelからbuilderへの依存
- schema定義からprojectionへの依存
- projectionからparser内部状態への直接依存
- package rootを内部module間のimport hubとして使うこと
- runtime具体型をsemantic IRへ持ち込むこと

`tests/test_module_boundaries.py`が主要な依存境界を検査する。

## 3. Single sources of truth

次を複数箇所へ複製しない。

- 型短縮規則: `glyph/type_shortcuts.py`
- Public IR schema名・version・top-level shape: `glyph/schema.py`
- verification class: `glyph/verification_classes.py`
- Host Requirement IR: `glyph/host_requirements.py`
- Host Requirement導出: `glyph/host_requirement_builder.py`

試験やstabilization scriptも正本をimportして使用する。

## 4. Compilation boundaries

`glyph/artifacts.py`が次を所有する。

- preprocess後の共通core parse
- macro / block / lambda / machineのlowering
- validation
- source-line remap
- Rust artifacts

legacyとGlyph 0.4は共通coreを通る。分岐してよいのは、0.4 opt-in判定、0.4専用前処理、追加意味検査だけである。

`glyph/glyph04_derived.py`は次を一回だけ導出する。

- resource flow
- verification report
- Host requirements

JSON、diagram、Rust scaffoldの各projectionで再計算しない。

## 5. Host Binding boundaries

Host Bindingは三層に分離する。

```text
host_requirements.py
    immutable IR data contract

host_requirement_builder.py
    Capability / Resource / Contractからの意味導出

host_binding_codegen.py
    Rust trait projection
```

IR層はbuilderや具体runtimeへ依存しない。

Host operation portは必ずrepresentation slotを持つ。`OpaqueValue`のようなcatch-all型で型情報の欠落を隠さない。

生成される`HostRequirementContext`のfieldはprivateとし、constructorとread-only accessorだけを公開する。

## 6. Semantic safety rules

- 同型resource入力が複数あり、出力identityを一意に決められない場合は拒否する。
- resource flowで型名をdictionary keyとして単一値へ上書きしない。
- Protocolのchoice、parallel、repeat、sequenceを単純な線形event列へ潰さない。
- nullable fieldで不可能状態を表現しない。
- `assert`をユーザー入力の意味検査に使用しない。
- 未知のverification classを黙って受理しない。

## 7. Remaining debt

以下は今後の分割対象だが、今回のrefactorでは動作リスクを避けて一括変更していない。

- `glyph/capabilities.py`: IR、surface extraction、flow analysisがまだ同居している。
- `glyph/contract_semantics.py`: Protocol parser、Contract row構築、式解析が同居している。
- `glyph/compilation.py`: diagram projectionが複数形式のserializationを集約している。
- `glyph/mermaid.py`: 一部helperがprivate名のまま別moduleから利用されている。
- 生成Rustは既存generatorの一部private methodへ依存している。

これらは、既存のmain byte-compatibility gateを維持しながら、小さいPRまたは独立commit単位で分割する。

## 8. Change acceptance

refactorは次をすべて満たす必要がある。

```text
[ ] package root APIが意図せず増えない
[ ] legacy生成物・diagnosticがmainとbyte一致する
[ ] Glyph 0.4 Public IR schemaが変わらない
[ ] derived modelを一回だけ構築する
[ ] IR → builder → projectionの依存方向を逆転させない
[ ] generated RustとHost Binding traitがrustcを通る
[ ] Python tests、acceptance、Rust tests、Clippyが成功する
```
