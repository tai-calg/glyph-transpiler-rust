from __future__ import annotations


_MARKER = "glyph-diagram-locale-v1"

_STYLE = r"""
<style id="glyph-diagram-locale-v1-style">
.glyph-diagram-settings{position:relative;flex:0 0 auto}
.glyph-diagram-settings-panel{position:absolute;right:0;top:calc(100% + 8px);z-index:120;display:none;min-width:235px;padding:13px;border:1px solid var(--line);border-radius:10px;background:var(--panel);box-shadow:var(--shadow)}
.glyph-diagram-settings-panel.open{display:block}
.glyph-diagram-settings-title{font-weight:720;margin-bottom:10px}
.glyph-diagram-settings-row{display:grid;grid-template-columns:72px minmax(0,1fr);align-items:center;gap:10px;color:var(--muted);font-size:12px}
.glyph-diagram-settings-row select{width:100%;min-width:0}
#status{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important}
#glyph-status-display{flex:0 0 auto}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-locale-v1-script">
(()=>{
const KEY="glyph.ui.locale",DEFAULT_LOCALE="ja";
let locale=localStorage.getItem(KEY)||DEFAULT_LOCALE,scheduled=false;
const pair=(ja,en)=>locale==="ja"?ja:en;
const set=(element,value)=>{if(element&&element.textContent!==value)element.textContent=value};
function diagnosticText(item){return locale==="ja"?(item?.message_ja||item?.message):(item?.message_en||item?.message)}
function selectedMachine(){const machines=(typeof snapshot!=="undefined"?snapshot?.views?.state?.machines:[])||[];return machines[typeof machineIndex!=="undefined"?machineIndex:0]||null}
function ensureStatusDisplay(){
  const canonical=document.getElementById("status");if(!canonical)return null;
  let display=document.getElementById("glyph-status-display");
  if(!display){display=document.createElement("div");display.id="glyph-status-display";canonical.after(display)}
  return display;
}
function ensureSettings(){
  const header=document.querySelector(".app > header");if(!header||document.getElementById("glyph-diagram-settings-button"))return;
  const wrap=document.createElement("div");wrap.className="glyph-diagram-settings";
  wrap.innerHTML=`<button id="glyph-diagram-settings-button" type="button" aria-haspopup="true" aria-expanded="false">⚙ <span></span></button><div class="glyph-diagram-settings-panel"><div class="glyph-diagram-settings-title"></div><label class="glyph-diagram-settings-row"><span></span><select id="glyph-diagram-language-select"><option value="ja">日本語</option><option value="en">English</option></select></label></div>`;
  header.insertBefore(wrap,document.getElementById("compile"));
  const button=wrap.querySelector("#glyph-diagram-settings-button"),panel=wrap.querySelector(".glyph-diagram-settings-panel"),select=wrap.querySelector("select");
  select.value=locale;
  button.addEventListener("click",event=>{event.stopPropagation();const open=!panel.classList.contains("open");panel.classList.toggle("open",open);button.setAttribute("aria-expanded",String(open))});
  select.addEventListener("change",()=>{locale=select.value==="en"?"en":"ja";localStorage.setItem(KEY,locale);apply();document.dispatchEvent(new CustomEvent("glyph-locale-change",{detail:{locale}}))});
  document.addEventListener("click",event=>{if(!wrap.contains(event.target)){panel.classList.remove("open");button.setAttribute("aria-expanded","false")}});
}
function applyDiagnostics(){
  const items=(typeof snapshot!=="undefined"?snapshot?.diagnostics:[])||[];
  document.querySelectorAll("#diagnostics .diagnostic").forEach((element,index)=>set(element,diagnosticText(items[index])||element.textContent));
  const rows=selectedMachine()?.diagnostics||[];
  document.querySelectorAll(".analysis-item > span:nth-child(2)").forEach((element,index)=>set(element,diagnosticText(rows[index])||element.textContent));
}
function translateSummary(){
  const summary=(typeof snapshot!=="undefined"?snapshot?.views?.summary:null)||{};
  const values=[
    [pair("システム","Systems"),summary.systems],
    [pair("呼出可能要素","Callables"),summary.callables],
    [pair("型","Types"),summary.types],
    [pair("状態機械","Machines"),summary.machines],
    [pair("警告","Warnings"),summary.state_warnings],
  ];
  document.querySelectorAll("#summary .pill").forEach((element,index)=>{const item=values[index];if(item)set(element,`${item[0]}: ${item[1]??0}`)});
}
function translateAnalysisTitle(){
  const count=selectedMachine()?.diagnostics?.length||0,element=document.querySelector(".analysis-title");
  if(element)set(element,locale==="ja"?`静的解析 · 警告 ${count} 件`:`Static analysis · ${count} warning${count===1?"":"s"}`);
}
function translateMeta(){
  const machine=selectedMachine();if(!machine)return;
  const values=[
    [pair("状態型","State"),machine.state_type],
    [pair("選択関数","Selector"),machine.selector],
    [pair("次状態関数","Next"),machine.next_function],
    [pair("初期状態","Initial"),machine.initial_state],
    [pair("到達可能","Reachable"),`${machine.analysis?.reachable_state_count??0}/${machine.analysis?.state_count??0}`],
  ];
  document.querySelectorAll(".machine-meta .pill").forEach((element,index)=>{const item=values[index];if(item)set(element,`${item[0]}: ${item[1]??""}`)});
}
function applyStatic(){
  document.documentElement.lang=locale==="ja"?"ja":"en";
  set(document.querySelector(".brand small"),pair("コンパイラ生成のI/O図・状態遷移図","Compiler-derived I/O and state views"));
  set(document.getElementById("compile"),pair("コンパイル","Compile"));set(document.getElementById("save"),pair("保存","Save"));
  set(document.querySelector(".toolbar-title"),pair("Glyph ソース","Glyph source"));
  set(document.querySelector('.tab[data-tab="io"]'),"I/O");set(document.querySelector('.tab[data-tab="state"]'),pair("状態遷移","State transitions"));
  const raw=String((typeof snapshot!=="undefined"?snapshot?.status:"")||document.getElementById("status")?.textContent||"").toLowerCase(),status=ensureStatusDisplay();
  if(status&&raw){status.className=`status ${raw}`;set(status,({starting:pair("起動中","starting"),ready:pair("準備完了","ready"),error:pair("エラー","error"),busy:pair("処理中","busy")})[raw]||raw)}
  const source=document.getElementById("editor")?.value||"",meta=document.getElementById("editor-meta"),count=source.split("\n").length;if(meta)set(meta,locale==="ja"?`${count} 行`:`${count} lines`);
  const tab=typeof activeTab!=="undefined"?activeTab:"state";
  set(document.querySelector(".view-controls h2"),tab==="io"?pair("I/O 構成","I/O topology"):pair("状態遷移","State transitions"));
  document.querySelectorAll(".ports").forEach(ports=>ports.querySelectorAll(".port-group").forEach((group,index)=>{set(group.querySelector(".port-title"),index===0?pair("入力","Inputs"):pair("出力","Output"));const unknown=group.querySelector(".unknown");if(unknown)set(unknown,index===0?pair("なし / 未宣言","none / undeclared"):pair("未宣言","undeclared"))}));
  set(document.querySelector(".type-section h3"),pair("型","Types"));
  const legend=document.querySelectorAll(".legend span");if(legend[0])set(legend[0],pair("到達可能状態","reachable state"));if(legend[1])set(legend[1],pair("到達不能状態","unreachable state"));
  document.querySelectorAll(".state-terminal").forEach(element=>{if(!element.dataset.glyphTerminal)element.dataset.glyphTerminal=element.textContent.toLowerCase();const values={success:["成功","success"],failure:["失敗","failure"],unreachable:["到達不能","unreachable"]},entry=values[element.dataset.glyphTerminal];if(entry)set(element,locale==="ja"?entry[0]:entry[1])});
  set(document.querySelector(".transition-index-title > span:first-child"),pair("遷移の詳細","Transition details"));
  set(document.querySelector(".transition-index-note"),pair("図中ラベルは入力→アクションの要約。完全な情報は各行に表示する","Labels summarize input → action; each row shows the complete transition."));
  translateSummary();translateAnalysisTitle();translateMeta();
  const button=document.getElementById("glyph-diagram-settings-button");if(button){set(button.querySelector("span"),pair("設定","Settings"));button.title=pair("表示設定","Display settings")}
  set(document.querySelector(".glyph-diagram-settings-title"),pair("表示設定","Display settings"));set(document.querySelector(".glyph-diagram-settings-row > span"),pair("言語","Language"));
}
function apply(){ensureSettings();applyStatic();applyDiagnostics()}
function schedule(){if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;apply()})}
new MutationObserver(schedule).observe(document.body,{childList:true,subtree:true,characterData:true});
document.addEventListener("DOMContentLoaded",apply,{once:true});apply();
})();
</script>
"""


def enhance_diagram_locale_html(html: str) -> str:
    """Add Japanese-default labels and an English selector to the diagram app."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
