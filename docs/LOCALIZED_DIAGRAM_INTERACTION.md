# Localized diagram interaction contract

## Language

Glyph Studio starts in Japanese. The Settings dialog can switch the presentation language between Japanese and English. The selected locale is stored in `localStorage` under `glyph.ui.locale`.

The locale changes presentation only. Compiler semantics, source text, transition identity and saved node/label positions are not changed.

Machine diagnostics carry `message_ja` and `message_en`. Unknown compiler details retain their original message rather than being rewritten heuristically.

## Transition label proximity

Automatic transition labels are anchored at the geometric midpoint of their SVG path. The label center must remain within 96 CSS pixels of that anchor.

Placement searches concentric candidate rings and rejects collisions with state nodes, I/O nodes and labels already placed. If a full label cannot be placed, the diagram uses its transition ID while the full input/guard/effect text remains in Transition details and the tooltip.

Manual label dragging uses the same 96-pixel tether. Double-clicking a label discards its manual position and returns it to automatic placement.

## Canvas navigation

Dragging an empty part of a diagram pans the canvas. Node and label dragging keeps their existing behavior.

When the internal canvas reaches its vertical boundary, unconsumed drag or wheel motion is handed to the preview pane. This allows the user to recover content clipped by the preview pane's own scroll position without moving the pointer to a narrow outer scrollbar.
