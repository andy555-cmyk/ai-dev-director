'use strict';
(()=>{
 const $=id=>document.getElementById(id),running=new Set(['queued','running','cancelling']);
 const labels={queued:'분석 준비 중',running:'자료 조사·분석 중',cancelling:'취소 중',completed:'분석 완료',failed:'연결·분석 확인 필요',cancelled:'분석 취소됨',interrupted:'분석 중단됨',unavailable:'연동 분석 미완료'};
 const phases={PLANNING:'계획 분석',BUILDING:'구현·보완 분석',REVIEWING:'테스트·검수 분석',DECIDING:'최종 판단 보조'};
 const visuals={idle:{act:.12,color:[.79,.84,.96]},queued:{act:.6,color:[.79,.84,.96]},running:{act:1,color:[.79,.84,.96]},cancelling:{act:.45,color:[1,.78,.48]},completed:{act:.3,color:[.69,1,.86]},failed:{act:.25,color:[1,.43,.5]},cancelled:{act:.12,color:[1,.78,.48]},interrupted:{act:.12,color:[1,.78,.48]},unavailable:{act:.1,color:[1,.43,.5]}};
 let token='',data=null,sending=false,checking=false,lastJob=null,pipelinePainted='';
 function hud(state,job){
  const visual=visuals[state]||visuals.idle,card=$('grok-card');
  if(!document.body?.classList.contains('replaying'))window.Trinity?.auxiliary(visual);
  card.style.setProperty('--grok-color','rgb('+visual.color.map(v=>Math.round(v*255)).join(',')+')');
  card.dataset.state=state;
  if(job){
   if(lastJob?.id===job.id&&running.has(lastJob.state)&&!running.has(job.state))window.Trinity?.pulse(visual.color);
   lastJob={id:job.id,state:job.state};
  }
 }
 async function auth(){if(!token){const r=await fetch('/ops/roles',{cache:'no-store'});if(!r.ok)throw Error('앱 서버에 연결할 수 없습니다.');token=(await r.json()).csrf;}if(!token)throw Error('앱 서버에 연결할 수 없습니다.');return token;}
 async function api(path,body){const headers={'X-Solomon-Bridge':await auth()},options={headers,cache:'no-store'};if(body!==undefined){options.method='POST';if(body!==null){headers['Content-Type']='application/json';options.body=JSON.stringify(body);}else options.body='';}const r=await fetch(path,options),out=await r.json();if(!r.ok)throw Error(out.error||'Grok에 연결하지 못했습니다.');return out;}
 function answer(text){const root=$('grok-answer');root.replaceChildren();let last=0;for(const match of String(text).matchAll(/https?:\/\/[^\s<>\]\)]+/g)){root.append(document.createTextNode(text.slice(last,match.index)));const a=document.createElement('a');a.textContent=match[0];a.href=match[0];a.target='_blank';a.rel='noopener noreferrer';root.append(a);last=match.index+match[0].length;}root.append(document.createTextNode(text.slice(last)));}
 function paint(){
  if(!data)return;const job=data.job,active=job&&running.has(job.state),card=$('grok-card');
  hud(job?.state||'idle',job);
  let status=job?labels[job.state]||'상태 확인 필요':data.installed?'CLI 설치됨 · 로그인 확인 필요':'CLI 설치 필요';
  if(job?.source==='pipeline')status=(phases[job.pipeline_stage]||'프로세스 연동')+' · '+(labels[job.state]||'상태 확인 필요');
  if(job?.state==='running')status+=' · '+Math.max(0,Math.floor((Date.now()-new Date(job.started_at).getTime())/1000))+'초';
  if(!document.body?.classList.contains('replaying'))$('grok-card-status').textContent=status;
  $('grok-submit').disabled=sending||active||!data.installed;$('grok-submit').textContent=active?'분석 중…':'분석 요청';
  $('grok-cancel').hidden=!active;$('grok-cancel').disabled=job?.state==='cancelling';
  $('grok-login').disabled=!data.installed;
  $('grok-job-state').textContent=job?(labels[job.state]||'상태 확인 필요'):'아직 요청 없음';
  $('grok-saved-question').textContent=job?.question||'';
  if(job?.answer)answer(job.answer);
  else $('grok-answer').textContent=job?.error||(active?'Grok이 웹 자료를 조사하고 있습니다. 창을 닫아도 분석은 계속됩니다.':'질문을 보내면 여기에 결과와 출처가 표시됩니다.');
  const pipeline=data.pipeline,root=$('grok-pipeline-steps');
  const pipelineKey=JSON.stringify(pipeline||null);
  if(root&&pipelineKey!==pipelinePainted){
   pipelinePainted=pipelineKey;
   root.replaceChildren();
   if(pipeline?.records?.length){
    const records=pipeline.records,done=records.filter(r=>r.state==='completed').length,bad=records.some(r=>!running.has(r.state)&&r.state!=='completed');
    $('grok-pipeline-status').textContent=(bad?'일부 단계 분석 미완료 · ':'단계 분석 연동 · ')+done+'/'+records.length+' 완료 · 분석 의견은 실제 테스트·독립 검수와 구분됩니다.';
    for(const record of records.slice(-12)){
     const li=document.createElement('li'),title=document.createElement('strong'),text=document.createElement('p');
     li.dataset.state=record.state;title.textContent=(record.stage_label||phases[record.stage]||record.stage)+(record.round?' · 보완 '+record.round+'차':'')+' — '+(labels[record.state]||'확인 필요');
     text.textContent=record.summary||record.error||'Grok이 제공된 요구사항과 검증 요약을 분석하고 있습니다.';li.append(title,text);
     for(const [key,label] of [['findings','관찰'],['recommendations','보완 제안'],['evidence_gaps','확인할 증거']])for(const line of record[key]||[]){const p=document.createElement('p');p.textContent=label+': '+line;li.append(p);}
     root.append(li);
    }
   }else{
    for(const label of Object.values(phases)){
     const li=document.createElement('li'),title=document.createElement('strong');
     li.dataset.state='waiting';title.textContent=label+' — 다음 작업 대기';li.append(title);root.append(li);
    }
   }
  }
 }
 async function poll(){try{data=await api('/ops/grok');paint();}catch(e){hud('unavailable');data=null;$('grok-card-status').textContent='서버 연결 확인 필요';if($('grok-panel').open)$('grok-message').textContent=e.message;}}
 async function send(e){e.preventDefault();if(sending||data?.job&&running.has(data.job.state))return;const question=$('grok-question').value.trim();if(question.length<5){$('grok-message').textContent='질문을 5자 이상 입력하세요.';return;}sending=true;paint();$('grok-message').textContent='분석 요청을 보내고 있습니다…';try{const out=await api('/ops/grok/research',{question,request_id:crypto.randomUUID()});if(out.status!=='accepted')throw Error('요청 접수를 확인하지 못했습니다.');$('grok-message').textContent='분석을 시작했습니다. 결과는 아래에 표시됩니다.';await poll();}catch(error){$('grok-message').textContent=error.message;}finally{sending=false;paint();}}
 function start(){
  const dialog=$('grok-panel'),card=$('grok-card');
  card.onclick=()=>{dialog.showModal();card.setAttribute('aria-expanded','true');poll();$('grok-question').focus();};
  $('grok-close').onclick=()=>dialog.close();dialog.addEventListener('close',()=>card.setAttribute('aria-expanded','false'));
  dialog.addEventListener('keydown',e=>{if(e.key==='Escape')e.stopPropagation();});
  $('grok-form').addEventListener('submit',send);
  $('grok-login').onclick=async()=>{const button=$('grok-login');button.disabled=true;try{const result=await api('/ops/auth/login',{provider:'grok'});$('grok-message').textContent=result.message;}catch(e){$('grok-message').textContent=e.message;}finally{button.disabled=!data?.installed;}};
  $('grok-check').onclick=async()=>{if(checking)return;checking=true;$('grok-check').disabled=true;try{const result=await api('/ops/diagnostics',null);const p=result.report?.providers?.find(row=>row.name==='grok');$('grok-message').textContent=p?.installed?'Grok CLI '+(p.version||'버전 확인 불가')+' 설치 확인 · 로그인은 CLI에서 확인하세요.':'Grok CLI 설치를 확인하세요.';await poll();}catch(e){$('grok-message').textContent=e.message;}finally{checking=false;$('grok-check').disabled=false;}};
  $('grok-cancel').onclick=async()=>{if(!data?.job)return;try{await api('/ops/grok/cancel',{request_id:data.job.id});$('grok-message').textContent='분석 취소를 요청했습니다.';await poll();}catch(e){$('grok-message').textContent=e.message;}};
  poll();setInterval(poll,3000);setInterval(paint,1000);
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start);else start();
})();
