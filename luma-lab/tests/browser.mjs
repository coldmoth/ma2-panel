import { chromium } from "playwright";
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { join } from "node:path";
import { DEFAULT_HALL } from "../src/model.mjs";
process.chdir(fileURLToPath(new URL("../", import.meta.url)));
const artifacts = process.env.LUMA_BROWSER_ARTIFACTS || "screenshots";
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
  }),
  page = await context.newPage();
const errors = [],
  sent = [],
  results = [];
page.on("pageerror", (e) => errors.push(e.message));
page.on("websocket", (ws) =>
  ws.on("framesent", (e) => {
    try {
      sent.push(JSON.parse(e.payload));
    } catch {}
  }),
);
const state = (fn) =>
  page.evaluate(async (code) => {
    const moduleURL = performance
      .getEntriesByType("resource")
      .find((e) => /\/src\/client\.mjs/.test(e.name))?.name;
    if (!moduleURL) return false;
    const { bridge } = await import(moduleURL);
    return Function("bridge", `return (${code})(bridge)`)(bridge);
  }, String(fn));
const wait = async (fn) => {
  const end = Date.now() + 20000;
  while (Date.now() < end) {
    if ((await state(fn)) === true) return;
    await page.waitForTimeout(75);
  }
  throw new Error("Condition timed out: " + String(fn));
};
const button = (name, parent = page) => parent.getByRole("button", { name, exact: true });
const click = (name) => button(name).click();
const main = page.getByRole("navigation", { name: /^(Main navigation|Основные разделы)$/ });
const nav = (name) => button(name, main).click();
try {
  await mkdir(artifacts, { recursive: true });
  await page.goto(process.env.LUMA_URL || "http://127.0.0.1:5178");
  await wait(
    (b) =>
      b.state.status?.mock === true &&
      b.ready() &&
      b.state.config?.fixtures?.length === 20 &&
      Object.keys(b.state.simulation).length === 20,
  );
  assert.equal(await page.locator("html").getAttribute("lang"), "en");
  await page.locator(".sidebar").getByRole("button", { name: "Keyboard shortcuts", exact: true }).click();
  await page.getByRole("dialog").locator(".shortcut-slots select").nth(1).selectOption("s2");
  await page.getByRole("dialog").locator(".shortcut-slots select").nth(2).selectOption("s3");
  await page.keyboard.press("Escape");
  assert.equal(sent.length, 0);
  results.push("startup: zero actions");
  if (await state((b) => b.state.status.blackout.phase === "active")) {
    await page.locator(".blackout").click();
    await wait((b) => b.state.status?.blackout?.phase === "idle");
  }
  await page.locator('[data-fixture="9"]').click();
  await wait((b) => b.state.selected.join(",") === "9");
  assert(await page.getByLabel("Pan", { exact: true }).isEnabled());
  await page.keyboard.down("Shift");
  await page.locator('[data-fixture="10"]').click();
  await page.keyboard.up("Shift");
  await wait((b) => b.state.selected.join(",") === "9,10");
  results.push("acknowledged selection and Shift");
  await click("Top view");
  assert.equal(await page.locator("[data-fixture]").count(), 20);
  await click("Perspective");
  results.push("shared stage coordinates");
  const dimmer = page.getByRole("region", { name: "Dimmer", exact: true });
  await button("50%", dimmer).click();
  await wait(
    (b) => b.state.shown[9]?.dim === 50 && b.state.shown[10]?.dim === 50,
  );
  results.push("mock dimmer");
  await click("Color #568aff");
  await wait((b) => b.state.shown[9]?.rgb?.[2] === 100);
  results.push("mock RGB");
  await page.locator('[data-fixture="9"]').click();
  await wait((b) => b.state.selected.join(",") === "9");
  const jogs = () => sent.filter((a) => a.a === "jog");
  const before = jogs().length;
  await page.keyboard.down("ArrowRight");
  await page.waitForTimeout(480);
  await page.keyboard.up("ArrowRight");
  await page.waitForTimeout(350);
  assert(jogs().length > before);
  const after = jogs().length;
  await page.waitForTimeout(300);
  assert.equal(jogs().length, after);
  assert(
    jogs()
      .slice(before)
      .every((a) => Math.abs(a.pan) <= 0.15),
  );
  results.push("held fine arrow: rate bound and keyup");
  await page
    .locator("summary")
    .filter({ hasText: "Precision and axis inversion" })
    .click();
  const oldFlip = await state(
    (b) => !!b.state.config.fixtures.find((f) => f.id === 9).flip_pan,
  );
  await click("Pan ↔");
  await wait(
    Function(
      "b",
      `return !!b.state.config?.fixtures.find(f=>f.id===9)?.flip_pan !== ${oldFlip}`,
    ),
  );
  results.push("backend per-fixture inversion");
  const stick = await page.locator('.joystick').boundingBox();
  const beforeStick = sent.filter(a=>a.a==='jog').length;
  await page.mouse.move(stick.x+stick.width/2,stick.y+stick.height/2);
  await page.mouse.down();await page.mouse.move(stick.x+stick.width*.8,stick.y+stick.height*.3);
  await page.waitForTimeout(350);await page.mouse.up();await page.waitForTimeout(300);
  assert(sent.filter(a=>a.a==='jog').length>beforeStick);
  const afterStick=sent.filter(a=>a.a==='jog').length;
  await page.waitForTimeout(250);assert.equal(sent.filter(a=>a.a==='jog').length,afterStick);
  await page.getByLabel('Pan',{exact:true}).fill('42');
  await page.getByLabel('Pan',{exact:true}).dispatchEvent('pointerup');
  await wait(b=>Math.abs((b.state.shown[9]?.pan??-100)-57.7777777778)<.01);
  await page.getByLabel('Zoom',{exact:true}).fill('36');
  await page.getByLabel('Zoom',{exact:true}).dispatchEvent('pointerup');
  await wait(b=>b.state.shown[9]?.zoom===36);
  results.push('mouse joystick stops on release, absolute Pan and Zoom use backend');
  await state(async b=>{try{await b.action({a:'zoom',v:101});}catch{ return true; }return false;});
  await page.getByRole('alert').waitFor();
  assert(await state(b=>!!b.state.error));
  await click("Dismiss message");
  results.push('real backend rejection displayed to operator');

  const blackouts = () => sent.filter((a) => a.a === "blackout").length;
  const initial = blackouts();
  await page.locator(".stage-heading").click();
  await page.keyboard.press("b");
  assert.equal(blackouts(), initial);
  await page.waitForTimeout(680);
  await page.keyboard.press("b");
  assert.equal(blackouts(), initial);
  await page.keyboard.press("b");
  await wait((b) => b.state.status?.blackout?.phase === "active");
  assert.equal(blackouts(), initial + 1);
  await wait((b) => ![...b.pending.values()].some((p) => p.a === "blackout"));
  await page.keyboard.press("b");
  await wait((b) => b.state.status?.blackout?.phase === "idle");
  assert.equal(blackouts(), initial + 2);
  results.push("Blackout arm, expiry, activation, safe restore");
  await page.locator(".stage-heading").click();
  await page.keyboard.press("2");
  await wait(
    (b) =>
      b.state.running.s2 === true &&
      b.state.running_meta.s2?.freshness === "fresh",
  );
  results.push("mock scene hotkey + confirmed active status");
  await nav("Fixtures");
  const search = page.getByRole("searchbox", { name: "Find a fixture", exact: true });
  await search.fill("Moving");
  assert.equal(await page.locator(".fixture-card").count(), 6);
  const beforeTyping = sent.length;
  await search.fill("bbb123");
  await page.keyboard.press("b");
  assert.equal(sent.length, beforeTyping);
  await search.fill("");
  results.push("catalog filtering, input suppresses shortcuts");
  await page.locator('[data-catalog-fixture="9"]').click();
  await wait((b) => b.state.selected.join(",") === "9");
  await click("Add to group");
  const groupDialog = page.getByRole("dialog");
  await button("Create group", groupDialog).click();
  await groupDialog.getByRole("textbox", { name: "Group name", exact: true }).fill("LUMA проверка");
  await button("Save group", groupDialog).click();
  await wait((b) => b.state.config.groups.some((g) =>
    g.label === "LUMA проверка" && g.fixtures.join(",") === "9",
  ));
  results.push("backend local group");
  await nav("Layout");
  await page.locator('[data-fixture="9"]').click();
  const layout = page.getByRole("complementary", { name: "Layout properties", exact: true });
  const x = layout.getByRole("spinbutton", { name: "X, m", exact: true });
  const width = (await state((b) => b.state.config.hall?.w)) ?? DEFAULT_HALL.w;
  const xMetres = Number((width * 0.127).toFixed(2));
  await x.fill(String(xMetres));
  await button("Save", layout).click();
  await wait(Function("b", `return b.state.config.fixtures.find(({ id }) => id === 9).x === ${xMetres / width}`));
  results.push("backend layout_save");
  await nav("Settings");
  const focus = page.getByRole("switch", { name: "Focus", exact: true });
  const old = await focus.isChecked();
  await focus.click();
  await page.getByRole("combobox", { name: "Language", exact: true }).selectOption("ru");
  await page.reload();
  await wait((b) => b.ready());
  assert.equal(await page.locator("html").getAttribute("lang"), "ru");
  await nav("Настройки");
  assert.equal(await page.getByRole("combobox", { name: "Язык", exact: true }).inputValue(), "ru");
  assert.equal(
    await page.getByRole("switch", { name: "Фокус", exact: true }).isChecked(),
    !old,
  );
  results.push("interface preference persistence");
  await nav("Зал");
  await page.locator(".stage-heading").click();
  await page.keyboard.press("3");
  await wait(
    (b) =>
      b.state.running.s3 === true &&
      b.state.running_meta.s3?.freshness === "fresh",
  );
  await page.waitForTimeout(1700);
  await nav("Настройки");
  await state(async b=>{
    for(const g of [...b.state.config.groups].filter(g=>g.label==='LUMA проверка'||g.label.startsWith('LUMA проверка ')))await b.action({a:'group_delete',id:g.id});
    await b.action({a:'layout_save',pos:[{id:9,x:.12,y:.22}]});
  });
  for (const [width, height] of [
    [1440, 900],
    [1366, 768],
    [1024, 768],
  ]) {
    await page.setViewportSize({ width, height });
    await page.screenshot({
      path: join(artifacts, `settings-${width}x${height}.png`),
    });
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    );
    await nav("Зал");
    await page.locator('[data-fixture="9"]').click();
    await wait((b) => b.state.selected.join(",") === "9");
    await page.getByRole("slider", { name: "Яркость", exact: true }).waitFor();
    await page.screenshot({ path: join(artifacts, `hall-${width}x${height}.png`) });
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth + 1,
      ),
    );
    assert(
      await page
        .locator(".quick-scenes-toggle")
        .evaluate((e) => e.getBoundingClientRect().bottom <= innerHeight + 1),
    );
    await nav("Настройки");
  }
  results.push("1440/1366/1024: no horizontal overflow, scene shelf toggle visible");
  await click("Подключение и система");
  await page.getByRole("heading", { name: "Подключение и система", exact: true }).waitFor();
  await page.getByRole("button", { name: /Сохранить/, exact: false }).first().waitFor();
  results.push("native connection and system settings");
  await page.setViewportSize({ width: 1440, height: 900 });
  await nav("Зал");
  await click("Свернуть навигацию");
  await page.reload();
  await wait((b) => b.ready());
  assert(await page.locator(".shell.collapsed").count());
  await click("Развернуть навигацию");
  results.push("sidebar persistence");
  await page.locator('[data-fixture="9"]').click();
  await wait((b) => b.state.selected.join(",") === "9");
  const beforeReconnect = sent.length;
  await state((b) => {
    b.socket.close();
    return true;
  });
  await wait((b) => !b.state.connected);
  assert.deepEqual(await state((b) => b.state.selected), [9]);
  await wait((b) => b.ready());
  assert.deepEqual(await state((b) => b.state.selected), [9]);
  assert.equal(sent.length, beforeReconnect);
  results.push("reconnect preserves local selection and never replays");
  assert.deepEqual(errors, []);
  assert.equal(results.length, 19);
  console.log(
    `PASS ${results.length} browser checks\n` +
      results.map((x) => `• ${x}`).join("\n"),
  );
} catch (e) {
  await page.screenshot({ path: join(artifacts, "failure.png") });
  console.log(
    "DEBUG",
    JSON.stringify(
      await state((b) => ({
        config: b.state.config?.show,
        status: b.state.status,
        error: b.state.error,
      })),
    ),
    page.url(),
  );
  throw e;
} finally {
  await writeFile(
    join(artifacts, "browser-results.json"),
    JSON.stringify(
      { results, errors, actions: sent.map(({ a }) => a) },
      null,
      2,
    ),
  );
  await browser.close();
}
