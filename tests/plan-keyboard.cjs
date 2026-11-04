'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const prefix=fs.readFileSync('tests/panel-v4.cjs','utf8').split('// Empty workspace:')[0];
const {context:c,document,ws}=new Function('require',prefix+'\nreturn {context,document,ws};')(require);
c.receive({status:{ma2:'logged_in',safety:{mode:'full'},features:{}}});
c.receive({config:{revision:'e:1',fixtures:[{id:1,label:'Голова',moves:true,x:.4,y:.4}],groups:[],scenes:[],presets:[],attrs:{}}});
let taps=0;const original=c.tapFixture;c.tapFixture=(...args)=>{taps++;original(...args);};
function widget(mode){const root=document.createElement('div');c.hallPlan(root,mode);c.updaters.forEach(fn=>fn());const hall=root.all().find(n=>n.className==='hall'),dot=root.all().find(n=>n.dataset.id==='1');dot.closest=()=>dot;return {hall,dot};}
let {hall,dot}=widget('control');
dot.fire('click',{detail:0});assert.equal(taps,1,'keyboard invokes tapFixture');
assert.deepEqual(Array.from(c.state.selection),[1]);
dot.fire('click',{detail:0});assert.deepEqual(Array.from(c.state.selection),[]);
function fire(type,x=40,y=40){hall.fire(type,{target:dot,pointerId:1,button:0,clientX:x,clientY:y});}
fire('pointerdown');fire('pointerup');dot.fire('click',{detail:1});assert.equal(taps,3,'native pointer click does not duplicate tap');
({hall,dot}=widget('edit'));c.planState.tab='place';
let before=ws().sent.length;fire('pointerdown');fire('pointermove',70,70);fire('pointerup',70,70);dot.fire('click',{detail:1});
assert.equal(taps,3,'drag never taps');assert.equal(ws().sent.slice(before).filter(a=>a.a==='layout_save').length,1);
before=ws().sent.length;fire('pointerdown');fire('pointermove',80,80);fire('pointercancel',80,80);dot.fire('click',{detail:1});
assert.equal(ws().sent.slice(before).filter(a=>a.a==='layout_save').length,0);
dot.disabled=true;dot.fire('click',{detail:0});assert.equal(taps,3,'disabled fixture never taps');dot.disabled=false;
fire('pointerdown');c.state.ma2='down';fire('pointerup');dot.fire('click',{detail:0});assert.equal(taps,3,'offline gesture/activation never taps');
console.log('plan keyboard and pointer: activation, no double tap, drag/cancel/offline passed');
