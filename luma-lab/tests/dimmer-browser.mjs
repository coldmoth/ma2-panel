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
  const slider = section.getByRole("slider", { name: "Dimmer", exact: true });
  const preset = (value) => section.getByRole("button", { name: `${value}%`, exact: true });
  const evidence = (quality) => section.locator(`.evidence-dot.${quality}`);
  const assertCurrent = async (value) => {
    await section.locator(".dimmer-readout").filter({ hasText: value }).waitFor();
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
  await reopen();
  await slider.waitFor();
  assert.equal(await slider.getAttribute("aria-valuetext"), "Unknown value");
  await evidence("unknown").waitFor();
  for (const key of ["ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown"])
    await noArrowCommands(slider, key);
  results.push("unknown: mounted slider, no keyboard actions");

  await preset(50).click();
  await settled([9]);
  await receipt(50, [50]);
  await assertCurrent("50%");
  assert.equal(await evidence("confirmed").count(), 0);
  await noArrowCommands(slider, "ArrowUp");
  results.push("explicit preset sends one request; panel echo cannot authorize a relative step");

  const readback40 = sample({ 9: { dim: 40 } });
  deliver(readback40);
  await evidence("confirmed").waitFor();
  await reopen();
  await assertCurrent("40%");
  await slider.press("ArrowUp");
  await settled([9]);
  await receipt(41, [50, 41]);
  assert(await slider.evaluate(element => element === document.activeElement));
  await noArrowCommands(slider, "ArrowDown");
  results.push("fresh 40% + ArrowUp sends exactly 41% and preserves focus");

  deliver(sample({ 9: { dim: 40 } }));
  await evidence("confirmed").waitFor();
  await slider.focus();
  await page.keyboard.down("ArrowUp");
  await evidence("last").waitFor({ timeout: 9000 });
  const beforeKeyUp = actions.length;
  await page.keyboard.up("ArrowUp");
  assert.deepEqual(actions.slice(beforeKeyUp), []);
  await noArrowCommands(slider, "ArrowUp");
  await assertCurrent("40%");
  results.push("expiry during a keyboard gesture discards the step; stale readback stays visible");

  await select(10, "Shift");
  await settled([9, 10]);
  deliver(sample({ 9: { dim: 40 } }));
  assert.equal(await evidence("confirmed").count(), 0);
  await noArrowCommands(slider, "ArrowUp");
  const mixed = sample({ 9: { dim: 40 }, 10: { dim: 70 } });
  deliver(mixed);
  await assertCurrent("Mixed");
  await evidence("confirmed").waitFor();
  await noArrowCommands(slider, "ArrowUp");
  await noArrowCommands(slider, "ArrowDown");
  await preset(75).press("Enter");
  await settled([9, 10]);
  await receipt(75, [50, 41, 75]);
  await page.waitForFunction(() => {
    const bridge = window.testBridge;
    return [9, 10].every((id) => bridge.state.shown[id]?.dim === 75);
  });
  results.push("mixed and partial readback send no inferred value; explicit preset applies to both");

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
  assert(await slider.isDisabled());
  for (const value of [0, 25, 50, 75, 100]) assert(await preset(value).isDisabled());
  assert.equal(dimActions().length, 3);
  results.push("partial support disables the slider and all presets");
  statusOverride = null;
  deliver({ status: lastStatus });

  await page.getByRole("button", { name: "Clear selection", exact: true }).click();
  await settled([]);
  await select(10);
  await settled([10]);
  assert.equal(await evidence("confirmed").count(), 0);
  await noArrowCommands(slider, "ArrowUp");
  results.push("clear and reselect cannot reuse readback");

  const readback10 = sample({ 10: { dim: 40 } });
  deliver(readback10);
  await evidence("confirmed").waitFor();
  await page.evaluate(() => window.testBridge.socket.close());
  await page.waitForFunction(() => !window.testBridge.state.connected);
  await settled([10]);
  deliver(readback10);
  assert.equal(await evidence("confirmed").count(), 0);
  await noArrowCommands(slider, "ArrowUp");
  results.push("WebSocket reconnect preserves selection and invalidates cached readback");

  const newSample = sample({ 10: { dim: 40 } });
  deliver(newSample);
  await evidence("confirmed").waitFor();
  statusOverride = { show: { name: "Different mock show", source: "ma2" } };
  deliver({ ...newSample, status: { ...lastStatus, ...statusOverride } });
  await settled([]);
  await select(10);
  await settled([10]);
  deliver(newSample);
  await evidence("unknown").waitFor();
  await noArrowCommands(slider, "ArrowUp");
  assert.deepEqual(dimActions().map(({ v }) => v), [50, 41, 75]);
  results.push("show switch cannot reuse cached readback");
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
