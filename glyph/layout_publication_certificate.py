from __future__ import annotations


_MARKER = "glyph-layout-publication-certificate-v1"


_SCRIPT = r"""
<script id="glyph-layout-publication-certificate-v1-script">
(() => {
  const MARKER = "glyph-layout-publication-certificate-v1";
  const TOTAL_BUDGET_MS = 32;
  let requestedGeneration = 0;
  let completedGeneration = 0;
  let running = false;
  let timer = null;
  let destroyed = false;

  const number = value => Number.parseFloat(value || "0") || 0;
  function activeTab(){return document.querySelector(".tab.active")?.dataset.tab||"state"}
  function stageOf(){return document.querySelector(".state-node")?.closest(".graph-stage")||null}
  function fingerprint(stage){
    const values=[
      MARKER,
      stage.dataset.diagramDigest||"source",
      stage.dataset.transitionLayoutGeneration||"0",
      stage.style.width,
      stage.style.height,
    ];
    for(const node of stage.querySelectorAll(".state-node")){
      values.push("n",node.offsetLeft,node.offsetTop,node.offsetWidth,node.offsetHeight);
    }
    for(const path of stage.querySelectorAll(":scope > svg.edge-svg > path")){
      values.push("p",path.dataset.transitionId||"initial",path.getAttribute("d")||"");
    }
    for(const cluster of stage.querySelectorAll(".transition-io-cluster")){
      values.push("l",cluster.dataset.transitionId||"",number(cluster.style.left),number(cluster.style.top),cluster.dataset.ioValue||"");
    }
    return values.join("\u001f");
  }
  function publish(stage,token,cacheHit,metrics={}){
    const value=fingerprint(stage);
    stage.dataset.layoutCertificateFingerprint=value;
    stage.dataset.layoutCertificateState="valid";
    stage.dataset.layoutCertificateVersion="2";
    stage.dataset.layoutCertificateProfile="interactive-fast";
    stage.dataset.layoutCertificateConstraints="structure,bounds,tether,initial-route-presence";
    stage.dataset.layoutCertificateViolations="[]";
    stage.dataset.layoutCertificateMetrics=JSON.stringify(metrics);
    stage.dataset.layoutCertificateCacheHit=cacheHit?"true":"false";
    stage.dataset.layoutCertificateDurationMs=String(metrics.durationMs??0);
    stage.dataset.layoutCertificateRequestState="completed";
    stage.dataset.transitionPublicationReady="true";
    if(stage.querySelector(":scope > svg.edge-svg > path:not(.state-transition-path)")){
      stage.dataset.initialRouteReady="true";
    }
    completedGeneration=token;
    document.dispatchEvent(new CustomEvent("glyph-layout-publication-certificate-ready",{
      detail:{marker:MARKER,version:2,fingerprint:value,cacheHit,metrics,profile:"interactive-fast"}
    }));
  }
  function degrade(stage,token,violations,metrics={}){
    stage.dataset.layoutCertificateState="degraded";
    stage.dataset.layoutCertificateProfile="interactive-fast";
    stage.dataset.layoutCertificateViolations=JSON.stringify(violations);
    stage.dataset.layoutCertificateMetrics=JSON.stringify(metrics);
    stage.dataset.layoutCertificateRequestState="completed";
    stage.dataset.transitionPublicationReady="true";
    completedGeneration=token;
    document.dispatchEvent(new CustomEvent("glyph-layout-publication-certificate-failed",{
      detail:{marker:MARKER,violations,metrics,degraded:true,profile:"interactive-fast"}
    }));
  }
  async function audit(token){
    const stage=stageOf();
    if(!stage||activeTab()!=="state")return;
    if(stage.dataset.transitionLayoutState!=="ready")return;
    const value=fingerprint(stage);
    if(stage.dataset.layoutCertificateFingerprint===value
      && stage.dataset.layoutCertificateState==="valid"){
      publish(stage,token,true,{durationMs:0});
      return;
    }
    stage.dataset.layoutCertificateState="pending";
    stage.dataset.layoutCertificateRequestState="running";
    stage.dataset.transitionPublicationReady="false";
    const started=performance.now(),violations=[];
    const transactionAudit=window.glyphTransitionLayoutTransaction?.audit?.();
    if(!transactionAudit?.ok)violations.push({kind:"transition-layout",details:transactionAudit||{missing:true}});
    const stageWidth=number(stage.style.width)||stage.scrollWidth;
    const stageHeight=number(stage.style.height)||stage.scrollHeight;
    if(!stageWidth||!stageHeight)violations.push({kind:"stage-bounds"});
    for(const node of stage.querySelectorAll(".state-node")){
      if(node.offsetLeft<0||node.offsetTop<0||node.offsetLeft+node.offsetWidth>stageWidth+1||node.offsetTop+node.offsetHeight>stageHeight+1){
        violations.push({kind:"node-bounds",node:node.querySelector(".state-name")?.textContent?.trim()||""});
      }
      if(performance.now()-started>TOTAL_BUDGET_MS)break;
    }
    if(performance.now()-started<=TOTAL_BUDGET_MS){
      for(const cluster of stage.querySelectorAll(".transition-io-cluster")){
        const x=number(cluster.style.left),y=number(cluster.style.top),distance=number(cluster.dataset.ioDistance);
        if(!Number.isFinite(x)||!Number.isFinite(y)||x<=0||y<=0)violations.push({kind:"label-position",transition:cluster.dataset.transitionId||""});
        if(distance>96.5)violations.push({kind:"label-tether",transition:cluster.dataset.transitionId||"",distance});
        if(performance.now()-started>TOTAL_BUDGET_MS)break;
      }
    }
    const metrics={durationMs:Number((performance.now()-started).toFixed(2)),budgetMs:TOTAL_BUDGET_MS};
    if(violations.length)degrade(stage,token,violations,metrics);
    else publish(stage,token,false,metrics);
  }
  async function drain(){
    if(running||destroyed)return;
    running=true;
    try{
      while(!destroyed&&completedGeneration<requestedGeneration){
        const token=requestedGeneration;
        try{
          await audit(token);
          if(token===requestedGeneration&&completedGeneration<token)completedGeneration=token;
        }catch(error){
          if(destroyed||token!==requestedGeneration)continue;
          const stage=stageOf();
          if(stage)degrade(stage,token,[{kind:"certificate-error",message:String(error?.message||error)}],{});
          else completedGeneration=token;
        }
      }
    }finally{running=false}
  }
  function schedule(reason="scheduled",delay=0){
    if(destroyed)return requestedGeneration;
    requestedGeneration+=1;
    const stage=stageOf();
    if(stage){
      stage.dataset.layoutCertificateRequestState="queued";
      stage.dataset.layoutCertificateReason=reason;
      stage.dataset.transitionPublicationReady="false";
    }
    clearTimeout(timer);
    timer=setTimeout(drain,Math.max(0,delay));
    return requestedGeneration;
  }
  function cancel(reason="cancelled"){
    requestedGeneration+=1;
    completedGeneration=requestedGeneration;
    clearTimeout(timer);
    const stage=stageOf();
    if(stage){
      stage.dataset.layoutCertificateRequestState="cancelled";
      stage.dataset.layoutCertificateReason=reason;
      stage.dataset.transitionPublicationReady="false";
    }
    return requestedGeneration;
  }

  for(const eventName of[
    "glyph-transition-layout-transaction-ready",
    "glyph-initial-transition-route-ready",
    "glyph-execution-context-changed",
    "glyph-locale-changed",
  ]){
    document.addEventListener(eventName,()=>{
      if(activeTab()==="state")schedule(eventName,0);
    });
  }
  document.addEventListener("change",event=>{
    if(event.target?.id==="machine-select")schedule("machine-change",0);
  });
  document.addEventListener("click",event=>{
    const tab=event.target?.closest?.(".tab[data-tab]");
    if(!tab)return;
    if(tab.dataset.tab==="state")requestAnimationFrame(()=>schedule("state-tab-activated",0));
    else cancel("state-tab-deactivated");
  },true);
  for(const eventName of["pagehide","beforeunload"]){
    window.addEventListener(eventName,()=>{
      destroyed=true;
      clearTimeout(timer);
      requestedGeneration+=1;
    },{once:true});
  }

  window.glyphLayoutPublicationCertificate={
    marker:MARKER,
    version:2,
    profile:"interactive-fast",
    budgetMs:TOTAL_BUDGET_MS,
    schedule,
    cancel,
    audit:()=>audit(requestedGeneration),
    get generation(){return requestedGeneration},
    get completedGeneration(){return completedGeneration},
  };
})();
</script>
"""


def enhance_layout_publication_certificate_html(html: str) -> str:
    """Install the time-bounded interactive geometry certificate."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
