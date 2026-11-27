import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { chromium } from "playwright";

const url = new URL(process.env.LUMA_URL || "http://127.0.0.1:5178");
assert.equal(url.hostname, "127.0.0.1");
const artifacts = process.env.LUMA_HALL_ARTIFACTS;

const labels = {
  en: { multiple: "Select multiple", done: "Done", groups: "Groups", cancel: "Cancel", choose: "Choose a fixture", top: "Top view", draft: "Draft selection: " },
  ru: { multiple: "Выбрать несколько", done: "Готово", groups: "Группы", cancel: "Отмена", choose: "Уточните прибор", top: "Вид сверху", draft: "В черновике: " },
};
const browser = await chromium.launch();
try {
  for (const locale of ["en", "ru"]) {
    const t = labels[locale];
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, hasTouch: true });
    page.setDefaultTimeout(8000);
    const actions = [], errors = [], acks = [];
    let rejectNext = false, holdNext = false, deliverAck;
    page.on("pageerror", error => errors.push(error.message));
    await page.addInitScript(lang => localStorage.setItem("luma.language.v1", lang), locale);
    await page.routeWebSocket("**/ws", client => {
      const server = client.connectToServer();
      let heldRequest;
      client.onMessage(frame => {
        const { request_id, config_revision, blackout_epoch, ...action } = JSON.parse(frame);
        if (action.a) actions.push(action);
        if (action.a === "select_fixtures" && holdNext) {
          holdNext = false;
          heldRequest = request_id;
        }
        if (action.a === "select_fixtures" && rejectNext) {
          rejectNext = false;
          server.send(JSON.stringify({ ...JSON.parse(frame), ids: [99999] }));
        } else server.send(frame);
      });
      server.onMessage(frame => {
        const message = JSON.parse(frame);
        if ("ok" in message) acks.push(message);
        if (heldRequest && message.request_id === heldRequest) {
          heldRequest = null;
          deliverAck(() => client.send(frame));
        } else client.send(frame);
      });
    });
    const fixture = id => page.locator(`[data-fixture="${id}"]`);
    const button = name => page.getByRole("button", { name, exact: true });
    const draft = page.locator(".hall-draft");
    const count = n => draft.getByText(t.draft + n, { exact: true }).waitFor();
    const checked = async (id, selected) => assert.equal(await fixture(id).getAttribute("aria-pressed"), String(selected));
    const settled = ids => page.waitForFunction(async ids => {
      const { bridge } = await import("/src/client.mjs");
      return bridge.state.status?.mock === true && bridge.ready() &&
        !bridge.pending.size && !bridge.state.selecting && String(bridge.state.selected) === String(ids);
    }, ids);

    await page.goto(url.href);
    await settled([]);
    await button(t.multiple).tap();
    await count(0);
    await fixture(9).tap();
    await fixture(10).tap();
    await count(2);
    await checked(9, true);
    await checked(10, true);
    await fixture(9).tap();
    await count(1);
    await checked(9, false);
    assert.equal(await fixture(10).locator("[data-hall-hit]").getAttribute("stroke"), "#c1a5ff");
    await page.keyboard.press("1");
    await page.keyboard.press("b");
    await page.keyboard.press("b");
    await page.keyboard.down("ArrowRight");
    await page.waitForTimeout(220);
    await page.keyboard.up("ArrowRight");
    assert.deepEqual(actions, []);

    holdNext = true;
    const heldAck = new Promise(resolve => { deliverAck = resolve; });
    await button(t.done).tap();
    await page.locator(".hall-apply:disabled").waitFor();
    assert.deepEqual(await page.evaluate(async () => (await import("/src/client.mjs")).bridge.state.selected), []);
    assert.equal(await draft.getByRole("button", { name: t.cancel }).isDisabled(), true);
    const releaseAck = await Promise.race([
      heldAck,
      new Promise((_, reject) => setTimeout(() => reject(new Error("Mock acknowledgement timed out")), 8000).unref()),
    ]);
    releaseAck();
    await settled([10]);
    await draft.waitFor({ state: "hidden" });
    assert.deepEqual(actions, [{ a: "select_fixtures", ids: [10] }]);

    await button(t.multiple).tap();
    await count(1);
    await checked(10, true);
    await fixture(9).tap();
    await count(2);
    await button(t.top).tap();
    await checked(9, true);
    await checked(10, true);
    await page.setViewportSize({ width: 820, height: 1180 });
    await page.keyboard.press("Escape");
    await draft.waitFor({ state: "hidden" });
    await settled([10]);
    await checked(9, false);
    await checked(10, true);
    assert.equal(await page.locator(".inspector-toggle").getAttribute("aria-expanded"), "true");
    assert.equal(actions.length, 1);

    await button(t.multiple).tap();
    await fixture(9).tap();
    assert.equal(await page.locator(".unselect").isDisabled(), true);
    assert.equal(await page.locator(".grandmaster").getByRole("slider").isDisabled(), true);
    rejectNext = true;
    await button(t.done).tap();
    await settled([10]);
    await count(2);
    assert.equal(acks.at(-1).ok, false);
    await button(t.cancel).tap();
    await draft.waitFor({ state: "hidden" });
    await checked(9, false);
    await checked(10, true);
    assert.deepEqual(actions.at(-1), { a: "select_fixtures", ids: [10, 9] });

    await fixture(10).focus();
    await page.keyboard.press("Enter");
    await settled([10]);
    await button(t.multiple).tap();
    await fixture(10).tap();
    await count(0);
    await button(t.done).tap();
    await settled([]);
    assert.deepEqual(actions.at(-1), { a: "clear" });

    if (artifacts && locale === "ru") await mkdir(artifacts, { recursive: true });
    for (const [width, height] of [[1440, 900], [1024, 768], [1180, 820], [820, 1180]]) {
      await page.setViewportSize({ width, height });
      await button(t.groups).tap();
      const popup = page.getByRole("region", { name: t.groups, exact: true });
      await popup.waitFor();
      assert.equal(await popup.locator("[data-hall-group]").count() >= 3, true);
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
      if (artifacts && locale === "ru" && width !== 1024 && width !== 1180)
        await page.screenshot({ path: join(artifacts, `hall-${width}x${height}.png`) });
      await page.keyboard.press("Escape");
      await button(t.multiple).tap();
      for (const id of [9, 10]) {
        await fixture(id).focus();
        await page.keyboard.press("Enter");
      }
      await count(2);
      if (artifacts && locale === "ru" && (width === 1024 || width === 1180))
        await page.screenshot({ path: join(artifacts, `hall-${width}x${height}.png`) });
      await button(t.cancel).tap();
    }
    assert.deepEqual(actions.map(a => a.a), ["select_fixtures", "select_fixtures", "select_fixtures", "clear"]);

    if (locale === "ru") {
      // Place two fixture symbols at exactly the same point in the isolated mock plan.
      await page.evaluate(async () => {
        const { bridge } = await import("/src/client.mjs");
        const { x, y } = bridge.state.config.fixtures.find(f => f.id === 10);
        await bridge.action({ a: "layout_save", pos: [{ id: 9, x, y }, { id: 10, x, y }] });
      });
      await page.waitForFunction(() => document.querySelector('[data-fixture="9"]').getAttribute("transform") ===
        document.querySelector('[data-fixture="10"]').getAttribute("transform"));
      const chooser = page.getByRole("region", { name: t.choose });
      async function chooseFixture(useTouch, id) {
        const target = await fixture(10).locator("[data-hall-hit]").boundingBox();
        const x = target.x + target.width / 2, y = target.y + target.height / 2;
        const before = actions.length;
        await (useTouch ? page.touchscreen.tap(x, y) : page.mouse.click(x, y));
        await chooser.waitFor();
        assert.deepEqual(actions.slice(before), []);
        const candidate = chooser.getByRole("button", { name: new RegExp(`, ID ${id}$`) });
        assert.match(await candidate.locator("strong").textContent(), /\S/);
        await (useTouch ? candidate.tap() : candidate.click());
        await chooser.waitFor({ state: "hidden" });
      }
      await chooseFixture(true, 9);
      await settled([9]);
      assert.deepEqual(actions.at(-1), { a: "select_fixtures", ids: [9] });
      await button(t.multiple).tap();
      await chooseFixture(false, 10);
      await count(2);
      await button(t.done).tap();
      await settled([9, 10]);
      assert.deepEqual(actions.slice(-3), [
        { a: "layout_save", pos: actions.at(-3).pos },
        { a: "select_fixtures", ids: [9] },
        { a: "select_fixtures", ids: [9, 10] },
      ]);
    }
    assert.deepEqual(errors, []);
    console.log(`PASS ${locale}: draft toggles, delayed ACK, cancel, refusal, empty selection, rotation, both views, four viewports${locale === "ru" ? ", mouse and touch disambiguation" : ""}`);
    await page.context().close();
  }
} finally {
  await browser.close();
}
