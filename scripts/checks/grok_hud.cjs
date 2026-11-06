// State polling must update the auxiliary HUD without changing the three mission roles.
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const nodes=new Map(),intervals=[],visuals=[],pulses=[];
 const node=id=>{if(!nodes.has(id))nodes.set(id,{dataset:{},style:{setProperty(){}},addEventListener(){},setAttribute(){},replaceChildren(){},append(){},textContent:''});return nodes.get(id);};
 let job={id:'existing-job',state:'completed'},offline=false;
 const w={Trinity:{auxiliary:v=>visuals.push(v),pulse:c=>pulses.push(c)}};
 const ctx={window:w,document:{readyState:'complete',getElementById:node,createElement:()=>({dataset:{},append(){},textContent:''})},
  fetch:async url=>{if(offline)throw Error('offline');return {ok:true,json:async()=>url==='/ops/roles'?{csrf:'test'}:{installed:true,job}};},
  setInterval:(fn,ms)=>intervals.push({fn,ms}),Date,crypto:{},Error};
 vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'../../console/grok.js'),'utf8'),ctx);
 const flush=()=>new Promise(r=>setImmediate(r));await flush();
 assert.equal(node('grok-card').dataset.state,'completed');assert.equal(pulses.length,0); // No replay on restored result.
 const poll=intervals.find(i=>i.ms===3000).fn;
 job={id:'new-job',state:'running',started_at:new Date().toISOString()};await poll();
 assert.equal(visuals.at(-1).act,1);assert.match(node('grok-card-status').textContent,/자료 조사/);
 job={...job,state:'completed'};await poll();await poll();
 assert.equal(pulses.length,1);assert.equal(visuals.at(-1).act,.3);
 job={id:'failed-job',state:'failed',error:'test error'};await poll();
 assert.equal(visuals.at(-1).color[0],1);assert.equal(node('grok-card').dataset.state,'failed');
 offline=true;await poll();
 assert.equal(node('grok-card').dataset.state,'unavailable');assert.equal(node('grok-card-status').textContent,'서버 연결 확인 필요');
 intervals.find(i=>i.ms===1000).fn();assert.equal(node('grok-card').dataset.state,'unavailable');
 offline=false;await poll();assert.equal(node('grok-card').dataset.state,'failed');
 console.log('Grok HUD live activity, terminal pulse, offline state and recovery: PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
