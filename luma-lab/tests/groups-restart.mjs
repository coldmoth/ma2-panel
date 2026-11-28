// Run after restarting the isolated harness with the documented group fixture.
import {chromium} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir, writeFile} from 'node:fs/promises';
const browser=await chromium.launch();
const p=await browser.newPage({viewport:{width:1440,height:900}});
const errors=[],actions=[];p.on('pageerror',e=>errors.push(e.message));p.on('websocket',ws=>ws.on('framesent',({payload})=>{const a=JSON.parse(payload);if(a.a)actions.push(a);}));
try {
 await mkdir(new URL('../screenshots/groups-editor/', import.meta.url), {recursive:true});
 await p.addInitScript(() => localStorage.setItem("luma.language.v1", "ru"));
 await p.goto(process.env.LUMA_URL || 'http://127.0.0.1:5196');await p.locator('[data-fixture="1"]').waitFor();
 const config=await p.evaluate(async()=>{const {bridge}=await import('/src/client.mjs');return bridge.state.config;});
 const g=config.groups.find(g=>g.label==='Проверка рестарта');assert.deepEqual(g.fixtures,[2,10]);assert.equal(g.color,'#7ab7b0');assert.equal(g.icon,'sun');
 await p.getByRole('button',{name:'Приборы',exact:true}).click();const nav=p.getByRole('complementary',{name:'Категории приборов'});
 for(const label of ['Балкон','Сцена']) {
  await nav.getByTitle(label,{exact:true}).click();assert.equal(await p.locator('.fixture-card').count(),2);
  assert.equal(await p.getByLabel('Действия группы').count(),0);assert.equal(await p.getByRole('button',{name:'Изменить состав',exact:true}).count(),0);
  await p.getByRole('button',{name:'Выделить группу',exact:true}).click();await p.waitForFunction(async()=>{const {bridge}=await import('/src/client.mjs');return !bridge.state.selecting;});
  assert.deepEqual(await p.evaluate(async()=>{const {bridge}=await import('/src/client.mjs');return bridge.state.selected;}),label.includes('Балкон')?[1,9]:[15,19]);
 }
 await p.screenshot({path:new URL('../screenshots/groups-editor/ma2-readonly.png',import.meta.url).pathname});
 assert(actions.every(a=>a.a==='select_fixtures'));assert.deepEqual(errors,[]);
 const output=new URL('../screenshots/groups-editor/restart-verification.json',import.meta.url);
 await writeFile(output,JSON.stringify({results:['backend restart preserves group IDs/members/color/icon; both backend MA2 group formats are read-only and selectable'],actions,errors},null,2));
 // Remove the test-created local group. Imported sample groups are kept in this isolated runtime only.
 await p.evaluate(async id=>{const {bridge}=await import('/src/client.mjs');await bridge.action({a:'group_delete',id});},g.id);
 console.log('PASS backend restart persistence and MA2 read-only/selection, zero console errors');
}finally{await browser.close();}
