import assert from "node:assert/strict";
import { chromium } from "playwright";

const url = new URL(process.env.LUMA_URL || "http://127.0.0.1:5178");
assert.equal(url.hostname, "127.0.0.1");
const browser = await chromium.launch();
const sizes = [[1440, 900], [1024, 768], [1180, 820], [820, 1180]];

try {
  const misses = [];
  for (const language of ["en", "ru"]) {
    for (const scale of [1, 2]) {
      // Browser zoom uses a smaller CSS viewport and more device pixels per CSS pixel.
      const page = await browser.newPage({ deviceScaleFactor: scale, hasTouch: true });
      const actions = [];
      page.on("websocket", ws => ws.on("framesent", ({ payload }) => {
        const { request_id, config_revision, blackout_epoch, ...action } = JSON.parse(payload);
        if (action.a) actions.push(action);
      }));
      await page.addInitScript(locale => localStorage.setItem("luma.language.v1", locale), language);
      const resize = ([width, height]) => page.setViewportSize({ width: width / scale, height: height / scale });
      const phase = expected => page.waitForFunction(async expected => {
        const { bridge } = await import("/src/client.mjs");
        return bridge.state.status?.mock === true && bridge.state.status.blackout?.phase === expected &&
          bridge.ready("blackout") && !bridge.pending.size &&
          document.querySelector(".blackout")?.classList.contains("active") === (expected === "active");
      }, expected);
      const button = page.locator(".global-bar .blackout");
      async function measure(label, inspector) {
        for (const size of sizes) {
          await resize(size);
          const points = await button.evaluate(el => {
            const r = el.getBoundingClientRect();
            const label = el.querySelector("span");
            return {
              hits: [0.1, 0.5, 0.9].map(f => {
                const target = document.elementFromPoint(r.left + r.width * f, r.top + r.height / 2);
                return el.contains(target) ? true : target?.className?.baseVal ?? target?.className ?? null;
              }),
              visible: r.left >= 0 && r.right <= innerWidth && r.top >= 0 && r.bottom <= innerHeight &&
                label.scrollWidth <= label.clientWidth,
              height: r.height,
            };
          });
          if (!points.visible || points.hits.some(hit => hit !== true) || points.height < 44) {
            misses.push({ language, scale, size, label, inspector, ...points });
            if (size[0] === 820) console.log("Portrait hit failure:", JSON.stringify(misses.at(-1)));
          }
        }
      }
      await resize(sizes[0]);
      await page.goto(url.href);
      await phase("idle");
      await page.locator(".inspector-strip").waitFor();
      await measure("Blackout", false);
      await resize(sizes[0]);
      await page.locator('[data-fixture="9"]').click();
      await page.locator(".inspector-strip .unselect").waitFor();
      await page.locator(".inspector-toggle").click();
      await page.locator(".inspector-dock.bottom .inspector").waitFor();
      await measure("Blackout", true);
      await page.setViewportSize({ width: 1180, height: 820 });
      await button.click();
      await phase("active");
      const restore = language === "ru" ? "Восстановить" : "Restore";
      assert.equal(await button.locator("span").textContent(), restore);
      await page.locator(".inspector-strip").waitFor();
      // The bridge clears the selection when Blackout activates.
      await measure(restore, false);

      // Physical hit at the center after rotation. On failure use the wide
      // viewport to reset the mock before checking the next locale and scale.
      const r = await button.boundingBox();
      const centerHitsButton = await button.evaluate(el => {
        const r = el.getBoundingClientRect();
        return el.contains(document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2));
      });
      const before = actions.length;
      await page.touchscreen.tap(r.x + r.width / 2, r.y + r.height / 2);
      if (!centerHitsButton) {
        misses.push({ language, scale, error: "Center of Restore sent no action" });
        await page.setViewportSize({ width: 1440, height: 900 });
        await button.click();
      }
      await phase("idle");
      assert.deepEqual(actions.slice(before), [{ a: "blackout" }]);
      assert.deepEqual(actions.map(action => action.a), ["select_fixtures", "blackout", "blackout"]);
      console.log(language, scale, JSON.stringify(actions));
      await page.close();
    }
  }
  assert.deepEqual(misses, []);
  console.log("PASS Blackout/Restore header matrix and rotation");
} finally {
  await browser.close();
}
