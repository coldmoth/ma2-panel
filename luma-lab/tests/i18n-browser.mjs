import assert from "node:assert/strict";
import { chromium } from "playwright";

const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  page.setDefaultTimeout(8000);
  const failures = [];
  page.on("pageerror", (error) => failures.push(error.message));
  const deskShow = '<img src=x onerror="window.i18nInjected=true">';
  const planShow = "План A";
  const fixtureName = "Прибор Ω";
  const groupName = "Группа Ω";
  const sent = [];
  await page.routeWebSocket("**/ws", (ws) => {
    const send = (message) => ws.send(JSON.stringify(message));
    const code = "show_mismatch";
    const params = { deskShow, planShow };
    send({
      config: {
        show: planShow, revision: "bridge:1",
        fixtures: [{ id: 1, label: fixtureName, type: "par", x: 0.5, y: 0.5 }],
        groups: [{ id: "g1", label: groupName, fixtures: [1] }],
      },
      status: {
        mock: true, ma2: "logged_in", blackout: { phase: "idle" }, blackout_epoch: 7,
        show: { name: deskShow, source: "ma2" },
        readiness: {
          connection: "authenticated", show: { name: deskShow, state: "mismatch" },
          actions: { light: { select_fixtures: { code, params } }, recovery: { show_identify: null }, plan: { show_open_plan: null } },
        },
        plan_selection: { state: "operator", code: "plan_missing", name: deskShow, params: { deskShow } },
      },
    });
    ws.onMessage((data) => {
      const request = JSON.parse(data);
      sent.push(request);
      send(sent.length === 1
        ? { request_id: request.request_id, ok: false, code, params, err: "Старый текст ошибки" }
        : { request_id: request.request_id, ok: false, err: 'Техническая причина. Login "panel" "private-password"' });
    });
  });

  await page.goto(process.env.LUMA_URL || "http://127.0.0.1:5206");
  await page.getByText("MA2 login confirmed", { exact: true }).waitFor();
  assert.equal(await page.locator("html").getAttribute("lang"), "en");
  assert.equal(await page.locator(".show-name").textContent(), `Console show: ${deskShow} · Local plan: ${planShow}`);
  await page.getByRole("button", { name: "Fixtures", exact: true }).click();
  assert.equal(await page.locator("[data-catalog-fixture='1'] b").textContent(), fixtureName);
  await page.getByText(groupName, { exact: true }).first().waitFor();

  await page.getByRole("button", { name: "Create plan", exact: true }).click();
  await page.getByRole("button", { name: "Cancel", exact: true }).click();
  assert.equal(sent.length, 0);
  await page.getByRole("button", { name: "Create plan", exact: true }).click();
  await page.getByRole("button", { name: "Confirm", exact: true }).click();
  const alert = page.locator(".error-banner");
  await alert.getByText(`Console show: ${deskShow}. Local plan: ${planShow}. Open the plan for the console show.`, { exact: true }).waitFor();
  assert.equal(await alert.locator("img").count(), 0);
  assert.equal(await page.evaluate(() => window.i18nInjected), undefined);

  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByLabel("Language", { exact: true }).selectOption("ru");
  assert.equal(await page.locator("html").getAttribute("lang"), "ru");
  await alert.getByText(`Пульт: ${deskShow}. Локальный план: ${planShow}. Откройте план шоу пульта.`, { exact: true }).waitFor();
  await page.getByRole("button", { name: "Приборы", exact: true }).click();
  assert.equal(await page.locator("[data-catalog-fixture='1'] b").textContent(), fixtureName);
  await page.getByText(groupName, { exact: true }).first().waitFor();
  assert.equal(await page.locator(".show-name").textContent(), `Пульт: ${deskShow} · Локальный план: ${planShow}`);

  await alert.getByRole("button", { name: "Скрыть сообщение" }).click();
  await page.getByRole("button", { name: "Создать план", exact: true }).click();
  await page.getByRole("button", { name: "Подтвердить", exact: true }).click();
  await alert.getByText("Не удалось выполнить действие.", { exact: true }).waitFor();
  assert.equal(sent.length, 2);
  assert.deepEqual(sent.map(({ request_id, ...payload }) => payload), Array(2).fill({
    a: "show_open_plan", name: deskShow, create_only: true, config_revision: "bridge:1", blackout_epoch: 7,
  }));
  await alert.getByRole("button", { name: "Диагностика", exact: true }).click();
  const diagnostics = page.locator(".settings-content");
  await diagnostics.getByRole("heading", { name: "Диагностика", exact: true }).waitFor();
  await diagnostics.getByText("Технические сведения", { exact: true }).click();
  const details = await diagnostics.locator("pre").first().textContent();
  assert.match(details, /Техническая причина/);
  assert.doesNotMatch(details, /private-password/);

  await page.reload();
  await page.getByText("Вход MA2 подтверждён", { exact: true }).waitFor();
  assert.equal(await page.locator("html").getAttribute("lang"), "ru");
  assert.deepEqual(failures, []);
  console.log("I1-A Chromium: EN by default, RU persists, error and confirmation switch live, names stay intact, params render as text, identical requests, legacy diagnostics redacted");
} finally {
  await browser.close();
}
