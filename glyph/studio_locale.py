from __future__ import annotations


_MARKER = "glyph-studio-locale-v1"

_STYLE = r"""
<style id="glyph-studio-locale-v1-style">
.glyph-settings-wrap{position:relative}
.glyph-settings-panel{position:absolute;right:0;top:calc(100% + 8px);z-index:120;display:none;min-width:240px;padding:13px;border:1px solid var(--line);border-radius:11px;background:var(--surface);box-shadow:var(--shadow)}
.glyph-settings-panel.open{display:block}
.glyph-settings-title{font-weight:720;margin-bottom:10px}
.glyph-settings-row{display:grid;grid-template-columns:78px minmax(0,1fr);align-items:center;gap:10px;color:var(--muted);font-size:12px}
.glyph-settings-row select{width:100%;border:1px solid var(--line);border-radius:8px;background:var(--surface-2);color:var(--text);padding:7px 9px}
</style>
"""

_SCRIPT = r"""
// glyph-studio-locale-v1-script
(()=>{
const KEY="glyph.ui.locale",DEFAULT_LOCALE="ja";
let locale=localStorage.getItem(KEY)||DEFAULT_LOCALE,scheduled=false;
const set=(element,value)=>{if(element&&element.textContent!==value)element.textContent=value};
const pair=(ja,en)=>locale==="ja"?ja:en;
function currentState(){try{return typeof state!=="undefined"?state:null}catch{return null}}
function diagnosticText(item){return locale==="ja"?(item?.message_ja||item?.message):(item?.message_en||item?.message)}
function ensureSettings(){
  const actions=document.querySelector(".header-actions");if(!actions||document.getElementById("glyph-settings-button"))return;
  const wrap=document.createElement("div");wrap.className="glyph-settings-wrap";
  wrap.innerHTML=`<button id="glyph-settings-button" class="icon-button quiet" type="button" aria-haspopup="true" aria-expanded="false">⚙</button><div id="glyph-settings-panel" class="glyph-settings-panel"><div class="glyph-settings-title"></div><label class="glyph-settings-row"><span></span><select id="glyph-language-select"><option value="ja">日本語</option><option value="en">English</option></select></label></div>`;
  actions.insertBefore(wrap,actions.firstChild);
  const button=wrap.querySelector("#glyph-settings-button"),panel=wrap.querySelector("#glyph-settings-panel"),select=wrap.querySelector("#glyph-language-select");
  select.value=locale;
  button.addEventListener("click",event=>{event.stopPropagation();const open=!panel.classList.contains("open");panel.classList.toggle("open",open);button.setAttribute("aria-expanded",String(open))});
  select.addEventListener("change",()=>{locale=select.value==="en"?"en":"ja";localStorage.setItem(KEY,locale);apply();document.dispatchEvent(new CustomEvent("glyph-locale-change",{detail:{locale}}))});
  document.addEventListener("click",event=>{if(!wrap.contains(event.target)){panel.classList.remove("open");button.setAttribute("aria-expanded","false")}});
}
function ensureAutoPreviewLabel(){
  const label=document.querySelector(".auto-preview"),input=document.getElementById("auto-preview");if(!label||!input)return null;
  let text=label.querySelector(".glyph-auto-preview-label");
  if(!text){
    [...label.childNodes].filter(node=>node.nodeType===Node.TEXT_NODE).forEach(node=>node.remove());
    text=document.createElement("span");text.className="glyph-auto-preview-label";label.appendChild(text);
  }
  return text;
}
function structuredMessage(element,value){
  if(!element||!value)return;
  let target=element.querySelector(":scope > .glyph-localized-diagnostic-message");
  if(!target){
    const br=element.querySelector(":scope > br");
    if(br){while(br.nextSibling)br.nextSibling.remove();target=document.createElement("span");target.className="glyph-localized-diagnostic-message";br.after(target)}
    else{target=element}
  }
  set(target,value);
}
function applyDiagnostics(){
  const data=currentState(),items=data?.diagnostics||[];
  document.querySelectorAll("#diagnostic-strip .diagnostic-message").forEach((element,index)=>set(element,diagnosticText(items[index])||""));
  const algebra=data?.glyph04_views?.type_algebra?.diagnostics||[];
  document.querySelectorAll("#content .error").forEach((element,index)=>structuredMessage(element,diagnosticText(algebra[index]||items[index])));
}
function applyStatic(){
  document.documentElement.lang=locale==="ja"?"ja":"en";
  set(document.querySelector(".version"),pair("セマンティック設計ワークスペース","Semantic design workspace"));
  set(document.querySelector(".pane-title"),pair("ソース","Source"));
  set(ensureAutoPreviewLabel(),pair("自動プレビュー","Auto preview"));
  set(document.querySelector("#reload .action-label"),pair("再読込","Reload"));
  set(document.querySelector("#preview .action-label"),pair("プレビュー","Preview"));
  set(document.getElementById("save"),pair("保存","Save"));
  const sync=document.getElementById("sync-state");if(sync)set(sync,(typeof dirty!=="undefined"&&dirty)?pair("未保存","Unsaved"):pair("保存済み","Saved"));
  const status=document.querySelector("#status span"),raw=String(currentState()?.status||"").toLowerCase();
  if(status){
    if(typeof busy!=="undefined"&&busy){const shown=status.textContent.toLowerCase(),busyLabels={working:["処理中","Working"],saving:["保存中","Saving"],previewing:["プレビュー中","Previewing"],reloading:["再読込中","Reloading"]},entry=busyLabels[shown]||busyLabels.working;set(status,locale==="ja"?entry[0]:entry[1])}
    else if(raw)set(status,({starting:pair("起動中","starting"),ready:pair("準備完了","ready"),error:pair("エラー","error"),busy:pair("処理中","busy")})[raw]||raw);
  }
  const meta=document.getElementById("editor-meta"),source=document.getElementById("editor")?.value||"",lineCount=source.split("\n").length;if(meta)set(meta,locale==="ja"?`${lineCount} 行 · ${source.length} 文字`:`${lineCount} lines · ${source.length} chars`);
  const button=document.getElementById("glyph-settings-button");if(button){button.title=pair("表示設定","Display settings");button.setAttribute("aria-label",button.title)}
  set(document.querySelector(".glyph-settings-title"),pair("表示設定","Display settings"));
  set(document.querySelector(".glyph-settings-row > span"),pair("言語","Language"));
  const search=document.getElementById("view-search");if(search){search.placeholder=pair("このビューを絞り込む","Filter this view");search.setAttribute("aria-label",search.placeholder)}
}
function apply(){ensureSettings();applyStatic();applyDiagnostics()}
function schedule(){if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;apply()})}
new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true,characterData:true});
document.addEventListener("DOMContentLoaded",apply,{once:true});apply();
})();
"""


def enhance_studio_locale_html(html: str) -> str:
    """Add Japanese-default UI localization and an English language selector."""

    if _MARKER in html:
        return html
    styled = html.replace("</head>", _STYLE + "\n</head>", 1)
    if "</script>" not in styled:
        raise ValueError("Studio HTML has no script closing tag")
    script, tail = styled.rsplit("</script>", 1)
    return script + "\n" + _SCRIPT + "\n</script>" + tail
