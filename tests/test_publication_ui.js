const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

function setup() {
  const nodes = new Map();
  const node = () => ({ id: "", dataset: {}, children: [], events: {}, attributes: {}, textContent: "", disabled: false,
    replaceChildren(...items) { this.children = items; }, append(...items) { this.children.push(...items); },
    setAttribute(k,v){ this.attributes[k]=v; }, addEventListener(k,fn){ this.events[k]=fn; },
    querySelectorAll(){ return this.children; }
  });
  const document = { createElement: node, getElementById(id){ if(!nodes.has(id)) { const n=node(); n.id=id; nodes.set(id,n); } return nodes.get(id); } };
  const requests=[]; let scope={projectId:"book-a",chapter:1,epoch:1};
  const context=vm.createContext({document, console, URLSearchParams, fetch: async (url,opts)=>{requests.push({url,opts}); return {ok:true,json:async()=>({operation_id:"op-1",book_id:"book-a",chapter_number:1,status:"paused",current_step:"fill_chapter",source_revision:"r1",content_sha256:"h1",checks:{},evidence:{},error:null})};}, window:{fetch:null}});
  vm.runInContext(fs.readFileSync("creative_os/web/publication-panel.js","utf8")+"\nglobalThis.Panel=PublicationPanel;",context);
  const panel=new context.Panel({document, getScope:()=>scope, endpoint:"/api/publication"});
  return {nodes, panel, requests, setScope(s){scope=s; panel.clear();}};
}

test("状态卡片展示作品章节版本哈希步骤证据与错误，unknown 显示需核对",()=>{
  const e=setup(); e.panel.render({book_id:"book-a",chapter_number:1,source_revision:"r1",content_sha256:"h1",status:"unknown",current_step:"publishing",operation_id:"op-1",evidence:{check:"ok"},error:"响应丢失"});
  assert.match(e.nodes.get("publication-status").textContent,/需核对/); assert.match(e.nodes.get("publication-evidence").textContent,/check/); assert.match(e.nodes.get("publication-error").textContent,/响应丢失/);
  assert.match(e.nodes.get("publication-meta").textContent,/book-a/); assert.match(e.nodes.get("publication-meta").textContent,/h1/);
});

test("安全暂停、立即暂停、继续和核对使用明确控制请求",async()=>{
  const e=setup(); e.panel.render({book_id:"book-a",chapter_number:1,status:"publishing",operation_id:"op-1"});
  await e.nodes.get("publication-pause-safe").events.click(); await e.nodes.get("publication-pause-immediate").events.click(); await e.nodes.get("publication-continue").events.click(); await e.nodes.get("publication-reconcile").events.click();
  const bodies=e.requests.map(x=>JSON.parse(x.opts.body)); assert.deepEqual(bodies.map(x=>x.action),["pause","pause","continue","reconcile"]); assert.equal(bodies[0].mode,"safe"); assert.equal(bodies[1].mode,"immediate");
});

test("失败检查阻断且已发布或版本冲突不可重发",()=>{ const e=setup(); e.panel.render({book_id:"book-a",chapter_number:1,status:"failed",operation_id:"op-1",pause_reason:"check_failed:word_count",checks:{word_count:false}}); assert.match(e.nodes.get("publication-error").textContent,/word_count/); assert.equal(e.nodes.get("publication-run").disabled,true); e.panel.render({book_id:"book-a",chapter_number:1,status:"published",operation_id:"op-1"}); assert.equal(e.nodes.get("publication-run").disabled,true); e.panel.render({book_id:"book-a",chapter_number:1,status:"version_conflict",operation_id:"op-1"}); assert.equal(e.nodes.get("publication-run").disabled,true); });
test("后端 paused/version_conflict 也阻断运行",()=>{ const e=setup(); e.panel.render({book_id:"book-a",chapter_number:1,status:"paused",pause_reason:"version_conflict",operation_id:"op-1"}); assert.match(e.nodes.get("publication-status").textContent,/版本冲突/); assert.equal(e.nodes.get("publication-run").disabled,true); });

test("Writer 发布快照使用番茄目标并携带十二项检查",()=>{ const source=fs.readFileSync("creative_os/web/writer.js","utf8"); assert.match(source,/publicationPlatform \|\| "tomato"/); for (const name of ["source_revision_continuous","chapter_title","word_count","structure_ok","characters_consistent","settings_consistent","combat_ok","sensitive_ok","format_ok","platform_match","unpublished","hash_unchanged"]) assert.match(source,new RegExp(name)); });

test("跨书切换清理旧发布结果，控件原生可聚焦",()=>{ const e=setup(); e.panel.render({book_id:"book-a",chapter_number:1,status:"published",operation_id:"op-1"}); e.setScope({projectId:"book-b",chapter:2,epoch:2}); assert.equal(e.nodes.get("publication-status").textContent,""); assert.equal(e.nodes.get("publication-evidence").textContent,""); assert.equal(e.nodes.get("publication-run").disabled,false); assert.ok(e.nodes.get("publication-run").events.click); });

test("深链 operation_id 在首次 setScope 后保留并可查询", async()=>{ const e=setup(); e.panel.operationId="deep-op"; e.panel.setScope({projectId:"book-a",chapter:1,epoch:1}); await e.panel.refresh(); assert.match(e.requests[0].url,/operation_id=deep-op/); });

test("无 operation_id 时运行先提交快照再运行并保存新 operation_id", async()=>{ const e=setup(); const actions=[]; e.panel.getSnapshot=()=>({snapshot:{book_id:"book-a",chapter_number:1,source_revision:"r1",content:"正文"},target:{platform:"fake",chapter_title:"第1章"},work_id:"work-a"}); e.panel.fetchImpl=async(url,opts)=>{ const body=JSON.parse(opts.body); actions.push(body.action); return {ok:true,json:async()=>body.action==="submit"?{operation_id:"created-op",book_id:"book-a",chapter_number:1,status:"ready_to_publish"}:{operation_id:"created-op",book_id:"book-a",chapter_number:1,status:"published"}}; }; e.panel.setScope({projectId:"book-a",chapter:1,epoch:1}); await e.panel.control({action:"run"}); assert.deepEqual(actions,["submit","run"]); assert.equal(e.panel.operationId,"created-op"); });

test("暂停范围可明确表达全局、单书、单章和步骤", async()=>{ const e=setup(); e.panel.render({book_id:"book-a",chapter_number:1,status:"publishing",operation_id:"op-1"}); e.nodes.get("publication-pause-scope").value="global"; await e.nodes.get("publication-pause-safe").events.click(); e.nodes.get("publication-pause-scope").value="book"; await e.nodes.get("publication-pause-safe").events.click(); e.nodes.get("publication-pause-scope").value="chapter"; await e.nodes.get("publication-pause-safe").events.click(); e.nodes.get("publication-pause-scope").value="step"; e.nodes.get("publication-pause-step").value="fill_chapter"; await e.nodes.get("publication-pause-safe").events.click(); const b=e.requests.map(x=>JSON.parse(x.opts.body)); assert.deepEqual(b.map(x=>x.scope),["global","book","chapter","step"]); assert.equal(b[3].step,"fill_chapter"); });

test("创建后 run 请求必须携带 submit 返回的 operation_id", async()=>{ const e=setup(); const bodies=[]; e.panel.getSnapshot=()=>({snapshot:{book_id:"book-a",chapter_number:1,source_revision:"r1",content:"正文"},target:{platform:"fake",chapter_title:"第1章"},work_id:"work-a"}); e.panel.fetchImpl=async(url,opts)=>{ const body=JSON.parse(opts.body); bodies.push(body); return {ok:true,json:async()=>body.action==="submit"?{operation_id:"created-op",book_id:"book-a",chapter_number:1,status:"ready_to_publish"}:{operation_id:"created-op",book_id:"book-a",chapter_number:1,status:"published"}}; }; e.panel.setScope({projectId:"book-a",chapter:1,epoch:1}); await e.panel.control({action:"run"}); assert.equal(bodies[1].action,"run"); assert.equal(bodies[1].operation_id,"created-op"); });
