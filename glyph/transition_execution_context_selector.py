from __future__ import annotations


_MARKER = "glyph-transition-execution-context-selector-v1"

_STYLE = r"""
<style id="glyph-transition-execution-context-selector-v1-style">
.execution-context-control{
  display:flex;
  align-items:center;
  gap:7px;
  margin-left:8px;
  padding-left:10px;
  border-left:1px solid var(--line);
}
.execution-context-control label{
  color:var(--muted);
  font-size:11px;
  white-space:nowrap;
}
.execution-context-control select{
  min-width:210px;
  max-width:300px;
}
@media(max-width:1100px){
  .execution-context-control label{display:none}
  .execution-context-control select{min-width:160px;max-width:220px}
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-execution-context-selector-v1-script">
(()=>{
const MARKER="glyph-transition-execution-context-selector-v1",AUTO="auto",MACHINE="machine",API_PATHS=new Set(["/api/state","/api/preview","/api/save"]);
let cache=null,currentMachine=null,currentKey=AUTO,timer=null,running=false;
const nativeFetch=window.fetch.bind(window);
const text=value=>String(value??"").trim();
const actionText=value=>typeof value==="string"?text(value):text(value?.display)||text(value?.expression);
const selectedMachine=data=>{const machines=data?.views?.state?.machines||[],name=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;return machines.find(machine=>machine.name===name)||machines[0]||null};
const contextKey=binding=>`context:${text(binding?.scope)||"system"}:${text(binding?.system)}:${text(binding?.entry)}`;
const storageKey=machine=>`glyph.transition.execution-context.v1:${text(machine?.name)||"machine"}`;
function contextsFor(machine){
  const contexts=new Map();
  for(const transition of machine?.transitions||[]){
    for(const binding of transition?.execution_action_bindings||[]){
      const key=contextKey(binding);
      if(!contexts.has(key))contexts.set(key,{key,scope:text(binding.scope)||"system",system:text(binding.system),entry:text(binding.entry)});
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
function bindingFor(transition,key){return(transition?.execution_action_bindings||[]).find(binding=>contextKey(binding)===key)||null}
function composedAction(machineAction,systemAction,context){
  const parts=[actionText(machineAction),actionText(systemAction)].filter(Boolean);
  if(!parts.length)return null;
  const display=parts.join("; ");
  return{display,expression:display,scope:parts.length===2?"composed":(systemAction?"system":"machine"),projection_provenance:"transition-execution-context-selection",system:context?.system||null,entry:context?.entry||null};
}
function projectionFor(transition,key){
  if(key===MACHINE)return{action:transition?.machine_action||null,invocations:transition?.machine_action_invocations||[],effects:transition?.machine_effect_invocations||[]};
  if(key.startsWith("context:")){
    const binding=bindingFor(transition,key),machineInvocations=transition?.machine_action_invocations||[],systemInvocations=binding?.action_invocations||[],machineEffects=transition?.machine_effect_invocations||[],systemEffects=binding?.effect_invocations||[];
    return{action:composedAction(transition?.machine_action,binding?.action,binding),invocations:[...machineInvocations,...systemInvocations],effects:[...machineEffects,...systemEffects]};
  }
  return{action:transition?.display_action||transition?.action||null,invocations:transition?.display_action_invocations||transition?.action_invocations||[],effects:transition?.display_effect_invocations||transition?.effect_invocations||[]};
}
function actionFor(transition){return projectionFor(transition,currentKey).action}
function projectPayload(payload){
  const machines=payload?.views?.state?.machines||[];
  for(const machine of machines){
    const key=selectionFor(machine);
    for(const transition of machine?.transitions||[]){
      const projection=projectionFor(transition,key);
      transition.action=projection.action;
      transition.action_invocations=projection.invocations.map(item=>({...item}));
      transition.effect_invocations=projection.effects.map(item=>({...item}));
      transition.ui_execution_context={key,source:"transition-execution-context-selector"};
    }
  }
  return payload;
}
window.fetch=async(input,init)=>{
  const response=await nativeFetch(input,init),raw=typeof input==="string"?input:input?.url||"";
  let path="";try{path=new URL(raw,window.location.href).pathname}catch{return response}
  if(!response.ok||!API_PATHS.has(path))return response;
  let payload;try{payload=await response.clone().json()}catch{return response}
  const headers=new Headers(response.headers);headers.delete("content-length");headers.delete("content-encoding");
  return new Response(JSON.stringify(projectPayload(payload)),{status:response.status,statusText:response.statusText,headers});
};
function optionLabel(context){if(context.system&&context.entry)return`${context.system} / ${context.entry}`;return context.entry||context.system||"implicit caller"}
function publish(){
  cache=null;
  document.dispatchEvent(new CustomEvent("glyph-execution-context-changed",{detail:{marker:MARKER,machine:currentMachine?.name||null,key:currentKey}}));
  // Existing renderers already use this neutral redraw hook. The locale value is
  // unchanged; only their API snapshot is re-read through the projection above.
  document.dispatchEvent(new CustomEvent("glyph-locale-changed",{detail:{source:MARKER}}));
}
async function state(){if(cache)return cache;const response=await fetch("/api/state",{cache:"no-store"});if(!response.ok)throw Error("diagram state unavailable");return cache=await response.json()}
function ensureControl(machine){
  const host=document.querySelector(".view-controls"),machineSelect=document.getElementById("machine-select");
  if(!host||!machineSelect)return false;
  const contexts=contextsFor(machine),valid=validKeys(machine);
  let control=document.getElementById("execution-context-control");
  if(!contexts.length){control?.remove();currentMachine=machine;currentKey=AUTO;return false}
  if(!control){
    control=document.createElement("div");control.id="execution-context-control";control.className="execution-context-control";
    const label=document.createElement("label");label.htmlFor="execution-context-select";label.textContent="実行コンテキスト";
    const select=document.createElement("select");select.id="execution-context-select";control.append(label,select);host.appendChild(control);
  }
  const select=control.querySelector("select"),signature=JSON.stringify(contexts);
  if(control.dataset.contextSignature!==signature){
    select.replaceChildren();
    const options=[{key:AUTO,label:"自動（単一コンテキスト）"},{key:MACHINE,label:"Machineのみ"},...contexts.map(item=>({key:item.key,label:optionLabel(item)}))];
    for(const item of options){const option=document.createElement("option");option.value=item.key;option.textContent=item.label;select.appendChild(option)}
    control.dataset.contextSignature=signature;
  }
  const previousMachine=currentMachine?.name||"",previousKey=currentKey,next=selectionFor(machine);
  currentMachine=machine;currentKey=next;select.value=currentKey;
  select.onchange=()=>{currentKey=valid.has(select.value)?select.value:AUTO;sessionStorage.setItem(storageKey(machine),currentKey);control.dataset.selectedContext=currentKey;publish()};
  control.dataset.selectedContext=currentKey;
  return previousMachine!==machine?.name||previousKey!==currentKey;
}
async function render(){
  if(running)return;running=true;
  try{const data=await state(),machine=selectedMachine(data);if(machine&&ensureControl(machine))publish()}finally{running=false}
}
function schedule(delay=0){clearTimeout(timer);timer=setTimeout(()=>render().catch(error=>console.error("execution-context selector failed",error)),delay)}
document.addEventListener("change",event=>{if(event.target?.id==="machine-select"){cache=null;currentMachine=null;currentKey=AUTO;schedule(0)}});
for(const event of["glyph-state-transition-ir-v3-labels-ready","glyph-transition-io-clusters-ready"]){document.addEventListener(event,()=>schedule(0))}
new MutationObserver(()=>schedule(20)).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
window.GlyphExecutionContext={marker:MARKER,actionFor,contextsFor,selectedKey:()=>currentKey,signature:()=>`${currentMachine?.name||""}:${currentKey}`,refresh:()=>{cache=null;schedule(0)}};
schedule(0);
})();
</script>
"""


def enhance_transition_execution_context_selector_html(html: str) -> str:
    """Let the user project Machine or one concrete System execution Action."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
