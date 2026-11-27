const {chromium} = require('./browser_smoke/node_modules/playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
(async () => {
  const [base, output, old, stable, rc, peerTrace] = process.argv.slice(2);
  const deskCommands = () => JSON.parse(fs.readFileSync(peerTrace, "utf8"));
  const browser = await chromium.launch({headless:true});
  const page = await browser.newPage({viewport:{width:1024,height:900}});
  async function waitIdle() {
    const until=Date.now()+30000;
    while(true) {
      const d=await(await page.request.get(base+'/api/update/idle')).json();
      if(d.idle) return;
      if(Date.now()>until) throw Error('Bridge did not become idle');
      await new Promise(r=>setTimeout(r,250));
    }
  }
  try {
    await page.goto(base+'/settings.html');
    await page.getByText('Установлено: '+old, {exact:true}).waitFor();
    await page.locator('#update-check').click();
    await page.locator('#update-start:not([disabled])').waitFor();
    assert.ok((await page.locator('#update-version').textContent()).includes('v'+stable.split('+')[0]));
    await waitIdle();
    await page.locator('#update-start').click();
    async function waitVersion(version) {
      const deadline=Date.now()+55000, history=[];
      while (true) {
        try {
          const d=await(await page.request.get(base+'/api/update/status', {timeout:1500})).json();
          history.push(d);
          if(d.current===version && d.phase==='completed') break;
          if(d.phase==='failed'||d.phase==='rolled_back') throw Error(JSON.stringify(d));
        } catch(error) {if(String(error).includes('phase')) throw error;}
        if(Date.now()>deadline) {fs.writeFileSync(output+'/status-history.json',JSON.stringify(history,null,2));throw Error('Version timeout '+version);}
        await new Promise(r=>setTimeout(r,250));
      }
      await page.goto(base+'/settings.html');
      await page.getByText('Установлено: '+version, {exact:true}).waitFor();
    }
    await waitVersion(stable);
    if (peerTrace) {
      await page.goto(base + '/');
      await page.goto(base + '/settings.html');
    }
    await page.locator('#update-check').click();
    await page.getByText('Новых обновлений в выбранном канале нет.', {exact:true}).waitFor();
    assert.equal(await page.locator('#update-start').isEnabled(), false);
    const channel=page.locator('#test-updates');
    assert.equal(await channel.isChecked(), false);
    const writes=[]; page.on('request', r=>{if(r.method()==='POST') writes.push(r.url());});
    await channel.check();
    await page.getByText('Настройка сохранена. Нажмите «Проверить обновления».', {exact:true}).waitFor();
    assert.equal(writes.filter(u=>u.endsWith('/api/update/start')||u.endsWith('/api/update/check')).length,0);
    await page.locator('#update-check').click();
    await page.locator('#update-start:not([disabled])').waitFor();
    assert.match(await page.locator('#update-version').textContent(), /-rc\.|-beta\./);
    await page.screenshot({path:output+'/channel-before-rc.png', fullPage:true});
    await waitIdle();
    const beforeLuma = peerTrace ? deskCommands() : null;
    await page.locator('#update-start').click();
    await waitVersion(rc);
    await channel.waitFor();
    await page.waitForFunction(()=>document.querySelector('#test-updates').checked);
    await page.screenshot({path:output+'/channel-after-restart.png', fullPage:true});
    if (peerTrace) {
      const assets = [], errors = [], sent = [], statuses = [];
      page.on('pageerror', error => errors.push(error.message));
      page.on('response', response => {
        if (response.ok()) assets.push(new URL(response.url()).pathname);
      });
      page.on('websocket', ws => {
        ws.on('framesent', frame => sent.push(JSON.parse(frame.payload)));
        ws.on('framereceived', frame => {
          const message = JSON.parse(frame.payload);
          if (message.status) statuses.push(message.status);
        });
      });
      await page.setViewportSize({width: 1440, height: 900});
      await page.goto(base + '/');
      await page.locator('.sidebar-version').getByText(rc.split('+')[0], { exact: true }).waitFor();
      const connect = page.getByRole('button', { name: 'Connect to MA2', exact: true });
      await connect.waitFor();
      assert.equal(statuses.at(-1)?.mock, false);
      assert.equal(statuses.at(-1)?.hall_trial, true);
      assert.deepEqual(sent, []);
      assert.deepEqual(deskCommands(), beforeLuma, 'LUMA startup must send no Telnet commands');
      assert(assets.some(path => /^\/luma\/assets\/index-[\w-]+\.js$/.test(path)));
      assert(assets.some(path => /^\/luma\/assets\/index-[\w-]+\.css$/.test(path)));
      await connect.click();
      await page.getByText('MA2 connected', { exact: true }).waitFor();
      assert.equal(statuses.at(-1)?.login?.USER, 'luma-ci');
      await page.locator('[data-fixture="1"]').click();
      const dimmer = page.getByRole('region', {name: 'Dimmer', exact: true});
      const slider = dimmer.getByRole('slider', {name: 'Dimmer', exact: true});
      await slider.waitFor();
      assert.equal(await slider.getAttribute('aria-valuetext'), 'Unknown value');
      const sentBeforeArrow = sent.length;
      await slider.press('ArrowUp');
      assert.deepEqual(sent.slice(sentBeforeArrow), [], 'Unknown brightness must not send a command');
      const deskBeforePreset = deskCommands().length;
      await dimmer.getByRole('button', {name: '50%', exact: true}).click();
      const deadline = Date.now() + 5000;
      const intensityCommands = () => deskCommands().slice(deskBeforePreset).filter(command => /^At /.test(command));
      while (!intensityCommands().length && Date.now() < deadline) {
        await new Promise(resolve => setTimeout(resolve, 50));
      }
      assert.deepEqual(intensityCommands(), ['At 50'], 'One explicit dimmer command must reach the isolated external peer');
      assert.deepEqual(sent.filter(({a}) => a === 'dim').map(({v}) => v), [50]);
      const classic = page.getByRole('link', {name: 'Classic panel', exact: true});
      assert.equal(await classic.getAttribute('href'), '/index.html');
      assert.deepEqual(errors, []);
      await page.screenshot({path: output + '/luma-delivered.png', fullPage:true});
    }
    fs.writeFileSync(output+'/browser.json', JSON.stringify({old,stable,rc,buttons:'passed',stableExcludesRC:true,preferencePersists:true},null,2));
  } catch(error) {await page.screenshot({path:output+'/failure.png',fullPage:true});fs.writeFileSync(output+'/failure.txt',await page.locator('body').innerText());throw error;} finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
