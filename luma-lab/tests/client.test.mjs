import { test } from "node:test";
import assert from "node:assert/strict";
import { BridgeClient } from "../src/client.mjs";
import { displayValues } from "../src/model.mjs";
class Socket {
  readyState = 1;
  sent = [];
  send(v) {
    this.sent.push(JSON.parse(v));
  }
  close() {
    this.readyState = 3;
  }
}
const denial = (code, message) => ({code, message});
function statusFor({ma2 = "logged_in", mock = true, name = "Mock show", showState = "matched",
                    blocked = null, master = null, blackout = null} = {}) {
  return {
    mock, ma2, blackout: {phase: blackout ? "unknown" : "idle"}, blackout_epoch: 7,
    show: {name, source: name ? "ma2" : "unknown"},
    readiness: {
      connection: {logged_in: "authenticated", tcp: "connecting", login_unknown: "login_unconfirmed",
                   login_failed: "connection_error", down: "connection_error"}[ma2],
      show: {state: showState, name},
      actions: {
        view: {show_status: null}, plan: {group_save: null, edit_begin: null, edit_end: null},
        light: {select_fixtures: blocked, dim: blocked, color: blocked, jog: blocked, aim: blocked, scene_go: blocked, scene_off: blocked, scene_slot_find: blocked, scene_create: blocked, highlight: blocked},
        general: {clear: null, master, blackout}, recovery: {halt: null, undo: null, scene_slot_cancel: null, highlight_off: null, highlight_ping: null},
      },
    },
  };
}
function connected(mock = true) {
  const c = new BridgeClient();
  c.socket = new Socket();
  c.receive({status: statusFor({mock}), config: {revision: "rev-A", show: "Mock show", fixtures: [{id: 1}]}});
  return c;
}
test("group draft keeps its revision and forgetting selection sends nothing", async () => {
  const c = connected();
  const p = c.action({a: "group_save", config_revision: "draft-revision"});
  assert.equal(c.socket.sent[0].config_revision, "draft-revision");
  c.receive({request_id: c.socket.sent[0].request_id, ok: true});
  await p;
  const select = c.select([1]);
  const req = c.socket.sent.at(-1), count = c.socket.sent.length;
  c.forgetSelection();
  c.receive({request_id: req.request_id, ok: true});
  await select;
  assert.deepEqual(c.state.selected, []);
  assert.equal(c.socket.sent.length, count);
});
test("no command on startup, non-mock backend is read-only", async () => {
  const c = connected(false);
  assert.equal(c.socket.sent.length, 0);
  await assert.rejects(c.action({ a: "blackout" }), { code: "mock_only" });
});
test("every request carries revision, blackout epoch and unique identity; no optimistic acknowledgement", async () => {
  const c = connected();
  const p = c.action({ a: "dim", v: 50 });
  const request = c.socket.sent[0];
  assert.equal(request.config_revision, "rev-A");
  assert.equal(request.blackout_epoch, 7);
  assert(request.request_id);
  assert.equal(c.getSnapshot().shown[1], undefined);
  c.receive({
    request_id: request.request_id,
    ok: true,
    a: "dim",
    outcome: "completed",
  });
  await p;
});
test("disconnect rejects inflight work, preserves UI selection, and marks selection for resync", async () => {
  const c = connected();
  c.state.selected = [1];
  c.state.live = { 1: { dim: 90 } };
  c.state.running = { s1: true };
  const p = c.action({ a: "dim", v: 10 });
  c.disconnected();
  await assert.rejects(p, { code: "command_unknown" });
  assert.deepEqual(c.state.selected, [1]);
  assert.equal(c.needsSelectionSync, true);
  assert.deepEqual(c.state.live, {});
  assert.deepEqual(c.state.running, {});
  assert.equal(c.socket.sent.length, 1);
});
test("unknown blackout cannot restore; stale revisions surface server rejection", async () => {
  const c = connected();
  c.receive({status: statusFor({blackout: denial("blackout_unknown", "Состояние неизвестно")})});
  await assert.rejects(c.action({ a: "blackout" }), { code: "blackout_unknown" });
  c.receive({status: statusFor()});
  const p = c.action({ a: "group_save", label: "A", ids: [1] });
  c.receive({
    request_id: c.socket.sent[0].request_id,
    a: "group_save",
    ok: false,
    conflict: true,
    err: "План изменён",
  });
  await assert.rejects(p, { code: "plan_revision" });
});
test("selection updates UI immediately and syncs with bridge when ready", async () => {
  const c = connected();
  const p = c.select([1]);
  assert.deepEqual(c.state.selected, [1]);
  assert.equal(c.state.selecting, false);
  assert.equal(c.socket.sent[0].a, "select_fixtures");
  c.receive({
    request_id: c.socket.sent[0].request_id,
    a: "select_fixtures",
    ok: true,
  });
  await p;
  assert.deepEqual(c.state.selected, [1]);
  assert.equal(c.needsSelectionSync, false);
});
test("clearing selection uses the existing clear operation, never empty fixture selection", async () => {
  const c = connected();
  c.state.selected = [1];
  const p = c.select([]);
  assert.equal(c.socket.sent[0].a, "clear");
  c.receive({ request_id: c.socket.sent[0].request_id, a: "clear", ok: true });
  await p;
  assert.deepEqual(c.state.selected, []);
});
test("old value revisions cannot restore stale evidence", () => {
  const c = connected();
  c.receive({
    values_revision: 10,
    shown: { 1: { dim: 25 } },
    values_meta: { "sent:1:dim": { freshness: "stale" } },
  });
  c.receive({
    values_revision: 9,
    shown: { 1: { dim: 100 } },
    values_meta: { "sent:1:dim": { freshness: "fresh" } },
  });
  assert.equal(c.state.shown[1].dim, 25);
  assert.equal(c.state.values_meta["sent:1:dim"].freshness, "stale");
});
test("local evidence expires even when an open socket stops delivering messages", () => {
  const c = connected();
  c.receive({
    shown: { 1: { dim: 25 } },
    values_meta: {
      "sent:1:dim": { source: "panel", freshness: "fresh", updated_at: 100 },
    },
    running: { s1: true },
    running_meta: {
      s1: { source: "ma2", freshness: "fresh", updated_at: 100 },
    },
  });
  c.expireEvidence(Date.now() + 6501);
  assert.equal(c.state.values_meta["sent:1:dim"].freshness, "stale");
  assert.equal(c.state.running_meta.s1.freshness, "stale");
});
test("blackout blocks later gestures until terminal response without retrying the blackout", async () => {
  const c = connected();
  const p = c.action({ a: "blackout" });
  assert.equal(c.ready(), false);
  await assert.rejects(c.action({ a: "jog", pan: 0.15, tilt: 0 }), { code: "blackout_pending" });
  c.receive({
    request_id: c.socket.sent[0].request_id,
    a: "blackout",
    ok: true,
  });
  await p;
  assert.equal(c.ready(), true);
  assert.equal(c.socket.sent.length, 1);
});
test("history survives stale snapshots, scene changes and disconnect; another show clears it", () => {
 const c=connected();
 c.receive({shown:{1:{pan:29.6296,dim:64}},master:73,values_meta:{'sent:1:pan':{freshness:'fresh',updated_at:1},'sent:1:dim':{freshness:'fresh',updated_at:1},master:{freshness:'fresh',source:'panel',updated_at:1}}});
 assert.equal(c.state.history[1].pan.quality,'pending');
 c.receive({live:{1:{pan:29.6296}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:2}}});
 assert.equal(c.state.history[1].pan.quality,'confirmed');
 c.receive({shown:{},live:{},master:null,values_meta:{}});
 assert.equal(c.state.history[1].pan.value,29.6296);
 assert.equal(c.state.masterEvidence.value,73);
 c.disconnected();
 assert.equal(c.state.history[1].pan.quality,'last');
 assert.equal(c.state.masterEvidence.quality,'last');
 c.receive({config:{...c.state.config,show:'another show'}});
 assert.deepEqual(c.state.history,{});
 assert.equal(c.state.masterEvidence.value,undefined);
 assert.equal(c.socket.sent.length,0);
});
test('repeated old readback cannot overwrite a newer pending command or refresh expired evidence', async()=>{
 const c=connected();c.state.selected=[1];
 const snapshot={live:{1:{dim:30}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:1}}};
 c.receive(snapshot);assert.equal(c.state.history[1].dim.value,30);
 const pending=c.control({a:'dim',v:64});c.receive(snapshot);
 c.receive({request_id:c.socket.sent[0].request_id,ok:true});await pending;
 assert.equal(c.state.history[1].dim.value,64);assert.equal(c.state.history[1].dim.quality,'pending');
 c.expireEvidence(Date.now()+10000);c.receive(snapshot);
 assert.equal(c.state.history[1].dim.quality,'unconfirmed');
});

const angles = {pan:{min:-270,max:270},tilt:{min:-135,max:135}};
const percent = (key, deg) => (deg-angles[key].min)/(angles[key].max-angles[key].min)*100;
function positionClient(fixtures=[{id:1}]) {
 const c=connected();c.state.config={...c.state.config,attrs:angles,fixtures};c.state.selected=fixtures.map(f=>f.id);return c;
}
async function ack(c,p,ok=true) {
 c.receive({request_id:c.socket.sent.at(-1).request_id,ok,err:ok?undefined:'rejected'});
 if(ok) await p;else await assert.rejects(p, { err: "rejected" });
}
test('confirmed Pan -110 and Tilt -65 follow rounded relative steps, never zero; readback confirms',async()=>{
 const c=positionClient();
 const snapshot={live:{1:{pan:percent('pan',-110),tilt:percent('tilt',-65)}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:1}}};
 c.receive(snapshot);
 const p=c.control({a:'jog',pan:1.004,tilt:.996});
 assert(Math.abs(displayValues(c.state,1).pan-percent('pan',-109))<1e-8);
 assert(Math.abs(displayValues(c.state,1).tilt-percent('tilt',-64))<1e-8);
 assert.equal(c.state.history[1].pan.quality,'pending');
 c.receive(snapshot);await ack(c,p);
 assert(Math.abs(c.state.history[1].pan.value-percent('pan',-109))<1e-8);
 assert.equal(c.socket.sent.length,1);assert.equal(c.socket.sent[0].a,'jog');
 c.receive({live:{1:{pan:percent('pan',-108.9),tilt:percent('tilt',-63.9)}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:2}}});
 assert.equal(c.state.history[1].pan.quality,'confirmed');
 const next=c.control({a:'jog',pan:1,tilt:0});await ack(c,next);
 assert(Math.abs(c.state.history[1].pan.value-percent('pan',-107.9))<1e-8);
});
test('relative prediction uses each fixture origin and inversion; a zero axis remains confirmed',async()=>{
 const c=positionClient([{id:1,flip_pan:true},{id:2,flip_tilt:true}]);
 c.receive({live:{1:{pan:40,tilt:20},2:{pan:60,tilt:70}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:1}}});
 const p=c.control({a:'jog',pan:1,tilt:0});await ack(c,p);
 assert(Math.abs(c.state.history[1].pan.value-(40-100/540))<1e-8);
 assert(Math.abs(c.state.history[2].pan.value-(60+100/540))<1e-8);
 assert.equal(c.state.history[1].tilt.quality,'confirmed');
});
test('in-flight stale DMX readback cannot bounce pending dim/rgb back to old value; matching readback confirms immediately', async()=>{
 const c=connected();c.state.selected=[1];
 c.receive({live:{1:{dim:0,rgb:[100,100,100]}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:1}}});
 assert.equal(c.state.history[1].dim.value,0);
 const pDim=c.control({a:'dim',v:50});
 // Pre-ACK in-flight readback with newer updated_at must not bounce dim back to 0.
 c.receive({live:{1:{dim:0}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:2}}});
 assert.equal(c.state.history[1].dim.value,50);
 assert.equal(c.state.history[1].dim.quality,'pending');
 c.receive({request_id:c.socket.sent.at(-1).request_id,ok:true,a:'dim'});
 await pDim;
 // Immediate post-ACK stale DMX sample with old value is ignored during grace window.
 c.receive({live:{1:{dim:0}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:3}}});
 assert.equal(c.state.history[1].dim.value,50);
 assert.equal(c.state.history[1].dim.quality,'pending');
 // Quantized 8-bit DMX match (49.8% for 50%) confirms immediately.
 c.receive({live:{1:{dim:49.8}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:4}}});
 assert.equal(c.state.history[1].dim.value,49.8);
 assert.equal(c.state.history[1].dim.quality,'confirmed');
 // Same protection for RGB color.
 const pCol=c.control({a:'color',r:100,g:0,b:50});
 c.receive({request_id:c.socket.sent.at(-1).request_id,ok:true,a:'color'});
 await pCol;
 c.receive({live:{1:{rgb:[100,100,100]}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:5}}});
 assert.deepEqual(c.state.history[1].rgb.value,[100,0,50]);
 assert.equal(c.state.history[1].rgb.quality,'pending');
 c.receive({live:{1:{rgb:[100,0,49.8]}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:6}}});
 assert.deepEqual(c.state.history[1].rgb.value,[100,0,49.8]);
 assert.equal(c.state.history[1].rgb.quality,'confirmed');
});
test('jog starts from 50 when unknown, continues from stale positions, and rejection cannot stay pending',async()=>{
 const c=positionClient();await ack(c,c.control({a:'jog',pan:1,tilt:1}));
 assert(Math.abs(displayValues(c.state,1).pan-(50+100/540))<1e-8);
 assert(Math.abs(displayValues(c.state,1).tilt-(50+100/270))<1e-8);
 c.receive({live:{1:{pan:30}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:1}}});
 c.expireEvidence(Date.now()+7000);
 assert.equal(c.state.history[1].pan.quality,'last');
 await ack(c,c.control({a:'jog',pan:1,tilt:0}));
 assert(Math.abs(c.state.history[1].pan.value-(30+100/540))<1e-8);
 assert.equal(c.state.history[1].pan.quality,'pending');
 c.receive({live:{1:{pan:31}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:2}}});
 await ack(c,c.control({a:'jog',pan:1,tilt:0}),false);
 assert.notEqual(c.state.history[1].pan.quality,'pending');
});
test('a changed but stale readback cannot replace a pending relative estimate',async()=>{
 const c=positionClient();
 c.receive({live:{1:{pan:30}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:1}}});
 const p=c.control({a:'jog',pan:1,tilt:0});await ack(c,p);
 const expected=c.state.history[1].pan.value;
 c.receive({live:{1:{pan:29}},values_meta:{live:{source:'ma2',freshness:'stale',updated_at:2}}});
 assert.equal(c.state.history[1].pan.value,expected);assert.equal(c.state.history[1].pan.quality,'pending');
});
test('panel echo is not confirmation and cannot hide an uncertain command outcome',async()=>{
 const c=positionClient();
 const p=c.control({a:'aim',pan:-110});
 c.receive({shown:{1:{pan:percent('pan',-110)}},values_meta:{'sent:1:pan':{source:'panel',freshness:'fresh',updated_at:1}}});
 await ack(c,p,false);
 assert.equal(c.state.history[1].pan.quality,'unconfirmed');
});

test("TCP without confirmed login still allows local UI selection, sends nothing, and blocks light commands", async () => {
  const c = connected();
  c.receive({status: statusFor({ma2: "login_unknown", name: null, showState: "pending",
    blocked: denial("login_unconfirmed", "нет связи с пультом")})});
  assert.equal(c.ready(), false);
  await c.select([1]);
  assert.deepEqual(c.state.selected, [1]);
  assert.equal(c.needsSelectionSync, true);
  assert.deepEqual(c.socket.sent, []);
  await assert.rejects(c.control({ a: "dim", v: 50 }), { code: "login_unconfirmed" });
  await assert.rejects(c.action({ a: "scene_go", id: "pianist" }), { code: "login_unconfirmed" });
  assert.equal(c.ready("show_status"), true);
  assert.equal(c.ready("halt"), true);
  assert.deepEqual(c.socket.sent, []);
  // Once MA2 becomes ready, the first light control automatically syncs selection first.
  c.receive({status: statusFor()});
  const dim = c.control({ a: "dim", v: 50 });
  assert.equal(c.socket.sent[0].a, "select_fixtures");
  assert.deepEqual(c.socket.sent[0].ids, [1]);
  c.receive({request_id: c.socket.sent[0].request_id, a: "select_fixtures", ok: true});
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(c.socket.sent[1].a, "dim");
  c.receive({request_id: c.socket.sent[1].request_id, a: "dim", ok: true});
  await dim;
  assert.equal(c.needsSelectionSync, false);
});

test("selection changes during preflight cancel the queued light command", async () => {
  const c = connected();
  const first = c.select([1]);
  const dim = c.control({ a: "dim", v: 50 });
  const second = c.select([]);
  const [firstRequest, secondRequest] = c.socket.sent;
  c.receive({ request_id: firstRequest.request_id, a: "select_fixtures", ok: true });
  await first;
  await assert.rejects(dim, { code: "selection_pending" });
  c.receive({ request_id: secondRequest.request_id, a: "clear", ok: true });
  await second;
  assert.deepEqual(c.socket.sent.map(({ a, ids }) => ({ a, ids })),
    [{ a: "select_fixtures", ids: [1] }, { a: "clear", ids: undefined }]);
});

test("connecting, login failure, authenticated with pending show, and mismatch are distinct", async () => {
  const c = new BridgeClient();
  assert.equal(c.blockReason("dim").code, "bridge_disconnected");
  c.socket = new Socket();
  assert.equal(c.blockReason("dim").code, "connecting");
  c.receive({status: statusFor({ma2: "tcp", name: null, blocked: denial("connecting", "нет связи")})});
  assert.equal(c.connectionKey(), "connection.login_check");
  c.receive({status: statusFor({ma2: "login_failed", name: null, blocked: denial("connection_error", "нет связи")})});
  assert.equal(c.connectionKey(), "connection.login_failed");
  c.receive({status: statusFor({name: null, showState: "pending", blocked: denial("show_pending", "текущее шоу не подтверждено")})});
  assert.equal(c.connectionKey(), "connection.authenticated");
  await assert.rejects(c.action({a: "dim", v: 10}), { code: "show_pending" });

  c.receive({status: statusFor({name: "Other", showState: "mismatch",
    blocked: denial("show_mismatch", "на пульте другое шоу"), master: denial("safety_denied", "allow_master")})});
  await assert.rejects(c.action({a: "scene_go", id: "pianist"}), { code: "show_mismatch" });
  await assert.rejects(c.action({a: "master", v: 50}), { code: "safety_denied" });
  assert.equal(c.ready("group_save"), true);
  assert.equal(c.ready("blackout"), true);
  assert.deepEqual(c.socket.sent, []);
  c.receive({status: statusFor()});
  await ack(c, c.select([1]));
  assert.deepEqual(c.state.selected, [1]);
});

test("desk loss and reconnect invalidate selection ACK and never repeat an operation", async () => {
  const c = connected();
  const config = c.state.config;
  c.receive({live: {1: {dim: 40}}, values_meta: {live: {source: "ma2", freshness: "fresh", updated_at: 1}}});
  const selection = c.select([1]);
  const request = c.socket.sent[0];
  c.receive({status: statusFor({ma2: "down", name: null, showState: "pending",
    blocked: denial("connection_error", "нет связи")})});
  assert.equal(c.state.history[1].dim.quality, "last");
  assert.equal(c.state.config, config);
  c.receive({status: statusFor({name: null, showState: "pending", blocked: denial("recovering", "восстановление")})});
  assert.equal(c.blockReason("dim").code, "recovering");
  c.receive({status: statusFor({name: "Other", showState: "mismatch", blocked: denial("show_mismatch", "другое шоу")})});
  c.receive({request_id: request.request_id, ok: true});
  await selection;
  assert.deepEqual(c.state.selected, []);
  assert.deepEqual(c.state.history, {});
  assert.equal(c.state.config, config);
  assert.equal(c.socket.sent.length, 1);
});

test("a ready snapshot can still be refused by the bridge", async () => {
  const c = connected();
  const p = c.action({a: "dim", v: 42});
  c.receive({request_id: c.socket.sent[0].request_id, ok: false, err: "legacy",
    reason: denial("rdm_active", "Идёт поиск RDM")});
  await assert.rejects(p, { code: "rdm_active" });
  assert.equal(c.state.feedback, null);
});

test("automatic plan snapshot cancels old requests and ignores late status, config and ACK", async () => {
  const c = connected();
  const oldStatus = c.state.status;
  const original = {...c.state.config, revision: "bridge:1"};
  c.receive({config: original, shown: {1: {dim: 80}}, running: {s1: true}, values_revision: 10});
  c.state.selected = [1];
  const select = c.select([1]);
  const selectId = c.socket.sent.at(-1).request_id;
  const edit = c.action({a: "group_save", id: "g"});
  const editId = c.socket.sent.at(-1).request_id;
  const expected = Promise.all([assert.rejects(select, { code: "plan_context_changed" }), assert.rejects(edit, { code: "plan_context_changed" })]);
  const config = {revision: "bridge:2", show: "Concert B", fixtures: [{id: 1}]};
  const status = {...statusFor({name: config.show}), blackout_epoch: 8,
    plan_selection: {state: "loaded", name: config.show, revision: config.revision}};
  c.receive({status, config, shown: {}, live: {}, running: {}, values_revision: 11});
  await expected;
  c.receive({status: oldStatus});
  c.receive({config: original, shown: {1: {dim: 80}}, values_revision: 10});
  c.receive({ok: true, request_id: selectId});
  c.receive({ok: true, request_id: editId});
  assert.deepEqual(c.state.config, config);
  assert.deepEqual(c.state.status.plan_selection, status.plan_selection);
  assert.deepEqual(c.state.selected, []);
  assert.deepEqual(c.state.shown, {});
  assert.deepEqual(c.state.running, {});
  assert.equal(c.state.feedback, null);
  assert.equal(c.socket.sent.length, 2);
});

for (const a of ["scene_go", "scene_off"]) {
  test(`${a} keeps snapshot and never replays on timeout or reconnect`, async (t) => {
    t.mock.timers.enable({ apis: ["setTimeout"] });
    const c = connected(), original = c.socket;
    const intent = { a, id: "s1", scene_identity: "original", config_revision: "rev-old" };
    const waiting = c.action(intent);
    const request = original.sent[0];
    assert.equal(request.config_revision, "rev-old");
    assert.equal(request.scene_identity, "original");
    const timedOut = assert.rejects(waiting, { code: "command_unknown" });
    t.mock.timers.tick(45000);
    await timedOut;
    assert.equal(original.sent.length, 1);
    c.receive({ request_id: request.request_id, ok: true, a });
    assert.equal(c.pending.size, 0);
    const interrupted = c.action(intent);
    c.disconnected();
    await assert.rejects(interrupted, { code: "command_unknown" });
    c.socket = new Socket();
    c.receive({ status: statusFor(), config: { revision: "rev-new", scenes: [{ id: "s1", identity: "new" }] } });
    t.mock.timers.tick(45000);
    assert.deepEqual(c.socket.sent, []);
    assert.equal(original.sent.length, 2);
  });
}

test("server actionHistory updates independently of fixture observations and sends undo with entry n", async () => {
  const c = connected();
  c.receive({
    live: { 1: { dim: 50 } },
    values_meta: { live: { source: "ma2", freshness: "fresh", updated_at: 10 } },
    values_revision: 1,
    history: [
      { n: 1, t: "12:00:00", a: "dim", what: "Яркость 50 % · приборов: 1", undo: true, done: false, reason: "" },
    ],
  });
  assert.equal(c.state.history[1]?.dim?.value, 50);
  assert.equal(c.state.actionHistory.length, 1);
  assert.equal(c.state.actionHistory[0].n, 1);
  const undoPromise = c.action({ a: "undo", n: 1 });
  const sent = c.socket.sent.at(-1);
  assert.equal(sent.a, "undo");
  assert.equal(sent.n, 1);
  c.receive({ request_id: sent.request_id, ok: true, a: "undo" });
  await undoPromise;
  c.disconnected();
  assert.deepEqual(c.state.actionHistory, []);
});

test("sceneSlot updates from server messages and clears on show switch or disconnect", () => {
  const c = connected();
  c.receive({ scene_slot: { request: "r1", state: "ready", exec: "2.1", token: "tok-1", checked: 1, total: 250 } });
  assert.deepEqual(c.state.sceneSlot, { request: "r1", state: "ready", exec: "2.1", token: "tok-1", checked: 1, total: 250 });
  c.receive({ config: { revision: "rev-B", show: "Other Show", fixtures: [{ id: 1 }] } });
  assert.equal(c.state.sceneSlot, null);
  c.receive({ scene_slot: { request: "r2", state: "searching", checked: 0, total: 10 } });
  assert.equal(c.state.sceneSlot.state, "searching");
  c.disconnected();
  assert.equal(c.state.sceneSlot, null);
});
