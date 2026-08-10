from __future__ import annotations


FAST_LEXICAL_WORKER_JS = r"""(()=>{
const isStart=code=>(code>=65&&code<=90)||(code>=97&&code<=122)||code===95;
const isPart=code=>isStart(code)||(code>=48&&code<=57);
const IDENT=/^[A-Za-z_][A-Za-z0-9_]*$/;
const KIND_PRIORITY=["Resource","Type","StateField","State","Field","Function","EntryFunction","Source","Sink","Temporal","Machine","System","Macro","Binding","Parameter","Contract","Identifier"];

function splitTopLevel(text,separator){
  const output=[];
  let start=0,round=0,brace=0,angle=0,bracket=0;
  for(let index=0;index<text.length;index+=1){
    const ch=text[index];
    if(ch==="(")round+=1;else if(ch===")")round=Math.max(0,round-1);
    else if(ch==="{")brace+=1;else if(ch==="}")brace=Math.max(0,brace-1);
    else if(ch==="<")angle+=1;else if(ch===">")angle=Math.max(0,angle-1);
    else if(ch==="[")bracket+=1;else if(ch==="]")bracket=Math.max(0,bracket-1);
    else if(ch===separator&&round===0&&brace===0&&angle===0&&bracket===0){output.push(text.slice(start,index).trim());start=index+1}
  }
  output.push(text.slice(start).trim());
  return output;
}
function topLevelIndex(text,target){
  let round=0,brace=0,angle=0,bracket=0;
  for(let index=0;index<text.length;index+=1){
    const ch=text[index];
    if(ch==="(")round+=1;else if(ch===")")round=Math.max(0,round-1);
    else if(ch==="{")brace+=1;else if(ch==="}")brace=Math.max(0,brace-1);
    else if(ch==="<")angle+=1;else if(ch===">")angle=Math.max(0,angle-1);
    else if(ch==="[")bracket+=1;else if(ch==="]")bracket=Math.max(0,bracket-1);
    else if(ch===target&&round===0&&brace===0&&angle===0&&bracket===0)return index;
  }
  return-1;
}
function directTypeName(raw){
  const match=String(raw||"").trim().match(/^([A-Za-z_][A-Za-z0-9_]*)$/);
  return match?match[1]:"";
}
function parseNamedFields(body){
  const fields=[];
  const pending=[];
  for(const part of splitTopLevel(body,",")){
    const item=part.trim();
    if(!item)continue;
    const colon=topLevelIndex(item,":");
    if(colon<0){if(IDENT.test(item))pending.push(item);continue}
    const name=item.slice(0,colon).trim();
    const type=item.slice(colon+1).trim();
    const names=[...pending,name];pending.length=0;
    for(const fieldName of names){if(IDENT.test(fieldName))fields.push({name:fieldName,type:directTypeName(type)})}
  }
  return fields;
}
function findMatchingOnLine(line,start,left="(",right=")"){
  if(start<0||line[start]!==left)return-1;
  let depth=0;
  for(let index=start;index<line.length;index+=1){
    if(line[index]===left)depth+=1;
    else if(line[index]===right){depth-=1;if(depth===0)return index}
  }
  return-1;
}
function primaryKind(kinds){
  for(const kind of KIND_PRIORITY){if(kinds.includes(kind))return kind}
  return"Identifier";
}

self.onmessage=event=>{
  const payload=event.data||{};
  const revision=Number(payload.revision||0);
  const source=String(payload.source||"");
  const table=new Map();
  const metadata=new Map();
  const metaFor=text=>{
    let row=metadata.get(text);
    if(!row){row={kinds:new Set(),owners:new Set(),ownerKinds:new Map()};metadata.set(text,row)}
    return row;
  };
  const mark=(text,kind,owner="")=>{
    if(!text)return;
    const meta=metaFor(text);meta.kinds.add(kind);
    if(owner){
      meta.owners.add(owner);
      let kinds=meta.ownerKinds.get(owner);
      if(!kinds){kinds=new Set();meta.ownerKinds.set(owner,kinds)}
      kinds.add(kind);
    }
  };

  // Pass 1: collect every identifier position while distinguishing comment-only occurrences.
  let index=0,comment=false;
  while(index<source.length){
    const code=source.charCodeAt(index);
    if(code===10){comment=false;index+=1;continue}
    if(code===35){comment=true;index+=1;continue}
    if(!isStart(code)){index+=1;continue}
    const start=index;index+=1;
    while(index<source.length&&isPart(source.charCodeAt(index)))index+=1;
    const text=source.slice(start,index);
    let row=table.get(text);
    if(!row){row={all:[],code:[]};table.set(text,row)}
    row.all.push(start);if(!comment)row.code.push(start);
  }

  // Pass 2: classify declarations line-by-line. This replaces the old whole-source
  // stripComments copy plus many independent global-regexp scans.
  const sumVariants=new Map();
  const productFields=new Map();
  const machineRows=[];
  let activeMachine=null;
  for(const rawLine of source.split("\n")){
    const hash=rawLine.indexOf("#");
    const line=hash<0?rawLine:rawLine.slice(0,hash);
    if(!line.trim())continue;
    const indented=/^[ \t]/.test(line);
    if(!indented)activeMachine=null;
    let match;

    if(indented){
      match=line.match(/^[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]*:=/);
      if(match)mark(match[1],"Binding");
      if(activeMachine){
        match=line.match(/^[ \t]+select[ \t]*=[ \t]*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)/);
        if(match)activeMachine.selectorField=match[2];
      }
      continue;
    }

    const first=line[0];
    if(first==="*"){
      match=line.match(/^\*[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*\(/);
      if(match){
        const name=match[1],open=line.indexOf("(",match.index),close=findMatchingOnLine(line,open);
        if(close>=0){
          mark(name,"Type");
          const fields=parseNamedFields(line.slice(open+1,close)),fieldMap={};
          for(const field of fields){fieldMap[field.name]=field.type;mark(field.name,"Field",name)}
          productFields.set(name,fieldMap);
        }
      }
      continue;
    }
    if(first==="+"){
      match=line.match(/^\+[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=(.*)$/);
      if(match){
        const name=match[1],parts=splitTopLevel(match[2],"|");
        if(parts.length&&!parts.some(part=>!part.match(/^([A-Za-z_][A-Za-z0-9_]*)/))){
          mark(name,"Type");const variants=[];
          for(const part of parts){const variant=part.match(/^([A-Za-z_][A-Za-z0-9_]*)/)?.[1]||"";if(variant){variants.push(variant);mark(variant,"State",name)}}
          sumVariants.set(name,variants);
        }
      }
      continue;
    }
    if(first==="="){
      match=line.match(/^=[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*([^\s].*)$/);
      if(match)mark(match[1],"Type");
      continue;
    }
    if(first===">"||first==="!"||first==="~"||first==="?"){
      match=line.match(/^([>!~?])[ \t]*([A-Za-z_][A-Za-z0-9_]*)[ \t]*\(/);
      if(match){
        const marker=match[1],name=match[2],open=line.indexOf("(",match.index),close=findMatchingOnLine(line,open);
        if(close>=0){
          const kind=marker==="!"?"Sink":marker==="?"?"Temporal":"Function";
          mark(name,kind);if(marker===">")mark(name,"EntryFunction");
          for(const field of parseNamedFields(line.slice(open+1,close)))mark(field.name,"Parameter",name);
        }
      }
      continue;
    }
    if(first==="@"){
      const raw=line.match(/^@([A-Z][A-Z0-9_]*)(?=[ \t]|=|$)/);
      const ast=line.match(/^@([A-Za-z_][A-Za-z0-9_]*)[ \t]*\(/);
      const name=raw?.[1]||ast?.[1]||"";
      if(name&&name!=="A"&&name!=="E")mark(name,"Macro");
      continue;
    }
    if(first==="'"){
      match=line.match(/^'[@>!?]?[ \t]*([A-Za-z_][A-Za-z0-9_]*)\b/);
      if(match)mark(match[1],"Contract");
      continue;
    }

    if(line.startsWith("resource")){
      match=line.match(/^resource[ \t]+([A-Za-z_][A-Za-z0-9_]*)(?:[ \t]*<[^>\n]*>)?[ \t]*\[/);
      if(match){
        const name=match[1],open=line.indexOf("[",match.index),close=findMatchingOnLine(line,open,"[","]");
        if(close>=0){
          mark(name,"Resource");mark(name,"Type");
          for(const part of splitTopLevel(line.slice(open+1,close),"|")){const state=part.match(/^[ \t]*([A-Za-z_][A-Za-z0-9_]*)/)?.[1]||"";if(state)mark(state,"State",name)}
        }
      }
      continue;
    }
    if(line.startsWith("ext")){
      match=line.match(/^ext[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]*\(/);
      if(match){
        const name=match[1],open=line.indexOf("(",match.index),close=findMatchingOnLine(line,open);
        if(close>=0){mark(name,"Source");for(const field of parseNamedFields(line.slice(open+1,close)))mark(field.name,"Parameter",name)}
      }
      continue;
    }
    if(line.startsWith("system")){
      match=line.match(/^system[ \t]+([A-Za-z_][A-Za-z0-9_]*)\b/);if(match)mark(match[1],"System");
      continue;
    }
    if(line.startsWith("machine")){
      match=line.match(/^machine[ \t]+([A-Za-z_][A-Za-z0-9_]*)[ \t]*\(/);
      if(match){
        const name=match[1],open=line.indexOf("(",match.index),close=findMatchingOnLine(line,open);
        if(close>=0){
          mark(name,"Machine");
          const params=parseNamedFields(line.slice(open+1,close));for(const param of params)mark(param.name,"Parameter",name);
          const stateParam=params[0]||null;
          activeMachine={name,stateType:stateParam?.type||"",selectorField:""};machineRows.push(activeMachine);
        }
      }
    }
  }

  for(const [owner,fields] of productFields.entries()){
    for(const [field,type] of Object.entries(fields)){if(type&&sumVariants.has(type))mark(field,"StateField",owner)}
  }
  const machineRecords=machineRows.map(row=>({
    name:row.name,stateType:row.stateType,selectorField:row.selectorField,
    selectorType:row.stateType&&row.selectorField?(productFields.get(row.stateType)?.[row.selectorField]||""):"",
  }));
  machineRecords.sort((left,right)=>left.name<right.name?-1:left.name>right.name?1:0);

  const names=[...table.keys()].sort();
  let allLength=0,codeLength=0;
  for(const name of names){const row=table.get(name);allLength+=row.all.length;codeLength+=row.code.length}
  const positions=new Int32Array(allLength),codePositions=new Int32Array(codeLength),records=[];
  let allOffset=0,codeOffset=0;
  for(const text of names){
    const row=table.get(text),meta=metadata.get(text);
    positions.set(row.all,allOffset);codePositions.set(row.code,codeOffset);
    const kinds=meta?[...meta.kinds]:["Identifier"];if(!kinds.length)kinds.push("Identifier");
    const owners=meta?[...meta.owners]:[];
    const ownerKinds=meta?Object.fromEntries([...meta.ownerKinds.entries()].map(([owner,set])=>[owner,[...set]])):{};
    records.push({text,allOffset,allCount:row.all.length,codeOffset,codeCount:row.code.length,kinds,owners,ownerKinds,kind:primaryKind(kinds)});
    allOffset+=row.all.length;codeOffset+=row.code.length;
  }
  self.postMessage({type:"snapshot",revision,sourceLength:source.length,records,positions,codePositions,machineRecords},[positions.buffer,codePositions.buffer]);
};
})();
"""


def install_fast_lexical_worker() -> None:
    """Replace the compatibility worker payload with the line-oriented implementation."""

    from . import editor_lexical_index

    editor_lexical_index.LEXICAL_WORKER_JS = FAST_LEXICAL_WORKER_JS


__all__ = ["FAST_LEXICAL_WORKER_JS", "install_fast_lexical_worker"]
