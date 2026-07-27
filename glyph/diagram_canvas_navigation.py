from __future__ import annotations


_MARKER = "glyph-diagram-canvas-navigation-v1"

_STYLE = r"""
<style id="glyph-diagram-canvas-navigation-v1-style">
.canvas-shell.glyph-pan-ready{
  --glyph-pan-gutter:220px;
  padding:var(--glyph-pan-gutter);
  overscroll-behavior:contain;
  touch-action:none;
  cursor:grab;
  scroll-behavior:auto;
}
.canvas-shell.glyph-pan-ready.glyph-panning{cursor:grabbing;user-select:none}
.canvas-shell.glyph-pan-ready .graph-stage{min-width:100%;min-height:100%;flex:none}
.canvas-shell.glyph-pan-ready:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-canvas-navigation-v1-script">
(()=>{
const GUTTER=220,INTERACTIVE=".state-node,.graph-node,.edge-label,.transition-label,button,select,input,textarea,a,.transition-detail,[data-line]";
let pan=null;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
function identity(){const tab=document.querySelector(".tab.active")?.dataset.tab||"state",index=tab==="state"?document.getElementById("machine-select")?.value||0:document.getElementById("system-select")?.value||0;return `${tab}:${index}`}
function key(){return `glyph.diagram.canvas-pan.v1:${identity()}`}
function maxScroll(element,axis){return axis==="x"?Math.max(0,element.scrollWidth-element.clientWidth):Math.max(0,element.scrollHeight-element.clientHeight)}
function saved(){try{return JSON.parse(sessionStorage.getItem(key())||"null")}catch{return null}}
function persist(shell){sessionStorage.setItem(key(),JSON.stringify({left:shell.scrollLeft,top:shell.scrollTop}))}
function blankTarget(event,shell){const target=event.target;if(target?.closest?.(INTERACTIVE))return false;return Boolean(target===shell||target?.closest?.(".graph-stage,.edge-svg,.glyph-zoom-surface"))}
function removeHelp(shell){shell.querySelector(":scope > .canvas-pan-help")?.remove();shell.removeAttribute("title")}
function bind(shell){
  removeHelp(shell);
  if(shell.dataset.canvasPanReady==="true")return;
  shell.dataset.canvasPanReady="true";shell.classList.add("glyph-pan-ready");shell.tabIndex=0;
  requestAnimationFrame(()=>{const position=saved();shell.scrollLeft=position?.left??GUTTER;shell.scrollTop=position?.top??GUTTER});
  shell.addEventListener("pointerdown",event=>{
    if((event.button!==0&&event.button!==1)||!blankTarget(event,shell))return;
    event.preventDefault();shell.focus({preventScroll:true});shell.setPointerCapture(event.pointerId);shell.classList.add("glyph-panning");
    const parent=shell.closest(".view-body");pan={shell,parent,pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,left:shell.scrollLeft,top:shell.scrollTop,parentTop:parent?.scrollTop||0};
  });
  shell.addEventListener("pointermove",event=>{
    if(!pan||pan.shell!==shell||pan.pointerId!==event.pointerId)return;
    event.preventDefault();
    const desiredX=pan.left-(event.clientX-pan.startX),desiredY=pan.top-(event.clientY-pan.startY);
    const nextX=clamp(desiredX,0,maxScroll(shell,"x")),nextY=clamp(desiredY,0,maxScroll(shell,"y"));
    shell.scrollLeft=nextX;shell.scrollTop=nextY;
    const residualY=desiredY-nextY;
    if(pan.parent&&Math.abs(residualY)>.5)pan.parent.scrollTop=clamp(pan.parentTop+residualY,0,maxScroll(pan.parent,"y"));
  });
  const finish=event=>{if(!pan||pan.shell!==shell||(event.pointerId!==undefined&&pan.pointerId!==event.pointerId))return;shell.classList.remove("glyph-panning");persist(shell);pan=null};
  shell.addEventListener("pointerup",finish);shell.addEventListener("pointercancel",finish);shell.addEventListener("lostpointercapture",finish);
  shell.addEventListener("scroll",()=>{clearTimeout(shell._glyphPanTimer);shell._glyphPanTimer=setTimeout(()=>persist(shell),120)},{passive:true});
  shell.addEventListener("wheel",event=>{
    if(event.ctrlKey||event.metaKey)return;
    const parent=shell.closest(".view-body");if(!parent)return;
    const maxY=maxScroll(shell,"y"),atTop=shell.scrollTop<=0,atBottom=shell.scrollTop>=maxY-1;
    if(!(maxY<=1||(event.deltaY<0&&atTop)||(event.deltaY>0&&atBottom)))return;
    const before=parent.scrollTop;parent.scrollTop=clamp(before+event.deltaY,0,maxScroll(parent,"y"));if(parent.scrollTop!==before)event.preventDefault();
  },{passive:false});
}
function enhance(){document.querySelectorAll(".canvas-shell").forEach(bind)}
for(const event of["glyph-transition-layout-ready","glyph-transition-input-action-labels-ready","glyph-state-transition-ir-v2-labels-ready","glyph-state-transition-ir-v3-labels-ready","glyph-uml-transition-ready","glyph-locale-change","glyph-locale-changed"])document.addEventListener(event,enhance);
document.addEventListener("change",event=>{if(event.target?.matches?.("#machine-select,#system-select"))setTimeout(enhance,0)});
new MutationObserver(enhance).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});enhance();
})();
</script>
"""


def enhance_diagram_canvas_navigation_html(html: str) -> str:
    """Pan empty canvas space and hand residual vertical motion to the preview pane."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
