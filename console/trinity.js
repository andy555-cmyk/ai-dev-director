'use strict';
/* TRINITY stage: three mission cores and an auxiliary research node feeding one fused core. Pure WebGL2.
   Ambient circuit lights keep the HUD alive; actual work increases their speed and brightness.
   Slots: 0 HEAD, 1 BUILDER, 2 REVIEWER, 3 GROK research (/ops/grok). */
window.Trinity=(function(){
const SLOTS=[[-.64,.86,.1],[-1.02,-.48,.12],[1.02,-.48,.12],[.78,.84,.1]];
const COUNTS={ribbon:7000,stream:4500,node:3200,dust:5200,edge:1700,nucleus:9000,verify:2400,shock:1800,gyro:9000,circuit:2500,halo:6000,engraving:6000,wave:5500,platform:2400};
function tracePoints(owner,lane){
  const s=SLOTS[owner],sx=Math.sign(s[0]),sy=Math.sign(s[1]),offset=lane*.024;
  return [[sx*.49,sy*.12+offset,.1],[sx*(.68+Math.abs(lane)*.008),sy*.12+offset,.1],
          [s[0]*.79,s[1]*.60+offset*.65,.1],[s[0]*.93,s[1]*.93+offset*.25,s[2]]];
}
function tracePoint(owner,lane,u){
  const p=tracePoints(owner,lane),i=u<.3?0:u<.65?1:2,f=i===0?u/.3:i===1?(u-.3)/.35:(u-.65)/.35;
  return p[i].map((v,j)=>v+(p[i+1][j]-v)*f);
}

const VS_POINTS=`#version 300 es
precision highp float;
layout(location=0) in vec4 aSeed;
layout(location=1) in vec2 aMeta;
uniform mat4 uVP;
uniform float uTime,uPx,uCore,uVerify,uPulse,uBoot,uPhC;
uniform vec3 uSlot[4];
uniform vec3 uColor[4];
uniform vec4 uAct,uPhS,uPhN;
uniform vec3 uEdge,uPhE,uPulseColor;
out vec3 vColor;
out float vAlpha,vKind;
const float TAU=6.28318530718;
vec3 rotX(vec3 p,float a){float c=cos(a),s=sin(a);return vec3(p.x,c*p.y-s*p.z,s*p.y+c*p.z);}
vec3 rotY(vec3 p,float a){float c=cos(a),s=sin(a);return vec3(c*p.x+s*p.z,p.y,-s*p.x+c*p.z);}
vec3 rotZ(vec3 p,float a){float c=cos(a),s=sin(a);return vec3(c*p.x-s*p.y,s*p.x+c*p.y,p.z);}
vec3 sph(float u,float v){float z=2.*u-1.;float r=sqrt(max(0.,1.-z*z));float a=TAU*v;return vec3(r*cos(a),z,r*sin(a));}
float pick(vec3 v,int i){return i==0?v.x:(i==1?v.y:v.z);}
float pick(vec4 v,int i){return i==0?v.x:(i==1?v.y:(i==2?v.z:v.w));}
vec3 trace(float u,int o,float lane){
  vec3 s=uSlot[o];float sx=sign(s.x),sy=sign(s.y),offset=lane*.024;
  vec3 a=vec3(sx*.49,sy*.12+offset,.1);
  vec3 b=vec3(sx*(.68+abs(lane)*.008),sy*.12+offset,.1);
  vec3 c=vec3(s.x*.79,s.y*.60+offset*.65,.1);
  vec3 d=vec3(s.x*.93,s.y*.93+offset*.25,s.z);
  return u<.3?mix(a,b,u/.3):u<.65?mix(b,c,(u-.3)/.35):mix(c,d,(u-.65)/.35);
}
void main(){
  float kind=aMeta.x;int o=int(aMeta.y+.5);
  vec3 col=uColor[o];float act=pick(uAct,o);float t=uTime;
  vec3 p=vec3(0.);float size=.014;float alpha=1.;
  float energy=clamp(uCore+uPulse*.6,0.,1.4);
  if(kind<.5){                                   // 0 fused core: one orbital ribbon per AI, intertwined
    float th=TAU*aSeed.x+uPhC*(.6+.8*aSeed.w);
    float w=aSeed.y-.5;
    float tw=th*1.5+t*.2+float(o)*2.1;
    float R=.47+.03*(aSeed.z-.5)+.028*sin(th*5.+t*1.7+float(o)*2.)*(.3+energy);
    float W=.038*(1.+.6*energy);
    vec3 l=vec3(cos(th)*(R+w*W*cos(tw)),w*W*sin(tw),sin(th)*(R+w*W*cos(tw)));
    p=rotY(rotX(l,1.18),float(o)*TAU/3.+t*.07);
    size=.006+.008*aSeed.z;alpha=.16+.24*min(energy,1.);
    col=mix(col,mix(vec3(.20,.85,1.),vec3(.66,.35,1.),float(o)/2.),.78);
  }else if(kind<1.5){                            // 1 stream: an AI pours its work into the core
    float u=fract(aSeed.x+pick(uPhS,o)*(.6+.8*aSeed.y));
    vec3 a=uSlot[o];float e=u*u*(3.-2.*u);
    vec3 base=a*(1.-e);
    vec3 dir=normalize(-a);vec3 n1=normalize(cross(dir,vec3(0.,0.,1.)));vec3 n2=cross(dir,n1);
    float ang=aSeed.z*TAU+u*7.+t*.5;
    float rad=(.012+.12*aSeed.w*aSeed.w)*sin(3.14159*u)*(.65+.7*act);
    p=base+(n1*cos(ang)+n2*sin(ang))*rad;
    float vis=step(aSeed.w,.2+.8*act);          // idle: only a thin thread stays lit
    alpha=vis*(.07+.60*act)*smoothstep(0.,.07,u)*(1.-.8*smoothstep(.70,1.,u));
    size=(.010+.017*aSeed.w)*(.8+.5*act);
    col=mix(col,vec3(1.),e*e*.35*uCore);
  }else if(kind<2.5){                            // 2 AI node: dense body + orbit ring
    vec3 c=uSlot[o];
    if(aSeed.z<.72){
      vec3 d=sph(aSeed.x,aSeed.y);
      float rr=(.085+.055*aSeed.w)*(1.+.32*act+.06*sin(t*2.2+aSeed.w*TAU)*(.4+act));
      d=rotY(rotX(d,t*.3+float(o)),t*.45);
      p=c+d*rr;col=mix(col,vec3(1.),.28*(1.-aSeed.w));
      alpha=.30+.5*act;size=.011+.013*aSeed.w;
    }else{
      float th=TAU*aSeed.x+pick(uPhN,o)*(.8+.4*aSeed.y);
      float rr=.19+.022*(aSeed.w-.5)+.03*act;
      vec3 l=vec3(cos(th)*rr,(aSeed.y-.5)*.014,sin(th)*rr);
      p=c+rotZ(rotX(l,1.2),float(o)*2.1+t*.1);
      alpha=(.22+.78*act)*(.4+.6*pow(aSeed.x,3.));size=.010;
    }
  }else if(kind<3.5){                            // 3 depth dust
    p=(aSeed.xyz*2.-1.)*vec3(3.8,2.3,2.8);p=rotY(p,t*.012);p.y+=sin(t*.07+aSeed.w*TAU)*.08;
    alpha=.09+.22*pow(.5+.5*sin(t*(.3+aSeed.w)+aSeed.x*40.),3.);
    size=.008+.016*aSeed.w*aSeed.w;col=mix(vec3(.5,.66,1.),vec3(1.),aSeed.z);
  }else if(kind<4.5){                            // 4 hand-off arc: slot o -> next slot (order, code, verdict)
    int n=(o+1)%3;vec3 a=uSlot[o],b=uSlot[n];vec3 m=(a+b)*.5;vec3 ctrl=m+normalize(m)*.50;
    float edge=pick(uEdge,o);
    float u=fract(aSeed.x+pick(uPhE,o)*(.75+.5*aSeed.y));
    p=mix(mix(a,ctrl,u),mix(ctrl,b,u),u)+(aSeed.yzw-.5)*.03*(.4+edge);
    float band=pow(.5+.5*sin(aSeed.x*TAU*4.),4.);
    alpha=(.045+.95*edge)*(.25+.75*band)*smoothstep(0.,.06,u)*smoothstep(1.,.94,u);
    col=mix(uColor[o],uColor[n],u);size=.009+.016*aSeed.w*(.3+edge);
  }else if(kind<5.5){                            // 5 nucleus: where the three become one
    vec3 d=sph(aSeed.x,aSeed.y);
    float rr=(.035+.115*pow(aSeed.z,1.5))*(1.+.26*uPulse+.10*sin(t*1.6+aSeed.w*TAU)*(.3+uCore));
    d=rotY(rotZ(d,t*.21+aSeed.w),uPhC*.5);p=d*rr;
    col=mix(col,vec3(1.,.96,.9),.3+.62*uCore*(1.-aSeed.z));
    alpha=.10+.25*uCore;size=.007+.009*(1.-aSeed.z);
  }else if(kind<6.5){                            // 6 verification scanner (Director running tests)
    float sgn=aSeed.y<.5?1.:-1.;
    float th=TAU*aSeed.x+t*1.3*sgn;float rr=.70+.016*(aSeed.w-.5);
    vec3 l=vec3(cos(th)*rr,0.,sin(th)*rr);
    p=rotX(l,1.57+.55*(sgn>0.?sin(t*.9):cos(t*.7)));
    alpha=uVerify*(.10+.90*pow(aSeed.x,5.));col=mix(vec3(.55,1.,.82),vec3(1.),pow(aSeed.x,8.));size=.012;
  }else if(kind<7.5){                            // 7 shockwave on a result
    float th=TAU*aSeed.x;float k=1.-uPulse;float rr=.25+k*2.4+(aSeed.w-.5)*.06;
    p=vec3(cos(th)*rr,sin(th)*rr,(aSeed.y-.5)*.06);
    alpha=uPulse*uPulse*(.6+.4*aSeed.z);col=uPulseColor;size=.011+.012*aSeed.z;
  }
  else if(kind<8.5){                               // 8 dimensional gyroscope rails and orbital traces
    float band=floor(aSeed.z*5.);
    float th=aSeed.x*TAU+uPhC*(.09+float(o)*.025);
    float radius=.69+band*.022+(aSeed.y-.5)*.006;
    vec3 rail=vec3(cos(th)*radius,0.,sin(th)*radius);
    p=rotZ(rotX(rail,1.05+float(o)*.46),float(o)*1.18+t*.035);
    float ticks=step(.78,fract(aSeed.x*90.));
    alpha=(.07+.16*ticks)*(.4+energy*.5);
    col=mix(vec3(.17,.67,.76),vec3(.71,.95,1.),ticks*.65);
    size=.006+.004*ticks;
  }else if(kind<9.5){                               // 9 seven etched circuit lanes per AI, with moving light packets
    float lane=floor(aSeed.y*7.)-3.;float u=aSeed.x;
    p=trace(u,o,lane);
    float packet=pow(.5+.5*cos((u+pick(uPhS,o)*.85)*TAU*2.+lane*.36),22.);
    col=mix(col,vec3(.75,.98,1.),packet*.68);
    alpha=(.24+packet*1.15)*(.65+.65*act);
    size=.0055+packet*.014;
  }else if(kind<10.5){                              // 10 three luminous, segmented rings around the intelligence core
    float band=floor(aSeed.y*3.),th=aSeed.x*TAU+uPhC*.13*(band==1.?-1.:1.);
    float radius=.57+band*.052;
    p=rotY(rotX(vec3(cos(th)*radius,sin(th)*radius,.08),.12*sin(t*.13)),.13*cos(t*.11));
    float segment=step(.16,fract(aSeed.x*(12.+band*4.)));
    float head=pow(.5+.5*cos(th*2.-uPhC*.7+band),24.);
    col=mix(vec3(.17,.78,1.),vec3(.72,.40,1.),.5+.5*sin(th+band));
    col=mix(col,vec3(.8,1.,1.),head*.65);
    alpha=segment*(.30+head*.85+uCore*.2);size=.006+head*.012;
  }else if(kind<11.5){                              // 11 circuit-board engraving on a translucent spherical shell
    float lane=floor(aSeed.y*20.)-9.5,u=aSeed.x,sgn=aSeed.z<.5?-1.:1.;
    float x=lane*.038;
    float top=sqrt(max(0.,.47*.47-x*x));
    float y=sgn*top*(.92-u*.56);
    x+=sign(x)*.025*smoothstep(.25,.45,u)-sign(x)*.025*smoothstep(.62,.82,u);
    float z=sqrt(max(0.,.47*.47-x*x-y*y));
    p=rotY(vec3(x,y,z),.16*sin(t*.11));
    float signal=pow(.5+.5*sin(u*TAU-uPhC*.8+lane*.25),12.);
    col=mix(vec3(.21,.68,1.),vec3(.65,.36,1.),step(0.,x));
    col=mix(col,vec3(.75,1.,1.),signal*.7);
    alpha=.24+signal*.4;size=.005+signal*.006;
    if(aSeed.w>.96){p=rotY(vec3(lane*.038,sgn*top*.38,sqrt(max(0.,.47*.47-lane*lane*.038*.038-top*top*.38*.38))),.16*sin(t*.11));size=.015;alpha=.7;}
  }else if(kind<12.5){                              // 12 layered blue wave filaments behind the core
    float lane=floor(aSeed.y*28.),x=(aSeed.x*2.-1.)*1.52;
    float wave=sin(x*2.6-t*.45+lane*.11);
    p=vec3(x,-.87+wave*.11+lane*.004,-.30+lane*.006);
    float crest=pow(.5+.5*sin(x*3.6-t*.7+lane*.12),10.);
    col=mix(vec3(.07,.30,.86),vec3(.20,.91,1.),crest);
    alpha=(.07+crest*.26)*(1.-smoothstep(.9,1.55,abs(x)));size=.005+crest*.004;
  }else if(kind<13.5){                              // 13 star flare at each AI junction
    p=uSlot[o];size=.24+.08*act;alpha=.48+.4*act;
    col=mix(col,vec3(.85,1.,1.),.35);
  }else if(kind<14.5){                              // 14 lit terminal dots at both ends of every circuit lane
    float lane=floor(aSeed.y*7.)-3.;
    p=trace(aSeed.x<.5?0.:1.,o,lane)+(aSeed.zww-.5)*.003;
    alpha=.45+.45*act;size=.017;
    col=mix(col,vec3(.85,1.,1.),.5);
  }else{                                           // 15 projection platform: concentric light rails and a rotating sweep
    float band=floor(aSeed.y*5.),th=aSeed.x*TAU;
    float r=.63+band*.13;
    p=vec3(cos(th)*r,-1.02+band*.008,sin(th)*r*.40);
    float sweep=pow(.5+.5*cos(th-uPhC*.5),24.);
    col=mix(vec3(.12,.45,1.),vec3(.26,.93,1.),sweep);
    alpha=(.12+sweep*.65)*(.55+.45*step(.25,fract(aSeed.x*60.)));size=.005+sweep*.008;
  }
  vec3 scatter=(aSeed.zxy*2.-1.)*3.2;            // boot: everything assembles out of scattered dust
  float bt=clamp(uBoot*1.3-aSeed.w*.3,0.,1.);bt=bt*bt*(3.-2.*bt);
  p=mix(scatter,p,bt);alpha*=bt;
  vec4 clip=uVP*vec4(p,1.);
  gl_Position=clip;gl_PointSize=max(1.5,size*uPx/clip.w);
  vColor=col;vAlpha=alpha;vKind=kind;
}`;
const FS_POINTS=`#version 300 es
precision highp float;
in vec3 vColor;in float vAlpha,vKind;out vec4 o;
void main(){
  vec2 c=gl_PointCoord*2.-1.;float d=dot(c,c);if(d>1.)discard;
  float a=exp(-d*4.2);
  if(abs(vKind-13.)<.2)a=exp(-d*16.)*.7+exp(-abs(c.y)*55.-abs(c.x)*4.)+exp(-abs(c.x)*55.-abs(c.y)*5.);
  a*=vAlpha;o=vec4(vColor*a,a);
}`;
const VS_FULL=`#version 300 es
out vec2 vUv;
void main(){vec2 p=vec2(float((gl_VertexID<<1)&2),float(gl_VertexID&2));vUv=p;gl_Position=vec4(p*2.-1.,0.,1.);}`;
const FS_BLUR=`#version 300 es
precision highp float;
in vec2 vUv;out vec4 o;uniform sampler2D uTex;uniform vec2 uDir;
void main(){
  vec4 c=texture(uTex,vUv)*.227027;
  c+=(texture(uTex,vUv+uDir*1.3846153)+texture(uTex,vUv-uDir*1.3846153))*.3162162;
  c+=(texture(uTex,vUv+uDir*3.2307692)+texture(uTex,vUv-uDir*3.2307692))*.0702703;
  o=c;
}`;
const FS_COMP=`#version 300 es
precision highp float;
in vec2 vUv;out vec4 o;
uniform sampler2D uScene,uB1,uB2;
uniform vec2 uRes,uCenter;uniform float uTime,uCore,uPulse;uniform vec3 uTint,uPulseColor;
float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
float noise(vec2 p){vec2 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
  return mix(mix(hash(i),hash(i+vec2(1.,0.)),f.x),mix(hash(i+vec2(0.,1.)),hash(i+vec2(1.,1.)),f.x),f.y);}
float fbm(vec2 p){float v=0.,a=.5;for(int i=0;i<5;i++){v+=a*noise(p);p=p*2.03+vec2(11.3,7.7);a*=.5;}return v;}
void main(){
  vec2 q=(vUv-uCenter)*vec2(uRes.x/uRes.y,1.);float r=length(q);
  vec3 bg=mix(vec3(.012,.025,.065),vec3(.003,.005,.018),smoothstep(0.,1.15,r));
  float neb=fbm(q*1.7+vec2(uTime*.012,-uTime*.008));float neb2=fbm(q*3.1-vec2(uTime*.01,0.)+neb);
  bg+=uTint*(.035+.10*uCore)*neb*neb2*(1.-smoothstep(.05,1.3,r))*1.6;
  float ring=smoothstep(.0035,0.,abs(r-.36))+smoothstep(.0035,0.,abs(r-.72))*.6+smoothstep(.003,0.,abs(r-1.08))*.3;
  bg+=vec3(.35,.5,.8)*ring*.045;
  bg+=uPulseColor*uPulse*.10*(1.-smoothstep(0.,1.2,r));
  vec2 ca=(vUv-.5)*.0016;
  vec3 scene=vec3(texture(uScene,vUv+ca).r,texture(uScene,vUv).g,texture(uScene,vUv-ca).b);
  vec3 col=bg+scene+texture(uB1,vUv).rgb*.62+texture(uB2,vUv).rgb*.92;
  float peak=max(col.r,max(col.g,col.b))+1e-4;                 // tone-map on the peak channel: bright stays coloured
  vec3 hue=col*((1.-exp(-peak*1.15))/peak);
  col=mix(hue,1.-exp(-col*1.15),.38);
  vec2 v=vUv-.5;col*=1.-.42*dot(v,v)*1.6;
  col+=(hash(vUv*uRes+fract(uTime)*91.7)-.5)*.022;
  o=vec4(max(col,0.),1.);
}`;

let canvas,gl,progP,progB,progC,uP={},uB={},uC={},vao,total=0,fb={},hdr=false,size=[0,0],running=false,raf=0;
let onFrame=null,failed=false,flat=null,listening=false;
const cur={act:[.1,.1,.1,.12],edge:[0,0,0],core:.18,verify:0,colors:[[1,.54,.36],[.42,.65,1],[.24,.95,.75],[.79,.84,.96]]};
const tgt={act:[.1,.1,.1,.12],edge:[0,0,0],core:.18,verify:0,colors:cur.colors.map(c=>c.slice())};
const ph={c:0,s:[0,0,0,0],e:[0,0,0],n:[0,0,0,0]};
let pulse=0,pulseColor=[1,1,1],boot=0,time=0,last=0,timeScale=1;
let rect={x:0,y:0,w:1,h:1};const mouse=[0,0],mouseS=[0,0];
const vp=new Float32Array(16);

function compile(type,src){const s=gl.createShader(type);gl.shaderSource(s,src);gl.compileShader(s);
  if(!gl.getShaderParameter(s,gl.COMPILE_STATUS))throw Error(gl.getShaderInfoLog(s)||'shader');return s;}
function program(vs,fs){const p=gl.createProgram();gl.attachShader(p,compile(gl.VERTEX_SHADER,vs));gl.attachShader(p,compile(gl.FRAGMENT_SHADER,fs));
  gl.bindAttribLocation(p,0,'aSeed');gl.bindAttribLocation(p,1,'aMeta');gl.linkProgram(p);
  if(!gl.getProgramParameter(p,gl.LINK_STATUS))throw Error(gl.getProgramInfoLog(p)||'link');return p;}
function uniforms(p,names){const o={};for(const n of names)o[n]=gl.getUniformLocation(p,n);return o;}
function rng(seed){let s=seed>>>0;return()=>{s=(s+0x6D2B79F5)|0;let t=Math.imul(s^s>>>15,1|s);t=t+Math.imul(t^t>>>7,61|t)^t;return((t^t>>>14)>>>0)/4294967296;};}

function buildGeometry(){
  const groups=[];const add=(kind,owner,n)=>groups.push([kind,owner,n]);
  for(let o=0;o<3;o++){add(0,o,COUNTS.ribbon);add(1,o,COUNTS.stream);add(2,o,COUNTS.node);add(4,o,COUNTS.edge);add(5,o,COUNTS.nucleus/3);}
  // Research has its own node and core stream; the mission hand-off cycle remains three roles.
  add(1,3,COUNTS.stream);add(2,3,COUNTS.node);
  for(let o=0;o<3;o++)add(8,o,COUNTS.gyro/3);
  for(let o=0;o<4;o++){add(9,o,COUNTS.circuit);add(13,o,1);add(14,o,140);}
  add(10,0,COUNTS.halo);add(11,0,COUNTS.engraving);add(12,0,COUNTS.wave);add(15,0,COUNTS.platform);
  add(3,0,COUNTS.dust);add(6,0,COUNTS.verify);add(7,0,COUNTS.shock);
  total=groups.reduce((a,g)=>a+g[2],0);
  const data=new Float32Array(total*6),rand=rng(20260930);let i=0;
  for(const [kind,owner,n] of groups)for(let k=0;k<n;k++){data[i++]=rand();data[i++]=rand();data[i++]=rand();data[i++]=rand();data[i++]=kind;data[i++]=owner;}
  vao=gl.createVertexArray();gl.bindVertexArray(vao);
  const buf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.bufferData(gl.ARRAY_BUFFER,data,gl.STATIC_DRAW);
  gl.enableVertexAttribArray(0);gl.vertexAttribPointer(0,4,gl.FLOAT,false,24,0);
  gl.enableVertexAttribArray(1);gl.vertexAttribPointer(1,2,gl.FLOAT,false,24,16);
  gl.bindVertexArray(null);
}
function target(w,h){
  const tex=gl.createTexture();gl.bindTexture(gl.TEXTURE_2D,tex);
  if(hdr)gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA16F,w,h,0,gl.RGBA,gl.HALF_FLOAT,null);
  else gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA8,w,h,0,gl.RGBA,gl.UNSIGNED_BYTE,null);
  for(const [k,v] of [[gl.TEXTURE_MIN_FILTER,gl.LINEAR],[gl.TEXTURE_MAG_FILTER,gl.LINEAR],[gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE],[gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE]])gl.texParameteri(gl.TEXTURE_2D,k,v);
  const f=gl.createFramebuffer();gl.bindFramebuffer(gl.FRAMEBUFFER,f);gl.framebufferTexture2D(gl.FRAMEBUFFER,gl.COLOR_ATTACHMENT0,gl.TEXTURE_2D,tex,0);
  const ok=gl.checkFramebufferStatus(gl.FRAMEBUFFER)===gl.FRAMEBUFFER_COMPLETE;gl.bindFramebuffer(gl.FRAMEBUFFER,null);
  return {f,tex,w,h,ok};
}
function freeTargets(){for(const k of Object.keys(fb)){gl.deleteFramebuffer(fb[k].f);gl.deleteTexture(fb[k].tex);}fb={};}
function resize(){
  const cw=canvas.clientWidth||1,ch=canvas.clientHeight||1;
  const dpr=Math.min(window.devicePixelRatio||1,1.5,Math.sqrt(3.4e6/(cw*ch)));     // cap the HDR buffers at ~3.4 MP
  const w=Math.max(2,Math.round(cw*dpr)),h=Math.max(2,Math.round(ch*dpr));
  if(w===size[0]&&h===size[1])return;
  size=[w,h];canvas.width=w;canvas.height=h;
  if(!gl)return;
  freeTargets();
  fb.scene=target(w,h);
  if(!fb.scene.ok&&hdr){hdr=false;freeTargets();fb.scene=target(w,h);}
  const w2=Math.max(2,w>>1),h2=Math.max(2,h>>1),w4=Math.max(2,w>>2),h4=Math.max(2,h>>2);
  fb.a1=target(w2,h2);fb.b1=target(w2,h2);fb.a2=target(w4,h4);fb.b2=target(w4,h4);
}
// ---- camera (column-major mat4)
function mul(o,a,b){for(let c=0;c<4;c++)for(let r=0;r<4;r++)o[c*4+r]=a[r]*b[c*4]+a[4+r]*b[c*4+1]+a[8+r]*b[c*4+2]+a[12+r]*b[c*4+3];return o;}
const P=new Float32Array(16),V=new Float32Array(16);
function camera(){
  const W=size[0],H=size[1],aspect=W/H,fov=36*Math.PI/180,f=1/Math.tan(fov/2);
  const need=Math.max(1.36/(Math.max(rect.h,.2)),1.50/(aspect*Math.max(rect.w,.2)));
  const dist=need*f,near=.1,far=40;
  P.fill(0);P[0]=f/aspect;P[5]=f;P[10]=(far+near)/(near-far);P[11]=-1;P[14]=2*far*near/(near-far);
  const yaw=.24*Math.sin(time*.11)+mouseS[0]*.22,pitch=.07*Math.sin(time*.17)+mouseS[1]*.12;
  const tx=0,ty=.06,tz=0;
  const ex=tx+dist*Math.sin(yaw)*Math.cos(pitch),ey=ty+dist*Math.sin(pitch),ez=tz+dist*Math.cos(yaw)*Math.cos(pitch);
  let zx=ex-tx,zy=ey-ty,zz=ez-tz;const zl=Math.hypot(zx,zy,zz);zx/=zl;zy/=zl;zz/=zl;
  let xx=zz,xy=0,xz=-zx;const xl=Math.hypot(xx,xy,xz);xx/=xl;xz/=xl;                  // up(0,1,0) x z
  const yx=zy*xz-zz*xy,yy=zz*xx-zx*xz,yz=zx*xy-zy*xx;
  V[0]=xx;V[1]=yx;V[2]=zx;V[3]=0;V[4]=xy;V[5]=yy;V[6]=zy;V[7]=0;V[8]=xz;V[9]=yz;V[10]=zz;V[11]=0;
  V[12]=-(xx*ex+xy*ey+xz*ez);V[13]=-(yx*ex+yy*ey+yz*ez);V[14]=-(zx*ex+zy*ey+zz*ez);V[15]=1;
  mul(vp,P,V);
  const ox=2*(rect.x+rect.w/2)-1,oy=1-2*(rect.y+rect.h/2);                            // lens shift: scene centre -> stage rect centre
  for(let c=0;c<4;c++){vp[c*4]+=ox*vp[c*4+3];vp[c*4+1]+=oy*vp[c*4+3];}
  return f;
}
function project(p){
  const x=vp[0]*p[0]+vp[4]*p[1]+vp[8]*p[2]+vp[12],y=vp[1]*p[0]+vp[5]*p[1]+vp[9]*p[2]+vp[13],w=vp[3]*p[0]+vp[7]*p[1]+vp[11]*p[2]+vp[15];
  return [(x/w*.5+.5),(1-(y/w*.5+.5)),w];
}
function approach(dt){
  const k=timeScale===0?1:1-Math.exp(-dt*3.2),kc=timeScale===0?1:1-Math.exp(-dt*2.2);
  for(let i=0;i<4;i++){cur.act[i]+=(tgt.act[i]-cur.act[i])*k;
    for(let j=0;j<3;j++)cur.colors[i][j]+=(tgt.colors[i][j]-cur.colors[i][j])*kc;}
  for(let i=0;i<3;i++)cur.edge[i]+=(tgt.edge[i]-cur.edge[i])*k;
  cur.core+=(tgt.core-cur.core)*k;cur.verify+=(tgt.verify-cur.verify)*k;
  mouseS[0]+=(mouse[0]-mouseS[0])*k*.6;mouseS[1]+=(mouse[1]-mouseS[1])*k*.6;
  pulse=Math.max(0,pulse-dt/1.7);
  ph.c+=dt*(.16+.8*cur.core+.7*pulse);
  for(let i=0;i<4;i++){ph.s[i]+=dt*(.075+.26*cur.act[i]);ph.n[i]+=dt*(.22+1.7*cur.act[i]);}
  for(let i=0;i<3;i++)ph.e[i]+=dt*(.045+.32*cur.edge[i]);
  boot=Math.min(1,boot+dt/3.2);
}
function blur(src,dst,dx,dy){
  gl.bindFramebuffer(gl.FRAMEBUFFER,dst.f);gl.viewport(0,0,dst.w,dst.h);
  gl.bindTexture(gl.TEXTURE_2D,src.tex);gl.uniform2f(uB.uDir,dx/dst.w,dy/dst.h);gl.drawArrays(gl.TRIANGLES,0,3);
}
function frame(now){
  raf=requestAnimationFrame(frame);
  const dt=Math.min(.05,Math.max(0,(now-last)/1000))*timeScale;last=now;
  if(document.hidden||document.body.dataset.view==='workshop')return;
  if(timeScale===0&&now-(frame.lastPaint||0)<200)return;
  frame.lastPaint=now;render(dt);
}
function render(dt){
  time+=dt;resize();approach(dt);
  const f=camera(),tint=[0,0,0];let wsum=0;
  for(let i=0;i<4;i++){const w=.25+cur.act[i];wsum+=w;for(let j=0;j<3;j++)tint[j]+=cur.colors[i][j]*w;}
  if(flat){drawFlat();emit();return;}
  gl.bindFramebuffer(gl.FRAMEBUFFER,fb.scene.f);gl.viewport(0,0,size[0],size[1]);
  gl.clearColor(0,0,0,0);gl.clear(gl.COLOR_BUFFER_BIT);
  gl.enable(gl.BLEND);gl.blendFunc(gl.ONE,gl.ONE);
  gl.useProgram(progP);gl.bindVertexArray(vao);
  gl.uniformMatrix4fv(uP.uVP,false,vp);gl.uniform1f(uP.uTime,time);gl.uniform1f(uP.uPx,size[1]*f*.5);
  gl.uniform1f(uP.uCore,cur.core);gl.uniform1f(uP.uVerify,cur.verify);gl.uniform1f(uP.uPulse,pulse);gl.uniform1f(uP.uBoot,boot);gl.uniform1f(uP.uPhC,ph.c);
  gl.uniform3fv(uP['uSlot[0]'],SLOTS.flat());gl.uniform3fv(uP['uColor[0]'],cur.colors.flat());
  gl.uniform4fv(uP.uAct,cur.act);gl.uniform3fv(uP.uEdge,cur.edge);gl.uniform4fv(uP.uPhS,ph.s);gl.uniform3fv(uP.uPhE,ph.e);gl.uniform4fv(uP.uPhN,ph.n);
  gl.uniform3fv(uP.uPulseColor,pulseColor);
  gl.drawArrays(gl.POINTS,0,total);
  gl.disable(gl.BLEND);gl.bindVertexArray(null);
  gl.useProgram(progB);gl.activeTexture(gl.TEXTURE0);gl.uniform1i(uB.uTex,0);
  blur(fb.scene,fb.a1,1,0);blur(fb.a1,fb.b1,0,1);blur(fb.b1,fb.a2,1.6,0);blur(fb.a2,fb.b2,0,1.6);
  gl.bindFramebuffer(gl.FRAMEBUFFER,null);gl.viewport(0,0,size[0],size[1]);
  gl.useProgram(progC);
  gl.activeTexture(gl.TEXTURE0);gl.bindTexture(gl.TEXTURE_2D,fb.scene.tex);gl.uniform1i(uC.uScene,0);
  gl.activeTexture(gl.TEXTURE1);gl.bindTexture(gl.TEXTURE_2D,fb.b1.tex);gl.uniform1i(uC.uB1,1);
  gl.activeTexture(gl.TEXTURE2);gl.bindTexture(gl.TEXTURE_2D,fb.b2.tex);gl.uniform1i(uC.uB2,2);
  const c=project([0,0,0]);
  gl.uniform2f(uC.uRes,size[0],size[1]);gl.uniform2f(uC.uCenter,c[0],1-c[1]);gl.uniform1f(uC.uTime,time);
  gl.uniform1f(uC.uCore,cur.core);gl.uniform1f(uC.uPulse,pulse);
  gl.uniform3f(uC.uTint,tint[0]/wsum,tint[1]/wsum,tint[2]/wsum);gl.uniform3fv(uC.uPulseColor,pulseColor);
  gl.drawArrays(gl.TRIANGLES,0,3);gl.activeTexture(gl.TEXTURE0);
  emit();
}
function emit(){
  if(!onFrame)return;
  const cw=canvas.clientWidth,ch=canvas.clientHeight,unit=project([.5,0,0]),zero=project([0,0,0]);
  onFrame({slots:SLOTS.map(s=>{const p=project(s);return [p[0]*cw,p[1]*ch];}),core:[zero[0]*cw,zero[1]*ch],
           unit:Math.abs(unit[0]-zero[0])*cw*2,act:cur.act,pulse});
}
// ---- 2D fallback (no WebGL2): same data, simpler picture
function drawFlat(){
  const c=flat,W=size[0],H=size[1],cw=canvas.clientWidth,k=W/cw;
  c.setTransform(1,0,0,1,0,0);c.fillStyle='#02090e';c.fillRect(0,0,W,H);
  const pt=p=>{const q=project(p);return[q[0]*W,q[1]*H];},o=pt([0,0,0]),unit=Math.abs(pt([1,0,0])[0]-o[0]);
  function rgba(col,a){return 'rgba('+col.map(v=>Math.round(v*255)).join(',')+','+a+')';}
  function glow(x,y,r,col,a){const g=c.createRadialGradient(x,y,0,x,y,r);g.addColorStop(0,rgba([1,1,1],a));g.addColorStop(.12,rgba(col,a*.95));g.addColorStop(.38,rgba(col,a*.36));g.addColorStop(1,rgba(col,0));c.fillStyle=g;c.fillRect(x-r,y-r,r*2,r*2);}
  function orbit(i,radius,alpha,width){
    const tilt=.48+i*.70,turn=i*1.08+time*.04;
    for(let j=0;j<160;j++){
      const th=j/160*Math.PI*2+ph.c*.12,th2=(j+1)/160*Math.PI*2+ph.c*.12;
      function pos(a){const x=Math.cos(a)*radius,y=Math.sin(a)*radius*Math.sin(tilt),z=Math.sin(a)*radius*Math.cos(tilt);return[x*Math.cos(turn)-y*Math.sin(turn),x*Math.sin(turn)+y*Math.cos(turn),z];}
      const a=pos(th),b=pos(th2),p=pt(a),q=pt(b);
      c.strokeStyle=rgba(cur.colors[i],alpha*(.50+.50*(a[2]/radius*.5+.5)));c.lineWidth=width*k;
      c.beginPath();c.moveTo(...p);c.lineTo(...q);c.stroke();
      if(j%8===0){c.fillStyle=rgba(cur.colors[i],.7);c.fillRect(p[0],p[1],1.8*k,1.8*k);}
    }
    // A narrow deterministic particle band retains depth in the no-WebGL renderer.
    for(let j=0;j<440;j++){
      const th=j/440*Math.PI*2+ph.c*.18;
      const r=radius+(Math.sin(j*12.9898+i*78.233)+Math.sin(j*4.173))*.012;
      const x=Math.cos(th)*r,y=Math.sin(th)*r*Math.sin(tilt),z=Math.sin(th)*r*Math.cos(tilt);
      const p=pt([x*Math.cos(turn)-y*Math.sin(turn),x*Math.sin(turn)+y*Math.cos(turn),z]);
      const depth=.55+.45*(z/radius*.5+.5),size=(.7+(j%5)*.21)*k;
      c.fillStyle=rgba(cur.colors[i],(.25+.40*depth)*(.7+cur.act[i]*.4));c.fillRect(p[0],p[1],size,size);
    }
  }
  c.globalCompositeOperation='lighter';
  const cyan=[.22,.88,1],violet=[.68,.38,1];
  // The fallback uses the same paths and light packets as the WebGL circuit bus.
  for(let lane=0;lane<28;lane++){
    c.beginPath();
    for(let j=0;j<=80;j++){
      const x=(j/80*2-1)*1.52,wave=Math.sin(x*2.6-time*.45+lane*.11);
      const p=pt([x,-.87+wave*.11+lane*.004,-.30+lane*.006]);
      if(j)c.lineTo(...p);else c.moveTo(...p);
    }
    c.strokeStyle=rgba(cyan,.10);c.lineWidth=.7*k;c.stroke();
  }
  for(let band=0;band<5;band++){
    c.beginPath();
    for(let j=0;j<=120;j++){
      const th=j/120*Math.PI*2,r=.63+band*.13,p=pt([Math.cos(th)*r,-1.02+band*.008,Math.sin(th)*r*.40]);
      if(j)c.lineTo(...p);else c.moveTo(...p);
    }
    c.strokeStyle=rgba(cyan,.35-band*.04);c.lineWidth=1.2*k;c.stroke();
  }
  glow(...o,unit*.50,cyan,.18);
  for(let band=0;band<3;band++)for(let j=0;j<180;j++){
    if(j%15<3)continue;
    const radius=.57+band*.052,th=j/180*Math.PI*2+ph.c*.13*(band===1?-1:1);
    const a=pt([Math.cos(th)*radius,Math.sin(th)*radius,.08]);
    const b=pt([Math.cos(th+.035)*radius,Math.sin(th+.035)*radius,.08]);
    const head=Math.pow(.5+.5*Math.cos(th*2-ph.c*.7+band),24);
    c.strokeStyle=rgba(band===1?violet:cyan,.4+head*.6);c.lineWidth=(1+head*1.6)*k;
    c.beginPath();c.moveTo(...a);c.lineTo(...b);c.stroke();
  }
  for(let lane=-9.5;lane<10;lane++)for(const sgn of [-1,1]){
    c.beginPath();const top=Math.sqrt(Math.max(0,.47*.47-lane*lane*.038*.038));
    for(let j=0;j<=24;j++){
      const u=j/24,x=lane*.038+Math.sign(lane)*.025*(u>.25&&u<.7?1:0),y=sgn*top*(.92-u*.56);
      const p=pt([x,y,Math.sqrt(Math.max(0,.47*.47-x*x-y*y))]);
      if(j)c.lineTo(...p);else c.moveTo(...p);
    }
    c.strokeStyle=rgba(lane<0?cyan:violet,.42);c.lineWidth=.8*k;c.stroke();
  }
  for(let i=0;i<4;i++){
    if(i<3)orbit(i,.78,.12+cur.act[i]*.18,.8);
    const s=pt(SLOTS[i]),col=cur.colors[i],radius=unit*.11;
    for(let lane=-3;lane<=3;lane++){
      const path=tracePoints(i,lane).map(pt);
      c.beginPath();c.moveTo(...path[0]);path.slice(1).forEach(p=>c.lineTo(...p));
      c.strokeStyle=rgba(col,.35+cur.act[i]*.35);c.lineWidth=1.05*k;c.shadowColor=rgba(col,.7);c.shadowBlur=5*k;c.stroke();c.shadowBlur=0;
      for(const end of [path[0],path[3]]){c.beginPath();c.arc(...end,1.8*k,0,7);c.fillStyle=rgba(col,.9);c.fill();}
      for(let j=0;j<3;j++){
        const u=((j/3-ph.s[i]*.85-lane*.028)%1+1)%1,p=pt(tracePoint(i,lane,u));
        glow(...p,(5+cur.act[i]*3)*k,col,.65);
        c.fillStyle=rgba([.8,1,1],.95);c.fillRect(p[0]-k,p[1]-k,2*k,2*k);
      }
    }
    c.shadowColor=rgba(col,.8);c.shadowBlur=12*k;
    c.beginPath();c.arc(s[0],s[1],radius*.63,0,Math.PI*2);c.strokeStyle=rgba(col,.95);c.lineWidth=1.5*k;c.stroke();
    c.shadowBlur=0;glow(s[0],s[1],radius*2,col,.88);
    c.shadowColor=rgba(col,.9);c.shadowBlur=8*k;c.strokeStyle=rgba(col,.8);c.lineWidth=.8*k;
    c.beginPath();c.moveTo(s[0]-radius*1.6,s[1]);c.lineTo(s[0]+radius*1.6,s[1]);
    c.moveTo(s[0],s[1]-radius*1.3);c.lineTo(s[0],s[1]+radius*1.3);c.stroke();c.shadowBlur=0;
    for(let j=0;j<70;j++){
      const a=j*2.399+time*.06,r=radius*.58*Math.sqrt(j/70);
      c.fillStyle=rgba(col,.65);c.fillRect(s[0]+Math.cos(a)*r,s[1]+Math.sin(a)*r,1.6*k,1.6*k);
    }
    for(let j=0;j<24;j++){
      const t=(j/24+ph.s[i])%1,e=t*t*(3-2*t);
      c.fillStyle=rgba(col,(.16+.65*cur.act[i])*Math.sin(Math.PI*t));c.beginPath();
      c.arc(s[0]+(o[0]-s[0])*e,s[1]+(o[1]-s[1])*e,(1+cur.act[i])*k,0,7);c.fill();
    }
  }
  glow(o[0],o[1],unit*.14,[.2,.9,1],.7+cur.core*.2);
  c.globalCompositeOperation='source-over';
}

function init(el,opts){
  canvas=el;onFrame=(opts&&opts.onFrame)||null;
  if(window.matchMedia&&window.matchMedia('(prefers-reduced-motion: reduce)').matches){timeScale=0;boot=1;}
  try{
    gl=canvas.getContext('webgl2',{antialias:false,alpha:false,powerPreference:'high-performance'});
    if(!gl)throw Error('WebGL2 unavailable');
    hdr=!!(gl.getExtension('EXT_color_buffer_float')||gl.getExtension('EXT_color_buffer_half_float'));
    progP=program(VS_POINTS,FS_POINTS);progB=program(VS_FULL,FS_BLUR);progC=program(VS_FULL,FS_COMP);
    uP=uniforms(progP,['uVP','uTime','uPx','uCore','uVerify','uPulse','uBoot','uPhC','uSlot[0]','uColor[0]','uAct','uEdge','uPhS','uPhE','uPhN','uPulseColor']);
    uB=uniforms(progB,['uTex','uDir']);uC=uniforms(progC,['uScene','uB1','uB2','uRes','uCenter','uTime','uCore','uPulse','uTint','uPulseColor']);
    buildGeometry();
    if(!listening){
      canvas.addEventListener('webglcontextlost',e=>{e.preventDefault();cancelAnimationFrame(raf);running=false;});
      canvas.addEventListener('webglcontextrestored',()=>{size=[0,0];fb={};init(canvas,{onFrame});});
    }
  }catch(err){
    failed=true;gl=null;flat=canvas.getContext('2d');
    // A canvas that already acquired WebGL cannot switch to 2D after a shader/context failure.
    if(!flat){const replacement=canvas.cloneNode(false);canvas.replaceWith(replacement);canvas=replacement;flat=canvas.getContext('2d');}
    if(window.console)console.warn('Trinity: WebGL2 fallback to 2D -',err.message);
  }
  if(!listening){listening=true;window.addEventListener('pointermove',e=>{mouse[0]=(e.clientX/window.innerWidth-.5)*2;mouse[1]=(e.clientY/window.innerHeight-.5)*2;},{passive:true});}
  size=[0,0];resize();
  if(!running){running=true;last=performance.now();raf=requestAnimationFrame(frame);}
  return {webgl:!failed,hdr};
}
function set(s){
  if(s.act)for(let i=0;i<3;i++)tgt.act[i]=s.act[i];
  if(s.edge)for(let i=0;i<3;i++)tgt.edge[i]=s.edge[i];
  if(s.core!=null)tgt.core=s.core;if(s.verify!=null)tgt.verify=s.verify;
  if(s.colors)for(let i=0;i<3;i++)tgt.colors[i]=s.colors[i].slice();
}
return {init,set,
  auxiliary(s){
    if(s.act!=null&&Number.isFinite(s.act))tgt.act[3]=Math.max(0,Math.min(1,s.act));
    if(s.color?.length===3&&s.color.every(Number.isFinite))tgt.colors[3]=s.color.slice();
  },
  pulse(color){pulse=1;pulseColor=(color||[1,1,1]).slice();},
  motion(on){timeScale=on?1:0;boot=1;},
  focus(r){rect=r;},                                  // stage rect inside the canvas, normalised {x,y,w,h}
  step(sec){for(let s=0;s<sec;s+=1/30){time+=1/30;approach(1/30);}render(0);},   // deterministic advance (captures, hidden tabs)
  state(){return {cur,tgt,pulse,boot,time,size:size.slice(),hdr,webgl:!failed,points:total};}};
})();
