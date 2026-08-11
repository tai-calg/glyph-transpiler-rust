from __future__ import annotations


def install_adaptive_lexical_schedule() -> None:
    """Replace the fixed lexical debounce with a bounded adaptive scheduler."""

    from . import editor_lexical_runtime

    script = editor_lexical_runtime._SCRIPT
    old_constant = "const DEBOUNCE_MS=32;"
    old_schedule = """function schedule({immediate=false,invalidate=false}={}){
  clearTimer();
  if(invalidate)invalidateSnapshot();
  const run=()=>{
    timer=0;
    const request=buildRequest();
    if(recoveryExhausted||recoveryFailures>0){pending=request;metrics.maxPendingDepth=Math.max(metrics.maxPendingDepth,1);return}
    if(inFlight){pending=request;metrics.maxPendingDepth=Math.max(metrics.maxPendingDepth,1);return}
    send(request);
  };
  if(immediate)run();else timer=setTimeout(run,DEBOUNCE_MS);
}"""
    new_constant = "const MIN_DEBOUNCE_MS=6,MID_DEBOUNCE_MS=12,MAX_DEBOUNCE_MS=20;"
    new_schedule = """function adaptiveDebounceMs(){
  const now=performance.now(),last=Number(metrics.lastScheduleAt||0);
  const delta=last?now-last:Number.POSITIVE_INFINITY;
  metrics.lastScheduleAt=now;
  const burst=delta<45?Math.min(4,Number(metrics.scheduleBurst||0)+1):0;
  metrics.scheduleBurst=burst;
  const delay=burst>=3?MAX_DEBOUNCE_MS:burst>=1?MID_DEBOUNCE_MS:MIN_DEBOUNCE_MS;
  metrics.lastDebounceMs=delay;
  return delay;
}
function schedule({immediate=false,invalidate=false}={}){
  clearTimer();
  if(invalidate)invalidateSnapshot();
  const run=()=>{
    timer=0;
    const request=buildRequest();
    if(recoveryExhausted||recoveryFailures>0){pending=request;metrics.maxPendingDepth=Math.max(metrics.maxPendingDepth,1);return}
    if(inFlight){pending=request;metrics.maxPendingDepth=Math.max(metrics.maxPendingDepth,1);return}
    send(request);
  };
  if(immediate){run();return}
  if(recoveryExhausted||recoveryFailures>0||inFlight){
    pending=buildRequest();metrics.maxPendingDepth=Math.max(metrics.maxPendingDepth,1);return;
  }
  timer=setTimeout(run,adaptiveDebounceMs());
}"""
    if old_constant not in script:
        raise RuntimeError("lexical debounce constant contract changed")
    if old_schedule not in script:
        raise RuntimeError("lexical schedule contract changed")
    editor_lexical_runtime._SCRIPT = script.replace(old_constant, new_constant, 1).replace(
        old_schedule, new_schedule, 1
    )


__all__ = ["install_adaptive_lexical_schedule"]
