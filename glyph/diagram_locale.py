from __future__ import annotations


_MARKER = "glyph-diagram-locale-v1"

_STYLE = r"""
<style id="glyph-diagram-locale-v1-style">
.glyph-settings-button{min-width:38px}
.glyph-settings-dialog{width:min(440px,calc(100vw - 32px));border:1px solid var(--line);border-radius:14px;padding:0;background:var(--panel);color:var(--text);box-shadow:0 24px 70px rgba(0,0,0,.42)}
.glyph-settings-dialog::backdrop{background:rgba(3,7,18,.52);backdrop-filter:blur(3px)}
.glyph-settings-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 16px;border-bottom:1px solid var(--line)}
.glyph-settings-head h2{margin:0;font-size:17px}.glyph-settings-close{padding:5px 9px}
.glyph-settings-body{display:grid;gap:14px;padding:16px}.glyph-settings-row{display:grid;grid-template-columns:minmax(120px,1fr) minmax(170px,1.3fr);align-items:center;gap:14px}
.glyph-settings-row label{font-weight:700}.glyph-settings-row select{width:100%}.glyph-settings-note{margin:0;color:var(--muted);font-size:12px;line-height:1.6}
.diagnostic{display:grid;gap:3px}.diagnostic-code{font:700 10px ui-monospace,SFMono-Regular,Menlo,monospace;color:var(--amber)}.diagnostic-help{color:var(--muted);font-size:11px}
.analysis-item{grid-template-columns:auto minmax(0,1fr) auto}.analysis-message{min-width:0}.analysis-help{display:block;margin-top:3px;color:var(--muted);font-size:10px}
@media(max-width:640px){.glyph-settings-row{grid-template-columns:1fr}.glyph-settings-dialog{width:calc(100vw - 20px)}}
</style>
"""

_SCRIPT = r"""
<script id="glyph-diagram-locale-v1-script">
(()=>{
const STORAGE_KEY="glyph.ui.locale",SUPPORTED=new Set(["ja","en"]);
let locale=SUPPORTED.has(localStorage.getItem(STORAGE_KEY))?localStorage.getItem(STORAGE_KEY):"ja";
const STRINGS={
 ja:{settings:"設定",settingsTitle:"表示設定",language:"表示言語",languageNote:"コンパイル結果の意味は変えず、UIと診断の表示だけを切り替えます。",close:"閉じる",compile:"コンパイル",save:"保存",io:"I/O",state:"状態遷移",autoLayout:"自動配置",systems:"システム",callables:"関数・作用",types:"型",machines:"状態機械",warnings:"警告",source:"Glyphコード",ioTitle:"I/O構成",ioNote:"system宣言を優先し、未宣言の場合はコンパイラが導出した呼出し関係を表示します。",stateTitle:"状態遷移",stateNote:"ワイルドカードを実状態へ展開し、到達不能分岐を除外して描画します。",transitionDetails:"遷移の詳細",transitionNote:"図中は入力→作用の要約です。完全な遷移情報は各行に表示します。",reachable:"到達可能",unreachable:"到達不能",typesSection:"型",themeWhite:"白",themeMono:"白黒",genericCompileError:"Glyphコードをコンパイルできません。",genericCompileHelp:"エラー位置の周辺で、括弧、型、名前、分岐の>>、default節を確認してください。",executionContextLabel:"実行コンテキスト",executionContextAuto:"自動（一致する場合のみ）",executionContextMachine:"Machineのみ",executionContextConditional:"（条件付き）",executionContextUnresolved:"（解析不能）",executionContextMultiple:"（複数遷移）",executionContextActionless:"（System Actionなし）",executionContextImplicit:"暗黙の呼出し元"},
 en:{settings:"Settings",settingsTitle:"Display settings",language:"Language",languageNote:"This changes only UI and diagnostic presentation, not compiler semantics.",close:"Close",compile:"Compile",save:"Save",io:"I/O",state:"State transitions",autoLayout:"Auto layout",systems:"Systems",callables:"Callables",types:"Types",machines:"Machines",warnings:"Warnings",source:"Glyph source",ioTitle:"I/O topology",ioNote:"Explicit system declarations are preferred; otherwise the compiler-derived call graph is shown.",stateTitle:"State transitions",stateNote:"Wildcards are expanded to concrete states and unreachable branches are removed before rendering.",transitionDetails:"Transition details",transitionNote:"The diagram shows an input-to-effect summary. Complete transition data is listed below.",reachable:"reachable state",unreachable:"unreachable state",typesSection:"Types",themeWhite:"White",themeMono:"Monochrome",genericCompileError:"Compilation failed.",genericCompileHelp:"Check brackets, types, names, branch >> syntax, and the default branch near the reported location.",executionContextLabel:"Execution context",executionContextAuto:"Auto (only when contexts agree)",executionContextMachine:"Machine only",executionContextConditional:" (conditional)",executionContextUnresolved:" (unresolved)",executionContextMultiple:" (multiple transitions)",executionContextActionless:" (no System Action)",executionContextImplicit:"implicit caller"}
};
const STANDARD_NOTES=new Set([STRINGS.ja.ioNote,STRINGS.en.ioNote,STRINGS.ja.stateNote,STRINGS.en.stateNote,"system宣言を優先し、未宣言時はコンパイラの呼出しグラフを表示する。","ワイルドカードは実状態へ展開し、到達不能分岐を除外してから描画する。"]);
const t=key=>STRINGS[locale]?.[key]??STRINGS.ja[key]??key;
window.GlyphI18n={get locale(){return locale},t};
const html=value=>String(value??"").replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch]));
function messageOf(item){const localized=item?.[`message_${locale}`];if(localized)return String(localized);const original=String(item?.message??"");if(locale==="ja"&&item?.severity==="error")return `${t("genericCompileError")} 詳細: ${original}`;return original}
function helpOf(item){const localized=item?.[`help_${locale}`];if(localized)return String(localized);return item?.severity==="error"?t("genericCompileHelp"):""}
function diagnosticMarkup(item){const code=String(item?.code??"");const help=helpOf(item);return `<div class="diagnostic" data-line="${Number(item?.line||0)}" title="${html(String(item?.message??""))}">${code?`<span class="diagnostic-code">${html(code)}</span>`:""}<span>${html(messageOf(item)||t("genericCompileError"))}</span>${help?`<span class="diagnostic-help">${html(help)}</span>`:""}</div>`}
function selectedMachine(){const machines=snapshot?.views?.state?.machines||[];const name=document.querySelector("#machine-select")?.selectedOptions?.[0]?.textContent;return machines.find(machine=>machine.name===name)||machines[0]||null}
function machineDiagnosticMarkup(item){const help=helpOf(item);return `<span class="analysis-code">${html(item?.code||"warning")}</span><span class="analysis-message">${html(messageOf(item))}${help?`<span class="analysis-help">${html(help)}</span>`:""}</span><span class="analysis-line">L${html(item?.line||"?")}</span>`}
function installOverrides(){
 if(typeof renderDiagnostics==="function"&&!renderDiagnostics.__glyphLocalized){const localized=function(){const rows=snapshot?.diagnostics||[];const markup=rows.map(diagnosticMarkup).join("");if(diagnostics.innerHTML!==markup)diagnostics.innerHTML=markup};localized.__glyphLocalized=true;renderDiagnostics=localized}
 if(typeof renderMachineDiagnostics==="function"&&!renderMachineDiagnostics.__glyphLocalized){const localized=function(machine){const rows=machine?.diagnostics||[];if(!rows.length)return "";return `<section class="analysis-panel"><div class="analysis-title">${html(t("warnings"))} · ${rows.length}</div>${rows.map(item=>`<div class="analysis-item" data-line="${Number(item?.line||0)}" title="${html(String(item?.message??""))}">${machineDiagnosticMarkup(item)}</div>`).join("")}</section>`};localized.__glyphLocalized=true;renderMachineDiagnostics=localized}
 if(typeof renderSummary==="function"&&!renderSummary.__glyphLocalized){const localized=function(){const s=snapshot?.views?.summary||{};const markup=[["systems",s.systems,""],["callables",s.callables,""],["types",s.types,""],["machines",s.machines,""],["warnings",s.state_warnings,"warn"]].map(([key,value,cls])=>`<span class="pill ${cls}">${html(t(key))}: ${value??0}</span>`).join("");const target=document.getElementById("summary");if(target&&target.innerHTML!==markup)target.innerHTML=markup};localized.__glyphLocalized=true;renderSummary=localized}
 if(typeof render==="function"&&!render.__glyphLocalized){const base=render;const localized=function(){base();queueMicrotask(apply)};localized.__glyphLocalized=true;render=localized}
}
function applyMachineDiagnostics(){
 const current=document.querySelector(".analysis-panel");
 const machine=selectedMachine();
 if(!machine||typeof renderMachineDiagnostics!=="function"){current?.remove();return}
 const markup=renderMachineDiagnostics(machine);
 if(!markup){current?.remove();return}
 const template=document.createElement("template");template.innerHTML=markup.trim();const next=template.content.firstElementChild;if(!next)return;
 if(current){if(current.outerHTML!==next.outerHTML)current.replaceWith(next)}else{document.querySelector(".machine-meta")?.insertAdjacentElement("afterend",next)}
 if(typeof bindJumps==="function")bindJumps();
}
function setText(selector,value){const element=document.querySelector(selector);if(element&&element.textContent!==value)element.textContent=value}
function apply(){
 if(document.documentElement.lang!==locale)document.documentElement.lang=locale;
 setText("#compile",t("compile"));setText("#save",t("save"));setText(".toolbar-title",t("source"));
 document.querySelectorAll(".tab").forEach(tab=>{const value=tab.dataset.tab==="state"?t("state"):t("io");if(tab.textContent!==value)tab.textContent=value});
 const stateView=document.querySelector(".tab.active")?.dataset.tab==="state";
 const title=document.querySelector(".view-controls h2");if(title){const value=stateView?t("stateTitle"):t("ioTitle");if(title.textContent!==value)title.textContent=value}
 const note=document.querySelector(".view-controls .note");if(note&&STANDARD_NOTES.has(note.textContent.trim())){const value=stateView?t("stateNote"):t("ioNote");if(note.textContent!==value)note.textContent=value}
 setText(".transition-index-title>span:first-child",t("transitionDetails"));setText(".transition-index-note",t("transitionNote"));setText(".type-section h3",t("typesSection"));
 const legend=document.querySelectorAll(".legend span");if(legend[0]&&legend[0].textContent!==t("reachable"))legend[0].textContent=t("reachable");if(legend[1]&&legend[1].textContent!==t("unreachable"))legend[1].textContent=t("unreachable");
 const theme=document.getElementById("diagram-theme");if(theme){const options=theme.options;if(options[0]&&options[0].textContent!==t("themeWhite"))options[0].textContent=t("themeWhite");if(options[1]&&options[1].textContent!==t("themeMono"))options[1].textContent=t("themeMono")}
 setText("#diagram-reset",t("autoLayout"));setText("#glyph-settings",t("settings"));setText("#glyph-settings-title",t("settingsTitle"));setText("#glyph-language-label",t("language"));setText("#glyph-language-note",t("languageNote"));setText("#glyph-settings-close",t("close"));
 if(typeof renderDiagnostics==="function")renderDiagnostics();applyMachineDiagnostics();
 document.querySelectorAll(".canvas-shell").forEach(shell=>shell.removeAttribute("title"));
 document.dispatchEvent(new CustomEvent("glyph-locale-applied",{detail:{locale}}));
}
function announceLocale(){const detail={locale};document.dispatchEvent(new CustomEvent("glyph-locale-changed",{detail}));document.dispatchEvent(new CustomEvent("glyph-locale-change",{detail}))}
function installSettings(){if(document.getElementById("glyph-settings"))return;const header=document.querySelector("header");if(!header)return;const button=document.createElement("button");button.id="glyph-settings";button.className="glyph-settings-button";button.type="button";button.textContent=t("settings");const compile=document.getElementById("compile");header.insertBefore(button,compile||null);const dialog=document.createElement("dialog");dialog.id="glyph-settings-dialog";dialog.className="glyph-settings-dialog";dialog.innerHTML=`<div class="glyph-settings-head"><h2 id="glyph-settings-title"></h2><button id="glyph-settings-close" class="glyph-settings-close" type="button"></button></div><div class="glyph-settings-body"><div class="glyph-settings-row"><label id="glyph-language-label" for="glyph-language"></label><select id="glyph-language"><option value="ja">日本語</option><option value="en">English</option></select></div><p id="glyph-language-note" class="glyph-settings-note"></p></div>`;document.body.appendChild(dialog);const select=dialog.querySelector("#glyph-language");select.value=locale;button.onclick=()=>typeof dialog.showModal==="function"?dialog.showModal():dialog.setAttribute("open","");dialog.querySelector("#glyph-settings-close").onclick=()=>typeof dialog.close==="function"?dialog.close():dialog.removeAttribute("open");dialog.addEventListener("click",event=>{if(event.target===dialog&&typeof dialog.close==="function")dialog.close()});select.onchange=()=>{locale=SUPPORTED.has(select.value)?select.value:"ja";localStorage.setItem(STORAGE_KEY,locale);installOverrides();apply();announceLocale()};apply()}
let scheduled=false;function enhance(){if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;installOverrides();installSettings();apply()})}
new MutationObserver(enhance).observe(document.body,{childList:true,subtree:true});document.addEventListener("glyph-state-transition-ir-v3-labels-ready",enhance);document.addEventListener("glyph-transition-layout-ready",enhance);enhance();
})();
</script>
"""


def enhance_diagram_locale_html(html: str) -> str:
    """Install Japanese-first UI localization with an English selector."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>").replace(
        "</body>", _SCRIPT + "\n</body>"
    )
