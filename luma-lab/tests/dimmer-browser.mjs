import assert from "node:assert/strict";
import { chromium } from "playwright";

const url = new URL(process.env.LUMA_URL || "http://127.0.0.1:5178");
assert.equal(url.hostname, "127.0.0.1");

const browser = await chromium.launch();
const results = [];
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const actions = [];
const section = page.getByRole("region", { name: "Dimmer", exact: true });
try {
  page.setDefaultTimeout(8000);
  const replies = new Map(), errors = [];
  let socket, lastStatus, liveOverride, statusOverride;
  page.on("pageerror", (error) => errors.push(error.message));
  await page.routeWebSocket("**/ws", (client) => {
    socket = client;
    liveOverride = null;
    const server = client.connectToServer();
    client.onMessage((frame) => {
      actions.push(JSON.parse(frame));
      server.send(frame);
    });
    server.onMessage((frame) => {
      const message = JSON.parse(frame);
      if (message.status) lastStatus = { ...message.status };
      if (message.request_id && "ok" in message) replies.set(message.request_id, message);
      if (liveOverride && message.values_meta) {
        message.values_meta.live = liveOverride.values_meta.live;
        if ("live" in message) message.live = liveOverride.live;
      }
      if (statusOverride && message.status) Object.assign(message.status, statusOverride);
      client.send(JSON.stringify(message));
    });
  });
  const settled = (ids) => page.waitForFunction((ids) => {
    const bridge = window.testBridge;
    return bridge.state.status?.mock === true && bridge.ready("dim") &&
      !bridge.pending.size && bridge.state.selected.join(",") === ids.join(",");
  }, ids);
  const fixture = (id) => page.locator(`[data-fixture="${id}"]`);
  const select = async (id, modifier) => {
    await fixture(id).click({ modifiers: modifier ? [modifier] : [] });
  };
  const target = section.getByRole("textbox", { name: "Target brightness (%)" });
  const slider = page.getByRole("slider", { name: "Dimmer", exact: true });
  const apply = section.getByRole("button", { name: "Apply", exact: true });
  const current = section.getByRole("status");
  const assertCurrent = async (value) => {
    await current.filter({ hasText: `Current · ${value}` }).waitFor();
  };
  const dimActions = () => actions.filter(({ a }) => a === "dim");
  const receipt = async (value, sequence) => {
    assert.deepEqual(dimActions().map(({ v }) => v), sequence);
    const request = dimActions().at(-1);
    assert.equal(request.v, value);
    const deadline = Date.now() + 8000;
    while (!replies.has(request.request_id) && Date.now() < deadline)
      await new Promise((resolve) => setTimeout(resolve, 50));
    const reply = replies.get(request.request_id);
    assert.equal(reply?.ok, true);
    assert.equal(reply.outcome, "completed");
    assert(reply.command_evidence?.length);
    assert(reply.command_evidence.every((evidence) => evidence === "sent"));
  };
  // The standard mock has no dimmer readback. Inject only inbound evidence;
  // selections, light commands and acknowledgements still use the real mock bridge.
  let stamp = Date.now() / 1000;
  const sample = (live) => ({ live, values_meta: {
    live: { source: "ma2", freshness: "fresh", updated_at: ++stamp },
  } });
  const deliver = (message) => {
    if (message.live) liveOverride = message;
    socket.send(JSON.stringify(message));
  };
  const noArrowCommands = async (control, key) => {
    const before = actions.length;
    await control.press(key);
    assert.deepEqual(actions.slice(before), [], `${key} must send no action`);
  };

  await page.goto(url.href);
  await page.evaluate(async () => {
    const module = performance.getEntriesByType("resource")
      .find(({ name }) => new URL(name).pathname === "/src/client.mjs");
    window.testBridge = (await import(module.name)).bridge;
  });
  await settled([]);
  await select(9);
  await settled([9]);

  const toggle = page.locator(".inspector-toggle");
  const reopen = async () => {
    const before = actions.length;
    await toggle.click();
    await page.locator(".inspector-strip").waitFor();
    await settled([9]);
    await toggle.click();
    await section.waitFor();
    assert.deepEqual(actions.slice(before), []);
  };
  await target.fill("75");
  await reopen();

  // This also exercises the original slider when checking the regression against old code.
  const unknownControl = (await slider.count()) ? slider : target;
  if (unknownControl === slider) assert.equal(await slider.getAttribute("aria-valuetext"), "Unknown value");
  for (const key of ["ArrowUp", "ArrowDown"]) {
    await noArrowCommands(unknownControl, key);
    results.push(`unknown + ${key}: no actions`);
  }
  await assertCurrent("Unknown");
  assert.equal(await slider.count(), 0);
  assert.equal(await target.inputValue(), "");
  await target.fill("101");
  assert(await apply.isDisabled());
  await target.press("Enter");
  assert.equal(dimActions().length, 0);
  await target.fill("60");
  assert.equal(dimActions().length, 0);
  await apply.click();
  await settled([9]);
  await receipt(60, [60]);
  results.push("explicit 60%: one dim request, mock completed");
  await assertCurrent("Unknown");
  await section.getByText("Last request · 60%", { exact: true }).waitFor();
  assert.equal(await slider.count(), 0);
  assert.equal(await target.inputValue(), "");
  results.push("sent without readback: current remains unknown");

  const readback40 = sample({ 9: { dim: 40 } });
  deliver(readback40);
  await assertCurrent("40%");
  await reopen();
  await assertCurrent("40%");
  await slider.press("ArrowUp");
  await settled([9]);
  await receipt(41, [60, 41]);
  await assertCurrent("Unknown");
  assert(await target.evaluate((element) => element === document.activeElement));
  await noArrowCommands(target, "ArrowDown");
  results.push("fresh 40% + ArrowUp: one dim 41%, focus stays in dimmer");

  deliver(sample({ 9: { dim: 40 } }));
  await assertCurrent("40%");
  await page.waitForFunction(() => {
    const bridge = window.testBridge;
    return bridge.state.history[9]?.dim?.quality === "last";
  }, null, { timeout: 9000 });
  await assertCurrent("Unknown");
  await noArrowCommands(target, "ArrowUp");
  results.push("readback expiry: current becomes unknown");

  await select(10, "Shift");
  await settled([9, 10]);
  deliver(sample({ 9: { dim: 40 } }));
  await assertCurrent("Unknown");
  const mixed = sample({ 9: { dim: 40 }, 10: { dim: 70 } });
  deliver(mixed);
  await assertCurrent("Mixed");
  assert.equal(await slider.count(), 0);
  await noArrowCommands(target, "ArrowUp");
  await noArrowCommands(target, "ArrowDown");
  await target.fill("55.5");
  await target.press("Enter");
  await settled([9, 10]);
  await receipt(55.5, [60, 41, 55.5]);
  await page.waitForFunction(() => {
    const bridge = window.testBridge;
    return [9, 10].every((id) => bridge.state.shown[id]?.dim === 55.5);
  });
  results.push("mixed and partial readback: no implicit action, explicit target applies to both");

  await select(9);
  await settled([9]);
  await select(19, "Shift");
  await settled([9, 19]);
  const unsupported = await page.evaluate(() => {
    const bridge = window.testBridge;
    return bridge.state.config.fixtures.find(({ id }) => id === 19).type;
  });
  statusOverride = { no_attr: { ...lastStatus.no_attr, dim: [unsupported] } };
  deliver({ status: { ...lastStatus, ...statusOverride } });
  await section.getByText(/Dimmer available on 1 of 2/).waitFor();
  assert(await target.isDisabled());
  assert(await apply.isDisabled());
  assert.equal(dimActions().length, 3);
  results.push("partial support: restriction shown, entire change disabled");
  statusOverride = null;
  deliver({ status: lastStatus });

  await select(9);
  await settled([9]);
  await target.fill("75");
  await page.getByRole("button", { name: "Clear selection", exact: true }).click();
  await settled([]);
  await select(10);
  await settled([10]);
  assert.equal(await target.inputValue(), "");
  assert.equal(await section.getByText(/Last request/).count(), 0);
  await target.press("Enter");
  assert.equal(dimActions().length, 3);
  results.push("clear/reselect: draft and last request stay out of the new selection");

  const readback10 = sample({ 10: { dim: 40 } });
  deliver(readback10);
  await assertCurrent("40%");
  await target.fill("80");
  await page.evaluate(() => window.testBridge.socket.close());
  await page.waitForFunction(() => !window.testBridge.state.connected);
  await settled([]);
  await select(10);
  await settled([10]);
  deliver(readback10);
  await assertCurrent("Unknown");
  assert.equal(await slider.count(), 0);
  assert.equal(await target.inputValue(), "");
  results.push("WebSocket reconnect: cached readback and draft cannot return");

  const newSample = sample({ 10: { dim: 40 } });
  deliver(newSample);
  await assertCurrent("40%");
  await target.fill("90");
  statusOverride = { show: { name: "Different mock show", source: "ma2" } };
  deliver({ ...newSample, status: { ...lastStatus, ...statusOverride } });
  await settled([]);
  await select(10);
  await settled([10]);
  deliver(newSample);
  await assertCurrent("Unknown");
  assert.equal(await target.inputValue(), "");
  await noArrowCommands(target, "ArrowUp");
  assert.deepEqual(dimActions().map(({ v }) => v), [60, 41, 55.5]);
  results.push("show switch: cached readback and draft cannot return");
  assert.deepEqual(errors, []);
  console.log(`PASS ${results.length} dimmer browser checks\n• ${results.join("\n• ")}`);
} catch (error) {
  console.error("Finished checks:", results);
  console.error("Actions:", actions.map(({ a, ids, v }) => ({ a, ids, v })));
  console.error("Inspector:", await section.innerText({ timeout: 200 }).catch(() => ""));
  console.error("State:", await page.evaluate(() => {
    const bridge = window.testBridge;
    return { ready: bridge.ready("dim"), selected: bridge.state.selected, history: bridge.state.history, floor: bridge.dimReadbackFloor, meta: bridge.state.values_meta.live };
  }).catch(() => null));
  throw error;
} finally {
  await browser.close();
}
