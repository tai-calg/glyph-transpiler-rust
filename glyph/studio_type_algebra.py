from __future__ import annotations

from copy import deepcopy
from typing import Mapping


def _records(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _json_value(value: object) -> object:
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def attach_type_algebra_view(
    studio_views: Mapping[str, object],
    algebra: Mapping[str, object],
    tooling: Mapping[str, object],
) -> dict[str, object]:
    """Attach Type Algebra data without changing the seven orthogonal view contract."""

    result = deepcopy(dict(studio_views))
    summary = result.setdefault("summary", {})
    if not isinstance(summary, dict):
        raise ValueError("invalid Studio summary payload")

    types = [_json_value(dict(item)) for item in _records(algebra.get("types"))]
    diagnostics = [
        _json_value(dict(item)) for item in _records(tooling.get("diagnostics"))
    ]
    structural = [
        _json_value(dict(item))
        for item in _records(tooling.get("structural_conversions"))
    ]
    machine_coverage = [
        _json_value(dict(item))
        for item in _records(tooling.get("machine_coverage"))
    ]
    isomorphism_classes = [
        _json_value(dict(item))
        for item in _records(algebra.get("isomorphism_classes"))
    ]

    result["type_algebra"] = {
        "types": types,
        "diagnostics": diagnostics,
        "isomorphism_classes": isomorphism_classes,
        "structural_conversions": structural,
        "machine_coverage": machine_coverage,
    }
    summary.update(
        {
            "type_algebra_types": len(types),
            "type_algebra_impossible": sum(
                bool(item.get("impossible"))
                for item in types
                if isinstance(item, Mapping)
            ),
            "type_algebra_diagnostics": len(diagnostics),
            "type_algebra_isomorphisms": len(isomorphism_classes),
            "type_algebra_structural_conversions": sum(
                bool(item.get("generated"))
                for item in structural
                if isinstance(item, Mapping)
            ),
            "type_algebra_machines": len(machine_coverage),
            "type_algebra_missing_cases": sum(
                int(item.get("missing_pairs") or 0)
                for item in machine_coverage
                if isinstance(item, Mapping)
            ),
            "type_algebra_unknown_cases": sum(
                int(item.get("unknown_pairs") or 0)
                for item in machine_coverage
                if isinstance(item, Mapping)
            ),
            "type_algebra_overlap_cases": sum(
                int(item.get("overlap_pairs") or 0)
                for item in machine_coverage
                if isinstance(item, Mapping)
            ),
        }
    )
    result["enabled"] = bool(result.get("enabled") or types or machine_coverage)
    return result


def extend_studio_html(html: str) -> str:
    """Add the Type Algebra view without duplicating the base Studio document."""

    view_anchor = (
        "{id:'Verification',glyph:'✓',description:'Static, model, runtime, and trusted guarantees.'}"
    )
    view_insert = (
        view_anchor
        + ",{id:'Type Algebra',glyph:'Σ',description:'Finite cardinalities, structural isomorphisms, and selector × input machine coverage.'}"
    )
    if view_anchor not in html:
        raise ValueError("Studio view registry anchor changed")
    html = html.replace(view_anchor, view_insert, 1)

    count_anchor = "'Verification':summary.verification_items||0,'Architecture'"
    count_insert = (
        "'Verification':summary.verification_items||0,'Type Algebra':summary.type_algebra_types||0,'Architecture'"
    )
    if count_anchor not in html:
        raise ValueError("Studio view count anchor changed")
    html = html.replace(count_anchor, count_insert, 1)

    renderer = r'''
function typeAlgebraView(){
 const view=state?.glyph04_views?.type_algebra||{},types=view.types||[],diagnostics=view.diagnostics||[],classes=view.isomorphism_classes||[],structural=view.structural_conversions||[],coverage=view.machine_coverage||[];
 if(!types.length&&!coverage.length)return empty('Type Algebra analysis is not available for this source.');
 const finite=types.filter(item=>item.cardinality_exact).length,impossible=types.filter(item=>item.impossible).length,generated=structural.filter(item=>item.generated).length,missing=coverage.reduce((sum,item)=>sum+Number(item.missing_pairs||0),0),unknown=coverage.reduce((sum,item)=>sum+Number(item.unknown_pairs||0),0),overlap=coverage.reduce((sum,item)=>sum+Number(item.overlap_pairs||0),0);
 const cards=`<div class="cards"><div class="card"><div class="value">${types.length}</div><div class="label">Types</div></div><div class="card"><div class="value">${finite}</div><div class="label">Exact finite domains</div></div><div class="card"><div class="value">${impossible}</div><div class="label">Impossible types</div></div><div class="card"><div class="value">${generated}</div><div class="label">Structural conversions</div></div><div class="card"><div class="value">${missing}</div><div class="label">Missing cases</div></div><div class="card"><div class="value">${unknown}</div><div class="label">Unknown cases</div></div><div class="card"><div class="value">${overlap}</div><div class="label">Overlapping cases</div></div></div>`;
 const typeRows=types.map(item=>`<div class="row"${lineAttr(item.source?.line)}${filterAttr(item.name,item.normal_form,item.cardinality,item.declaration_kind)}><b>${esc(item.name)}</b><span class="chip ${item.impossible?'bad':item.cardinality_exact?'ok':''}">${item.impossible?'impossible':item.cardinality_exact?'finite':'symbolic'}</span><span class="mono">|T|=${esc(item.cardinality??'?')} · ${esc(item.normal_form||'?')}</span>${sourceJump(item.source?.line)}</div>`).join('');
 const diagnosticRows=diagnostics.map(item=>`<div class="error"${lineAttr(item.line)}${filterAttr(item.code,item.subject,item.message)}><b>${esc(item.code)}</b><br>${esc(item.message)}</div>`).join('');
 const classRows=classes.map(item=>`<div class="card"${filterAttr(item.id,item.members,item.normal_form)}><div class="step-head"><b>${esc((item.members||[]).join(' ≅ '))}</b><span class="chip accent">${esc(item.id)}</span></div><div class="mono">${esc(item.normal_form)}</div><div class="muted">cardinality: ${esc(item.cardinality??'?')}</div></div>`).join('');
 const structuralRows=structural.map(item=>`<div class="card"${filterAttr(item.source_type,item.target_type,(item.steps||[]).map(step=>step.law))}><div class="step-head"><b>${esc(item.source_type)} ↔ ${esc(item.target_type)}</b><span class="chip ${item.generated?'ok':'bad'}">${item.generated?'generated':'rejected'}</span></div>${(item.steps||[]).map(step=>`<div class="mono">${esc(step.law)}: ${esc(step.before)} → ${esc(step.after)}</div>`).join('')}${item.reason?`<div class="muted">${esc(item.reason)}</div>`:''}</div>`).join('');
 const coverageRows=coverage.map(item=>{
  const outcomeCards=[['defined',item.defined_pairs,'ok'],['rejected',item.rejected_pairs,'bad'],['default',item.fallthrough_pairs,''],['missing',item.missing_pairs,'bad'],['unknown',item.unknown_pairs,''],['overlap',item.overlap_pairs,'bad']].map(([label,value,kind])=>`<span class="chip ${kind}">${label}: ${esc(value??'?')}</span>`).join('');
  const guards=(item.guards||[]).map(guard=>`<div class="row"${lineAttr(guard.line)}${filterAttr(guard.condition,guard.classification)}><b>#${guard.index} ${esc(guard.classification)}</b><span>→</span><span class="mono">${esc(guard.condition)}<br>true=${guard.true_cases} · first=${guard.first_match_cases} · shadowed=${guard.shadowed_cases} · unknown=${guard.unknown_cases}</span>${sourceJump(guard.line)}</div>`).join('');
  const cases=(item.cases||[]).map(row=>{const representatives=(row.inputs||[]).map(input=>`${input.name}=${input.value}`).join(', '),regionItems=row.regions||[],regions=regionItems.length?regionItems.map(input=>`${input.name}=${input.value}`).join(', '):representatives,multiplicity=row.multiplicity||'1',label=row.outcome==='fallthrough'?'default':row.outcome;return `<div class="row"${lineAttr(row.line)}${filterAttr(row.selector,regions,representatives,row.outcome,row.target_state,row.matching_clauses)}><b>${esc(row.selector)}</b><span class="chip ${row.outcome==='defined'||row.outcome==='fallthrough'?'ok':row.outcome==='missing'||row.outcome==='rejected'?'bad':''}">${esc(label)}</span><span class="mono">region: ${esc(regions||'()')} · cases=${esc(multiplicity)}${regionItems.length?`<br>representative: ${esc(representatives||'()')}`:''}<br>clause=${esc(row.selected_clause??'—')} · matches=${esc((row.matching_clauses||[]).join(',')||'—')} · target=${esc(row.target_state??'?')}</span>${sourceJump(row.line)}</div>`}).join('');
  const partition=item.partitioned?`symbolic regions: ${esc(item.region_count??(item.cases||[]).length)} · concrete cases: ${esc(item.concrete_case_count??item.possible_pairs??'?')}`:`possible: ${esc(item.possible_pairs??'?')}`;
  return `<section class="section card"${filterAttr(item.machine,item.selector_type,item.input_types,item.complete)}><div class="step-head"><div><b>${esc(item.machine)}</b><div class="mono muted">${esc(item.selector_field||'?')}: ${esc(item.selector_type||'?')} × ${esc((item.input_types||[]).join(' × ')||'()')}</div></div><span class="chip ${item.complete===true?'ok':item.complete===false?'bad':''}">${item.complete===true?'complete':item.complete===false?'incomplete':'unknown'}</span></div><div class="mono">domain: ${esc(item.domain_semantics||'selector×input')}<br>selector: ${esc(item.selector_cardinality??item.state_cardinality??'?')} · input: ${esc(item.input_cardinality??'?')} · ${partition}</div><div class="chips">${outcomeCards}</div>${item.reason?`<div class="muted" style="margin-top:8px">${esc(item.reason)}</div>`:''}${guards?`<h3>Guard reachability</h3><div class="card">${guards}</div>`:''}${cases?`<h3>Coverage matrix</h3><div class="card">${cases}</div>`:''}</section>`;
 }).join('');
 return `<section class="section">${sectionHeading('Type Algebra summary')}${cards}</section>${diagnosticRows?`<section class="section">${sectionHeading('Diagnostics',diagnostics.length+' warnings')}${diagnosticRows}</section>`:''}<section class="section">${sectionHeading('Types',types.length+' declarations')}<div class="card">${typeRows}</div></section>${classRows?`<section class="section">${sectionHeading('Isomorphism classes')}<div class="cards">${classRows}</div></section>`:''}${structuralRows?`<section class="section">${sectionHeading('Structural conversions')}<div class="cards">${structuralRows}</div></section>`:''}${coverageRows?`<section class="section">${sectionHeading('Machine selector × input coverage')}${coverageRows}</section>`:''}`;
}
'''.strip()
    renderer_anchor = "async function architecture()"
    if renderer_anchor not in html:
        raise ValueError("Studio renderer anchor changed")
    html = html.replace(renderer_anchor, renderer + "\n" + renderer_anchor, 1)

    dispatch_anchor = "else if(active==='Verification')html=verificationView();else if(active==='Architecture')"
    dispatch_insert = "else if(active==='Verification')html=verificationView();else if(active==='Type Algebra')html=typeAlgebraView();else if(active==='Architecture')"
    if dispatch_anchor not in html:
        raise ValueError("Studio render dispatch anchor changed")
    return html.replace(dispatch_anchor, dispatch_insert, 1)
