// Real mock backend integration; explicitly injected readback below is a TEST fixture,
// never a production source of MA2 evidence.
import { chromium } from "playwright";
import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
process.chdir(fileURLToPath(new URL("../",import.meta.url)));
const dir="screenshots/workspace-v2", results=[], errors=[], sent=[];
const browser=await chromium.launch();
const context=await browser.newContext({viewport:{width:1440,height:900}});
const page=await context.newPage();
page.on("pageerror",e=>errors.push(e.message));
page.on("console",m=>{if(m.type()==="error")errors.push(m.text());});
page.on("websocket",ws=>ws.on("framesent",e=>{try{sent.push(JSON.parse(e.payload));}catch{}}));
const state=fn=>page.evaluate(async code=>{
  const url=performance.getEntriesByType('resource').find(e=>/\/src\/client\.mjs/.test(e.name))?.name;
  if(!url)return false;
  const {bridge}=await import(url);
  return Function("b",`return (${code})(b)`)(bridge);
},String(fn));
const wait=async fn=>{for(let i=0;i<160;i++){if(await state(fn))return;await page.waitForTimeout(75);}throw Error(`Timeout: ${fn}`);};
const nav=name=>page.getByRole('button',{name,exact:true}).click();
const count=a=>sent.filter(s=>s.a===a).length;
const metrics=()=>page.locator('.stage-viewport > svg').evaluate(s=>{
  const m=s.getScreenCTM(),g=s.querySelector('g[transform]').getBBox(),r=s.getBoundingClientRect(),main=document.querySelector('.page-hall').getBoundingClientRect();
  return {viewBox:s.getAttribute("viewBox"),svg:{width:r.width,height:r.height},geometry:{width:g.width*m.a,height:g.height*m.d},availableHeight:main.height};
});
const range=key=>page.getByRole('slider',{name:key,exact:true});
const angle=async key=>Number(await range(key).inputValue());
async function dragStick(x,y,ms=220) {
 const r=await page.locator('.joystick').boundingBox();
 await page.mouse.move(r.x+r.width*x,r.y+r.height*y);await page.mouse.down();await page.waitForTimeout(ms);await page.mouse.up();await page.waitForTimeout(200);
}
async function freshReadback() {
 // Deliberately tagged test observation. Uses protocol percentages, not simulation.
 await state(b=>{
   const attrs=b.state.config.attrs,to=(k,v)=>(v-attrs[k].min)/(attrs[k].max-attrs[k].min)*100;
   b.receive({live:{9:{pan:to('pan',-110),tilt:to('tilt',-65),dim:64}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:Date.now()}}});
 });
}
try {
 await mkdir(dir,{recursive:true});
 await page.addInitScript(() => localStorage.setItem("luma.language.v1", "ru"));
 await page.goto(process.env.LUMA_URL||'http://127.0.0.1:5191');await wait(b=>b.ready());
 assert.equal(sent.length,0);
 assert.equal(await page.locator('.page-hall h1').count(),0);
 const shelf=page.getByRole('button',{name:/Быстрые сцены/});
 assert.equal(await shelf.getAttribute('aria-expanded'),'false');
 const after=await metrics();
 assert(after.geometry.height/after.svg.height>.8);
 results.push({test:'hall uses the available plot at 1440x900',after});
 await page.locator('[data-fixture="9"]').click();await wait(b=>b.state.selected.join(',')==='9');
 await state(async b=>{for(const axis of ['pan','tilt'])if(b.state.config.fixtures.find(f=>f.id===9)[`flip_${axis}`])await b.action({a:'fixture_flag',id:9,[`flip_${axis}`]:false});});
 await freshReadback();assert.equal(await angle('Pan'),-110);assert.equal(await angle('Tilt'),-65);
 await page.screenshot({path:`${dir}/after-1440.png`});
 const aims=count('aim');const start=count('jog');
 await dragStick(.95,.5);
 const pan=await angle('Pan');assert(pan>-110 && pan<-108);
 assert.equal(count('aim'),aims);assert(count('jog')>start && count('jog')-start<=3);
 await page.locator('.range-field').filter({has:range('Pan')}).locator('.evidence-dot.pending').waitFor();
 assert.equal(await state(b=>b.state.history[9].pan.quality),'pending');
 const frozen=count('jog');await page.waitForTimeout(220);assert.equal(count('jog'),frozen);
 results.push({test:'confirmed Pan -110 → relative joystick, no aim/zero/echo',pan,commands:frozen-start});
 await freshReadback();await dragStick(.5,.05);
 const tilt=await angle('Tilt');assert(tilt>-65 && tilt<-63);assert.equal(count('aim'),aims);
 results.push({test:'confirmed Tilt -65 → relative joystick',tilt});
 // A new test readback confirms the expected values (the real desk is not connected).
 await state(b=>{const v=b.state.history[9];b.receive({live:{9:{pan:v.pan.value,tilt:v.tilt.value,dim:64}},values_meta:{live:{source:'ma2',freshness:'fresh',updated_at:Date.now()}}});});
 assert.equal(await state(b=>b.state.history[9].tilt.quality),'confirmed');
 await page.locator('.stage-heading').click();const kb=count('jog');
 await page.keyboard.down('ArrowRight');await page.waitForTimeout(220);await page.keyboard.up('ArrowRight');await page.waitForTimeout(150);
 assert(count('jog')>kb);
 const remembered=await angle('Pan');
 await page.locator('[data-fixture="10"]').click();await wait(b=>b.state.selected.join(',')==='10');
 await page.locator('[data-fixture="9"]').click();await wait(b=>b.state.selected.join(',')==='9');
 assert.equal(await angle('Pan'),remembered);assert.equal(await angle('Яркость'),64);
 await nav('Приборы');await nav('Сцены');await nav('Зал');assert.equal(await angle('Pan'),remembered);
 results.push({test:'keyboard, fixture and tab changes preserve Pan/Tilt/Dimmer'});
 const closed=await metrics();await shelf.click();const opened=await metrics();
 assert.deepEqual(opened.svg,closed.svg);assert.equal(opened.viewBox,closed.viewBox);
 assert(await page.locator('.quick-scenes-content .scene-card').count()>0);
 await range('Pan').focus();await page.keyboard.press('Escape');assert.equal(await shelf.getAttribute('aria-expanded'),'false');
 assert.deepEqual(await state(b=>b.state.selected),[9]);
 results.push({test:'scene overlay leaves model size and selection intact; Escape closes shelf'});
 const handle=page.getByRole('separator',{name:'Ширина инспектора'}),r=await handle.boundingBox();
 const oldJoy=(await page.locator('.joystick').boundingBox()).height,oldWheel=(await page.locator('.color-wheel').boundingBox()).width;
 await page.mouse.move(r.x+5,r.y+120);await page.mouse.down();await page.mouse.move(r.x-155,r.y+120,{steps:8});await page.mouse.up();
 const width=Number(await handle.getAttribute('aria-valuenow'));assert(width>=510&&width<=530);
 assert((await page.locator('.joystick').boundingBox()).height>oldJoy);
 assert((await page.locator('.color-wheel').boundingBox()).width>oldWheel);
 assert.equal(await page.evaluate(()=>Number(JSON.parse(localStorage.getItem('luma.inspectorWidth')))),width);
 await nav('Сцены');await nav('Зал');assert.equal(Number(await handle.getAttribute('aria-valuenow')),width);
 await page.screenshot({path:`${dir}/inspector-wide-1440.png`});
 await page.reload();await wait(b=>b.ready());await page.locator('[data-fixture="9"]').click();
 assert.equal(Number(await handle.getAttribute('aria-valuenow')),width);
 assert.equal(await shelf.getAttribute('aria-expanded'),'false');
 results.push({test:'mouse resizes inspector and controls; width survives tabs and reload',width});
 const layouts=[];
 for(const [w,h] of [[1366,768],[1024,768],[820,1180]]) {
   await page.setViewportSize({width:w,height:h});
   await page.waitForTimeout(100);
   for(const view of ['Вид сверху','Перспектива']) {
     await nav(view);
     assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
     assert(await page.evaluate(()=>document.documentElement.scrollHeight<=innerHeight+1));
     assert(await page.locator('.stage-viewport > svg').evaluate(s=>{
       const r=s.getBoundingClientRect();return [...s.querySelectorAll('[data-fixture]')].every(e=>{const b=e.getBoundingClientRect();return b.left>=r.left-1&&b.right<=r.right+1&&b.top>=r.top-1&&b.bottom<=r.bottom+1;});
     }));
     layouts.push({viewport:[w,h],view,...await metrics()});
     await page.screenshot({path:`${dir}/after-${w}-${view==='Перспектива'?'perspective':'top'}.png`});
   }
 }
 results.push({test:'adaptive hall, no clipping or page overflow',layouts});
 await page.setViewportSize({width:1440,height:900});await page.waitForFunction(()=>document.querySelector('[role="separator"]').getAttribute('aria-valuemax')==='640');await handle.focus();await page.keyboard.press('Home');assert.equal(Number(await handle.getAttribute('aria-valuenow')),280);
 await page.keyboard.press('End');assert.equal(Number(await handle.getAttribute('aria-valuenow')),640);
 await page.keyboard.press('ArrowRight');assert.equal(Number(await handle.getAttribute('aria-valuenow')),620);
 results.push({test:'keyboard resize supports bounds and steps'});
 // Touch resize uses the actual browser Pointer Events implementation.
 const touch=await context.newCDPSession(page),tr=await handle.boundingBox();
 await touch.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:tr.x+5,y:140}]});
 await touch.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{x:tr.x+85,y:140}]});
 await touch.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});
 assert(Number(await handle.getAttribute('aria-valuenow'))<620);
 results.push({test:'touch inspector resize'});
 await page.locator('[data-fixture="9"]').click();await wait(b=>b.state.selected.join(',')==='9');
 await range('Pan').fill('-110');await range('Pan').dispatchEvent('pointerup');
 await range('Tilt').fill('-65');await range('Tilt').dispatchEvent('pointerup');await page.waitForTimeout(180);
 await freshReadback();
 await page.locator('.joystick').scrollIntoViewIfNeeded();
 const joy=await page.locator('.joystick').boundingBox(),touchBefore=count('jog');
 await touch.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{x:joy.x+joy.width*.9,y:joy.y+joy.height/2}]});await page.waitForTimeout(220);
 await touch.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await page.waitForTimeout(180);
 assert(count('jog')>touchBefore);const touchAfter=count('jog');await page.waitForTimeout(180);assert.equal(count('jog'),touchAfter);
 // Blur stops a held gesture, even if the pointerup never arrives.
 await page.mouse.move(joy.x+joy.width*.9,joy.y+joy.height/2);await page.mouse.down();await page.waitForTimeout(140);
 await page.evaluate(()=>window.dispatchEvent(new Event('blur')));await page.mouse.up();const blurAfter=count('jog');await page.waitForTimeout(220);assert.equal(count('jog'),blurAfter);
 results.push({test:'touch movement and blur stop without queued repeats'});
 await range('Grandmaster').fill('73');await range('Grandmaster').dispatchEvent('pointerup');await page.waitForTimeout(200);
 await nav('Сцены');await nav('Зал');assert.equal(await angle('Grandmaster'),73);
 await shelf.click();const scene=page.locator('.quick-scenes-content .scene-card').first();await scene.click();await page.waitForTimeout(1800);
 assert(count('scene_go')>0);assert.equal(await angle('Grandmaster'),73);
 await shelf.click();
 await page.getByRole('button',{name:/Blackout/}).click();await wait(b=>b.state.status?.blackout?.phase==='active');
 await page.getByRole('button',{name:/Восстановить/}).click();await wait(b=>b.state.status?.blackout?.phase==='idle');
 results.push({test:'scene Go, Grandmaster retention and Blackout restore use existing backend'});
 await page.locator('[data-fixture="9"]').click();await wait(b=>b.state.selected.join(',')==='9');
 await page.locator('.movement').scrollIntoViewIfNeeded();const j=await page.locator('.joystick').boundingBox();
 await page.mouse.move(j.x+j.width*.9,j.y+j.height/2);await page.mouse.down();await page.waitForTimeout(150);
 await state(b=>{b.socket.close();return true;});await page.mouse.up();await wait(b=>b.ready());
 const reconnected=count('jog');await page.waitForTimeout(250);assert.equal(count('jog'),reconnected);
 results.push({test:'disconnect stops movement; reconnect never replays it'});
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:results.length,results},null,2));
} catch(e) {await page.screenshot({path:`${dir}/failure.png`,fullPage:true});throw e;}
finally {await writeFile(`${dir}/verification.json`,JSON.stringify({results,errors,actions:sent.map(a=>a.a)},null,2));await browser.close();}
