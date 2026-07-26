from __future__ import annotations


_MARKER = "glyph-diagram-canvas-navigation-v1"

_STYLE = r"""
<style id="glyph-diagram-canvas-navigation-v1-style">
.canvas-shell.glyph-canvas-pan{
  --glyph-pan-gutter:220px;
  padding:var(--glyph-pan-gutter);
  overscroll-behavior:contain;
  touch-action:none;
  cursor:grab;
  scroll-behavior:auto;
}
.canvas-shell.glyph-canvas-pan.dragging-canvas{cursor:grabbing;user-select:none}
.canvas-shell.glyph-canvas-pan .graph-stage{flex:none}
.canvas-shell.glyph-canvas-pan .state-node,
.canvas-shell.glyph-canvas-pan .graph-node,
.canvas-shell.glyph-canvas-pan .edge-label,
.canvas-shell.glyph-canvas-pan .transition-label{cursor:pointer}
.canvas-pan-help{
  position:sticky;
  left:12px;
  bottom:12px;
  z-index:18;
  display:inline-flex;
  gap:7px;
  align-items:center;
  width:max-content;
  max-width:calc(100% - 24px);
  padding:6px 9px;
  border:1px solid var(--line);
  border-radius:999px;
  background:var(--panel);
  color:var(--muted);
  font-size:10px;
  pointer-events:none;
  box-shadow:0 4px 12px rgba(0,0,0,.18);
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-canvas-navigation-v1-script">
(()=>{
const GUTTER=220,INTERACTIVE=".state-node,.graph-node,.edge-label,.transition-label,button,select,input,textarea,a,[data-line]";
let drag=null;
function locale(){return localStorage.getItem("glyph.ui.locale")==="en"?"en":"ja"}
function key(shell){const tab=document.querySelector(".tab.active")?.dataset.tab||"state",index=tab==="state"?document.getElementById("machine-select")?.value||0:document.getElementById("system-select")?.value||0;return `glyph.diagram.canvas-pan.v1:${tab}:${index}`}
function saved(shell){try{return JSON.parse(sessionStorage.getItem(key(shell))||"null")}catch{return null}}
function persist(shell){sessionStorage.setItem(key(shell),JSON.stringify({left:shell.scrollLeft,top:shell.scrollTop}))}
function blankTarget(event,shell){const target=event.target;if(target.closest?.(INTERACTIVE))return false;return Boolean(target===shell||target.closest?.(".graph-stage,.edge-svg"))}
function help(shell){
  let element=shell.querySelector(":scope > .canvas-pan-help");
  if(!element){element=document.createElement("div");element.className="canvas-pan-help";shell.appendChild(element)}
  const value=locale()==="ja"?"空白をドラッグしてキャンバスを移動":"Drag empty canvas to pan";
  if(element.textContent!==value)element.textContent=value;
}
function bind(shell){
  if(shell.dataset.canvasPanReady==="true"){help(shell);return}
  shell.dataset.canvasPanReady="true";shell.classList.add("glyph-canvas-pan");help(shell);
  requestAnimationFrame(()=>{const position=saved(shell);shell.scrollLeft=position?.left??GUTTER;shell.scrollTop=position?.top??GUTTER});
  shell.addEventListener("pointerdown",event=>{
    if((event.button!==0&&event.button!==1)||!blankTarget(event,shell))return;
    event.preventDefault();shell.classList.add("dragging-canvas");shell.setPointerCapture(event.pointerId);
    drag={shell,pointerId:event.pointerId,startX:event.clientX,startY:event.clientY,left:shell.scrollLeft,top:shell.scrollTop};
  });
  shell.addEventListener("pointermove",event=>{if(!drag||drag.shell!==shell||drag.pointerId!==event.pointerId)return;event.preventDefault();shell.scrollLeft=drag.left-(event.clientX-drag.startX);shell.scrollTop=drag.top-(event.clientY-drag.startY)});
  const finish=event=>{if(!drag||drag.shell!==shell||drag.pointerId!==event.pointerId)return;shell.classList.remove("dragging-canvas");persist(shell);drag=null};
  shell.addEventListener("pointerup",finish);shell.addEventListener("pointercancel",finish);
  shell.addEventListener("scroll",()=>{clearTimeout(shell._glyphPanTimer);shell._glyphPanTimer=setTimeout(()=>persist(shell),120)},{passive:true});
}
function enhance(){document.querySelectorAll(".canvas-shell").forEach(bind)}
for(const name of["glyph-transition-layout-ready","glyph-transition-input-action-labels-ready","glyph-state-transition-ir-v2-labels-ready","glyph-uml-transition-ready","glyph-locale-change"])document.addEventListener(name,enhance);
document.addEventListener("change",event=>{if(event.target?.matches?.("#machine-select,#system-select"))setTimeout(enhance,0)});
new MutationObserver(enhance).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
enhance();
})();
</script>
"""


def enhance_diagram_canvas_navigation_html(html: str) -> str:
    """Allow blank-canvas drag panning with reachable space around the diagram."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
