// A small DOM regression test for honest status rendering and motion controls.
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const {JSDOM}=require(process.env.HUD_JSDOM_PATH||'jsdom');
(async()=>{
 const root=path.resolve(__dirname,'../..');
 const dom=new JSDOM(fs.readFileSync(path.join(root,'console/index.html'),'utf8'),{url:'http://127.0.0.1:8081/',runScripts:'outside-only'}),w=dom.window;
 w.matchMedia=()=>({matches:false});const motion=[];w.Trinity={motion:v=>motion.push(v)};
 w.fetch=async url=>({ok:true,json:async()=>url==='/ops/roles'?{csrf:'test'}:{report:null}});
 w.eval(fs.readFileSync(path.join(root,'console/hud.js'),'utf8'));
 await new Promise(r=>setTimeout(r,20));
 const status=data=>w.dispatchEvent(new w.CustomEvent('director:status',{detail:data}));
 status({result:{run_id:'test',tests:{final_gate:'MISSING'}}});
 assert.equal(w.document.getElementById('hud-final').textContent,'검증 증거 확인 필요');
 assert.equal(w.document.getElementById('hud-review').textContent,'대기');
 status({result:{tests:{canonical:'PASS',post:{passed:4,total:5},post_passed:false,reviewer:'fail',final_gate:'FAIL'}}});
 assert.equal(w.document.getElementById('hud-tests').dataset.state,'fail');
 assert.equal(w.document.getElementById('hud-final').textContent,'보완 후 재검증 필요');
 status({result:{tests:{canonical:'PASS',post:{passed:5,total:5},post_passed:true,reviewer:'pass',final_gate:'PASS'}}});
 assert.equal(w.document.getElementById('hud-final').textContent,'최종 검증 통과');
 const button=w.document.getElementById('hud-motion');button.click();assert.equal(button.getAttribute('aria-pressed'),'false');assert.equal(motion.at(-1),false);
 assert.ok([...w.document.querySelectorAll('.hud-connections b')].every(n=>n.textContent==='확인 필요'));
 dom.window.close();console.log('HUD evidence, unknown connections and motion controls: PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
