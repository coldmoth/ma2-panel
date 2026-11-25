import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";
import { chromium } from "playwright";

const artifacts = process.env.LUMA_SEARCH_ARTIFACTS;
if (artifacts) await mkdir(artifacts, { recursive: true });
const url = process.env.LUMA_URL || "http://127.0.0.1:5178";
const strings = {
  en: { tab: "Fixtures", label: "Find a fixture", clear: "Clear fixture search", empty: "No fixtures found", groupActions: "Group actions" },
  ru: { tab: "Приборы", label: "Найти прибор", clear: "Очистить поиск приборов", empty: "Приборы не найдены", groupActions: "Действия группы" },
};
const screens = [
  { width: 1440, height: 900 },
  { width: 1024, height: 768 },
  { width: 1180, height: 820, touch: true },
  { width: 820, height: 1180, touch: true },
];
const browser = await chromium.launch();
const results = [];

try {
  for (const [language, t] of Object.entries(strings)) {
    for (const { width, height, touch } of screens) {
      const page = await browser.newPage({ viewport: { width, height }, hasTouch: !!touch });
      page.setDefaultTimeout(5000);
      const actions = [], errors = [];
      page.on("pageerror", error => errors.push(error.message));
      page.on("websocket", socket => socket.on("framesent", ({ payload }) => actions.push(String(payload))));
      try {
        await page.addInitScript(lang => localStorage.setItem("luma.language.v1", lang), language);
        await page.goto(url);
        await page.locator('[data-fixture="1"]').waitFor();
        await page.getByRole("button", { name: t.tab, exact: true }).click();
        const input = page.getByRole("searchbox", { name: t.label, exact: true });
        const cards = page.locator("[data-catalog-fixture]");
        const ids = () => cards.evaluateAll(elements => elements.map(el => Number(el.dataset.catalogFixture)));
        const catalog = await ids();
        assert.equal(catalog.length, 20);
        assert.equal(await input.getAttribute("enterkeyhint"), "search");
        assert.equal(await page.locator("html").getAttribute("lang"), language);
        if (touch) {
          const control = page.locator(".catalog-search-control");
          assert((await control.boundingBox()).height >= 44);
          await input.tap();
          assert.equal(await input.evaluate(el => el === document.activeElement), true);
        }
        await input.fill("  lEd bAr  ");
        assert.deepEqual(await ids(), [1, 2, 3, 4, 5, 6, 7, 8]);
        await input.fill("LED Bar");
        if (artifacts && ((language === "en" && width === 1440) || (language === "ru" && width === 820))) {
          await page.screenshot({ path: join(artifacts, `after-${language}.png`) });
        }
        await input.fill("20");
        assert.deepEqual(await ids(), [20]);
        await input.fill("");
        assert.deepEqual(await ids(), catalog);
        const group = page.locator(".fixture-navigation").getByRole("button").filter({ hasText: "LED-бары" });
        await group.click();
        await input.press("1");
        await input.press("Shift+B");
        await input.press("Shift+B");
        for (const arrow of ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"]) await input.press(arrow);
        assert.equal(await input.inputValue(), "1BB");
        await page.getByText(t.empty, { exact: true }).waitFor();
        await page.getByLabel(t.groupActions).click();
        await page.locator(".group-actions[open]").waitFor();
        await page.keyboard.press("Escape");
        await page.locator(".group-actions[open]").waitFor({ state: "hidden" });
        assert.equal(await input.inputValue(), "1BB");
        assert.deepEqual(await ids(), []);
        const clear = page.getByRole("button", { name: t.clear, exact: true });
        if (touch) {
          await clear.tap();
        } else {
          await input.focus();
          await page.keyboard.press("Tab");
          assert.equal(await clear.evaluate(el => el === document.activeElement && el.matches(":focus-visible")), true);
          await page.keyboard.press("Enter");
        }
        assert.equal(await input.inputValue(), "");
        assert.equal(await input.evaluate(el => el === document.activeElement), true);
        assert.equal(await group.getAttribute("aria-pressed"), "true");
        assert.deepEqual(await ids(), [1, 2, 3, 4, 5, 6, 7, 8]);
        assert.equal(await page.locator('[data-catalog-fixture][aria-pressed="true"]').count(), 0);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
        assert.deepEqual(errors, []);
        assert.deepEqual(actions, []);
        results.push({ language, width, height, touch: !!touch, actions });
        console.log("PASS", language, `${width}×${height}`, touch ? "touch" : "keyboard", "zero actions");
      } finally {
        await page.close();
      }
    }
  }
} finally {
  if (artifacts) await writeFile(join(artifacts, "search-actions.json"), JSON.stringify(results, null, 2));
  await browser.close();
}
