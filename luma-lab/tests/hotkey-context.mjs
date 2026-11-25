import assert from "node:assert/strict";
import { chromium } from "playwright";

const url = new URL(process.env.LUMA_URL || "http://127.0.0.1:5178");
assert.equal(url.hostname, "127.0.0.1");
const browser = await chromium.launch();
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const actions = [];
  page.on("websocket", ws => ws.on("framesent", ({ payload }) => {
    const { request_id, config_revision, blackout_epoch, scene_identity, ...action } = JSON.parse(payload);
    if (action.a) actions.push(action);
  }));
  const { keyboard } = page;
  const settled = (selected = []) => page.waitForFunction(async selected => {
    const { bridge } = await import("/src/client.mjs");
    return bridge.state.status?.mock === true && bridge.ready() && !bridge.pending.size &&
      bridge.state.selected.join(",") === selected.join(",");
  }, selected);
  const button = name => page.getByRole("button", { name, exact: true });
  const blackout = page.locator(".blackout");

  await page.goto(url.href);
  await settled();
  await page.locator(".sidebar").getByRole("button", { name: "Keyboard shortcuts", exact: true }).click();
  await page.getByRole("dialog").locator(".shortcut-slots select").nth(0).selectOption("s1");
  await page.keyboard.press("Escape");
  await button("Fixtures").click();
  await page.locator(".fixture-navigation button").filter({ hasText: "Движущиеся головы" }).click();
  await page.locator('[data-catalog-fixture="9"]').click();
  await settled([9]);
  assert(await page.evaluate(async () => (await import("/src/client.mjs")).bridge.ready("jog")));
  actions.length = 0;

  const menu = page.locator(".group-actions");
  const trigger = menu.locator("summary");
  await trigger.click();
  await keyboard.press("1");
  console.log("Menu + 1:", JSON.stringify(actions));
  assert.deepEqual(actions, [], "An open group menu must own the keyboard");
  await keyboard.press("b");
  await keyboard.press("b");
  await keyboard.down("ArrowRight");
  await page.waitForTimeout(250);
  assert.deepEqual(actions, []);
  await menu.locator("button").first().focus();
  await keyboard.down("Escape");
  await keyboard.down("Escape");
  await keyboard.up("Escape");
  await keyboard.down("ArrowRight");
  await page.waitForTimeout(250);
  await keyboard.up("ArrowRight");
  assert.equal(await menu.getAttribute("open"), null);
  assert(await trigger.evaluate(el => el === document.activeElement));
  await settled([9]);
  assert.deepEqual(actions, []);

  await keyboard.down("1");
  await keyboard.down("1");
  await keyboard.up("1");
  await settled([9]);
  assert.deepEqual(actions, [{ a: "scene_go", id: "s1" }]);

  await page.getByRole("searchbox", { name: "Find a fixture" }).focus();
  await keyboard.press("1");
  await keyboard.press("b");
  await keyboard.press("b");
  await keyboard.down("ArrowRight");
  await page.waitForTimeout(220);
  await keyboard.up("ArrowRight");
  assert.deepEqual(actions, [{ a: "scene_go", id: "s1" }]);
  await page.getByRole("searchbox", { name: "Find a fixture" }).clear();
  await trigger.focus();
  await keyboard.press("b");
  await trigger.click();
  // Opening a layer must invalidate the first B, even when Escape immediately follows.
  await keyboard.press("Escape");
  await keyboard.press("b");
  assert.deepEqual(actions, [{ a: "scene_go", id: "s1" }]);

  await trigger.click();
  await menu.locator("button").first().click();
  const dialog = page.getByRole("dialog");
  await dialog.waitFor();
  await keyboard.press("1");
  await keyboard.press("b");
  await keyboard.press("Escape");
  await dialog.waitFor({ state: "hidden" });
  assert(await trigger.evaluate(el => el === document.activeElement));

  await settled([9]);
  const editingActions = [{ a: "scene_go", id: "s1" }, { a: "plan_editing", active: true }, { a: "plan_editing", active: false }];
  assert.deepEqual(actions, editingActions);

  await keyboard.down("b");
  await keyboard.down("b");
  await keyboard.up("b");
  assert.deepEqual(actions, editingActions);
  // Playwright headless can keep both tabs focused. Exercise the browser blur
  // event explicitly, independently of the host window manager.
  await page.evaluate(() => window.dispatchEvent(new Event("blur")));
  await keyboard.press("b");
  assert.deepEqual(actions, editingActions);
  assert(await blackout.evaluate(el => el.classList.contains("armed")));

  await page.evaluate(() => {
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await keyboard.press("1");
  await keyboard.press("b");
  await keyboard.press("b");
  assert.deepEqual(actions, editingActions);
  await page.evaluate(() => {
    delete document.hidden;
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await keyboard.press("b");
  assert.deepEqual(actions, editingActions);
  await keyboard.press("b");
  await page.waitForFunction(() => document.querySelector(".blackout").classList.contains("active"));
  await settled([9]);
  await keyboard.press("b");
  await page.waitForFunction(() => !document.querySelector(".blackout").classList.contains("active"));
  await settled([9]);
  assert(await blackout.isEnabled());
  const expected = [...editingActions, { a: "blackout" }, { a: "blackout" }];
  assert.deepEqual(actions, expected);

  await button("Hall").click();
  const shelf = page.locator(".quick-scenes-toggle");
  await shelf.click();
  await keyboard.press("1");
  await keyboard.press("b");
  await keyboard.press("b");
  await keyboard.press("Escape");
  assert.equal(await shelf.getAttribute("aria-expanded"), "false");
  assert(await shelf.evaluate(el => el === document.activeElement));
  assert.deepEqual(actions, expected);
  console.log("PASS keyboard context:", JSON.stringify(actions));
} finally {
  await browser.close();
}
