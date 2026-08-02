import fs from "node:fs/promises";
import { spawn } from "node:child_process";
import { chromium } from "playwright";

const port = 8899;
const url = `http://127.0.0.1:${port}`;
const logs = [];
const child = spawn("python3", ["glyph.py", "examples/state_diagrams/conveyor_control.glyph"], {
  env: {...process.env, GLYPH_DIAGRAM_PORT:String(port), GLYPH_DIAGRAM_NO_BROWSER:"1", PYTHONUNBUFFERED:"1"},
  stdio:["ignore","pipe","pipe"],
});
child.stdout.on("data", chunk=>logs.push(chunk.toString()));
child.stderr.on("data", chunk=>logs.push(chunk.toString()));
async function stop(){if(child.exitCode!==null)return;child.kill("SIGTERM");await Promise.race([new Promise(r=>child.once("exit",r)),new Promise(r=>setTimeout(r,1200))]);if(child.exitCode===null)child.kill("SIGKILL")}
for(let i=0;i<160;i+=1){
  try{const response=await fetch(`${url}/api/state`,{cache:"no-store"});if(response.ok&&(await response.json()).status==="ready")break}catch{}
  if(i===159)throw new Error(logs.join(""));
  await new Promise(r=>setTimeout(r,100));
}
const browser=await chromium.launch({headless:true});
try{
  const page=await browser.newPage({viewport:{width:1500,height:900}});
  await page.goto(url,{waitUntil:"domcontentloaded"});
  await page.waitForFunction(()=>document.querySelector("#status")?.textContent==="ready");
  await page.click('button[data-tab="state"]');
  await page.waitForFunction(()=>{
    const stage=document.querySelector(".state-node")?.closest(".graph-stage");
    return stage?.dataset.transitionPublicationReady==="true"&&stage?.dataset.stateDiagramWorkspaceGeometryReady==="true"&&stage?.dataset.initialRouteReady==="true";
  });
  await page.click("#diagram-fit");
  await page.waitForTimeout(200);
  await page.click("#diagram-view-reset");
  await page.waitForFunction(()=>document.querySelector(".graph-stage")?.dataset.viewportScale==="1");
  await page.click("#diagram-zoom-out");
  await page.click("#diagram-zoom-out");
  await page.waitForFunction(()=>document.querySelector(".graph-stage")?.dataset.viewportScale==="0.8");
  await page.waitForTimeout(200);
  const audit=await page.evaluate(()=>{
    const nodes=[...document.querySelectorAll(".state-node")];
    const node=nodes[0];
    const rect=node.getBoundingClientRect();
    const x=(rect.left+rect.right)/2,y=(rect.top+rect.bottom)/2;
    const describe=element=>{
      const style=getComputedStyle(element);
      const value=element.getBoundingClientRect();
      return{
        tag:element.tagName,
        class:element.className?.baseVal||element.className||"",
        id:element.id||"",
        text:element.textContent?.trim()?.slice(0,60)||"",
        pointerEvents:style.pointerEvents,
        visibility:style.visibility,
        display:style.display,
        opacity:style.opacity,
        zIndex:style.zIndex,
        position:style.position,
        transform:style.transform,
        rect:{left:value.left,top:value.top,right:value.right,bottom:value.bottom,width:value.width,height:value.height},
      };
    };
    return{
      point:{x,y},
      node:describe(node),
      nodeInlineStyle:node.getAttribute("style"),
      nodeParent:describe(node.parentElement),
      stack:document.elementsFromPoint(x,y).map(describe),
      stageCount:document.querySelectorAll(".graph-stage").length,
      shellCount:document.querySelectorAll(".canvas-shell").length,
      nodeCount:nodes.length,
      stages:[...document.querySelectorAll(".graph-stage")].map((stage,index)=>({index,...describe(stage),containsNode:stage.contains(node),html:stage.outerHTML.slice(0,160)})),
      nodesAtPoint:nodes.filter(item=>{const r=item.getBoundingClientRect();return x>=r.left&&x<=r.right&&y>=r.top&&y<=r.bottom}).map(describe),
      bodyAtPoint:document.elementFromPoint(x,y)?.outerHTML?.slice(0,220)||"",
    };
  });
  console.log(JSON.stringify(audit,null,2));
  await fs.mkdir("build/state-node-hit-test",{recursive:true});
  await fs.writeFile("build/state-node-hit-test/audit.json",JSON.stringify(audit,null,2));
  await page.screenshot({path:"build/state-node-hit-test/screenshot.png",fullPage:true});
}finally{await browser.close();await stop()}
