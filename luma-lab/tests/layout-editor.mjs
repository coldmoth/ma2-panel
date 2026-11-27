// Real browser + isolated mock. Never connects to a desk.
import {chromium,webkit} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir,writeFile} from 'node:fs/promises';
const output=new URL('../screenshots/layout-editor/',import.meta.url);
await mkdir(output,{recursive:true});
const results=[],errors=[],actions=[];
const browser=await chromium.launch();
const context=await browser.newContext({viewport:{width:1440,height:900},hasTouch:true});
const page=await context.newPage();
page.setDefaultTimeout(8000);
results.push=(...items)=>{console.log(...items);return Array.prototype.push.apply(results,items);};
page.on('pageerror',e=>errors.push(e.message));
page.on('websocket',ws=>ws.on('framesent',({payload})=>{try{const a=JSON.parse(payload);if(a.a)actions.push(a);}catch{}}));
const state=()=>page.evaluate(async()=>{const {bridge}=await import('/src/client.mjs');return bridge.state;});
const fixture=async id=>(await state()).config.fixtures.find(f=>f.id===id);
const saved=async()=>{await page.waitForTimeout(35);return page.waitForFunction(async()=>{const {bridge}=await import('/src/client.mjs');return !bridge.pending.size && document.querySelector('.layout-status')?.textContent==='Сохранено';},null,{timeout:8000});};
async function choose(id,shift=false){
 const el=page.locator(`[data-fixture="${id}"]`);
 await el.focus();await page.keyboard.press(shift?'Shift+Enter':'Enter');
 if(await page.getByRole('button',{name:'Закрыть участок',exact:true}).count())await page.getByRole('button',{name:'Закрыть участок',exact:true}).click();
}
async function origin(id){return page.locator(`[data-fixture="${id}"]`).evaluate(e=>{const m=e.getScreenCTM();return {x:m.e,y:m.f};});}
async function roomPoint(x,y){return page.locator('[data-hall-geometry]').evaluate(async(g,{x,y})=>{
 const {project}=await import('/src/model.mjs');const {bridge}=await import('/src/client.mjs');
 const v=project(x,y,true,bridge.state.config.hall),p=new DOMPoint(...v).matrixTransform(g.getScreenCTM());return {x:p.x,y:p.y};
},{x,y});}
async function dragTo(id,x,y){
 const start=await origin(id),end=await roomPoint(x,y);
 await page.mouse.move(start.x,start.y);await page.mouse.down();await page.mouse.move(end.x,end.y,{steps:9});await page.mouse.up();await saved();
 const f=await fixture(id);assert(Math.abs(f.x-x)<.002 && Math.abs(f.y-y)<.002,`drag ${id}`);
}
async function rotate(id,angle,{shift=false,cancel=false,touch=false}={}){
 const center=await origin(id),hit=await page.locator(`[data-rotation="${id}"] circle`).first().boundingBox(),
   start={x:hit.x+hit.width/2,y:hit.y+hit.height/2},r=Math.hypot(start.x-center.x,start.y-center.y),a=angle*Math.PI/180,
   end={x:center.x+Math.sin(a)*r,y:center.y-Math.cos(a)*r};
 if(shift)await page.keyboard.down('Shift');
 if(touch){const cdp=await context.newCDPSession(page);await cdp.send('Input.dispatchTouchEvent',{type:'touchStart',touchPoints:[{...start,id:1}]});await cdp.send('Input.dispatchTouchEvent',{type:'touchMove',touchPoints:[{...end,id:1}]});await cdp.send('Input.dispatchTouchEvent',{type:'touchEnd',touchPoints:[]});await cdp.send('Emulation.setTouchEmulationEnabled',{enabled:false});await cdp.detach();}
 else {await page.mouse.move(start.x,start.y);await page.mouse.down();await page.mouse.move(end.x,end.y,{steps:8});
  assert.match(await page.locator('.layout-status').textContent(),/несохран/);
  if(cancel)await page.keyboard.press('Escape');await page.mouse.up();}
 if(shift)await page.keyboard.up('Shift');
 if(!cancel)await saved();
}
try {
 await page.addInitScript(() => localStorage.setItem("luma.language.v1", "ru"));
 await page.goto(process.env.LUMA_URL || 'http://127.0.0.1:5194');
 await page.locator('[data-fixture="1"]').waitFor();
 await page.evaluate(async()=>{const {bridge}=await import('/src/client.mjs');
  const xy=[[.2,.12],[.4,.12],[.6,.12],[.8,.12],[.05,.35],[.05,.6],[.95,.35],[.95,.6],[.12,.22],[.5,.22],[.88,.22],[.18,.86],[.5,.88],[.82,.86],[.12,.73],[.34,.84],[.66,.84],[.88,.73],[.4,.98],[.6,.98]];
  await bridge.action({a:'layout_save',pos:xy.map(([x,y],i)=>({id:i+1,x,y,rot:null}))});
  await bridge.action({a:'hall_save',hall:{...bridge.state.config.hall,w:18,d:14,stageWidth:12,stageDepth:4}});
 });
 const workingSelection=(await state()).selected;
 await page.getByRole('button',{name:'Расстановка',exact:true}).click();
 await page.getByRole('button',{name:'Вид сверху',exact:true}).click();
 await page.waitForTimeout(150);
 await choose(1);
 await rotate(1,45,{shift:true});assert.equal((await fixture(1)).rot,45);
 results.push('mouse rotation 45° with Shift; persisted');
 await page.getByRole('spinbutton',{name:'Поворот, °',exact:true}).fill('90');
 await page.getByRole('button',{name:'Сохранить',exact:true}).click();await saved();assert.equal((await fixture(1)).rot,90);
 await page.getByRole('combobox',{name:'Режим ориентации'}).selectOption('auto');await saved();assert.equal((await fixture(1)).rot,undefined);
 await dragTo(1,.03,.5);
 assert.equal(await page.getByRole('slider',{name:'Поворот прибора'}).getAttribute('aria-valuenow'),'90');
 results.push('numeric 90°; reset Auto; drag to left wall gives 90°');
 await rotate(1,45);assert(Math.abs((await fixture(1)).rot-45)<.2);
 const beforeCancel=await fixture(1);await rotate(1,140,{cancel:true});assert.deepEqual(await fixture(1),beforeCancel);
 results.push('Escape restores original rotation');
 // Actual touch pointer rotation, then keyboard access on the same handle.
 await rotate(1,90,{touch:true});assert(Math.abs((await fixture(1)).rot-90)<.3);
 await page.getByRole('slider',{name:'Поворот прибора'}).focus();await page.keyboard.press('ArrowRight');await saved();
 assert(Math.abs((await fixture(1)).rot-90.1)<.3);
 results.push('touch rotation and keyboard 0.1° adjustment');
 // Pin the 5 CSS px threshold, irrespective of editor zoom.
 for(const zoom of [false,true]){
  if(zoom){await page.getByRole('button',{name:'Увеличить',exact:true}).click();await page.getByRole('button',{name:'Увеличить',exact:true}).click();}
  const before=await fixture(2),p=await origin(2);await page.mouse.move(p.x,p.y);await page.mouse.down();await page.mouse.move(p.x+4,p.y);await page.mouse.up();
  assert.deepEqual(await fixture(2),before);assert.equal(await page.locator('[data-fixture="2"]').getAttribute('aria-pressed'),'true');
 }
 await page.getByRole('button',{name:'Сбросить вид'}).click();
 results.push('4 CSS px remains a click before/after zoom');
 await choose(2);await dragTo(2,.32123,.27123);
 const precise=await fixture(2);
 await page.getByRole('spinbutton',{name:'Поворот, °',exact:true}).fill('45.1');await page.getByRole('button',{name:'Сохранить',exact:true}).click();await saved();
 const rotated=await fixture(2);assert.equal(rotated.x,precise.x);assert.equal(rotated.y,precise.y);assert.equal(rotated.rot,45.1);
 // Hold the real request briefly: status/preview must reflect a pending save.
 await page.evaluate(async()=>{const {bridge}=await import('/src/client.mjs');const send=bridge.socket.send.bind(bridge.socket);bridge.socket.send=data=>{if(JSON.parse(data).a==='layout_save'){bridge.socket.send=send;window.releaseLayout=()=>send(data);}else send(data);};});
 await page.getByRole('button',{name:'90°',exact:true}).click();
 await page.locator('.layout-status').filter({hasText:'Сохранение…'}).waitFor();assert(await page.getByRole('button',{name:'Отменить',exact:true}).isDisabled());
 assert.equal((await fixture(2)).rot,45.1);
 await page.evaluate(()=>window.releaseLayout());await saved();assert.equal((await fixture(2)).rot,90);
 results.push('angle-only save preserves exact X/Y; pending status and lock until ACK');

 // Twenty physical drags, with LED bars aligned along the walls.
 for(let id=1;id<=20;id++){
  await choose(id);
  const col=(id-1)%5,row=Math.floor((id-1)/5);
  await dragTo(id,.12+col*.18,.16+row*.21);
  if(id<=8){await page.getByRole('button',{name:'Выровнять вдоль стены'}).click();await saved();}
 }
 results.push('placed 20 fixtures by dragging; aligned 8 bars');
 // Place three tiny PARs with touching/overlapping hit targets.
 for(const [id,x] of [[15,.46],[16,.50],[17,.54]]){
  await choose(id);await page.getByRole('spinbutton',{name:'X, м',exact:true}).fill(String(Number((x*(await state()).config.hall.w).toFixed(2))));
  await page.getByRole('spinbutton',{name:'Y, м',exact:true}).fill('7');await page.getByRole('button',{name:'Сохранить',exact:true}).click();await saved();
 }
 // A genuine pointer click opens local precision; each close neighbour remains selectable.
 const close=await origin(16);await page.mouse.click(close.x,close.y);
 await page.getByRole('button',{name:'Выбрать отдельно ID 15',exact:true}).click();
 await page.getByRole('button',{name:'Выбрать отдельно ID 16',exact:true}).click();
 await page.getByRole('button',{name:'Выбрать отдельно ID 17',exact:true}).click();
 assert.equal(await page.locator('[data-fixture="17"]').getAttribute('aria-pressed'),'true');
 await page.getByRole('button',{name:'Закрыть участок',exact:true}).click();
 await choose(15);await choose(16,true);assert.equal(await page.locator('[data-fixture][aria-pressed="true"]').count(),2);
 assert.deepEqual((await state()).selected,workingSelection);
 results.push('three adjacent PARs individually selectable; Shift selection independent of hall');
 await choose(17);await page.getByRole('spinbutton',{name:'X, м',exact:true}).fill('8.25');await page.getByRole('spinbutton',{name:'Y, м',exact:true}).fill('6.75');
 await page.getByRole('button',{name:'Сохранить',exact:true}).click();await saved();
 const coordinates=await fixture(17);assert(Math.abs(coordinates.x*(await state()).config.hall.w-8.25)<1e-8);
 await page.getByRole('button',{name:'Отменить',exact:true}).click();await saved();assert.notEqual((await fixture(17)).x,coordinates.x);
 await page.getByRole('button',{name:'Повторить',exact:true}).click();await saved();assert.equal((await fixture(17)).x,coordinates.x);
 await page.getByRole('spinbutton',{name:'X, м',exact:true}).fill('2');await page.getByRole('button',{name:'Сбросить',exact:true}).click();assert.equal((await fixture(17)).x,coordinates.x);
 results.push('centimetre coordinates; draft reset; local Undo/Redo');
 // Pointer cancellation and lost capture must never save or poison the next click.
 for(const event of ['pointercancel','lostpointercapture']){
  await choose(17);const before=await fixture(17),p=await origin(17);
  await page.mouse.move(p.x,p.y);await page.mouse.down();await page.mouse.move(p.x+24,p.y+10);
  await page.locator('.stage-viewport>svg').dispatchEvent(event,{pointerId:1});await page.mouse.up();assert.deepEqual(await fixture(17),before);
  const next=await origin(18);await page.mouse.click(next.x,next.y);assert.equal(await page.locator('[data-fixture="18"]').getAttribute('aria-pressed'),'true');
  if(await page.getByRole('button',{name:'Закрыть участок'}).count())await page.getByRole('button',{name:'Закрыть участок'}).click();
 }
 results.push('pointercancel/lost capture rollback and next click works');
 // Force a real revision rejection. Preview must roll back, history must not advance.
 await choose(17);
 await page.evaluate(async()=>{const {bridge}=await import('/src/client.mjs');const send=bridge.socket.send.bind(bridge.socket);bridge.socket.send=data=>{const a=JSON.parse(data);if(a.a==='layout_save'){bridge.socket.send=send;a.config_revision='stale-layout-test';}send(JSON.stringify(a));};});
 await page.getByRole('spinbutton',{name:'X, м',exact:true}).fill('3');await page.getByRole('button',{name:'Сохранить',exact:true}).click();await page.getByRole('alert').last().waitFor();
 assert.equal((await fixture(17)).x,coordinates.x);
 assert.match(await page.locator('.layout-status').textContent(),/Ошибка/);
 // Recover explicitly and clear the rejected draft.
 await page.getByRole('button',{name:'Сбросить',exact:true}).click();
 await page.getByRole('button',{name:'45°',exact:true}).click();await saved();
 results.push('backend revision error rolls preview back; explicit recovery');
 await page.locator('.layout-geometry summary').click();
 const hallBefore=(await state()).config.hall,positionsBefore=(await state()).config.fixtures.map(({id,x,y})=>({id,x,y}));
 await page.getByRole('spinbutton',{name:'Ширина помещения, м',exact:true}).fill('20');
 await page.getByRole('spinbutton',{name:'Длина помещения, м',exact:true}).fill('16');
 await page.getByRole('spinbutton',{name:'Ширина сцены, м',exact:true}).fill('12');
 await page.getByRole('spinbutton',{name:'Глубина сцены, м',exact:true}).fill('4');
 await page.getByRole('button',{name:'Сохранить геометрию',exact:true}).click();await saved();
 assert.deepEqual((await state()).config.fixtures.map(({id,x,y})=>({id,x,y})),positionsBefore);
 assert.equal((await state()).config.hall.w,20);
 await page.getByRole('button',{name:'Отменить',exact:true}).click();await saved();assert.deepEqual((await state()).config.hall,hallBefore);
 await page.getByRole('button',{name:'Повторить',exact:true}).click();await saved();
 await page.locator('.layout-geometry summary').click();
 results.push('room/stage geometry persists normalized positions; geometry Undo/Redo');
 const persisted=(await state()).config;
 await page.reload();await page.locator('[data-fixture="1"]').waitFor();await page.getByRole('button',{name:'Расстановка',exact:true}).click();await choose(1);
 assert.deepEqual((await state()).config.fixtures,persisted.fixtures);assert.deepEqual((await state()).config.hall,persisted.hall);
 assert(await page.getByRole('button',{name:'Отменить',exact:true}).isDisabled());
 results.push('reload preserves fixtures/geometry; session history cleared');
 const measures=[];
 for(const [width,height] of [[1440,900],[1024,768]]){
  if(width===1024){const cdp=await context.newCDPSession(page);await cdp.send('Emulation.setTouchEmulationEnabled',{enabled:true});await cdp.detach();}
  await page.setViewportSize({width,height});await page.waitForTimeout(180);
  for(const collapsed of width>1100?[false,true]:[false]){
   if(collapsed)await page.getByRole('button',{name:'Свернуть навигацию',exact:true}).click();
   const m=await page.evaluate(()=>({size:[innerWidth,innerHeight],overflow:document.documentElement.scrollHeight>innerHeight || document.documentElement.scrollWidth>innerWidth,
    canvas:document.querySelector('.stage-viewport').getBoundingClientRect().toJSON(),inspector:document.querySelector('.layout-inspector').getBoundingClientRect().toJSON()}));
   assert(!m.overflow,JSON.stringify(m));assert(m.inspector.x>m.canvas.x+m.canvas.width-2);assert(m.canvas.height>400);
   await page.screenshot({path:new URL(`chromium-${width}${collapsed?'-collapsed':''}.png`,output).pathname});measures.push({...m,collapsed});
   if(collapsed)await page.getByRole('button',{name:'Развернуть навигацию',exact:true}).click();
  }
 }
 // Clear selection through a genuine empty-background click.
 await page.locator('.stage-viewport>svg').click({position:{x:8,y:8}});assert.equal(await page.locator('[data-fixture][aria-pressed="true"]').count(),0);
 assert(actions.filter(a=>['layout_save','hall_save'].includes(a.a)).length>25);assert(actions.every(a=>['layout_save','hall_save','plan_editing'].includes(a.a)),JSON.stringify(actions.filter(a=>!['layout_save','hall_save','plan_editing'].includes(a.a))));
 assert.deepEqual(errors,[]);
 await writeFile(new URL('verification.json',output),JSON.stringify({results,measures,errors,actions:actions.map(({a,pos,hall})=>({a,pos,hall}))},null,2));
 console.log(JSON.stringify({passed:results.length,results,actions:actions.length,measures},null,2));
} catch(e){await page.screenshot({path:new URL('failure.png',output).pathname});throw e;}
finally {await browser.close();}
// Independent engine checks the editor layout and pointer rotation.
const wb=await webkit.launch();
try{
 const p=await wb.newPage({viewport:{width:1024,height:768}});
 await p.addInitScript(() => localStorage.setItem("luma.language.v1", "ru"));
 await p.goto(process.env.LUMA_URL||'http://127.0.0.1:5194');
 await p.getByRole('button',{name:'Расстановка',exact:true}).click();await p.locator('[data-fixture="1"]').focus();await p.keyboard.press('Enter');
 await p.getByRole('slider',{name:'Поворот прибора'}).focus();await p.keyboard.press('Shift+ArrowRight');
 await p.waitForFunction(()=>document.querySelector('.layout-status')?.textContent==='Сохранено');
 await p.screenshot({path:new URL('webkit-1024.png',output).pathname});
 assert(await p.locator('.layout-inspector').isVisible());console.log('WebKit keyboard rotation and 1024 layout PASS');
}finally{await wb.close();}
