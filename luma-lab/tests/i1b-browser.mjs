// Run against the isolated mock started by npm run dev.
import assert from "node:assert/strict";
import { chromium } from "playwright";

const url = new URL(process.env.LUMA_URL || "http://127.0.0.1:5178");
assert.equal(url.hostname, "127.0.0.1");

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  page.setDefaultTimeout(7000);
  const actions = [], errors = [], overflow = [];
  const dialog = page.getByRole("dialog");
  page.on("pageerror", error => errors.push(error.message));
  page.on("websocket", ws => {
    if (!new URL(ws.url()).pathname.endsWith("/ws")) return;
    ws.on("framesent", ({ payload }) => {
      const { request_id, ...action } = JSON.parse(payload);
      if (action.a) actions.push(action);
    });
  });
  const button = (name, parent = page) => parent.getByRole("button", { name, exact: true });
  const nav = name => button(name, page.locator(".main-nav")).click();
  const text = (name, parent = page) => parent.getByText(name, { exact: true }).first().waitFor();
  const settled = () => page.waitForFunction(async () => {
    const { bridge } = await import("/src/client.mjs");
    return bridge.state.status?.mock === true && !!bridge.state.config && !bridge.state.selecting && !bridge.pending.size;
  });
  const language = locale => page.waitForFunction(lang => document.documentElement.lang === lang, locale);
  async function checkOverflow(area) {
    const clipped = await page.evaluate(() => {
      const selectors = [
        ".stage-tools button", ".stage-heading", ".layout-toolbar", ".layout-form-actions",
        ".catalog-toolbar", ".catalog-caption", ".group-form-footer", ".settings-nav button",
        ".settings-row > label", ".settings-row > b", ".modal-head h2", ".shortcut-list > div",
        ".inspector .field-top", ".scene-detail", ".scene-fade",
      ];
      return [...document.querySelectorAll(selectors.join(","))]
        .filter(el => el.clientWidth > 0 && el.scrollWidth > el.clientWidth + 2)
        .map(el => `${el.className || el.tagName}: ${el.innerText.trim()}`);
    });
    overflow.push(...clipped.map(item => `${area}: ${item}`));
  }
  const labels = {
    en: {
      hall: "Hall", fixtures: "Fixtures", scenes: "Scenes", layout: "Layout", settings: "Settings",
      top: "Top view", dim: "Dimmer", clear: "Clear selection", quick: "Quick scenes",
      catalog: "Find a fixture", create: "New local group", groupName: "Group name",
      groupActions: "Group actions", remove: "Delete group", confirmDelete: "Delete local group?",
      library: "Scene library", stop: "Stop", undo: "Undo", properties: "Fixture properties",
      geometry: "Geometry Room and stage", width: "Room width, m", language: "Language",
      interface: "Interface", system: "Connection and system", legacy: "Classic ma2-panel tool · Russian only",
      diagnostics: "Diagnostics", prep: "Venue preparation", editor: "Record new scene",
      record: "Record scene", keys: "Keyboard shortcuts", keyHint: "Add a fixture to the selection",
      timeout: "The operation timed out. Check Diagnostics.", dismiss: "Dismiss message",
      design: "Small shapes.",
    },
    ru: {
      hall: "Зал", fixtures: "Приборы", scenes: "Сцены", layout: "Расстановка", settings: "Настройки",
      top: "Вид сверху", dim: "Яркость", clear: "Снять выделение", quick: "Быстрые сцены",
      catalog: "Найти прибор", create: "Новая локальная группа", groupName: "Название группы",
      groupActions: "Действия группы", remove: "Удалить группу", confirmDelete: "Удалить локальную группу?",
      library: "Библиотека сцен", stop: "Остановить", undo: "Отменить", properties: "Свойства прибора",
      geometry: "Геометрия Помещение и сцена", width: "Ширина помещения, м", language: "Язык",
      interface: "Интерфейс", system: "Подключение и система", legacy: "Штатный инструмент ma2-panel · только на русском",
      diagnostics: "Диагностика", prep: "Подготовка площадки", editor: "Запись новой сцены",
      record: "Записать сцену", keys: "Горячие клавиши", keyHint: "Добавить прибор к выбору",
      timeout: "Время ожидания операции истекло. Проверьте диагностику.", dismiss: "Скрыть сообщение",
      design: "Маленькая форма.",
    },
  };
  const comparableActions = {};
  async function inspect(locale) {
    const l = labels[locale];
    await settled();
    await language(locale);
    await nav(l.hall);
    await button(l.top).click();
    const start = actions.length;
    const fixture = page.locator('[data-fixture="9"]');
    await fixture.click();
    await page.getByRole("region", { name: l.dim, exact: true })
      .getByRole("slider", { name: l.dim, exact: true }).waitFor();
    await settled();
    assert.match(await fixture.getAttribute("aria-label"), /ID 9$/);
    await checkOverflow(`${locale} Hall and Inspector`);
    await button(l.clear).click();
    await settled();
    await page.locator(".quick-scenes-toggle").click();
    await text(l.quick, page.locator(".quick-scenes-toggle"));
    await page.locator(".quick-scenes .scene-launch").first().waitFor();
    await page.locator(".quick-scenes-toggle").click();

    await nav(l.fixtures);
    const search = page.getByRole("searchbox", { name: l.catalog, exact: true });
    await search.fill("Moving Head 09");
    await page.locator('[data-catalog-fixture="9"]').waitFor();
    assert.equal(await page.locator(".fixture-card").count(), 1);
    await search.clear();
    await checkOverflow(`${locale} Fixtures`);
    await button(l.create).click();
    await dialog.getByRole("heading", { name: l.create, exact: true }).waitFor();
    await dialog.getByLabel(l.groupName, { exact: true }).waitFor();
    await checkOverflow(`${locale} group editor`);
    await page.keyboard.press("Escape");
    await dialog.waitFor({ state: "hidden" });
    await page.locator(".fixture-navigation button").filter({ hasText: "LED-бары" }).click();
    await page.getByLabel(l.groupActions, { exact: true }).click();
    await button(l.remove).click();
    await dialog.getByRole("heading", { name: l.confirmDelete, exact: true }).waitFor();
    assert.match(await dialog.locator(".group-editor p").first().textContent(), /LED-бары/);
    await page.keyboard.press("Escape");

    await nav(l.scenes);
    assert.match(await page.locator(".section-heading h2").textContent(), new RegExp(l.library));
    await page.locator(".scene-launch").first().click();
    await settled();
    await page.locator(".live-scenes-bar .live-stop-btn").first().click();
    await settled();
    comparableActions[locale] = actions.slice(start).filter(action =>
      ["select_fixtures", "scene_go", "scene_off"].includes(action.a));
    await button(l.record).click();
    await dialog.getByRole("heading", { name: l.editor, exact: true }).waitFor();
    await page.keyboard.press("Escape");

    await nav(l.layout);
    await text(l.properties);
    await button(l.undo, page.locator(".layout-workspace")).waitFor();
    await page.locator(".layout-geometry summary").click();
    await page.getByLabel(l.width, { exact: true }).waitFor();
    await checkOverflow(`${locale} Layout`);
    await nav(l.settings);
    await page.getByLabel(l.language, { exact: true }).waitFor();
    await checkOverflow(`${locale} Settings`);
    for (const section of [l.system, l.diagnostics, l.prep]) {
      await button(section, page.locator(".settings-nav")).click();
      await page.getByRole("heading", { name: section, exact: true }).waitFor();
    }
    await nav(l.hall);
    await page.keyboard.press("?");
    await dialog.getByRole("heading", { name: l.keys, exact: true }).waitFor();
    await text(l.keyHint, dialog);
    await checkOverflow(`${locale} shortcuts`);
    await page.keyboard.press("Escape");
    await nav(l.settings);
    await button(l.interface, page.locator(".settings-nav")).click();
  }

  await page.goto(url.href);
  // The demo discovers one fixture type per cycle. Compare both locales
  // after discovery so a legitimate background config update cannot split
  // the two paths across different revisions.
  let profilesReady = false;
  for (let attempt = 0; attempt < 80 && !profilesReady; attempt++) {
    profilesReady = await page.evaluate(async () => {
      const { bridge } = await import("/src/client.mjs");
      const config = bridge.state.config;
      if (!bridge.state.status?.mock || !bridge.ready() || !config?.fixtures.length) return false;
      const diagnostics = await (await fetch("/api/diag")).json();
      const reads = diagnostics.export.type_reads;
      return config.fixtures.every(({ type }) => reads[type.split(" ")[0]]?.spec && config.dmx_map?.[type]?.has);
    });
    if (!profilesReady) await page.waitForTimeout(250);
  }
  assert(profilesReady, "Mock fixture profile discovery did not finish");
  await inspect("en");
  await page.evaluate(async () => {
    const { bridge } = await import("/src/client.mjs");
    const { BridgeError } = await import("/src/errors.mjs");
    bridge.report(new BridgeError({ code: "timeout", err: "Техническая причина" }));
  });
  await text(labels.en.timeout, page.locator(".error-banner"));
  await page.getByLabel("Language", { exact: true }).selectOption("ru");
  await language("ru");
  await text(labels.ru.timeout, page.locator(".error-banner"));
  await button(labels.ru.dismiss, page.locator(".error-banner")).click();
  await page.setViewportSize({ width: 1024, height: 768 });
  await inspect("ru");

  // The dialog keeps focus and makes the Settings form inert to pointer input.
  // Dispatch the same change event to check the already mounted dialog updates.
  await button(labels.ru.keys, page.locator(".sidebar")).click();
  await text(labels.ru.keyHint, dialog);
  await page.locator("#luma-language").evaluate(select => {
    select.value = "en";
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await language("en");
  await text(labels.en.keyHint, dialog);
  await checkOverflow("en shortcuts at 1024×768");
  await page.keyboard.press("Escape");
  for (const [id, name] of Object.entries(labels.en).filter(([id]) =>
    ["hall", "fixtures", "scenes", "layout", "settings"].includes(id))) {
    await nav(name);
    await page.locator(`.page-${id}`).waitFor();
    await checkOverflow(`en ${name} at 1024×768`);
  }
  await page.getByLabel("Language", { exact: true }).selectOption("ru");
  await language("ru");
  await page.reload();
  await language("ru");
  await settled();
  await page.setViewportSize({ width: 1440, height: 900 });
  await checkOverflow("ru Hall at 1440×900");
  await page.goto(new URL("/design-lab", url).href);
  await page.locator(".dl-intro h1").filter({ hasText: labels.ru.design }).waitFor();
  assert.equal(await page.getByRole("button", { name: /Вращающаяся голова/ }).count() > 0, true);

  for (const action of ["select_fixtures", "scene_go", "scene_off"]) {
    assert(comparableActions.en.some(payload => payload.a === action), `Missing ${action}`);
  }
  assert.deepEqual(comparableActions.ru, comparableActions.en);
  assert.deepEqual(errors, []);
  assert.deepEqual(overflow, []);
  console.log("I1-B Chromium: EN/RU workspaces, dialogs, errors, live switch, reload, 1440×900 and 1024×768, identical action payloads");
} finally {
  await browser.close();
}
