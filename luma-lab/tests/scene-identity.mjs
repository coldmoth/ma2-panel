import assert from "node:assert/strict";
import { chromium } from "playwright";

const url = new URL(process.env.LUMA_URL || "http://127.0.0.1:5178");
assert.equal(url.hostname, "127.0.0.1");
const browser = await chromium.launch();
try {
  const a = await browser.newPage();
  const b = await browser.newPage();
  const actions = [];
  a.on("websocket", (ws) => ws.on("framesent", ({ payload }) => {
    const action = JSON.parse(payload);
    if (action.a === "scene_go" || action.a === "scene_off") actions.push(action);
  }));
  await a.addInitScript(() => {
    if (!localStorage.getItem("luma.sceneShortcuts")) {
      localStorage.setItem("luma.sceneShortcuts", JSON.stringify({ "LUMA · Mock Hall": ["s6"] }));
    }
  });
  const state = (page) => page.evaluate(async () => {
    const { bridge } = await import("/src/client.mjs");
    return bridge.state.config;
  });
  const ready = (page) => page.waitForFunction(() => {
    const bridge = window.sceneIdentityTestBridge;
    return bridge.state.status.mock && bridge.state.config?.scenes.length && bridge.ready("scene_go") && !bridge.pending.size;
  });
  const act = (page, action) => page.evaluate(async (action) => {
    const { bridge } = await import("/src/client.mjs");
    return bridge.action(action);
  }, action);
  const slot = a.getByRole("dialog").locator(".shortcut-slots select").first();
  const shortcuts = () => a.locator(".sidebar").getByRole("button", { name: "Keyboard shortcuts", exact: true }).click();
  const close = () => a.keyboard.press("Escape");

  await Promise.all([a.goto(url.href), b.goto(url.href)]);
  await Promise.all([a, b].map((page) => page.evaluate(async () => {
    window.sceneIdentityTestBridge = (await import("/src/client.mjs")).bridge;
  })));
  await Promise.all([ready(a), ready(b)]);
  await shortcuts();
  assert.match(await slot.locator("option:checked").textContent(), /previous target unverified/);
  await close();
  await a.keyboard.press("1");
  await a.getByRole("alert").filter({ hasText: "The shortcut’s scene is unverified" }).waitFor();
  assert.deepEqual(actions, []);

  await shortcuts();
  await slot.selectOption("s6");
  await close();
  const original = (await state(a)).scenes.find((scene) => scene.id === "s6");
  await act(b, { a: "group_save", label: "P0.4 local group", ids: [12] });
  await a.waitForFunction(() => window.sceneIdentityTestBridge.state.config.groups.some((g) => g.label === "P0.4 local group"));
  await shortcuts();
  assert.equal(await slot.inputValue(), original.id);
  await close();

  // Recording is hosted by the classic editor. Set it up over tab B's
  // protocol session while exercising the shortcuts in A's actual UI.
  const classicAction = (action) => b.evaluate(async (action) => {
    const { bridge } = await import("/src/client.mjs");
    const request_id = `p04-${crypto.randomUUID()}`;
    await new Promise((resolve, reject) => {
      function reply(event) {
        const frame = JSON.parse(event.data);
        if (frame.request_id !== request_id || !("ok" in frame)) return;
        bridge.socket.removeEventListener("message", reply);
        if (frame.ok) resolve();
        else reject(new Error(frame.err));
      }
      bridge.socket.addEventListener("message", reply);
      bridge.socket.send(JSON.stringify({
        ...action, request_id,
        config_revision: bridge.state.config.revision, blackout_epoch: bridge.state.status.blackout_epoch,
      }));
    });
  }, action);
  await classicAction({ a: "scene_delete", id: original.id });
  await act(b, { a: "select_fixtures", ids: [12] });
  await classicAction({ a: "scene_create", page: 1, exec: "1.107", confirm: "1.107", label: "Replacement" });
  await a.waitForFunction(() => window.sceneIdentityTestBridge.state.config.scenes.some((s) => s.exec === "1.107"));
  const config = await state(a);
  const replacement = config.scenes.find((scene) => scene.exec === "1.107");
  assert.notEqual(replacement.id, original.id);
  assert.notEqual(replacement.identity, original.identity);
  await shortcuts();
  assert.match(await slot.locator("option:checked").textContent(), /previous target unverified/);
  await close();
  await a.keyboard.press("1");
  await a.getByRole("alert").filter({ hasText: "The shortcut’s scene is unverified" }).waitFor();
  assert.deepEqual(actions, []);

  await shortcuts();
  await slot.selectOption(replacement.id);
  await close();
  await a.keyboard.press("1");
  await ready(a);
  assert.equal(actions.length, 1);
  assert.deepEqual(
    { a: actions[0].a, id: actions[0].id, scene_identity: actions[0].scene_identity, config_revision: actions[0].config_revision },
    { a: "scene_go", id: replacement.id, scene_identity: replacement.identity, config_revision: config.revision },
  );
  await a.waitForFunction((id) => window.sceneIdentityTestBridge.state.running[id] === true, replacement.id);
  console.log("Legacy and deleted shortcuts sent zero frames. Explicit reassignment sent one:", actions[0]);

  // Replace the Cue while the previous version is still tracked as a panel playback.
  await classicAction({ a: "scene_create", page: 1, exec: "1.107", confirm: "1.107",
    label: "Overwritten Cue", replace: true });
  await a.waitForFunction((previous) => window.sceneIdentityTestBridge.state.config.scenes
    .some((s) => s.id === previous.id && s.identity !== previous.identity), replacement);
  const nextScene = (await state(a)).scenes.find((scene) => scene.exec === "1.102");
  const nav = (name) => a.locator(".main-nav").getByRole("button", { name, exact: true }).click();
  await nav("Scenes");
  await a.getByRole("button", { name: `Play ${nextScene.label}`, exact: true }).click();
  const warning = "Automatic Off was skipped. The previous scene may still be active on Executor 1.107.";
  await a.getByRole("alert").getByText(warning, { exact: true }).waitFor();
  assert.deepEqual(actions.slice(1).map(({ a, id }) => ({ a, id })), [{ a: "scene_go", id: nextScene.id }]);
  await nav("Settings");
  await a.locator("#luma-language").selectOption("ru");
  await a.getByRole("alert").getByText(
    "Автоматический Off пропущен. Предыдущая сцена может оставаться активной на Executor 1.107.",
    { exact: true },
  ).waitFor();
  console.log("Skipped Off warning names Executor 1.107 in EN and RU.");
} finally {
  await browser.close();
}
