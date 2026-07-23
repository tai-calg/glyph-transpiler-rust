from __future__ import annotations


STUDIO_HTML = r'''<!doctype html>
<html lang="ja" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Glyph Studio</title>
<style>
:root{
  color-scheme:dark;
  --bg:#0b0d12;
  --surface:#11141b;
  --surface-2:#171b24;
  --surface-3:#1d2330;
  --editor:#0c0f15;
  --line:#2a3240;
  --line-soft:#202733;
  --text:#eef2f8;
  --muted:#98a3b4;
  --faint:#687487;
  --accent:#8da8ff;
  --accent-strong:#6f8ff0;
  --accent-soft:rgba(141,168,255,.13);
  --ok:#69d9aa;
  --ok-soft:rgba(105,217,170,.12);
  --bad:#ff8495;
  --bad-soft:rgba(255,132,149,.12);
  --warn:#e6c66d;
  --rust:#d5a2f3;
  --model:#d7a75f;
  --runtime:#b78fe7;
  --trusted:#79aabd;
  --shadow:0 12px 36px rgba(0,0,0,.24);
  --editor-width:44%;
  --nav-width:184px;
}
html[data-theme="light"]{
  color-scheme:light;
  --bg:#f4f6fa;
  --surface:#ffffff;
  --surface-2:#f7f9fc;
  --surface-3:#edf1f7;
  --editor:#fbfcfe;
  --line:#d9e0ea;
  --line-soft:#e7ebf1;
  --text:#18202d;
  --muted:#5e6b7d;
  --faint:#8792a2;
  --accent:#496ed6;
  --accent-strong:#385fc8;
  --accent-soft:rgba(73,110,214,.10);
  --ok:#16865d;
  --ok-soft:rgba(22,134,93,.10);
  --bad:#c53d52;
  --bad-soft:rgba(197,61,82,.09);
  --warn:#946f12;
  --rust:#8b55b5;
  --model:#9a6a18;
  --runtime:#7650a7;
  --trusted:#397389;
  --shadow:0 12px 32px rgba(25,42,70,.10);
}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;background:var(--bg);color:var(--text);font:14px/1.5 Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;overflow:hidden}
button,input,textarea{font:inherit}
button{border:1px solid var(--line);background:var(--surface-2);color:var(--text);border-radius:9px;padding:7px 11px;cursor:pointer;transition:background .14s,border-color .14s,color .14s,transform .14s}
button:hover{background:var(--surface-3);border-color:var(--faint)}
button:active{transform:translateY(1px)}
button:focus-visible,input:focus-visible,textarea:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
button.primary{background:var(--accent-strong);border-color:var(--accent-strong);color:white}
button.primary:hover{filter:brightness(1.08)}
button.quiet{background:transparent;border-color:transparent;color:var(--muted)}
button.quiet:hover{background:var(--surface-3);color:var(--text)}
button:disabled{opacity:.55;cursor:default;transform:none}
.app-header{height:62px;display:flex;align-items:center;gap:11px;padding:0 14px;border-bottom:1px solid var(--line);background:var(--surface);position:relative;z-index:20}
.brand-block{display:flex;align-items:center;gap:10px;min-width:155px}.brand-mark{width:30px;height:30px;border-radius:9px;display:grid;place-items:center;background:var(--accent-soft);color:var(--accent);font-weight:800;border:1px solid color-mix(in srgb,var(--accent) 35%,var(--line))}.brand{font-weight:760;letter-spacing:-.01em}.version{font-size:10px;color:var(--muted);letter-spacing:.08em;text-transform:uppercase}
.path{min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted);font:12px ui-monospace,SFMono-Regular,Menlo,monospace;flex:1}
.header-actions{display:flex;align-items:center;gap:7px}.icon-button{width:36px;height:36px;padding:0;display:grid;place-items:center}.action-label{display:inline}
.status{display:inline-flex;align-items:center;gap:7px;padding:6px 9px;border:1px solid var(--line);border-radius:999px;background:var(--surface-2);font-size:12px;color:var(--muted)}.status::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--faint)}.status.ready{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 30%,var(--line));background:var(--ok-soft)}.status.ready::before{background:var(--ok)}.status.error{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 34%,var(--line));background:var(--bad-soft)}.status.error::before{background:var(--bad)}.status.busy::before{background:var(--accent);animation:pulse 1s infinite alternate}@keyframes pulse{to{opacity:.28}}
.sync-state{font-size:12px;color:var(--muted);min-width:62px;text-align:right}.sync-state.dirty{color:var(--warn)}
.workspace{height:calc(100vh - 62px);display:grid;grid-template-columns:minmax(280px,var(--editor-width)) 7px minmax(0,1fr);background:var(--bg)}
.workspace.editor-hidden{grid-template-columns:0 0 minmax(0,1fr)}.workspace.editor-hidden .editor-pane,.workspace.editor-hidden .splitter{display:none}
.editor-pane{min-width:0;display:flex;flex-direction:column;border-right:1px solid var(--line);background:var(--editor)}
.pane-toolbar{height:46px;display:flex;align-items:center;gap:9px;padding:0 12px;border-bottom:1px solid var(--line);background:var(--surface)}.pane-title{font-weight:650}.pane-meta{margin-left:auto;color:var(--muted);font-size:12px}.auto-preview{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:12px;white-space:nowrap}.auto-preview input{accent-color:var(--accent)}
.editor-wrap{min-height:0;flex:1;display:grid;grid-template-columns:auto 1fr;overflow:hidden}.line-numbers{padding:15px 10px 20px 8px;background:color-mix(in srgb,var(--editor) 90%,var(--surface-2));border-right:1px solid var(--line-soft);color:var(--faint);text-align:right;white-space:pre;font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;user-select:none;overflow:hidden}.editor{min-width:0;width:100%;height:100%;resize:none;border:0;outline:0;background:var(--editor);color:var(--text);padding:15px 18px 40px;font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace;tab-size:2;white-space:pre;overflow:auto}
.diagnostic-strip{min-height:34px;max-height:112px;overflow:auto;border-top:1px solid var(--line);background:var(--surface);padding:7px 10px}.diagnostic-strip.empty-strip{display:none}.diagnostic-item{display:flex;align-items:flex-start;gap:8px;color:var(--bad);padding:4px 5px;border-radius:6px;cursor:pointer}.diagnostic-item:hover{background:var(--bad-soft)}.diagnostic-icon{font-weight:800}.diagnostic-message{min-width:0;word-break:break-word}.diagnostic-line{margin-left:auto;color:var(--muted);white-space:nowrap}
.splitter{cursor:col-resize;background:var(--line-soft);position:relative;z-index:5}.splitter::after{content:"";position:absolute;inset:0 2px;border-radius:999px;background:transparent}.splitter:hover::after,.splitter.dragging::after{background:var(--accent)}
.viewer{min-width:0;display:flex;flex-direction:column;background:var(--bg)}
.viewer-toolbar{min-height:70px;display:flex;align-items:center;gap:12px;padding:11px 16px;border-bottom:1px solid var(--line);background:var(--surface)}.view-heading{min-width:0;flex:1}.view-title-row{display:flex;align-items:center;gap:9px}.view-title{font-size:17px;font-weight:720;letter-spacing:-.01em}.view-count{font-size:11px;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:1px 7px}.view-description{color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:2px}.search-wrap{position:relative;width:min(260px,32vw)}.search-wrap::before{content:"⌕";position:absolute;left:10px;top:50%;transform:translateY(-52%);color:var(--muted)}.view-search{width:100%;border:1px solid var(--line);background:var(--surface-2);color:var(--text);border-radius:9px;padding:8px 10px 8px 29px}.view-search::placeholder{color:var(--faint)}
.viewer-body{min-height:0;flex:1;display:grid;grid-template-columns:var(--nav-width) minmax(0,1fr)}.view-nav{overflow:auto;border-right:1px solid var(--line);background:var(--surface);padding:10px 8px}.nav-group{margin-bottom:15px}.nav-label{padding:5px 9px;color:var(--faint);font-size:10px;font-weight:700;letter-spacing:.11em;text-transform:uppercase}.nav-item{width:100%;display:flex;align-items:center;gap:8px;border:0;background:transparent;color:var(--muted);padding:8px 9px;text-align:left;border-radius:8px}.nav-item:hover{background:var(--surface-3);color:var(--text)}.nav-item.active{background:var(--accent-soft);color:var(--accent)}.nav-glyph{width:20px;text-align:center;color:inherit;font:12px ui-monospace,SFMono-Regular,Menlo,monospace}.nav-name{flex:1;white-space:nowrap}.nav-count{font-size:10px;min-width:20px;text-align:center;border-radius:999px;background:var(--surface-3);color:var(--muted);padding:1px 5px}.nav-item.active .nav-count{background:color-mix(in srgb,var(--accent) 18%,transparent);color:var(--accent)}
.content{min-width:0;overflow:auto;padding:20px 22px 48px;scroll-behavior:smooth}.content-inner{max-width:1240px;margin:0 auto}.section{margin-bottom:28px}.section-heading{display:flex;align-items:baseline;gap:9px;margin:2px 0 12px}.section-heading h2{margin:0}.section-note{color:var(--muted);font-size:12px}
h2{font-size:15px;margin:5px 0 12px}h3{font-size:13px;margin:20px 0 9px;color:var(--muted);font-weight:650}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px}.card{background:var(--surface);border:1px solid var(--line);border-radius:11px;padding:13px;transition:border-color .13s,background .13s}.card[data-line],.row[data-line],h2[data-line],.stage[data-line],.algorithm-step[data-line],.application[data-line],.diagnostic-item[data-line]{cursor:pointer}.card[data-line]:hover,.row[data-line]:hover,.stage[data-line]:hover,.algorithm-step[data-line]:hover{border-color:var(--accent);background:color-mix(in srgb,var(--surface) 88%,var(--accent-soft))}.filter-hidden{display:none!important}.value{font-size:25px;font-weight:760;letter-spacing:-.03em}.label,.muted{color:var(--muted)}.faint{color:var(--faint)}.mono{font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace}.empty{color:var(--muted);border:1px dashed var(--line);border-radius:11px;padding:24px;text-align:center;background:var(--surface)}
pre{white-space:pre-wrap;word-break:break-word;background:var(--editor);border:1px solid var(--line);border-radius:10px;padding:14px;font:12px/1.58 ui-monospace,SFMono-Regular,Menlo,monospace}.error{border:1px solid color-mix(in srgb,var(--bad) 45%,var(--line));background:var(--bad-soft);color:var(--bad);padding:12px;border-radius:10px;margin-bottom:12px}.error[data-line]{cursor:pointer}.error[data-line]:hover{border-color:var(--bad)}
.edge,.row{display:grid;grid-template-columns:minmax(120px,1fr) 36px minmax(120px,1fr) minmax(80px,auto);gap:8px;padding:9px 7px;border-bottom:1px solid var(--line-soft);align-items:center}.edge:last-child,.row:last-child{border-bottom:0}.component{border-left:3px solid var(--accent)}.component.effect{border-left-color:var(--bad)}.component.rust{border-left-color:var(--rust)}.component.external{border-left-color:var(--muted)}.component.data{border-left-color:var(--ok)}
.symbol{display:grid;grid-template-columns:55px 115px minmax(120px,1fr) minmax(120px,1fr);gap:9px;padding:8px;border-bottom:1px solid var(--line-soft)}.symbol.header{color:var(--muted);font-size:12px;position:sticky;top:-20px;background:var(--bg);z-index:2}.chips{display:flex;flex-wrap:wrap;gap:5px;margin-top:8px}.chip{display:inline-flex;align-items:center;border:1px solid var(--line);background:var(--surface-2);border-radius:999px;padding:2px 7px;font-size:11px;color:var(--muted)}.chip.accent{border-color:color-mix(in srgb,var(--accent) 38%,var(--line));color:var(--accent);background:var(--accent-soft)}.chip.ok{border-color:color-mix(in srgb,var(--ok) 40%,var(--line));color:var(--ok);background:var(--ok-soft)}.chip.bad{border-color:color-mix(in srgb,var(--bad) 38%,var(--line));color:var(--bad);background:var(--bad-soft)}
.applications{margin-top:11px;padding-top:9px;border-top:1px solid var(--line-soft)}.application{display:flex;gap:7px;align-items:center;margin-top:5px;padding:3px;border-radius:6px}.application:hover{background:var(--surface-2)}.line{margin-left:auto;color:var(--muted);font-size:12px}.step-head{display:flex;align-items:baseline;gap:9px;margin-bottom:9px}.step-name{font-weight:750}.type{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--ok)}
.algorithm{margin-bottom:25px}.algorithm-step{border:1px solid var(--line);background:var(--surface);border-radius:11px;margin:9px 0;padding:12px}.branches{display:grid;gap:6px}.branch{display:grid;grid-template-columns:minmax(120px,1fr) 30px minmax(120px,1fr);gap:8px;padding:8px;background:var(--surface-2);border-radius:8px}.pipeline{display:flex;align-items:stretch;gap:7px;overflow-x:auto;padding:5px 0}.stage{min-width:150px;background:var(--surface-2);border:1px solid var(--line);border-radius:9px;padding:9px}.stage.lambda{border-color:#7461a8}.stage.rust{border-color:var(--rust)}.stage.effect{border-color:var(--bad)}.stage.function{border-color:var(--accent)}.stage .kind{text-transform:uppercase;font-size:10px;letter-spacing:.08em;color:var(--muted)}.pipe-arrow{display:flex;align-items:center;color:var(--muted);font-size:18px}.err{color:var(--bad);font-size:11px;margin-top:5px}.expression{font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:var(--surface-2);padding:9px;border-radius:8px}.return-step{border-color:var(--ok)}
.identity{border-left:3px solid var(--ok)}.state-chain,.sequence{display:flex;align-items:stretch;gap:7px;overflow-x:auto;padding:8px 1px}.state-node,.event-node,.graph-node{min-width:130px;border:1px solid var(--line);background:var(--surface-2);border-radius:9px;padding:9px}.state-node{border-color:color-mix(in srgb,var(--ok) 55%,var(--line))}.event-node.send{border-color:color-mix(in srgb,var(--accent) 55%,var(--line))}.event-node.receive{border-color:color-mix(in srgb,var(--ok) 55%,var(--line))}.graph-node.handler{border-color:color-mix(in srgb,var(--runtime) 55%,var(--line))}.graph-node.exit{border-color:color-mix(in srgb,var(--ok) 55%,var(--line))}.graph-node.target{border-color:var(--faint)}.arrow{display:flex;align-items:center;color:var(--muted);font-size:18px}.direction{font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted)}.region{display:flex;align-items:center;flex-wrap:wrap;gap:5px;margin-top:8px}.region-part{border:1px solid var(--line);border-radius:7px;padding:4px 8px;background:var(--surface-2)}.region-separator{color:var(--muted)}
.strength-grid{display:grid;grid-template-columns:repeat(4,minmax(120px,1fr));gap:9px}.strength{border-top:3px solid var(--accent)}.strength.model{border-top-color:var(--model)}.strength.runtime{border-top-color:var(--runtime)}.strength.trusted{border-top-color:var(--trusted)}.table-wrap{overflow-x:auto;border:1px solid var(--line);border-radius:10px}table{width:100%;border-collapse:collapse;background:var(--surface);min-width:520px}th,td{text-align:left;padding:9px;border-bottom:1px solid var(--line-soft)}th{color:var(--muted);font-weight:550;background:var(--surface-2)}tr:last-child td{border-bottom:0}.count{text-align:center}.formula{max-height:280px;overflow:auto}
.code-shell{border:1px solid var(--line);border-radius:11px;overflow:hidden;background:var(--editor)}.code-toolbar{display:flex;align-items:center;gap:8px;padding:8px 10px;border-bottom:1px solid var(--line);background:var(--surface)}.code-name{font:12px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);flex:1}.code-shell pre{margin:0;border:0;border-radius:0;max-height:none}.copy-result{font-size:11px;color:var(--ok)}
.toast{position:fixed;right:18px;bottom:18px;z-index:50;background:var(--surface-3);border:1px solid var(--line);border-radius:10px;padding:10px 13px;box-shadow:var(--shadow);opacity:0;transform:translateY(8px);pointer-events:none;transition:opacity .18s,transform .18s}.toast.show{opacity:1;transform:translateY(0)}
.mobile-nav-button{display:none}
@media(max-width:1050px){.action-label{display:none}.header-actions button:not(.primary){padding-inline:9px}.search-wrap{width:190px}}
@media(max-width:860px){
  .app-header{padding:0 9px}.brand-block{min-width:auto}.brand-block .version,.path{display:none}.workspace{grid-template-columns:1fr}.editor-pane,.splitter{display:none}.workspace.editor-visible-mobile .editor-pane{display:flex;position:fixed;inset:62px 0 0 0;z-index:30}.workspace.editor-visible-mobile .viewer{display:none}.viewer-body{grid-template-columns:1fr}.view-nav{display:none;position:absolute;left:0;top:70px;bottom:0;width:min(260px,82vw);z-index:25;box-shadow:var(--shadow);border-right:1px solid var(--line)}.viewer.nav-open .view-nav{display:block}.mobile-nav-button{display:grid}.viewer-toolbar{padding:10px}.view-description{display:none}.search-wrap{width:min(210px,42vw)}.strength-grid{grid-template-columns:repeat(2,minmax(120px,1fr))}.content{padding:16px 13px 40px}.edge,.row{grid-template-columns:1fr 25px 1fr}.edge>:last-child,.row>:last-child{display:none}.toast{left:12px;right:12px;bottom:12px}}
@media(max-width:560px){.sync-state{display:none}.status{padding:6px}.status span{display:none}.search-wrap{width:42px}.view-search{padding-left:29px}.view-search:not(:focus){color:transparent}.view-title{font-size:15px}.cards{grid-template-columns:1fr}.strength-grid{grid-template-columns:repeat(2,1fr)}.header-actions{gap:4px}}
</style>
</head>
<body>
<header class="app-header">
  <div class="brand-block">
    <div class="brand-mark">G</div>
    <div><div class="brand">Glyph Studio</div><div class="version">Design workspace</div></div>
  </div>
  <div id="path" class="path"></div>
  <div id="sync-state" class="sync-state">Saved</div>
  <div id="status" class="status"><span>starting</span></div>
  <div class="header-actions">
    <button id="theme" class="icon-button quiet" type="button" title="Toggle theme" aria-label="Toggle theme">◐</button>
    <button id="toggle-editor" class="icon-button quiet" type="button" title="Toggle editor" aria-label="Toggle editor">⌁</button>
    <button id="reload" type="button" title="Reload from disk">↻ <span class="action-label">Reload</span></button>
    <button id="preview" type="button" title="Preview without saving (Ctrl/Cmd+Enter)">▶ <span class="action-label">Preview</span></button>
    <button id="save" class="primary" type="button" title="Save (Ctrl/Cmd+S)">Save</button>
  </div>
</header>
<main id="workspace" class="workspace">
  <section id="editor-pane" class="editor-pane" aria-label="Glyph source editor">
    <div class="pane-toolbar">
      <span class="pane-title">Source</span>
      <label class="auto-preview"><input id="auto-preview" type="checkbox"> Auto preview</label>
      <span id="editor-meta" class="pane-meta">0 lines</span>
    </div>
    <div class="editor-wrap">
      <div id="line-numbers" class="line-numbers" aria-hidden="true">1</div>
      <textarea id="editor" class="editor" spellcheck="false" aria-label="Glyph source"></textarea>
    </div>
    <div id="diagnostic-strip" class="diagnostic-strip empty-strip" aria-live="polite"></div>
  </section>
  <div id="splitter" class="splitter" role="separator" aria-orientation="vertical" aria-label="Resize editor"></div>
  <section id="viewer" class="viewer">
    <div class="viewer-toolbar">
      <button id="mobile-nav" class="icon-button quiet mobile-nav-button" type="button" aria-label="Open view navigation">☰</button>
      <div class="view-heading">
        <div class="view-title-row"><div id="view-title" class="view-title">Overview</div><span id="view-count" class="view-count">0</span></div>
        <div id="view-description" class="view-description"></div>
      </div>
      <label class="search-wrap"><input id="view-search" class="view-search" type="search" placeholder="Filter this view" aria-label="Filter current view"></label>
    </div>
    <div class="viewer-body">
      <nav id="view-nav" class="view-nav" aria-label="Studio views"></nav>
      <div id="content" class="content"><div class="content-inner"></div></div>
    </div>
  </section>
</main>
<div id="toast" class="toast" role="status" aria-live="polite"></div>
<script>
const VIEW_GROUPS=[
  {label:'Design',views:[
    {id:'Overview',glyph:'◎',description:'Design summary, build state, and Glyph 0.4 coverage.'},
    {id:'Capability',glyph:'◇',description:'Ownership, sharing, links, borrows, and capability-bearing boundaries.'},
    {id:'Resource',glyph:'ρ',description:'Symbolic resource identities and state transitions.'},
    {id:'World/Region',glyph:'@',description:'Execution loci, dynamic regions, and contract applications.'},
    {id:'Protocol',glyph:'⇄',description:'Typed send/receive sequences with structured control paths.'},
    {id:'Handler',glyph:'!',description:'Declared failure exits, recovery steps, and host obligations.'},
    {id:'Law/Monitor',glyph:'□',description:'Temporal laws, verification classes, and monitor delivery.'},
    {id:'Verification',glyph:'✓',description:'Static, model, runtime, and trusted guarantee coverage.'}
  ]},
  {label:'Program',views:[
    {id:'Architecture',glyph:'⌘',description:'System components and declared connections.'},
    {id:'State',glyph:'S',description:'State machines, initial states, and transitions.'},
    {id:'Logic',glyph:'λ',description:'Algorithm blocks, branches, and pipelines.'},
    {id:'Flow',glyph:'→',description:'Lowered execution nodes and data/control edges.'},
    {id:'Time',glyph:'T',description:'Temporal and safety constraints.'}
  ]},
  {label:'Generated',views:[
    {id:'Rust',glyph:'R',description:'Generated pure logic Rust.'},
    {id:'Host',glyph:'H',description:'Generated effect-boundary host scaffold.'},
    {id:'Manual',glyph:'M',description:'User-owned manual Rust extension point.'},
    {id:'AST',glyph:'{}',description:'Typed design JSON emitted by the compiler.'},
    {id:'Symbols',glyph:'#',description:'Compiler symbols and resolved types.'},
    {id:'Artifacts',glyph:'▦',description:'All generated files for this source.'}
  ]}
];
const VIEWS=VIEW_GROUPS.flatMap(group=>group.views);
let active=localStorage.getItem('glyphStudio.activeView')||'Overview';
if(!VIEWS.some(view=>view.id===active))active='Overview';
let state=null,dirty=false,lastVersion=-1,busy=false,autoTimer=null,toastTimer=null;
const workspace=document.getElementById('workspace');
const viewer=document.getElementById('viewer');
const editor=document.getElementById('editor');
const content=document.getElementById('content');
const contentInner=content.querySelector('.content-inner');
const search=document.getElementById('view-search');
const splitter=document.getElementById('splitter');

function esc(value){return String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]))}
function lineAttr(line){return Number(line)>0?` data-line="${Number(line)}"`:''}
function filterAttr(...values){return ` data-filter="${esc(values.flat(Infinity).filter(Boolean).join(' ')).toLowerCase()}"`}
function chips(values,kind=''){return (values||[]).map(value=>`<span class="chip ${kind}">${esc(value)}</span>`).join('')}
function empty(message){return `<div class="empty">${esc(message)}</div>`}
function studioView(name){return state?.glyph04_views?.views?.[name]||{}}
function sectionHeading(title,note=''){return `<div class="section-heading"><h2>${esc(title)}</h2>${note?`<span class="section-note">${esc(note)}</span>`:''}</div>`}
function diagnosticLine(message){const match=String(message||'').match(/(?:^|\s)(\d+)行目/);return match?Number(match[1]):null}
function applications(items){if(!(items||[]).length)return '';return `<div class="applications"><div class="muted">Applied to</div>${items.map(item=>`<div class="application"${lineAttr(item.line)}${filterAttr(item.target_kind,item.target)}><span class="chip accent">${esc(item.target_kind||'target')}</span><b>${esc(item.target)}</b><span class="line">L${esc(item.line||'—')}</span></div>`).join('')}</div>`}

async function request(url,body){
  const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})});
  const value=await response.json();
  if(!response.ok)throw new Error(value.error||`Request failed: ${response.status}`);
  return value;
}
async function artifact(name){const response=await fetch('/api/artifact?name='+encodeURIComponent(name),{cache:'no-store'});const value=await response.json();return value.content||''}
function setBusy(value,label='Working'){
  busy=value;
  for(const id of ['save','preview','reload'])document.getElementById(id).disabled=value;
  const status=document.getElementById('status');
  if(value){status.className='status busy';status.innerHTML=`<span>${esc(label)}</span>`}else updateChrome();
}
function showToast(message){const toast=document.getElementById('toast');toast.textContent=message;toast.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>toast.classList.remove('show'),1900)}
function updateDirty(next){dirty=next;const sync=document.getElementById('sync-state');sync.textContent=dirty?'Unsaved':'Saved';sync.className='sync-state'+(dirty?' dirty':'');}
function updateEditorMeta(){const lines=editor.value.split('\n').length;document.getElementById('editor-meta').textContent=`${lines} lines · ${editor.value.length} chars`;document.getElementById('line-numbers').textContent=Array.from({length:lines},(_,index)=>index+1).join('\n')}
function syncEditorScroll(){document.getElementById('line-numbers').scrollTop=editor.scrollTop}
function updateDiagnostics(){
  const strip=document.getElementById('diagnostic-strip');
  const diagnostics=state?.diagnostics||[];
  strip.classList.toggle('empty-strip',!diagnostics.length);
  strip.innerHTML=diagnostics.map(item=>{const line=item.line||diagnosticLine(item.message);return `<div class="diagnostic-item"${lineAttr(line)}><span class="diagnostic-icon">×</span><span class="diagnostic-message">${esc(item.message)}</span>${line?`<span class="diagnostic-line">L${line}</span>`:''}</div>`}).join('');
}
function goLine(line){
  const number=Math.max(1,Number(line)||1),parts=editor.value.split('\n');let start=0;
  for(let index=1;index<number;index++)start+=(parts[index-1]||'').length+1;
  const end=start+(parts[number-1]||'').length;
  if(window.innerWidth<=860){workspace.classList.add('editor-visible-mobile')}
  else if(workspace.classList.contains('editor-hidden'))toggleEditor(true);
  editor.focus();editor.setSelectionRange(start,end);
  const lineHeight=parseFloat(getComputedStyle(editor).lineHeight)||20;editor.scrollTop=Math.max(0,(number-3)*lineHeight);syncEditorScroll();
}

function viewCount(id){
  const summary=state?.glyph04_views?.summary||{},semantic=state?.semantic||{},execution=state?.execution_ir||{};
  const counts={
    'Overview':0,'Capability':summary.capability_functions||0,'Resource':summary.resource_identities||0,
    'World/Region':summary.worlds||0,'Protocol':summary.protocols||0,'Handler':summary.handlers||0,
    'Law/Monitor':summary.laws||0,'Verification':summary.verification_items||0,
    'Architecture':semantic.architecture?.systems?.length||0,'State':execution.machines?.length||0,
    'Logic':semantic.blocks?.length||0,'Flow':execution.nodes?.length||0,'Time':execution.temporal?.length||0,
    'Rust':1,'Host':1,'Manual':state?.artifact_names?.includes('manual.rs')?1:0,'AST':1,
    'Symbols':(semantic.symbols||[]).filter(symbol=>!String(symbol.name||'').startsWith('__glyph_')).length,
    'Artifacts':state?.artifact_names?.length||0
  };
  return counts[id]||0;
}
function makeNavigation(){
  const nav=document.getElementById('view-nav');
  nav.innerHTML=VIEW_GROUPS.map(group=>`<div class="nav-group"><div class="nav-label">${esc(group.label)}</div>${group.views.map(view=>`<button type="button" class="nav-item ${view.id===active?'active':''}" data-view="${esc(view.id)}"><span class="nav-glyph">${esc(view.glyph)}</span><span class="nav-name">${esc(view.id)}</span><span class="nav-count">${viewCount(view.id)}</span></button>`).join('')}</div>`).join('');
  nav.querySelectorAll('[data-view]').forEach(button=>button.addEventListener('click',()=>selectView(button.dataset.view)));
}
function selectView(id){active=id;localStorage.setItem('glyphStudio.activeView',id);viewer.classList.remove('nav-open');search.value='';makeNavigation();render()}
function updateViewHeader(){const view=VIEWS.find(item=>item.id===active)||VIEWS[0];document.getElementById('view-title').textContent=view.id;document.getElementById('view-description').textContent=view.description;document.getElementById('view-count').textContent=viewCount(view.id)}
function updateChrome(){
  if(!state)return;
  document.getElementById('path').textContent=state.source_path||'';
  const status=document.getElementById('status');status.className='status '+state.status;status.innerHTML=`<span>${esc(state.status)}</span>`;
  updateDiagnostics();updateViewHeader();makeNavigation();
}

function diagnostics(){return (state?.diagnostics||[]).map(item=>{const line=item.line||diagnosticLine(item.message);return `<div class="error"${lineAttr(line)}>${esc(item.message)}</div>`}).join('')}
function overview(){
  const execution=state.execution_ir||{},semantic=state.semantic||{},summary=state.glyph04_views?.summary||{};
  const base=[['Functions',(semantic.functions||[]).length],['Algorithm blocks',(semantic.blocks||[]).length],['Rust TODOs',(semantic.rust_todos||[]).length],['Machines',(execution.machines||[]).length],['Time constraints',(execution.temporal||[]).length],['Symbols',(semantic.symbols||[]).length]];
  const design=[['Resources',summary.resources||0],['Resource identities',summary.resource_identities||0],['Worlds',summary.worlds||0],['Protocols',summary.protocols||0],['Handlers',summary.handlers||0],['Laws',summary.laws||0]];
  const cards=items=>`<div class="cards">${items.map(([label,value])=>`<div class="card"${filterAttr(label)}><div class="value">${value}</div><div class="label">${esc(label)}</div></div>`).join('')}</div>`;
  return diagnostics()+`<section class="section">${sectionHeading('Program')}</section>${cards(base)}${state.glyph04_views?.enabled?`<section class="section" style="margin-top:28px">${sectionHeading('Glyph 0.4 design')}</section>${cards(design)}`:''}<section class="section" style="margin-top:28px">${sectionHeading('Build details')}<div class="card"><div class="mono">Status: ${esc(state.status)}<br>Updated: ${esc(state.updated_at)}<br>Digest: ${esc((state.digest||'').slice(0,16))}<br>Output: ${esc(state.output_dir)}</div></div></section>`
}
function capabilityView(){
  const view=studioView('capability'),resources=view.resources||[],functions=view.functions||[],aggregates=view.aggregates||[],operations=view.operations||[];
  if(!resources.length&&!functions.length&&!aggregates.length&&!operations.length)return empty('Glyph 0.4 capability declarations are not present.');
  const resourceCards=resources.map(resource=>`<div class="card identity"${lineAttr(resource.line)}${filterAttr(resource.name,resource.states)}><b>${esc(resource.name)}</b><div class="muted">resource · L${esc(resource.line||'—')}</div><div class="chips">${chips(resource.states,'ok')}</div></div>`).join('');
  const functionCards=functions.map(fn=>`<div class="card"${lineAttr(fn.line)}${filterAttr(fn.name,fn.marker,(fn.params||[]).map(item=>item.type?.raw||item.type?.name),fn.result?.raw||fn.result?.name)}><b>${esc(fn.name)}</b><div class="muted">${esc(fn.marker)} function · L${esc(fn.line||'—')}</div><div class="mono" style="margin-top:8px">${(fn.params||[]).map(param=>`${esc(param.name)}: ${esc(param.type?.raw||param.type?.name||'?')}`).join('<br>')||'()'}<br>→ ${esc(fn.result?.raw||fn.result?.name||'?')}</div></div>`).join('');
  const aggregateCards=aggregates.map(item=>`<div class="card"${lineAttr(item.line)}${filterAttr(item.name,(item.fields||[]).map(field=>field.name+' '+(field.type?.raw||field.type?.name||'')))}><b>${esc(item.name)}</b><div class="muted">aggregate · L${esc(item.line||'—')}</div><div class="mono" style="margin-top:8px">${(item.fields||[]).map(field=>`${esc(field.name)}: ${esc(field.type?.raw||field.type?.name||'?')}`).join('<br>')||'No capability fields'}</div></div>`).join('');
  const operationRows=operations.map(operation=>`<div class="row"${lineAttr(operation.line)}${filterAttr(operation.kind,operation.source,operation.target)}><b>${esc(operation.kind)}</b><span>→</span><span class="mono">${esc(operation.source||'')} ${operation.target?'→ '+esc(operation.target):''}</span><span class="line">L${esc(operation.line||'—')}</span></div>`).join('');
  return `${resourceCards?`<section class="section">${sectionHeading('Resources',resources.length+' declarations')}<div class="cards">${resourceCards}</div></section>`:''}${functionCards?`<section class="section">${sectionHeading('Capability boundaries',functions.length+' functions')}<div class="cards">${functionCards}</div></section>`:''}${aggregateCards?`<section class="section">${sectionHeading('Stored capabilities',aggregates.length+' aggregates')}<div class="cards">${aggregateCards}</div></section>`:''}${operationRows?`<section class="section">${sectionHeading('Operations',operations.length+' operations')}<div class="card">${operationRows}</div></section>`:''}`
}
function resourceView(){
  const identities=studioView('resource').identities||[];if(!identities.length)return empty('No symbolic resource identities were derived.');
  return identities.map(identity=>{const states=(identity.states||[]).map((name,index)=>`${index?'<span class="arrow">→</span>':''}<div class="state-node"><div class="direction">state ${index+1}</div><b>${esc(name)}</b></div>`).join('');const transitions=(identity.transitions||[]).map(item=>`<div class="row"${lineAttr(item.line)}${filterAttr(item.function,item.kind,item.source?.state,item.target?.state)}><b>${esc(item.function)}</b><span>→</span><span>${esc(item.source?.state||'fresh')} → ${esc(item.target?.state||'?')}</span><span class="chip">${esc(item.kind)}</span></div>`).join('');return `<section class="section card identity"${lineAttr(identity.line)}${filterAttr(identity.resource,identity.identity,identity.states,identity.capabilities)}><div class="step-head"><div><b>${esc(identity.resource)}</b><div class="mono muted">${esc(identity.identity)}</div></div><span class="line">L${esc(identity.line||'—')}</span></div><div class="chips">${chips(identity.capabilities,'accent')}</div><div class="state-chain">${states}</div><div>${transitions}</div></section>`}).join('')
}
function worldRegionView(){const worlds=studioView('world_region').worlds||[];if(!worlds.length)return empty('No World or Region contracts are present.');return `<div class="cards">${worlds.map(world=>{const region=(world.region||[]).map((part,index)=>`${index?'<span class="region-separator">/</span>':''}<span class="region-part">${esc(part)}</span>`).join('');return `<div class="card"${lineAttr(world.line)}${filterAttr(world.name,world.locus,world.region)}><div class="step-head"><b>${esc(world.name)}</b><span class="chip accent">${esc(world.locus)}</span><span class="line">L${esc(world.line||'—')}</span></div><div class="muted">Dynamic Region</div><div class="region">${region||'<span class="muted">root</span>'}</div>${applications(world.applications)}</div>`}).join('')}</div>`}
function protocolView(){const protocols=studioView('protocol').protocols||[];if(!protocols.length)return empty('No Protocol contracts are present.');return protocols.map(protocol=>{const events=(protocol.events||[]).map((event,index)=>`${index?'<span class="arrow">→</span>':''}<div class="event-node ${esc(event.direction)}"${filterAttr(event.direction,event.type,event.path,event.controls)}><div class="direction">${event.direction==='send'?'send →':'receive ←'}</div><b>${esc(event.type||'?')}</b><div class="mono muted">${esc(event.path)}</div><div class="chips">${chips(event.controls)}</div></div>`).join('');return `<section class="section card"${lineAttr(protocol.line)}${filterAttr(protocol.name,(protocol.events||[]).map(item=>item.type))}><div class="step-head"><b>${esc(protocol.name)}</b><span class="line">L${esc(protocol.line||'—')}</span></div><div class="sequence">${events||'<span class="muted">No events.</span>'}</div>${applications(protocol.applications)}</section>`}).join('')}
function handlerView(){const handlers=studioView('handler').handlers||[];if(!handlers.length)return empty('No Handler contracts are present.');return handlers.map(handler=>{const byId=Object.fromEntries((handler.nodes||[]).map(node=>[node.id,node]));const chain=(handler.edges||[]).map((edge,index)=>{const source=byId[edge.source]||{},target=byId[edge.target]||{};return `${index===0?`<div class="graph-node ${esc(source.kind)}"${lineAttr(source.line)}><div class="direction">${esc(source.kind)}</div><b>${esc(source.label)}</b></div>`:''}<span class="arrow" title="${esc(edge.label)}">→</span><div class="graph-node ${esc(target.kind)}"${lineAttr(target.line)}${filterAttr(target.kind,target.label,target.arguments,target.verification)}><div class="direction">${esc(target.kind)}</div><b>${esc(target.label)}</b>${(target.arguments||[]).length?`<div class="mono muted">${esc(target.arguments.join(', '))}</div>`:''}<div class="chips">${chips(String(target.verification||'').split('+').filter(Boolean))}</div></div>`}).join('');return `<section class="section card"${lineAttr(handler.line)}${filterAttr(handler.name,(handler.steps||[]).map(step=>step.operation))}><div class="step-head"><b>${esc(handler.name)}</b><span class="line">L${esc(handler.line||'—')}</span></div><div class="sequence">${chain}</div>${applications(handler.applications)}</section>`}).join('')}
function lawView(){const laws=studioView('law').laws||[];if(!laws.length)return empty('No Law contracts or monitor obligations are present.');return laws.map(law=>`<section class="section card"${lineAttr(law.line)}${filterAttr(law.name,law.verification,JSON.stringify(law.formula||{}))}><div class="step-head"><b>${esc(law.name)}</b><div class="chips">${chips(String(law.verification||'').split('+').filter(Boolean),'accent')}</div><span class="line">L${esc(law.line||'—')}</span></div><pre class="formula">${esc(JSON.stringify(law.formula||{},null,2))}</pre>${(law.requirements||[]).map(requirement=>`<div class="muted">Monitor requirement: ${esc(requirement.id||requirement.kind)}</div>`).join('')}${applications(law.applications)}</section>`).join('')}
function verificationView(){const view=studioView('verification_strength'),classes=view.classes||[],matrix=view.matrix||[],items=view.items||[];if(!items.length)return empty('No Glyph 0.4 verification report is present.');const cards=classes.map(item=>`<div class="card strength ${esc(item.name)}"${filterAttr(item.name)}><div class="value">${item.count||0}</div><div class="label">${esc(item.name)}</div></div>`).join('');const head=['Axis','static','model','runtime','trusted'];const rows=matrix.map(row=>`<tr${filterAttr(row.axis)}><td><b>${esc(row.axis)}</b></td>${head.slice(1).map(name=>`<td class="count">${row[name]||0}</td>`).join('')}</tr>`).join('');const itemRows=items.map(item=>`<div class="card"${lineAttr(item.line)}${filterAttr(item.subject,item.axis,item.statement,item.classes)} style="margin-bottom:8px"><div class="step-head"><b>${esc(item.subject)}</b><span class="chip">${esc(item.axis)}</span><span class="line">L${esc(item.line||'—')}</span></div><div>${esc(item.statement)}</div><div class="chips">${chips(item.classes||[],'accent')}</div></div>`).join('');return `<section class="section">${sectionHeading('Verification strength')}<div class="strength-grid">${cards}</div></section><section class="section">${sectionHeading('Axis × guarantee class')}<div class="table-wrap"><table><thead><tr>${head.map(name=>`<th>${esc(name)}</th>`).join('')}</tr></thead><tbody>${rows}</tbody></table></div></section><section>${sectionHeading('Obligations',items.length+' items')}${itemRows}</section>`}
async function architecture(){let data={systems:[]};try{data=JSON.parse(await artifact('architecture-ir.json'))}catch(_){}const systems=data.systems||[];if(!systems.length)return empty('system declaration is not present.');return systems.map(system=>{const byId=Object.fromEntries((system.components||[]).map(component=>[component.id,component]));const components=(system.components||[]).map(component=>`<div class="card component ${esc(component.kind)}"${lineAttr(component.line)}${filterAttr(component.name,component.kind,component.binding)}><b>${esc(component.name)}</b><div class="muted">${esc(component.kind)}${component.binding?' · '+esc(component.binding):''} · L${component.line}</div></div>`).join('');const edges=(system.edges||[]).map(edge=>`<div class="edge"${lineAttr(edge.line)}${filterAttr(byId[edge.source_id]?.name,byId[edge.target_id]?.name)}><b>${esc(byId[edge.source_id]?.name||edge.source_id)}</b><span>→</span><b>${esc(byId[edge.target_id]?.name||edge.target_id)}</b><span class="muted">L${edge.line}</span></div>`).join('');return `<section class="section">${sectionHeading(system.name)}<div class="cards">${components}</div><h3>Connections</h3><div class="card">${edges}</div></section>`}).join('')}
function stateView(){const machines=state.execution_ir?.machines||[];if(!machines.length)return empty('machine declaration is not present.');return machines.map(machine=>{const transitions=(machine.transitions||[]).map(item=>`<div class="edge"${lineAttr(item.source?.line||machine.source?.line||1)}${filterAttr(item.source_state,item.target_state,item.condition)}><b>${esc(item.source_state)}</b><span>→</span><b>${esc(item.target_state)}</b><span>${esc(item.condition)}</span></div>`).join('');return `<section class="section">${sectionHeading(machine.name)}<div class="card mono">initial: ${esc(machine.initial_state)}<br>success: ${esc(machine.success_state)}<br>failure: ${esc(machine.failure_state)}</div><h3>Transitions</h3><div class="card">${transitions}</div></section>`}).join('')}
function renderPipeline(value){const first=`<div class="stage value"><div class="kind">INPUT</div><b>${esc(value.input_text||'value')}</b><div class="muted">${esc(value.input_type||'')}</div></div>`;const stages=(value.stages||[]).map(stage=>`<div class="pipe-arrow">→</div><div class="stage ${esc(stage.kind)}"${lineAttr(stage.source?.line||1)}${filterAttr(stage.kind,stage.label,stage.input_type,stage.output_type)}><div class="kind">${esc(stage.kind)}</div><b>${esc(stage.label)}</b><div class="muted">${esc(stage.input_type||'?')} → ${esc(stage.output_type||'?')} · L${stage.source?.line||0}</div>${stage.propagates?'<div class="err">Err exits this function</div>':''}</div>`).join('');return `<div class="pipeline">${first}${stages}</div>`}
function renderValue(value){if(value.kind==='conditional')return `<div class="branches">${(value.branches||[]).map(branch=>`<div class="branch"${lineAttr(branch.source?.line||1)}${filterAttr(branch.condition,branch.value,branch.binders)}><b>${esc(branch.condition==='_'?'otherwise':branch.condition)}</b><span>→</span><span>${esc(branch.value)}${(branch.binders||[]).length?`<div class="muted">bind ${esc(branch.binders.join(', '))}</div>`:''}</span></div>`).join('')}</div>`;if(value.kind==='pipeline')return renderPipeline(value);return `<div class="expression">${esc(value.source_text)}</div>`}
async function logic(){let data={functions:[]};try{data=JSON.parse(await artifact('algorithm-ir.json'))}catch(_){}const functions=data.functions||[];if(!functions.length)return empty('No := algorithm blocks. Lowered compiler helpers are intentionally hidden.');return functions.map(fn=>`<section class="algorithm"${filterAttr(fn.name,fn.return_type)}><h2${lineAttr(fn.source?.line||1)}>${esc(fn.name)} <span class="type">→ ${esc(fn.return_type)}</span></h2>${(fn.steps||[]).map(step=>`<div class="algorithm-step ${step.kind==='return'?'return-step':''}"${lineAttr(step.source?.line||1)}${filterAttr(step.kind,step.name,step.type)}><div class="step-head"><span class="step-name">${step.kind==='return'?'return':esc(step.name)}</span><span class="type">${esc(step.type)}</span><span class="line">L${step.source?.line||0}</span></div>${renderValue(step.value||{})}</div>`).join('')}</section>`).join('')}
function flowView(){const execution=state.execution_ir||{},nodes=execution.nodes||[],edges=execution.edges||[];const cards=nodes.map(node=>`<div class="card component ${esc(node.kind)}"${lineAttr(node.source?.line||1)}${filterAttr(node.label,node.kind)}><b>${esc(node.label)}</b><div class="muted">${esc(node.kind)} · L${node.source?.line||0}</div></div>`).join('');const rows=edges.map(edge=>`<div class="edge"${lineAttr(edge.source?.line||1)}${filterAttr(edge.source_id,edge.target_id,edge.label,edge.kind)}><b>${esc(edge.source_id)}</b><span>→</span><b>${esc(edge.target_id)}</b><span>${esc(edge.label||edge.kind)}</span></div>`).join('');return `<section class="section">${sectionHeading('Lowered execution flow',nodes.length+' nodes')}<div class="cards">${cards}</div><h3>Edges</h3><div class="card">${rows||empty('No execution edges.')}</div></section>`}
function timeView(){const items=state.execution_ir?.temporal||[];return `${sectionHeading('Time and safety constraints',items.length+' items')}${items.map(item=>`<div class="card"${lineAttr(item.source?.line||1)}${filterAttr(item.name,item.formula,item.streaming_monitor)} style="margin-bottom:9px"><b>${esc(item.name)}</b><pre>${esc(item.formula)}</pre><div class="muted">${esc(item.streaming_monitor)}</div></div>`).join('')||empty('No temporal constraints.')}`}
async function codeView(name){const text=await artifact(name);if(!text&&name==='manual.rs')return empty('manual.rs is available only in GlyphProjectStudio after the scaffold is created.');return `<div class="code-shell"><div class="code-toolbar"><span class="code-name">${esc(name)}</span><span id="copy-result" class="copy-result"></span><button type="button" data-copy-code>Copy</button></div><pre id="code-content">${esc(text)}</pre></div>`}
function astView(){return `<div class="code-shell"><div class="code-toolbar"><span class="code-name">typed design</span><button type="button" data-copy-code>Copy</button></div><pre id="code-content">${esc(JSON.stringify(state.semantic||{},null,2))}</pre></div>`}
function symbolsView(){const items=(state.semantic?.symbols||[]).filter(symbol=>!String(symbol.name||'').startsWith('__glyph_'));return `<div class="symbol header"><span>ID</span><span>Kind</span><span>Name</span><span>Type</span></div>${items.map(symbol=>`<div class="symbol"${filterAttr(symbol.id,symbol.kind,symbol.name,symbol.type)}><span>${symbol.id}</span><span>${esc(symbol.kind)}</span><b>${esc(symbol.name)}</b><span>${esc(symbol.type||'')}</span></div>`).join('')||empty('No symbols.')}`}
function artifactsView(){return `${sectionHeading('Generated automatically',String((state.artifact_names||[]).length)+' files')}<div class="cards">${(state.artifact_names||[]).map(name=>`<div class="card"${filterAttr(name)}><b>${esc(name)}</b><div class="mono muted" style="margin-top:6px">${esc(state.output_dir+'/'+name)}</div></div>`).join('')}</div>`}

async function render(){
  if(!state)return;
  updateChrome();contentInner.innerHTML='<div class="muted">Rendering…</div>';
  let html='';
  if(active==='Overview')html=overview();else if(active==='Capability')html=capabilityView();else if(active==='Resource')html=resourceView();else if(active==='World/Region')html=worldRegionView();else if(active==='Protocol')html=protocolView();else if(active==='Handler')html=handlerView();else if(active==='Law/Monitor')html=lawView();else if(active==='Verification')html=verificationView();else if(active==='Architecture')html=await architecture();else if(active==='State')html=stateView();else if(active==='Logic')html=await logic();else if(active==='Flow')html=flowView();else if(active==='Time')html=timeView();else if(active==='Rust')html=await codeView('generated.rs');else if(active==='Host')html=await codeView('host.generated.rs');else if(active==='Manual')html=await codeView('manual.rs');else if(active==='AST')html=astView();else if(active==='Symbols')html=symbolsView();else html=artifactsView();
  contentInner.innerHTML=html;applyFilter();content.scrollTop=0;
}
function applyFilter(){const query=search.value.trim().toLowerCase();let visible=0,total=0;contentInner.querySelectorAll('[data-filter]').forEach(item=>{total++;const match=!query||String(item.dataset.filter||'').includes(query);item.classList.toggle('filter-hidden',!match);if(match)visible++});const count=document.getElementById('view-count');if(query&&total)count.textContent=`${visible}/${total}`;else count.textContent=viewCount(active)}
async function copyCode(){const text=document.getElementById('code-content')?.textContent||'';try{await navigator.clipboard.writeText(text)}catch(_){const temporary=document.createElement('textarea');temporary.value=text;document.body.appendChild(temporary);temporary.select();document.execCommand('copy');temporary.remove()}const result=document.getElementById('copy-result');if(result)result.textContent='Copied';showToast('Copied to clipboard')}

async function previewSource(silent=false){if(busy)return;setBusy(true,'previewing');try{const next=await request('/api/preview',{source:editor.value});state=next;lastVersion=next.version;await render();if(!silent)showToast(next.status==='ready'?'Preview updated':'Preview has errors')}catch(error){showToast(error.message)}finally{setBusy(false)}}
async function saveSource(){if(busy)return;setBusy(true,'saving');try{const next=await request('/api/save',{source:editor.value});state=next;lastVersion=next.version;updateDirty(false);await render();showToast(next.status==='ready'?'Saved':'Saved with errors')}catch(error){showToast(error.message)}finally{setBusy(false)}}
async function reloadSource(){if(busy)return;if(dirty&&!confirm('Discard unsaved editor changes and reload from disk?'))return;setBusy(true,'reloading');try{const next=await request('/api/rebuild',{});state=next;lastVersion=next.version;editor.value=state.source||'';updateDirty(false);updateEditorMeta();await render();showToast('Reloaded from disk')}catch(error){showToast(error.message)}finally{setBusy(false)}}
async function refresh(force=false){try{const response=await fetch('/api/state',{cache:'no-store'});const next=await response.json();if(force||next.version!==lastVersion){state=next;lastVersion=next.version;if(!dirty){editor.value=state.source||'';updateEditorMeta()}await render()}}catch(_){}}
function schedulePreview(){clearTimeout(autoTimer);if(document.getElementById('auto-preview').checked)autoTimer=setTimeout(()=>previewSource(true),800)}
function toggleEditor(forceVisible=false){
  if(window.innerWidth<=860){workspace.classList.toggle('editor-visible-mobile',forceVisible||!workspace.classList.contains('editor-visible-mobile'));return}
  workspace.classList.toggle('editor-hidden',forceVisible?false:!workspace.classList.contains('editor-hidden'));
  localStorage.setItem('glyphStudio.editorHidden',workspace.classList.contains('editor-hidden')?'1':'0');
}
function setTheme(theme){document.documentElement.dataset.theme=theme;localStorage.setItem('glyphStudio.theme',theme);document.getElementById('theme').textContent=theme==='dark'?'☼':'◐'}

editor.addEventListener('input',()=>{updateDirty(true);updateEditorMeta();schedulePreview()});
editor.addEventListener('scroll',syncEditorScroll);
editor.addEventListener('keydown',event=>{if(event.key==='Tab'){event.preventDefault();const start=editor.selectionStart,end=editor.selectionEnd;editor.setRangeText('  ',start,end,'end');updateDirty(true);updateEditorMeta();schedulePreview()}});
content.addEventListener('click',event=>{const lineTarget=event.target.closest('[data-line]');if(lineTarget)goLine(lineTarget.dataset.line);const copy=event.target.closest('[data-copy-code]');if(copy)copyCode()});
document.getElementById('diagnostic-strip').addEventListener('click',event=>{const target=event.target.closest('[data-line]');if(target)goLine(target.dataset.line)});
document.getElementById('save').addEventListener('click',saveSource);
document.getElementById('preview').addEventListener('click',()=>previewSource(false));
document.getElementById('reload').addEventListener('click',reloadSource);
document.getElementById('toggle-editor').addEventListener('click',()=>toggleEditor(false));
document.getElementById('theme').addEventListener('click',()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark'));
document.getElementById('mobile-nav').addEventListener('click',()=>viewer.classList.toggle('nav-open'));
search.addEventListener('input',applyFilter);search.addEventListener('keydown',event=>{if(event.key==='Escape'){search.value='';applyFilter();search.blur()}});
document.addEventListener('keydown',event=>{
  const modifier=event.ctrlKey||event.metaKey;
  if(modifier&&event.key.toLowerCase()==='s'){event.preventDefault();saveSource()}
  if(modifier&&event.key==='Enter'){event.preventDefault();previewSource(false)}
  if(modifier&&event.key.toLowerCase()==='k'){event.preventDefault();search.focus();search.select()}
  if(event.key==='Escape'&&workspace.classList.contains('editor-visible-mobile'))workspace.classList.remove('editor-visible-mobile');
});
let dragStart=null;
splitter.addEventListener('pointerdown',event=>{dragStart={x:event.clientX,width:document.getElementById('editor-pane').getBoundingClientRect().width};splitter.setPointerCapture(event.pointerId);splitter.classList.add('dragging')});
splitter.addEventListener('pointermove',event=>{if(!dragStart)return;const width=Math.min(window.innerWidth*.72,Math.max(280,dragStart.width+event.clientX-dragStart.x));document.documentElement.style.setProperty('--editor-width',width+'px')});
splitter.addEventListener('pointerup',event=>{if(!dragStart)return;splitter.releasePointerCapture(event.pointerId);splitter.classList.remove('dragging');const width=document.getElementById('editor-pane').getBoundingClientRect().width;localStorage.setItem('glyphStudio.editorWidth',String(Math.round(width)));dragStart=null});
window.addEventListener('resize',()=>viewer.classList.remove('nav-open'));

const savedTheme=localStorage.getItem('glyphStudio.theme')||'dark';setTheme(savedTheme);
const savedWidth=Number(localStorage.getItem('glyphStudio.editorWidth'));if(savedWidth>=280)document.documentElement.style.setProperty('--editor-width',savedWidth+'px');
if(localStorage.getItem('glyphStudio.editorHidden')==='1')workspace.classList.add('editor-hidden');
updateEditorMeta();refresh(true);setInterval(()=>refresh(false),700);
</script>
</body>
</html>'''
