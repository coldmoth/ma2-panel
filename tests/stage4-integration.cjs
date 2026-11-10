'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs');
const prefix = fs.readFileSync('tests/panel-v4.cjs','utf8').split('// Empty workspace:')[0];
const {context:c,document,status,ws} = new Function('require',prefix+'\nreturn {context,document,status,ws};')(require);
const config = {show:'Mock show',revision:'r1',scene_fade:2,fixtures:[{id:1,params:['Dimmer']}],
  groups:[],scenes:[{id:'a',exec:'1.101',label:'Сцена'}],pages:{},presets:[],attrs:{}};
status();c.receive({config});c.go('scenes');
assert.equal(c.sceneFade,2);assert.equal(c.fadeSeconds,2);
let input=document.getElementById('page').all().find(n=>n.getAttribute('aria-label')==='Время перехода, секунды');
input.value='5';input.fire('change');
assert.equal(ws().sent.at(-1)?.a,'scene_fade','Fade must reach the shared server value, not only local scene_go');
assert.equal(ws().sent.at(-1).fade,5);
assert(c.CONFIG_WRITES.includes('scene_fade'),'shared Fade uses revision/serial-write protocol');
const save=ws().sent.at(-1);
c.receive({config:{...config,revision:'r2',scene_fade:5}});
c.receive({a:'scene_fade',request_id:save.request_id,ok:true,outcome:'completed'});
assert.equal(c.sceneFade,5);assert.equal(c.fadeSeconds,5);
c.go('light');
assert.equal(document.getElementById('page').all().find(n=>n.getAttribute('aria-label')==='Время перехода, секунды').value,'5');
// Another client can change the shared Fade without a page reload.
c.receive({config:{...config,revision:'r3',scene_fade:10}});
assert.equal(c.sceneFade,10);assert.equal(c.fadeSeconds,10);
console.log('stage4 integration: persisted shared Fade and cross-client updates passed');
// Cancelling a gesture must still allow a new swatch/slider gesture in the preserved card.
c.receive({config:{...config,revision:'r4',fixtures:[{id:1,color:'rgb',params:['Dimmer','ColorRGB_Red','ColorRGB_Green','ColorRGB_Blue']}]}});
c.selectFixtures([1]);c.go('light');
const nodes=()=>document.getElementById('page').all();
const red=nodes().find(n=>n.getAttribute('aria-label')==='Красный');
c.cancelTargetControls();
let count=ws().sent.length;
red.click();assert.equal(ws().sent.length,count,'an old interrupted click cannot restart the colour');
red.fire('pointerdown',{pointerId:1});red.click();red.fire('pointerup',{pointerId:1});
assert.equal(ws().sent.at(-1)?.a,'color','new swatch works without reconstructing the card');
const saturation=nodes().find(n=>n.getAttribute('aria-label')==='Насыщенность');
c.cancelTargetControls();count=ws().sent.length;
saturation.value='70';saturation.fire('input');assert.equal(ws().sent.length,count);
saturation.fire('pointerdown',{pointerId:2});saturation.fire('input');
assert.equal(ws().sent.length,count+1,'new RGB slider uses its own gesture generation');
saturation.fire('pointerup',{pointerId:2});

// A restart/unknown Grand Master journal must never look like the idle state.
status({blackout:{phase:'unknown',reason:'Проверьте Grand Master на MA2 вручную'}});
assert.equal(document.getElementById('blackout').disabled,true);
assert.match(document.getElementById('banners').textContent,/Проверьте Grand Master/);
// Recovery must allow reading/confirming identity while every light action is blocked.
c.receive({status:{ma2:'logged_in',recovering:true,safety:{mode:'full',allow_fixture_read:true},features:{}}});
assert.equal(c.connected(),false);
assert.equal(c.send({a:'dim',v:100}),false);
assert.equal(c.send({a:'fixtures_fetch'}),true,'read Patch is available during recovery');
const read=ws().sent.at(-1);
c.receive({a:'fixtures_fetch',request_id:read.request_id,ok:false,ambiguous:[{new_id:23,candidates:[{old_id:23,label:'Old'}]}],request_token:'recovery'});
c.state.fetch.choices={'23':null};
const choices=c.fixtureImportChoices(c.state.fetch);
const confirm=choices.all().find(n=>n.tagName==='BUTTON'&&n.textContent==='Применить выбор');
assert.equal(confirm.disabled,false,'identity confirmation is reachable during recovery');
assert.equal(c.send({a:'import_confirm_merge',request_token:'recovery',choices:{'23':null}}),true);
assert.equal(c.send({a:'scene_go',id:'a'}),false);
console.log('recovery UI: read/identity confirmation available, light remains blocked');
