// Full operator scenario against an isolated real mock backend, never a desk.
import {chromium,webkit} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,readFile,writeFile} from 'node:fs/promises';
const output=new URL('../screenshots/groups-editor/',import.meta.url);
await mkdir(output,{recursive:true});
const results=[],errors=[],actions=[],measures=[];
const url=process.env.LUMA_URL || 'http://127.0.0.1:5196';
const browser=await chromium.launch();
const context=await browser.newContext({viewport:{width:1440,height:900},hasTouch:true});
const page=await context.newPage();page.setDefaultTimeout(8000);
page.on('pageerror',e=>errors.push(e.message));
page.on('websocket',ws=>ws.on('framesent',({payload})=>{try{const a=JSON.parse(payload);if(a.a)actions.push(a);}catch{}}));
const groupActions = () => actions.filter(({a}) => a !== 'plan_editing');
const state=()=>page.evaluate(async()=>{const {bridge}=await import('/src/client.mjs');return bridge.state;});
const dialog=()=>page.locator('dialog[open]');
const nav=()=>page.getByRole('complementary',{name:'Категории приборов'});
const card=id=>page.locator(`[data-catalog-fixture="${id}"]`);
const group=async label=>(await state()).config.groups.find(g=>g.label===label);
const settled=()=>page.waitForFunction(async()=>{const {bridge}=await import('/src/client.mjs');return !bridge.pending.size && !bridge.state.selecting;});
async function save(){await dialog().getByRole('button',{name:'Сохранить группу',exact:true}).click();await dialog().waitFor({state:'hidden'});await settled();}
async function openGroup(label){await nav().getByRole('button').filter({hasText:label}).click();}
async function edit(){await page.getByRole('button',{name:'Изменить состав',exact:true}).click();}
async function deleteGroup(label){await openGroup(label);await page.getByLabel('Действия группы').click();await page.getByRole('button',{name:'Удалить группу',exact:true}).click();await dialog().getByRole('button',{name:'Удалить группу',exact:true}).click();await dialog().waitFor({state:'hidden'});await settled();}
function record(s){results.push(s);console.log('PASS',s);}
try {
 await page.addInitScript(() => localStorage.setItem("luma.language.v1", "ru"));
 await page.goto(url);await page.locator('[data-fixture="1"]').waitFor();await settled();
 await page.waitForFunction(async () => {
  const {bridge} = await import('/src/client.mjs');
  const config = bridge.state.config;
  return config?.fixtures.every(({type}) => config.dmx_map?.[type]?.has);
 });
 const original=(await state()).config.fixtures, originalHall=(await state()).config.hall;
 await page.getByRole('button',{name:'Приборы',exact:true}).click();
 const before=groupActions().length;
 await nav().getByRole('button',{name:'Новая локальная группа',exact:true}).click();
 await dialog().getByLabel('Название группы').fill('Левая сторона');
 for(const name of ['LED Bar 01','Moving Head 09','PAR 15','Fresnel 19'])await dialog().getByRole('checkbox',{name:`В группе: ${name}`,exact:true}).check();
 await page.screenshot({path:new URL('group-editor.png',output).pathname});
 await save();const left=await group('Левая сторона');assert.deepEqual(left.fixtures,[1,9,15,19]);
 assert(groupActions().slice(before).every(a=>a.a==='group_save'));
 await openGroup('Левая сторона');assert.equal(await page.locator('.fixture-card').count(),4);
 record('create group with four fixture types; composition and count; CRUD sends only config actions');
 await page.getByRole('button',{name:'Выделить группу',exact:true}).click();await settled();assert.deepEqual((await state()).selected,[1,9,15,19]);
 await card(1).click();await settled();await page.getByRole('button',{name:'Добавить в группу',exact:true}).click();
 await dialog().getByRole('button').filter({hasText:'Фронтальный свет'}).click();
 assert(await dialog().getByRole('checkbox',{name:'В группе: LED Bar 01',exact:true}).isChecked());await save();
 assert((await group('Фронтальный свет')).fixtures.includes(1));assert.deepEqual((await group('Левая сторона')).fixtures,[1,9,15,19]);
 record('selected fixture added to another existing group; overlapping membership retained');
 await edit();await dialog().getByLabel('Название группы').fill('Левая сцена');
 await dialog().getByRole('checkbox',{name:'В группе: PAR 15',exact:true}).uncheck();
 await dialog().getByRole('button',{name:'Цвет #7ab7b0',exact:true}).click();await dialog().getByRole('button',{name:'Иконка: Свет',exact:true}).click();await save();
 const renamed=await group('Левая сцена');assert.equal(renamed.id,left.id);assert.deepEqual(renamed.fixtures,[1,9,19]);assert.equal(renamed.icon,'sun');assert.equal(renamed.color,'#7ab7b0');
 await page.getByRole('button',{name:'Зал',exact:true}).click();await page.locator('.sidebar-groups>button').filter({hasText:'Левая сцена'}).click();await settled();
 assert.deepEqual((await state()).selected,[1,9,19]);
 assert.equal(await page.locator('.sidebar-groups>button').filter({hasText:'Левая сцена'}).locator('svg path').getAttribute('d'),await page.evaluate(async()=>{return 'M12 3v2 M12 19v2 M3 12h2 M19 12h2 M5.6 5.6 1.4 1.4 M17 17l1.4 1.4 M5.6 18.4 1.4-1.4 M17 7l1.4-1.4 M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0';}));
 record('rename/remove/color/icon persist; Hall selects updated fixture IDs and icon');
 await page.reload();await page.locator('[data-fixture="1"]').waitFor();assert.deepEqual((await group('Левая сцена')).fixtures,[1,9,19]);
 const disk=JSON.parse(await readFile(process.env.LUMA_GROUP_CONFIG || '/tmp/luma-groups-runtime/config.json','utf8'));
 assert.deepEqual(disk.groups.find(g=>g.id===left.id).fixtures,[1,9,19]);
 assert.deepEqual((await state()).config.fixtures,original);assert.deepEqual((await state()).config.hall,originalHall);
 record('reload and on-disk persistence; all fixture properties and geometry unchanged');
 await page.getByRole('button',{name:'Приборы',exact:true}).click();await openGroup('Левая сцена');
 await page.getByRole('button',{name:'Выделить группу',exact:true}).click();await settled();
 await page.screenshot({path:new URL('fixtures.png',output).pathname});
 // Real backend revision error: no optimistic success and draft is retained.
 await edit();await dialog().getByLabel('Название группы').fill('Не терять черновик');
 await page.evaluate(async()=>{const {bridge}=await import('/src/client.mjs');const send=bridge.socket.send.bind(bridge.socket);bridge.socket.send=data=>{const a=JSON.parse(data);if(a.a==='group_save'){bridge.socket.send=send;a.config_revision='stale-groups-test';}send(JSON.stringify(a));};});
 await dialog().getByRole('button',{name:'Сохранить группу',exact:true}).click();await dialog().getByRole('alert').waitFor();
 assert.equal(await dialog().getByLabel('Название группы').inputValue(),'Не терять черновик');assert(await group('Левая сцена'));
 await dialog().getByRole('button',{name:'Отмена',exact:true}).click();record('backend rejects stale revision; inline error and draft preserved; cancel writes nothing');
 // Another window changes the same group while the editor is open.
 await edit();const second=await context.newPage();await second.goto(url);await second.locator('[data-fixture="1"]').waitFor();
 await second.evaluate(async id=>{const {bridge}=await import('/src/client.mjs');const g=bridge.state.config.groups.find(g=>g.id===id);await bridge.action({a:'group_save',id,label:'Левая сцена · актуальная',ids:g.fixtures});},left.id);
 await dialog().getByRole('button',{name:'Загрузить актуальную',exact:true}).waitFor();assert(await dialog().getByRole('button',{name:'Сохранить группу',exact:true}).isDisabled());
 await dialog().getByRole('button',{name:'Загрузить актуальную',exact:true}).click();assert.equal(await dialog().getByLabel('Название группы').inputValue(),'Левая сцена · актуальная');
 await dialog().getByRole('button',{name:'Отмена',exact:true}).click();await second.close();record('concurrent config broadcast blocks stale draft; explicit reload gets current data');
 // Delayed ACK must block duplicate saves and closing.
 await edit();await dialog().getByLabel('Название группы').fill('Левая сцена');
 await page.evaluate(async()=>{const {bridge}=await import('/src/client.mjs');const receive=bridge.receive.bind(bridge);bridge.receive=m=>{if(m.a==='group_save' && m.ok!==undefined){setTimeout(()=>receive(m),500);}else receive(m);};window.restoreGroupReceive=()=>{bridge.receive=receive;};});
 const count=actions.filter(a=>a.a==='group_save').length;
 await dialog().getByRole('button',{name:'Сохранить группу',exact:true}).click();assert(await dialog().getByRole('button',{name:'Сохранение…',exact:true}).isDisabled());
 await dialog().getByRole('button',{name:'Закрыть',exact:true}).click();assert(await dialog().isVisible());await page.keyboard.press('Escape');assert(await dialog().isVisible());await dialog().waitFor({state:'hidden'});await page.evaluate(()=>window.restoreGroupReceive());
 assert.equal(actions.filter(a=>a.a==='group_save').length,count+1);record('delayed ACK blocks duplicate save and premature close');
 // Search by display type, name, Fixture ID.
 await nav().getByRole('button').filter({hasText:'Все приборы'}).click();
 for(const [q,n] of [['Moving Head',6],['Fresnel 19',1],['20',1]]){await page.getByLabel('Найти прибор',{exact:true}).fill(q);assert.equal(await page.locator('.fixture-card').count(),n);}
 await page.getByLabel('Найти прибор',{exact:true}).fill('');await card(2).click();await settled();await card(10).click({modifiers:['Shift']});await settled();assert.deepEqual((await state()).selected,[2,10]);
 await page.getByRole('button',{name:'Добавить в группу',exact:true}).click();await dialog().getByRole('button',{name:'Создать новую группу',exact:true}).click();await dialog().getByLabel('Название группы').fill('Дуэт');await save();assert.deepEqual((await group('Дуэт')).fixtures,[2,10]);
 record('search name/ID/type; Shift multiselect; create group from selected fixtures');
 await nav().getByRole('button',{name:'Новая локальная группа',exact:true}).click();await dialog().getByLabel('Название группы').fill('Пустая');await save();await openGroup('Пустая');await page.getByText('Группа пока пуста',{exact:true}).waitFor();await deleteGroup('Пустая');record('empty groups create/open/delete');
 // Deleting the active Hall group clears local selection without sending Clear.
 await page.getByRole('button',{name:'Зал',exact:true}).click();await page.locator('.sidebar-groups>button').filter({hasText:'Левая сцена'}).click();await settled();
 await page.getByRole('button',{name:'Приборы',exact:true}).click();await openGroup('Левая сцена');
 for(const [width,height] of [[1440,900],[1024,768]]){
  await page.setViewportSize({width,height});await page.waitForTimeout(100);
  const m=await page.evaluate(()=>({width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth}));assert(!m.overflow,JSON.stringify(m));measures.push(m);
  await page.screenshot({path:new URL(`fixtures-${width}.png`,output).pathname});await edit();await page.screenshot({path:new URL(`editor-${width}.png`,output).pathname});
  const modal=await dialog().boundingBox();assert(modal.x>=0 && modal.y>=0 && modal.x+modal.width<=width+1 && modal.y+modal.height<=height+1);
  await dialog().getByRole('button',{name:'Отмена',exact:true}).click();
 }
 await page.setViewportSize({width:1440,height:900});
 await page.getByLabel('Действия группы').click();await page.getByRole('button',{name:'Удалить группу',exact:true}).click();await dialog().getByRole('button',{name:'Отмена',exact:true}).click();assert(await group('Левая сцена'));
 const deletion=actions.length;await deleteGroup('Левая сцена');assert.equal(await group('Левая сцена'),undefined);assert.deepEqual((await state()).selected,[]);assert(actions.slice(deletion).every(a=>a.a==='group_delete'));
 assert((await group('Фронтальный свет')).fixtures.includes(1));assert.deepEqual((await state()).config.fixtures,original);await deleteGroup('Дуэт');
 record('delete confirmation/cancel; active selection cleared locally; fixtures and other groups unchanged');
 assert(actions.every(a=>['group_save','group_delete','select_fixtures','plan_editing'].includes(a.a)),JSON.stringify(actions));
 assert(actions.filter(({a}) => a === 'plan_editing').every(({active}) => typeof active === 'boolean'));assert.deepEqual(errors,[]);
 const safari=await webkit.launch();try {const p=await safari.newPage({viewport:{width:1024,height:768}});await p.addInitScript(() => localStorage.setItem("luma.language.v1", "ru"));await p.goto(url);await p.locator('[data-fixture="1"]').waitFor();await p.getByRole('button',{name:'Приборы',exact:true}).click();await p.getByRole('button',{name:'Новая локальная группа',exact:true}).click();await p.getByLabel('Название группы').fill('WebKit');await p.getByRole('checkbox',{name:'В группе: LED Bar 01',exact:true}).check();await p.getByRole('button',{name:'Сохранить группу',exact:true}).click();await p.locator('dialog[open]').waitFor({state:'hidden'});assert(await p.getByRole('complementary',{name:'Категории приборов'}).getByRole('button').filter({hasText:'WebKit'}).count());await p.screenshot({path:new URL('webkit-1024.png',output).pathname});await p.evaluate(async()=>{const {bridge}=await import('/src/client.mjs');const g=bridge.state.config.groups.find(g=>g.label==='WebKit');await bridge.action({a:'group_delete',id:g.id});});}finally{await safari.close();}
 record('Chromium desktop/tablet and WebKit touch-size CRUD; no horizontal overflow or JS errors');
 await writeFile(new URL('verification.json',output),JSON.stringify({results,measures,errors,actions},null,2));
 console.log(`${results.length} scenario groups PASS; ${actions.length} actions`);
} catch(e) {await page.screenshot({path:new URL('failure.png',output).pathname});throw e;} finally {await browser.close();}
