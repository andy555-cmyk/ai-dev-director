const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
let replaced=false;
const replacement={clientWidth:800,clientHeight:600,getContext:kind=>kind==='2d'?{}:null};
const brokenCanvas={clientWidth:800,clientHeight:600,getContext:()=>null,cloneNode:()=>replacement,replaceWith:c=>{assert.equal(c,replacement);replaced=true;}};
const window={devicePixelRatio:1,addEventListener:()=>{},matchMedia:()=>({matches:false})};
const context={window,document:{hidden:false,body:{dataset:{view:'stage'}}},Image:class{},performance:{now:()=>0},requestAnimationFrame:()=>1,cancelAnimationFrame:()=>{},Float32Array,Math,console:{warn:()=>{}}};
vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'../../console/trinity.js'),'utf8'),context);
const result=window.Trinity.init(brokenCanvas);
assert.equal(result.webgl,false);assert.equal(replaced,true);
window.Trinity.motion(false);window.Trinity.motion(true);
console.log('HUD renderer recovers a non-switchable WebGL canvas: PASS');

// Exercise the fourth node through the same frame callback used to pin its card.
function renderer(webgl){
 const arcs=[],uniforms={},buffers=[];let geometry,frame;
 const c2d=new Proxy({createRadialGradient:()=>({addColorStop(){}}),arc:(...args)=>arcs.push(args)},{get:(o,k)=>o[k]||(()=>{})});
 const gpu=new Proxy({
  getShaderParameter:()=>true,getProgramParameter:()=>true,getExtension:()=>null,
  checkFramebufferStatus:()=> 'FRAMEBUFFER_COMPLETE',getUniformLocation:(_,name)=>name,
  bufferData:(_,data)=>{geometry=data;},
  uniform3fv:(name,data)=>{uniforms[name]=Array.from(data);},
  uniform4fv:(name,data)=>{uniforms[name]=Array.from(data);}
 },{get:(o,k)=>o[k]||(k===k.toUpperCase()?k:(()=>({})))});
 const el={clientWidth:1000,clientHeight:800,getContext:k=>k==='webgl2'?(webgl?gpu:null):c2d,addEventListener(){}};
 const win={devicePixelRatio:1,addEventListener(){},matchMedia:()=>({matches:false})};
 const ctx={...context,window:win};
 vm.runInNewContext(fs.readFileSync(path.resolve(__dirname,'../../console/trinity.js'),'utf8'),ctx);
 const t=win.Trinity;t.init(el,{onFrame:f=>{frame=f;}});
 t.auxiliary({act:1,color:[.79,.84,.96]});
 t.set({act:[.2,.4,.6],edge:[1,0,0],colors:[[1,0,0],[0,1,0],[0,0,1]]});
 t.step(2);
 assert.equal(frame.slots.length,4);assert.ok(frame.slots[3][0]>frame.core[0]&&frame.slots[3][1]<frame.core[1]);
 assert.ok(t.state().cur.act[3]>.99);assert.equal(t.state().tgt.act[3],1);
 assert.equal(t.state().tgt.edge.length,3);
 if(webgl){
  assert.equal(uniforms.uAct.length,4);assert.equal(uniforms.uPhS.length,4);assert.equal(uniforms.uPhN.length,4);
  assert.equal(uniforms['uSlot[0]'].length,12);assert.equal(uniforms['uColor[0]'].length,12);
  assert.equal(uniforms.uEdge.length,3);
  assert.ok(t.state().points<=125000,'Keep the expanded particle scene within its GPU budget');
  for(let i=0;i<geometry.length;i+=6)if(geometry[i+5]===3)buffers.push(geometry[i+4]);
  assert.equal(buffers.filter(k=>k===1).length,4500);assert.equal(buffers.filter(k=>k===2).length,3200);
  assert.ok(buffers.includes(9)&&buffers.includes(13)&&buffers.includes(14));
  for(let owner=0;owner<4;owner++){
   const kinds=[];
   for(let i=0;i<geometry.length;i+=6)if(geometry[i+5]===owner)kinds.push(geometry[i+4]);
   assert.ok(kinds.includes(9)&&kinds.includes(14),'Every AI must have a circuit path and lit terminals');
   assert.equal(kinds.filter(k=>k===13).length,1,'One flare per AI junction bounds bloom overdraw');
  }
 }else{
  assert.ok(arcs.length>100); // Node rings, stream particles and new circuit terminal dots.
  for(const slot of frame.slots)assert.ok(arcs.some(a=>Math.hypot(a[0]-slot[0],a[1]-slot[1])<.001));
 }
 const time=t.state().time;
 t.motion(false);t.auxiliary({act:.25,color:[1,.43,.5]});t.step(0);
 assert.equal(t.state().cur.act[3],.25);assert.equal(t.state().cur.colors[3][0],1);
 assert.equal(t.state().time,time); // Motion off must still apply state changes.
 return t;
}
renderer(true);renderer(false);
console.log('HUD four nodes, lit circuits/terminals, bounded particles, independent research and reduced motion (WebGL/2D): PASS');
