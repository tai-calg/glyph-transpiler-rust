from __future__ import annotations


_MARKER = "glyph-workspace-layout-v1"

_STYLE = r"""
<style id="glyph-workspace-layout-v1-style">
html,body,.app{width:100%;height:100%;min-height:0;overflow:hidden!important}
body{overscroll-behavior:none}
.app{height:100dvh;min-height:0}
header{flex:0 0 auto;height:auto!important;min-height:58px;max-width:100%;flex-wrap:wrap;align-content:center;row-gap:7px;padding:8px 14px;overflow:hidden}
header .brand{flex:0 0 auto;min-width:0}
header .path{flex:1 1 220px;min-width:80px}
header .status,header button{flex:0 0 auto}
header button{min-height:34px;padding:6px 10px;white-space:nowrap}
main{flex:1 1 0;height:0;min-height:0;max-width:100%;overflow:hidden;overscroll-behavior:none}
.editor-pane,.viewer{height:100%;min-height:0;overflow:hidden;contain:layout paint}
.editor-pane{display:flex!important;flex-direction:column}
.toolbar,.viewer-head{flex:0 0 auto}
.editor-wrap{flex:1 1 0;min-height:0;overflow:hidden}
.editor{min-height:0;max-height:100%;overflow:auto!important;overscroll-behavior:contain;scrollbar-gutter:stable}
.lines{height:100%;overflow:hidden}
.diagnostics{flex:0 1 auto;overscroll-behavior:contain;scrollbar-gutter:stable}
.viewer-head{height:auto!important;min-height:62px;max-width:100%;flex-wrap:wrap;align-content:center;gap:8px;padding:8px 15px;overflow:hidden}
.tabs{display:flex;min-width:0;max-width:100%;flex-wrap:wrap;gap:5px}
.tabs .tab{min-height:34px;padding:6px 10px;white-space:nowrap}
.summary{margin-left:auto;min-width:0;max-width:100%;justify-content:flex-end}
.diagram-tools{margin-left:auto!important;min-width:0;max-width:100%;justify-content:flex-end;overflow:visible!important}
.diagram-tools select,.diagram-tools button{flex:0 1 auto;max-width:100%;min-height:32px;height:auto!important;padding:5px 8px!important;white-space:nowrap}
.view-body{flex:1 1 0;min-height:0;overflow:auto!important;overscroll-behavior:contain;scrollbar-gutter:stable}
.view-controls{max-width:100%;flex-wrap:wrap;align-items:flex-start}
.view-controls>div{min-width:0;flex:1 1 260px}
.view-controls select{flex:0 1 280px;margin-left:auto!important;min-width:min(210px,100%)!important;max-width:100%}
.canvas-shell{max-width:100%;overscroll-behavior:contain;scrollbar-gutter:stable}
@media(max-width:1280px){
  header{gap:8px}.brand small{display:none}.summary{display:none!important}
  .viewer-head{gap:6px}.diagram-tools{width:100%;margin-left:0!important;justify-content:flex-start}
}
@media(max-width:1040px){
  :root{--editor:40%}
  main{grid-template-columns:minmax(300px,var(--editor)) 5px minmax(0,1fr)!important}
  .viewer-head{align-items:flex-start}.tabs{width:100%}
  .diagram-tools{gap:5px!important}.diagram-tools .separator{display:none}
}
@media(max-width:900px){
  main{grid-template-columns:minmax(270px,42%) 5px minmax(0,1fr)!important}
  .editor-pane{display:flex!important}.splitter{display:block!important}
  header .path{display:none}
}
</style>
"""


def enhance_workspace_layout_html(html: str) -> str:
    """Keep app chrome fixed while editor and preview scroll independently."""

    if _MARKER in html:
        return html
    return html.replace("</head>", _STYLE + "\n</head>")
