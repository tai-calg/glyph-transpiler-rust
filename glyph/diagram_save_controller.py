from __future__ import annotations

import re


_MARKER = "glyph-save-triggered-rendering-v3"


_STYLE = r"""
<style id="glyph-save-triggered-rendering-v3-style">
.glyph-save-state{display:flex;align-items:center;gap:6px;white-space:nowrap;font-size:11px;color:var(--muted);border-radius:7px;padding:3px 6px}
.glyph-save-state strong{font-weight:750;color:var(--text)}
.glyph-save-state[data-persistence="unsaved"] .glyph-persistence{color:var(--amber)}
.glyph-save-state[data-persistence="conflict"]{cursor:pointer;outline:1px solid rgba(255,122,139,.38)}
.glyph-save-state[data-persistence="conflict"] .glyph-persistence{color:var(--red)}
.glyph-save-state[data-render="error"] .glyph-render{color:var(--red)}
.glyph-save-state[data-render="saving"] .glyph-render,.glyph-save-state[data-render="compiling"] .glyph-render{color:var(--amber)}
.glyph-save-state:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
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
@media(max-width:760px){
 .glyph-save-state{gap:4px;padding:3px 4px;max-width:120px;overflow:hidden}
 .glyph-save-state .glyph-render{display:none}
 .glyph-save-state span:nth-child(2){display:none}
}
</style>
"""


_SCRIPT = r"""
<script id="glyph-save-triggered-rendering-v3-script">
(()=>{
const MARKER="glyph-save-triggered-rendering-v3";
const STATE_REQUEST_TIMEOUT_MS=5000;
const SAVE_ACK_TIMEOUT_MS=5000;
const POLL_INTERVAL_MS=3000;
const ACTIVE_POLL_INTERVAL_MS=250;
const COPY={
 ja:{
  saved:"保存済み",unsaved:"未保存",conflict:"競合",
  ready:"描画済み",saving:"保存中",compiling:"コンパイル中",error:"コンパイルエラー",
  stale:"表示中の図は最後に正常コンパイルされた保存内容",
  compilingStale:"新しい保存内容をコンパイル中。図は最後の正常結果を表示中",
  noValid:"表示できる正常な図がまだない",
  conflictTitle:"外部変更を検出",
  conflictMessage:"編集中にファイルが外部で変更された。どちらを採用するか選択してください。",
  loadExternal:"外部版を読み込む",overwrite:"自分の版で上書き",cancel:"キャンセル",
  requestFailed:"保存要求に失敗した",outcomeUnknown:"保存結果を確認できないため、ディスク状態を再確認してください",
  saveTitle:"保存して描画 (Ctrl/Cmd+S)",resolveConflict:"競合を解決"
 },
 en:{
  saved:"Saved",unsaved:"Unsaved",conflict:"Conflict",
  ready:"Rendered",saving:"Saving",compiling:"Compiling",error:"Compile error",
  stale:"The diagram shows the last successfully compiled saved source",
  compilingStale:"Compiling the new saved source; the diagram still shows the last successful result",
  noValid:"No valid diagram is available yet",
  conflictTitle:"External change detected",
  conflictMessage:"The file changed outside Glyph Studio while you were editing. Choose which version to keep.",
  loadExternal:"Load external version",overwrite:"Overwrite with mine",cancel:"Cancel",
  requestFailed:"Save request failed",outcomeUnknown:"The save result could not be confirmed. Recheck the disk state.",
  saveTitle:"Save & Render (Ctrl/Cmd+S)",resolveConflict:"Resolve conflict"
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
  group.setAttribute("aria-live","polite");
  group.innerHTML='<strong class="glyph-persistence"></strong><span>·</span><span class="glyph-render"></span>';
  header.insertBefore(group,saveButton);
 }
 const viewer=document.querySelector(".viewer");
 if(viewer&&!document.getElementById("glyph-stale-banner")){
  const banner=document.createElement("div");
  banner.id="glyph-stale-banner";
  banner.className="glyph-stale-banner";
  banner.hidden=true;
  banner.setAttribute("role","status");
  viewer.insertBefore(banner,viewer.firstChild);
 }
 if(!document.getElementById("glyph-conflict-dialog")){
  const dialog=document.createElement("dialog");
  dialog.id="glyph-conflict-dialog";
  dialog.className="glyph-conflict-dialog";
  dialog.setAttribute("aria-labelledby","glyph-conflict-title");
  dialog.setAttribute("aria-describedby","glyph-conflict-description");
  dialog.innerHTML='<div id="glyph-conflict-title" class="glyph-conflict-head"></div><div class="glyph-conflict-body"><p id="glyph-conflict-description"></p><div class="glyph-conflict-actions"><button type="button" data-action="cancel"></button><button type="button" data-action="load"></button><button type="button" class="danger" data-action="overwrite"></button></div></div>';
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
 const renderState=saveInFlight?"saving":snapshot?.status==="compiling"?"compiling":snapshot?.status==="error"?"error":"ready";
 if(group){
  group.dataset.persistence=persistence;
  group.dataset.render=renderState;
  setText(group.querySelector(".glyph-persistence"),t(persistence));
  setText(group.querySelector(".glyph-render"),t(renderState));
  const actionable=Boolean(conflict);
  group.setAttribute("role",actionable?"button":"status");
  group.tabIndex=actionable?0:-1;
  group.title=actionable?t("resolveConflict"):"";
  group.onclick=actionable?()=>showConflictDialog({force:true}):null;
  group.onkeydown=actionable?event=>{
   if(event.key==="Enter"||event.key===" "){
    event.preventDefault();
    showConflictDialog({force:true});
   }
  }:null;
 }
 const button=document.getElementById("save");
 if(button){
  button.disabled=saveInFlight;
  button.title=t("saveTitle");
  button.setAttribute("aria-label",t("saveTitle"));
  button.setAttribute("aria-busy",saveInFlight?"true":"false");
 }
 const banner=document.getElementById("glyph-stale-banner");
 if(banner){
  const stale=isStale();
  banner.hidden=!stale;
  if(stale){
   const hasValid=Number(snapshot?.last_successful_version||0)>0;
   const message=snapshot?.status==="compiling"?t("compilingStale"):hasValid?t("stale"):t("noValid");
   setText(banner,message);
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
 diagnostics?.setAttribute("role",snapshot?.status==="error"?"alert":"status");
 document.dispatchEvent(new CustomEvent("glyph-save-state-changed",{
  detail:{marker:MARKER,persistence,render:renderState,stale:isStale()}
 }));
}

function showConflictDialog({force=false}={}){
 updateUi();
 const dialog=document.getElementById("glyph-conflict-dialog");
 if(!dialog||!conflict)return;
 if(dialog.open)return;
 if(!force&&conflictDialogShownFor===String(conflict.digest||""))return;
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

async function fetchJson(path,options={},timeoutMs=STATE_REQUEST_TIMEOUT_MS){
 const controller=new AbortController();
 const timeout=timeoutMs>0?setTimeout(()=>controller.abort(),timeoutMs):null;
 try{
  const response=await fetch(path,{
   headers:{"Content-Type":"application/json",...(options.headers||{})},
   ...options,
   signal:controller.signal,
  });
  let payload={};
  try{payload=await response.json()}catch{payload={error:await response.text()}}
  return {response,payload};
 }finally{if(timeout!==null)clearTimeout(timeout)}
}

function applySnapshot(next,{updateEditor=false}={}){
 const currentVersion=Number(snapshot?.version??-1);
 const nextVersion=Number(next?.version??-1);
 if(nextVersion<currentVersion)return false;
 const previousRenderedDigest=String(snapshot?.rendered_digest||"");
 snapshot=next;
 if(updateEditor){
  editor.value=String(next.source||"");
  dirty=false;
  syncLines();
 }
 const preservesCurrentDiagram=(next?.status==="error"||next?.status==="compiling")
  && String(next?.rendered_digest||"")===previousRenderedDigest
  && Boolean(view?.childElementCount);
 if(preservesCurrentDiagram){
  setStatus(next.status==="compiling"?"busy":next.status||"error");
  renderSummary();
  renderDiagnostics();
 }else{
  render();
  window.GlyphExecutionContext?.refresh?.();
  setStatus(next.status==="compiling"?"busy":next.status||"starting");
 }
 updateUi();
 return true;
}

async function reconcileSubmittedSave(submittedSource){
 try{
  const {response,payload}=await fetchJson("/api/state",{},STATE_REQUEST_TIMEOUT_MS);
  if(!response.ok||String(payload?.source??"")!==submittedSource)return false;
  editorBaseDigest=String(payload.digest||editorBaseDigest);
  conflict=null;
  conflictDialogShownFor="";
  dirty=editor.value!==submittedSource;
  applySnapshot(payload,{updateEditor:false});
  return true;
 }catch{return false}
}

async function performSave(source,{baseDigest=null}={}){
 saveInFlight=true;
 updateUi();
 setStatus("busy");
 const submittedSource=source;
 try{
  const {response,payload}=await fetchJson("/api/save",{
   method:"POST",
   body:JSON.stringify({
    source:submittedSource,
    base_digest:baseDigest||editorBaseDigest||null,
   }),
  },SAVE_ACK_TIMEOUT_MS);
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
  if(!response.ok)throw new Error(payload?.message||payload?.error||`${response.status}`);
  const next=payload;
  editorBaseDigest=String(next.digest||editorBaseDigest);
  conflict=null;
  conflictDialogShownFor="";
  dirty=editor.value!==submittedSource;
  applySnapshot(next,{updateEditor:false});
  schedulePoll(50);
  return true;
 }catch(error){
  if(error?.name==="AbortError"&&await reconcileSubmittedSave(submittedSource)){
   schedulePoll(50);
   return true;
  }
  setStatus("error");
  const message=error?.name==="AbortError"?t("outcomeUnknown"):String(error?.message||error||t("requestFailed"));
  diagnostics.innerHTML=`<div class="diagnostic">${esc(message)}</div>`;
  dirty=true;
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
  const completed=await performSave(request.source,{baseDigest:request.baseDigest});
  if(!completed)break;
  request=queuedSave;
 }
}

save=async function saveAndRender(options={}){
 const request={source:editor.value,baseDigest:options.baseDigest||null};
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
   showConflictDialog();
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
 closeConflictDialog();
 try{
  const {response,payload}=await fetchJson("/api/rebuild",{method:"POST",body:"{}"});
  if(!response.ok)throw new Error(payload?.message||payload?.error||`${response.status}`);
  editorBaseDigest=String(payload.digest||conflict.digest);
  conflict=null;
  conflictDialogShownFor="";
  applySnapshot(payload,{updateEditor:true});
  schedulePoll(50);
 }catch(error){
  dirty=true;
  diagnostics.innerHTML=`<div class="diagnostic">${esc(String(error?.message||error))}</div>`;
  updateUi();
 }
}

async function overwriteExternalVersion(){
 if(!conflict)return;
 const observedDigest=String(conflict.digest||"");
 closeConflictDialog();
 await save({baseDigest:observedDigest});
}

function nextPollDelay(){
 return snapshot?.status==="compiling"?ACTIVE_POLL_INTERVAL_MS:POLL_INTERVAL_MS;
}

function schedulePoll(delay=nextPollDelay()){
 clearTimeout(pollTimer);
 pollTimer=setTimeout(async()=>{
  await load(false);
  schedulePoll();
 },delay);
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
document.addEventListener("glyph-locale-changed",updateUi);
document.addEventListener("visibilitychange",()=>{
 if(document.hidden)return;
 load(false).finally(()=>schedulePoll());
});

ensureUi();
updateUi();
if(snapshot){
 initialized=true;
 editorBaseDigest=String(snapshot.digest||"");
 updateUi();
}else{
 queueMicrotask(()=>load(true));
}
schedulePoll();
window.GlyphSaveTriggeredRendering={
 marker:MARKER,
 version:3,
 get baseDigest(){return editorBaseDigest},
 get conflict(){return conflict},
 get saveInFlight(){return saveInFlight},
 refresh:updateUi,
 openConflict:()=>showConflictDialog({force:true}),
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
        "document.addEventListener('keydown',event=>{if(event.isComposing)return;if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();save()}});",
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
