from __future__ import annotations


_MARKER = "glyph-transition-layout-transaction-bootstrap-v1"

_SCRIPT = r"""
<script id="glyph-transition-layout-transaction-bootstrap-v1-script">
(()=>{
const MARKER="glyph-transition-layout-transaction-bootstrap-v1";
const transitionScript=name=>`glyph-transition-${name}-v1-script`;
const managed=new Set([
  transitionScript("io-clusters"),
  transitionScript("io-collision-solver"),
  transitionScript("label-readability"),
  transitionScript("readable-layout"),
  transitionScript("semantic-role-lines"),
  transitionScript("dense-canvas-dimensions"),
  transitionScript("node-layout-guard"),
  transitionScript("label-drag-guard"),
]);
const ioClusterScript=transitionScript("io-clusters");
const control={marker:MARKER,ownsScheduling:false,managedScripts:managed};
const nativeAdd=EventTarget.prototype.addEventListener;
const nativeSetTimeout=window.setTimeout.bind(window);
const NativeMutationObserver=window.MutationObserver;

function owner(){return document.currentScript?.id||""}
function allowInteractive(ownerId,type,event){
  if(ownerId!==ioClusterScript)return false;
  if(!["pointerdown","pointermove","pointerup","click","dblclick","mouseenter","mouseleave"].includes(type))return false;
  return Boolean(event?.target?.closest?.(".transition-io-cluster"));
}

EventTarget.prototype.addEventListener=function(type,listener,options){
  const ownerId=owner();
  if(!managed.has(ownerId)||typeof listener!=="function")return nativeAdd.call(this,type,listener,options);
  const wrapped=function(event){
    if(control.ownsScheduling&&!allowInteractive(ownerId,type,event))return;
    return listener.call(this,event);
  };
  return nativeAdd.call(this,type,wrapped,options);
};

window.setTimeout=function(callback,delay,...args){
  const ownerId=owner();
  if(!managed.has(ownerId)||typeof callback!=="function")return nativeSetTimeout(callback,delay,...args);
  return nativeSetTimeout((...values)=>{
    if(control.ownsScheduling)return;
    callback(...values);
  },delay,...args);
};

window.MutationObserver=class GlyphManagedMutationObserver extends NativeMutationObserver{
  constructor(callback){
    const ownerId=owner();
    super((records,observer)=>{
      if(control.ownsScheduling&&managed.has(ownerId))return;
      callback(records,observer);
    });
  }
};

window.glyphTransitionLegacyControl=control;
})();
</script>
"""


def enhance_transition_layout_transaction_bootstrap_html(html: str) -> str:
    """Install scheduling ownership before legacy transition layout layers load."""

    if _MARKER in html:
        return html
    return html.replace("</body>", _SCRIPT + "\n</body>")
