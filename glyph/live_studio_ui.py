from __future__ import annotations

from .studio_ui import STUDIO_HTML


_NAV_MARKER = "{id:'Overview',glyph:'◎',description:'Design summary, build state, and Glyph 0.4 coverage.'},{id:'Capability'"
_COUNT_MARKER = "{'Overview':summary.semantic_entities||0,'Capability'"
_RENDER_MARKER = "if(active==='Overview')html=overview();else if(active==='Capability')"
_FUNCTION_MARKER = "function capabilityView(){"
_EVENT_MARKER = "editor.addEventListener('input'"
_STYLE_MARKER = "</style>"


def _build_live_studio_html() -> str:
    html = STUDIO_HTML
    for marker in (
        _NAV_MARKER,
        _COUNT_MARKER,
        _RENDER_MARKER,
        _FUNCTION_MARKER,
        _EVENT_MARKER,
        _STYLE_MARKER,
    ):
        if marker not in html:
            raise RuntimeError(f"Glyph Studio UI injection point changed: {marker}")

    html = html.replace(
        _NAV_MARKER,
        "{id:'Overview',glyph:'◎',description:'Design summary, build state, and Glyph 0.4 coverage.'},"
        "{id:'Live Image',glyph:'◉',description:'Active World, pending patches, definition cells, and reload safety.'},"
        "{id:'Capability'",
        1,
    )
    html = html.replace(
        _COUNT_MARKER,
        "{'Overview':summary.semantic_entities||0,'Live Image':state?.live_image?.active_world?.version||0,'Capability'",
        1,
    )
    html = html.replace(
        _RENDER_MARKER,
        "if(active==='Overview')html=overview();else if(active==='Live Image')html=liveImageView();else if(active==='Capability')",
        1,
    )

    live_function = r'''
function liveImageView(){
 const image=state?.live_image||{},activeWorld=image.active_world,pending=image.pending_patch,cells=image.definition_cells||[],history=image.world_history||[],leases=image.leases||[];
 if(!activeWorld)return empty('Live Image has not committed its bootstrap World yet.');
 const activeCard=`<div class="card live-world"><div class="step-head"><div><div class="direction">Active World</div><b>World ${esc(activeWorld.version)}</b></div><span class="chip ok">committed</span></div><div class="detail-grid"><span class="detail-key">Parent</span><span class="detail-value">${esc(activeWorld.parent_version??'bootstrap')}</span><span class="detail-key">Definitions</span><span class="detail-value">${(activeWorld.definitions||[]).length}</span><span class="detail-key">Source</span><span class="detail-value mono">${esc(String(activeWorld.source_digest||'').slice(0,16))}</span><span class="detail-key">Code</span><span class="detail-value mono">${esc(String(activeWorld.code_digest||'').slice(0,16))}</span></div></div>`;
 const leaseCards=leases.length?leases.map(item=>`<div class="card"><b>World ${esc(item.world)}</b><div class="muted">${esc(item.count)} active lease(s)</div></div>`).join(''):empty('No running World leases.');
 let pendingHtml=empty('No pending patch. Valid function-body changes are already committed atomically.');
 if(pending){
  const changes=(pending.changes||[]).map(change=>`<div class="card live-change ${esc(change.safety)}"${lineAttr(change.line)}${filterAttr(change.definition_id,change.kind,change.name,change.safety,change.reason,change.affected)}><div class="step-head"><div><b>${esc(change.name)}</b><div class="mono muted">${esc(change.definition_id)}</div></div><span class="chip ${change.safety==='hot-swap'?'ok':change.safety==='migration'?'bad':'accent'}">${esc(change.safety)}</span>${sourceJump(change.line)}</div><div>${esc(change.change)} · ${esc(change.reason)}</div>${(change.affected||[]).length?`<div class="muted" style="margin-top:7px">Invalidates: ${esc(change.affected.join(', '))}</div>`:''}</div>`).join('');
  const blockers=(pending.blockers||[]).map(value=>`<span class="chip bad">${esc(value)}</span>`).join('');
  pendingHtml=`<div class="card pending-patch"><div class="step-head"><div><div class="direction">Pending Patch</div><b>${esc(pending.id)}</b></div><span class="chip accent">World ${esc(pending.base_world)} → ${esc(pending.target_world)}</span></div><div class="chips">${blockers||'<span class="chip ok">no permanent blockers</span>'}</div><div class="live-actions"><button data-live-action="commit">Commit eligible patch</button><button class="quiet" data-live-action="discard">Discard patch</button></div></div><div class="cards">${changes}</div>`;
 }
 const cellRows=cells.map(cell=>`<div class="row"${filterAttr(cell.id)}><b class="mono">${esc(cell.id)}</b><span>→</span><span>World ${esc(cell.active_world??'—')}</span><span>${(cell.history||[]).length} version(s)</span></div>`).join('')||empty('No definition cells.');
 const worldRows=history.map(world=>`<div class="row"><b>World ${esc(world.version)}</b><span>←</span><span>${esc(world.parent_version??'bootstrap')}</span><span class="mono">${esc(String(world.source_digest||'').slice(0,12))}</span></div>`).join('');
 return `<section class="section">${sectionHeading('Live Image','transactional definition generations')}<div class="cards">${activeCard}</div></section><section class="section">${sectionHeading('Pending reload')} ${pendingHtml}</section><section class="section">${sectionHeading('Running generations')}<div class="cards">${leaseCards}</div></section><section class="section">${sectionHeading('Definition cells',cells.length+' cells')}<div class="card">${cellRows}</div></section><section>${sectionHeading('World history',history.length+' generations')}<div class="card">${worldRows}</div></section>`;
}
async function performLiveAction(action){
 try{
  if(action==='discard'){state=await request('/api/live/discard',{});showToast('Pending patch discarded')}
  else{
   const pending=state?.live_image?.pending_patch;if(!pending)return showToast('No pending patch');
   const body={};
   if((pending.blockers||[]).includes('migration-plan-required')){const plan=prompt('Describe the state/resource migration plan. Empty input cancels.');if(!plan)return;body.migration_plan=plan}
   if((pending.blockers||[]).includes('reader-generation-acknowledgement-required')){if(!confirm('Apply the new reader/macro generation only to subsequent read transactions?'))return;body.reader_acknowledged=true}
   state=await request('/api/live/commit',body);showToast('Live World committed')
  }
  rebuildSemanticCache();updateChrome();await render();
 }catch(error){showToast(error.message)}
}
'''
    html = html.replace(_FUNCTION_MARKER, live_function + _FUNCTION_MARKER, 1)

    live_event = "content.addEventListener('click',event=>{const action=event.target.closest('[data-live-action]');if(action){event.preventDefault();event.stopPropagation();performLiveAction(action.dataset.liveAction)}});"
    html = html.replace(_EVENT_MARKER, live_event + _EVENT_MARKER, 1)

    live_css = r'''
.live-world{border-left:3px solid var(--ok)}.pending-patch{border-left:3px solid var(--warn);margin-bottom:12px}.live-change.hot-swap{border-left:3px solid var(--ok)}.live-change.quiescence{border-left:3px solid var(--accent)}.live-change.migration,.live-change.reader{border-left:3px solid var(--bad)}.live-actions{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
'''
    html = html.replace(_STYLE_MARKER, live_css + _STYLE_MARKER, 1)
    return html


LIVE_STUDIO_HTML = _build_live_studio_html()
