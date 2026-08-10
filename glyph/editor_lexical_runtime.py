from __future__ import annotations


_MARKER = "glyph-editor-lexical-runtime-v3"

_SCRIPT = r"""
<script id="glyph-editor-lexical-runtime-v3-script">
(()=>{
const MARKER="glyph-editor-lexical-runtime-v3";
const DEBOUNCE_MS=120;
const RECOVERY_DELAY_MS=100;
const MAX_RECOVERY_ATTEMPTS=3;
const editor=document.getElementById("editor");
const documentRuntime=window.GlyphEditorDocument;
if(!editor||!documentRuntime||editor.dataset.lexicalIndexReady==="true")return;

let worker=null,snapshot=null,inFlight=null,pending=null,timer=0,recoveryTimer=0,minimumRevision=0;
let recoveryFailures=0,recoveryAttempts=0,recoveryExhausted=false;
const metrics={
  buildsSent:0,buildsCompleted:0,staleAccepted:0,staleDiscarded:0,maxPendingDepth:0,
  workerRestarts:0,workerStarts:0,workerFailures:0,recoveryCycles:0,recoveryAttempts:0,recoveryExhausted:0,
};

const emit=(name,detail={})=>document.dispatchEvent(new CustomEvent(name,{detail:{marker:MARKER,...detail}}));
function lowerBound(values,target,selector=value=>value){
  let low=0,high=values.length;
  while(low<high){const middle=(low+high)>>1;if(selector(values[middle])<target)low=middle+1;else high=middle}
  return low;
}
function lastBefore(values,target){
  let low=0,high=values.length;
  while(low<high){const middle=(low+high)>>1;if(values[middle]<target)low=middle+1;else high=middle}
  return low>0?values[low-1]:-1;
}
function clearTimer(){if(timer){clearTimeout(timer);timer=0}}
function clearRecoveryTimer(){if(recoveryTimer){clearTimeout(recoveryTimer);recoveryTimer=0}}
function invalidateSnapshot(){
  minimumRevision=documentRuntime.revision();
  snapshot=null;
  emit("glyph-editor-lexical-index-invalidated",{revision:minimumRevision});
}
function resetRecoveryAfterExact(){
  recoveryFailures=0;
  recoveryAttempts=0;
  recoveryExhausted=false;
  clearRecoveryTimer();
}
function markRecoveryExhausted(){
  if(recoveryExhausted)return;
  recoveryExhausted=true;
  metrics.recoveryExhausted+=1;
  clearRecoveryTimer();
  emit("glyph-editor-lexical-index-recovery-exhausted",{
    revision:documentRuntime.revision(),attempts:recoveryAttempts,failures:recoveryFailures,
  });
}
function scheduleRecovery(){
  clearRecoveryTimer();
  if(recoveryExhausted)return;
  if(recoveryAttempts>=MAX_RECOVERY_ATTEMPTS){markRecoveryExhausted();return}
  recoveryTimer=setTimeout(()=>{
    recoveryTimer=0;
    if(recoveryExhausted||worker||inFlight)return;
    recoveryAttempts+=1;
    metrics.recoveryAttempts=recoveryAttempts;
    metrics.workerRestarts+=1;
    const request=buildRequest();
    send(request,{recovery:true});
  },RECOVERY_DELAY_MS);
}
function handleWorkerFailure(active,event){
  if(active!==worker)return;
  const message=String(event?.message||"lexical index worker failed");
  try{active.terminate()}catch{}
  worker=null;inFlight=null;snapshot=null;
  metrics.workerFailures+=1;
  if(recoveryFailures===0)metrics.recoveryCycles+=1;
  recoveryFailures+=1;
  emit("glyph-editor-lexical-index-error",{
    message,revision:documentRuntime.revision(),recoveryFailures,recoveryAttempts,
  });
  if(recoveryAttempts>=MAX_RECOVERY_ATTEMPTS)markRecoveryExhausted();
  else scheduleRecovery();
}
function ensureWorker({recovery=false}={}){
  if(worker)return worker;
  if(recoveryExhausted)return null;
  if(recoveryFailures>0&&!recovery)return null;
  let active;
  try{active=new Worker("/assets/editor-lexical-worker.js")}
  catch(error){
    const message=String(error?.message||error);
    metrics.workerFailures+=1;
    if(recoveryFailures===0)metrics.recoveryCycles+=1;
    recoveryFailures+=1;
    emit("glyph-editor-lexical-index-error",{message,revision:documentRuntime.revision(),recoveryFailures,recoveryAttempts});
    if(recoveryAttempts>=MAX_RECOVERY_ATTEMPTS)markRecoveryExhausted();
    else scheduleRecovery();
    return null;
  }
  worker=active;
  metrics.workerStarts+=1;
  active.onmessage=event=>{
    if(active!==worker)return;
    const result=event.data||{};
    if(result.type!=="snapshot")return;
    const completed=inFlight;
    inFlight=null;
    metrics.buildsCompleted+=1;
    const currentRevision=documentRuntime.revision();
    if(Number(result.revision)<minimumRevision){metrics.staleDiscarded+=1}
    else if(!snapshot||Number(result.revision)>=Number(snapshot.revision)){
      snapshot=result;
      if(Number(result.revision)<Number(currentRevision))metrics.staleAccepted+=1;
      const exact=Number(result.revision)===Number(currentRevision);
      if(exact)resetRecoveryAfterExact();
      emit("glyph-editor-lexical-index-updated",{revision:result.revision,currentRevision,exact});
    }else metrics.staleDiscarded+=1;
    const next=pending;
    pending=null;
    if(next&&Number(next.revision)>Number(completed?.revision||-1))send(next,{recovery:recoveryFailures>0});
  };
  active.onerror=event=>handleWorkerFailure(active,event);
  return active;
}
function send(request,{recovery=false}={}){
  const active=ensureWorker({recovery});
  if(!active)return false;
  inFlight=request;
  metrics.buildsSent+=1;
  active.postMessage(request);
  return true;
}
function buildRequest(){return{revision:documentRuntime.revision(),source:editor.value}}
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
  if(immediate)run();else timer=setTimeout(run,DEBOUNCE_MS);
}
function refresh(){
  if(recoveryExhausted||recoveryFailures>0){pending=buildRequest();metrics.maxPendingDepth=Math.max(metrics.maxPendingDepth,1);return false}
  schedule({immediate:true});
  return true;
}
function invalidate(){
  invalidateSnapshot();
  if(recoveryExhausted||recoveryFailures>0){pending=buildRequest();metrics.maxPendingDepth=Math.max(metrics.maxPendingDepth,1);return false}
  schedule({immediate:true});
  return true;
}
function record(name){
  if(!snapshot)return null;
  const text=String(name||"");
  const index=lowerBound(snapshot.records,text,row=>row.text);
  const row=snapshot.records[index];
  return row?.text===text?row:null;
}
function machineInfo(name){
  if(!snapshot)return null;
  const text=String(name||"");
  const records=snapshot.machineRecords||[];
  const index=lowerBound(records,text,row=>row.name);
  const row=records[index];
  return row?.name===text?row:null;
}
function allPositions(row){return row&&snapshot?snapshot.positions.subarray(row.allOffset,row.allOffset+row.allCount):new Int32Array()}
function codePositionsFor(row){return row&&snapshot?snapshot.codePositions.subarray(row.codeOffset,row.codeOffset+row.codeCount):new Int32Array()}
function query(prefix,caret,{limit=8,exclude="",kinds=null,owner=null,allowContract=false}={}){
  if(!snapshot)return[];
  const text=String(prefix??"");
  const records=snapshot.records;
  const kindSet=Array.isArray(kinds)&&kinds.length?new Set(kinds):null;
  let start=text?lowerBound(records,text,row=>row.text):0;
  const rows=[];
  for(let index=start;index<records.length;index+=1){
    const row=records[index];
    if(text&&!row.text.startsWith(text))break;
    if(row.codeCount<=0||row.text===exclude)continue;
    const ownedKinds=owner?(row.ownerKinds?.[owner]||[]):null;
    if(owner&&!ownedKinds.length)continue;
    const candidateKinds=owner?ownedKinds:row.kinds;
    if(kindSet&&!candidateKinds.some(kind=>kindSet.has(kind)))continue;
    if(!allowContract&&row.kinds.length===1&&row.kinds[0]==="Contract")continue;
    const positions=codePositionsFor(row);
    rows.push({
      text:row.text,kind:row.kind,kinds:[...row.kinds],owners:[...row.owners],origin:"document",
      count:row.codeCount,recent:lastBefore(positions,Number(caret)||0),added:Math.max(0,row.text.length-text.length),
    });
  }
  rows.sort((a,b)=>b.recent-a.recent||b.count-a.count||a.added-b.added||(a.text<b.text?-1:a.text>b.text?1:0));
  return rows.slice(0,Math.max(1,limit));
}

document.addEventListener("glyph-editor-document-changed",event=>{if(event.detail?.composing)return;schedule()});
document.addEventListener("glyph-editor-source-replaced",()=>schedule({immediate:true,invalidate:true}));
document.addEventListener("glyph-editor-composition-changed",event=>{if(event.detail?.active===false)schedule()});
editor.dataset.lexicalIndexReady="true";
window.GlyphEditorLexicalIndex={
  marker:MARKER,version:2,snapshot:()=>snapshot,record,machineInfo,allPositions,codePositions:codePositionsFor,query,
  refresh,invalidate,
  metrics:()=>({...metrics,inFlight:Boolean(inFlight),pending:Boolean(pending),recoveryFailures,recoveryAttempts,recoveryExhausted}),
};
invalidate();
})();
</script>
"""


def enhance_editor_lexical_runtime_html(html: str) -> str:
    """Install the lexical index runtime with one bounded Worker recovery owner."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")


__all__ = ["enhance_editor_lexical_runtime_html"]
