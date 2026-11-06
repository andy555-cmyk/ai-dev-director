'use strict';
const $=id=>document.getElementById(id);
let report=null,token='',busy=false,loginPending=false;
const loginBusy=new Set();
const authLabels={missing:'미설치',manual_check:'직접 확인 필요',unknown:'확인되지 않음',timeout:'조회 시간 초과',not_logged_in:'로그인 필요',api_billing:'API 또는 외부 인증',logged_in:'구독 로그인 확인'};
const providerLabels={claude:'Claude Code',codex:'OpenAI Codex',agy:'Antigravity',grok:'Grok',unknown:'미설정'};
const installLinks={claude:'https://code.claude.com/docs/en/overview',codex:'https://developers.openai.com/codex/cli/',agy:'https://antigravity.google/',grok:'https://docs.x.ai/build/overview'};
const statusLabels={ready:'설치·구독 로그인 확인',needs_check:'추가 확인 필요',blocked:'설정 보완 필요'};
function node(tag,text){const n=document.createElement(tag);n.textContent=text;return n;}
function render(r){
 report=r;$('export').disabled=false;$('badge').textContent=statusLabels[r.status]||'확인 필요';$('badge').dataset.status=r.status;
 $('headline').textContent=r.status==='ready'?'설치와 구독 로그인이 확인됐습니다.':r.status==='blocked'?'작업 전 설정을 보완하세요.':'아직 확인할 연결이 있습니다.';
 $('checked').textContent='점검 시간 '+new Date(r.checked_at).toLocaleString('ko-KR')+' · '+r.scope;
 $('environment').replaceChildren();
 for(const [key,value] of [['앱 버전',r.version],['시스템',r.platform+' · '+r.architecture],['Python',r.python],['Git',r.git_ok?'실행 확인':'설치·실행 확인 필요'],['설치된 AI',r.installed_count+'개'],['확인된 구독 로그인',r.confirmed_subscription_count+'개']]){
  const row=node('div','');row.append(node('dt',key),node('dd',value));$('environment').append(row);
 }
 $('providers').replaceChildren();
 for(const p of r.providers){
  const card=node('article','');card.className='provider';
  card.append(node('h3',providerLabels[p.name]),node('p',p.installed?'설치됨 · 버전 '+(p.version||'확인 불가'):'설치되지 않음'),node('span',authLabels[p.auth]||'확인 필요'),node('p','인증 방식: '+(p.billing==='subscription'?'구독':p.billing==='api_or_external'?'API 또는 외부 제공자':'확인되지 않음')));
  const actions=node('div','');actions.className='provider-actions';
  const login=node('button',p.auth==='logged_in'?'다시 로그인':'계정 로그인');
  login.type='button';login.dataset.provider=p.name;login.setAttribute('aria-label',providerLabels[p.name]+' 계정 로그인');
  login.disabled=!p.installed||loginBusy.has(p.name);login.addEventListener('click',()=>openLogin(p.name,login));
  const check=node('button','연결 확인');check.type='button';check.className='secondary';
  check.setAttribute('aria-label',providerLabels[p.name]+' 로그인 상태 확인');check.addEventListener('click',refresh);
  actions.append(login,check);card.append(actions);
  if(p.name==='agy'){const note=node('p','Antigravity는 CLI에서 로그인합니다. 기존 계정으로 연결되면 CLI에서 계정을 관리하세요.');note.className='login-note';card.append(note);}
  if(p.name==='grok'){const note=node('p','보조 분석·리서치 전용입니다. 로그인은 CLI에서 확인하고 HUD 우측 상단에서 분석을 요청하세요.');note.className='login-note';card.append(note);}
  card.append(node('code',p.name==='agy'?'agy':p.help));
  const link=node('a','공식 설치 안내 ↗');link.href=installLinks[p.name];link.target='_blank';link.rel='noopener noreferrer';card.append(link);$('providers').append(card);
 }
 $('roles').replaceChildren();for(const [role,name] of Object.entries(r.roles))$('roles').append(node('span',role.toUpperCase()+' · '+providerLabels[name]));
 for(const key of ['blockers','warnings']){const list=$(key);list.replaceChildren();for(const text of r[key]||[])list.append(node('li',text));}
 if(!r.blockers.length&&!r.warnings.length)$('warnings').append(node('li','추가 확인 항목이 없습니다. 실제 작업은 별도 검증이 필요합니다.'));
}
async function openLogin(provider,button){
 if(loginBusy.has(provider))return;
 loginBusy.add(provider);button.disabled=true;
 const previousLabel=button.textContent;button.textContent='로그인 창 여는 중…';
 $('login-message').textContent=providerLabels[provider]+' 공식 로그인 창을 열고 있습니다…';
 try{
  if(!token)throw Error('화면을 새로고침한 뒤 다시 시도하세요.');
  const res=await fetch('/ops/auth/login',{method:'POST',headers:{'Content-Type':'application/json','X-Solomon-Bridge':token},body:JSON.stringify({provider})});
  const result=await res.json();
  if(!res.ok)throw Error(result.error||'로그인 창을 열지 못했습니다.');
  if(result.status!=='opened')throw Error('로그인 창이 열렸는지 확인하지 못했습니다. 다시 시도하세요.');
  loginPending=true;$('verify-login').hidden=false;$('login-message').textContent=result.message;
 }catch(error){$('login-message').textContent=error.message;}
 finally{
  loginBusy.delete(provider);button.disabled=false;button.textContent=previousLabel;
  for(const current of $('providers').querySelectorAll('button[data-provider]'))if(current.dataset.provider===provider)current.disabled=false;
 }
}
async function refresh(){if(busy)return false;busy=true;$('refresh').disabled=true;$('verify-login').disabled=true;$('message').textContent='CLI 설치와 로그인 상태를 확인하고 있습니다…';try{if(!token)throw Error('연결을 다시 불러온 뒤 재시도하세요.');const res=await fetch('/ops/diagnostics',{method:'POST',headers:{'X-Solomon-Bridge':token},cache:'no-store'});const result=await res.json();if(!res.ok)throw Error(result.error||'진단 실패');render(result.report);$('message').textContent='진단이 완료됐습니다.';return true;}catch(error){$('message').textContent=error.message;return false;}finally{busy=false;$('refresh').disabled=false;$('verify-login').disabled=false;}}
$('refresh').addEventListener('click',refresh);
$('verify-login').addEventListener('click',async()=>{if(await refresh()){loginPending=false;$('login-message').textContent='로그인 상태를 다시 확인했습니다. 각 AI 카드의 결과를 확인하세요. Antigravity와 Grok은 CLI에서 직접 확인해야 합니다.';}});
window.addEventListener('focus',()=>{if(loginPending&&!busy)refresh();});
$('export').addEventListener('click',()=>{if(!report)return;const blob=new Blob([JSON.stringify(report,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='AI_Dev_Director_Diagnostics.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
(async()=>{try{const res=await fetch('/ops/roles',{cache:'no-store'});if(!res.ok)throw Error('관리 화면에 연결할 수 없습니다.');token=(await res.json()).csrf;if(!token)throw Error('관리 화면에 연결할 수 없습니다.');await refresh();}catch(error){$('message').textContent=error.message;}})();
