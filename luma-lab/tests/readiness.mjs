import assert from "node:assert/strict";
import { chromium } from "playwright";

const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.addInitScript(() => localStorage.setItem("luma.language.v1", "ru"));
  const sent = [];
  let wire, latest, unconfirmed = false;
  const loginDenial = { code: "login_unconfirmed", message: "нет связи с пультом" };

  function deliverStatus(message = {}) {
    const status = structuredClone(latest.status);
    if (unconfirmed) {
      status.ma2 = "login_unknown";
      status.show = { name: null, source: "unknown" };
      status.readiness.connection = "login_unconfirmed";
      status.readiness.show = { state: "pending", name: null };
      for (const category of ["light", "general"])
        for (const action of Object.keys(status.readiness.actions[category]))
          status.readiness.actions[category][action] = loginDenial;
    }
    wire.send(JSON.stringify({ ...message, status }));
  }

  await page.routeWebSocket("**/ws", (ws) => {
    wire = ws;
    const server = ws.connectToServer();
    server.onMessage((data) => {
      const message = JSON.parse(data);
      if (!message.status) return ws.send(data);
      latest = message;
      deliverStatus(message);
    });
    ws.onMessage((data) => {
      sent.push(JSON.parse(data));
      server.send(data);
    });
  });
  await page.goto(process.env.LUMA_URL || "http://127.0.0.1:5206");
  await page.getByText("Mock MA2 · выбор доступен", { exact: true }).waitFor();
  const fixture = page.locator('[data-fixture="9"]');
  await fixture.click();
  const dimmer = page.getByRole("slider", { name: "Яркость", exact: true });
  await dimmer.waitFor();
  assert(await dimmer.isEnabled());

  await page.locator(".sidebar").getByRole("button", { name: "Горячие клавиши", exact: true }).click();
  await page.getByRole("dialog").locator(".shortcut-slots select").nth(0).selectOption("s1");
  await page.keyboard.press("Escape");
  const before = sent.length;

  unconfirmed = true;
  deliverStatus();
  await page.getByText("TCP подключён · вход MA2 не подтверждён", { exact: true }).waitFor();
  assert.match(await page.locator(".show-name").textContent(), /Шоу пульта ожидается · Локальный план:/);
  assert(await page.getByRole("slider", { name: "Grandmaster", exact: true }).isDisabled());
  assert(await dimmer.isDisabled());
  const otherFixture = page.locator('[data-fixture="10"]');
  assert(await otherFixture.isEnabled());
  await otherFixture.click();
  assert.equal(await otherFixture.getAttribute("aria-pressed"), "true");
  assert.equal(await fixture.getAttribute("aria-pressed"), "false");
  assert(await dimmer.isDisabled());
  await page.locator(".inspector-toggle").click();
  assert.equal(await dimmer.count(), 0);
  await page.locator(".inspector-toggle").click();
  assert(await dimmer.isDisabled());
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("1");
  await page.getByRole("alert").filter({ hasText: "Вход в MA2 не подтверждён" }).waitFor();
  assert.equal(sent.length, before);

  unconfirmed = false;
  deliverStatus();
  await page.getByText("Mock MA2 · выбор доступен", { exact: true }).waitFor();
  assert.equal(await otherFixture.getAttribute("aria-pressed"), "true");
  assert.equal(sent.length, before);
  await page.keyboard.press("1");
  assert.equal(sent.at(-1).a, "scene_go");
  console.log("C1 mock UI: selection and Inspector stay local; all outgoing actions blocked without login; reconnect does not replay");
} finally {
  await browser.close();
}
