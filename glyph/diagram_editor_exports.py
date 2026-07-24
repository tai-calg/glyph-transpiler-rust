from __future__ import annotations


_MARKER = "glyph-diagram-editor-exports-v1"

_STYLE = r"""
<style id="glyph-diagram-editor-exports-v1-style">
:root{
  color-scheme:light;
  --bg:#f4f6f8;--panel:#ffffff;--panel2:#f8fafc;--panel3:#eef2f6;
  --line:#d7dde5;--text:#18212f;--muted:#667085;--faint:#98a2b3;
  --blue:#2563eb;--green:#16865b;--purple:#7557b7;--red:#c73546;--amber:#9a6700;
  --shadow:0 12px 32px rgba(16,24,40,.10);
}
body{background:var(--bg)!important;color:var(--text)!important}
header,.toolbar,.viewer-head,.diagnostics,.editor-pane,.lines{background:#fff!important}
.editor{background:#fbfcfe!important;color:#1f2937!important}
.canvas-shell{background:linear-gradient(rgba(15,23,42,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(15,23,42,.035) 1px,transparent 1px),#fff!important;background-size:24px 24px!important;box-shadow:var(--shadow)!important}
.graph-node{border-color:#b8c4d2!important;background:#fff!important;box-shadow:0 8px 20px rgba(16,24,40,.09)!important}
.graph-node.effect{border-color:#baa9d4!important;background:#fcfaff!important}.graph-node.external{background:#fafafa!important}
.state-node{border-color:#60758a!important;background:#fff!important;box-shadow:0 7px 18px rgba(16,24,40,.10)!important}
.edge-label,.transition-label{background:#fff!important;color:#344054!important;border-color:#cfd7e2!important;box-shadow:0 2px 8px rgba(16,24,40,.08)}
.transition-label.failure-transition{background:#fff7f8!important;color:#a42838!important}
.initial-transition-path{stroke:#111827!important}.initial-dot{background:#111827!important}
.diagram-tools{display:flex;align-items:center;gap:6px;margin-left:8px;flex-wrap:wrap}
.diagram-tools select,.diagram-tools button{height:34px;padding:6px 9px;background:#fff;color:#344054;border-color:#d0d5dd}
.diagram-tools button:hover{background:#f2f4f7}.diagram-tools .export{font-weight:650}
.diagram-tools .separator{width:1px;height:22px;background:#d0d5dd;margin:0 2px}
.graph-stage.editable .state-node,.graph-stage.editable .graph-node{cursor:grab;user-select:none;touch-action:none}
.graph-stage.editable .state-node.dragging,.graph-stage.editable .graph-node.dragging{cursor:grabbing;z-index:20;box-shadow:0 12px 28px rgba(37,99,235,.20)!important;outline:2px solid rgba(37,99,235,.35)}
.graph-stage .selected-node{outline:2px solid #2563eb;outline-offset:3px}
.theme-monochrome{--blue:#111;--green:#111;--purple:#111;--red:#111;--amber:#111;--text:#111;--muted:#333;--faint:#666;--line:#aaa}
.theme-monochrome body,.theme-monochrome header,.theme-monochrome .toolbar,.theme-monochrome .viewer-head,.theme-monochrome .editor-pane,.theme-monochrome .lines,.theme-monochrome .canvas-shell{background:#fff!important;color:#111!important}
.theme-monochrome .canvas-shell{background:#fff!important;box-shadow:none!important;border:1px solid #111!important}
.theme-monochrome .state-node,.theme-monochrome .graph-node{background:#fff!important;border-color:#111!important;color:#111!important;box-shadow:none!important}
.theme-monochrome .state-node.failure,.theme-monochrome .state-node.success{border-color:#111!important}
.theme-monochrome .state-node.unreachable{opacity:1!important}
.theme-monochrome .edge-label,.theme-monochrome .transition-label{background:#fff!important;color:#111!important;border-color:#111!important;box-shadow:none!important}
.theme-monochrome .state-transition-path,.theme-monochrome .initial-transition-path,.theme-monochrome .edge-svg path{stroke:#111!important}
.theme-monochrome .failure-transition{stroke-dasharray:7 5!important}
.theme-monochrome .view-body{background:#fff}
@media print{
  header,.editor-pane,.splitter,.viewer-head,.view-controls,.machine-meta,.analysis-panel,.legend,.type-section{display:none!important}
  body,.app,main,.viewer,.view-body{height:auto!important;overflow:visible!important;background:#fff!important}
  main{display:block!important}.view-body{padding:0!important}.canvas-shell{border:0!important;box-shadow:none!important;overflow:visible!important}
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-editor-exports-v1-script">
(() => {
  const MARKER = "glyph-diagram-editor-exports-v1";
  const root = document.documentElement;
  let selected = null;
  let drag = null;
  let stateCache = null;
  let stateCacheAt = 0;

  const byId = id => document.getElementById(id);
  const text = value => String(value ?? "");
  const clamp = (value, low, high) => Math.max(low, Math.min(high, value));
  const num = value => Number.parseFloat(value || "0") || 0;
  const download = (blob, name) => { const url=URL.createObjectURL(blob); const a=document.createElement("a"); a.href=url;a.download=name;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),500); };

  async function readState(force=false){
    if(!force && stateCache && Date.now()-stateCacheAt<600)return stateCache;
    const response=await fetch("/api/state",{cache:"no-store"});
    if(!response.ok)throw new Error("diagram state is unavailable");
    stateCache=await response.json();stateCacheAt=Date.now();return stateCache;
  }
  function selectedMachine(state){const rows=state?.views?.state?.machines||[];const name=byId("machine-select")?.selectedOptions?.[0]?.textContent;return rows.find(row=>row.name===name)||rows[0]||null}
  function selectedSystem(state){const rows=state?.views?.io?.systems||[];const name=byId("system-select")?.selectedOptions?.[0]?.textContent;return rows.find(row=>row.name===name)||rows[0]||null}
  function viewKey(stage){
    const tab=document.querySelector(".tab.active")?.dataset.tab||"state";
    const item=tab==="state"?byId("machine-select")?.value||"0":byId("system-select")?.value||"0";
    return `glyph.diagram.positions.v1:${stateCache?.digest||"source"}:${tab}:${item}`;
  }
  function nodeId(node){return node.querySelector(".state-name,.node-name")?.textContent?.trim()||node.dataset.nodeId||"node"}
  function positions(stage){const result={};stage.querySelectorAll(".state-node,.graph-node").forEach(node=>{result[nodeId(node)]={x:num(node.style.left),y:num(node.style.top)}});return result}
  function savePositions(stage){try{localStorage.setItem(viewKey(stage),JSON.stringify(positions(stage)))}catch(_){}}
  function restorePositions(stage){
    let saved=null;try{saved=JSON.parse(localStorage.getItem(viewKey(stage))||"null")}catch(_){}
    if(!saved)return false;
    let changed=false;stage.querySelectorAll(".state-node,.graph-node").forEach(node=>{const p=saved[nodeId(node)];if(!p)return;node.style.left=`${p.x}px`;node.style.top=`${p.y}px`;changed=true});return changed;
  }
  function clearPositions(stage){try{localStorage.removeItem(viewKey(stage))}catch(_){}}

  function statePath(a,b,same,index){
    const aw=a.offsetWidth,bw=b.offsetWidth,ah=a.offsetHeight,bh=b.offsetHeight;
    const x1=a.offsetLeft+aw/2,y1=a.offsetTop+ah/2,x2=b.offsetLeft+bw/2,y2=b.offsetTop+bh/2;
    if(same){const spread=58+(index%3)*14;return `M ${x1-27} ${y1-ah*.42} C ${x1-spread} ${y1-98}, ${x1+spread} ${y1-98}, ${x1+27} ${y1-ah*.42}`}
    const dx=x2-x1,dy=y2-y1,len=Math.max(1,Math.hypot(dx,dy));
    const rx=aw/2,ry=ah/2;const sx=x1+dx/len*rx,sy=y1+dy/len*ry,tx=x2-dx/len*(bw/2),ty=y2-dy/len*(bh/2),offset=(index%3-1)*22;
    return `M ${sx} ${sy} Q ${(sx+tx)/2-dy*.1+offset} ${(sy+ty)/2+dx*.1+offset} ${tx} ${ty}`;
  }
  function ioPath(a,b){const x1=a.offsetLeft+a.offsetWidth,y1=a.offsetTop+a.offsetHeight/2,x2=b.offsetLeft,y2=b.offsetTop+b.offsetHeight/2,m=Math.max(60,(x2-x1)*.48);return `M ${x1} ${y1} C ${x1+m} ${y1}, ${x2-m} ${y2}, ${x2} ${y2}`}
  async function reroute(stage){
    const state=await readState();const isState=stage.querySelector(".state-node")!==null;
    const svg=stage.querySelector(":scope > svg.edge-svg");if(!svg)return;
    if(isState){
      const machine=selectedMachine(state);if(!machine)return;
      const nodes=new Map([...stage.querySelectorAll(".state-node")].map(node=>[nodeId(node),node]));
      const paths=[...svg.querySelectorAll("path.state-transition-path")];
      const labels=[...stage.querySelectorAll(".edge-label.transition-label")];
      (machine.transitions||[]).forEach((transition,index)=>{const a=nodes.get(transition.source_state),b=nodes.get(transition.target_state);if(!a||!b)return;paths[index]?.setAttribute("d",statePath(a,b,a===b,index));if(labels[index]){labels[index].style.left=`${(a.offsetLeft+b.offsetLeft+a.offsetWidth)/2+(index%3-1)*18}px`;labels[index].style.top=`${(a.offsetTop+b.offsetTop+a.offsetHeight)/2-(a===b?80:0)+(index%2)*12}px`;}});
      delete stage.dataset.initialTransitionRouting;
      delete stage.dataset.transitionLabelLayout;
      document.dispatchEvent(new CustomEvent("glyph-transition-input-action-labels-ready"));
      document.dispatchEvent(new CustomEvent("glyph-transition-layout-ready"));
    }else{
      const system=selectedSystem(state);if(!system)return;
      const nodes=new Map([...stage.querySelectorAll(".graph-node")].map(node=>[nodeId(node),node]));
      const paths=[...svg.querySelectorAll(":scope > path")];const labels=[...stage.querySelectorAll(".edge-label")];
      (system.edges||[]).forEach((edge,index)=>{const a=nodes.get((system.nodes||[]).find(n=>n.id===edge.source_id)?.name),b=nodes.get((system.nodes||[]).find(n=>n.id===edge.target_id)?.name);if(!a||!b)return;paths[index]?.setAttribute("d",ioPath(a,b));if(labels[index]){labels[index].style.left=`${(a.offsetLeft+b.offsetLeft+a.offsetWidth)/2}px`;labels[index].style.top=`${(a.offsetTop+b.offsetTop+a.offsetHeight)/2}px`;}});
    }
  }

  function selectNode(node){selected?.classList.remove("selected-node");selected=node;if(selected)selected.classList.add("selected-node")}
  function makeEditable(stage){
    if(stage.dataset.editorReady==="true")return;stage.dataset.editorReady="true";stage.classList.add("editable");
    restorePositions(stage);reroute(stage).catch(()=>{});
    stage.querySelectorAll(".state-node,.graph-node").forEach(node=>{
      node.addEventListener("pointerdown",event=>{if(event.button!==0)return;event.preventDefault();selectNode(node);node.classList.add("dragging");node.setPointerCapture(event.pointerId);drag={node,stage,startX:event.clientX,startY:event.clientY,left:num(node.style.left),top:num(node.style.top)};});
      node.addEventListener("pointermove",event=>{if(!drag||drag.node!==node)return;const grid=event.shiftKey?1:8;const x=Math.round(clamp(drag.left+event.clientX-drag.startX,8,stage.scrollWidth-node.offsetWidth-8)/grid)*grid;const y=Math.round(clamp(drag.top+event.clientY-drag.startY,8,stage.scrollHeight-node.offsetHeight-8)/grid)*grid;node.style.left=`${x}px`;node.style.top=`${y}px`;reroute(stage).catch(()=>{});});
      node.addEventListener("pointerup",()=>{if(!drag||drag.node!==node)return;node.classList.remove("dragging");savePositions(stage);reroute(stage).catch(()=>{});drag=null;});
      node.addEventListener("click",event=>{event.stopPropagation();selectNode(node)});
    });
    stage.addEventListener("click",()=>selectNode(null));
  }

  function xmlEscape(value){return text(value).replace(/[&<>\"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]))}
  function activeStage(){const stage=document.querySelector(".graph-stage");if(!stage)throw new Error("表示中の図がない");return stage}
  function svgText(x,y,value,size=12,weight=400,anchor="start"){return `<text x="${x}" y="${y}" font-family="Arial,Helvetica,sans-serif" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}" fill="#111">${xmlEscape(value)}</text>`}
  function exportedSvg(){
    const stage=activeStage(),width=Math.ceil(stage.scrollWidth),height=Math.ceil(stage.scrollHeight);let body="";
    const edge=stage.querySelector(":scope > svg.edge-svg");if(edge){const clone=edge.cloneNode(true);clone.setAttribute("xmlns","http://www.w3.org/2000/svg");clone.querySelectorAll("path").forEach(path=>{path.setAttribute("stroke",root.classList.contains("theme-monochrome")?"#111":path.classList.contains("failure-transition")?"#c73546":"#60758a");path.setAttribute("fill","none")});body+=clone.innerHTML;}
    const initial=stage.querySelector(".initial-dot");if(initial)body+=`<circle cx="${initial.offsetLeft+initial.offsetWidth/2}" cy="${initial.offsetTop+initial.offsetHeight/2}" r="9" fill="#111"/>`;
    stage.querySelectorAll(".state-node").forEach(node=>{const x=node.offsetLeft,y=node.offsetTop,w=node.offsetWidth,h=node.offsetHeight,dashed=node.classList.contains("unreachable")?' stroke-dasharray="7 5"':'';body+=`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${h/2}" fill="#fff" stroke="#111" stroke-width="2"${dashed}/>`;body+=svgText(x+w/2,y+h/2+4,nodeId(node),14,700,"middle");const terminal=node.querySelector(".state-terminal")?.textContent?.trim();if(terminal)body+=svgText(x+w/2,y+h/2+20,terminal,9,500,"middle")});
    stage.querySelectorAll(".graph-node").forEach(node=>{const x=node.offsetLeft,y=node.offsetTop,w=node.offsetWidth,h=node.offsetHeight;body+=`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="10" fill="#fff" stroke="#111" stroke-width="1.5"/>`;body+=svgText(x+12,y+22,node.querySelector(".node-kind")?.textContent||"",9,500);body+=svgText(x+12,y+43,nodeId(node),15,700);[...node.querySelectorAll(".port-text")].forEach((port,index)=>body+=svgText(x+14,y+67+index*17,port.textContent||"",10,400))});
    stage.querySelectorAll(".edge-label").forEach(label=>{const x=label.offsetLeft-label.offsetWidth/2,y=label.offsetTop-label.offsetHeight/2,w=label.offsetWidth,h=label.offsetHeight;body+=`<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="4" fill="#fff" stroke="#777"/>`;body+=svgText(x+w/2,y+h/2+4,label.textContent||"",10,500,"middle")});
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="#fff"/>${body}</svg>`;
  }
  function fileBase(){const machine=byId("machine-select")?.selectedOptions?.[0]?.textContent||byId("system-select")?.selectedOptions?.[0]?.textContent||"glyph-diagram";return machine.trim().replace(/[^A-Za-z0-9._-]+/g,"-").replace(/^-|-$/g,"")||"glyph-diagram"}
  function exportSvg(){download(new Blob([exportedSvg()],{type:"image/svg+xml;charset=utf-8"}),`${fileBase()}.svg`)}
  async function renderCanvas(scale=2){const svg=exportedSvg();const image=new Image();const url=URL.createObjectURL(new Blob([svg],{type:"image/svg+xml"}));await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;image.src=url});const canvas=document.createElement("canvas");canvas.width=image.naturalWidth*scale;canvas.height=image.naturalHeight*scale;const context=canvas.getContext("2d");context.scale(scale,scale);context.fillStyle="#fff";context.fillRect(0,0,image.naturalWidth,image.naturalHeight);context.drawImage(image,0,0);URL.revokeObjectURL(url);return canvas}
  async function exportPng(){const canvas=await renderCanvas(2);canvas.toBlob(blob=>blob&&download(blob,`${fileBase()}.png`),"image/png")}
  function binaryString(bytes){let result="";for(let i=0;i<bytes.length;i+=8192)result+=String.fromCharCode(...bytes.subarray(i,i+8192));return result}
  async function exportPdf(){
    const canvas=await renderCanvas(2),jpeg=canvas.toDataURL("image/jpeg",.94).split(",")[1],imageBytes=Uint8Array.from(atob(jpeg),c=>c.charCodeAt(0));
    const pageW=841.89,pageH=595.28,margin=28,ratio=Math.min((pageW-2*margin)/canvas.width,(pageH-2*margin)/canvas.height),w=canvas.width*ratio,h=canvas.height*ratio,x=(pageW-w)/2,y=(pageH-h)/2;
    const stream=`q\n${w.toFixed(2)} 0 0 ${h.toFixed(2)} ${x.toFixed(2)} ${y.toFixed(2)} cm\n/Im0 Do\nQ\n`;
    const objects=["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 >>",`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pageW} ${pageH}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`,null,`<< /Length ${stream.length} >>\nstream\n${stream}endstream`];
    let pdf="%PDF-1.4\n%\xE2\xE3\xCF\xD3\n",offsets=[0];
    for(let i=0;i<objects.length;i++){offsets.push(pdf.length);pdf+=`${i+1} 0 obj\n`;if(i===3){pdf+=`<< /Type /XObject /Subtype /Image /Width ${canvas.width} /Height ${canvas.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${imageBytes.length} >>\nstream\n`;pdf+=binaryString(imageBytes);pdf+="\nendstream"}else pdf+=objects[i];pdf+="\nendobj\n"}
    const xref=pdf.length;pdf+=`xref\n0 ${objects.length+1}\n0000000000 65535 f \n`;for(const offset of offsets.slice(1))pdf+=`${String(offset).padStart(10,"0")} 00000 n \n`;pdf+=`trailer\n<< /Size ${objects.length+1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
    download(new Blob([Uint8Array.from(pdf,c=>c.charCodeAt(0)&255)],{type:"application/pdf"}),`${fileBase()}.pdf`);
  }

  function applyTheme(value){root.classList.toggle("theme-monochrome",value==="monochrome");localStorage.setItem("glyph.diagram.theme",value);document.querySelector("#diagram-theme")?.setAttribute("data-value",value)}
  function installTools(){
    const head=document.querySelector(".viewer-head");if(!head||byId("diagram-tools"))return;
    const tools=document.createElement("div");tools.id="diagram-tools";tools.className="diagram-tools";tools.innerHTML=`<select id="diagram-theme" title="表示テーマ"><option value="white">White</option><option value="monochrome">Monochrome</option></select><span class="separator"></span><button id="diagram-reset">Auto layout</button><button id="diagram-svg" class="export">SVG</button><button id="diagram-png" class="export">PNG</button><button id="diagram-pdf" class="export">PDF</button>`;head.appendChild(tools);
    const theme=localStorage.getItem("glyph.diagram.theme")||"white";byId("diagram-theme").value=theme;applyTheme(theme);byId("diagram-theme").onchange=event=>applyTheme(event.target.value);
    byId("diagram-reset").onclick=()=>{const stage=document.querySelector(".graph-stage");if(!stage)return;clearPositions(stage);if(typeof window.render==="function")window.render();else location.reload()};
    byId("diagram-svg").onclick=()=>{try{exportSvg()}catch(error){alert(error.message)}};byId("diagram-png").onclick=()=>exportPng().catch(error=>alert(error.message));byId("diagram-pdf").onclick=()=>exportPdf().catch(error=>alert(error.message));
  }
  document.addEventListener("keydown",event=>{if(!selected||!["ArrowLeft","ArrowRight","ArrowUp","ArrowDown"].includes(event.key))return;event.preventDefault();const step=event.shiftKey?1:8;const dx=event.key==="ArrowLeft"?-step:event.key==="ArrowRight"?step:0,dy=event.key==="ArrowUp"?-step:event.key==="ArrowDown"?step:0;selected.style.left=`${Math.max(0,num(selected.style.left)+dx)}px`;selected.style.top=`${Math.max(0,num(selected.style.top)+dy)}px`;const stage=selected.closest(".graph-stage");savePositions(stage);reroute(stage).catch(()=>{})});
  function enhance(){installTools();const stage=document.querySelector(".graph-stage");if(stage)makeEditable(stage)}
  new MutationObserver(()=>setTimeout(enhance,0)).observe(document.body,{childList:true,subtree:true});
  document.addEventListener("glyph-uml-transition-ready",enhance);document.addEventListener("glyph-initial-transition-ready",enhance);enhance();
})();
</script>
"""


def enhance_diagram_editor_exports_html(html: str) -> str:
    """Add editable node positions, white themes, and SVG/PNG/PDF exports."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
