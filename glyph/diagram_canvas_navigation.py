from __future__ import annotations


_MARKER = "glyph-diagram-canvas-navigation-v1"

_STYLE = r"""
<style id="glyph-diagram-canvas-navigation-v1-style">
.canvas-shell.glyph-pan-ready{cursor:grab;touch-action:none}
.canvas-shell.glyph-pan-ready.glyph-panning{cursor:grabbing;user-select:none}
.canvas-shell.glyph-pan-ready .graph-stage{min-width:100%;min-height:100%}
.canvas-shell.glyph-pan-ready:focus-visible{outline:2px solid var(--blue);outline-offset:2px}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-canvas-navigation-v1-script">
(()=>{
const INTERACTIVE=".state-node,.graph-node,.edge-label,.transition-label,button,select,input,textarea,a,.transition-detail";
let pan=null;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
function maxScroll(element,axis){return axis==="x"?Math.max(0,element.scrollWidth-element.clientWidth):Math.max(0,element.scrollHeight-element.clientHeight)}
function bind(shell){
 if(shell.dataset.canvasPanReady==="true")return;
 shell.dataset.canvasPanReady="true";shell.classList.add("glyph-pan-ready");shell.tabIndex=0;
 shell.addEventListener("pointerdown",event=>{
   if(event.button!==0||event.target?.closest?.(INTERACTIVE))return;
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
   if(pan.parent&&Math.abs(residualY)>.5){pan.parent.scrollTop=clamp(pan.parentTop+residualY,0,maxScroll(pan.parent,"y"))}
 });
 const finish=event=>{if(!pan||pan.shell!==shell||(event.pointerId!==undefined&&pan.pointerId!==event.pointerId))return;shell.classList.remove("glyph-panning");pan=null};
 shell.addEventListener("pointerup",finish);shell.addEventListener("pointercancel",finish);shell.addEventListener("lostpointercapture",finish);
 shell.addEventListener("wheel",event=>{
   if(event.ctrlKey||event.metaKey)return;
   const parent=shell.closest(".view-body");if(!parent)return;
   const maxY=maxScroll(shell,"y"),atTop=shell.scrollTop<=0,atBottom=shell.scrollTop>=maxY-1;
   const cannotConsume=maxY<=1||(event.deltaY<0&&atTop)||(event.deltaY>0&&atBottom);
   if(!cannotConsume)return;
   const before=parent.scrollTop;parent.scrollTop=clamp(before+event.deltaY,0,maxScroll(parent,"y"));
   if(parent.scrollTop!==before)event.preventDefault();
 },{passive:false});
}
function enhance(){document.querySelectorAll(".canvas-shell").forEach(bind)}
new MutationObserver(enhance).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
for(const event of["glyph-transition-layout-ready","glyph-state-transition-ir-v3-labels-ready","glyph-uml-transition-ready"])document.addEventListener(event,enhance);
enhance();
})();
</script>
"""


def enhance_diagram_canvas_navigation_html(html: str) -> str:
    """Pan a canvas from empty space and hand residual motion to the preview pane."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
