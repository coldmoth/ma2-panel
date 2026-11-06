'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs');
const prefix = fs.readFileSync('tests/panel-v4.cjs', 'utf8').split('// Empty workspace:')[0];
const {context:c,ws,page,findBtn} = new Function('require', prefix + '\nreturn {context,ws,page,findBtn};')(require);
const status = {ma2:'logged_in',show:{name:'Atlas'},safety:{mode:'full'},features:{}};
const cfg = {show:'Atlas',revision:'epoch:1',fixtures:[{id:1,label:'Head',type:'H',address:'1.1',moves:true,params:['Dimmer','Pan','Tilt']},{id:2,label:'Dimmer',type:'D',params:['Dimmer']}],groups:[],scenes:[],presets:[],attrs:{pan:{min:-270,max:270},tilt:{min:-135,max:135}}};
c.receive({status,config:structuredClone(cfg)}); c.go('light'); c.selectFixtures([1]);
const old=ws(); old.onclose(); c.connect();
assert.equal(c.connected(),false,'a new socket must wait for fresh config');
c.receive({status}); assert.equal(c.connected(),false,'status alone cannot validate selection');
c.receive({config:structuredClone(cfg)});
assert.deepEqual(Array.from(c.state.selection),[1],'same identity restores intent');
assert.equal(c.connected(),false,'controls wait for bridge selection acknowledgement');
const sync=ws().sent.at(-1); assert.equal(sync.a,'select_fixtures');
assert.deepEqual(Array.from(sync.ids),[1]);
c.receive({a:sync.a,request_id:sync.request_id,ok:true});
assert.equal(c.connected(),true);
assert.equal(findBtn('25%').disabled,false,'ACK must enable rendered controls, not only connected()');
assert.deepEqual(ws().sent.map(x=>x.a),['select_fixtures'],'no control replay');
// Reused fixture IDs are not identity. A changed patch discards the entire old intent.
ws().onclose(); c.connect(); const changed=structuredClone(cfg); changed.fixtures[0].address='2.1';
c.receive({status,config:changed});
assert.deepEqual(Array.from(c.state.selection),[]); assert.equal(ws().sent.length,0);
// A live config update also cannot silently retarget selected IDs.
c.selectFixtures([1]); const live=structuredClone(changed); live.fixtures[0].type='Replacement'; c.receive({config:live});
assert.deepEqual(Array.from(c.state.selection),[]);
// A static fixture has no dead movement tab, including after a head was selected.
c.selectFixtures([2]); c.lightUI.controlTab='movement'; c.render();
assert.equal(findBtn('Движение'),undefined); assert.equal(page.all().some(n=>n.className==='pad'),false);
assert.ok(findBtn('25%'));
console.log('stage atlas: validated reconnect, reused IDs, live changes and static capabilities passed');

// Explicit Group must never leave the controls pointing at the prior local selection.
cfg.ma2groups=[{n:1,name:'Group',ids:[1]}]; c.receive({config:structuredClone(cfg)});
c.selectFixtures([2]); c.lightUI.tab='groups';c.render();
findBtn('На MA2').click();
assert.equal(ws().sent.at(-1).a,'ma2_group_go');
assert.deepEqual(Array.from(c.state.selection),[1]);assert.equal(c.connected(),false);
assert.equal(c.send({a:'dim',v:50}),false,'old controls cannot act while Group is unresolved');
let groupAction=ws().sent.at(-1);c.receive({a:groupAction.a,request_id:groupAction.request_id,ok:true});
assert.equal(c.connected(),true);assert.equal(findBtn('25%').disabled,false);
// Stop during reconnect selection sync cancels both the pending request and its lock.
ws().onclose();c.connect();c.receive({status,config:structuredClone(cfg)});
const late=ws().sent.at(-1);assert.equal(c.connected(),false);
c.discardPending();c.receive({status:{...status,halted:true}});c.receive({status});
assert.equal(c.connected(),true);assert.deepEqual(Array.from(c.state.selection),[]);
c.receive({a:late.a,request_id:late.request_id,ok:true});assert.deepEqual(Array.from(c.state.selection),[]);
console.log('review regressions: Group target, real control unlock and cancelled selection sync passed');

// Editing movement calibration must not turn the selected fixtures into a different target.
c.receive({config:structuredClone(cfg)});c.selectFixtures([1]);
const inversion=structuredClone(cfg);inversion.fixtures[0].flip_pan=true;inversion.fixtures[0].beam={home:50};
c.receive({config:inversion});assert.deepEqual(Array.from(c.state.selection),[1],'movement settings retain selection');

// Supported optics stay available even when a fixture has no Pan/Tilt.
const optics=structuredClone(cfg);
optics.fixtures.push({id:3,label:'Static optics',type:'O',params:['Dimmer','Zoom','Focus']});
c.receive({config:optics});c.lightUI.controlTab='light';c.selectFixtures([3]);
assert.ok(page.all().some(n=>n.classList.contains('c-zoom')),'static Zoom is reachable');
assert.ok(page.all().some(n=>n.classList.contains('c-focus')),'static Focus is reachable');
assert.equal(findBtn('Движение'),undefined,'optics never imply Pan/Tilt');

// The overview follows readback without rebuilding the plan or retaining stale activity.
const overview=structuredClone(cfg);overview.scenes=[{id:'live',exec:'1.101',label:'Live overview'}];
c.receive({config:overview});c.selectFixtures([]);
c.receive({running:{live:true},running_meta:{live:{source:'ma2',freshness:'fresh',updated_at:1}}});
assert.match(page.textContent,/Live overview/,'fresh running readback appears in the overview');
c.receive({running:{live:null},running_meta:{live:{source:'ma2',freshness:'stale',updated_at:1}}});
assert.doesNotMatch(page.textContent,/Live overview/,'stale readback never looks active');
