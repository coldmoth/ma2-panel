import { test } from "node:test";
import assert from "node:assert/strict";
import {
  fixtureKind,
  supports,
  commonValue,
  displayValues,
  blackoutKey,
  hexToRGB,
  rgbToHex,
  project,
} from "../src/model.mjs";

test("classification and explicit visual override never alter MA2 type", () => {
  assert.equal(fixtureKind({ type: "LED Bar 18" }), "bar");
  assert.equal(
    fixtureKind({ type: "Generic", params: ["Pan", "Tilt"] }),
    "head",
  );
  assert.equal(fixtureKind({ type: "Profile Spot" }), "profile");
  assert.equal(fixtureKind({ type: "Fresnel" }), "fresnel");
  assert.equal(fixtureKind({ type: "Wall Washer" }), "washer");
  assert.equal(fixtureKind({ type: "Unknown" }), "generic");
  assert.equal(fixtureKind({ type: "Moving Head", icon: "bar" }), "bar");
});
test("unknown capability stays unavailable and missing fixture never controllable", () => {
  assert.equal(supports({ type: "Unknown" }, "dim", {}), false);
  assert.equal(
    supports({ missing: true, params: ["Dimmer"] }, "dim", {}),
    false,
  );
  assert.equal(supports({ params: ["Pan", "Tilt"] }, "pos", {}), true);
  assert.equal(
    supports({ type: "A" }, "zoom", { dmx_map: { A: { has: ["zoom"] } } }),
    true,
  );
  assert.equal(
    supports({ color: "none", params: ["ColorRGB1"] }, "color", {}),
    false,
  );
});
test("per-parameter evidence never labels panel history as readback",()=>{
 const v=displayValues({history:{1:{dim:{value:70,quality:"confirmed"},pan:{value:60,quality:"pending"}}}},1);
 assert.equal(v.dim,70);assert.equal(v.quality.dim,"confirmed");assert.equal(v.quality.pan,"pending");
 assert.equal(displayValues({},1).source,"unknown");
});
test("mixed and unknown values never become zero", () => {
  assert.equal(commonValue([{ dim: 20 }, { dim: 60 }], "dim"), "mixed");
  assert.equal(commonValue([{}, {}], "dim"), null);
  assert.equal(commonValue([{ dim: 20 }, {}], "dim"), "mixed");
});
test("Blackout B requires a second non-repeated press, unknown never restores", () => {
  assert.deepEqual(blackoutKey("idle", null, 100), {
    armedAt: 100,
    send: false,
  });
  assert.equal(blackoutKey("idle", 100, 650).send, true);
  assert.equal(blackoutKey("idle", 100, 701).send, false);
  assert.equal(blackoutKey("unknown", 100, 200).send, false);
  assert.equal(blackoutKey("active", null, 100).send, true);
});
test("RGB/HEX roundtrip uses protocol percentages; stage projects same coordinate source", () => {
  assert.deepEqual(hexToRGB("#ff8000"), [100, 50.2, 0]);
  assert.equal(rgbToHex([100, 50.2, 0]), "#ff8000");
  assert.deepEqual(project(0.5, 0.5, false), [470, 280]);
  assert.deepEqual(project(0.5, 0.5, true), [470, 280]);
});

test("last known survives freshness and pending is not confirmed readback", () => {
  const state = {status:{ma2:"down"}, history:{1:{pan:{value:29.63, quality:"last"},dim:{value:64,quality:"pending"}}}};
  assert.equal(displayValues(state,1).pan,29.63);
  assert.equal(displayValues(state,1).quality.pan,"last");
  assert.equal(displayValues(state,1).quality.dim,"pending");
});

test("plan projection inverses both views and wall orientation respects manual zero",async()=>{
 const {project,unproject,fixtureAngle,stageRect}=await import('../src/model.mjs');
 for(const top of [true,false])for(const xy of [[.1,.2],[.85,.93],[.5,.5]]){
  const hall={w:18,d:26,stage:'left',stageDepth:4,stageWidth:10,stageOffset:.25};
  const actual=unproject(...project(...xy,top,hall),top,hall);
  assert(actual.every((v,i)=>Math.abs(v-xy[i])<1e-10));
  assert.deepEqual(stageRect(hall),[0,(1-10/26)*.25,4/18,10/26]);
 }
 assert.equal(fixtureAngle({x:.03,y:.4},'bar'),90);
 assert.equal(fixtureAngle({x:.4,y:.03},'bar'),0);
 assert.equal(fixtureAngle({x:.03,y:.4,rot:0},'bar'),0);
 assert.equal(fixtureAngle({x:.03,y:.4,rot:37.5},'bar'),37.5);
});

test('auto bars use nearest wall in metres and preserve manual precision', async () => {
 const {fixtureAngle}=await import('../src/model.mjs');
 assert.equal(fixtureAngle({x:.2,y:.1},'bar',{w:4,d:40}),90);
 assert.equal(fixtureAngle({x:.1,y:.2},'bar',{w:40,d:4}),0);
 assert.equal(fixtureAngle({x:.2,y:.1,rot:45.1},'bar',{w:4,d:40}),45.1);
});

test('inspectorLimits allows side dock on laptop and tablet landscape, bottom dock on portrait', async () => {
 const {inspectorLimits}=await import('../src/model.mjs');
 assert(inspectorLimits(1280, 190).max >= 280);
 assert(inspectorLimits(1366, 190).max >= 280);
 assert(inspectorLimits(1024, 68).max >= 280);
 assert(inspectorLimits(1024, 190).max >= 280);
 assert(inspectorLimits(820, 68).max < 280);
});
