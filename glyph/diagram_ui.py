from __future__ import annotations


DIAGRAM_HTML = r'''<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Glyph Diagram</title>
<style>
:root{
  color-scheme:dark;
  --bg:#090c12;--panel:#111722;--panel2:#151d29;--panel3:#1b2533;
  --line:#2a3748;--text:#edf3fb;--muted:#91a0b4;--faint:#647286;
  --blue:#58a6ff;--green:#45d19a;--purple:#bd8cff;--red:#ff7a8b;--amber:#e7bf62;
  --shadow:0 16px 44px rgba(0,0,0,.28);--editor:42%;
}
*{box-sizing:border-box}html,body{height:100%}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.45 Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;overflow:hidden}
button,select,textarea{font:inherit}button,select{border:1px solid var(--line);background:var(--panel2);color:var(--text);border-radius:8px;padding:8px 11px}button{cursor:pointer}button:hover{background:var(--panel3)}button.primary{background:#2563eb;border-color:#3b82f6;color:white}.app{height:100%;display:flex;flex-direction:column}
header{height:58px;display:flex;align-items:center;gap:12px;padding:0 14px;background:var(--panel);border-bottom:1px solid var(--line)}.brand{font-weight:760;font-size:16px}.brand small{display:block;color:var(--muted);font-size:10px;font-weight:600;letter-spacing:.08em;text-transform:uppercase}.path{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted);font:12px ui-monospace,SFMono-Regular,Menlo,monospace}.status{display:inline-flex;align-items:center;gap:7px;color:var(--muted);font-size:12px}.status::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--faint)}.status.ready{color:var(--green)}.status.ready::before{background:var(--green)}.status.error{color:var(--red)}.status.error::before{background:var(--red)}
main{min-height:0;flex:1;display:grid;grid-template-columns:minmax(330px,var(--editor)) 6px minmax(0,1fr)}.editor-pane{min-width:0;display:flex;flex-direction:column;background:#0b1018;border-right:1px solid var(--line)}.splitter{background:var(--line);cursor:col-resize}.splitter:hover{background:var(--blue)}.toolbar{height:47px;display:flex;align-items:center;gap:8px;padding:0 11px;background:var(--panel);border-bottom:1px solid var(--line)}.toolbar-title{font-weight:700}.toolbar-meta{margin-left:auto;color:var(--muted);font-size:12px}.editor-wrap{min-height:0;flex:1;display:grid;grid-template-columns:auto 1fr}.lines{padding:14px 9px;background:var(--panel);border-right:1px solid var(--line);color:var(--faint);white-space:pre;text-align:right;overflow:hidden;font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}.editor{width:100%;height:100%;resize:none;border:0;outline:0;background:#0b1018;color:var(--text);padding:14px 17px 50px;white-space:pre;overflow:auto;tab-size:2;font:13px/1.6 ui-monospace,SFMono-Regular,Menlo,monospace}.diagnostics{min-height:0;max-height:105px;overflow:auto;border-top:1px solid var(--line);background:var(--panel)}.diagnostic{padding:8px 11px;color:var(--red);border-bottom:1px solid rgba(255,122,139,.15)}
.viewer{min-width:0;display:flex;flex-direction:column}.viewer-head{height:62px;display:flex;align-items:center;gap:12px;padding:0 15px;background:var(--panel);border-bottom:1px solid var(--line)}.tabs{display:flex;gap:5px}.tab{border-color:transparent;background:transparent;color:var(--muted)}.tab.active{background:rgba(88,166,255,.13);border-color:rgba(88,166,255,.35);color:var(--blue)}.summary{margin-left:auto;display:flex;gap:7px;flex-wrap:wrap}.pill{border:1px solid var(--line);background:var(--panel2);border-radius:999px;padding:4px 8px;color:var(--muted);font-size:11px}.view-body{min-height:0;flex:1;overflow:auto;padding:17px}.view-controls{display:flex;align-items:center;gap:10px;margin-bottom:13px}.view-controls h2{font-size:17px;margin:0}.view-controls select{margin-left:auto;min-width:210px}.note{color:var(--muted);font-size:12px}.canvas-shell{position:relative;min-height:390px;border:1px solid var(--line);border-radius:12px;background:radial-gradient(circle at 50% 0%,rgba(88,166,255,.06),transparent 42%),linear-gradient(rgba(255,255,255,.018) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.018) 1px,transparent 1px),var(--panel);background-size:auto,24px 24px,24px 24px,auto;overflow:auto;box-shadow:var(--shadow)}.graph-stage{position:relative;min-width:100%;min-height:390px}.edge-svg{position:absolute;inset:0;overflow:visible;pointer-events:none}.graph-node{position:absolute;width:230px;min-height:138px;border:1px solid #35506f;border-radius:11px;background:linear-gradient(180deg,#172336,#111a28);box-shadow:0 10px 25px rgba(0,0,0,.22);overflow:hidden;cursor:pointer}.graph-node:hover{border-color:var(--blue)}.graph-node.effect{border-color:#76569a;background:linear-gradient(180deg,#241a32,#171321)}.graph-node.external{border-style:dashed;border-color:#5f6a79;background:linear-gradient(180deg,#1b2029,#141820)}.node-head{padding:10px 12px;border-bottom:1px solid var(--line)}.node-kind{font-size:9px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}.node-name{font-size:15px;font-weight:760;overflow:hidden;text-overflow:ellipsis}.ports{display:grid;grid-template-columns:1fr 1fr;min-height:82px}.port-group{padding:9px 10px}.port-group+ .port-group{border-left:1px solid var(--line)}.port-title{font-size:9px;letter-spacing:.1em;color:var(--faint);text-transform:uppercase;margin-bottom:5px}.port{display:flex;gap:5px;align-items:center;margin:4px 0;min-width:0}.port-dot{width:7px;height:7px;border-radius:50%;background:var(--blue);flex:0 0 auto}.port.out .port-dot{background:var(--green)}.port-text{font:11px ui-monospace,SFMono-Regular,Menlo,monospace;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.unknown{color:var(--faint);font-size:11px}.edge-label{position:absolute;transform:translate(-50%,-50%);font:10px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--muted);background:var(--panel);border:1px solid var(--line);border-radius:5px;padding:2px 5px;pointer-events:none}
.type-section{margin-top:18px}.type-section h3{margin:0 0 9px;font-size:13px;color:var(--muted)}.type-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:9px}.type-card{border:1px solid var(--line);border-radius:10px;background:var(--panel);padding:11px;cursor:pointer}.type-card:hover{border-color:var(--blue)}.type-name{font-weight:720}.type-kind{float:right;color:var(--muted);font-size:10px;text-transform:uppercase}.type-row{display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-top:1px solid rgba(255,255,255,.04);font:11px ui-monospace,SFMono-Regular,Menlo,monospace}.type-row span:last-child{color:var(--green)}
.machine-meta{display:flex;gap:7px;flex-wrap:wrap;margin-bottom:11px}.state-node{position:absolute;width:158px;height:76px;border:2px solid #466481;border-radius:38px;background:linear-gradient(180deg,#182536,#121b28);display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;cursor:pointer;box-shadow:0 9px 22px rgba(0,0,0,.22)}.state-node.success{border-color:var(--green)}.state-node.failure{border-color:var(--red)}.state-node.any{border-style:dashed;border-color:var(--faint);color:var(--muted)}.state-name{font-weight:750}.state-terminal{font-size:9px;text-transform:uppercase;letter-spacing:.1em;margin-top:3px}.state-node.success .state-terminal{color:var(--green)}.state-node.failure .state-terminal{color:var(--red)}.initial-dot{position:absolute;width:18px;height:18px;border-radius:50%;background:var(--text);box-shadow:0 0 0 5px rgba(237,243,251,.1)}.empty{padding:54px 20px;text-align:center;color:var(--muted)}
@media(max-width:900px){main{grid-template-columns:1fr}.editor-pane,.splitter{display:none}.summary{display:none}}
</style>
</head>
<body>
<div class="app">
<header>
  <div class="brand">Glyph Diagram<small>Compiler-derived I/O and state views</small></div>
  <div class="path" id="path"></div>
  <div class="status" id="status">starting</div>
  <button id="compile" class="primary">Compile</button>
  <button id="save">Save</button>
</header>
<main id="main">
  <section class="editor-pane">
    <div class="toolbar"><span class="toolbar-title">Glyph source</span><span class="toolbar-meta" id="editor-meta"></span></div>
    <div class="editor-wrap"><div class="lines" id="lines"></div><textarea class="editor" id="editor" spellcheck="false"></textarea></div>
    <div class="diagnostics" id="diagnostics"></div>
  </section>
  <div class="splitter" id="splitter"></div>
  <section class="viewer">
    <div class="viewer-head">
      <div class="tabs"><button class="tab active" data-tab="io">I/O</button><button class="tab" data-tab="state">State transitions</button></div>
      <div class="summary" id="summary"></div>
    </div>
    <div class="view-body" id="view"></div>
  </section>
</main>
</div>
<script>
const editor=document.getElementById('editor');
const lines=document.getElementById('lines');
const statusEl=document.getElementById('status');
const diagnostics=document.getElementById('diagnostics');
const view=document.getElementById('view');
let snapshot=null,activeTab='io',systemIndex=0,machineIndex=0,dirty=false,previewTimer=null;
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
async function request(path,options={}){const response=await fetch(path,{headers:{'Content-Type':'application/json'},...options});if(!response.ok)throw new Error(await response.text());return response.json()}
function setStatus(name){statusEl.textContent=name;statusEl.className='status '+name}
function syncLines(){const count=Math.max(1,editor.value.split('\n').length);lines.textContent=Array.from({length:count},(_,i)=>i+1).join('\n');document.getElementById('editor-meta').textContent=count+' lines'}
function jumpToLine(line){if(!line)return;const rows=editor.value.split('\n');let start=0;for(let i=0;i<Math.max(0,line-1);i++)start+=rows[i].length+1;editor.focus();editor.setSelectionRange(start,start+(rows[line-1]||'').length);editor.scrollTop=Math.max(0,(line-4)*20)}
function renderSummary(){const s=snapshot?.views?.summary||{};document.getElementById('summary').innerHTML=[['Systems',s.systems],['Callables',s.callables],['Types',s.types],['Machines',s.machines]].map(([k,v])=>`<span class="pill">${k}: ${v??0}</span>`).join('')}
function renderDiagnostics(){const rows=snapshot?.diagnostics||[];diagnostics.innerHTML=rows.map(item=>`<div class="diagnostic">${esc(item.message)}</div>`).join('')}
function nodeHeight(){return 138}
function layeredLayout(nodes,edges){
 const map=new Map(nodes.map(n=>[n.id,n])),incoming=new Map(nodes.map(n=>[n.id,0])),out=new Map(nodes.map(n=>[n.id,[]]));
 edges.forEach(e=>{if(map.has(e.source_id)&&map.has(e.target_id)){incoming.set(e.target_id,(incoming.get(e.target_id)||0)+1);out.get(e.source_id).push(e.target_id)}});
 const rank=new Map(),queue=[];nodes.forEach(n=>{if((incoming.get(n.id)||0)===0){rank.set(n.id,0);queue.push(n.id)}});
 while(queue.length){const id=queue.shift(),r=rank.get(id)||0;(out.get(id)||[]).forEach(t=>{rank.set(t,Math.max(rank.get(t)||0,r+1));incoming.set(t,incoming.get(t)-1);if(incoming.get(t)===0)queue.push(t)})}
 let fallback=0;nodes.forEach(n=>{if(!rank.has(n.id))rank.set(n.id,fallback++%3)});
 const groups=new Map();nodes.forEach(n=>{const r=rank.get(n.id);if(!groups.has(r))groups.set(r,[]);groups.get(r).push(n)});
 const pos=new Map();let maxRows=1,maxRank=0;[...groups.keys()].sort((a,b)=>a-b).forEach(r=>{const group=groups.get(r);maxRows=Math.max(maxRows,group.length);maxRank=Math.max(maxRank,r);group.forEach((n,i)=>pos.set(n.id,{x:55+r*300,y:45+i*180}))});
 return {pos,width:Math.max(760,110+maxRank*300+250),height:Math.max(390,90+maxRows*180)}
}
function curve(a,b){const x1=a.x+230,y1=a.y+nodeHeight()/2,x2=b.x,y2=b.y+nodeHeight()/2,m=Math.max(60,(x2-x1)*.48);return `M ${x1} ${y1} C ${x1+m} ${y1}, ${x2-m} ${y2}, ${x2} ${y2}`}
function renderIoGraph(system){
 const nodes=system.nodes||[],edges=system.edges||[];if(!nodes.length)return '<div class="empty">表示できる関数または作用境界がない。</div>';
 const {pos,width,height}=layeredLayout(nodes,edges);let paths='',labels='';
 edges.forEach(e=>{const a=pos.get(e.source_id),b=pos.get(e.target_id);if(!a||!b)return;paths+=`<path d="${curve(a,b)}" fill="none" stroke="#5c7695" stroke-width="2" marker-end="url(#arrow)"/>`;labels+=`<span class="edge-label" style="left:${(a.x+b.x+230)/2}px;top:${(a.y+b.y+nodeHeight())/2}px">connects</span>`});
 const cards=nodes.map(n=>{const p=pos.get(n.id),inputs=n.inputs||[];return `<div class="graph-node ${esc(n.kind)}" data-line="${n.declaration_line||n.line||0}" style="left:${p.x}px;top:${p.y}px"><div class="node-head"><div class="node-kind">${esc(n.kind)}${n.binding?` · ${esc(n.binding)}`:''}</div><div class="node-name">${esc(n.name)}</div></div><div class="ports"><div class="port-group"><div class="port-title">Inputs</div>${inputs.length?inputs.map(i=>`<div class="port"><span class="port-dot"></span><span class="port-text">${esc(i.name)}: ${esc(i.type)}</span></div>`).join(''):'<div class="unknown">none / undeclared</div>'}</div><div class="port-group"><div class="port-title">Output</div>${n.output?`<div class="port out"><span class="port-dot"></span><span class="port-text">${esc(n.output)}</span></div>`:'<div class="unknown">undeclared</div>'}</div></div></div>`}).join('');
 return `<div class="canvas-shell"><div class="graph-stage" style="width:${width}px;height:${height}px"><svg class="edge-svg" width="${width}" height="${height}"><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#5c7695"/></marker></defs>${paths}</svg>${labels}${cards}</div></div>`
}
function renderTypes(types){if(!types.length)return '';return `<section class="type-section"><h3>Types</h3><div class="type-grid">${types.map(t=>{let body='';if(t.kind==='product')body=(t.fields||[]).map(f=>`<div class="type-row"><span>${esc(f.name)}</span><span>${esc(f.type)}</span></div>`).join('');else if(t.kind==='sum')body=(t.variants||[]).map(v=>{const payload=[...(v.tuple||[]),...(v.fields||[]).map(f=>f.name+':'+f.type)].join(', ');return `<div class="type-row"><span>${esc(v.name)}</span><span>${esc(payload||'unit')}</span></div>`}).join('');else body=`<div class="type-row"><span>target</span><span>${esc(t.target)}</span></div>`;return `<div class="type-card" data-line="${t.line||0}"><span class="type-kind">${esc(t.kind)}</span><div class="type-name">${esc(t.name)}</div>${body}</div>`}).join('')}</div></section>`}
function renderIo(){const io=snapshot?.views?.io||{},systems=io.systems||[];systemIndex=Math.min(systemIndex,Math.max(0,systems.length-1));const selected=systems[systemIndex];view.innerHTML=`<div class="view-controls"><div><h2>I/O topology</h2><div class="note">system宣言を優先し、未宣言時はコンパイラの呼出しグラフを表示する。</div></div>${systems.length?`<select id="system-select">${systems.map((s,i)=>`<option value="${i}" ${i===systemIndex?'selected':''}>${esc(s.name)}</option>`).join('')}</select>`:''}</div>${selected?renderIoGraph(selected):'<div class="empty">I/O宣言がない。</div>'}${renderTypes(io.types||[])}`;const select=document.getElementById('system-select');if(select)select.onchange=e=>{systemIndex=Number(e.target.value);renderIo()};bindJumps()}
function statePositions(machine){const states=[...(machine.states||[])],needsAny=(machine.transitions||[]).some(t=>t.source_state==='*'||t.target_state==='*');if(needsAny)states.unshift({name:'*',terminal:null,any:true,source:{line:machine.source?.line||0}});const width=Math.max(780,states.length*150),height=540,cx=width/2,cy=270,r=Math.min(width*.36,190+states.length*10),pos=new Map();states.forEach((s,i)=>{const angle=-Math.PI/2+i*2*Math.PI/states.length;pos.set(s.name,{x:cx+Math.cos(angle)*r-79,y:cy+Math.sin(angle)*r-38,state:s})});return {states,pos,width,height}}
function statePath(a,b,same){const x1=a.x+79,y1=a.y+38,x2=b.x+79,y2=b.y+38;if(same)return `M ${x1-25} ${y1-32} C ${x1-70} ${y1-90}, ${x1+70} ${y1-90}, ${x1+25} ${y1-32}`;const dx=x2-x1,dy=y2-y1,len=Math.max(1,Math.hypot(dx,dy)),sx=x1+dx/len*80,sy=y1+dy/len*38,tx=x2-dx/len*80,ty=y2-dy/len*38;return `M ${sx} ${sy} Q ${(sx+tx)/2-dy*.12} ${(sy+ty)/2+dx*.12} ${tx} ${ty}`}
function renderStateGraph(machine){const {states,pos,width,height}=statePositions(machine),transitions=machine.transitions||[];let paths='',labels='';transitions.forEach((t,i)=>{const a=pos.get(t.source_state),b=pos.get(t.target_state);if(!a||!b)return;paths+=`<path d="${statePath(a,b,t.source_state===t.target_state)}" fill="none" stroke="#7892b0" stroke-width="2" marker-end="url(#state-arrow)"/>`;const lx=(a.x+b.x)/2+79,ly=(a.y+b.y)/2+28-(t.source_state===t.target_state?72:0);labels+=`<span class="edge-label" style="left:${lx}px;top:${ly}px">${esc(t.condition)}</span>`});
 const initial=pos.get(machine.initial_state);let initialMarkup='';if(initial){const dotX=initial.x+79,dotY=Math.max(12,initial.y-48);paths+=`<path d="M ${dotX} ${dotY+18} L ${dotX} ${initial.y-2}" stroke="#edf3fb" stroke-width="2" marker-end="url(#state-arrow)"/>`;initialMarkup=`<span class="initial-dot" style="left:${dotX-9}px;top:${dotY}px"></span>`}
 const cards=states.map(s=>{const p=pos.get(s.name),terminal=s.terminal||'',cls=s.any?'any':terminal;return `<div class="state-node ${cls}" data-line="${s.source?.line||machine.source?.line||0}" style="left:${p.x}px;top:${p.y}px"><div class="state-name">${s.any?'Any state':esc(s.name)}</div>${terminal?`<div class="state-terminal">${esc(terminal)}</div>`:''}</div>`}).join('');return `<div class="canvas-shell"><div class="graph-stage" style="width:${width}px;height:${height}px"><svg class="edge-svg" width="${width}" height="${height}"><defs><marker id="state-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#7892b0"/></marker></defs>${paths}</svg>${labels}${initialMarkup}${cards}</div></div>`}
function renderState(){const machines=snapshot?.views?.state?.machines||[];machineIndex=Math.min(machineIndex,Math.max(0,machines.length-1));const machine=machines[machineIndex];view.innerHTML=`<div class="view-controls"><div><h2>State transitions</h2><div class="note">machine ASTと遷移関数から静的に確定できた状態だけを表示する。</div></div>${machines.length?`<select id="machine-select">${machines.map((m,i)=>`<option value="${i}" ${i===machineIndex?'selected':''}>${esc(m.name)}</option>`).join('')}</select>`:''}</div>${machine?`<div class="machine-meta"><span class="pill">State: ${esc(machine.state_type)}</span><span class="pill">Selector: ${esc(machine.selector)}</span><span class="pill">Next: ${esc(machine.next_function)}</span><span class="pill">Initial: ${esc(machine.initial_state)}</span></div>${renderStateGraph(machine)}`:'<div class="empty">machine宣言がないため、状態遷移は推測しない。</div>'}`;const select=document.getElementById('machine-select');if(select)select.onchange=e=>{machineIndex=Number(e.target.value);renderState()};bindJumps()}
function bindJumps(){document.querySelectorAll('[data-line]').forEach(el=>el.onclick=()=>jumpToLine(Number(el.dataset.line)))}
function render(){setStatus(snapshot?.status||'starting');document.getElementById('path').textContent=snapshot?.source_path||'';renderSummary();renderDiagnostics();activeTab==='io'?renderIo():renderState()}
async function load(initial=false){try{const next=await request('/api/state');snapshot=next;if(initial||!dirty){editor.value=next.source||'';dirty=false;syncLines()}render()}catch(error){setStatus('error');diagnostics.innerHTML=`<div class="diagnostic">${esc(error.message)}</div>`}}
async function compile(){setStatus('busy');snapshot=await request('/api/preview',{method:'POST',body:JSON.stringify({source:editor.value})});render()}
async function save(){setStatus('busy');snapshot=await request('/api/save',{method:'POST',body:JSON.stringify({source:editor.value})});dirty=false;render()}
document.getElementById('compile').onclick=compile;document.getElementById('save').onclick=save;
editor.addEventListener('input',()=>{dirty=true;syncLines();clearTimeout(previewTimer);previewTimer=setTimeout(()=>compile().catch(()=>{}),500)});editor.addEventListener('scroll',()=>{lines.scrollTop=editor.scrollTop});
document.querySelectorAll('.tab').forEach(button=>button.onclick=()=>{activeTab=button.dataset.tab;document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===button));render()});
document.addEventListener('keydown',event=>{if((event.ctrlKey||event.metaKey)&&event.key==='Enter'){event.preventDefault();compile()}if((event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='s'){event.preventDefault();save()}});
const splitter=document.getElementById('splitter'),main=document.getElementById('main');let resizing=false;splitter.onpointerdown=e=>{resizing=true;splitter.setPointerCapture(e.pointerId)};splitter.onpointermove=e=>{if(!resizing)return;const pct=Math.max(25,Math.min(70,e.clientX/window.innerWidth*100));document.documentElement.style.setProperty('--editor',pct+'%')};splitter.onpointerup=()=>resizing=false;
load(true);setInterval(()=>{if(!dirty)load(false)},900);
</script>
</body>
</html>
'''
