/* 0.4.3 설정: 업데이트 확인·한 번 눌러 업데이트, 자동 확인, 받는 곳, 믿는 출시 서명, 화면 설정 */
(()=>{
 const $=id=>document.getElementById(id);
 const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let token='',snap=null,timer=0;
 async function auth(){if(!token){const r=await fetch('/ops/roles',{cache:'no-store'});token=(await r.json()).csrf||'';}return token;}
 async function api(path,body){const o={cache:'no-store',headers:{'X-Solomon-Bridge':await auth()}};if(body!==undefined){o.method='POST';if(body!==null){o.headers['Content-Type']='application/json';o.body=JSON.stringify(body);}}const r=await fetch(path,o),out=await r.json();if(!r.ok)throw Error(out.error||'요청이 실패했습니다');return out;}
 const when=t=>{if(!t)return '';const d=new Date(t);return isNaN(d)?esc(t):d.toLocaleString('ko-KR',{month:'long',day:'numeric',hour:'2-digit',minute:'2-digit'});};
 const STATE={idle:'아직 확인 전',checking:'확인하는 중',up_to_date:'최신 판을 쓰고 있습니다',available:'새 판이 있습니다',downloading:'새 판을 받아 확인하는 중',ready:'설치 준비 끝',installing:'앱을 바꾸고 다시 켜는 중',error:'확인하지 못했습니다'};
 function build(){
  const dlg=document.createElement('dialog');dlg.id='set-panel';dlg.setAttribute('aria-labelledby','set-title');
  dlg.innerHTML=`<header class="set-head"><div><p class="set-eyebrow">SETTINGS</p><h2 id="set-title">설정</h2></div><button type="button" id="set-close">닫기</button></header>
  <div class="set-body">
   <section class="set-sec" aria-labelledby="set-up-h"><h3 id="set-up-h">업데이트</h3><div id="set-update" aria-live="polite"></div>
    <label class="set-check"><input type="checkbox" id="set-auto"> 켤 때와 6시간마다 새 판 자동 확인</label>
    <form id="set-repo-form" class="set-row"><label for="set-repo">받는 곳 (GitHub 주인/저장소)</label><div class="set-inline"><input id="set-repo" spellcheck="false" autocomplete="off"><button type="submit">저장</button></div></form>
   </section>
   <section class="set-sec" aria-labelledby="set-view-h"><h3 id="set-view-h">화면</h3>
    <div class="set-inline"><span>HUD 움직임 효과</span><button type="button" id="set-motion"></button></div>
   </section>
   <section class="set-sec" aria-labelledby="set-dev-h"><h3 id="set-dev-h">개발자 · 출시</h3>
    <p class="set-note">아래 서명이 붙은 판만 설치됩니다</p><ul id="set-signers"></ul>
    <p class="set-note">새 판 올리기: 클로드 코드에 「디렉터 새 판 출시해줘」라고 하면 <code>tools/release_mac.py publish</code>로 만들고 서명해서 올립니다</p>
    <p class="set-note">새 개발자: <code>tools/release_mac.py keygen --name 이름</code>으로 키를 만들고, 나온 공개키를 이미 등록된 사람이 다음 판에 넣어 출시합니다</p>
   </section>
  </div><p id="set-msg" role="status"></p>`;
  document.body.appendChild(dlg);
  $('set-close').onclick=()=>dlg.close();
  dlg.addEventListener('close',()=>{clearTimeout(timer);timer=0;});
  $('set-auto').onchange=async e=>{try{snap=await api('/ops/settings',{auto_check:e.target.checked});msg('저장했습니다');}catch(err){msg(err.message);e.target.checked=!e.target.checked;}};
  $('set-repo-form').onsubmit=async e=>{e.preventDefault();try{snap=await api('/ops/settings',{update_repo:$('set-repo').value});msg('받는 곳을 저장했습니다');render();}catch(err){msg(err.message);}};
  $('set-motion').onclick=()=>{$('hud-motion')?.click();motionLabel();};
  dlg.addEventListener('click',async e=>{const b=e.target.closest('button[data-up]');if(!b)return;
   if(b.dataset.up==='apply'&&!confirm('업데이트하면 앱이 잠깐 꺼졌다가 새 판으로 다시 켜집니다\n진행 중인 작업은 다시 켜진 뒤 이어서 합니다'))return;
   b.disabled=true;try{snap=await api(b.dataset.up==='check'?'/ops/update/check':'/ops/update/apply',null);msg('');}catch(err){msg(err.message);}render();poll();});
  return dlg;
 }
 function msg(t){const m=$('set-msg');if(m)m.textContent=t||'';}
 function motionLabel(){const on=$('hud-motion')?.getAttribute('aria-pressed')!=='false';const b=$('set-motion');if(b){b.textContent=on?'켜짐':'꺼짐';b.setAttribute('aria-pressed',String(on));}}
 function render(){
  badge();
  if(!snap||!$('set-update'))return;
  const s=snap,st=s.state||'idle',busy=['checking','downloading','installing'].includes(st),L=s.latest;
  let html=`<div class="set-now"><div><span class="set-label">지금 판</span><b class="set-ver">${esc(s.current)}</b></div><div class="set-state set-${esc(st)}">${busy?'<i class="set-spin"></i>':''}${esc(STATE[st]||st)}</div></div>`;
  if(st==='error'&&s.error)html+=`<p class="set-err">${esc(s.error)}</p>`;
  if(L&&['available','downloading','ready','installing','error'].includes(st))html+=`<div class="set-new"><div class="set-new-top"><b>새 판 ${esc(L.version)}</b><span>${esc(L.signer)} 출시${L.published_at?' · '+when(L.published_at):''}</span></div>${L.notes?`<p class="set-notes">${esc(L.notes)}</p>`:''}
   ${s.install_supported?`<button type="button" class="set-primary" data-up="apply" ${busy?'disabled':''}>업데이트하고 다시 켜기</button>`:'<p class="set-note">개발용으로 실행 중이라 여기서는 설치할 수 없습니다 · 설치된 앱에서 업데이트하세요</p>'}</div>`;
  html+=`<div class="set-inline"><button type="button" data-up="check" ${busy?'disabled':''}>업데이트 확인</button><span class="set-note">${s.checked_at?'마지막 확인 '+when(s.checked_at):''}${s.settings?.update_repo?' · '+esc(s.settings.update_repo):''}</span></div>`;
  const li=s.last_install;if(li)html+=`<p class="set-note">${li.ok?'최근 업데이트':'최근 업데이트 실패'} · ${esc(li.from)} → ${esc(li.version)} · ${when(li.at)}${li.ok?'':' · '+esc(li.message)}</p>`;
  $('set-update').innerHTML=html;
  $('set-auto').checked=!!s.settings?.auto_check;
  if(document.activeElement!==$('set-repo'))$('set-repo').value=s.settings?.update_repo||'';
  $('set-signers').innerHTML=(s.signers||[]).map(k=>`<li><b>${esc(k.name)}</b><code>${esc(k.fingerprint)}</code></li>`).join('');
  motionLabel();
 }
 function badge(){const b=$('btn-settings');if(!b)return;const on=!!snap&&['available','ready'].includes(snap.state);b.classList.toggle('has-update',on);b.title=on?'새 판이 있습니다 · 눌러서 업데이트':'설정 · 업데이트 확인';}
 async function load(){try{snap=await api('/ops/update');}catch(e){}render();}
 function poll(){clearTimeout(timer);const busy=snap&&['checking','downloading','installing'].includes(snap.state);timer=setTimeout(async()=>{await load();if($('set-panel').open||busy)poll();},busy?1200:5000);}
 function open(){const d=$('set-panel');if(!d.open)d.showModal();load().then(poll);}
 function init(){build();const nav=document.querySelector('.top-actions');const btn=document.createElement('button');btn.type='button';btn.id='btn-settings';btn.textContent='설정';btn.onclick=open;nav.insertBefore(btn,$('btn-halt'));
  window.openDirectorSettings=open;load();setInterval(()=>{if(!$('set-panel').open)load();},60000);}
 document.readyState==='loading'?document.addEventListener('DOMContentLoaded',init):init();
})();
