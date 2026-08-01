from __future__ import annotations


_MARKER = "glyph-transition-label-inspector-v1"

_STYLE = r"""
<style id="glyph-transition-label-inspector-v1-style">
.transition-io-cluster{
  cursor:grab!important;
}
.transition-io-cluster.dragging-io{
  cursor:grabbing!important;
}
.transition-label-inspector{
  position:fixed;
  z-index:10020;
  width:min(680px,calc(100vw - 24px));
  max-height:calc(100vh - 24px);
  overflow:auto;
  padding:0;
  border:1px solid var(--line);
  border-radius:12px;
  background:var(--panel);
  color:var(--text);
  box-shadow:0 18px 56px rgba(0,0,0,.42);
}
.transition-label-inspector[hidden]{display:none!important}
.transition-label-inspector-head{
  position:sticky;
  top:0;
  z-index:2;
  display:flex;
  align-items:center;
  gap:10px;
  padding:9px 11px;
  border-bottom:1px solid var(--line);
  background:var(--panel);
}
.transition-label-inspector-title{font-weight:760}
.transition-label-inspector-id{
  color:var(--blue);
  font:700 10px/1.35 ui-monospace,SFMono-Regular,Menlo,monospace;
}
.transition-label-inspector-close{
  margin-left:auto;
  padding:4px 8px;
}
.transition-label-inspector-body{padding:12px}
.transition-label-inspector-full{
  padding:10px 11px;
  border:1px solid var(--line);
  border-radius:9px;
  background:var(--panel2);
  white-space:pre-wrap;
  overflow-wrap:anywhere;
  word-break:normal;
  font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;
}
.transition-label-inspector-grid{
  display:grid;
  grid-template-columns:92px minmax(0,1fr);
  gap:7px 10px;
  margin-top:11px;
}
.transition-label-inspector-key{color:var(--muted);font-size:11px}
.transition-label-inspector-value{
  min-width:0;
  white-space:pre-wrap;
  overflow-wrap:anywhere;
  font:11px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;
}
.transition-label-inspector-status[data-status="exact"]{color:#45d19a}
.transition-label-inspector-status[data-status="may"]{color:#e7bf62}
.transition-label-inspector-status[data-status="unknown"]{color:var(--muted)}
.transition-label-inspector-hint{
  margin-top:11px;
  color:var(--faint);
  font-size:10px;
}
.theme-monochrome .transition-label-inspector{
  background:#fff!important;
  color:#111!important;
  border-color:#111!important;
  box-shadow:none!important;
}
.theme-monochrome .transition-label-inspector-head,
.theme-monochrome .transition-label-inspector-full{
  background:#fff!important;
  border-color:#111!important;
}
@media(max-width:720px){
  .transition-label-inspector-grid{grid-template-columns:1fr}
  .transition-label-inspector-key{margin-top:5px}
}
</style>
"""

_SCRIPT = r"""
<script id="glyph-transition-label-inspector-v1-script">
(()=>{
const MARKER="glyph-transition-label-inspector-v1";
let inspector=null,currentCluster=null;
const text=value=>String(value??"");
const esc=value=>text(value).replace(/[&<>"']/g,char=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
const locale=()=>window.GlyphI18n?.locale||document.documentElement.lang||"ja";
const isJapanese=()=>!locale().startsWith("en");
function ensureInspector(){
  if(inspector?.isConnected)return inspector;
  inspector=document.createElement("section");
  inspector.className="transition-label-inspector";
  inspector.hidden=true;
  inspector.setAttribute("role","dialog");
  inspector.setAttribute("aria-modal","false");
  inspector.innerHTML='<div class="transition-label-inspector-head"><span class="transition-label-inspector-title"></span><span class="transition-label-inspector-id"></span><button type="button" class="transition-label-inspector-close" aria-label="close">×</button></div><div class="transition-label-inspector-body"></div>';
  inspector.querySelector(".transition-label-inspector-close")?.addEventListener("click",close);
  document.body.append(inspector);
  return inspector;
}
function semanticLabel(status){
  if(!isJapanese())return status==="exact"?"Exact":status==="may"?"May":"Unknown";
  return status==="exact"?"Exact（厳密確定）":status==="may"?"May（可能性あり）":"Unknown（解析未確定）";
}
function row(key,value,className=""){
  if(!text(value).trim())return"";
  return`<div class="transition-label-inspector-key">${esc(key)}</div><div class="transition-label-inspector-value ${className}">${esc(value)}</div>`;
}
function position(panel,cluster){
  const rect=cluster.getBoundingClientRect(),margin=12,gap=9;
  const width=Math.min(panel.offsetWidth,window.innerWidth-margin*2);
  let left=rect.left+rect.width/2-width/2;
  left=Math.max(margin,Math.min(window.innerWidth-width-margin,left));
  let top=rect.bottom+gap;
  if(top+panel.offsetHeight>window.innerHeight-margin)top=Math.max(margin,rect.top-panel.offsetHeight-gap);
  panel.style.left=`${Math.round(left)}px`;
  panel.style.top=`${Math.round(top)}px`;
}
function open(cluster){
  const panel=ensureInspector(),status=cluster.dataset.rtaiSemanticStatus||"unknown";
  const full=text(cluster.dataset.ioValue||cluster.querySelector(".transition-io-value")?.textContent||cluster.textContent).trim();
  const reason=text(cluster.dataset.rtaiSemanticReason||"").trim();
  panel.querySelector(".transition-label-inspector-title").textContent=isJapanese()?"遷移ラベル全文":"Full transition label";
  panel.querySelector(".transition-label-inspector-id").textContent=cluster.dataset.transitionId||"";
  panel.querySelector(".transition-label-inspector-close").setAttribute("aria-label",isJapanese()?"閉じる":"Close");
  panel.querySelector(".transition-label-inspector-body").innerHTML=`
    <div class="transition-label-inspector-full">${esc(full)}</div>
    <div class="transition-label-inspector-grid">
      ${row(isJapanese()?"Input":"Input",cluster.dataset.inputValue)}
      ${row(isJapanese()?"Guard":"Guard",cluster.dataset.guardValue)}
      ${row(isJapanese()?"Action":"Action",cluster.dataset.actionValue||cluster.dataset.outputValue)}
      ${row(isJapanese()?"解析状態":"Analysis",semanticLabel(status),`transition-label-inspector-status`)}
      ${row(isJapanese()?"理由":"Reason",reason)}
    </div>
    <div class="transition-label-inspector-hint">${isJapanese()?"ドラッグでラベルを移動できる。Alt + ダブルクリックで配置を自動位置へ戻す。":"Drag the label to move it. Alt + double-click resets its placement."}</div>`;
  const statusElement=panel.querySelector(".transition-label-inspector-status");
  if(statusElement)statusElement.dataset.status=status;
  currentCluster=cluster;
  panel.hidden=false;
  panel.dataset.transitionId=cluster.dataset.transitionId||"";
  panel.dataset.fullText=full;
  requestAnimationFrame(()=>position(panel,cluster));
  document.dispatchEvent(new CustomEvent("glyph-transition-label-inspector-opened",{detail:{marker:MARKER,transitionId:cluster.dataset.transitionId||"",fullText:full}}));
}
function close(){
  if(!inspector)return;
  inspector.hidden=true;
  currentCluster=null;
}
document.addEventListener("dblclick",event=>{
  const cluster=event.target?.closest?.(".transition-io-cluster");
  if(!cluster||event.altKey)return;
  event.preventDefault();
  event.stopImmediatePropagation();
  open(cluster);
},true);
document.addEventListener("pointerdown",event=>{
  if(!inspector||inspector.hidden)return;
  if(inspector.contains(event.target)||event.target?.closest?.(".transition-io-cluster")===currentCluster)return;
  close();
},true);
document.addEventListener("keydown",event=>{if(event.key==="Escape")close()});
window.addEventListener("resize",()=>{if(inspector&&!inspector.hidden&&currentCluster?.isConnected)position(inspector,currentCluster)});
window.glyphTransitionLabelInspector={marker:MARKER,version:1,open,close,current:()=>currentCluster};
})();
</script>
"""


def enhance_transition_label_inspector_html(html: str) -> str:
    """Keep transition labels draggable and show their complete text on double click."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )


__all__ = ["enhance_transition_label_inspector_html"]
