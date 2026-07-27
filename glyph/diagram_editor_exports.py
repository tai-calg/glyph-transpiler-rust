from __future__ import annotations


_MARKER = "glyph-diagram-editor-exports-v1"

_STYLE = r"""
<style id="glyph-diagram-editor-exports-v1-style">
:root{color-scheme:light;--bg:#f4f6f8;--panel:#fff;--panel2:#f8fafc;--panel3:#eef2f6;--line:#d7dde5;--text:#18212f;--muted:#667085;--faint:#98a2b3;--blue:#2563eb;--green:#16865b;--purple:#7557b7;--red:#c73546;--amber:#9a6700;--shadow:0 12px 32px rgba(16,24,40,.10)}
body{background:var(--bg)!important;color:var(--text)!important}header,.toolbar,.viewer-head,.diagnostics,.editor-pane,.lines{background:#fff!important}.editor{background:#fbfcfe!important;color:#1f2937!important}
.canvas-shell{background:linear-gradient(rgba(15,23,42,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(15,23,42,.035) 1px,transparent 1px),#fff!important;background-size:24px 24px!important;box-shadow:var(--shadow)!important}
.graph-node,.state-node{background:#fff!important;border-color:#60758a!important;box-shadow:0 7px 18px rgba(16,24,40,.10)!important}.graph-node.effect{background:#fcfaff!important}.edge-label,.transition-label{background:#fff!important;color:#344054!important;border-color:#cfd7e2!important;box-shadow:0 2px 8px rgba(16,24,40,.08)}.transition-label.failure-transition{background:#fff7f8!important;color:#a42838!important}.initial-transition-path{stroke:#111827!important}.initial-dot{background:#111827!important}
.diagram-tools{display:flex;align-items:center;gap:6px;margin-left:8px;flex-wrap:wrap}.diagram-tools select,.diagram-tools button{height:34px;padding:6px 9px;background:#fff;color:#344054;border-color:#d0d5dd}.diagram-tools button:hover{background:#f2f4f7}.diagram-tools .export{font-weight:650}.diagram-tools .separator{width:1px;height:22px;background:#d0d5dd;margin:0 2px}
.graph-stage.editable .state-node,.graph-stage.editable .graph-node{cursor:grab;user-select:none;touch-action:none}.graph-stage.editable .dragging{cursor:grabbing;z-index:20;outline:2px solid rgba(37,99,235,.35);box-shadow:0 12px 28px rgba(37,99,235,.20)!important}.selected-node{outline:2px solid #2563eb!important;outline-offset:3px}
.theme-monochrome{--blue:#111;--green:#111;--purple:#111;--red:#111;--amber:#111;--text:#111;--muted:#333;--faint:#666;--line:#aaa}.theme-monochrome body,.theme-monochrome header,.theme-monochrome .toolbar,.theme-monochrome .viewer-head,.theme-monochrome .editor-pane,.theme-monochrome .lines,.theme-monochrome .canvas-shell{background:#fff!important;color:#111!important}.theme-monochrome .canvas-shell{background:#fff!important;box-shadow:none!important;border:1px solid #111!important}.theme-monochrome .state-node,.theme-monochrome .graph-node,.theme-monochrome .edge-label,.theme-monochrome .transition-label{background:#fff!important;border-color:#111!important;color:#111!important;box-shadow:none!important}.theme-monochrome .state-node.unreachable{opacity:1!important}.theme-monochrome .state-transition-path,.theme-monochrome .initial-transition-path,.theme-monochrome .edge-svg path{stroke:#111!important}.theme-monochrome .failure-transition{stroke-dasharray:7 5!important}
@media print{header,.editor-pane,.splitter,.viewer-head,.view-controls,.machine-meta,.analysis-panel,.legend,.type-section{display:none!important}body,.app,main,.viewer,.view-body{height:auto!important;overflow:visible!important;background:#fff!important}main{display:block!important}.view-body{padding:0!important}.canvas-shell{border:0!important;box-shadow:none!important;overflow:visible!important}}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-editor-exports-v1-script">
(()=>{
const root=document.documentElement;
const $=selector=>document.querySelector(selector);
const all=selector=>[...document.querySelectorAll(selector)];
const num=value=>Number.parseFloat(value||"0")||0;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
let selected=null,drag=null,cache=null;

const download=(blob,name)=>{
  const url=URL.createObjectURL(blob),anchor=document.createElement("a");
  anchor.href=url;anchor.download=name;anchor.click();
  setTimeout(()=>URL.revokeObjectURL(url),500);
};

async function state(){
  if(cache)return cache;
  const response=await fetch("/api/state",{cache:"no-store"});
  if(!response.ok)throw Error("diagram state unavailable");
  return cache=await response.json();
}

function nameOf(node){return node.querySelector(".state-name,.node-name")?.textContent?.trim()||"node"}
function viewportScale(stage){return window.glyphDiagramViewport?.scaleFor(stage)||Number.parseFloat(stage?.dataset.viewportScale||"1")||1}
function key(stage){
  const tab=$(".tab.active")?.dataset.tab||"state";
  const index=tab==="state"?$("#machine-select")?.value||0:$("#system-select")?.value||0;
  return `glyph.diagram.positions.v1:${cache?.digest||"source"}:${tab}:${index}`;
}
function save(stage){
  const value={};
  stage.querySelectorAll(".state-node,.graph-node").forEach(node=>{
    value[nameOf(node)]={x:num(node.style.left),y:num(node.style.top)};
  });
  localStorage.setItem(key(stage),JSON.stringify(value));
}
function restore(stage){
  let value;
  try{value=JSON.parse(localStorage.getItem(key(stage))||"null")}catch{}
  if(!value)return false;
  let changed=false;
  stage.querySelectorAll(".state-node,.graph-node").forEach(node=>{
    const position=value[nameOf(node)];
    if(position){node.style.left=`${position.x}px`;node.style.top=`${position.y}px`;changed=true}
  });
  return changed;
}

function stateCurve(source,target,same,index){
  const x1=source.offsetLeft+source.offsetWidth/2,y1=source.offsetTop+source.offsetHeight/2;
  const x2=target.offsetLeft+target.offsetWidth/2,y2=target.offsetTop+target.offsetHeight/2;
  if(same){
    const spread=58+index%3*14;
    return `M ${x1-27} ${y1-34} C ${x1-spread} ${y1-98}, ${x1+spread} ${y1-98}, ${x1+27} ${y1-34}`;
  }
  const dx=x2-x1,dy=y2-y1,length=Math.max(1,Math.hypot(dx,dy));
  const startX=x1+dx/length*source.offsetWidth/2,startY=y1+dy/length*source.offsetHeight/2;
  const endX=x2-dx/length*target.offsetWidth/2,endY=y2-dy/length*target.offsetHeight/2;
  const offset=(index%3-1)*22;
  return `M ${startX} ${startY} Q ${(startX+endX)/2-dy*.1+offset} ${(startY+endY)/2+dx*.1+offset} ${endX} ${endY}`;
}

async function reroute(stage){
  const data=await state(),svg=stage.querySelector(":scope > svg.edge-svg");
  if(!svg)return;
  if(stage.querySelector(".state-node")){
    const rows=data.views?.state?.machines||[];
    const name=$("#machine-select")?.selectedOptions?.[0]?.textContent;
    const machine=rows.find(item=>item.name===name)||rows[0];
    const nodes=new Map([...stage.querySelectorAll(".state-node")].map(node=>[nameOf(node),node]));
    const paths=[...svg.querySelectorAll("path.state-transition-path")];
    const labels=[...stage.querySelectorAll(".transition-label")];
    (machine?.transitions||[]).forEach((transition,index)=>{
      const source=nodes.get(transition.source_state),target=nodes.get(transition.target_state);
      if(!source||!target)return;
      paths[index]?.setAttribute("d",stateCurve(source,target,source===target,index));
      if(labels[index]){
        labels[index].style.left=`${(source.offsetLeft+target.offsetLeft+source.offsetWidth)/2+(index%3-1)*18}px`;
        labels[index].style.top=`${(source.offsetTop+target.offsetTop+source.offsetHeight)/2-(source===target?80:0)+(index%2)*12}px`;
      }
    });
    delete stage.dataset.initialTransitionRouting;
    document.dispatchEvent(new CustomEvent("glyph-transition-input-action-labels-ready"));
  }else{
    const rows=data.views?.io?.systems||[];
    const name=$("#system-select")?.selectedOptions?.[0]?.textContent;
    const system=rows.find(item=>item.name===name)||rows[0];
    const nodes=new Map([...stage.querySelectorAll(".graph-node")].map(node=>[nameOf(node),node]));
    const paths=[...svg.querySelectorAll(":scope > path")];
    const labels=[...stage.querySelectorAll(".edge-label")];
    (system?.edges||[]).forEach((edge,index)=>{
      const sourceName=(system.nodes||[]).find(node=>node.id===edge.source_id)?.name;
      const targetName=(system.nodes||[]).find(node=>node.id===edge.target_id)?.name;
      const source=nodes.get(sourceName),target=nodes.get(targetName);
      if(!source||!target)return;
      const x1=source.offsetLeft+source.offsetWidth,y1=source.offsetTop+source.offsetHeight/2;
      const x2=target.offsetLeft,y2=target.offsetTop+target.offsetHeight/2;
      const middle=Math.max(60,(x2-x1)*.48);
      paths[index]?.setAttribute("d",`M ${x1} ${y1} C ${x1+middle} ${y1}, ${x2-middle} ${y2}, ${x2} ${y2}`);
      if(labels[index]){
        labels[index].style.left=`${(source.offsetLeft+target.offsetLeft+source.offsetWidth)/2}px`;
        labels[index].style.top=`${(source.offsetTop+target.offsetTop+source.offsetHeight)/2}px`;
      }
    });
  }
}

function select(node){selected?.classList.remove("selected-node");selected=node;selected?.classList.add("selected-node")}
function ready(stage){return stage.querySelector(".state-node")?stage.dataset.umlTransitionReady==="true"&&stage.dataset.initialRouteReady==="true":true}
function edit(stage){
  if(stage.dataset.editorReady==="true"||!ready(stage))return;
  stage.dataset.editorReady="true";stage.classList.add("editable");
  const restored=restore(stage);if(restored)reroute(stage).catch(()=>{});
  stage.querySelectorAll(".state-node,.graph-node").forEach(node=>{
    node.onpointerdown=event=>{
      if(event.button)return;
      event.preventDefault();select(node);node.classList.add("dragging");node.setPointerCapture(event.pointerId);
      drag={node,stage,x:event.clientX,y:event.clientY,left:num(node.style.left),top:num(node.style.top)};
    };
    node.onpointermove=event=>{
      if(!drag||drag.node!==node)return;
      const grid=event.shiftKey?1:8,scale=viewportScale(stage);
      const left=drag.left+(event.clientX-drag.x)/scale,top=drag.top+(event.clientY-drag.y)/scale;
      node.style.left=`${Math.round(clamp(left,8,stage.scrollWidth-node.offsetWidth-8)/grid)*grid}px`;
      node.style.top=`${Math.round(clamp(top,8,stage.scrollHeight-node.offsetHeight-8)/grid)*grid}px`;
      reroute(stage).catch(()=>{});
    };
    node.onpointerup=()=>{
      if(!drag||drag.node!==node)return;
      node.classList.remove("dragging");save(stage);reroute(stage).catch(()=>{});drag=null;
    };
    node.onclick=event=>{event.stopPropagation();select(node)};
  });
  stage.onclick=()=>select(null);
}

const esc=value=>String(value??"").replace(/[&<>\"]/g,character=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[character]));
const text=(x,y,value,size=12,weight=400,anchor="start")=>`<text x="${x}" y="${y}" font-family="Arial,Helvetica,sans-serif" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}" fill="#111">${esc(value)}</text>`;

function svg(){
  const stage=$(".graph-stage");if(!stage)throw Error("表示中の図がない");
  const width=Math.ceil(stage.scrollWidth),height=Math.ceil(stage.scrollHeight);let body="";
  const edges=stage.querySelector(":scope > svg.edge-svg");
  if(edges){
    const clone=edges.cloneNode(true);
    clone.querySelectorAll("path").forEach(path=>{
      path.setAttribute("stroke",root.classList.contains("theme-monochrome")?"#111":path.classList.contains("failure-transition")?"#c73546":"#60758a");
      path.setAttribute("fill","none");
    });
    body+=clone.innerHTML;
  }
  const dot=stage.querySelector(".initial-dot");
  if(dot)body+=`<circle cx="${dot.offsetLeft+9}" cy="${dot.offsetTop+9}" r="9" fill="#111"/>`;
  stage.querySelectorAll(".state-node").forEach(node=>{
    const x=node.offsetLeft,y=node.offsetTop,width=node.offsetWidth,height=node.offsetHeight,dash=node.classList.contains("unreachable")?' stroke-dasharray="7 5"':"";
    body+=`<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="${height/2}" fill="#fff" stroke="#111" stroke-width="2"${dash}/>${text(x+width/2,y+height/2+4,nameOf(node),14,700,"middle")}`;
  });
  stage.querySelectorAll(".graph-node").forEach(node=>{
    const x=node.offsetLeft,y=node.offsetTop,width=node.offsetWidth,height=node.offsetHeight;
    body+=`<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="10" fill="#fff" stroke="#111"/>${text(x+12,y+24,nameOf(node),15,700)}`;
    [...node.querySelectorAll(".port-text")].forEach((port,index)=>body+=text(x+12,y+52+index*16,port.textContent,10));
  });
  const transitionLabels=[...stage.querySelectorAll(".transition-io-cluster")];
  if(transitionLabels.length){
    transitionLabels.forEach(cluster=>{
      const label=cluster.querySelector('.transition-io-node[data-io-kind="io"]');
      if(!label)return;
      const x=cluster.offsetLeft-cluster.offsetWidth/2+label.offsetLeft;
      const y=cluster.offsetTop-cluster.offsetHeight/2+label.offsetTop;
      const width=label.offsetWidth,height=label.offsetHeight;
      const provisional=cluster.classList.contains("provisional-trigger");
      const stroke=root.classList.contains("theme-monochrome")?"#111":provisional?"#9a6700":"#2563eb";
      const dash=provisional?' stroke-dasharray="5 3"':"";
      const value=label.querySelector(".transition-io-value")?.textContent||"";
      body+=`<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="5" fill="#fff" stroke="${stroke}"${dash}/>${text(x+width/2,y+height/2+3,value,7,700,"middle")}`;
    });
  }else{
    stage.querySelectorAll(".edge-label:not(.transition-label)").forEach(label=>{
      const x=label.offsetLeft-label.offsetWidth/2,y=label.offsetTop-label.offsetHeight/2,width=label.offsetWidth,height=label.offsetHeight;
      body+=`<rect x="${x}" y="${y}" width="${width}" height="${height}" rx="4" fill="#fff" stroke="#777"/>${text(x+width/2,y+height/2+4,label.textContent,10,500,"middle")}`;
    });
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="#fff"/>${body}</svg>`;
}

function base(){return($("#machine-select")?.selectedOptions?.[0]?.textContent||$("#system-select")?.selectedOptions?.[0]?.textContent||"glyph-diagram").trim().replace(/[^A-Za-z0-9._-]+/g,"-")}
async function canvas(){
  const image=new Image(),url=URL.createObjectURL(new Blob([svg()],{type:"image/svg+xml"}));
  await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;image.src=url});
  const canvas=document.createElement("canvas");canvas.width=image.naturalWidth*2;canvas.height=image.naturalHeight*2;
  const context=canvas.getContext("2d");context.scale(2,2);context.fillStyle="#fff";context.fillRect(0,0,image.naturalWidth,image.naturalHeight);context.drawImage(image,0,0);URL.revokeObjectURL(url);return canvas;
}
function binary(bytes){let result="";for(let index=0;index<bytes.length;index+=8192)result+=String.fromCharCode(...bytes.subarray(index,index+8192));return result}
async function pdf(){
  const canvasElement=await canvas(),jpg=Uint8Array.from(atob(canvasElement.toDataURL("image/jpeg",.94).split(",")[1]),character=>character.charCodeAt(0));
  const pageWidth=841.89,pageHeight=595.28,ratio=Math.min(785/canvasElement.width,539/canvasElement.height),width=canvasElement.width*ratio,height=canvasElement.height*ratio,x=(pageWidth-width)/2,y=(pageHeight-height)/2;
  const stream=`q\n${width} 0 0 ${height} ${x} ${y} cm\n/Im0 Do\nQ\n`;
  const objects=["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 >>",`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pageWidth} ${pageHeight}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`,null,`<< /Length ${stream.length} >>\nstream\n${stream}endstream`];
  let output="%PDF-1.4\n%\xE2\xE3\xCF\xD3\n",offsets=[0];
  objects.forEach((object,index)=>{
    offsets.push(output.length);output+=`${index+1} 0 obj\n`;
    if(index===3)output+=`<< /Type /XObject /Subtype /Image /Width ${canvasElement.width} /Height ${canvasElement.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpg.length} >>\nstream\n${binary(jpg)}\nendstream`;
    else output+=object;
    output+="\nendobj\n";
  });
  const xref=output.length;output+="xref\n0 6\n0000000000 65535 f \n";
  offsets.slice(1).forEach(offset=>output+=`${String(offset).padStart(10,"0")} 00000 n \n`);
  output+=`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  download(new Blob([Uint8Array.from(output,character=>character.charCodeAt(0)&255)],{type:"application/pdf"}),`${base()}.pdf`);
}

function tools(){
  const header=$(".viewer-head");if(!header||$("#diagram-tools"))return;
  const controls=document.createElement("div");controls.id="diagram-tools";controls.className="diagram-tools";
  controls.innerHTML='<select id="diagram-theme"><option value="white">White</option><option value="monochrome">Monochrome</option></select><span class="separator"></span><button id="diagram-reset">Auto layout</button><button id="diagram-svg" class="export">SVG</button><button id="diagram-png" class="export">PNG</button><button id="diagram-pdf" class="export">PDF</button>';
  header.appendChild(controls);
  const theme=localStorage.getItem("glyph.diagram.theme")||"white";
  $("#diagram-theme").value=theme;root.classList.toggle("theme-monochrome",theme==="monochrome");
  $("#diagram-theme").onchange=event=>{localStorage.setItem("glyph.diagram.theme",event.target.value);root.classList.toggle("theme-monochrome",event.target.value==="monochrome")};
  $("#diagram-reset").onclick=()=>{const stage=$(".graph-stage");if(stage)localStorage.removeItem(key(stage));location.reload()};
  $("#diagram-svg").onclick=()=>download(new Blob([svg()],{type:"image/svg+xml"}),`${base()}.svg`);
  $("#diagram-png").onclick=async()=>{const canvasElement=await canvas();canvasElement.toBlob(blob=>blob&&download(blob,`${base()}.png`),"image/png")};
  $("#diagram-pdf").onclick=()=>pdf().catch(error=>alert(error.message));
}

document.addEventListener("keydown",event=>{
  if(!selected||!event.key.startsWith("Arrow"))return;
  event.preventDefault();
  const step=event.shiftKey?1:8,dx=event.key==="ArrowLeft"?-step:event.key==="ArrowRight"?step:0,dy=event.key==="ArrowUp"?-step:event.key==="ArrowDown"?step:0;
  selected.style.left=`${Math.max(0,num(selected.style.left)+dx)}px`;selected.style.top=`${Math.max(0,num(selected.style.top)+dy)}px`;
  const stage=selected.closest(".graph-stage");save(stage);reroute(stage).catch(()=>{});
});

function enhance(){tools();const stage=$(".graph-stage");if(stage)edit(stage)}
new MutationObserver(()=>setTimeout(enhance,20)).observe(document.body,{childList:true,subtree:true});
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
