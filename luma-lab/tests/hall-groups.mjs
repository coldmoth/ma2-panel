import assert from "node:assert/strict";
import { chromium } from "playwright";

const url = new URL(process.env.LUMA_URL || "http://127.0.0.1:5178");
assert.equal(url.hostname, "127.0.0.1");

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 820, height: 1180 }, hasTouch: true });
  const actions = [], errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("websocket", ws => ws.on("framesent", ({ payload }) => {
    const { request_id, config_revision, blackout_epoch, ...action } = JSON.parse(payload);
    if (action.a) actions.push(action);
  }));
  // The stock mock has no imported console groups. Exercise that config shape while
  // still letting the real mock validate and acknowledge the explicit fixture IDs.
  await page.routeWebSocket("**/ws", client => {
    const server = client.connectToServer();
    server.onMessage(frame => {
      const message = JSON.parse(frame);
      if (message.config) {
        message.config.ma2groups = [...(message.config.ma2groups || []), { n: 42, name: "Imported heads", ids: [10, 9] }];
      }
      client.send(JSON.stringify(message));
    });
  });
  const settled = ids => page.waitForFunction(ids => {
    const bridge = window.hallGroupsTestBridge;
    return bridge.state.status?.mock === true && bridge.ready() &&
      !bridge.pending.size && !bridge.state.selecting && String(bridge.state.selected) === String(ids);
  }, ids);
  const edit = action => page.evaluate(async action => {
    const { bridge } = await import("/src/client.mjs");
    return bridge.action(action);
  }, action);
  const toggle = page.getByRole("button", { name: "Groups", exact: true });
  const list = page.getByRole("region", { name: "Groups", exact: true });
  const label = "Hall group regression";

  await page.goto(url.href);
  await page.evaluate(async () => { window.hallGroupsTestBridge = (await import("/src/client.mjs")).bridge; });
  await settled([]);
  await toggle.tap();
  await list.waitFor();
  await page.keyboard.press("1");
  await page.keyboard.press("b");
  await page.keyboard.press("b");
  await page.keyboard.down("ArrowRight");
  await page.waitForTimeout(220);
  await page.keyboard.up("ArrowRight");
  await page.keyboard.press("Escape");
  await list.waitFor({ state: "hidden" });
  assert.equal(await toggle.evaluate(el => el === document.activeElement), true);
  assert.deepEqual(actions, []);

  await toggle.tap();
  await list.locator('[data-hall-group="heads"]').tap();
  await settled([9, 10, 11, 12, 13, 14]);
  assert.match(await page.locator(".inspector-summary").textContent(), /6 fixtures/);
  assert.deepEqual(actions.splice(0), [{ a: "select_fixtures", ids: [9, 10, 11, 12, 13, 14] }]);

  await toggle.tap();
  const deskGroup = list.locator('[data-hall-group="ma2:42"]');
  assert.match(await deskGroup.textContent(), /MA2 group.*2 fixtures/i);
  await deskGroup.tap();
  await settled([10, 9]);
  assert.deepEqual(actions.splice(0), [{ a: "select_fixtures", ids: [10, 9] }]);

  await toggle.tap();
  await edit({ a: "group_save", label, ids: [9, 10] });
  const group = list.getByRole("button", { name: new RegExp(label) });
  await group.waitFor();
  assert.match(await group.textContent(), /2 fixtures/);
  const id = await group.getAttribute("data-hall-group");
  await edit({ a: "group_save", id, label, ids: [10] });
  await group.getByText(/1 fixture/).waitFor();
  await group.tap();
  await settled([10]);
  await toggle.tap();

  // The live configuration can change with the list open.
  await edit({ a: "group_save", id, label, ids: [] });
  await group.getByText(/0 fixtures/).waitFor();
  assert.equal(await group.isDisabled(), true);
  await settled([]);
  await edit({ a: "group_delete", id });
  await group.waitFor({ state: "detached" });
  await page.keyboard.press("Escape");
  await list.waitFor({ state: "hidden" });
  assert.deepEqual(actions, [
    { a: "group_save", label, ids: [9, 10] },
    { a: "group_save", id, label, ids: [10] },
    { a: "select_fixtures", ids: [10] },
    { a: "group_save", id, label, ids: [] },
    { a: "group_delete", id },
  ]);
  assert.deepEqual(errors, []);
  console.log("PASS Hall groups: touch, shortcut isolation, exact members, live edits, empty group and deletion");
} finally {
  await browser.close();
}
