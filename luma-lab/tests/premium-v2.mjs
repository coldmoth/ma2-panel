import { chromium } from "playwright";
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
process.chdir(fileURLToPath(new URL("../", import.meta.url)));
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
const nav = (name) => page.getByRole("button", { name, exact: true }).click();
try {
 await mkdir("screenshots/premium-v2",{recursive:true});
 await page.addInitScript(() => localStorage.setItem("luma.language.v1", "ru"));
 await page.goto(process.env.LUMA_URL || "http://127.0.0.1:5189");await wait(b=>b.ready());
 await page.locator('[data-fixture="9"]').click();await wait(b=>b.state.selected.join(',')==='9');
 const initial = await state(b=>({hall:b.state.config.hall,fixtures:b.state.config.fixtures}));
 await state(async b=>{await b.action({a:"aim",pan:-110,tilt:0});await b.action({a:"dim",v:64});await b.action({a:"master",v:73});});
 await wait(b=>b.state.masterEvidence.value===73);
 await page.waitForTimeout(500);
 const panBefore=await state(b=>b.state.history[9].pan.value);
 assert(Math.abs(panBefore-(-110-(initial.fixtures.length? -270: -270))/540*100)<1);
 const joy=page.locator('.joystick'),box=await joy.boundingBox();
 await page.mouse.move(box.x+box.width*.85,box.y+box.height/2);await page.mouse.down();await page.waitForTimeout(340);await page.mouse.up();
 await page.waitForTimeout(300);
 const jogs=sent.filter(a=>a.a==='jog');assert(jogs.length>0 && jogs.length<=4);assert(jogs.every(a=>a.pan>0&&a.pan<=.15));
 const count=sent.filter(a=>a.a==='jog').length;await page.waitForTimeout(300);assert.equal(sent.filter(a=>a.a==='jog').length,count);
 assert.equal(sent.filter(a=>a.a==='aim').length,1);
 assert(Math.abs(await state(b=>b.state.history[9].pan.value)-panBefore)<2);
 results.push('Pan -110: mouse sends relative jog, <=10 Hz, stops on release');
 await page.locator(".stage-heading").click();await page.keyboard.down('ArrowRight');await page.waitForTimeout(240);await page.keyboard.up('ArrowRight');await page.waitForTimeout(250);
 assert(sent.filter(a=>a.a==='jog').length>count);results.push('keyboard relative jog');
 // Touch pointer follows the same hold/release path as the mouse.
 const beforeTouch=sent.filter(a=>a.a==='jog').length;
 const touch=await context.newCDPSession(page);
 await touch.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:box.x+box.width*.9,y:box.y+box.height/2}]});
 await page.waitForTimeout(240);await touch.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await page.waitForTimeout(180);
 assert(sent.filter(a=>a.a==='jog').length>beforeTouch);results.push('touch pointer relative jog');
 const controls=()=>sent.filter(a=>['aim','dim','jog','master','select_fixtures','clear'].includes(a.a)).length;
 const before=controls();await nav('Расстановка');
 await page.locator('[data-fixture="15"]').click();
 await page.locator('[data-fixture="16"]').click({modifiers:['Shift']});
 assert.equal(await page.locator('[data-fixture="15"]').getAttribute('aria-pressed'),'true');
 assert.equal(await page.locator('[data-fixture="16"]').getAttribute('aria-pressed'),'true');
 assert.equal(controls(),before);assert.deepEqual(await state(b=>b.state.selected),[9]);
 results.push('layout independent click/Shift selection without light commands');
 await page.locator('[data-fixture="9"]').click();
 const f=page.locator('[data-fixture="9"]'),fb=await f.boundingBox();
 await page.mouse.move(fb.x+fb.width/2,fb.y+fb.height/2);await page.mouse.down();await page.mouse.move(fb.x+fb.width/2+35,fb.y+fb.height/2+25,{steps:8});await page.mouse.up();
 await wait(b=>Math.abs(b.state.config.fixtures.find(f=>f.id===9).x-.12)>.01);
 const roomWidth = await state(b=>b.state.config.hall.w);
 await page.locator('.layout-fields input').nth(0).fill('2.5');await nav('Сохранить');
 await page.waitForFunction(async roomWidth => {
  const {bridge} = await import('/src/client.mjs');
  return Math.abs(bridge.state.config.fixtures.find(f=>f.id===9).x - 2.5 / roomWidth) < .00001;
 }, roomWidth);
 await page.getByLabel('Поворот, °',{exact:true}).fill('37.5');await nav('Сохранить');await wait(b=>b.state.config.fixtures.find(f=>f.id===9).rot===37.5);
 await page.locator('.layout-fields select').first().selectOption('profile');await wait(b=>b.state.config.fixtures.find(f=>f.id===9).icon==='profile');
 await page.getByLabel('Ширина помещения, м',{exact:true}).fill('20');await page.getByLabel('Длина помещения, м',{exact:true}).fill('26');
 await page.getByLabel('Ширина сцены, м',{exact:true}).fill('10');await page.getByLabel('Глубина сцены, м',{exact:true}).fill('4');
 await page.getByLabel('Положение вдоль стены, %',{exact:true}).fill('25');await page.getByLabel('Сцена у стены',{exact:true}).selectOption('left');
 await nav('Сохранить геометрию');await wait(b=>b.state.config.hall.w===20&&b.state.config.hall.stageOffset===.25);
 assert.equal(controls(),before);results.push('drag, arbitrary rotation, icon and geometry persisted through backend');
 // Dense selection is local and leaves coordinates and working selection intact.
 await state(b=>b.action({a:'layout_save',pos:[{id:15,x:.4,y:.65},{id:16,x:.41,y:.65},{id:17,x:.42,y:.65}]}));
 await page.locator('[data-fixture="17"]').click();
 await page.getByLabel('Выбрать отдельно ID 15',{exact:true}).click();
 assert.equal(await page.locator('[data-fixture="15"]').getAttribute('aria-pressed'),'true');
 assert.deepEqual(await state(b=>b.state.selected),[9]);
 await page.getByLabel('Закрыть участок',{exact:true}).click();
 await page.evaluate(async fixtures=>{const {bridge:b}=await import(performance.getEntriesByType('resource').find(e=>/\/src\/client\.mjs/.test(e.name)).name);await b.action({a:'layout_save',pos:fixtures.filter(f=>[15,16,17].includes(f.id)).map(({id,x,y})=>({id,x,y}))});},initial.fixtures);
 results.push('dense local magnifier selects each PAR independently');
 await page.reload();await wait(b=>b.ready());await nav('Расстановка');assert.equal(await page.getByLabel('Ширина помещения, м',{exact:true}).inputValue(),'20');
 await page.locator('[data-fixture="9"]').click();assert.equal(await page.getByLabel('Поворот, °',{exact:true}).inputValue(),'37.5');
 // Restore only fields changed by this verification, using isolated mock config.
 await state(async b=>{await b.action({a:'layout_save',pos:[{id:9,x:.12,y:.22}]});await b.action({a:'fixture_flag',id:9,rot:0});await b.action({a:'fixture_flag',id:9,icon:'head'});});
 await page.evaluate(async hall=>{const {bridge:b}=await import(performance.getEntriesByType('resource').find(e=>/\/src\/client\.mjs/.test(e.name)).name);await b.action({a:'hall_save',hall});},initial.hall);
 await nav('Зал');assert.equal(await page.locator('.zoom-controls').count(),0);
 await page.locator('[data-fixture="9"]').click();await wait(b=>b.state.selected.includes(9));
 await state(b=>b.action({a:'master',v:73}));
 const masterActions=sent.filter(a=>a.a==='master').length;
 await nav('Приборы');await nav('Сцены');await nav('Зал');
 assert.equal(await state(b=>b.state.masterEvidence.value),73);assert.equal(sent.filter(a=>a.a==='master').length,masterActions);
 await page.locator(".stage-heading").click();await page.keyboard.press('3');await page.waitForTimeout(1900);
 assert.equal(await state(b=>b.state.masterEvidence.value),73);assert.equal(sent.filter(a=>a.a==='master').length,masterActions);
 results.push('Grandmaster stable across tabs and scene without implicit master commands');
 await state(b=>b.expireEvidence(Date.now()+10000));
 assert.equal(await state(b=>b.state.masterEvidence.value),73);assert.equal(await state(b=>b.state.masterEvidence.quality),'last');
 results.push('last known does not disappear on expiry');
 for(const [width,height] of [[1440,900],[1024,768]]) {
   await page.setViewportSize({width,height});await nav('Зал');
   await page.screenshot({path:`screenshots/premium-v2/hall-${width}.png`,fullPage:true});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   const barIds=await page.locator('[data-kind="bar"]').evaluateAll(es=>es.map(e=>e.dataset.fixture));
   const beamIds=await page.locator('[data-beam]').evaluateAll(es=>es.map(e=>e.dataset.beam));assert(!barIds.some(id=>beamIds.includes(id)));
   const par=await page.locator('[data-kind="par"] svg').first().getAttribute('width');const head=await page.locator('[data-kind="head"] svg').first().getAttribute('width');assert(Number(par)<Number(head));
   await nav('Расстановка');await page.locator('[data-fixture="9"]').click();await page.screenshot({path:`screenshots/premium-v2/layout-${width}.png`,fullPage:true});
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 }
 await nav('Зал');await nav('Вид сверху');await page.screenshot({path:'screenshots/premium-v2/hall-top-1024.png',fullPage:true});await nav('Перспектива');
 results.push('1440x900 and 1024x768 hall/layout screenshots; compact PAR; no bar cones');
 await page.locator('[data-fixture="9"]').click();await wait(b=>b.state.selected.includes(9));
 const bb=await page.locator('.joystick').boundingBox();await page.mouse.move(bb.x+bb.width*.9,bb.y+bb.height/2);await page.mouse.down();await page.waitForTimeout(150);
 await state(b=>{b.socket.close();return true;});await page.mouse.up();await wait(b=>b.ready());
 const afterReconnect=sent.filter(a=>a.a==='jog').length;await page.waitForTimeout(400);assert.equal(sent.filter(a=>a.a==='jog').length,afterReconnect);
 assert.deepEqual(await state(b=>b.state.selected),[]);results.push('disconnect stops held joystick without replay on reconnect');
 assert.deepEqual(errors,[]);console.log(JSON.stringify({results},null,2));
} catch(e) {await page.screenshot({path:'screenshots/premium-v2/failure.png',fullPage:true});throw e;}
finally {await writeFile('screenshots/premium-v2/verification.json',JSON.stringify({results,errors,actions:sent.map(a=>a.a)},null,2));await browser.close();}
