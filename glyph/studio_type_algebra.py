from __future__ import annotations

from copy import deepcopy
from typing import Mapping


def _records(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
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
        + ",{id:'Type Algebra',glyph:'Σ',description:'Finite cardinalities, impossible types, structural isomorphisms, and machine coverage.'}"
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
 const finite=types.filter(item=>item.cardinality_exact).length,impossible=types.filter(item=>item.impossible).length,generated=structural.filter(item=>item.generated).length;
 const cards=`<div class="cards"><div class="card"><div class="value">${types.length}</div><div class="label">Types</div></div><div class="card"><div class="value">${finite}</div><div class="label">Exact finite domains</div></div><div class="card"><div class="value">${impossible}</div><div class="label">Impossible types</div></div><div class="card"><div class="value">${generated}</div><div class="label">Structural conversions</div></div></div>`;
 const typeRows=types.map(item=>`<div class="row"${lineAttr(item.source?.line)}${filterAttr(item.name,item.normal_form,item.cardinality,item.declaration_kind)}><b>${esc(item.name)}</b><span class="chip ${item.impossible?'bad':item.cardinality_exact?'ok':''}">${item.impossible?'impossible':item.cardinality_exact?'finite':'symbolic'}</span><span class="mono">|T|=${esc(item.cardinality??'?')} · ${esc(item.normal_form||'?')}</span>${sourceJump(item.source?.line)}</div>`).join('');
 const diagnosticRows=diagnostics.map(item=>`<div class="error"${lineAttr(item.line)}${filterAttr(item.code,item.subject,item.message)}><b>${esc(item.code)}</b><br>${esc(item.message)}</div>`).join('');
 const classRows=classes.map(item=>`<div class="card"${filterAttr(item.id,item.members,item.normal_form)}><div class="step-head"><b>${esc((item.members||[]).join(' ≅ '))}</b><span class="chip accent">${esc(item.id)}</span></div><div class="mono">${esc(item.normal_form)}</div><div class="muted">cardinality: ${esc(item.cardinality??'?')}</div></div>`).join('');
 const structuralRows=structural.map(item=>`<div class="card"${filterAttr(item.source_type,item.target_type,(item.steps||[]).map(step=>step.law))}><div class="step-head"><b>${esc(item.source_type)} ↔ ${esc(item.target_type)}</b><span class="chip ${item.generated?'ok':'bad'}">${item.generated?'generated':'rejected'}</span></div>${(item.steps||[]).map(step=>`<div class="mono">${esc(step.law)}: ${esc(step.before)} → ${esc(step.after)}</div>`).join('')}${item.reason?`<div class="muted">${esc(item.reason)}</div>`:''}</div>`).join('');
 const coverageRows=coverage.map(item=>`<div class="card"${filterAttr(item.machine,item.state_type,item.input_types,item.complete)}><div class="step-head"><b>${esc(item.machine)}</b><span class="chip ${item.complete===true?'ok':item.complete===false?'bad':''}">${item.complete===true?'complete':item.complete===false?'incomplete':'unknown'}</span></div><div class="mono">state: ${esc(item.state_type)} (${esc(item.state_cardinality??'?')})<br>input: ${esc((item.input_types||[]).join(' × ')||'()')} (${esc(item.input_cardinality??'?')})<br>possible: ${esc(item.possible_pairs??'?')} · defined: ${esc(item.defined_pairs)} · missing: ${esc(item.missing_pairs??'?')}</div>${item.reason?`<div class="muted">${esc(item.reason)}</div>`:''}</div>`).join('');
 return `<section class="section">${sectionHeading('Type Algebra summary')}${cards}</section>${diagnosticRows?`<section class="section">${sectionHeading('Diagnostics',diagnostics.length+' warnings')}${diagnosticRows}</section>`:''}<section class="section">${sectionHeading('Types',types.length+' declarations')}<div class="card">${typeRows}</div></section>${classRows?`<section class="section">${sectionHeading('Isomorphism classes')}<div class="cards">${classRows}</div></section>`:''}${structuralRows?`<section class="section">${sectionHeading('Structural conversions')}<div class="cards">${structuralRows}</div></section>`:''}${coverageRows?`<section class="section">${sectionHeading('Machine state-space coverage')}<div class="cards">${coverageRows}</div></section>`:''}`;
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
