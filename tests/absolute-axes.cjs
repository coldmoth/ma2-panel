// Focused movement interaction tests: render must not move lights, each axis is independent.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
class El {
  constructor(tag) { this.tagName=tag; this.children=[]; this.events={}; this.dataset={}; this.attrs={}; this.style={}; this.className=''; this.value='50';
    this.classList={toggle:(key,on)=>{ const s=new Set(this.className.split(' ').filter(Boolean)); on?s.add(key):s.delete(key); this.className=[...s].join(' '); },contains:key=>this.className.split(' ').includes(key)}; }
  appendChild(n) { this.children.push(n); n.parentNode=this; return n; }
  set textContent(v) { this.text=String(v); this.children=[]; } get textContent() { return (this.text||'')+this.children.map(n=>n.textContent).join(''); }
  setAttribute(k,v) { this.attrs[k]=String(v); } addEventListener(k,f) { (this.events[k]||= []).push(f); }
  fire(k,event={}) { (this.events[k]||[]).forEach(f=>f({preventDefault(){},...event})); }
  querySelectorAll(){return [];} getBoundingClientRect(){return {width:200,height:200};} releasePointerCapture(){} setPointerCapture(){}
}
let ready=true, sent=[], now=1000, timers=[];
const document={createElement:t=>new El(t),addEventListener(){},activeElement:null};
const c=vm.createContext({document,console,Math,Number,performance:{now:()=>now},setInterval:()=>1,clearInterval(){},setTimeout:fn=>{timers.push(fn);return timers.length;},clearTimeout:id=>{if(id)timers[id-1]=null;},
  state:{selection:[1,2],shown:{1:{pan:10,tilt:20},2:{pan:60,tilt:20}},config:{fixtures:[{id:1,moves:true},{id:2,moves:true}],attrs:{pan:{min:-270,max:270},tilt:{min:-135,max:135}},presets:[]}},
  confirm:()=>true,canMove:f=>f.moves,connected:()=>ready,featureReason:()=>'',busy:a=>Object.values(c.pending).some(request=>request.a===a),pending:{},fixtures:()=>[],attributeVisible:()=>true,toolVisible:()=>true,split:()=>({yes:[{id:1},{id:2}],no:[]}),sliderChannels:{},
  setFill:(n,v)=>{n.classList.toggle('unknown',typeof v!=='number'); if(typeof v==='number')n.value=v;},cancelSlider(){},send:a=>{sent.push(a);return true;},throttleSlider:a=>sent.push(a)});
vm.runInContext(fs.readFileSync('static/move.js','utf8'),c);
const root=new El('div'); c.renderMove(root);
assert.ok(c.moveState.els.modeAbsolute,'movement has an absolute mode selector');
c.moveState.els.modeAbsolute.fire('click');
const axis=c.moveState.els.axes;
assert.equal(sent.length,0,'rendering or switching modes never sends movement');
assert.match(axis.pan.output.textContent,/Разные/); assert.match(axis.tilt.output.textContent,/-81/);
axis.pan.input.fire('keydown',{key:'ArrowRight'});axis.pan.input.value='75'; axis.pan.input.fire('input');
assert.equal(sent.length,1); assert.equal(sent[0].a,'aim'); assert.equal(sent[0].pan,135); assert.equal('tilt' in sent[0],false);
c.state.shown={1:{pan:75},2:{pan:75}}; c.renderMove(root);
assert.match(axis.tilt.output.textContent,/неизвестно/); assert.equal(axis.tilt.input.disabled,false,'unknown position still accepts an explicit absolute target');
ready=false;c.renderMove(root);axis.pan.input.fire('input'); assert.equal(sent.length,1,'disconnection blocks input');
ready=true;c.renderMove(root);
axis.pan.input.fire('pointerdown',{pointerId:4,button:0});
c.state.selection=[2]; c.renderMove(root);axis.pan.input.value='10';axis.pan.input.fire('input');
assert.equal(sent.length,1,'a selection change cancels the active touch');
axis.pan.input.fire('pointerup',{pointerId:4});axis.pan.input.fire('keydown',{key:'ArrowRight'});axis.pan.input.fire('input');
now=1200; timers.filter(Boolean).forEach(fn=>fn());timers=[];
assert.equal(sent.length,2,'a fresh keyboard action works after cancellation');
axis.pan.input.fire('pointerdown',{pointerId:5,button:0});axis.pan.input.fire('pointercancel',{pointerId:5});axis.pan.input.fire('input');
assert.equal(sent.length,2,'touch cancellation prevents a trailing input');
// Repeated input keeps only the latest value per axis; another axis still sends independently.
axis.pan.input.fire('keydown',{key:'ArrowRight'});axis.pan.input.value='20';axis.pan.input.fire('input');
axis.pan.input.value='30';axis.pan.input.fire('input');
axis.tilt.input.fire('keydown',{key:'ArrowRight'});axis.tilt.input.value='50';axis.tilt.input.fire('input');
assert.equal(sent.at(-1).tilt,0);
now=1400;timers.filter(Boolean).forEach(fn=>fn());timers=[];
assert.equal(sent.at(-1).pan,-108);
const count=sent.length;
axis.pan.input.value='40';axis.pan.input.fire('input');
c.state.selection=[1];c.renderMove(root);now=1600;timers.filter(Boolean).forEach(fn=>fn());timers=[];
assert.equal(sent.length,count,'selection change cancels a queued absolute target');
console.log('absolute axes: independent targets, honest states, connection and gesture cancellation passed');

// An old management row must not acquire permission to delete from a newer plan.
c.state.config={...c.state.config,revision:7,presets:[{id:'saved',label:'Старая позиция',pos:{1:{pan:50,tilt:50}}}]};
c.moveState.manage=true;c.renderMove(root);
const oldDelete=c.moveState.els.presets.children[0].children[1];
c.state.config={...c.state.config,revision:8};
oldDelete.fire('click');
assert.equal(sent.at(-1).a,'preset_delete');
assert.equal(sent.at(-1).config_revision,7,'stale preset delete keeps the revision displayed to the operator');
c.state.shown={1:{pan:50,tilt:50}};
c.pending={'browser:123':{a:'preset_save'}};c.renderMove(root);
assert.equal(c.moveState.els.save.disabled,true,'a request-ID keyed pending save disables duplicate saving');
c.pending={};c.renderMove(root);
assert.equal(c.moveState.els.save.disabled,false,'save becomes available again when the request finishes');
console.log('movement presets: stale deletion revision and request-ID pending save passed');
