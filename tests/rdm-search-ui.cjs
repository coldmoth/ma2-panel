'use strict';
const assert = require('node:assert/strict');
const fs = require('fs');
const vm = require('vm');

// User choices and reconnection must never replay an RDM start.
function element(tag, props, ...children) {
  return {tag, props: props || {}, children: children.flat(Infinity).filter(x => x !== null && x !== undefined),
    get textContent() { return this.children.map(x => typeof x === 'object' ? x.textContent : String(x)).join(''); }};
}
function all(node) { return [node, ...node.children.filter(x => typeof x === 'object').flatMap(all)]; }
function button(node, label) { return all(node).find(x => x.tag === 'button' && x.textContent === label); }
const sent = [], events = {}, confirmations = [];
let agree = false, online = true;
const c = vm.createContext({console, JSON, Object, String, Array, Number, Math,
  state: {ws: {}, rdmSearch: null}, SECTIONS: {},
  on(type, fn) { (events[type] || (events[type] = [])).push(fn); },
  render() {}, notice() {}, connected: () => online, bridgeUp: () => online, safe: () => true,
  h: element, add: (node, ...items) => node.children.push(...items.flat(Infinity).filter(Boolean)),
  fixtures: () => [], confirm: text => { confirmations.push(text); return agree; },
  send: action => { sent.push(action); return true; },
  document: {getElementById: () => ({open: false})}});
vm.runInContext(fs.readFileSync('static/patch.js', 'utf8'), c);
function reply(message) { (events.ok || []).forEach(fn => fn(message.ok, message)); }
function status(search) { c.state.rdmSearch = search; (events.status || []).forEach(fn => fn({rdm_search: search})); }
function click(node) { assert.ok(node, 'missing control'); if (!node.props.disabled) node.props.onclick({currentTarget: node}); }

click(button(c.rdmCard(), 'Поиск RDM'));
assert.equal(sent.at(-1).a, 'rdm_prepare');
reply({ok: true, a: 'rdm_prepare', offer: {token: 'cancelled', universes: [1, 3]}});
assert.equal(sent.filter(x => x.a === 'rdm_start').length, 0);
assert.match(confirmations[0], /френел/);
assert.match(confirmations[0], /18/);
assert.match(confirmations[0], /1, 3/);

agree = true;
click(button(c.rdmCard(), 'Поиск RDM'));
reply({ok: true, a: 'rdm_prepare', offer: {token: 'once', universes: [1]}});
reply({ok: true, a: 'rdm_prepare', offer: {token: 'once', universes: [1]}});
assert.equal(sent.filter(x => x.a === 'rdm_start').length, 1, 'duplicate offer must not start twice');
assert.equal(sent.at(-1).token, 'once');

const active = {id: 'job', active: true, pending: true, phase: 'collecting', collection: 'running', off_state: 'unknown', universes: [1], devices: [], lines: []};
status(active);
assert.ok(button(c.rdmCard(), 'Поиск RDM').props.disabled);
click(button(c.rdmCard(), 'Остановить поиск'));
assert.equal(sent.at(-1).a, 'rdm_stop');
assert.ok(!sent.some(x => x.a === 'rdm_identify' || x.a === 'rdm_link'));

const unknown = {...active, active: false, phase: 'done', collection: 'completed', reason: 'обрыв'};
status(unknown);
online = false;
let banner = c.rdmSearchBanner();
assert.match(banner.textContent, /Выключение RDM не подтверждено/);
assert.match(banner.textContent, /Setup.*Console.*Global Settings.*Off/);
assert.ok(button(banner, 'Проверить выключение').props.disabled);
assert.doesNotMatch(c.rdmCard().textContent, /Поиск завершён успешно|Найдено 0/);
const starts = sent.filter(x => x.a === 'rdm_start').length;
c.state.ws = {}; online = true;
status(unknown);
assert.equal(sent.filter(x => x.a === 'rdm_start').length, starts, 'reconnect must not replay start');
click(button(c.rdmSearchBanner(), 'Проверить выключение'));
assert.equal(sent.at(-1).a, 'rdm_check');

status({...unknown, pending: false, off_state: 'confirmed'});
assert.equal(c.rdmSearchBanner(), null);
assert.match(c.rdmCard().textContent, /выключен.*подтвержден/i);
assert.match(c.rdmCard().textContent, /не доказывает отсутствие|не подтверждает отсутствие/i);

// A delayed prepare from a previous socket is not a fresh consent invitation.
click(button(c.rdmCard(), 'Поиск RDM'));
c.state.ws = {};
reply({ok: true, a: 'rdm_prepare', offer: {token: 'old-socket', universes: [1]}});
assert.equal(sent.filter(x => x.a === 'rdm_start').length, starts);
console.log('RDM search UI tests passed');
