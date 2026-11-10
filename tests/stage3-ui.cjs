// Concert UI regressions against real scripts; browser layout is tested separately.
'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs');
const prefix = fs.readFileSync('tests/panel-v4.cjs','utf8').split('// Empty workspace:')[0];
const {context:c,document,status,ws} = new Function('require',prefix+'\nreturn {context,document,status,ws};')(require);
status();
const cfg = {revision:'r1',show:'Mock show',hall:{w:18,d:14,stage:'top'},
 fixtures:[1,2].map(id=>({id,label:'Прибор '+id,type:'RGB head',params:['Dimmer','ColorRGB_Red','ColorRGB_Green','ColorRGB_Blue','Pan','Tilt','Zoom','Focus'],moves:true,x:id/3,y:.4})),
 groups:[],scenes:[{id:'s',exec:'1.1',label:'Песня'}],pages:[{n:1,label:'Концерт'}],presets:[],attrs:{}};
c.receive({config:cfg});c.go('light');c.selectFixtures([1]);
const page = document.getElementById('page');
const nodes=()=>page.all(), find=label=>nodes().find(n=>n.getAttribute('aria-label')===label);

// A response to an older target must not discard a more recent selection.
const old = ws().sent.at(-1);
c.selectFixtures([2]);
c.receive({ok:false,a:'select_fixtures',request_id:old.request_id,err:'Старый запрос отклонён'});
assert.deepEqual(Array.from(c.state.selection),[2],'old refusal preserves newer selection');

// All target-dependent channels are cancelled, not just dim/color.
c.sliderChannels.zoom={latest:{a:'zoom',v:99},timer:1,sent:0};
c.selectFixtures([1]);
assert.equal(c.sliderChannels.zoom.latest,null,'old zoom never follows new selection');

let range=find('Яркость');
range.fire('pointerdown',{pointerId:1});range.value='73';range.fire('input');
const workspace=page.children[0];
c.receive({config:{...cfg,revision:'r2'},live:{1:{dim:12}},values_meta:{live:{source:'ma2',freshness:'fresh'}}});
assert.equal(page.children[0],workspace,'config broadcast cannot replace a live gesture');
assert.equal(range.value,73,'external values cannot move the thumb during gesture');
range.fire('pointerup',{pointerId:1});

// Typed fields defer structure only. Readback and safety remain live; blur catches up.
const draft=c.h('input',{id:'test-draft',value:'Солист'});page.appendChild(draft);draft.focus();
c.receive({config:{...cfg,revision:'r3',fixtures:cfg.fixtures.map(f=>({...f,label:'Обновлённый '+f.id}))}});
assert.equal(draft.value,'Солист');
status({ma2:'down'});
assert.equal(find('Яркость').disabled,true,'disconnect disables controls even while typing');
let afterBlur;
c.setTimeout=fn=>{afterBlur=fn;return 1;};
draft.blur();draft.fire('blur');assert.equal(typeof afterBlur,'function','blur schedules deferred structure');afterBlur();
assert.match(page.textContent,/Обновлённый 1/,'pending config becomes visible without another WS packet');

status();c.go('scenes');
assert(nodes().some(n=>n.classList.contains('live-plan')),'scene screen exposes the working plan');
const scenesDOM=page.children[0];
c.receive({running:{s:true},running_meta:{s:{source:'ma2',freshness:'fresh'}}});
assert.equal(page.children[0],scenesDOM,'scene readback updates tiles without replacing the plan');
assert(nodes().find(n=>n.classList.contains('tile')).classList.contains('run'));
const tile=nodes().find(n=>n.classList.contains('tile'));
c.send({a:'scene_go',id:'s',fade:5},tile);const transition=ws().sent.at(-1);
status({operations:[{request_id:transition.request_id,stage:'transition'}]});
assert.match(tile.textContent,/переход моста/,'transition comes from the registered bridge operation');
c.receive({ok:true,a:'scene_go',request_id:transition.request_id,outcome:'completed',command_evidence:['sent']});
assert.doesNotMatch(tile.textContent,/переход моста/,'terminal response clears transition feedback');
const fade=nodes().find(n=>n.getAttribute('aria-label')==='Время перехода, секунды');
assert(fade,'one shared transition control');fade.value='5';fade.fire('change');
assert.equal(ws().sent.at(-1).a,'scene_fade');
c.receive({config:{...c.state.config,scene_fade:5}});
assert.equal(c.sceneFade,5);assert.equal(c.fadeSeconds,5);
c.go('light');assert.equal(find('Время перехода, секунды').value,'5');

// An interrupted physical gesture cannot restart itself after a Blackout barrier.
range=find('Яркость');range.fire('pointerdown',{pointerId:2});
range.value='42';range.fire('input',{type:'input'});
c.cancelTargetControls();
const stopped=ws().sent.length;
range.value='91';range.fire('input',{type:'input'});
assert.equal(ws().sent.length,stopped,'late input from an interrupted gesture is discarded');
range.fire('pointerdown',{pointerId:3});range.fire('input',{type:'input'});
assert(ws().sent.length===stopped+1 || c.sliderChannels.dim.latest && c.sliderChannels.dim.latest.v===91,'a new intentional gesture is allowed');
range.fire('pointerup',{pointerId:3});

// Hall form draft survives a remote config and a later blur/rebuild, with explicit conflict.
c.go('hall');nodes().find(n=>n.tagName==='BUTTON'&&n.textContent==='Форма зала').click();
let width=nodes().find(n=>n.id==='hall-w');width.value='25';width.focus();width.fire('input',{type:'input'});
c.receive({config:{...cfg,revision:'r4',hall:{...cfg.hall,w:50}}});
width.blur();width.fire('blur');afterBlur();
width=nodes().find(n=>n.id==='hall-w');assert.equal(width.value,'25');
assert.match(page.textContent,/Ваш черновик сохранён/);
nodes().find(n=>n.tagName==='BUTTON'&&n.textContent==='Отбросить черновик и принять новый план').click();
assert.equal(nodes().find(n=>n.id==='hall-w').value,'50');
c.go('light');

// Unknown capabilities do not pretend to support every attribute.
c.receive({config:{...cfg,fixtures:[{id:1,type:'Unknown',x:.4,y:.4}]}});
c.selectFixtures([1]);
assert.equal(nodes().some(n=>n.getAttribute('aria-label')==='Яркость'),false);
assert.match(page.textContent,/Параметры.*не прочитаны/);
c.receive({config:{...cfg,fixtures:[{id:1,type:'Mapped',params:['Pan'],x:.4,y:.4}],dmx_map:{Mapped:{dim:1,r:2,g:3,b:4,has:['focus']}}}});
assert.equal(c.supports(c.fixture(1),'dim'),true,'confirmed DMX map supplements a partial attribute export');
assert.equal(c.supports(c.fixture(1),'color'),true);
assert.equal(c.supports(c.fixture(1),'focus'),true);
assert.equal(c.pagesList()[0].label,'Концерт');
c.state.config.pages={'2':'Вторая'};assert.equal(c.pagesList()[0].n,2);
console.log('stage3 UI: selection ordering, gesture/config, text/blur/safety, plan/scenes, shared Fade, capabilities passed');
