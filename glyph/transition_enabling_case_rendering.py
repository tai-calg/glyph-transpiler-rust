from __future__ import annotations


_MARKER = "glyph-transition-enabling-cases-v1"

_SCRIPT = r'''
<script id="glyph-transition-enabling-cases-v1-script">
(()=>{
const MARKER="glyph-transition-enabling-cases-v1";
let cache=null,timer=null,running=false;
const text=value=>String(value??"").trim();
const esc=value=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
async function state(){if(cache)return cache;const response=await fetch("/api/state",{cache:"no-store"});if(!response.ok)throw Error("diagram state unavailable");return cache=await response.json()}
function selectedMachine(data){const machines=data?.views?.state?.machines||[],name=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent;return machines.find(machine=>machine.name===name)||machines[0]||null}
function actionOf(transition){const action=transition?.action;if(typeof action==="string")return text(action);return text(action?.display)||text(action?.expression)}
function casesOf(transition){return Array.isArray(transition?.enabling_cases)?transition.enabling_cases:[]}
function inputOf(item){const input=item?.input_pattern;return input?`${input.confidence==="fallback"?"? ":""}${text(input.display)||text(input.expression)}`:""}
function guardOf(item){return text(item?.guard?.display)||text(item?.guard?.expression).replace(/^true$/i,"")}
function lineOf(item,action){const input=inputOf(item),guard=guardOf(item),left=`${input}${guard?` [${guard}]`:""}`.trim();return`${left}${action?`${left?" ":""}➞ ${action}`:""}`.trim()}
function update(cluster,transition){const cases=casesOf(transition);if(!cases.length)return false;const action=actionOf(transition),lines=cases.map(item=>lineOf(item,action)).filter(Boolean),value=cluster.querySelector(".transition-io-value");if(!value)return false;const signature=JSON.stringify([cases,action]);if(cluster.dataset.enablingCaseSignature===signature)return false;value.replaceChildren(...lines.map(line=>{const span=document.createElement("span");span.className="transition-semantic-line transition-role-line enabling-case-line";span.textContent=line;return span}));const first=cases[0]||{};cluster.dataset.inputValue=inputOf(first);cluster.dataset.guardValue=guardOf(first);cluster.dataset.actionValue=action;cluster.dataset.outputValue=action;cluster.dataset.ioValue=lines.join(" || ");cluster.dataset.fullLabel=lines.join("\n");cluster.dataset.enablingCaseCount=String(cases.length);cluster.dataset.legacyProjectionLossy=String(Boolean(transition?.legacy_projection_lossy));cluster.dataset.enablingCaseSignature=signature;cluster.title=lines.join("\n");cluster.setAttribute("aria-label",lines.join("; "));cluster.classList.toggle("multiple-enabling-cases",cases.length>1);return true}
async function apply(){if(running)return;const stage=document.querySelector(".state-node")?.closest(".graph-stage");if(!stage||stage.dataset.transitionIoClustersReady!=="true")return;running=true;try{const data=await state(),machine=selectedMachine(data);if(!machine)return;let changed=0;(machine.transitions||[]).forEach((transition,index)=>{const id=transition.id||`T${index+1}`,escaped=window.CSS?.escape?CSS.escape(id):id.replace(/[^A-Za-z0-9_-]/g,"\\$&"),cluster=stage.querySelector(`.transition-io-cluster[data-transition-id="${escaped}"]`);if(cluster&&update(cluster,transition))changed+=1});stage.dataset.transitionEnablingCasesReady="true";document.dispatchEvent(new CustomEvent("glyph-transition-enabling-cases-ready",{detail:{marker:MARKER,changed}}));window.glyphTransitionSemanticRoleLines?.apply?.()}finally{running=false}}
function schedule(delay=0){clearTimeout(timer);timer=setTimeout(()=>apply().catch(error=>console.error("enabling-case rendering failed",error)),delay)}
for(const event of["glyph-transition-io-clusters-ready","glyph-locale-changed","glyph-state-transition-ir-v3-labels-ready"]){document.addEventListener(event,()=>{cache=null;schedule(0)})}
document.addEventListener("change",event=>{if(event.target?.id==="machine-select"){cache=null;schedule(0)}});
new MutationObserver(()=>schedule(30)).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
window.glyphTransitionEnablingCases={marker:MARKER,apply:()=>schedule(0)};
schedule(0);
})();
</script>
'''


def enhance_transition_enabling_case_rendering_html(html: str) -> str:
    """Render Input Pattern and Guard only from StateTransitionIR enabling_cases."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
