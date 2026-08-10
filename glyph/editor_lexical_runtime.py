from __future__ import annotations


_MARKER = "glyph-editor-lexical-runtime-v3"

_SCRIPT = r"""
<script id="glyph-editor-lexical-runtime-v3-script">
(()=>{
const MARKER="glyph-editor-lexical-runtime-v3";
const DEBOUNCE_MS=32;
const RECOVERY_DELAY_MS=100;
const MAX_RECOVERY_ATTEMPTS=3;
const MAX_FUZZY_PREFIX=48;
const editor=document.getElementById("editor");
const documentRuntime=window.GlyphEditorDocument;
if(!editor||!documentRuntime||editor.dataset.lexicalIndexReady==="true")return;

let worker=null,snapshot=null,inFlight=null,pending=null,timer=0,recoveryTimer=0,minimumRevision=0;
let recoveryFailures=0,recoveryAttempts=0,recoveryExhausted=false;
const metrics={
  buildsSent:0,buildsCompleted:0,staleAccepted:0,staleDiscarded:0,maxPendingDepth:0,
  workerRestarts:0,workerStarts:0,workerFailures:0,recoveryCycles:0,recoveryAttempts:0,recoveryExhausted:0,
  transportFailures:0,invalidMessages:0,queryRowsScanned:0,fuzzyRowsScanned:0,
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
function fuzzyEditBudget(length){
  if(length<3)return 0;
  if(length<=4)return 1;
  if(length<=8)return 2;
  return 3;
}
function matchText(query,candidate){
  const source=String(query??"");
  const target=String(candidate??"");
  if(!source)return{matched:true,kind:"empty",score:0,edits:0,matchedLength:0};
  if(target.startsWith(source))return{matched:true,kind:"prefix",score:0,edits:0,matchedLength:source.length};
  const foldedSource=source.toLowerCase(),foldedTarget=target.toLowerCase();
  if(foldedTarget.startsWith(foldedSource))return{matched:true,kind:"case-prefix",score:8,edits:0,matchedLength:source.length};
  const budget=fuzzyEditBudget(source.length);
  if(!budget||source.length>MAX_FUZZY_PREFIX||!target)return null;
  const minimumTarget=Math.max(1,source.length-budget);
  const maximumTarget=Math.min(target.length,source.length+budget,MAX_FUZZY_PREFIX+budget);
  if(maximumTarget<minimumTarget)return null;
  let previousPrevious=null;
  let previous=Array.from({length:maximumTarget+1},(_,index)=>index);
  for(let sourceIndex=1;sourceIndex<=foldedSource.length;sourceIndex+=1){
    const current=new Array(maximumTarget+1);
    current[0]=sourceIndex;
    let rowMinimum=current[0];
    for(let targetIndex=1;targetIndex<=maximumTarget;targetIndex+=1){
      const substitution=previous[targetIndex-1]+(foldedSource[sourceIndex-1]===foldedTarget[targetIndex-1]?0:1);
      let value=Math.min(previous[targetIndex]+1,current[targetIndex-1]+1,substitution);
      if(previousPrevious&&sourceIndex>1&&targetIndex>1
        && foldedSource[sourceIndex-1]===foldedTarget[targetIndex-2]
        && foldedSource[sourceIndex-2]===foldedTarget[targetIndex-1]){
        value=Math.min(value,previousPrevious[targetIndex-2]+1);
      }
      current[targetIndex]=value;
      rowMinimum=Math.min(rowMinimum,value);
    }
    if(rowMinimum>budget&&sourceIndex>budget+1)return null;
    previousPrevious=previous;
    previous=current;
  }
  let bestEdits=budget+1,bestLength=-1;
  for(let length=minimumTarget;length<=maximumTarget;length+=1){
    const edits=previous[length];
    if(edits<bestEdits||(edits===bestEdits&&Math.abs(length-source.length)<Math.abs(bestLength-source.length))){
      bestEdits=edits;bestLength=length;
    }
  }
  if(bestEdits>budget||bestLength<0)return null;
  let casePenalty=0;
  const compared=Math.min(source.length,bestLength);
  for(let index=0;index<compared;index+=1){
    if(source[index]!==target[index]&&foldedSource[index]===foldedTarget[index])casePenalty+=1;
  }
  return{
    matched:true,
    kind:"fuzzy",
    score:100+bestEdits*24+Math.abs(bestLength-source.length)*3+Math.min(6,casePenalty),
    edits:bestEdits,
    matchedLength:bestLength,
  };
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
    metrics.transportFailures+=1;
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
    if(result.type!=="snapshot"){
      metrics.invalidMessages+=1;
      handleWorkerFailure(active,{message:"lexical index worker returned an invalid message"});
      return;
    }
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
  active.onmessageerror=event=>{
    metrics.transportFailures+=1;
    handleWorkerFailure(active,{message:String(event?.message||"lexical index worker message deserialization failed")});
  };
  return active;
}
function send(request,{recovery=false}={}){
  const active=ensureWorker({recovery});
  if(!active)return false;
  inFlight=request;
  metrics.buildsSent+=1;
  try{active.postMessage(request)}
  catch(error){
    metrics.transportFailures+=1;
    handleWorkerFailure(active,{message:String(error?.message||error)});
    return false;
  }
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
function queryRowOrder(left,right){
  return Number(left.matchScore||0)-Number(right.matchScore||0)
    ||right.recent-left.recent
    ||right.count-left.count
    ||left.added-right.added
    ||(left.text<right.text?-1:left.text>right.text?1:0);
}
function insertBounded(rows,candidate,limit){
  let low=0,high=rows.length;
  while(low<high){const middle=(low+high)>>1;if(queryRowOrder(rows[middle],candidate)<=0)low=middle+1;else high=middle}
  if(low>=limit&&rows.length>=limit)return;
  rows.splice(low,0,candidate);
  if(rows.length>limit)rows.pop();
}
function query(prefix,caret,{limit=8,exclude="",kinds=null,owner=null,allowContract=false}={}){
  if(!snapshot)return[];
  const text=String(prefix??"");
  const records=snapshot.records;
  const rowLimit=Math.max(1,Number(limit)||1);
  const kindSet=Array.isArray(kinds)&&kinds.length?new Set(kinds):null;
  const rows=[];
  const seen=new Set();
  const eligible=row=>{
    metrics.queryRowsScanned+=1;
    if(row.codeCount<=0||row.text===exclude)return null;
    const ownedKinds=owner?(row.ownerKinds?.[owner]||[]):null;
    if(owner&&!ownedKinds.length)return null;
    const candidateKinds=owner?ownedKinds:row.kinds;
    if(kindSet&&!candidateKinds.some(kind=>kindSet.has(kind)))return null;
    if(!allowContract&&row.kinds.length===1&&row.kinds[0]==="Contract")return null;
    return candidateKinds;
  };
  const offer=(row,match)=>{
    const candidateKinds=eligible(row);if(!candidateKinds)return;
    const positions=codePositionsFor(row);
    insertBounded(rows,{
      text:row.text,kind:row.kind,kinds:[...row.kinds],owners:[...row.owners],origin:"document",
      count:row.codeCount,recent:lastBefore(positions,Number(caret)||0),added:Math.max(0,row.text.length-text.length),
      matchKind:match.kind,matchScore:match.score,matchEdits:match.edits,
    },rowLimit);
    seen.add(row.text);
  };
  if(!text){
    for(const row of records)offer(row,{kind:"empty",score:0,edits:0});
    return rows;
  }
  const start=lowerBound(records,text,row=>row.text);
  for(let index=start;index<records.length;index+=1){
    const row=records[index];
    if(!row.text.startsWith(text))break;
    offer(row,{kind:"prefix",score:0,edits:0});
  }
  if(rows.length>=rowLimit)return rows;
  for(const row of records){
    if(seen.has(row.text))continue;
    const candidateKinds=eligible(row);if(!candidateKinds)continue;
    metrics.fuzzyRowsScanned+=1;
    const match=matchText(text,row.text);
    if(!match||match.kind==="prefix")continue;
    const positions=codePositionsFor(row);
    insertBounded(rows,{
      text:row.text,kind:row.kind,kinds:[...row.kinds],owners:[...row.owners],origin:"document",
      count:row.codeCount,recent:lastBefore(positions,Number(caret)||0),added:Math.max(0,row.text.length-text.length),
      matchKind:match.kind,matchScore:match.score,matchEdits:match.edits,
    },rowLimit);
  }
  return rows;
}

document.addEventListener("glyph-editor-document-changed",event=>{if(event.detail?.composing)return;schedule()});
document.addEventListener("glyph-editor-source-replaced",()=>schedule({immediate:true,invalidate:true}));
document.addEventListener("glyph-editor-composition-changed",event=>{if(event.detail?.active===false)schedule()});
editor.dataset.lexicalIndexReady="true";
window.GlyphEditorLexicalIndex={
  marker:MARKER,version:2,snapshot:()=>snapshot,record,machineInfo,allPositions,codePositions:codePositionsFor,query,matchText,
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
