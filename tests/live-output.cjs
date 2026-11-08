'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const prefix = fs.readFileSync('tests/panel-v4.cjs', 'utf8').split('// Empty workspace:')[0];
const {context:c, document, status, ws} = new Function('require', prefix + '\nreturn {context,document,status,ws};')(require);
status();
c.receive({config:{show:'Live test', fixtures:[{id:1,type:'LED',x:.3,y:.3},{id:2,type:'LED',x:.6,y:.3}],groups:[],scenes:[],presets:[],attrs:{}}});
c.state.selection=[1];
const sent=ws().sent.length;
c.receive({tracked:false,shown:{},live:{1:{dim:10,rgb:[0,100,0]}},values_meta:{shown:{source:'unknown',freshness:'unknown'},live:{source:'ma2',freshness:'fresh',updated_at:1}}});
assert.equal(c.known('dim'),10,'fresh readback must survive the scene clearing panel history');
assert.equal(c.known('color'),'0,100,0');
c.updaters=[];
const slider=c.sliderCard('dim','Яркость','%',true), color=c.colorCard();
c.updaters.forEach(fn=>fn());
assert.match(slider.textContent,/10%/);
assert.match(slider.textContent,/прочитано с MA2/i);
assert.match(color.textContent,/R 0 · G 100 · B 0/);
assert.match(color.textContent,/прочитано с MA2/i);

// A conflicting last panel command must not replace measured output or its label.
c.receive({tracked:true,shown:{1:{dim:90,rgb:[100,0,0]}},values_meta:{shown:{source:'panel',freshness:'fresh'}}});
assert.equal(c.known('dim'),10);
assert.equal(c.known('color'),'0,100,0');
c.state.selection=[1,2];
c.state.live[2]={dim:80,rgb:[100,0,100]};
assert.equal(c.known('dim'),'mixed');
assert.equal(c.known('color'),'mixed');
delete c.state.live[2];
assert.equal(c.known('dim'),'mixed','partly missing output must not be filled from panel history');

c.state.selection=[1];c.updaters=[];
const plan=document.createElement('div');c.hallPlan(plan,'control');
c.updaters.forEach(fn=>fn());
let lit=plan.all().find(n=>n.classList.contains('lit'));
assert.ok(lit);
assert.equal(lit.style['--c'],'rgba(0,255,0,0.1)','10% output must not glow at the old 25% minimum');
c.state.live[1].dim=0;c.updaters.forEach(fn=>fn());
assert.equal(plan.all().some(n=>n.classList.contains('lit')),false,'zero output is dark');

c.receive({tracked:false,shown:{},values_meta:{shown:{source:'unknown',freshness:'unknown'},live:{source:'ma2',freshness:'stale'}}});
assert.equal(c.known('dim'),null);
assert.equal(c.known('color'),null);
c.updaters.forEach(fn=>fn());
assert.equal(plan.all().some(n=>n.classList.contains('lit')),false);
assert.equal(ws().sent.length,sent,'display updates must never send light commands');
console.log('live output: measured dim/RGB after scenes, source, mixed/missing, stale and proportional plan glow passed');
