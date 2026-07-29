from __future__ import annotations


_MARKER = "glyph-transition-enabling-case-labels-v1"

_STYLE = r"""
<style id="glyph-transition-enabling-case-labels-v1-style">
.transition-io-cluster.enabling-case-labels .transition-io-value{
  display:flex;
  flex-direction:column;
  align-items:center;
  gap:2px;
  white-space:normal;
  overflow:visible;
  text-overflow:clip;
}
.transition-enabling-case-line{
  display:block;
  white-space:nowrap;
  line-height:1.3;
}
.transition-enabling-case-line.provisional-input-pattern{
  text-decoration:underline dotted;
  text-underline-offset:2px;
}
.transition-enabling-case-line + .transition-enabling-case-line{
  border-top:1px solid color-mix(in srgb,var(--line) 65%,transparent);
  padding-top:2px;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-enabling-case-labels-v1-script">
(()=>{
const MARKER="glyph-transition-enabling-case-labels-v1";
let cache=null,timer=null,running=false;
const text=value=>String(value??"").trim();
const esc=value=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
async function state(){if(cache)return cache;const response=await fetch("/api/state",{cache:"no-store"});if(!response.ok)throw Error("diagram state unavailable");return cache=await response.json()}
function selectedMachine(data){const machines=data?.views?.state?.machines||[],name=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;return machines.find(machine=>machine.name===name)||machines[0]||null}
function actionOf(transition){const action=transition?.action;if(typeof action==="string")return text(action);return text(action?.display)||text(action?.expression)}
function guardOf(enablingCase){const direct=text(enablingCase?.guard?.display);if(direct)return direct;return(enablingCase?.guard_terms||[]).map(item=>text(item?.display)).filter(Boolean).join(" & ")}
function inputOf(enablingCase){return text(enablingCase?.input_pattern?.display)}
function exactOf(enablingCase){return text(enablingCase?.exact_enabling_condition?.expression)}
function summaryOf(enablingCase,action){const input=inputOf(enablingCase),guard=guardOf(enablingCase),left=`${input}${guard?`${input?" ":""}[${guard}]`:""}`;return`${left}${action?`${left?" ":""}➞ ${action}`:""}`||"—"}
function lineMarkup(enablingCase,action){const input=inputOf(enablingCase),guard=guardOf(enablingCase),exact=exactOf(enablingCase),summary=summaryOf(enablingCase,action),provisional=enablingCase?.input_pattern?.confidence==="provisional";return`<span class="transition-enabling-case-line${provisional?" provisional-input-pattern":""}" data-enabling-case-id="${esc(enablingCase?.id||"")}" data-input-value="${esc(input)}" data-guard-value="${esc(guard)}" data-action-value="${esc(action)}" data-exact-enabling-condition="${esc(exact)}">${esc(summary)}</span>`}
function updateCluster(cluster,transition){const cases=Array.isArray(transition?.enabling_cases)?transition.enabling_cases:[];if(!cases.length)return false;const value=cluster.querySelector(".transition-io-value");if(!value)return false;const action=actionOf(transition),signature=JSON.stringify([action,cases]);if(cluster.dataset.enablingCaseSignature===signature)return false;value.innerHTML=cases.map(item=>lineMarkup(item,action)).join("");const first=cases[0]||{},input=inputOf(first),guard=guardOf(first),exact=exactOf(first);cluster.dataset.inputValue=input;cluster.dataset.guardValue=guard;cluster.dataset.actionValue=action;cluster.dataset.outputValue=action;cluster.dataset.exactEnablingCondition=exact;cluster.dataset.enablingCaseId=text(first?.id);cluster.dataset.enablingCaseCount=String(cases.length);cluster.dataset.ioValue=summaryOf(first,action);cluster.dataset.fullLabel=cases.map(item=>summaryOf(item,action)).join("\n");cluster.dataset.enablingCaseSignature=signature;cluster.classList.add("enabling-case-labels");cluster.classList.toggle("provisional-trigger",cases.some(item=>item?.input_pattern?.confidence==="provisional"));cluster.title=cluster.dataset.fullLabel;cluster.setAttribute("aria-label",cluster.dataset.fullLabel);return true}
async function apply(){if(running)return;const stage=document.querySelector(".state-node")?.closest(".graph-stage");if(!stage||stage.dataset.transitionIoClustersReady!=="true")return;running=true;try{const data=await state(),machine=selectedMachine(data);if(!machine)return;const transitions=machine.transitions||[];let changed=0;for(const [index,transition] of transitions.entries()){const id=transition.id||`T${index+1}`,escaped=window.CSS?.escape?CSS.escape(id):id.replace(/[^A-Za-z0-9_-]/g,"\\$&"),cluster=stage.querySelector(`.transition-io-cluster[data-transition-id="${escaped}"]`);if(cluster&&updateCluster(cluster,transition))changed+=1}stage.dataset.transitionEnablingCasesReady="true";document.dispatchEvent(new CustomEvent("glyph-transition-enabling-cases-ready",{detail:{marker:MARKER,machine:machine.name,changed}}))}finally{running=false}}
function schedule(delay=0){clearTimeout(timer);timer=setTimeout(()=>apply().catch(error=>console.error("transition Enabling Case rendering failed",error)),delay)}
for(const event of["glyph-transition-io-clusters-ready","glyph-transition-semantic-role-lines-ready","glyph-locale-changed"]){document.addEventListener(event,()=>{cache=null;schedule(0)})}
document.addEventListener("change",event=>{if(event.target?.id==="machine-select"){cache=null;schedule(0)}});
new MutationObserver(()=>schedule(24)).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
window.glyphTransitionEnablingCaseLabels={marker:MARKER,apply:()=>schedule(0)};
schedule(0);
})();
</script>
"""


def enhance_transition_enabling_case_labels_html(html: str) -> str:
    """Render compiler-owned Enabling Cases as Input Pattern [Guard] ➞ Action."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
