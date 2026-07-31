from __future__ import annotations


_MARKER = "glyph-transition-layout-transaction-bootstrap-v1"

_SCRIPT = r"""
<script id="glyph-transition-layout-transaction-bootstrap-v1-script">
(()=>{
const MARKER="glyph-transition-layout-transaction-bootstrap-v1";
const transitionScript=name=>`glyph-transition-${name}-v1-script`;
const managed=new Set([
  transitionScript("io-clusters"),
  transitionScript("io-collision-solver"),
  transitionScript("label-readability"),
  transitionScript("readable-layout"),
  transitionScript("semantic-role-lines"),
  transitionScript("dense-canvas-dimensions"),
  transitionScript("node-layout-guard"),
  transitionScript("label-drag-guard"),
]);
const ioClusterScript=transitionScript("io-clusters");
const transactionScript=transitionScript("layout-transaction");
const initialRouterScript=["glyph-initial-transition-routing","v2-script"].join("-");
const publicationScript=["glyph-layout-publication-certificate","v1-script"].join("-");
const transactionDownstreamEvents=new Set([
  "glyph-transition-enabling-cases-ready",
  "glyph-transition-io-clusters-ready",
]);
const transactionReadinessEvents=new Set([
  "glyph-state-transition-ir-v3-labels-ready",
  "glyph-state-transition-ir-v4-labels-ready",
  "glyph-uml-transition-ready",
]);
const publicationIndependentEvents=new Set([
  "glyph-transition-layout-transaction-ready",
  "glyph-execution-context-changed",
  "glyph-locale-changed",
]);
const control={
  marker:MARKER,
  version:3,
  ownsScheduling:false,
  managedScripts:managed,
  protocol:"layout-generation-v1",
};
const nativeAdd=EventTarget.prototype.addEventListener;
const nativeSetTimeout=window.setTimeout.bind(window);
const NativeMutationObserver=window.MutationObserver;
let routeRequestSequence=0;
let routeRetryTimer=null;

function owner(){return document.currentScript?.id||""}
function stageOf(){return document.querySelector(".state-node")?.closest(".graph-stage")||null}
function generationOf(stage=stageOf()){
  return String(stage?.dataset.transitionLayoutGeneration||"0");
}
function allowPassiveInteraction(ownerId,type,event){
  if(ownerId!==ioClusterScript)return false;
  if(!["mouseenter","mouseleave"].includes(type))return false;
  return Boolean(event?.target?.closest?.(".transition-io-cluster"));
}
function ensureTransactionPrerequisite(stage=stageOf()){
  if(!stage||stage.dataset.editorReady==="true")return false;
  stage.dataset.editorReady="true";
  stage.dataset.transitionEditorPrerequisite="synthetic";
  return true;
}
function releaseTransactionPrerequisite(stage=stageOf()){
  if(!stage||stage.dataset.transitionEditorPrerequisite!=="synthetic")return false;
  delete stage.dataset.editorReady;
  delete stage.dataset.transitionEditorPrerequisite;
  return true;
}
function invalidateDownstream(stage,generation){
  if(!stage)return;
  const value=String(generation??generationOf(stage));
  stage.dataset.transitionPublicationReady="false";
  stage.dataset.initialRouteReady="pending";
  stage.dataset.initialRouteCertificate="pending";
  stage.dataset.initialRouteLayoutGeneration=value;
  stage.dataset.layoutProtocolGeneration=value;
  stage.dataset.layoutCertificateRequestState="invalidated";
  delete stage.dataset.initialTransitionRouting;
}
function initialRoutingEligible(stage=stageOf()){
  return Boolean(stage&&stage.dataset.transitionLayoutState==="ready");
}
function routeProtocolDetails(stage=stageOf()){
  const selected=document.getElementById("machine-select")?.selectedOptions?.[0]?.textContent?.trim()||"";
  const machine=(typeof snapshot==="object"&&snapshot?.views?.state?.machines||[])
    .find(item=>item.name===selected)
    ||(typeof snapshot==="object"&&snapshot?.views?.state?.machines||[])[0]
    ||null;
  const stateNames=[...(stage?.querySelectorAll(".state-name")||[])]
    .map(node=>node.textContent?.trim()||"");
  return {
    selectedMachine:selected,
    initialState:machine?.initial_state??null,
    stateNames,
    labelsReady:stage?.dataset.transitionInputActionLabelsReady||"",
    layoutState:stage?.dataset.transitionLayoutState||"",
    layoutGeneration:generationOf(stage),
    hasSvg:Boolean(stage?.querySelector(":scope > svg.edge-svg")),
    hasInitialPath:Boolean(stage?.querySelector(":scope > svg.edge-svg > path:not(.state-transition-path)")),
    hasInitialDot:Boolean(stage?.querySelector(".initial-dot")),
    routerGeneration:window.glyphInitialTransitionRouter?.generation??null,
    routerCompletedGeneration:window.glyphInitialTransitionRouter?.completedGeneration??null,
    requestSequence:routeRequestSequence,
  };
}
function markRouteProtocolFailure(stage,state,reason){
  if(!stage)return;
  const details=routeProtocolDetails(stage);
  stage.dataset.initialRouteProtocolState=state;
  stage.dataset.initialRouteReady="failed";
  stage.dataset.initialRouteCertificate="failed";
  stage.dataset.initialRouteError=reason;
  stage.dataset.initialRouteFailureDetails=JSON.stringify(details);
  stage.dataset.transitionPublicationReady="false";
  stage.dataset.layoutCertificateState="failed";
  stage.dataset.layoutCertificateRequestState="failed";
  stage.dataset.layoutCertificateReason="initial-route-protocol-failed";
  stage.dataset.layoutCertificateViolations=JSON.stringify([{kind:state,reason,details}]);
}
function publicationEligible(event,stage=stageOf()){
  if(!stage||stage.dataset.transitionLayoutState!=="ready")return false;
  if(event?.detail?.stable!==true)return false;
  const layoutGeneration=generationOf(stage);
  const routeGeneration=String(
    event?.detail?.layoutGeneration
    ??stage.dataset.initialRouteLayoutGeneration
    ??""
  );
  return routeGeneration===layoutGeneration
    &&stage.dataset.initialRouteCertificate==="valid"
    &&stage.dataset.initialRouteSettleState==="stable";
}

EventTarget.prototype.addEventListener=function(type,listener,options){
  const ownerId=owner();
  if(typeof listener!=="function")return nativeAdd.call(this,type,listener,options);

  if(ownerId===transactionScript&&transactionDownstreamEvents.has(type))return;
  if(ownerId===publicationScript
    &&(publicationIndependentEvents.has(type)||type==="change"))return;

  if(ownerId===publicationScript&&type==="glyph-initial-transition-route-ready"){
    const wrapped=function(event){
      const stage=stageOf();
      if(!publicationEligible(event,stage))return;
      const generation=generationOf(stage);
      stage.dataset.layoutProtocolPublicationRequest=`${generation}:stable-initial-route`;
      return listener.call(this,event);
    };
    return nativeAdd.call(this,type,wrapped,options);
  }

  if(ownerId===initialRouterScript){
    if(["pagehide","beforeunload"].includes(type)){
      return nativeAdd.call(this,type,listener,options);
    }
    return;
  }

  if(ownerId===transactionScript&&!(["pagehide","beforeunload"].includes(type))){
    const wrapped=function(event){
      const stage=stageOf();
      const api=window.glyphTransitionLayoutTransaction;
      const inFlight=Boolean(api&&api.completedGeneration<api.generation);
      if(transactionReadinessEvents.has(type)
        &&(inFlight||["pending","ready"].includes(stage?.dataset.transitionLayoutState))){
        return;
      }
      ensureTransactionPrerequisite(stage);
      const result=listener.call(this,event);
      invalidateDownstream(stage,api?.generation);
      return result;
    };
    return nativeAdd.call(this,type,wrapped,options);
  }

  if(!managed.has(ownerId))return nativeAdd.call(this,type,listener,options);
  const wrapped=function(event){
    if(control.ownsScheduling&&!allowPassiveInteraction(ownerId,type,event))return;
    return listener.call(this,event);
  };
  return nativeAdd.call(this,type,wrapped,options);
};

window.setTimeout=function(callback,delay,...args){
  const ownerId=owner();
  if(typeof callback!=="function")return nativeSetTimeout(callback,delay,...args);
  if(ownerId===transactionScript){
    return nativeSetTimeout((...values)=>{
      ensureTransactionPrerequisite();
      invalidateDownstream(stageOf(),window.glyphTransitionLayoutTransaction?.generation);
      callback(...values);
    },delay,...args);
  }
  if(ownerId===initialRouterScript){
    return nativeSetTimeout((...values)=>{
      if(!initialRoutingEligible())return;
      callback(...values);
    },delay,...args);
  }
  if(ownerId===publicationScript){
    return nativeSetTimeout((...values)=>{
      const stage=stageOf();
      if(!stage||stage.dataset.initialRouteSettleState!=="stable")return;
      callback(...values);
    },delay,...args);
  }
  if(!managed.has(ownerId))return nativeSetTimeout(callback,delay,...args);
  return nativeSetTimeout((...values)=>{
    if(control.ownsScheduling)return;
    callback(...values);
  },delay,...args);
};

window.MutationObserver=class GlyphManagedMutationObserver extends NativeMutationObserver{
  constructor(callback){
    const ownerId=owner();
    super((records,observer)=>{
      if(control.ownsScheduling&&managed.has(ownerId))return;
      if(ownerId===initialRouterScript)return;
      callback(records,observer);
    });
  }
};

function wrapTransactionApi(){
  const api=window.glyphTransitionLayoutTransaction;
  if(!api||api.layoutGenerationProtocol===MARKER)return Boolean(api);
  const original=api.schedule.bind(api);
  api.schedule=(reason="scheduled",delay=0)=>{
    const stage=stageOf();
    if(reason==="state-tab-activated"
      &&stage
      &&["pending","ready"].includes(stage.dataset.transitionLayoutState)){
      return api.generation;
    }
    ensureTransactionPrerequisite(stage);
    const generation=original(reason,delay);
    invalidateDownstream(stage,generation);
    return generation;
  };
  api.layoutGenerationProtocol=MARKER;
  return true;
}
function initialRouteDomReady(stage){
  const svg=stage?.querySelector(":scope > svg.edge-svg");
  return Boolean(stage
    &&stage.dataset.transitionInputActionLabelsReady==="true"
    &&stage.dataset.transitionLayoutState==="ready"
    &&svg?.querySelector(":scope > path:not(.state-transition-path)")
    &&stage.querySelector(".initial-dot")
    &&stage.querySelector(".state-node"));
}
function wrapInitialRouterApi(){
  const api=window.glyphInitialTransitionRouter;
  if(!api||api.layoutGenerationProtocol===MARKER)return Boolean(api);
  const original=api.schedule.bind(api);
  function request(reason="scheduled",delay=0){
    const stage=stageOf();
    if(!initialRoutingEligible(stage))return api.generation;
    const generation=generationOf(stage);
    const requestToken=++routeRequestSequence;
    invalidateDownstream(stage,generation);
    clearTimeout(routeRetryTimer);
    stage.dataset.initialRouteProtocolSequence=String(requestToken);
    stage.dataset.initialRouteProtocolReason=reason;
    stage.dataset.initialRouteProtocolState="waiting-dom";
    const run=attempt=>{
      const current=stageOf();
      if(requestToken!==routeRequestSequence
        ||current!==stage
        ||generationOf(current)!==generation
        ||!initialRoutingEligible(current))return;
      if(!initialRouteDomReady(current)){
        if(attempt>=120){
          markRouteProtocolFailure(
            current,
            "dom-timeout",
            "initial-route DOM prerequisites did not become ready",
          );
          return;
        }
        routeRetryTimer=nativeSetTimeout(()=>run(attempt+1),16);
        return;
      }
      current.dataset.initialRouteProtocolAttempt=String(attempt);
      current.dataset.initialRouteProtocolState=attempt?"retrying":"running";
      const routerGeneration=original(reason,0);
      current.dataset.initialRouteProtocolRouterGeneration=String(routerGeneration);
      const inspect=poll=>{
        if(requestToken!==routeRequestSequence
          ||generationOf(stageOf())!==generation
          ||stage.dataset.initialRouteCertificate==="valid")return;
        if(api.completedGeneration<routerGeneration){
          if(poll>=120){
            markRouteProtocolFailure(
              stage,
              "router-timeout",
              "initial-route router generation did not complete",
            );
            return;
          }
          routeRetryTimer=nativeSetTimeout(()=>inspect(poll+1),16);
          return;
        }
        if(attempt>=8){
          markRouteProtocolFailure(
            stage,
            "router-stalled",
            "initial-route router completed without issuing a certificate",
          );
          return;
        }
        run(attempt+1);
      };
      routeRetryTimer=nativeSetTimeout(()=>inspect(0),32);
    };
    routeRetryTimer=nativeSetTimeout(()=>run(0),Math.max(0,delay));
    return api.generation;
  }
  api.schedule=request;
  api.layoutGenerationProtocol=MARKER;
  return true;
}
function wrapPublicationApi(){
  const api=window.glyphLayoutPublicationCertificate;
  if(!api||api.layoutGenerationProtocol===MARKER)return Boolean(api);
  const original=api.schedule.bind(api);
  api.schedule=(reason="scheduled",delay=0)=>{
    const stage=stageOf();
    if(reason!=="stable-initial-route")return api.generation;
    const generation=generationOf(stage);
    const request=`${generation}:stable-initial-route`;
    if(!stage
      ||stage.dataset.transitionLayoutState!=="ready"
      ||stage.dataset.initialRouteCertificate!=="valid"
      ||stage.dataset.initialRouteSettleState!=="stable"
      ||String(stage.dataset.initialRouteLayoutGeneration||"")!==generation){
      return api.generation;
    }
    if(stage.dataset.layoutProtocolPublicationRequest===request
      &&["queued","running","completed"].includes(
        stage.dataset.layoutCertificateRequestState||""
      ))return api.generation;
    stage.dataset.layoutProtocolPublicationRequest=request;
    return original(reason,delay);
  };
  api.layoutGenerationProtocol=MARKER;
  return true;
}
function installProtocolApis(){
  wrapTransactionApi();
  wrapInitialRouterApi();
  wrapPublicationApi();
}

document.addEventListener("glyph-transition-layout-transaction-ready",event=>{
  const stage=stageOf();
  const generation=String(event?.detail?.generation??generationOf(stage));
  invalidateDownstream(stage,generation);
  releaseTransactionPrerequisite(stage);
  installProtocolApis();
  window.glyphInitialTransitionRouter?.schedule?.("transaction-generation-ready",0);
},{capture:true});

document.addEventListener("glyph-initial-transition-route-ready",event=>{
  const stage=stageOf();
  if(!stage)return;
  const generation=generationOf(stage);
  if(event?.detail&&event.detail.stable!==true){
    event.detail.layoutGeneration=generation;
    stage.dataset.initialRouteLayoutGeneration=generation;
    stage.dataset.transitionPublicationReady="false";
  }
},{capture:true});

document.addEventListener("glyph-layout-publication-certificate-ready",event=>{
  const stage=stageOf();
  if(!stage)return;
  stage.dataset.layoutProtocolPublishedGeneration=generationOf(stage);
  releaseTransactionPrerequisite(stage);
  document.dispatchEvent(new CustomEvent("glyph-initial-transition-ready",{
    detail:{
      marker:MARKER,
      generation:generationOf(stage),
      publication:event?.detail||null,
    },
  }));
});

document.addEventListener("DOMContentLoaded",installProtocolApis,{once:true});
nativeSetTimeout(installProtocolApis,0);
window.glyphTransitionLegacyControl=control;
})();
</script>
"""


def enhance_transition_layout_transaction_bootstrap_html(html: str) -> str:
    """Install one layout owner and a generation-ordered publication protocol."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
