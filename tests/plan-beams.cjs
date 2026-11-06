'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs');
const prefix = fs.readFileSync('tests/panel-v4.cjs', 'utf8').split('// Empty workspace:')[0];
const {context:c, document} = new Function('require', prefix + '\nreturn {context,document};')(require);
c.receive({status:{ma2:'logged_in',safety:{mode:'full'}}});
const f = {id:1,label:'Head',moves:true,x:.25,y:.5,beam:{home:50,invert:false}};
c.receive({config:{fixtures:[f,{id:2,moves:false,x:.5,y:.5}],hall:{w:20,d:10,stage:'top'},attrs:{pan:{min:-270,max:270}}}});
c.state.shown = {1:{pan:50}};
const close=(actual,expected)=>assert(Math.abs(actual-expected)<1e-8, `${actual} != ${expected}`);
for(const [stage,x,y] of [['top',10,1.5],['bottom',10,8.5],['left',1.5,5],['right',18.5,5]]) {
  c.state.config.hall.stage=stage;
  const expected=Math.atan2(y-f.y*10,x-f.x*20)*180/Math.PI;
  close(c.planBeamAngle(f,c.state.config.hall),expected);
  c.state.shown[1].pan=60;close(c.planBeamAngle(f,c.state.config.hall),expected+54);
  f.beam.invert=true;close(c.planBeamAngle(f,c.state.config.hall),expected-54);
  c.state.shown[1].pan=50;f.beam.invert=false;
}
c.state.config.hall.stage='top';

function widget(mode) {
  c.updaters.length=0;
  const root=document.createElement('div'); c.hallPlan(root,mode);
  const update=()=>c.updaters.forEach(fn=>fn()); update();
  const beams=root.all().filter(n=>n.className.split(' ').includes('plan-beam'));
  assert.equal(beams.length,1,'only moving placed fixtures get beam geometry');
  return {root,beam:beams[0],update};
}
for (const mode of ['control','edit']) {
  const {root,beam,update}=widget(mode);
  assert.equal(beam.hidden,false);
  assert.match(root.textContent,/Расчётное направление.*Pan/);
  const home=beam.style.transform;
  c.state.shown[1].pan=60;update(); assert.notEqual(beam.style.transform,home);
  const normal=beam.style.transform; f.beam.invert=true;update();assert.notEqual(beam.style.transform,normal);
  f.beam.home=60;update();assert.equal(beam.style.transform,home,'new calibration takes effect');
  for(const stage of ['left','right','bottom','top']) {
    c.state.config.hall.stage=stage;update();assert.equal(beam.hidden,false);
  }
  c.state.selection=[1];update();assert.ok(beam.className.includes('selected'));
  c.state.valuesMeta={'sent:1:pan':{freshness:'stale'}};update();assert.equal(beam.hidden,true);
  c.state.valuesMeta={};delete c.state.shown[1].pan;update();assert.equal(beam.hidden,true);
  c.state.shown[1]={pan:50,tilt:99};f.beam={home:50,invert:false};update();assert.equal(beam.hidden,false,'Tilt does not invent a projection');
  delete f.beam.home;update();assert.equal(beam.hidden,true);
  f.beam.home=50;f.missing=true;update();assert.equal(beam.hidden,true);delete f.missing;
}
console.log('plan beams: calibration, invert, four stages, selection, stale/unknown, Tilt and missing passed');
