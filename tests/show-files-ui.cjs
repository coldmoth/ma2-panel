'use strict';
const assert = require('node:assert/strict');
const fs = require('fs');
const vm = require('vm');

// A sent confirmation can lose its reply. Recovery must GET its status, never POST again.
async function run() {
  assert.ok(fs.existsSync('static/show-files.js'), 'show-file UI is missing');
  const requests = [], timers = [], storage = new Map();
  let answer = {ok: true, id: 'op1', kind: 'save', state: 'confirm', name: 'School', size: 42};
  let broken = false, agree = true;
  const context = vm.createContext({console, JSON, Date, Math, Number, String, encodeURIComponent,
    state: {}, render() {}, h() {}, icon() {}, connected: () => true, safe: () => true,
    confirm: () => agree,
    sessionStorage: {getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value)},
    setTimeout: fn => timers.push(fn), clearTimeout() {},
    fetch: async (url, options={}) => {
      requests.push([url, options]);
      if (broken && options.method === 'POST' && url.endsWith('/confirm')) throw new Error('lost reply');
      return {ok: true, json: async () => answer};
    }});
  vm.runInContext(fs.readFileSync('static/show-files.js', 'utf8'), context);
  agree = false;
  await context.showFilesPrepare('save');
  assert.equal(requests.filter(([, o]) => o.method === 'POST').length, 1, 'cancel must not confirm');
  agree = true; broken = true;
  await context.showFilesPrepare('save');
  const sent = requests.filter(([url]) => url.endsWith('/confirm')).length;
  assert.equal(sent, 1);
  assert.equal(storage.get('ma2-show-file-operation'), 'op1');
  assert.match(context.showFileUI.error, /неизвестен|связ/i);
  broken = false;
  answer = {...answer, state: 'unknown', reason: 'SaveShow timed out'};
  await context.showFilesRefresh();
  assert.equal(requests.filter(([url]) => url.endsWith('/confirm')).length, sent);
  assert.equal(requests.at(-1)[1].method || 'GET', 'GET');
  assert.equal(context.showFileUI.operation.state, 'unknown');
  answer = {...answer, state: 'ready'};
  await context.showFilesRefresh();
  assert.equal(context.showFileUI.operation.state, 'ready');
  assert.equal(requests.filter(([url]) => url.endsWith('/confirm')).length, 1);
  requests.length = 0;
  vm.runInContext(fs.readFileSync('static/show-files.js', 'utf8'), context);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(requests.length, 1);
  assert.equal(requests[0][0], '/api/show-files/op1');
  assert.equal(requests[0][1].method || 'GET', 'GET', 'restored ID must never confirm');
  console.log('show-files UI tests passed');
}
run().catch(error => {console.error(error); process.exitCode = 1;});
