from __future__ import annotations


_MARKER = "glyph-transition-execution-context-selector-v2"

_STYLE = r"""
<style id="glyph-transition-execution-context-selector-v2-style">
.execution-context-control{
  display:flex;
  align-items:center;
  gap:7px;
  margin-left:auto;
  min-width:0;
}
.execution-context-control label{
  color:var(--muted);
  font-size:11px;
  white-space:nowrap;
}
.execution-context-control select{
  min-width:230px;
  max-width:360px;
}
@media(max-width:1100px){
  .execution-context-control label{display:none}
  .execution-context-control select{min-width:175px;max-width:250px}
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-execution-context-selector-v2-script">
(()=>{
const MARKER="glyph-transition-execution-context-selector-v2",AUTO="auto",MACHINE="machine";
const BLOCKED=new Set(["unresolved","multiple-transition-calls"]);
let currentMachine=null,currentKey=AUTO,timer=null,running=false,pending=false,lastSnapshotSignature="";
const text=value=>String(value??"").trim();
const actionText=value=>typeof value==="string"?text(value):text(value?.display)||text(value?.expression);
const english=()=>String(window.GlyphI18n?.locale||document.documentElement.lang||"ja").startsWith("en");
const tr=(key,ja,en)=>window.GlyphI18n?.t?.(key)??(english()?en:ja);
const selectedMachine=data=>{const machines=data?.views?.state?.machines||[],name=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;return machines.find(machine=>machine.name===name)||machines[0]||null};
const contextKey=binding=>`context:${text(binding?.scope)||"system"}:${text(binding?.system)}:${text(binding?.entry)}`;
const storageKey=machine=>`glyph.transition.execution-context.v2:${text(machine?.name)||"machine"}`;
const statusRank=status=>({"resolved":0,"actionless":1,"conditional":2,"unresolved":3,"multiple-transition-calls":4}[status]??0);
const contextRecords=transition=>transition?.execution_contexts||transition?.execution_action_bindings||[];
function presentationStatus(binding){const status=text(binding?.status)||"resolved";return status==="resolved"&&!binding?.action?"actionless":status}
function contextsFor(machine){
  const contexts=new Map();
  for(const transition of machine?.transitions||[]){
    for(const binding of contextRecords(transition)){
      const key=contextKey(binding),status=presentationStatus(binding),known=contexts.get(key);
      if(!known){contexts.set(key,{key,scope:text(binding.scope)||"system",system:text(binding.system),entry:text(binding.entry),status});continue}
      if(statusRank(status)>statusRank(known.status))known.status=status;
    }
  }
  return[...contexts.values()].sort((a,b)=>(a.system||a.entry).localeCompare(b.system||b.entry)||a.entry.localeCompare(b.entry));
}
function validKeys(machine){return new Set([AUTO,MACHINE,...contextsFor(machine).map(item=>item.key)])}
function selectionFor(machine){
  const valid=validKeys(machine);
  if(currentMachine?.name===machine?.name&&valid.has(currentKey))return currentKey;
  const saved=sessionStorage.getItem(storageKey(machine))||AUTO;
  return valid.has(saved)?saved:AUTO;
}
function bindingFor(transition,key){return contextRecords(transition).find(binding=>contextKey(binding)===key)||null}
function composedAction(machineAction,systemAction,context){
  const parts=[actionText(machineAction),actionText(systemAction)].filter(Boolean);
  if(!parts.length)return null;
  const display=parts.join("; ");
  return{display,expression:display,scope:parts.length===2?"composed":(systemAction?"system":"machine"),projection_provenance:"transition-execution-context-selection",system:context?.system||null,entry:context?.entry||null,status:context?.status||"resolved"};
}
function projectionFor(transition,key=currentKey){
  if(key===MACHINE)return{action:transition?.machine_action||null,invocations:transition?.machine_action_invocations||[],effects:transition?.machine_effect_invocations||[],status:"machine",blocked:false};
  if(key.startsWith("context:")){
    const binding=bindingFor(transition,key),status=binding?.status||"missing",blocked=BLOCKED.has(status),machineInvocations=transition?.machine_action_invocations||[],machineEffects=transition?.machine_effect_invocations||[],systemAction=blocked?null:binding?.action,systemInvocations=blocked?[]:(binding?.action_invocations||[]),systemEffects=blocked?[]:(binding?.effect_invocations||[]);
    return{action:composedAction(transition?.machine_action,systemAction,binding),invocations:[...machineInvocations,...systemInvocations],effects:[...machineEffects,...systemEffects],status,blocked,cases:binding?.action_cases||[]};
  }
  return{action:transition?.display_action||transition?.action||null,invocations:transition?.display_action_invocations||transition?.action_invocations||[],effects:transition?.display_effect_invocations||transition?.effect_invocations||[],status:transition?.action_scope?.context_required?"context-required":"auto",blocked:false};
}
function actionFor(transition){return projectionFor(transition).action}
function statusSuffix(status){
  if(status==="conditional")return tr("executionContextConditional","（条件付き）","(conditional)");
  if(status==="unresolved")return tr("executionContextUnresolved","（解析不能）","(unresolved)");
  if(status==="multiple-transition-calls")return tr("executionContextMultiple","（複数遷移）","(multiple transitions)");
  if(status==="actionless")return tr("executionContextActionless","（System Actionなし）","(no System Action)");
  return"";
}
function optionLabel(context){const base=context.system&&context.entry?`${context.system} / ${context.entry}`:(context.entry||context.system||tr("executionContextImplicit","暗黙の呼出し元","implicit caller"));return`${base}${statusSuffix(context.status)}`}
function publish(reason="selection"){document.dispatchEvent(new CustomEvent("glyph-execution-context-changed",{detail:{marker:MARKER,machine:currentMachine?.name||null,key:currentKey,reason}}))}
function liveState(){return typeof snapshot==="object"&&snapshot?snapshot:null}
async function state(){const live=liveState();if(live)return live;const response=await fetch("/api/state",{cache:"no-store"});if(!response.ok)throw Error("diagram state unavailable");return response.json()}
function snapshotSignature(data){return`${data?.version??""}:${data?.digest??""}:${JSON.stringify((data?.views?.state?.machines||[]).map(machine=>[machine.name,(machine.transitions||[]).map(item=>item.execution_contexts||item.execution_action_bindings||[])]))}`}
function ensureControl(machine){
  const host=document.querySelector(".view-controls"),machineSelect=document.getElementById("machine-select");
  if(!host||!machineSelect)return false;
  const contexts=contextsFor(machine),valid=validKeys(machine);
  let control=document.getElementById("execution-context-control");
  if(!contexts.length){const changed=Boolean(control)||currentKey!==AUTO||currentMachine?.name!==machine?.name;control?.remove();currentMachine=machine;currentKey=AUTO;return changed}
  if(!control){
    control=document.createElement("div");control.id="execution-context-control";control.className="execution-context-control";
    const label=document.createElement("label");label.htmlFor="execution-context-select";
    const select=document.createElement("select");select.id="execution-context-select";control.append(label,select);host.appendChild(control);
  }
  const label=control.querySelector("label"),select=control.querySelector("select"),labelText=tr("executionContextLabel","実行コンテキスト","Execution context");
  if(label.textContent!==labelText)label.textContent=labelText;
  const signature=JSON.stringify([contexts,window.GlyphI18n?.locale||"ja"]);
  if(control.dataset.contextSignature!==signature){
    select.replaceChildren();
    const options=[{key:AUTO,label:tr("executionContextAuto","自動（一致する場合のみ）","Auto (only when contexts agree)")},{key:MACHINE,label:tr("executionContextMachine","Machineのみ","Machine only")},...contexts.map(item=>({key:item.key,label:optionLabel(item)}))];
    for(const item of options){const option=document.createElement("option");option.value=item.key;option.textContent=item.label;select.appendChild(option)}
    control.dataset.contextSignature=signature;
  }
  const previousMachine=currentMachine?.name||"",previousKey=currentKey,next=selectionFor(machine);
  currentMachine=machine;currentKey=next;select.value=currentKey;
  select.onchange=()=>{currentKey=valid.has(select.value)?select.value:AUTO;sessionStorage.setItem(storageKey(machine),currentKey);control.dataset.selectedContext=currentKey;publish("selection")};
  control.dataset.selectedContext=currentKey;
  return previousMachine!==machine?.name||previousKey!==currentKey;
}
async function render(){
  if(running){pending=true;return}
  running=true;
  try{
    do{
      pending=false;
      const data=await state(),signature=snapshotSignature(data),machine=selectedMachine(data),sourceChanged=signature!==lastSnapshotSignature;
      lastSnapshotSignature=signature;
      const selectionChanged=Boolean(machine&&ensureControl(machine));
      if(machine&&(sourceChanged||selectionChanged))publish(sourceChanged?"source-change":"selection");
    }while(pending)
  }finally{
    running=false;
    if(pending)schedule(0);
  }
}
function schedule(delay=0){pending=true;clearTimeout(timer);timer=setTimeout(()=>render().catch(error=>console.error("execution-context selector failed",error)),delay)}
document.addEventListener("change",event=>{if(event.target?.id==="machine-select"){currentMachine=null;currentKey=AUTO;schedule(0)}});
for(const event of["glyph-state-transition-ir-v3-labels-ready","glyph-transition-io-clusters-ready","glyph-locale-changed","glyph-locale-applied"]){document.addEventListener(event,()=>schedule(0))}
new MutationObserver(()=>schedule(20)).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
window.GlyphExecutionContext={marker:MARKER,actionFor,projectionFor,contextsFor,selectedKey:()=>currentKey,signature:()=>`${currentMachine?.name||""}:${currentKey}:${lastSnapshotSignature}`,refresh:()=>schedule(0)};
schedule(0);
})();
</script>
"""


def enhance_transition_execution_context_selector_html(html: str) -> str:
    """Select Machine or one complete System execution context projection."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
