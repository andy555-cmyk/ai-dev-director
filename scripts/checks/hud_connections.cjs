const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {JSDOM}=require(process.env.HUD_JSDOM_PATH||'jsdom');
(async()=>{
 const root=path.resolve(__dirname,'../..'),requests=[];
 const dom=new JSDOM(fs.readFileSync(path.join(root,'console/index.html'),'utf8'),{url:'http://127.0.0.1:8081/',runScripts:'outside-only'}),w=dom.window;
 w.matchMedia=()=>({matches:false});w.Trinity={motion(){}};
 let state='connected',offline=false;
 w.fetch=async(url,options={})=>{
  requests.push({url,...options});if(offline)throw Error('서버 연결 실패');
  return {ok:true,json:async()=>url==='/ops/roles'?{csrf:'test-token'}:{
   // The first cached report is stale; boot must run a fresh, bounded CLI diagnostic.
   report:{checked_at:new Date(Date.now()-(options.method==='GET'?120000:0)).toISOString()},
   connections:{providers:['claude','codex','agy','grok'].map(name=>({name,state,reason:state==='connected'?'구독 로그인 확인':'계정 로그인이 필요합니다.',checked_at:new Date().toISOString()}))}
  }};
 };
 w.eval(fs.readFileSync(path.join(root,'console/hud.js'),'utf8'));
 const settle=()=>new Promise(r=>setTimeout(r,30));await settle();
 const badges=()=>[...w.document.querySelectorAll('.hud-connections b')];
 assert.ok(badges().every(b=>b.textContent==='연결됨'&&b.dataset.ready==='true'));
 assert.ok([...w.document.querySelectorAll('.hud-connections li small')].every(n=>n.textContent.includes('구독 로그인 확인')&&n.textContent.includes('확인')));
 assert.equal(requests.filter(r=>r.method==='POST').length,1);
 assert.equal(requests.at(-1).headers['X-Solomon-Bridge'],'test-token');
 state='disconnected';w.document.getElementById('hud-connect-refresh').click();await settle();
 assert.ok(badges().every(b=>b.textContent==='연결 안됨'&&b.dataset.state==='disconnected'));
 assert.match(w.document.querySelector('.hud-connections li small').textContent,/로그인이 필요/);
 offline=true;w.document.getElementById('hud-connect-refresh').click();await settle();
 assert.ok(badges().every(b=>b.textContent==='확인 필요'&&b.dataset.ready==='false'));
 assert.match(w.document.getElementById('hud-connect-message').textContent,/서버 연결 실패/);
 offline=false;state='connected';w.document.getElementById('hud-connect-refresh').click();await settle();
 assert.ok(badges().every(b=>b.textContent==='연결됨'));
 assert.equal(w.document.getElementById('hud-connect-refresh').disabled,false);
 assert.ok(requests.every(r=>['/ops/roles','/ops/diagnostics'].includes(r.url)));
 dom.window.close();console.log('HUD connection labels/reasons, stale refresh, protected recheck, offline clearing and recovery: PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
