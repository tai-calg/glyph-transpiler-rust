from __future__ import annotations


_MARKER = "glyph-transition-readable-exports-v1"

_SCRIPT = r"""
<script id="glyph-transition-readable-exports-v1-script">
(()=>{
const MARKER="glyph-transition-readable-exports-v1";
const root=document.documentElement;
const $=selector=>document.querySelector(selector);
const esc=value=>String(value??"").replace(/[&<>\"]/g,character=>({"&":"&amp;","<":"&lt;",">":"&gt;",'\"':"&quot;"}[character]));
const text=(x,y,value,size=12,weight=400,anchor="start")=>`<text x="${x}" y="${y}" font-family="Arial,Helvetica,sans-serif" font-size="${size}" font-weight="${weight}" text-anchor="${anchor}" fill="#111">${esc(value)}</text>`;
const nodeName=node=>node.querySelector(".state-name,.node-name")?.textContent?.trim()||"node";

function renderedLines(element){
  const semantic=[...element?.querySelectorAll(":scope > .transition-semantic-line")||[]].map(line=>line.textContent||"").filter(Boolean);
  if(semantic.length)return semantic;
  const value=element?.textContent||"",node=element?.firstChild;
  if(!value||!node||node.nodeType!==Node.TEXT_NODE)return[value];
  const lines=[];
  let current="",currentTop=null;
  for(let index=0;index<value.length;index+=1){
    const range=document.createRange();
    range.setStart(node,index);range.setEnd(node,index+1);
    const rect=range.getBoundingClientRect();
    if(currentTop===null)currentTop=rect.top;
    if(Math.abs(rect.top-currentTop)>1){lines.push(current);current="";currentTop=rect.top}
    current+=value[index];
  }
  if(current)lines.push(current);
  return lines.map(line=>line.trim()).filter(Boolean);
}

function multilineText(x,y,width,height,lines,size=9,weight=700){
  const safe=lines.length?lines:[""];
  const lineHeight=size*1.28,startY=y+height/2-((safe.length-1)*lineHeight)/2+size*.34;
  const tspans=safe.map((line,index)=>`<tspan x="${x+width/2}" y="${startY+index*lineHeight}">${esc(line.trim())}</tspan>`).join("");
  return`<text font-family="Arial,Helvetica,sans-serif" font-size="${size}" font-weight="${weight}" text-anchor="middle" fill="#111">${tspans}</text>`;
}

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
    const x=node.offsetLeft,y=node.offsetTop,nodeWidth=node.offsetWidth,nodeHeight=node.offsetHeight,dash=node.classList.contains("unreachable")?' stroke-dasharray="7 5"':"";
    body+=`<rect x="${x}" y="${y}" width="${nodeWidth}" height="${nodeHeight}" rx="${nodeHeight/2}" fill="#fff" stroke="#111" stroke-width="2"${dash}/>${text(x+nodeWidth/2,y+nodeHeight/2+4,nodeName(node),14,700,"middle")}`;
  });
  stage.querySelectorAll(".graph-node").forEach(node=>{
    const x=node.offsetLeft,y=node.offsetTop,nodeWidth=node.offsetWidth,nodeHeight=node.offsetHeight;
    body+=`<rect x="${x}" y="${y}" width="${nodeWidth}" height="${nodeHeight}" rx="10" fill="#fff" stroke="#111"/>${text(x+12,y+24,nodeName(node),15,700)}`;
    [...node.querySelectorAll(".port-text")].forEach((port,index)=>body+=text(x+12,y+52+index*16,port.textContent,10));
  });
  const transitionLabels=[...stage.querySelectorAll(".transition-io-cluster")];
  if(transitionLabels.length){
    transitionLabels.forEach(cluster=>{
      const label=cluster.querySelector('.transition-io-node[data-io-kind="io"]'),valueElement=label?.querySelector(".transition-io-value");
      if(!label||!valueElement)return;
      const x=cluster.offsetLeft-cluster.offsetWidth/2+label.offsetLeft,y=cluster.offsetTop-cluster.offsetHeight/2+label.offsetTop;
      const labelWidth=label.offsetWidth,labelHeight=label.offsetHeight,value=valueElement.textContent||"",lines=renderedLines(valueElement);
      const provisional=cluster.classList.contains("provisional-trigger"),stroke=root.classList.contains("theme-monochrome")?"#111":provisional?"#9a6700":"#2563eb",dash=provisional?' stroke-dasharray="5 3"':"";
      body+=`<g class="transition-io-export-label" data-full-label="${esc(value)}"><title>${esc(value)}</title><rect x="${x}" y="${y}" width="${labelWidth}" height="${labelHeight}" rx="5" fill="#fff" stroke="${stroke}"${dash}/>${multilineText(x,y,labelWidth,labelHeight,lines)}</g>`;
    });
  }else{
    stage.querySelectorAll(".edge-label:not(.transition-label)").forEach(label=>{
      const x=label.offsetLeft-label.offsetWidth/2,y=label.offsetTop-label.offsetHeight/2,labelWidth=label.offsetWidth,labelHeight=label.offsetHeight;
      body+=`<rect x="${x}" y="${y}" width="${labelWidth}" height="${labelHeight}" rx="4" fill="#fff" stroke="#777"/>${text(x+labelWidth/2,y+labelHeight/2+4,label.textContent,10,500,"middle")}`;
    });
  }
  return`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="100%" height="100%" fill="#fff"/>${body}</svg>`;
}

function base(){return($("#machine-select")?.selectedOptions?.[0]?.textContent||$("#system-select")?.selectedOptions?.[0]?.textContent||"glyph-diagram").trim().replace(/[^A-Za-z0-9._-]+/g,"-")}
function download(blob,name){const url=URL.createObjectURL(blob),anchor=document.createElement("a");anchor.href=url;anchor.download=name;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),500)}
async function canvas(){
  const image=new Image(),url=URL.createObjectURL(new Blob([svg()],{type:"image/svg+xml"}));
  await new Promise((resolve,reject)=>{image.onload=resolve;image.onerror=reject;image.src=url});
  const canvasElement=document.createElement("canvas");canvasElement.width=image.naturalWidth*2;canvasElement.height=image.naturalHeight*2;
  const context=canvasElement.getContext("2d");context.scale(2,2);context.fillStyle="#fff";context.fillRect(0,0,image.naturalWidth,image.naturalHeight);context.drawImage(image,0,0);URL.revokeObjectURL(url);return canvasElement;
}
function binary(bytes){let result="";for(let index=0;index<bytes.length;index+=8192)result+=String.fromCharCode(...bytes.subarray(index,index+8192));return result}
async function pdf(){
  const canvasElement=await canvas(),jpg=Uint8Array.from(atob(canvasElement.toDataURL("image/jpeg",.94).split(",")[1]),character=>character.charCodeAt(0));
  const pageWidth=841.89,pageHeight=595.28,ratio=Math.min(785/canvasElement.width,539/canvasElement.height),width=canvasElement.width*ratio,height=canvasElement.height*ratio,x=(pageWidth-width)/2,y=(pageHeight-height)/2;
  const stream=`q\n${width} 0 0 ${height} ${x} ${y} cm\n/Im0 Do\nQ\n`;
  const objects=["<< /Type /Catalog /Pages 2 0 R >>","<< /Type /Pages /Kids [3 0 R] /Count 1 >>",`<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pageWidth} ${pageHeight}] /Resources << /XObject << /Im0 4 0 R >> >> /Contents 5 0 R >>`,null,`<< /Length ${stream.length} >>\nstream\n${stream}endstream`];
  let output="%PDF-1.4\n%\xE2\xE3\xCF\xD3\n",offsets=[0];
  objects.forEach((object,index)=>{offsets.push(output.length);output+=`${index+1} 0 obj\n`;if(index===3)output+=`<< /Type /XObject /Subtype /Image /Width ${canvasElement.width} /Height ${canvasElement.height} /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length ${jpg.length} >>\nstream\n${binary(jpg)}\nendstream`;else output+=object;output+="\nendobj\n"});
  const xref=output.length;output+="xref\n0 6\n0000000000 65535 f \n";offsets.slice(1).forEach(offset=>output+=`${String(offset).padStart(10,"0")} 00000 n \n`);output+=`trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
  download(new Blob([Uint8Array.from(output,character=>character.charCodeAt(0)&255)],{type:"application/pdf"}),`${base()}.pdf`);
}

function bind(){
  const svgButton=$("#diagram-svg"),pngButton=$("#diagram-png"),pdfButton=$("#diagram-pdf");
  if(svgButton&&svgButton.dataset.readableExport!=="true"){svgButton.dataset.readableExport="true";svgButton.onclick=()=>download(new Blob([svg()],{type:"image/svg+xml"}),`${base()}.svg`)}
  if(pngButton&&pngButton.dataset.readableExport!=="true"){pngButton.dataset.readableExport="true";pngButton.onclick=async()=>{const canvasElement=await canvas();canvasElement.toBlob(blob=>blob&&download(blob,`${base()}.png`),"image/png")}}
  if(pdfButton&&pdfButton.dataset.readableExport!=="true"){pdfButton.dataset.readableExport="true";pdfButton.onclick=()=>pdf().catch(error=>alert(error.message))}
}

new MutationObserver(()=>bind()).observe(document.body,{childList:true,subtree:true});
document.addEventListener("glyph-transition-io-clusters-ready",bind);bind();
window.glyphReadableDiagramExports={marker:MARKER,svg,canvas,pdf,bind};
window.svg=svg;
})();
</script>
"""


def enhance_transition_readable_exports_html(html: str) -> str:
    """Export the exact readable transition labels shown in the editor."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
