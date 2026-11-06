const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {JSDOM}=require(process.env.HUD_JSDOM_PATH||'jsdom');
(async()=>{
 const root=path.resolve(__dirname,'../..'),dom=new JSDOM(fs.readFileSync(path.join(root,'console/index.html'),'utf8'),{url:'http://127.0.0.1:8081/',runScripts:'outside-only'}),w=dom.window;
 const timers=[],effects=[];w.setInterval=(fn,ms)=>timers.push({fn,ms});w.Trinity={auxiliary:v=>effects.push(v),pulse(){}};
 let report={records:[{stage:'PLANNING',stage_label:'계획 분석',state:'completed',summary:'<img src=x onerror=alert(1)>',recommendations:['요구사항 확인']},{stage:'BUILDING',stage_label:'구현·보완 분석',state:'running',round:1}]};
 let job={id:'pipe-test',source:'pipeline',pipeline_stage:'BUILDING',state:'running',started_at:new Date().toISOString()};
 w.fetch=async url=>({ok:true,json:async()=>url==='/ops/roles'?{csrf:'test'}:{installed:true,job,pipeline:report}});
 w.eval(fs.readFileSync(path.join(root,'console/grok.js'),'utf8'));await new Promise(r=>setTimeout(r,20));
 const list=w.document.getElementById('grok-pipeline-steps');
 assert.equal(list.children.length,2);assert.equal(list.querySelector('img'),null);
 assert.match(list.textContent,/보완 1차/);assert.match(w.document.getElementById('grok-card-status').textContent,/구현·보완 분석/);
 const first=list.firstChild;timers.find(t=>t.ms===1000).fn();assert.equal(list.firstChild,first); // Reading results must not reset scrolling each second.
 const poll=timers.find(t=>t.ms===3000).fn;
 report={records:[...report.records.slice(0,1),{...report.records[1],state:'failed',error:'응답 형식 오류'}]};job={...job,state:'failed'};await poll();
 assert.match(w.document.getElementById('grok-pipeline-status').textContent,/일부 단계 분석 미완료/);
 assert.match(list.textContent,/응답 형식 오류/);
 w.document.body.classList.add('replaying');w.document.getElementById('grok-card-status').textContent='기록 재생 · 대기';const count=effects.length;
 await poll();assert.equal(effects.length,count);assert.equal(w.document.getElementById('grok-card-status').textContent,'기록 재생 · 대기');
 dom.window.close();console.log('Grok pipeline stages, repair evidence, safe text, stable result reading and replay isolation: PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
