'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const prefix = fs.readFileSync('tests/panel-v4.cjs', 'utf8').split('// Empty workspace:')[0];
const {context: c, ws, document} = new Function('require', prefix + '\nreturn {context, ws, document};')(require);
c.receive({status: {ma2: 'logged_in', safety: {mode: 'full'}, features: {}}});
c.receive({config: {revision: 'epoch:1', fixtures: [], groups: [], scenes: [], presets: [], pages: {}, attrs: {}}});
const raw = () => ws().sent;
const first = document.createElement('button'), second = document.createElement('button');
assert(c.send({a:'shows_list'}, first));
assert(c.send({a:'shows_list'}, second));
const a = raw().at(-2), b = raw().at(-1);
assert.notEqual(a.request_id, b.request_id);
c.receive({ok:true,a:'shows_list',request_id:b.request_id,names:[]});
assert.equal(second.getAttribute('aria-busy'), null);
assert.equal(first.getAttribute('aria-busy'), 'true');
c.receive({ok:false,a:'shows_list',request_id:a.request_id,err:'first failed'});
assert.equal(first.getAttribute('aria-busy'), null);
// Routine actions and long operations never insert a generic banner above controls.
for (const action of ['color', 'move', 'jog', 'dim', 'show_save']) {
  c.receive({status: {ma2:'logged_in',operations:[{request_id:'shared',a:action,stage:'running'}],safety:{mode:'full'}}});
  assert.equal(document.getElementById('banners').textContent, '');
}
c.receive({status: {ma2:'disconnected',safety:{mode:'full'}}});
assert.match(document.getElementById('banners').textContent, /Управление недоступно/);
c.receive({status: {ma2:'logged_in',safety:{mode:'full'}}});
// The rendered form keeps its baseline even when another client publishes a newer plan.
const stale = c.h('button', {onclick: () => c.send({a:'group_save',label:'stale',ids:[12]})}, 'save');
c.receive({config: {revision:'epoch:2',fixtures:[],groups:[],scenes:[],presets:[],pages:{},attrs:{}}});
stale.click();
assert.equal(raw().at(-1).config_revision, 'epoch:1');
let id = raw().at(-1).request_id;
c.receive({ok:false,a:'group_save',request_id:id,conflict:true,err:'stale'});
// A burst of local edits is serialized and only rebased onto its own confirmed result.
const before = raw().length;
c.send({a:'fixture_flag',id:12,flip_pan:true});
c.send({a:'fixture_flag',id:14,flip_pan:true});
assert.equal(raw().length, before + 1);
id = raw().at(-1).request_id;
c.receive({ok:true,a:'fixture_flag',request_id:id,config_revision:'epoch:3'});
assert.equal(raw().length, before + 2);
assert.equal(raw().at(-1).config_revision, 'epoch:3');
// Reconnect drops outstanding commands and does not replay them.
const old = ws(); old.onclose(); c.connect();
assert.equal(raw().length, 0);
assert.match(document.getElementById('notice').textContent, /неизвестен/);
console.log('protocol: request correlation, stale forms, serial saves and no replay passed');
