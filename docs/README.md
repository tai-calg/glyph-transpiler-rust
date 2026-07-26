# Glyph Documentation

Glyphの文書を目的別に整理しています。初めて使う場合は、まずルートの[README](../README.md)を読んでください。

## 最初に読む文書

- [公開README・導入・文法一覧](../README.md)
- [Glyph Language 0.4](LANGUAGE.md)
- [短縮構文](COMPACT_SYNTAX.md)
- [図の編集、拡大縮小、出力](DIAGRAM_EDITOR.md)
- [I/O図と状態遷移図](IO_STATE_APP.md)

## 基本文法と実装境界

- [raw preprocessor](PREPROCESSOR.md)
- [`/>`パイプラインとラムダ](PIPELINE_DESIGN.md)
- [条件分岐とRust TODO契約](RUST_TODO.md)
- [enum variant guard patterns](VARIANT_PATTERNS.md)
- [500文字ソフトウェアスケッチ](SKETCH_DESIGN.md)
- [Source-level Algorithm IR](ALGORITHM_IR.md)

## システム構造と生成物

- [Compilation Pipeline and IR Schemas](COMPILATION_PIPELINE.md)
- [Glyph execution structure](EXECUTION_STRUCTURE.md)
- [Glyph Host Binding Contract](HOST_BINDING_DESIGN.md)
- [Public Glyph UI Platform](PUBLIC_UI.md)
- [Glyph Public UI SDK](PUBLIC_UI_SDK.md)
- [Glyph UI IR and Generic Gradio Renderer](UI_IR.md)
- [Glyph Gradio Live Host](GRADIO_HOST.md)

## 状態、時間、検証

- [Glyph temporal constraints](TEMPORAL.md)
- [時相制約設計書](TEMPORAL_DESIGN.md)
- [時相制約 実装状況](TEMPORAL_IMPLEMENTATION_STATUS.md)
- [Glyph Type Algebra IR](TYPE_ALGEBRA_IR.md)
- [Glyph Monoidal IR](MONOIDAL_IR.md)
- [Glyph 0.4 Compliance and Stabilization Gate](GLYPH04_COMPLIANCE.md)
- [Glyph v0.1 Acceptance Campaign](ACCEPTANCE.md)
- [検証記録](VERIFICATION.md)

## Capability、Resource、Contract

- [Glyph 0.4 — Capability, Resource and Kinded Contract Space](CONTRACTS.md)
- [Glyph 0.4 Implementation Status](IMPLEMENTATION_STATUS.md)

## Studioと開発環境

- [Glyph Studio UX](STUDIO_UX.md)
- [Glyph Studio 0.4 Orthogonal Views](STUDIO_04_DESIGN.md)
- [Glyph Studio Semantic Navigation](STUDIO_SEMANTIC_NAVIGATION.md)
- [Glyph: expression trees and one-process development environment](LISP_CORE.md)
- [Glyph Maintainability Boundaries](MAINTAINABILITY.md)

## プロジェクト管理

- [設計書](DESIGN.md)
- [Changelog](CHANGELOG.md)
- [PR #10 Implementation Notes](PR_IMPLEMENTATION_NOTES.md)
