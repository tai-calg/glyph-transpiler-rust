from __future__ import annotations


_MARKER = "glyph-editor-lexical-runtime-v3"

_SCRIPT = r"""
<script id="glyph-editor-lexical-runtime-v3-script">
(()=>{
const MARKER="glyph-editor-lexical-runtime-v3";
const DEBOUNCE_MS=32;
const RECOVERY_DELAY_MS=100;
const MAX_RECOVERY_ATTEMPTS=3;
const MAX_FUZZY_PREFIX=256;
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
function subsequenceMatch(source,target,foldedSource,foldedTarget){
  if(source.length<2||source.length>MAX_FUZZY_PREFIX||!target)return null;
  const maxGaps=Math.min(24,Math.max(4,source.length*2));
  const boundaryAt=found=>{
    const previous=found>0?target[found-1]:"";
    return found===0||previous==="_"||previous==="-"||(/[a-z0-9]/.test(previous)&&/[A-Z]/.test(target[found]));
  };
  const findWithin=(needle,from,through)=>{
    for(let index=from;index<=through;index+=1){if(foldedTarget[index]===needle)return index}
    return-1;
  };
  let best=null,searchStart=0;
  while(searchStart<foldedTarget.length){
    const start=foldedTarget.indexOf(foldedSource[0],searchStart);
    if(start<0)break;
    const maximumEnd=Math.min(foldedTarget.length-1,start+source.length+maxGaps-1);
    const positions=[start];
    let cursor=start+1,casePenalty=source[0]!==target[start]?1:0,boundaryHits=boundaryAt(start)?1:0,valid=true;
    for(let index=1;index<foldedSource.length;index+=1){
      const found=findWithin(foldedSource[index],cursor,maximumEnd);
      if(found<0){valid=false;break}
      positions.push(found);
      if(source[index]!==target[found]&&foldedSource[index]===foldedTarget[found])casePenalty+=1;
      if(boundaryAt(found))boundaryHits+=1;
      cursor=found+1;
    }
    if(valid){
      const span=positions[positions.length-1]-start+1,gaps=span-source.length;
      const weakStart=start>0&&!boundaryAt(start);
      if(gaps<=maxGaps&&!(weakStart&&source.length<4)){
        let consecutive=0;
        for(let index=1;index<positions.length;index+=1){if(positions[index]===positions[index-1]+1)consecutive+=1}
        const candidate={
          matched:true,
          kind:"subsequence",
          score:200+start*10+gaps*5+Math.min(8,casePenalty)-boundaryHits*4-consecutive*2,
          edits:null,
          matchedLength:span,
        };
        if(!best||candidate.score<best.score||(candidate.score===best.score&&candidate.matchedLength<best.matchedLength))best=candidate;
      }
    }
    searchStart=start+1;
  }
  return best;
}
function boundedEditPrefix(source,target,foldedSource,foldedTarget,budget){
  const sourceLength=foldedSource.length;
  const maximumTarget=Math.min(target.length,sourceLength+budget);
  const minimumTarget=Math.max(1,sourceLength-budget);
  if(maximumTarget<minimumTarget)return null;
  const infinity=budget+2;
  const first=new Int16Array(maximumTarget+1);
  const second=new Int16Array(maximumTarget+1);
  const third=new Int16Array(maximumTarget+1);
  let previous=first,previousPrevious=third,current=second;
  let previousLow=0,previousHigh=Math.min(maximumTarget,budget);
  let previousPreviousLow=1,previousPreviousHigh=0;
  for(let targetIndex=0;targetIndex<=previousHigh;targetIndex+=1)previous[targetIndex]=targetIndex;
  for(let sourceIndex=1;sourceIndex<=sourceLength;sourceIndex+=1){
    const low=Math.max(0,sourceIndex-budget),high=Math.min(maximumTarget,sourceIndex+budget);
    for(let targetIndex=low;targetIndex<=high;targetIndex+=1){
      if(targetIndex===0){current[targetIndex]=sourceIndex;continue}
      const deletion=targetIndex>=previousLow&&targetIndex<=previousHigh?previous[targetIndex]+1:infinity;
      const insertion=targetIndex-1>=low?current[targetIndex-1]+1:infinity;
      const substitution=targetIndex-1>=previousLow&&targetIndex-1<=previousHigh
        ?previous[targetIndex-1]+(foldedSource[sourceIndex-1]===foldedTarget[targetIndex-1]?0:1)
        :infinity;
      let value=Math.min(deletion,insertion,substitution);
      if(sourceIndex>1&&targetIndex>1
        && foldedSource[sourceIndex-1]===foldedTarget[targetIndex-2]
        && foldedSource[sourceIndex-2]===foldedTarget[targetIndex-1]
        && targetIndex-2>=previousPreviousLow&&targetIndex-2<=previousPreviousHigh){
        value=Math.min(value,previousPrevious[targetIndex-2]+1);
      }
      current[targetIndex]=value;
    }
    const reusable=previousPrevious;
    previousPrevious=previous;
    previous=current;
    current=reusable;
    previousPreviousLow=previousLow;previousPreviousHigh=previousHigh;
    previousLow=low;previousHigh=high;
  }
  let bestEdits=budget+1,bestLength=-1;
  for(let length=minimumTarget;length<=maximumTarget;length+=1){
    if(length<previousLow||length>previousHigh)continue;
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
function matchText(query,candidate){
  const source=String(query??"");
  const target=String(candidate??"");
  if(!source)return{matched:true,kind:"empty",score:0,edits:0,matchedLength:0};
  if(target.startsWith(source))return{matched:true,kind:"prefix",score:0,edits:0,matchedLength:source.length};
  const foldedSource=source.toLowerCase(),foldedTarget=target.toLowerCase();
  if(foldedTarget.startsWith(foldedSource))return{matched:true,kind:"case-prefix",score:8,edits:0,matchedLength:source.length};
  const budget=fuzzyEditBudget(source.length);
  if(budget&&source.length<=MAX_FUZZY_PREFIX&&target){
    const fuzzy=boundedEditPrefix(source,target,foldedSource,foldedTarget,budget);
    if(fuzzy)return fuzzy;
  }
  return subsequenceMatch(source,target,foldedSource,foldedTarget);
}
function matchTier(kind){
  if(kind==="empty"||kind==="prefix")return 0;
  if(kind==="case-prefix")return 1;
  if(kind==="fuzzy")return 2;
  if(kind==="subsequence")return 3;
  return 4;
}
function nonNegativeInteger(value){return Number.isSafeInteger(Number(value))&&Number(value)>=0}
function stringArray(value){return Array.isArray(value)&&value.every(item=>typeof item==="string")}
function validSnapshotMessage(result,completed){
  if(!result||result.type!=="snapshot"||!completed)return false;
  const revision=Number(result.revision),sourceLength=Number(result.sourceLength);
  if(!Number.isSafeInteger(revision)||revision<0||revision!==Number(completed.revision))return false;
  if(!Number.isSafeInteger(sourceLength)||sourceLength<0||sourceLength!==String(completed.source??"").length)return false;
  if(!Array.isArray(result.records)||!Array.isArray(result.machineRecords))return false;
  if(!(result.positions instanceof Int32Array)||!(result.codePositions instanceof Int32Array))return false;
  let expectedAllOffset=0,expectedCodeOffset=0,previousText=null;
  for(const row of result.records){
    if(!row||typeof row.text!=="string"||!row.text||!stringArray(row.kinds)||!row.kinds.length||!stringArray(row.owners))return false;
    if(previousText!==null&&row.text<=previousText)return false;
    previousText=row.text;
    if(!nonNegativeInteger(row.allOffset)||!nonNegativeInteger(row.allCount)||!nonNegativeInteger(row.codeOffset)||!nonNegativeInteger(row.codeCount))return false;
    if(Number(row.allOffset)!==expectedAllOffset||Number(row.codeOffset)!==expectedCodeOffset||Number(row.codeCount)>Number(row.allCount))return false;
    expectedAllOffset+=Number(row.allCount);expectedCodeOffset+=Number(row.codeCount);
    if(expectedAllOffset>result.positions.length||expectedCodeOffset>result.codePositions.length)return false;
    if(typeof row.kind!=="string"||!row.kinds.includes(row.kind))return false;
    if(!row.ownerKinds||typeof row.ownerKinds!=="object"||Array.isArray(row.ownerKinds))return false;
    for(const [owner,kinds] of Object.entries(row.ownerKinds)){
      if(!row.owners.includes(owner)||!stringArray(kinds)||!kinds.every(kind=>row.kinds.includes(kind)))return false;
    }
  }
  if(expectedAllOffset!==result.positions.length||expectedCodeOffset!==result.codePositions.length)return false;
  let previousMachine="";
  for(const row of result.machineRecords){
    if(!row||typeof row.name!=="string"||typeof row.stateType!=="string"||typeof row.selectorField!=="string"||typeof row.selectorType!=="string")return false;
    if(previousMachine&&row.name<previousMachine)return false;
    previousMachine=row.name;
  }
  return true;
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
    const completed=inFlight;
    if(!validSnapshotMessage(result,completed)){
      metrics.invalidMessages+=1;
      handleWorkerFailure(active,{message:"lexical index worker returned an invalid snapshot"});
      return;
    }
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
  const leftTier=matchTier(left.matchKind),rightTier=matchTier(right.matchKind);
  return leftTier-rightTier
    ||Number(left.matchScore||0)-Number(right.matchScore||0)
    ||Number(left.queryPreference??Number.MAX_SAFE_INTEGER)-Number(right.queryPreference??Number.MAX_SAFE_INTEGER)
    ||Number(right.queryInScope||0)-Number(left.queryInScope||0)
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
function finalizeQueryRows(rows){
  return rows.map(row=>{
    const result={...row};delete result.queryPreference;delete result.queryInScope;return result;
  });
}
function query(prefix,caret,{limit=8,exclude="",kinds=null,owner=null,allowContract=false,exactText=null,preferredKinds=null,scopeStart=-1}={}){
  if(!snapshot)return[];
  const text=String(prefix??"");
  const records=snapshot.records;
  const rowLimit=Math.max(1,Number(limit)||1);
  const kindSet=Array.isArray(kinds)&&kinds.length?new Set(kinds):null;
  const preferenceOrder=Array.isArray(preferredKinds)?preferredKinds:[];
  const scopeBoundary=Number(scopeStart??-1);
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
  const preferenceFor=candidateKinds=>{
    let best=Number.MAX_SAFE_INTEGER;
    for(const kind of candidateKinds){const index=preferenceOrder.indexOf(kind);if(index>=0)best=Math.min(best,index)}
    return best;
  };
  const offer=(row,match)=>{
    const candidateKinds=eligible(row);if(!candidateKinds)return;
    const positions=codePositionsFor(row);
    const recent=lastBefore(positions,Number(caret)||0);
    insertBounded(rows,{
      text:row.text,kind:row.kind,kinds:[...row.kinds],owners:[...row.owners],origin:"document",
      count:row.codeCount,recent,added:Math.max(0,row.text.length-text.length),
      matchKind:match.kind,matchScore:match.score,matchEdits:match.edits,
      queryPreference:preferenceFor(candidateKinds),queryInScope:scopeBoundary>=0&&recent>=scopeBoundary?1:0,
    },rowLimit);
    seen.add(row.text);
  };
  if(exactText){
    const exactRow=record(String(exactText));
    if(exactRow){const match=matchText(text,exactRow.text);if(match)offer(exactRow,match)}
    return finalizeQueryRows(rows);
  }
  if(!text){
    for(const row of records)offer(row,{kind:"empty",score:0,edits:0});
    return finalizeQueryRows(rows);
  }
  const start=lowerBound(records,text,row=>row.text);
  for(let index=start;index<records.length;index+=1){
    const row=records[index];
    if(!row.text.startsWith(text))break;
    offer(row,{kind:"prefix",score:0,edits:0});
  }
  if(rows.length>=rowLimit)return finalizeQueryRows(rows);
  for(const row of records){
    if(seen.has(row.text))continue;
    const candidateKinds=eligible(row);if(!candidateKinds)continue;
    metrics.fuzzyRowsScanned+=1;
    const match=matchText(text,row.text);
    if(!match||match.kind==="prefix")continue;
    const positions=codePositionsFor(row);
    const recent=lastBefore(positions,Number(caret)||0);
    insertBounded(rows,{
      text:row.text,kind:row.kind,kinds:[...row.kinds],owners:[...row.owners],origin:"document",
      count:row.codeCount,recent,added:Math.max(0,row.text.length-text.length),
      matchKind:match.kind,matchScore:match.score,matchEdits:match.edits,
      queryPreference:preferenceFor(candidateKinds),queryInScope:scopeBoundary>=0&&recent>=scopeBoundary?1:0,
    },rowLimit);
  }
  return finalizeQueryRows(rows);
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