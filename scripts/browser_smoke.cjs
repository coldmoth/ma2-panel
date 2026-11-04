/* Actual Chromium and WebKit rendering/WS smoke; see browser_smoke.py for isolation. */
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
let playwright;
try { playwright = require('playwright'); }
catch { playwright = require('./browser_smoke/node_modules/playwright'); }
const [fullURL, simpleURL, output] = process.argv.slice(2);
assert(fullURL && simpleURL && output, 'Run through scripts/browser_smoke.py');
fs.mkdirSync(output, {recursive: true});
const results = [];

async function until(predicate, label) {
  const deadline = Date.now() + 12000;
  while (!predicate()) {
    if (Date.now() > deadline) throw new Error('Timed out: ' + label);
    await new Promise(resolve => setTimeout(resolve, 50));
  }
}
async function noOverflow(page, label) {
  const size = await page.evaluate(() => ({width: innerWidth, actual: document.documentElement.scrollWidth}));
  assert(size.actual <= size.width + 1, `${label}: document overflow ${JSON.stringify(size)}`);
}
async function screenshot(page, name) {
  await page.screenshot({path: path.join(output, name + '.png'), fullPage: true});
}
async function cutConnection(page, context, ready, offlineCheck, frames) {
  await context.setOffline(true);
  // Network emulation does not reliably close an already-open WS in every engine.
  // Explicitly close the actual native socket while the reconnect path is offline.
  await page.evaluate(() => window.__smokeSockets.forEach(ws => ws.close()));
  await offlineCheck();
  await screenshot(page, page.__smokeName + '-offline');
  const before = frames.length;
  await context.setOffline(false);
  await ready();
  await page.waitForTimeout(2300); // one reconnect interval plus a joystick timer window
  assert.equal(frames.length, before, 'Reconnect must not replay any action');
}
async function checkEngine(name) {
  const browser = await playwright[name].launch({headless: true});
  const context = await browser.newContext({viewport: {width: 1024, height: 768}, hasTouch: true});
  const errors = [];
  try {
    await context.addInitScript(() => {
      const NativeSocket = window.WebSocket;
      window.__smokeSockets = [];
      window.WebSocket = class extends NativeSocket {
        constructor(...args) { super(...args); window.__smokeSockets.push(this); }
      };
    });
    await require('./plan_beams_smoke.cjs')(context, fullURL, output, name);
    for (const mode of ['full', 'simple']) {
      const page = await context.newPage();
      page.__smokeName = name + '-' + mode;
      page.setDefaultTimeout(12000);
      page.on('pageerror', error => errors.push(`${mode}: ${error.message}`));
      const frames = [];
      page.on('websocket', socket => socket.on('framesent', event => {
        try { const action = JSON.parse(event.payload); if (action.a) frames.push(action); } catch {}
      }));
      const ready = mode === 'full'
        ? () => page.waitForFunction(() => connected() && state.mock === true)
        : () => page.waitForFunction(() => /Имитация.*подключено/.test(document.querySelector('#connection').textContent));
      await page.goto(mode === 'full' ? fullURL : simpleURL);
      await ready();
      // Isolate synthetic replies in the browser: no action reaches even the mock bridge.
      await page.evaluate(mode => {
        const socket = window.__smokeSockets.at(-1), originalSend = socket.send;
        let action;
        socket.send = raw => { action = JSON.parse(raw); };
        const reply = msg => socket.onmessage({data: JSON.stringify({...msg, a:action.a, request_id:action.request_id})});
        try {
          if (mode === 'full') send({a:'master',value:20});
          else document.querySelector('.simple-scene .go').click();
          reply({ok:false,outcome:'unknown',err:'Тестовая ошибка: ' + 'длинный_контекст_'.repeat(35)});
          if (mode === 'full') send({a:'master',value:30});
          else document.querySelector('.simple-scene .go').click();
          reply({ok:false,outcome:'partial',err:'Вторая ошибка'});
          if (mode === 'full') send({a:'master',value:40});
          else document.querySelector('.simple-scene .go').click();
          reply({ok:true});
        } finally { socket.send = originalSend; }
      }, mode);
      await page.waitForTimeout(6100);
      assert.equal(await page.locator('#errors .error-entry').count(), 2);
      assert.match(await page.locator('#errors').textContent(), /Результат неизвестен/);
      for (const width of [1024,390]) {
        await page.setViewportSize({width,height:844});
        await noOverflow(page, name + '/' + mode + '/durable-errors');
        const box = await page.locator('#errors').boundingBox();
        assert(box.height <= 844 * .25 + 1, 'Errors have a bounded scroll region');
        assert(await page.locator('#blackout').isVisible(), 'Blackout remains present');
        const close = await page.locator('#errors button').first().boundingBox();
        assert(close.y >= box.y && close.y + close.height <= box.y + box.height + 1, 'First dismissal fits error region');
        await screenshot(page, name + '-' + mode + '-errors-' + width);
      }
      await page.locator('#errors button').first().focus();
      await page.keyboard.press('Enter');
      assert.equal(await page.locator('#errors .error-entry').count(), 1);
      await page.locator('#errors button').click();
      assert(await page.locator('#errors').isHidden());
      await page.setViewportSize({width:1024,height:768});
      if (mode === 'full') await page.evaluate(() => go('scenes'));
      await page.evaluate(() => {
        const socket=window.__smokeSockets.at(-1);
        window.__busyReply=socket.onmessage;
        socket.onmessage=event=>{const msg=JSON.parse(event.data);if(!msg.status)window.__busyReply(event);};
        window.__publishFileBusy=(active,kind,state='running')=>window.__busyReply({data:JSON.stringify({
          status:{ma2:'logged_in',mock:true,safety:{mode:'full'},show_file_active:active,show_file:{kind,state}}
        })});
      });
      try {
        const before=frames.length;
        for(const kind of ['save','load','upload']) {
          await page.evaluate(kind=>window.__publishFileBusy(true,kind),kind);
          assert(await page.locator('#blackout').isDisabled());
          assert.match(await page.locator(mode==='full'?'#banners':'#connection').textContent(),/файл.*шоу.*недоступно/);
          const go=mode==='full'?page.locator('.tile[data-scene="smoke-scene"]'):page.locator('.simple-scene .go');
          assert(await go.isDisabled(),mode+' scene Go disabled during '+kind);
          for(const off of await page.getByRole('button',{name:/^Выключить/}).all())assert(await off.isDisabled());
          await page.evaluate(kind=>window.__publishFileBusy(true,kind,'unknown'),kind);
          assert(await page.locator('#blackout').isDisabled(),'unknown text never clears active lock');
          if(kind==='save')await screenshot(page,name+'-'+mode+'-file-busy');
          await page.evaluate(kind=>window.__publishFileBusy(false,kind,'failed'),kind);
          assert(await page.locator('#blackout').isEnabled());
          assert(await go.isEnabled());
        }
        assert.equal(frames.length,before,'Status transitions never replay an action');
      } finally {
        await page.evaluate(()=>{window.__smokeSockets.at(-1).onmessage=window.__busyReply;});
      }
      if (mode === 'full') {
        {
        await page.evaluate(() => {
          window.__fixtureTaps = 0;
          const original = tapFixture;
          tapFixture = function(...args) { window.__fixtureTaps++; return original(...args); };
          go('light'); lightUI.tab='plan'; render();
        });
        const fixtureButton = page.locator('.hall .fx').first();
        await fixtureButton.focus();
        await page.keyboard.press('Shift+Tab'); await page.keyboard.press('Tab');
        assert(await fixtureButton.evaluate(el => el === document.activeElement), 'Tab reaches fixture');
        let taps = await page.evaluate(() => window.__fixtureTaps);
        await page.keyboard.press('Enter');
        assert.equal(await page.evaluate(() => window.__fixtureTaps), ++taps, 'Enter activates fixture once');
        assert.deepEqual(await page.evaluate(() => state.selection), [1]);
        await fixtureButton.focus(); await page.keyboard.press('Space');
        assert.equal(await page.evaluate(() => window.__fixtureTaps), ++taps, 'Space activates fixture once');
        assert.deepEqual(await page.evaluate(() => state.selection), []);
        await fixtureButton.click();
        assert.equal(await page.evaluate(() => window.__fixtureTaps), ++taps, 'Pointer activates fixture once');
        await page.evaluate(() => go('hall'));
        for (const tab of ['place','groups']) {
          await page.evaluate(tab => { planState.tab=tab; render(); }, tab);
          for (const key of ['Enter','Space']) {
            await fixtureButton.focus(); await page.keyboard.press(key);
            assert.equal(await page.evaluate(() => window.__fixtureTaps), ++taps, tab + '/' + key + ' once');
          }
        }
        await page.evaluate(() => { planState.tab='place'; render(); });
        let box = await fixtureButton.boundingBox();
        let start = frames.length;
        await page.mouse.move(box.x+box.width/2,box.y+box.height/2);
        await page.mouse.down(); await page.mouse.move(box.x+box.width/2+45,box.y+box.height/2+35,{steps:4});
        await page.mouse.up();
        await until(() => frames.slice(start).some(a=>a.a==='layout_save'), 'Drag saves position');
        assert.equal(frames.slice(start).filter(a=>a.a==='layout_save').length,1);
        assert.equal(await page.evaluate(() => window.__fixtureTaps),taps,'Drag has no selection click');
        await page.waitForFunction(() => !busy('layout_save'));
        await fixtureButton.waitFor({state:'visible'});
        box = await fixtureButton.boundingBox(); start = frames.length;
        await page.mouse.move(box.x+box.width/2,box.y+box.height/2); await page.mouse.down();
        await page.mouse.move(box.x+box.width/2+35,box.y+box.height/2+35);
        await fixtureButton.dispatchEvent('pointercancel',{pointerId:1}); await page.mouse.up();
        assert.equal(frames.slice(start).filter(a=>a.a==='layout_save').length,0,'Cancelled drag never saves');
        await page.evaluate(() => { lightUI.tab='groups'; });
        }
        for (const section of ['scenes', 'light', 'history', 'start', 'hall', 'patch', 'shows']) {
          await page.locator(`#rail [data-sec="${section}"]`).tap();
          await page.waitForFunction(section => state.sec === section, section);
          await noOverflow(page, name + '/' + section);
        }
        await page.locator('#rail [data-sec="scenes"]').tap();
        await page.getByRole('button', {name: 'Изменить', exact: true}).tap();
        await page.locator('#dlg[open]').waitFor();
        const box = await page.locator('#dlg').boundingBox();
        assert(box.x >= 0 && box.y >= 0 && box.x + box.width <= 1025 && box.y + box.height <= 769,
               'Scene dialog must fit tablet viewport');
        await screenshot(page, name + '-full-dialog');
        await page.getByRole('button', {name: 'Отмена', exact: true}).tap();
        const beforeScene = frames.length;
        await page.locator('button.tile[data-scene="smoke-scene"]').tap();
        await until(() => frames.slice(beforeScene).some(a => a.a === 'scene_go'), 'full scene action');
        await page.locator('#rail [data-sec="light"]').tap();
        await page.getByText('Тестовая группа', {exact: true}).tap();
        await page.getByRole('button', {name: 'Движение', exact: true}).tap();
        const pad = page.getByLabel('Пад Pan и Tilt');
        await pad.waitFor();
        const padBox = await pad.boundingBox();
        assert(padBox && padBox.y >= 0 && padBox.y + padBox.height <= 768, 'Joystick fits viewport');
        const stepBox = await page.getByRole('button', {name: 'Tilt −1°', exact: true}).boundingBox();
        assert(stepBox && stepBox.y + stepBox.height <= 768, 'Step controls fit viewport');
        await noOverflow(page, name + '/movement');
        await screenshot(page, name + '-full-movement');
        const beforeJog = frames.length;
        await page.mouse.move(padBox.x + padBox.width / 2, padBox.y + padBox.height / 2);
        await page.mouse.down();
        await page.mouse.move(padBox.x + padBox.width * .85, padBox.y + padBox.height * .2, {steps: 5});
        await until(() => frames.slice(beforeJog).some(a => a.a === 'jog' && a.pan && a.tilt), 'Pan/Tilt drag sends both axes');
        await page.mouse.up();
        await page.waitForTimeout(300);
        const afterRelease = frames.length;
        await page.waitForTimeout(400);
        assert.equal(frames.length, afterRelease, 'Released joystick must stop');
        // Cut a second active drag and reconnect before release: stale gesture must not resume.
        await page.mouse.move(padBox.x + padBox.width / 2, padBox.y + padBox.height / 2);
        await page.mouse.down();
        await page.mouse.move(padBox.x + padBox.width * .85, padBox.y + padBox.height * .2);
        const beforeCut = frames.filter(a => a.a === 'jog').length;
        await until(() => frames.filter(a => a.a === 'jog').length > beforeCut, 'active drag before disconnect');
        await cutConnection(page, context, ready, async () => {
          await page.waitForFunction(() => !bridgeUp());
          await page.waitForFunction(() => !moveState.drag);
          assert(await page.locator('#blackout').isDisabled(), 'Disconnected controls disabled');
        }, frames);
        await page.mouse.up();
        // Selection intentionally resets on reconnect; begin a fresh explicit interaction.
        await page.getByText('Тестовая группа', {exact: true}).tap();
        await page.getByRole('button', {name: 'Движение', exact: true}).tap();
        await page.getByRole('button', {name: 'Положение', exact: true}).tap();
        for (const attr of ['pan', 'tilt']) {
          const label = (attr === 'pan' ? 'Pan' : 'Tilt') + ' — абсолютное положение';
          const range = page.getByRole('slider', {name: label, exact: true});
          assert(await range.isEnabled(), `${label} must be enabled`);
          const bounds = await range.boundingBox();
          assert(bounds && bounds.x >= 0 && bounds.y >= 0 && bounds.x + bounds.width <= 1024 &&
                 bounds.y + bounds.height <= 768, `${label} fits viewport`);
          const start = frames.length;
          await page.mouse.move(bounds.x + bounds.width * .5, bounds.y + bounds.height / 2);
          await page.mouse.down();
          await page.mouse.move(bounds.x + bounds.width * .72, bounds.y + bounds.height / 2, {steps: 5});
          await page.mouse.up();
          await until(() => frames.slice(start).some(a => a.a === 'aim' && Number.isFinite(a[attr])), label + ' sends aim');
          await page.waitForTimeout(250);
          const aimed = frames.slice(start).filter(a => a.a === 'aim');
          assert(aimed.every(a => !Object.hasOwn(a, attr === 'pan' ? 'tilt' : 'pan')), 'One range must send only its own axis');
        }
        await noOverflow(page, name + '/absolute');
        await screenshot(page, name + '-full-absolute');
      } else {
        const go = page.locator('button.go');
        await go.tap();
        await until(() => frames.some(a => a.a === 'scene_go'), 'simple scene action');
        await page.waitForFunction(() => !document.querySelector('#blackout').disabled);
        const beforeDialog = frames.length;
        const dialogPromise = page.waitForEvent('dialog').then(async dialog => {
          assert.equal(dialog.type(), 'confirm');
          await dialog.dismiss();
        });
        await page.locator('#blackout').tap();
        await dialogPromise;
        assert.equal(frames.length, beforeDialog, 'Cancelled blackout must send nothing');
        await noOverflow(page, name + '/simple');
        await screenshot(page, name + '-simple');
        await cutConnection(page, context, ready, async () => {
          await page.waitForFunction(() => /Нет связи с мостом/.test(document.querySelector('#connection').textContent));
          assert(await go.isDisabled(), 'Simple controls disabled while disconnected');
        }, frames);
      }
      assert.deepEqual(errors, [], 'No uncaught page JavaScript errors');
      results.push({engine: name, mode, viewport: '1024x768', result: 'PASS', actions: frames.length});
      console.log(`PASS ${name}/${mode} 1024x768: navigation, dialogs, WS, overflow${mode === 'full' ? ', Pan/Tilt joystick, absolute axes and disconnect' : ', disconnect'}`);
      await page.close();
    }
    const wizard = await context.newPage();
    wizard.__smokeName = name + '-setup';
    wizard.on('pageerror', error => errors.push(error.message));
    await wizard.goto(fullURL + '/setup.html');
    await wizard.locator('#setup-form').waitFor({state: 'visible'});
    await wizard.waitForFunction(() => !document.getElementById('setup-save').disabled);
    await noOverflow(wizard, name + ' setup desktop');
    await screenshot(wizard, name + '-setup-desktop');
    await wizard.setViewportSize({width: 390, height: 844});
    await noOverflow(wizard, name + ' setup phone');
    await screenshot(wizard, name + '-setup-phone');
    await wizard.locator('#setup-lan').check();
    await wizard.locator('#setup-save').click();
    await wizard.locator('#setup-restart').waitFor({state: 'visible'});
    assert.match(await wizard.locator('#setup-saved').textContent(), /сохранены.*перезапустите/i);
    assert.match(await wizard.locator('#setup-network').textContent(), /только на этом компьютере/i);
    await context.setOffline(true);
    await wizard.waitForFunction(() => document.getElementById('setup-save').disabled, null, {timeout: 12000});
    assert.match(await wizard.locator('#setup-live').textContent(), /недоступен/);
    await screenshot(wizard, name + '-setup-offline');
    await context.setOffline(false);
    await wizard.waitForFunction(() => !document.getElementById('setup-save').disabled, null, {timeout: 12000});
    await wizard.close();
    results.push({engine: name, mode: 'setup', result: 'PASS'});
    console.log(`PASS ${name}/setup: desktop, phone, saved vs active, offline/reconnect`);
  } catch (error) {
    for (const page of context.pages()) await screenshot(page, page.__smokeName + '-failure').catch(() => {});
    throw error;
  } finally {
    await browser.close();
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({results, errors}, null, 2));
  }
}
(async () => { for (const engine of ['chromium', 'webkit']) await checkEngine(engine); })()
  .catch(error => { console.error(error); process.exitCode = 1; });
