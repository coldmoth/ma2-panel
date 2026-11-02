// Runs the real panel scripts on a small fake DOM: empty workspace, shows, highlight lifecycle, blackout, show switch.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

class Node {
  constructor(tag) {
    this.tagName = (tag || '').toUpperCase(); this.children = []; this.parentNode = null; this.attrs = {}; this.dataset = {};
    this.events = {}; this.hidden = false; this.disabled = false; this.checked = false; this.value = ''; this.type = '';
    this._text = ''; this.className = ''; this.clientWidth = this.clientHeight = 0;
    const self = this;
    this.style = {setProperty(k, v) { this[k] = v; }};
    this.classList = {
      add: (...n) => { const s = new Set(self.className.split(' ').filter(Boolean)); n.forEach(x => s.add(x)); self.className = [...s].join(' '); },
      remove: (...n) => { self.className = self.className.split(' ').filter(c => c && !n.includes(c)).join(' '); },
      contains: n => self.className.split(' ').includes(n),
      toggle: (n, on) => (on === undefined ? !self.classList.contains(n) : on) ? self.classList.add(n) : self.classList.remove(n)
    };
  }
  get textContent() { return this._text + this.children.map(c => c.textContent).join(''); }
  set textContent(v) { this.children.forEach(c => { c.parentNode = null; }); this.children = []; this._text = String(v); }
  set innerHTML(v) { this._text = ''; }
  appendChild(el) { if (el.parentNode) el.parentNode.removeChild(el); this.children.push(el); el.parentNode = this; return el; }
  append(...items) { items.forEach(el => this.appendChild(el)); }
  replaceChildren(...items) { this.textContent = ''; this.append(...items); }
  removeChild(el) { this.children = this.children.filter(c => c !== el); el.parentNode = null; return el; }
  setAttribute(k, v) { this.attrs[k] = String(v); if (['id', 'type', 'value', 'placeholder'].includes(k)) this[k] = String(v); if (k.startsWith('data-')) this.dataset[k.slice(5).replace(/-(.)/g, (_, c) => c.toUpperCase())] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  hasAttribute(k) { return k in this.attrs; }
  addEventListener(name, fn) { (this.events[name] || (this.events[name] = [])).push(fn); }
  fire(name, extra) { const ev = Object.assign({target: this, currentTarget: this, preventDefault() {}, stopPropagation() {}}, extra); (this.events[name] || []).forEach(fn => fn.call(this, ev)); if(typeof this['on'+name] === 'function') this['on'+name](ev); }
  click() { if (!this.disabled) this.fire('click'); }
  contains(el) { for (let n = el; n; n = n.parentNode) if (n === this) return true; return false; }
  all() { return this.children.flatMap(c => [c, ...c.all()]); }
  querySelectorAll(sel) {
    const m = sel.match(/^(?:#([\w-]+)\s+)?\[([\w-]+)\]$/);
    const root = m && m[1] ? document.getElementById(m[1]) : this;
    return m ? root.all().filter(n => n.attrs[m[2]] !== undefined) : [];
  }
  closest() { return null; }
  focus() { document.activeElement = this; }
  blur() { document.activeElement = null; }
  setPointerCapture() {} releasePointerCapture() {}
  getBoundingClientRect() { return {left: 0, top: 0, width: 100, height: 100}; }
  showModal() { this.open = true; } close() { this.open = false; }
}
const ids = new Map();
const document = {
  activeElement: null,
  getElementById(id) { if (!ids.has(id)) { const n = new Node('div'); n.id = id; ids.set(id, n); } return ids.get(id); },
  createElement: tag => new Node(tag), createElementNS: (_, tag) => new Node(tag),
  createTextNode: text => { const n = new Node('#text'); n._text = text; return n; },
  querySelectorAll: sel => document.getElementById('rail').querySelectorAll(sel.replace(/^#rail\s+/, '')),
  addEventListener() {}
};
for (const sec of ['scenes', 'light', 'hall', 'shows', 'start']) {
  const b = new Node('button'); b.setAttribute('data-sec', sec); document.getElementById('rail').appendChild(b);
}
const timers = [];
class WebSocket { static OPEN = 1; constructor() { this.readyState = 1; this.sent = []; } send(t) { this.sent.push(JSON.parse(t)); } close() {} }
const context = vm.createContext({document, WebSocket, console, location: {protocol: 'http:', host: 'localhost'}, performance: {now: () => 1e9},
  setTimeout: () => 0, clearTimeout() {}, setInterval: (fn, delay) => { timers.push({fn, delay}); return timers.length; },
  clearInterval: id => { if (timers[id - 1]) timers[id - 1].cleared = true; }, confirm: () => true, prompt: () => null,
  Object, JSON, Math, Array, Number, String});
for (const path of ['static/app.js', 'static/light.js', 'static/plan.js', 'static/move.js']) vm.runInContext(fs.readFileSync(path, 'utf8'), context, {filename: path});
vm.runInContext('connect()', context);
const ws = () => context.state.ws;
const sent = () => ws().sent;
const page = document.getElementById('page');
const findBtn = text => page.all().concat(document.getElementById('banners').all()).find(n => n.tagName === 'BUTTON' && n.textContent.includes(text));
const status = extra => context.receive({status: Object.assign({ma2: 'logged_in', safety: {mode: 'full', allow_fixture_read: true, allow_highlight: true, allow_show_load: true, allow_show_save: true, master: true}, show: {name: 'Mock show'}}, extra)});

// Empty workspace: the panel works, Свет and Зал wait for fixtures, Площадка offers the fetch.
status();
context.receive({config: {fixtures: [], groups: [], scenes: [], presets: [], pages: {}, attrs: {pan: {min: -270, max: 270}, tilt: {min: -135, max: 135}}, plan: {}}});
for (const sec of ['scenes', 'light', 'hall', 'shows', 'start']) { context.go(sec); assert.equal(context.state.sec, ['light', 'hall'].includes(sec) ? 'start' : sec === 'scenes' ? 'start' : sec); }
assert.equal(document.getElementById('rail').children.find(b => b.dataset.sec === 'light').disabled, true);
const fetchBtn = findBtn('Получить оборудование из MA2');
assert.ok(fetchBtn && !fetchBtn.disabled);
fetchBtn.click();
assert.equal(sent().at(-1).a, 'fixtures_fetch');
context.receive({ok: false, a: 'fixtures_fetch', err: 'MA2 не создала файл'});
assert.match(page.textContent, /Не получено из MA2: MA2 не создала файл/);
console.log('empty workspace and fetch passed');

// Shows: explicit load only, typed confirmation, save is separate.
context.go('shows');
const before = sent().length;
context.receive({ok: true, a: 'shows_list', names: ['Demo', 'Mock show'], raw_lines: ['"Demo"'], local_names: []});
status();
assert.equal(sent().slice(before).filter(a => a.a === 'show_load').length, 0);
findBtn('Demo').click();
const load = findBtn('Загрузить «Demo»');
assert.equal(load.disabled, true);
const inputs = page.all().filter(n => n.tagName === 'INPUT');
const ack = inputs.find(n => n.type === 'checkbox'), conf = inputs.find(n => n.id === 'load-confirm');
ack.checked = true; ack.fire('change');
conf.value = 'Demo'; conf.fire('input');
assert.equal(load.disabled, false);
load.click();
assert.deepEqual(sent().at(-1), {a: 'show_load', name: 'Demo', confirm_name: 'Demo', ack_unsaved: true});
findBtn('Сохранить шоу на пульте').click();  // one button, after confirm(): no typed name
assert.deepEqual(sent().at(-1), {a: 'show_save'});
status({show_load: {state: 'loading', name: 'Demo'}});
assert.equal(context.connected(), false);
assert.equal(document.getElementById('halt').disabled, false);
status({show_load: {state: 'done', name: 'Demo'}});
console.log('shows: explicit load, confirmation, save passed');

// Highlight lifecycle in Зал.
context.receive({config: {show: 'Mock show', hall: {w: 18, d: 14, stage: 'top', stageDepth: 4}, groups: [], scenes: [], presets: [], pages: {}, plan: {},
  attrs: {pan: {min: -270, max: 270}, tilt: {min: -135, max: 135}},
  fixtures: [{id: 12, label: 'Head', x: .1, y: .2, moves: true}, {id: 14, label: 'Other'}, {id: 90, label: 'Work', service: true}]}});
status({highlight: {state: 'idle', available: [12, 14]}});
context.go('hall');
assert.equal(sent().at(-1).a, 'edit_begin');
const box = () => page.all().find(n => n.tagName === 'INPUT' && n.type === 'checkbox');
assert.equal(box().checked, false);
box().checked = true; box().fire('change');
assert.equal(timers.at(-1).delay, 3000);
assert.deepEqual(sent().at(-1), {a: 'highlight', id: 12});
timers.at(-1).fn();
assert.equal(sent().at(-1).a, 'highlight_ping');
findBtn('Other').click();
assert.deepEqual(sent().at(-1), {a: 'highlight', id: 14});
assert.match(page.textContent, /Work \(служебные\)/);
box().checked = false; box().fire('change');
assert.deepEqual(sent().slice(-3).map(a => a.a), ['highlight_off', 'edit_end', 'edit_begin']);
assert.equal(timers.at(-1).cleared, true);
box().checked = true; box().fire('change');
context.go('light');
assert.deepEqual(sent().slice(-2).map(a => a.a), ['highlight_off', 'edit_end']);
assert.equal(timers.at(-1).cleared, true);
context.go('hall');
assert.equal(box().checked, false);  // every entry starts with the highlight off
context.go('light');
const n = sent().filter(a => a.a === 'highlight').length;
context.lightUI.tab = 'plan'; context.render();
const dot = page.all().find(x => x.className && x.className.includes('fx'));
context.tapFixture(12, 'control');
assert.equal(sent().filter(a => a.a === 'highlight').length, n);
assert.deepEqual(sent().at(-1), {a: 'select_fixtures', ids: [12]});
assert.ok(dot);
status({highlight: {state: 'stuck', zone: [12, 14], reason: 'нет связи'}});
assert.ok(findBtn('Снять подсветку'));
console.log('highlight lifecycle passed');

// Colour wheel maths and the honest states of the colour card.
assert.deepEqual(Array.from(context.hsv2rgb(0, 1, 1)), [100, 0, 0]);
assert.deepEqual(Array.from(context.hsv2rgb(120, 1, 1)), [0, 100, 0]);
assert.deepEqual(Array.from(context.hsv2rgb(240, .5, .8)), [40, 40, 80]);
assert.equal(Math.round(context.rgb2hsv([100, 50, 0]).h), 30);
context.state.config.fixtures.push({id: 15, label: 'Fresnel', color: 'none'});
context.state.selection = [15]; context.render();
assert.match(page.textContent, /нет смешения цвета/);
context.state.selection = [12, 14]; context.state.shown = {12: {rgb: [100, 0, 0]}, 14: {rgb: [0, 0, 100]}}; context.sectionKey = null; context.render();
assert.match(page.textContent, /У выбранных разные цвета/);
assert.doesNotMatch(page.textContent, /NaN/);
console.log('colour card passed');

// Blackout needs a second press; a show switch drops selection and values.
const count = sent().filter(a => a.a === 'blackout').length;
document.getElementById('blackout').click();
assert.equal(sent().filter(a => a.a === 'blackout').length, count);
document.getElementById('blackout').click();
assert.equal(sent().filter(a => a.a === 'blackout').length, count + 1);
context.receive({shown: {12: {dim: 50, rgb: [100, 0, 0]}}});
context.receive({config: {show: 'Demo', fixtures: [], groups: [], scenes: [], presets: [], pages: {}, plan: {}, attrs: {}}});
assert.equal(context.state.selection.length, 0);
assert.deepEqual(JSON.parse(JSON.stringify(context.state.shown)), {});
console.log('blackout and show switch passed');

// Master comes from the bridge, not a DOM node discarded by a fade/section change.
status();
context.receive({config: {show: 'Demo', fixtures: [], groups: [], scenes: [{id:'s1',exec:'2.101',label:'Финал'}], presets: [], attrs:{}}});
context.receive({master:99}); context.go('scenes');
assert.match(page.textContent, /99%/);
findBtn('2 с').click();
assert.match(page.textContent, /99%/);
context.go('shows'); context.go('scenes'); assert.match(page.textContent, /99%/);
context.notice('Сохранено', 'success');
assert.equal(document.getElementById('notice').classList.contains('success'), true);
const resultButton = findBtn('+ Добавить'); const resultLabel = resultButton.textContent;
context.feedback(resultButton, false, 'Пульт не ответил');
assert.equal(resultButton.textContent, resultLabel);
assert.match(document.getElementById('notice').textContent, /Пульт не ответил/);
console.log('master persistence and durable feedback passed');

// Touch movement has an explicit fine-step cross and discoverable preset management.
context.receive({config:{show:'Demo', fixtures:[{id:12,label:'Голова',moves:true}], groups:[], scenes:[],
 presets:[{id:'p1',label:'Центр',pos:{12:{pan:50,tilt:50}}}], attrs:{pan:{min:-270,max:270,step:2},tilt:{min:-135,max:135,step:2}}, plan:{}}});
context.state.selection=[12]; context.go('light');
assert.ok(findBtn('Движение'));
findBtn('Движение').click();
assert.equal(page.all().some(n=>n.tagName==='INPUT' && n.type==='number'), false);
const panRight = page.all().find(n=>n.tagName==='BUTTON' && n.getAttribute('aria-label')==='Pan +1°');
assert.ok(panRight); panRight.click(); assert.equal(sent().at(-1).step,1);
const mirrorButton = findBtn('Зеркально'); assert.equal(mirrorButton.tagName,'BUTTON');
const managePresets = findBtn('Управлять пресетами'); assert.ok(managePresets);
managePresets.click();
const deletePreset = page.all().find(n=>n.tagName==='BUTTON' && n.getAttribute('aria-label')==='Удалить пресет Центр');
const beforeDelete = sent().length; deletePreset.click();
assert.deepEqual(JSON.parse(JSON.stringify(sent().slice(beforeDelete))),[{a:'preset_delete',id:'p1'}]);
context.moveState.drag={pointer:1,t:0,vx:1,vy:0,timer:1};
findBtn('Свет',true); context.go('scenes');
const afterLeave=sent().length; context.joyTick(); assert.equal(sent().length,afterLeave);
console.log('compact movement and preset deletion passed');

// Scenes are readable without knowing MA2 pages; address remains an internal target.
context.receive({config:{show:'Demo',fixtures:[],groups:[],presets:[],attrs:{},scenes:[
 {id:'a',exec:'1.101',label:'Рояль'}, {id:'b',exec:'2.105',label:'Финал'}]}});
context.go('scenes');
const tiles = page.all().filter(n=>n.tagName==='BUTTON' && n.dataset.scene);
assert.ok(tiles[0].textContent.includes('Рояль'));
assert.ok(tiles[1].textContent.includes('Финал'));
assert.ok(!tiles[0].textContent.includes('1.101'));
assert.ok(!page.textContent.includes('Страница 2'));
tiles[1].click(); assert.equal(sent().at(-1).id,'b');
console.log('flat scene list passed');

// New scene creation asks the bridge for a slot; stale replies cannot choose a target.
context.openStore(1);
const storeDialog=document.getElementById('dlg');
const storeName=storeDialog.all().find(n=>n.id==='store-name'); storeName.value='Новая';
const search=storeDialog.all().find(n=>n.tagName==='BUTTON' && n.textContent==='Найти место');
assert.ok(search); search.click();
const searchRequest=sent().at(-1); assert.equal(searchRequest.a,'scene_slot_find');
context.receive({ok:true,a:'scene_slot_find'});
context.receive({scene_slot:{request:'old',state:'ready',exec:'2.200',token:'stale'}});
assert.ok(!storeDialog.textContent.includes('2.200'));
context.receive({scene_slot:{request:searchRequest.request,state:'ready',exec:'1.1',token:'token1'}});
const write=storeDialog.all().find(n=>n.tagName==='BUTTON' && n.textContent==='Записать');
assert.ok(write); write.click(); write.click();
assert.equal(sent().filter(a=>a.a==='scene_create' && a.token==='token1').length,1);
console.log('safe slot offer dialog passed');

// Preparation exposes compact fixture settings without changing the desk.
context.receive({ok:true,a:'scene_create'});
context.receive({config:{show:'Demo',hall:{w:18,d:14,stage:'top',stageDepth:4},fixtures:[{id:12,label:'Голова',moves:true,x:.3,y:.3}],groups:[],scenes:[],presets:[],plan:{},attrs:{pan:{min:-270,max:270},tilt:{min:-135,max:135}}}});
context.go('hall');
const fixtureSettings=page.all().find(n=>n.tagName==='DETAILS' && n.textContent.includes('Настройки прибора'));
assert.ok(fixtureSettings); assert.equal(!!fixtureSettings.open,false);
const beforeSettings=sent().length; fixtureSettings.open=true; fixtureSettings.fire('toggle');
assert.equal(sent().length,beforeSettings);
context.go('light');
assert.match(context.linkLine().text,/Подключено/);
console.log('compact preparation and connection status passed');

// The teacher panel uses the same order and never exposes console pages or edit actions.
const simpleIds=new Map(); const simpleDoc={createElement:tag=>new Node(tag),getElementById:id=>{
 if(!simpleIds.has(id))simpleIds.set(id,new Node('div')); return simpleIds.get(id);
}};
let simpleSocket;
class SimpleSocket extends WebSocket { constructor(){super();simpleSocket=this;} }
const simpleContext=vm.createContext({document:simpleDoc,WebSocket:SimpleSocket,location:{protocol:'http:',host:'localhost'},setTimeout:()=>0,confirm:()=>true});
vm.runInContext(fs.readFileSync(process.env.MA2_SIMPLE_SCRIPT || 'static/simple.js','utf8'),simpleContext);
simpleSocket.onmessage({data:JSON.stringify({status:{ma2:'logged_in',safety:{mode:'full'}}})});
simpleSocket.onmessage({data:JSON.stringify({config:{scenes:[{id:'z',exec:'2.105',label:'Финал'},{id:'a',exec:'1.101',label:'Рояль'}]}})});
assert.match(simpleDoc.getElementById('scenes').textContent,/1 · Финал/);
assert.match(simpleDoc.getElementById('scenes').textContent,/2 · Рояль/);
assert.doesNotMatch(simpleDoc.getElementById('scenes').textContent,/Страница|2\.105|1\.101/);
simpleDoc.getElementById('scenes').all().find(n=>n.tagName==='BUTTON').click();
assert.equal(simpleSocket.sent[0].id,'z');
console.log('simple panel flat scene order passed');

// One inversion gesture must affect every selected head, despite duplicate-submit protection.
context.receive({config:{show:'Demo',fixtures:[{id:12,label:'A',moves:true},{id:14,label:'B',moves:true}],groups:[],scenes:[],presets:[],attrs:{pan:{min:-270,max:270},tilt:{min:-135,max:135}}}});
context.state.selection=[12,14];context.lightUI.controlTab='movement';context.go('light');
const beforeFlip=sent().length;findBtn('Pan наоборот').click();
assert.deepEqual(JSON.parse(JSON.stringify(sent().slice(beforeFlip))),[
 {a:'fixture_flag',id:12,flip_pan:true},{a:'fixture_flag',id:14,flip_pan:true}
]);
console.log('multi-head inversion gesture passed');

// Unconfirmed writes must be visible and blocked in the teacher UI too.
simpleSocket.onmessage({data:JSON.stringify({ok:true,a:'scene_go'})});
simpleSocket.onmessage({data:JSON.stringify({config:{scenes:[{id:'z',exec:'2.105',label:'Финал',write_error:'Запись не подтверждена'}]}})});
const unsafeGo=simpleDoc.getElementById('scenes').all().find(n=>n.tagName==='BUTTON');
assert.equal(unsafeGo.disabled,true);
assert.match(simpleDoc.getElementById('scenes').textContent,/Запись не подтверждена/);
console.log('teacher UI blocks unconfirmed writes passed');

// A delayed older snapshot must not overwrite a newer master or fixture state.
context.receive({master:70,values_revision:11});
context.receive({master:40,values_revision:10});
assert.equal(context.state.master,70);
console.log('out of order value snapshots passed');

// Keyboard focus is not an ongoing gesture: another panel can move the master thumb.
context.receive({config:{show:'Demo',fixtures:[],groups:[],scenes:[{id:'a',exec:'1.101',label:'Тест'}],presets:[],attrs:{}}});
context.go('scenes');
const focusedMaster=page.all().find(n=>n.tagName==='INPUT' && n.getAttribute('aria-label')==='Общая яркость');
focusedMaster.focus();
context.receive({master:85,values_revision:12});
assert.equal(Number(focusedMaster.value),85);
console.log('focused master follows confirmed state passed');
