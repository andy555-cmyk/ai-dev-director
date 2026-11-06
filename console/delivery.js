/* v4 앱 만들기: 한 줄 → 기획 승인 → 만들기·화면 검수 → 중간 화면 승인 → 출시 승인 */
(()=>{
 const $=id=>document.getElementById(id);
 const STEPS=[['PLANNING','기획'],['WAIT_PLAN_APPROVAL','기획 승인'],['BUILDING','만들기·화면 검수'],['WAIT_SCREEN_APPROVAL','중간 화면 승인'],['PACKAGING','출시 묶음'],['WAIT_RELEASE_APPROVAL','출시 승인'],['READY','완료']];
 const LABEL={PLANNING:'기획서 쓰는 중',WAIT_PLAN_APPROVAL:'기획 승인 기다림',BUILDING:'만들고 화면 확인하는 중',WAIT_SCREEN_APPROVAL:'중간 화면 승인 기다림',PACKAGING:'출시 묶음 만드는 중',WAIT_RELEASE_APPROVAL:'출시 승인 기다림',READY:'완료',STOPPED:'멈춤',FAILED:'막힘'};
 const TASK={todo:'대기',building:'만드는 중',done:'완료',blocked:'막힘'};
 const DOC={prd:'요구사항',screens:'화면',data:'데이터',design:'디자인'};
 let token='',current='',timer=0,busy=false;
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 async function auth(){if(!token){const r=await fetch('/ops/roles',{cache:'no-store'});token=(await r.json()).csrf||'';}return token;}
 async function api(path,body){const o={cache:'no-store',headers:{'X-Solomon-Bridge':await auth()}};if(body!==undefined){o.method='POST';o.headers['Content-Type']='application/json';o.body=JSON.stringify(body);}const r=await fetch(path,o),out=await r.json();if(!r.ok)throw Error(out.error||'요청이 실패했습니다');return out;}
 function build(){
  const dlg=document.createElement('dialog');dlg.id='dlv-panel';dlg.setAttribute('aria-labelledby','dlv-title');
  dlg.innerHTML=`<header class="dlv-head"><div><p class="dlv-eyebrow">ONE LINE → APP</p><h2 id="dlv-title">앱 만들기</h2></div><button type="button" id="dlv-close">닫기</button></header>
  <div class="dlv-body"><aside class="dlv-side">
   <form id="dlv-form"><label for="dlv-goal">만들 앱 한 줄</label><textarea id="dlv-goal" rows="3" maxlength="2000" minlength="5" required placeholder="조기축구회 출석과 회비를 관리하는 웹앱"></textarea>
   <label for="dlv-folder">만들 폴더</label><div class="dlv-folder"><input id="dlv-folder" placeholder="/Users/나/dev/새앱" required><button type="button" id="dlv-pick">고르기</button></div>
   <button type="submit" id="dlv-start" class="dlv-primary">기획 시작</button><p class="dlv-hint">대표 확인은 세 번뿐 · 기획, 중간 화면, 출시</p></form>
   <h3 class="dlv-sub">만든 앱</h3><ul id="dlv-list"></ul></aside>
   <section class="dlv-main" id="dlv-main" aria-live="polite"><p class="dlv-empty">만들 앱 한 줄을 적으면 기획부터 시작합니다</p></section></div>
  <p id="dlv-msg" role="status"></p>`;
  document.body.appendChild(dlg);
  $('dlv-close').onclick=()=>dlg.close();
  dlg.addEventListener('close',()=>{clearTimeout(timer);timer=0;});
  $('dlv-pick').onclick=async()=>{try{const r=await api('/ops/pick-folder',null);if(r.path)$('dlv-folder').value=r.path;}catch(e){msg(e.message);}};
  $('dlv-form').onsubmit=async e=>{e.preventDefault();if(busy)return;busy=true;$('dlv-start').disabled=true;try{const d=await api('/ops/deliveries',{goal:$('dlv-goal').value,project_path:$('dlv-folder').value});current=d.delivery_id;$('dlv-goal').value='';msg('기획을 시작했습니다');await refresh();}catch(err){msg(err.message);}finally{busy=false;$('dlv-start').disabled=false;}};
  return dlg;
 }
 function msg(t){$('dlv-msg').textContent=t||'';}
 function shots(urls,cls){return (urls||[]).filter(Boolean).map(u=>`<a href="${esc(u)}" target="_blank" rel="noopener"><img class="${cls||'dlv-shot'}" src="${esc(u)}" alt="앱 화면 캡처" loading="lazy"></a>`).join('');}
 function steps(phase){let reached=STEPS.findIndex(s=>s[0]===phase);if(phase==='READY')reached=STEPS.length-1;return `<ol class="dlv-steps">${STEPS.map((s,i)=>`<li class="${i<reached?'done':i===reached?'now':''}">${s[1]}</li>`).join('')}</ol>`;}
 function actions(d){
  const fb=`<div class="dlv-fb"><label for="dlv-fbtext">고칠 점</label><textarea id="dlv-fbtext" rows="2" maxlength="1000" placeholder="예: 첫 화면에 이번 주 경기 출석부터 보이게"></textarea><button type="button" data-act="feedback">의견 보내기</button></div>`;
  if(d.phase==='WAIT_PLAN_APPROVAL')return `<div class="dlv-act"><button type="button" class="dlv-primary" data-act="approve" data-what="plan">이 기획으로 만들기</button></div>${fb}`;
  if(d.phase==='WAIT_SCREEN_APPROVAL')return `<div class="dlv-act"><button type="button" class="dlv-primary" data-act="approve" data-what="screen">화면 좋아요, 계속</button></div>${fb}`;
  if(d.phase==='WAIT_RELEASE_APPROVAL')return `<div class="dlv-act"><button type="button" class="dlv-primary" data-act="approve" data-what="release">출시 승인</button><span class="dlv-note">파일 ${esc(d.release?.files)}개 · ${esc(d.release?.zip)}</span></div>${fb}`;
  if(d.phase==='STOPPED'||d.phase==='FAILED')return `<div class="dlv-act"><button type="button" class="dlv-primary" data-act="resume">이어서 하기</button></div>`;
  if(d.phase==='READY'){const ex=d.release?.exported||{};return `<div class="dlv-act"><span class="dlv-note">${ex.copied?`프로젝트 폴더에 ${esc(ex.files)}개 파일을 넣었습니다`:esc(ex.why||'')}</span><span class="dlv-note">${esc(d.release?.zip)}</span></div>`;}
  return `<div class="dlv-act"><span class="dlv-run"><i></i>${esc(LABEL[d.phase]||d.phase)}</span><button type="button" data-act="stop">멈추기</button></div>`;
 }
 function detail(d){
  const wf=Object.entries(d.wireframes||{}).map(([k,v])=>`<figure>${shots(v.slice(0,1),'dlv-wire')}<figcaption>${esc((d.screen_names||{})[k]||k)}</figcaption></figure>`).join('');
  const docs=Object.entries(d.plan_docs||{}).map(([k,v])=>`<details><summary>${esc(DOC[k]||k)}</summary><pre>${esc(v)}</pre></details>`).join('');
  const tasks=(d.tasks||[]).map(t=>`<li class="t-${esc(t.status)}"><b>${esc(t.id)}</b><span>${esc(t.title)}</span><em>${esc(TASK[t.status]||t.status)}${t.screen_passed===false?' · 화면 다시':''}</em>${t.shots?.length?`<div class="dlv-thumbs">${shots(t.shots)}</div>`:''}</li>`).join('');
  const ev=(d.events||[]).slice(-14).reverse().map(e=>`<li><time>${esc((e.at||'').slice(11,16))}</time>${esc(e.text)}</li>`).join('');
  const showWire=['WAIT_PLAN_APPROVAL','PLANNING'].includes(d.phase)||!(d.latest_shots||[]).length;
  return `<div class="dlv-top"><h3>${esc(d.title||d.goal)}</h3><span class="dlv-phase p-${esc(d.phase)}">${esc(LABEL[d.phase]||d.phase)}</span></div>
   ${steps(d.phase)}${d.summary?`<p class="dlv-summary">${esc(d.summary)}</p>`:''}${d.reason?`<p class="dlv-reason">${esc(d.reason)}</p>`:''}
   ${actions(d)}
   ${showWire&&wf?`<h4>화면 설계</h4><div class="dlv-wires">${wf}</div>`:''}
   ${!showWire?`<h4>지금 화면</h4><div class="dlv-thumbs big">${shots(d.latest_shots)}</div>`:''}
   ${docs?`<h4>기획 문서</h4><div class="dlv-docs">${docs}</div>`:''}
   ${tasks?`<h4>작업 ${d.progress.done}/${d.progress.total}</h4><ol class="dlv-tasks">${tasks}</ol>`:''}
   ${ev?`<h4>진행 기록</h4><ul class="dlv-events">${ev}</ul>`:''}`;
 }
 async function act(btn){
  if(busy||!current)return;busy=true;btn.disabled=true;
  try{const a=btn.dataset.act,base='/ops/deliveries/'+encodeURIComponent(current)+'/';let d;
   if(a==='approve'){const now=await api(base.slice(0,-1));d=await api(base+'approve',{what:btn.dataset.what,plan_hash:now.plan_hash});}
   else if(a==='feedback'){const t=$('dlv-fbtext').value.trim();if(!t)throw Error('고칠 점을 적어 주세요');d=await api(base+'feedback',{text:t});}
   else d=await api(base+a,{});
   msg({approve:'승인했습니다',feedback:'의견을 반영해 다시 작업합니다',stop:'멈췄습니다',resume:'이어서 진행합니다'}[a]);await refresh();}
  catch(e){msg(e.message);}finally{busy=false;btn.disabled=false;}
 }
 async function refresh(){
  clearTimeout(timer);
  try{const list=(await api('/ops/deliveries')).deliveries||[];if(!current&&list[0])current=list[0].delivery_id;
   $('dlv-list').innerHTML=list.map(d=>`<li><button type="button" data-id="${esc(d.delivery_id)}" class="${d.delivery_id===current?'on':''}"><b>${esc(d.title||d.goal)}</b><span>${esc(LABEL[d.phase]||d.phase)} · ${d.progress.done}/${d.progress.total}</span></button></li>`).join('')||'<li class="dlv-none">아직 없음</li>';
   if(current){const open=[...document.querySelectorAll('#dlv-main details[open]')].map(x=>x.querySelector('summary').textContent);const fb=$('dlv-fbtext')?.value||'';const d=await api('/ops/deliveries/'+encodeURIComponent(current));$('dlv-main').innerHTML=detail(d);document.querySelector('#dlv-panel .dlv-body').classList.add('has-current');
    document.querySelectorAll('#dlv-main details').forEach(x=>{if(open.includes(x.querySelector('summary').textContent))x.open=true;});if($('dlv-fbtext'))$('dlv-fbtext').value=fb;}
  }catch(e){msg(e.message);}
  if($('dlv-panel').open)timer=setTimeout(refresh,4000);
 }
 document.addEventListener('click',e=>{const b=e.target.closest('#dlv-list button[data-id]');if(b){current=b.dataset.id;refresh();return;}const a=e.target.closest('#dlv-main button[data-act]');if(a)act(a);});
 function init(){const dlg=build();const nav=document.querySelector('.top-actions');const btn=document.createElement('button');btn.type='button';btn.id='btn-deliver';btn.textContent='앱 만들기';btn.title='한 줄로 앱 만들기 · 기획부터 출시 묶음까지';nav.insertBefore(btn,nav.children[2]||null);btn.onclick=()=>{dlg.showModal();refresh();};if(location.hash==='#deliver')setTimeout(()=>{if(!dlg.open){dlg.showModal();refresh();}},400);}
 document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init):init();
})();
