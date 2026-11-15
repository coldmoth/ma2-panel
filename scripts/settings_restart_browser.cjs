// Runs against a real start.bat process tree. Never launches or accesses MA2.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('./browser_smoke/node_modules/playwright');
(async()=>{
  const [base,newPort,busyPort,simplePort,output]=process.argv.slice(2);
  const browser=await chromium.launch({headless:true});
  const processes=[];const errors=[];
  try {
    const page=await browser.newPage();
    page.on('pageerror',e=>errors.push(e.message));
    await page.goto(base+'/settings.html');
    await page.locator('#settings-form').waitFor({state:'visible'});
    processes.push(await (await page.request.get(base+'/api/update/health')).json());
    // Two-second polling continues during this test; no ten-second silence exists.
    await page.waitForTimeout(2500);
    await page.evaluate(async port=>{
      window.restartSockets=await Promise.all([location.port,port].map(p=>new Promise((resolve,reject)=>{
        const ws=new WebSocket(`ws://127.0.0.1:${p}/ws`);ws.onopen=()=>resolve(ws);ws.onerror=reject;
      })));
    },simplePort);
    async function save(rate,port){
      await page.locator('#rate_hz').fill(String(rate));
      if(port)await page.locator('#port').fill(String(port));
      await page.locator('#save').click();
      await page.waitForFunction(()=>document.getElementById('save-status').textContent.startsWith('Сохранено'));
    }
    async function restart(){
      const started=Date.now();
      // An actual read may hold the physical lock briefly; retry the visible busy refusal.
      while(Date.now()-started<10000){
        await page.locator('#restart').click();
        await page.waitForTimeout(300);
        const text=await page.locator('#save-status').textContent().catch(()=> '');
        if(text.startsWith('Перезапуск отложен:'))continue;
        return;
      }
      throw Error('No safe restart window within 10 seconds');
    }
    await save(6);
    await restart();
    await page.waitForFunction(()=>document.getElementById('save-status').textContent.includes('настройки загружены заново'),null,{timeout:20000});
    assert.equal(await page.locator('#rate_hz').inputValue(),'6');
    processes.push(await (await page.request.get(base+'/api/update/health')).json());
    assert.notEqual(processes[0].instance,processes[1].instance);
    assert.equal(await page.evaluate(()=>window.restartSockets.every(ws=>ws.readyState===WebSocket.CLOSED)),true);
    assert.equal((await (await page.request.get(`http://127.0.0.1:${simplePort}/api/update/health`)).json()).instance,processes[1].instance);
    await page.screenshot({path:path.join(output,'same-port.png'),fullPage:true});
    await save(7,newPort);
    await restart();
    await page.waitForURL(`http://127.0.0.1:${newPort}/settings.html`,{timeout:20000});
    await page.locator('#settings-form').waitFor({state:'visible'});
    assert.equal(await page.locator('#rate_hz').inputValue(),'7');
    const next=`http://127.0.0.1:${newPort}`;
    processes.push(await (await page.request.get(next+'/api/update/health')).json());
    assert.notEqual(processes[1].instance,processes[2].instance);
    await page.screenshot({path:path.join(output,'new-port.png'),fullPage:true});
    // Old process response must never be reported as a successful restart.
    await save(8);
    await page.route('**/api/restart',route=>route.fulfill({json:{ok:true,instance:processes[2].instance}}));
    await page.clock.install();
    await page.locator('#restart').click();
    await page.waitForTimeout(200);
    await page.clock.fastForward(47000);
    await page.waitForFunction(()=>document.getElementById('save-status').textContent.includes('Истекло время ожидания'));
    assert.equal(await page.locator('#restart').isEnabled(),true);
    await page.unroute('**/api/restart');
    await page.clock.resume();
    // Real startup failure: BAT exits on occupied port; UI must show diagnostics.
    await save(9,busyPort);
    await restart();
    await page.waitForTimeout(5000);
    await page.clock.fastForward(47000);
    await page.waitForFunction(()=>document.getElementById('save-status').textContent.includes('Истекло время ожидания'));
    assert.match(await page.locator('#save-status').textContent(),/start.bat.*bridge.log/);
    assert.equal(await page.locator('#restart').isEnabled(),true);
    await page.screenshot({path:path.join(output,'startup-error.png'),fullPage:true});
    assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(output,'browser.json'),JSON.stringify({processes,scenarios:['same port','new port + settings loaded','old instance timeout','real occupied-port startup failure'],errors},null,2));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
