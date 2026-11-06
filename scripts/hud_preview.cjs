// Browser preview only. The installed app uses companion_server.py and real local APIs.
const http=require('node:http'),fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..');let roles={head:'claude',builder:'antigravity',reviewer:'openai'};
const total={calls:0,seconds:0,tokens:0,exact_tokens:0},usage={by_role:{},by_provider:{},total};
const emptyStatus={project_name:'프로젝트 미선택',pending_result_count:0,human_required_count:0,result:{},providers:{},run:{},stage_sentence:'작업 대기'};
const server=http.createServer((req,res)=>{
 function json(data,code=200){res.writeHead(code,{'Content-Type':'application/json; charset=utf-8','Cache-Control':'no-store'});res.end(JSON.stringify(data));}
 const url=new URL(req.url,'http://terminal.local:4173'),route=url.pathname;
 if(route==='/__responsive'){res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});return res.end('<!doctype html><html><body style="margin:0;background:#16202b"><iframe title="Mobile HUD QA" src="/" style="width:390px;height:844px;border:0"></iframe></body></html>');}
 if(req.method==='POST'){
  if(route==='/ops/roles'){let body='';req.on('data',b=>body+=b);req.on('end',()=>{try{const r=JSON.parse(body);if(Object.keys(r).sort().join(',')!=='builder,head,reviewer'||new Set(Object.values(r)).size!==3||Object.values(r).some(v=>!['claude','antigravity','openai'].includes(v)))throw Error();roles=r;json({roles,message:'미리보기 역할 변경 · 설치한 앱의 설정에는 영향을 주지 않습니다.'});}catch{json({error:'역할 설정 오류'},400);}});return;}
  if(route==='/ops/diagnostics')return json({error:'미리보기에서는 CLI를 조회하지 않습니다. 설치한 앱에서 진단하세요.'},409);
  return json({status:'error',error:'미리보기에서는 실제 AI 실행과 프로젝트 변경을 하지 않습니다. 설치한 앱에서 실행하세요.'},409);
 }
 if(route==='/ops/roles')return json({roles,csrf:'local-preview-not-a-credential'});
 if(route==='/ops/diagnostics')return json({report:null});
 if(route==='/status')return json(emptyStatus);
 if(route==='/ops/activity')return json({missions:[],working_now:[],usage:{all:usage,today:usage},events:[],recent_calls:[]});
 if(route==='/chat/messages')return json({messages:[]});
 if(route==='/ops/replay')return json({calls:[],steps:[]});
 if(route==='/ops/state')return json({orders:[],csrf:'local-preview-not-a-credential'});
 if(route==='/health')return json({product:'ai-dev-director-hud-preview',version:'0.3.0'});
 if(route==='/classic'){
  res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});
  return res.end('<!doctype html><html lang="ko"><body style="margin:0;background:#07151e;color:#d8f4ff;font:16px/1.8 sans-serif;padding:40px"><h1>AI DEV 작업실</h1><p>실제 작업실은 설치한 앱에서 프로젝트·실행 기록·검증 결과와 연결됩니다.</p><p>현재 화면은 HUD 디자인 미리보기이며 AI 호출과 파일 변경을 실행하지 않습니다.</p><a href="/" target="_top" style="color:#74ebf3">HUD로 돌아가기</a></body></html>');
 }
 let name=route==='/'?'index.html':route==='/setup'?'setup.html':route.slice(1);
 if(!/^[\w.-]+\.(html|js|css|svg|png)$/.test(name))return json({error:'not found'},404);
 const file=path.join(root,'console',name);if(!fs.existsSync(file))return json({error:'not found'},404);
 const types={html:'text/html',js:'text/javascript',css:'text/css',svg:'image/svg+xml',png:'image/png'};
 res.writeHead(200,{'Content-Type':types[name.split('.').pop()],'Cache-Control':'no-store','Content-Security-Policy':"default-src 'self'; frame-ancestors 'self'; base-uri 'none'"});fs.createReadStream(file).pipe(res);
});server.listen(4173,'0.0.0.0',()=>console.log('HUD browser preview on 4173; execution disabled'));
