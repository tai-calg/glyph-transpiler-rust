from __future__ import annotations


def install_exact_completion_fast_publication() -> None:
    """Publish an exact lexical snapshot without waiting for another animation frame."""

    from . import editor_completion

    script = editor_completion._SCRIPT
    schedule_old = (
        "function schedule(options={}){if(frame)cancelAnimationFrame(frame);"
        "frame=requestAnimationFrame(()=>update(options))}"
    )
    schedule_new = (
        "function schedule(options={}){if(frame)cancelAnimationFrame(frame);"
        "frame=requestAnimationFrame(()=>update(options))}\n"
        "function updateExact(options={}){"
        "if(frame){cancelAnimationFrame(frame);frame=0}"
        "metrics.fastExactUpdates=(metrics.fastExactUpdates||0)+1;update(options)}"
    )
    listener_old = (
        '  if(document.activeElement===editor)schedule({allowEmpty:explicit});\n'
        '});'
    )
    listener_new = (
        '  if(document.activeElement===editor){'
        'if(event.detail?.exact)updateExact({allowEmpty:explicit});'
        'else schedule({allowEmpty:explicit})}\n'
        '});'
    )
    if schedule_old not in script:
        raise RuntimeError("editor completion schedule contract changed")
    if listener_old not in script:
        raise RuntimeError("editor completion lexical-update contract changed")
    editor_completion._SCRIPT = script.replace(schedule_old, schedule_new, 1).replace(
        listener_old, listener_new, 1
    )


__all__ = ["install_exact_completion_fast_publication"]
