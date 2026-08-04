from __future__ import annotations

import re


_MARKER = "glyph-save-triggered-rendering-v2"


_STYLE = r"""
<style id="glyph-save-triggered-rendering-v2-style">
.glyph-save-state{display:flex;align-items:center;gap:6px;white-space:nowrap;font-size:11px;color:var(--muted)}
.glyph-save-state strong{font-weight:750;color:var(--text)}
.glyph-save-state[data-persistence="unsaved"] .glyph-persistence{color:var(--amber)}
.glyph-save-state[data-persistence="conflict"] .glyph-persistence{color:var(--red)}
.glyph-save-state[data-render="error"] .glyph-render{color:var(--red)}
.glyph-save-state[data-render="rendering"] .glyph-render{color:var(--amber)}
#save[disabled]{cursor:wait;opacity:.72}
.glyph-stale-banner{display:flex;align-items:center;gap:9px;padding:9px 14px;border-bottom:1px solid rgba(231,191,98,.38);background:rgba(231,191,98,.1);color:var(--amber);font-size:12px}
.glyph-stale-banner[hidden]{display:none}
.glyph-conflict-dialog{width:min(560px,calc(100vw - 32px));border:1px solid var(--line);border-radius:14px;padding:0;background:var(--panel);color:var(--text);box-shadow:0 24px 70px rgba(0,0,0,.42)}
.glyph-conflict-dialog::backdrop{background:rgba(3,7,18,.58);backdrop-filter:blur(3px)}
.glyph-conflict-head{padding:15px 17px;border-bottom:1px solid var(--line);font-size:17px;font-weight:760}
.glyph-conflict-body{display:grid;gap:12px;padding:16px 17px}
.glyph-conflict-body p{margin:0;color:var(--muted);line-height:1.65}
.glyph-conflict-actions{display:flex;justify-content:flex-end;gap:8px;flex-wrap:wrap}
.glyph-conflict-actions .danger{border-color:rgba(255,122,139,.55);color:var(--red)}
@media(max-width:760px){.glyph-save-state{display:none}}
</style>
"""


_SCRIPT = r"""
<script id="glyph-save-triggered-rendering-v2-script">
(()=>{
const MARKER="glyph-save-triggered-rendering-v2";
const REQUEST_TIMEOUT_MS=15000;
const POLL_INTERVAL_MS=3000;
const COPY={
 ja:{
  saved:"保存済み",unsaved:"未保存",conflict:"競合",
  ready:"描画済み",rendering:"保存・描画中",error:"コンパイルエラー",
  stale:"表示中の図は最後に正常コンパイルされた保存内容",
  noValid:"表示できる正常な図がまだない",
  conflictTitle:"外部変更を検出",
  conflictMessage:"編集中にファイルが外部で変更された。どちらを採用するか選択してください。",
  loadExternal:"外部版を読み込む",overwrite:"自分の版で上書き",cancel:"キャンセル",
  requestFailed:"保存要求に失敗した",saveTitle:"保存して描画 (Ctrl/Cmd+S)"
 },
 en:{
  saved:"Saved",unsaved:"Unsaved",conflict:"Conflict",
  ready:"Rendered",rendering:"Saving & rendering",error:"Compile error",
  stale:"The diagram shows the last successfully compiled saved source",
  noValid:"No valid diagram is available yet",
  conflictTitle:"External change detected",
  conflictMessage:"The file changed outside Glyph Studio while you were editing. Choose which version to keep.",
  loadExternal:"Load external version",overwrite:"Overwrite with mine",cancel:"Cancel",
  requestFailed:"Save request failed",saveTitle:"Save & Render (Ctrl/Cmd+S)"
 }
};
let editorBaseDigest="";
let initialized=false;
let saveInFlight=false;
let queuedSave=null;
let pollInFlight=false;
let conflict=null;
let conflictDialogShownFor="";
let pollTimer=null;

const language=()=>window.GlyphI18n?.locale==="en"||document.documentElement.lang==="en"?"en":"ja";
const t=key=>COPY[language()][key]||key;
const setText=(element,value)=>{if(element&&element.textContent!==value)element.textContent=value};

function ensureUi(){
 const header=document.querySelector("header");
 const saveButton=document.getElementById("save");
 if(header&&saveButton&&!document.getElementById("glyph-save-state")){
  const group=document.createElement("div");
  group.id="glyph-save-state";
  group.className="glyph-save-state";
  group.innerHTML='<strong class="glyph-persistence"></strong><span>·</span><span class="glyph-render"></span>';
  header.insertBefore(group,saveButton);
 }
 const viewer=document.querySelector(".viewer");
 if(viewer&&!document.getElementById("glyph-stale-banner")){
  const banner=document.createElement("div");
  banner.id="glyph-stale-banner";
  banner.className="glyph-stale-banner";
  banner.hidden=true;
  viewer.insertBefore(banner,viewer.firstChild);
 }
 if(!document.getElementById("glyph-conflict-dialog")){
  const dialog=document.createElement("dialog");
  dialog.id="glyph-conflict-dialog";
  dialog.className="glyph-conflict-dialog";
  dialog.innerHTML='<div class="glyph-conflict-head"></div><div class="glyph-conflict-body"><p></p><div class="glyph-conflict-actions"><button type="button" data-action="cancel"></button><button type="button" data-action="load"></button><button type="button" class="danger" data-action="overwrite"></button></div></div>';
  document.body.appendChild(dialog);
  dialog.querySelector('[data-action="cancel"]').onclick=()=>closeConflictDialog();
  dialog.querySelector('[data-action="load"]').onclick=()=>loadExternalVersion();
  dialog.querySelector('[data-action="overwrite"]').onclick=()=>overwriteExternalVersion();
 }
}

function isStale(next=snapshot){
 if(!next)return false;
 return String(next.digest||"")!==String(next.rendered_digest||"");
}

function updateUi(){
 ensureUi();
 const group=document.getElementById("glyph-save-state");
 const persistence=conflict?"conflict":dirty?"unsaved":"saved";
 const renderState=saveInFlight?"rendering":snapshot?.status==="error"?"error":"ready";
 if(group){
  group.dataset.persistence=persistence;
  group.dataset.render=renderState;
  setText(group.querySelector(".glyph-persistence"),t(persistence));
  setText(group.querySelector(".glyph-render"),t(renderState));
 }
 const button=document.getElementById("save");
 if(button){
  button.disabled=saveInFlight;
  button.title=t("saveTitle");
  button.setAttribute("aria-busy",saveInFlight?"true":"false");
 }
 const banner=document.getElementById("glyph-stale-banner");
 if(banner){
  const stale=isStale();
  banner.hidden=!stale;
  if(stale){
   const hasValid=Number(snapshot?.last_successful_version||0)>0;
   setText(banner,hasValid?t("stale"):t("noValid"));
   banner.dataset.sourceDigest=String(snapshot?.digest||"");
   banner.dataset.renderedDigest=String(snapshot?.rendered_digest||"");
  }
 }
 const dialog=document.getElementById("glyph-conflict-dialog");
 if(dialog){
  setText(dialog.querySelector(".glyph-conflict-head"),t("conflictTitle"));
  setText(dialog.querySelector(".glyph-conflict-body p"),t("conflictMessage"));
  setText(dialog.querySelector('[data-action="load"]'),t("loadExternal"));
  setText(dialog.querySelector('[data-action="overwrite"]'),t("overwrite"));
  setText(dialog.querySelector('[data-action="cancel"]'),t("cancel"));
 }
 document.dispatchEvent(new CustomEvent("glyph-save-state-changed",{
  detail:{marker:MARKER,persistence,render:renderState,stale:isStale()}
 }));
}

function showConflictDialog(){
 updateUi();
 const dialog=document.getElementById("glyph-conflict-dialog");
 if(!dialog||!conflict)return;
 if(dialog.open)return;
 conflictDialogShownFor=String(conflict.digest||"");
 if(typeof dialog.showModal==="function")dialog.showModal();
 else dialog.setAttribute("open","");
}

function closeConflictDialog(){
 const dialog=document.getElementById("glyph-conflict-dialog");
 if(!dialog)return;
 if(typeof dialog.close==="function"&&dialog.open)dialog.close();
 else dialog.removeAttribute("open");
 updateUi();
}

async function fetchJson(path,options={}){
 const controller=new AbortController();
 const timeout=setTimeout(()=>controller.abort(),REQUEST_TIMEOUT_MS);
 try{
  const response=await fetch(path,{
   headers:{"Content-Type":"application/json",...(options.headers||{})},
   ...options,
   signal:controller.signal,
  });
  let payload={};
  try{payload=await response.json()}catch{payload={error:await response.text()}}
  return {response,payload};
 }finally{clearTimeout(timeout)}
}

function applySnapshot(next,{updateEditor=false}={}){
 const currentVersion=Number(snapshot?.version??-1);
 const nextVersion=Number(next?.version??-1);
 if(nextVersion<currentVersion)return false;
 snapshot=next;
 if(updateEditor){
  editor.value=String(next.source||"");
  dirty=false;
  syncLines();
 }
 render();
 window.GlyphExecutionContext?.refresh?.();
 setStatus(next.status||"starting");
 updateUi();
 return true;
}

async function performSave(source,{force=false}={}){
 saveInFlight=true;
 updateUi();
 setStatus("busy");
 const submittedSource=source;
 try{
  const {response,payload}=await fetchJson("/api/save",{
   method:"POST",
   body:JSON.stringify({
    source:submittedSource,
    base_digest:editorBaseDigest||null,
    force:Boolean(force),
   }),
  });
  if(response.status===409&&payload?.error==="save_conflict"){
   conflict={
    source:String(payload.current_source??""),
    digest:String(payload.current_digest??""),
    state:payload.state||null,
   };
   dirty=true;
   setStatus("error");
   updateUi();
   showConflictDialog();
   return false;
  }
  if(!response.ok)throw new Error(payload?.error||payload?.message||`${response.status}`);
  const next=payload;
  editorBaseDigest=String(next.digest||editorBaseDigest);
  conflict=null;
  conflictDialogShownFor="";
  dirty=editor.value!==submittedSource;
  applySnapshot(next,{updateEditor:false});
  return true;
 }catch(error){
  setStatus("error");
  const message=error?.name==="AbortError"?t("requestFailed"):String(error?.message||error);
  diagnostics.innerHTML=`<div class="diagnostic">${esc(message)}</div>`;
  updateUi();
  return false;
 }finally{
  saveInFlight=false;
  updateUi();
 }
}

async function drainSaveQueue(initialRequest){
 let request=initialRequest;
 while(request){
  queuedSave=null;
  const completed=await performSave(request.source,{force:request.force});
  if(!completed&&conflict)break;
  request=queuedSave;
 }
}

save=async function saveAndRender(options={}){
 const request={source:editor.value,force:Boolean(options.force)};
 if(saveInFlight){
  queuedSave=request;
  dirty=true;
  updateUi();
  return;
 }
 await drainSaveQueue(request);
};

load=async function loadSavedState(initial=false){
 if(pollInFlight||saveInFlight)return;
 pollInFlight=true;
 try{
  const {response,payload:next}=await fetchJson("/api/state");
  if(!response.ok)throw new Error(next?.error||`${response.status}`);
  if(!initialized||initial){
   initialized=true;
   editorBaseDigest=String(next.digest||"");
   conflict=null;
   applySnapshot(next,{updateEditor:!dirty});
   return;
  }
  const diskChanged=String(next.digest||"")!==editorBaseDigest;
  if(diskChanged&&dirty){
   conflict={
    source:String(next.source||""),
    digest:String(next.digest||""),
    state:next,
   };
   updateUi();
   if(conflictDialogShownFor!==conflict.digest)showConflictDialog();
   return;
  }
  if(diskChanged){
   editorBaseDigest=String(next.digest||"");
   conflict=null;
   conflictDialogShownFor="";
   applySnapshot(next,{updateEditor:true});
   return;
  }
  if(Number(next.version||0)>Number(snapshot?.version||0)){
   applySnapshot(next,{updateEditor:false});
  }else{
   updateUi();
  }
 }catch(error){
  if(error?.name!=="AbortError"){
   setStatus("error");
   diagnostics.innerHTML=`<div class="diagnostic">${esc(String(error?.message||error))}</div>`;
  }
 }finally{
  pollInFlight=false;
 }
};

async function loadExternalVersion(){
 if(!conflict)return;
 const external=conflict;
 closeConflictDialog();
 try{
  const {response,payload}=await fetchJson("/api/rebuild",{method:"POST",body:"{}"});
  if(!response.ok)throw new Error(payload?.error||`${response.status}`);
  editorBaseDigest=String(payload.digest||external.digest);
  conflict=null;
  conflictDialogShownFor="";
  applySnapshot(payload,{updateEditor:true});
 }catch(error){
  editor.value=external.source;
  editorBaseDigest=external.digest;
  dirty=false;
  syncLines();
  conflict=null;
  conflictDialogShownFor="";
  diagnostics.innerHTML=`<div class="diagnostic">${esc(String(error?.message||error))}</div>`;
  updateUi();
 }
}

async function overwriteExternalVersion(){
 if(!conflict)return;
 editorBaseDigest=conflict.digest;
 conflict=null;
 conflictDialogShownFor="";
 closeConflictDialog();
 await save({force:true});
}

editor.addEventListener("input",()=>{
 dirty=true;
 updateUi();
});
window.addEventListener("beforeunload",event=>{
 if(!dirty&&!conflict)return;
 event.preventDefault();
 event.returnValue="";
});
document.addEventListener("glyph-locale-applied",updateUi);
document.addEventListener("glyph-locale-changed",updateUi);
document.addEventListener("visibilitychange",()=>{if(!document.hidden)load(false)});

ensureUi();
updateUi();
if(snapshot){
 initialized=true;
 editorBaseDigest=String(snapshot.digest||"");
 updateUi();
}else{
 queueMicrotask(()=>load(true));
}
pollTimer=setInterval(()=>load(false),POLL_INTERVAL_MS);
window.GlyphSaveTriggeredRendering={
 marker:MARKER,
 version:2,
 get baseDigest(){return editorBaseDigest},
 get conflict(){return conflict},
 get saveInFlight(){return saveInFlight},
 refresh:updateUi,
};
})();
</script>
"""


def _replace_once(html: str, old: str, new: str, label: str) -> str:
    if old not in html:
        raise ValueError(f"save controller anchor changed: {label}")
    return html.replace(old, new, 1)


def _replace_pattern_once(
    html: str,
    pattern: str,
    replacement: str,
    label: str,
) -> str:
    result, count = re.subn(
        pattern,
        replacement,
        html,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise ValueError(f"save controller anchor changed: {label}")
    return result


def enhance_save_controller_html(html: str) -> str:
    """Make saving the only source action that compiles and redraws diagrams."""

    if _MARKER in html:
        return html
    html = _replace_once(
        html,
        '  <button id="compile" class="primary">Compile</button>\n'
        '  <button id="save">Save</button>',
        '  <button id="save" class="primary" '
        'title="Save and render (Ctrl/Cmd+S)">Save & Render</button>\n'
        f'  <!-- {_MARKER} -->',
        "header controls",
    )
    html = _replace_once(
        html,
        "let snapshot=null,activeTab='io',systemIndex=0,machineIndex=0,dirty=false,previewTimer=null;",
        "let snapshot=null,activeTab='io',systemIndex=0,machineIndex=0,dirty=false;",
        "preview timer state",
    )
    html = _replace_once(
        html,
        "async function compile(){setStatus('busy');snapshot=await request('/api/preview',{method:'POST',body:JSON.stringify({source:editor.value})});render()}\n",
        "",
        "base preview request",
    )
    html = _replace_once(
        html,
        "document.getElementById('compile').onclick=compile;document.getElementById('save').onclick=save;",
        "document.getElementById('save').onclick=()=>save();",
        "base compile button handler",
    )
    html = _replace_pattern_once(
        html,
        r"editor\.addEventListener\('input',\(\)=>\{.*?\}\);"
        r"(?=editor\.addEventListener\('scroll')",
        "editor.addEventListener('input',()=>{dirty=true;syncLines()});",
        "editor input preview",
    )
    html = _replace_once(
        html,
        "document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();compile()}if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();save()}});",
        "document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();save()}});",
        "compile keyboard shortcut",
    )
    forbidden = (
        "/api/preview",
        "previewTimer",
        "previewController",
        "stableCompile",
        'id="compile"',
    )
    remaining = [value for value in forbidden if value in html]
    if remaining:
        raise ValueError(
            "save controller still contains preview execution: "
            + ", ".join(remaining)
        )
    html = html.replace("</head>", _STYLE + "\n</head>", 1)
    return html.replace("</body>", _SCRIPT + "\n</body>", 1)
