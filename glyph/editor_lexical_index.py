from __future__ import annotations


_MARKER = "glyph-editor-lexical-index-v1"

LEXICAL_WORKER_JS = r"""(()=>{
const isStart=code=>(code>=65&&code<=90)||(code>=97&&code<=122)||code===95;
const isPart=code=>isStart(code)||(code>=48&&code<=57);
self.onmessage=event=>{
  const payload=event.data||{};
  const revision=Number(payload.revision||0);
  const source=String(payload.source||"");
  const table=new Map();
  let index=0,comment=false;
  while(index<source.length){
    const code=source.charCodeAt(index);
    if(code===10){comment=false;index+=1;continue}
    if(code===35){comment=true;index+=1;continue}
    if(!isStart(code)){index+=1;continue}
    const start=index;
    index+=1;
    while(index<source.length&&isPart(source.charCodeAt(index)))index+=1;
    const text=source.slice(start,index);
    let row=table.get(text);
    if(!row){row={all:[],code:[]};table.set(text,row)}
    row.all.push(start);
    if(!comment)row.code.push(start);
  }
  const names=[...table.keys()].sort();
  let allLength=0,codeLength=0;
  for(const name of names){const row=table.get(name);allLength+=row.all.length;codeLength+=row.code.length}
  const positions=new Int32Array(allLength),codePositions=new Int32Array(codeLength),records=[];
  let allOffset=0,codeOffset=0;
  for(const text of names){
    const row=table.get(text);
    positions.set(row.all,allOffset);
    codePositions.set(row.code,codeOffset);
    records.push({text,allOffset,allCount:row.all.length,codeOffset,codeCount:row.code.length});
    allOffset+=row.all.length;codeOffset+=row.code.length;
  }
  self.postMessage({type:"snapshot",revision,sourceLength:source.length,records,positions,codePositions},[positions.buffer,codePositions.buffer]);
};
})();
"""

_SCRIPT = r"""
<script id="glyph-editor-lexical-index-v1-script">
(()=>{
const MARKER="glyph-editor-lexical-index-v1";
const DEBOUNCE_MS=120;
const editor=document.getElementById("editor");
const documentRuntime=window.GlyphEditorDocument;
if(!editor||!documentRuntime||editor.dataset.lexicalIndexReady==="true")return;
let worker=null,snapshot=null,inFlight=null,pending=null,timer=0,restartCount=0,minimumRevision=0;
const metrics={buildsSent:0,buildsCompleted:0,staleAccepted:0,staleDiscarded:0,maxPendingDepth:0,workerRestarts:0};

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
function ensureWorker(){
  if(worker)return worker;
  try{
    worker=new Worker("/assets/editor-lexical-worker.js");
  }catch(error){
    emit("glyph-editor-lexical-index-error",{message:String(error?.message||error)});
    return null;
  }
  worker.onmessage=event=>{
    const result=event.data||{};
    if(result.type!=="snapshot")return;
    const completed=inFlight;
    inFlight=null;
    metrics.buildsCompleted+=1;
    const currentRevision=documentRuntime.revision();
    if(Number(result.revision)<minimumRevision){
      metrics.staleDiscarded+=1;
    }else if(!snapshot||Number(result.revision)>=Number(snapshot.revision)){
      result.recordMap=new Map(result.records.map(record=>[record.text,record]));
      snapshot=result;
      if(result.revision<currentRevision)metrics.staleAccepted+=1;
      emit("glyph-editor-lexical-index-updated",{revision:result.revision,currentRevision,exact:result.revision===currentRevision});
    }else{
      metrics.staleDiscarded+=1;
    }
    const next=pending;
    pending=null;
    if(next&&Number(next.revision)>Number(completed?.revision||-1))send(next);
  };
  worker.onerror=event=>{
    const message=String(event?.message||"lexical index worker failed");
    try{worker?.terminate()}catch{}
    worker=null;inFlight=null;pending=null;snapshot=null;
    emit("glyph-editor-lexical-index-error",{message});
    if(restartCount<1){
      restartCount+=1;metrics.workerRestarts+=1;
      setTimeout(()=>schedule({immediate:true,invalidate:true}),100);
    }
  };
  return worker;
}
function send(request){
  const active=ensureWorker();
  if(!active)return;
  inFlight=request;
  metrics.buildsSent+=1;
  active.postMessage(request);
}
function buildRequest(){return{revision:documentRuntime.revision(),source:editor.value}}
function schedule({immediate=false,invalidate=false}={}){
  clearTimeout(timer);timer=0;
  if(invalidate){minimumRevision=documentRuntime.revision();snapshot=null;emit("glyph-editor-lexical-index-invalidated",{revision:minimumRevision})}
  const run=()=>{
    timer=0;
    const request=buildRequest();
    if(inFlight){pending=request;metrics.maxPendingDepth=Math.max(metrics.maxPendingDepth,1);return}
    send(request);
  };
  if(immediate)run();else timer=setTimeout(run,DEBOUNCE_MS);
}
function record(name){return snapshot?.recordMap?.get(String(name||""))||null}
function allPositions(row){return row&&snapshot?snapshot.positions.subarray(row.allOffset,row.allOffset+row.allCount):new Int32Array()}
function codePositionsFor(row){return row&&snapshot?snapshot.codePositions.subarray(row.codeOffset,row.codeOffset+row.codeCount):new Int32Array()}
function query(prefix,caret,{limit=8,exclude=""}={}){
  if(!snapshot)return[];
  const text=String(prefix??"");
  const records=snapshot.records;
  let start=text?lowerBound(records,text,row=>row.text):0;
  const rows=[];
  for(let index=start;index<records.length;index+=1){
    const row=records[index];
    if(text&&!row.text.startsWith(text))break;
    if(row.codeCount<=0||row.text===exclude)continue;
    const positions=codePositionsFor(row);
    rows.push({
      text:row.text,
      count:row.codeCount,
      recent:lastBefore(positions,Number(caret)||0),
      added:Math.max(0,row.text.length-text.length),
    });
  }
  rows.sort((a,b)=>b.recent-a.recent||b.count-a.count||a.added-b.added||(a.text<b.text?-1:a.text>b.text?1:0));
  return rows.slice(0,Math.max(1,limit));
}

document.addEventListener("glyph-editor-document-changed",event=>{
  if(event.detail?.composing)return;
  schedule();
});
document.addEventListener("glyph-editor-source-replaced",()=>schedule({immediate:true,invalidate:true}));
document.addEventListener("glyph-editor-composition-changed",event=>{if(event.detail?.active===false)schedule()});
editor.dataset.lexicalIndexReady="true";
window.GlyphEditorLexicalIndex={
  marker:MARKER,
  version:1,
  snapshot:()=>snapshot,
  record,
  allPositions,
  codePositions:codePositionsFor,
  query,
  refresh:()=>schedule({immediate:true}),
  invalidate:()=>schedule({immediate:true,invalidate:true}),
  metrics:()=>({...metrics,inFlight:Boolean(inFlight),pending:Boolean(pending)}),
};
schedule({immediate:true,invalidate:true});
})();
</script>
"""


def enhance_editor_lexical_index_html(html: str) -> str:
    """Install a coalesced worker-backed lexical index for editor features."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")


__all__ = ["LEXICAL_WORKER_JS", "enhance_editor_lexical_index_html"]
