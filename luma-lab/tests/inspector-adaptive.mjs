import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import { join } from "node:path";
import { chromium } from "playwright";

const url = new URL(process.env.LUMA_URL || "http://127.0.0.1:5178");
assert.equal(url.hostname, "127.0.0.1");
const shots = process.env.LUMA_INSPECTOR_ARTIFACTS;
if (shots) await mkdir(shots, { recursive: true });

const browser = await chromium.launch();
const screens = [
  { width: 1440, height: 900, touch: false },
  { width: 1024, height: 768, touch: false },
  { width: 1180, height: 820, touch: true },
  { width: 820, height: 1180, touch: true },
  // Browser zoom halves the available CSS pixels while doubling their device size.
  { width: 720, height: 450, touch: false, scale: 2 },
];
const strings = {
  en: { hall: "Hall", fixtures: "Fixtures", open: "Open Inspector",
    collapse: "Collapse Inspector", clear: "Clear selection", two: "2 fixtures", dim: "Dimmer" },
  ru: { hall: "Зал", fixtures: "Приборы", open: "Открыть инспектор",
    collapse: "Свернуть инспектор", clear: "Снять выделение", two: "2 прибора", dim: "Яркость" },
};

async function check(locale, { width, height, touch, scale = 1 }) {
  const page = await browser.newPage({ viewport: { width, height }, hasTouch: touch,
    isMobile: touch, deviceScaleFactor: scale });
  page.setDefaultTimeout(5000);
  const t = strings[locale];
  const actions = [], errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("websocket", ws => {
    if (!new URL(ws.url()).pathname.endsWith("/ws")) return;
    ws.on("framesent", ({ payload }) => {
      const { a } = JSON.parse(payload);
      if (a) actions.push(a);
    });
  });
  await page.addInitScript(lang => localStorage.setItem("luma.language.v1", lang), locale);
  const button = name => page.getByRole("button", { name, exact: true });
  const nav = name => page.locator(".main-nav").getByRole("button", { name, exact: true });
  const click = element => touch ? element.tap() : element.click();
  const dock = page.locator(".inspector-dock");
  const toggle = page.locator(".inspector-toggle");
  const fixture = id => page.locator(`[data-fixture="${id}"]`);
  const card = id => page.locator(`[data-catalog-fixture="${id}"]`);
  const dimmer = page.getByRole("region", { name: t.dim });
  const open = button(t.open);
  const collapse = button(t.collapse);
  const settled = ids => page.waitForFunction(async ids => {
    const { bridge } = await import("/src/client.mjs");
    return bridge.state.status?.mock === true && bridge.ready("dim") && !bridge.pending.size &&
      !bridge.state.selecting && String(bridge.state.selected) === String(ids);
  }, ids);
  const noActions = async operation => {
    const before = actions.length;
    await operation();
    assert.deepEqual(actions.slice(before), []);
  };
  const fullWidth = async () => {
    assert.equal(await dock.count(), 0);
    const { main, workspace, overflow } = await page.locator(".inspector-workspace").evaluate(el => ({
      main: el.querySelector("main").offsetWidth,
      workspace: el.clientWidth,
      overflow: document.documentElement.scrollWidth - innerWidth,
    }));
    assert.equal(main, workspace);
    assert(overflow <= 1);
    return main;
  };
  const header = async () => {
    assert(await page.locator(".global-bar .blackout").evaluate(el => {
      const r = el.getBoundingClientRect();
      return r.height >= 44 && [0.1, 0.5, 0.9].every(f =>
        el.contains(document.elementFromPoint(r.left + r.width * f, r.top + r.height / 2)));
    }));
  };
  const shot = async suffix => {
    if (shots && locale === "en" && scale === 1) {
      await page.screenshot({ path: join(shots, `${suffix}-${width}x${height}.png`) });
    }
  };

  try {
    await page.goto(url.href);
    await settled([]);
    const hallWidth = await fullWidth();
    await header();
    await shot("after");
    await noActions(async () => {
      await click(open);
      await dock.waitFor();
      assert.equal(await toggle.getAttribute("aria-expanded"), "true");
      assert.equal(await dimmer.count(), 0);
      await click(toggle);
      await fullWidth();
      await click(nav(t.fixtures));
      await card(9).waitFor();
      assert.equal(await fullWidth(), hallWidth);
      await click(nav(t.hall));
      await fixture(9).waitFor();
    });

    await click(fixture(9));
    await settled([9]);
    const side = width >= 1024;
    await dock.waitFor();
    assert(await dock.evaluate((el, side) => el.classList.contains(side ? "side" : "bottom"), side));
    await noActions(() => click(collapse));
    assert.equal(await fullWidth(), hallWidth);
    assert.match(await page.locator(".inspector-summary").innerText(), /Moving Head 09/);
    await shot("after-selected");
    await click(fixture(10));
    await settled([10]);
    assert.match(await page.locator(".inspector-summary").innerText(), /Moving Head 10/);
    await click(fixture(9));
    await settled([9]);
    await noActions(() => click(open));

    if (!side) {
      assert.equal(await page.getByRole("separator").count(), 0);
    } else {
      const handle = page.getByRole("separator");
      await noActions(async () => {
        const initial = Number(await handle.getAttribute("aria-valuenow"));
        await handle.press("ArrowRight");
        assert.equal(Number(await handle.getAttribute("aria-valuenow")), initial - 20);
        const r = await handle.boundingBox();
        await page.mouse.move(r.x + r.width / 2, r.y + 100);
        await page.mouse.down();
        await page.mouse.move(r.x + r.width / 2 + 30, r.y + 100, { steps: 4 });
        await page.mouse.up();
        assert(await handle.evaluate(el => el === document.activeElement));
        assert.equal(Number(await handle.getAttribute("aria-valuenow")), initial - 50);
      });
    }
    await dimmer.waitFor();
    const plot = await page.locator(".stage-viewport").boundingBox();
    assert(plot.height >= 130 && plot.width >= 500);
    await header();
    await shot("after-open");

    await noActions(async () => {
      if (width === 1440 && scale === 1) {
        const handle = page.getByRole("separator");
        const oldWidth = await handle.getAttribute("aria-valuenow");
        await handle.focus();
        await page.setViewportSize({ width: 820, height: 900 });
        await page.locator(".inspector-dock.bottom").waitFor();
        assert(await collapse.evaluate(el => el === document.activeElement));
        await page.setViewportSize({ width, height });
        await handle.waitFor();
        assert.equal(await handle.getAttribute("aria-valuenow"), oldWidth);
      }
      if (touch) {
        const target = dimmer.getByRole("slider", { name: t.dim, exact: true });
        await target.focus();
        await page.setViewportSize({ width: height, height: width });
        await page.locator(`.inspector-dock.${side ? "bottom" : "side"}`).waitFor();
        await dimmer.waitFor();
        assert(await target.evaluate(el => el === document.activeElement));
        await settled([9]);
        await header();
        await page.setViewportSize({ width, height });
        await header();
      }
      await collapse.press("Enter");
      assert(await open.evaluate(el => el === document.activeElement));
      assert.equal(await fullWidth(), hallWidth);
      await settled([9]);
      await click(nav(t.fixtures));
      assert.equal(await fullWidth(), hallWidth);
      assert.equal(await card(9).getAttribute("aria-pressed"), "true");
      await open.press("Space");
      assert(await collapse.evaluate(el => el === document.activeElement));
      await dimmer.waitFor();
      await click(nav(t.hall));
      await dimmer.waitFor();
      await settled([9]);
      await header();
    });

    await fixture(10).click({ modifiers: ["Shift"] });
    await settled([9, 10]);
    await noActions(async () => {
      await click(collapse);
      assert.match(await page.locator(".inspector-summary").innerText(), new RegExp(t.two));
      await click(open);
      await dimmer.waitFor();
    });

    await button(t.clear).press("Enter");
    await settled([]);
    assert(await open.evaluate(el => el === document.activeElement));
    await fullWidth();
    await header();
    assert.deepEqual(errors, []);
    assert.deepEqual(actions, [
      ...Array(4).fill("select_fixtures"), "clear",
    ]);
    console.log(`PASS ${locale} ${width}×${height}${scale === 2 ? " (200%)" : ""}: ${actions.join(", ")}`);
  } finally {
    await page.close();
  }
}

try {
  for (const locale of Object.keys(strings)) {
    for (const screen of screens) await check(locale, screen);
  }
} finally {
  await browser.close();
}
