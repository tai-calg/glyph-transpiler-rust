# Provisional trigger classification — UI appendix

Glyph keeps compilation and preview available when a branch condition is input-derived but the compiler cannot prove whether it is an occurrence or a persistent condition.

```text
input-derived ambiguous condition
    -> warning
    -> provisional trigger
    -> diagram remains editable and exportable
```

A provisional trigger is rendered on the trigger side with a leading `?`. It is not enclosed in guard brackets.

```text
? input.forced_open
? input.request_open [state.failures<3]
```

The default diagnostic presentation is Japanese. The settings dialog can switch the UI and structured diagnostics to English without changing compiler semantics.

Structured machine diagnostics may carry `message_ja`, `message_en`, `help_ja` and `help_en`. The original `message` remains available for compatibility and auditability.
