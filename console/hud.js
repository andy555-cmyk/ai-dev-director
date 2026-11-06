'use strict';
// HUD presentation consumes existing status data; it never invents successful checks.
(()=>{
 const $=id=>document.getElementById(id);
 function badge(id,text,state){const n=$(id);if(n){n.textContent=text;n.dataset.state=state||'unknown';}}
 function verification(status){
  if(document.body.classList.contains('replaying')){for(const id of ['hud-scope','hud-tests','hud-review'])badge(id,'기록 재생 중');$('hud-final').textContent='실제 검증 결과는 작업실에서 확인';return;}
  const result=status.result||{},tests=result.tests||{};
  badge('hud-scope',tests.canonical==='PASS'?'확인 완료':tests.canonical==='FAIL'?'범위 확인 실패':'확인 전',tests.canonical==='PASS'?'pass':tests.canonical==='FAIL'?'fail':'unknown');
  const count=tests.post;
  if(count&&Number(count.total)>0)badge('hud-tests',count.passed+'/'+count.total+' 통과',tests.post_passed===true?'pass':tests.post_passed===false?'fail':'unknown');
  else badge('hud-tests',tests.post_passed===true?'검증 명령 통과':tests.post_passed===false?'검증 실패':'실행 전',tests.post_passed===true?'pass':tests.post_passed===false?'fail':'unknown');
  badge('hud-review',tests.reviewer==='pass'?'검수 통과':tests.reviewer==='fail'?'보완 필요':'대기',tests.reviewer==='pass'?'pass':tests.reviewer==='fail'?'fail':'unknown');
  const final=$('hud-final'),gate=tests.final_gate;
  final.textContent=gate==='PASS'?'최종 검증 통과':gate==='FAIL'?'보완 후 재검증 필요':result.run_id?'검증 증거 확인 필요':'최종 판단 전';
  final.dataset.state=gate==='PASS'?'pass':gate==='FAIL'?'fail':'unknown';
 }
 let connectionBusy=false,connectionToken='';
 function paintConnections(view){
  for(const li of document.querySelectorAll('.hud-connections [data-ai]')){
   const row=view?.providers?.find(p=>p.name===li.dataset.ai),b=li.querySelector('b'),detail=li.querySelector('small');
   const state=['connected','disconnected'].includes(row?.state)?row.state:'unknown';
   b.textContent={connected:'연결됨',disconnected:'연결 안됨',unknown:'확인 필요'}[state];
   b.dataset.state=state;b.dataset.ready=String(state==='connected');
   let reason=row?.reason||'아직 연결을 점검하지 않았습니다.';
   const time=new Date(row?.checked_at||'');
   if(Number.isFinite(time.getTime()))reason+=' · 확인 '+time.toLocaleTimeString('ko-KR',{hour12:false});
   detail.textContent=reason;b.title=reason;
  }
 }
 async function connections(force=false){
  if(connectionBusy)return;connectionBusy=true;
  const button=$('hud-connect-refresh'),message=$('hud-connect-message');
  button.disabled=true;button.textContent='점검 중…';
  async function request(method){
   const res=await fetch('/ops/diagnostics',{method,headers:{'X-Solomon-Bridge':connectionToken},cache:'no-store'});
   const out=await res.json();if(!res.ok)throw Error(out.error||'연결 상태를 불러오지 못했습니다.');return out;
  }
  try{
   if(!connectionToken){const roles=await fetch('/ops/roles',{cache:'no-store'});if(!roles.ok)throw Error('앱 서버에 연결하지 못했습니다.');connectionToken=(await roles.json()).csrf;}
   if(!connectionToken)throw Error('앱 연결을 다시 불러오세요.');
   let out=await request(force?'POST':'GET');
   const checked=new Date(out.report?.checked_at||'').getTime(),age=Date.now()-checked;
   if(!force&&(!Number.isFinite(checked)||age>60000||age< -30000))out=await request('POST');
   paintConnections(out.connections);
   message.textContent='CLI 실행·로그인 또는 최근 10분 이내 실제 응답 기준 · 30초마다 갱신';
  }catch(e){
   paintConnections({providers:[...document.querySelectorAll('.hud-connections [data-ai]')].map(li=>({name:li.dataset.ai,state:'unknown',reason:'점검하지 못했습니다. 연결 상태를 다시 확인하세요.'}))});
   message.textContent=e.message;
  }finally{connectionBusy=false;button.disabled=false;button.textContent='연결 상태 다시 점검';}
 }
 function start(){
  const button=$('hud-motion');
  let motion=!window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  try{const saved=sessionStorage.getItem('hud-motion');if(saved!==null)motion=saved==='on';}catch(e){}
  function apply(){window.Trinity?.motion(motion);button.textContent=motion?'모션 켜짐':'모션 꺼짐';button.setAttribute('aria-pressed',String(motion));document.body.classList.toggle('motion-off',!motion);}
  button.onclick=()=>{motion=!motion;try{sessionStorage.setItem('hud-motion',motion?'on':'off');}catch(e){}apply();};
  window.addEventListener('director:status',e=>verification(e.detail||{}));
  $('hud-evidence').onclick=e=>{e.preventDefault();$('tab-workshop').click();};
  $('hud-connect-refresh').onclick=()=>connections(true);
  apply();connections();setInterval(()=>connections(),30000);
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
