from __future__ import annotations


_MARKER = "glyph-diagram-middle-drag-zoom-v1"

_STYLE = r"""
<style id="glyph-diagram-middle-drag-zoom-v1-style">
.canvas-shell.glyph-middle-zoom-ready.glyph-middle-zooming{
  cursor:ns-resize!important;
  user-select:none!important;
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-middle-drag-zoom-v1-script">
(()=>{
const MARKER="glyph-diagram-middle-drag-zoom-v1",DRAG_TO_WHEEL=2,MAX_DELTA_PER_FRAME=80;
let active=null,destroyed=false;
const clamp=(value,min,max)=>Math.max(min,Math.min(max,value));
function dispatchZoom(record,deltaY){
  if(!record?.shell?.isConnected||!deltaY)return;
  record.shell.dispatchEvent(new WheelEvent("wheel",{
    bubbles:true,
    cancelable:true,
    deltaMode:0,
    deltaY:clamp(deltaY*DRAG_TO_WHEEL,-MAX_DELTA_PER_FRAME,MAX_DELTA_PER_FRAME),
    ctrlKey:true,
    clientX:record.anchorX,
    clientY:record.anchorY,
  }));
}
function flush(record){
  if(!record)return;
  if(record.frame){cancelAnimationFrame(record.frame);record.frame=0}
  const delta=record.pendingDelta;record.pendingDelta=0;
  dispatchZoom(record,delta);
}
function queue(record){
  if(record.frame)return;
  record.frame=requestAnimationFrame(()=>{
    record.frame=0;
    if(active!==record||destroyed)return;
    const delta=record.pendingDelta;record.pendingDelta=0;
    dispatchZoom(record,delta);
  });
}
function start(shell,event){
  if(destroyed||event.button!==1||!shell.querySelector(".graph-stage"))return;
  if(!window.glyphDiagramViewport?.setScale)return;
  event.preventDefault();event.stopPropagation();
  const record={
    shell,
    pointerId:event.pointerId,
    lastY:event.clientY,
    anchorX:event.clientX,
    anchorY:event.clientY,
    pendingDelta:0,
    frame:0,
  };
  active=record;
  shell.classList.add("glyph-middle-zooming");
  shell.dataset.middleDragZoomState="dragging";
  shell.setPointerCapture?.(event.pointerId);
}
function move(shell,event){
  const record=active;
  if(!record||record.shell!==shell||record.pointerId!==event.pointerId)return;
  event.preventDefault();event.stopPropagation();
  const delta=event.clientY-record.lastY;record.lastY=event.clientY;
  if(!Number.isFinite(delta)||Math.abs(delta)<.01)return;
  record.pendingDelta+=delta;queue(record);
}
function finish(shell,event){
  const record=active;
  if(!record||record.shell!==shell||(event.pointerId!==undefined&&record.pointerId!==event.pointerId))return;
  event.preventDefault();event.stopPropagation();
  flush(record);
  active=null;
  shell.releasePointerCapture?.(record.pointerId);
  shell.classList.remove("glyph-middle-zooming");
  shell.dataset.middleDragZoomState="idle";
}
function bind(shell){
  if(shell.dataset.middleDragZoomReady==="true")return;
  shell.dataset.middleDragZoomReady="true";
  shell.classList.add("glyph-middle-zoom-ready");
  shell.addEventListener("pointerdown",event=>start(shell,event),true);
  shell.addEventListener("pointermove",event=>move(shell,event),true);
  shell.addEventListener("pointerup",event=>finish(shell,event),true);
  shell.addEventListener("pointercancel",event=>finish(shell,event),true);
  shell.addEventListener("lostpointercapture",event=>finish(shell,event),true);
  shell.addEventListener("auxclick",event=>{if(event.button===1){event.preventDefault();event.stopPropagation()}},true);
}
function enhance(){document.querySelectorAll(".canvas-shell").forEach(bind)}
for(const eventName of["glyph-transition-layout-transaction-ready","glyph-locale-change","glyph-locale-changed"]){document.addEventListener(eventName,enhance)}
document.addEventListener("change",event=>{if(event.target?.matches?.("#machine-select,#system-select"))setTimeout(enhance,0)});
new MutationObserver(enhance).observe(document.getElementById("view")||document.body,{childList:true,subtree:true});
for(const eventName of["pagehide","beforeunload"]){window.addEventListener(eventName,()=>{destroyed=true;if(active)flush(active);active=null},{once:true})}
window.glyphDiagramMiddleDragZoom={marker:MARKER,version:1,active:()=>Boolean(active)};
enhance();
})();
</script>
"""


def enhance_diagram_middle_drag_zoom_html(html: str) -> str:
    """Zoom a diagram around the press point while middle-button dragging."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )


__all__ = ["enhance_diagram_middle_drag_zoom_html"]
