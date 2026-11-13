'use strict';
// Empty panel + independent synthetic console. Never substitutes for real V2 FixtureTypes.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {chromium,webkit}=require('./browser_smoke/node_modules/playwright');
const [url,,out]=process.argv.slice(2),headers={'x-ma2-test':process.env.MA2_TEST_TOKEN},results=[];
(async()=>{
 for(const [engine,type] of Object.entries({chromium,webkit})){
  const browser=await type.launch(),context=await browser.newContext({viewport:{width:1366,height:768},hasTouch:true});
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));page.setDefaultTimeout(15000);
  async function control(mode){const r=await (mode?context.request.post(url+'/__quality/control',{headers,data:{mode}}):context.request.get(url+'/__quality/control',{headers}));assert(r.ok());return r.json();}
  async function check(name,fn){try{await fn();results.push({engine,profile:'field-start',name,status:'success'});}catch(e){results.push({engine,profile:'field-start',name,status:'failure',error:e.message});throw e;}}
  async function nav(sec){await page.locator(`#rail [data-sec="${sec}"]`).click();}
  async function pick(ids){await nav('light');await page.getByRole('button',{name:'Приборы',exact:true}).click();
   const clear=page.locator('.target-bar').getByRole('button',{name:'Снять выбор',exact:true});if(await clear.isEnabled())await clear.click();
   for(const id of ids)await page.locator('.fixture-row').filter({has:page.locator('.id',{hasText:new RegExp('^'+id+'$')})}).click();
   await page.waitForFunction(ids=>JSON.stringify(state.selection)===JSON.stringify(ids),ids);
  }
  try{
   if(engine!=='chromium'){const before=(await control()).instance;await control('reset');
    for(let n=0;n<150;n++){await new Promise(r=>setTimeout(r,100));try{if((await control()).instance!==before)break;}catch{}}
   }
   await page.goto(url);await page.waitForFunction(()=>connected()&&state.mock);
   await check('empty-install-import-patch-and-types',async()=>{
    const initial=await control();assert.deepEqual(initial.config.fixtures,[]);assert.deepEqual(initial.config.groups,[]);assert.deepEqual(initial.config.ma2groups||[],[]);assert(!Object.keys(initial.config.dmx_map||{}).length);
    await nav('prepare');await page.getByRole('button',{name:'Шоу',exact:true}).click();
    await page.getByRole('button',{name:/^Привязать план к «/}).click();
    await page.waitForFunction(()=>state.config.show===state.show.name);
    await nav('prepare');await page.getByRole('button',{name:'Подключение и синхронизация',exact:true}).click();
    await page.getByRole('button',{name:'Получить оборудование из MA2',exact:true}).click();
    await page.waitForFunction(()=>state.config.fixtures.length===60&&state.fetch?.state==='done');
    const s=await control();assert(s.config.fixtures.every(f=>!(f.params||[]).length));
    assert.equal(s.config.dmx_map['1 Profile A']?.r,2,'Confirmed RGB channel is missing');assert.equal(Object.keys(s.config.dmx_map).length,3);assert(s.config.dmx_map['1 Profile A'].has.includes('pos'));assert.notEqual(s.config.fixtures.find(f=>f.id===1).moves,true,'movement must not come from a name guess');
    for(const n of [1,2,3])assert(s.received.some(c=>c.startsWith('Export FixtureType '+n+' ')));
   });
   await check('visible-selection-and-independent-rgb-dimmer',async()=>{
    await nav('light');for(const name of ['Группы','Приборы','План'])assert(await page.getByRole('button',{name,exact:true}).isVisible());
    await pick([1]);await page.locator('.c-dim').getByRole('button',{name:'100%',exact:true}).click();
    await page.locator('.primary-colors').getByRole('button',{name:'Красный',exact:true}).click();
    await page.waitForFunction(()=>state.simulation?.[1]?.dim===100&&state.simulation[1].rgb.join(',')==='100,0,0');
    const s=await control();assert.equal(s.output[1].dim,100);assert.deepEqual(s.output[1].rgb,[100,0,0]);assert.equal(s.output[2].dim,0);
    await page.locator('.target-bar').getByRole('button',{name:'Снять выбор',exact:true}).click();await page.waitForFunction(()=>!state.selection.length);
    const cleared=await control();assert.deepEqual(cleared.output,s.output,'deselect must preserve light');assert(cleared.received.slice(s.received.length).every(c=>cleared.read_only.includes(c)),'deselect sends no light commands');
   });
   await check('group-import-from-empty-and-panel-group',async()=>{
    await nav('prepare');await page.getByRole('button',{name:'Подключение и синхронизация',exact:true}).click();
    await page.getByRole('button',{name:'Прочитать из MA2',exact:true}).click();await page.waitForFunction(()=>state.ma2read?.ok&&state.ma2read.groups.length===2);
    await page.getByRole('button',{name:'Добавить отмеченное',exact:true}).click();await page.waitForFunction(()=>state.config.ma2groups?.length===2);
    await nav('light');await page.getByRole('button',{name:'Группы',exact:true}).click();await page.getByText('Фронт MA2',{exact:true}).click();
    await page.waitForFunction(()=>JSON.stringify(state.selection)==='[1,2]');assert.match(await page.locator('.pick').textContent(),/1, 2/);
    page.once('dialog',d=>d.accept('Панельная группа'));await page.getByRole('button',{name:'Группа из выбранных (2)',exact:true}).click();
    await page.waitForFunction(()=>state.config.groups.some(g=>g.label==='Панельная группа'));
    await page.locator('.c-dim').getByRole('button',{name:'50%',exact:true}).click();await page.waitForFunction(()=>[1,2].every(id=>state.simulation[id].dim===50));
   });
   await check('multiple-fixtures-motion-and-unsupported-explanation',async()=>{
    await pick([1,2]);await page.getByRole('button',{name:'Движение',exact:true}).click();await page.getByRole('button',{name:'Положение',exact:true}).click();
    for(const axis of ['Pan','Tilt']){const slider=page.getByRole('slider',{name:axis+' — абсолютное положение',exact:true});await slider.focus();await slider.press('Home');await slider.press('ArrowRight');}
    await page.waitForFunction(()=>[1,2].every(id=>state.simulation[id].pan<10&&state.simulation[id].tilt<10));
    const s=await control();for(const id of [1,2])assert(s.output[id].pan<10&&s.output[id].tilt<10);
    await pick([57]);const red=page.locator('.primary-colors').getByRole('button',{name:'Красный',exact:true});if(await red.count())assert(await red.isDisabled());assert.match(await page.locator('.ctl').textContent(),/не поддерживают.*цвет|нет смешения цвета/);
   });
   await check('reimport-reconnect-and-restart-preserve-data',async()=>{
    const before=(await control()).config;
    await nav('prepare');await page.getByRole('button',{name:'Подключение и синхронизация',exact:true}).click();await page.getByRole('button',{name:'Получить снова',exact:true}).click();
    await page.waitForFunction(()=>Object.keys(state.config.dmx_map||{}).length===3&&Object.values(state.config.dmx_map).every(p=>!p.stale));
    assert.deepEqual((await control()).config.groups,before.groups);assert.deepEqual((await control()).config.ma2groups,before.ma2groups);
    const cutoff=(await control()).received.length;await control('disconnect');await page.waitForFunction(()=>!connected());await control('connect');await page.waitForFunction(()=>connected());
    await page.waitForFunction(()=>Object.keys(state.config.dmx_map||{}).length===3&&Object.values(state.config.dmx_map).every(p=>!p.stale));
    const after=await control();assert(after.received.slice(cutoff).every(c=>after.read_only.includes(c)),'reconnect must never replay light');
    const instance=after.instance;await control('restart');for(let n=0;n<150;n++){await new Promise(r=>setTimeout(r,100));try{if((await control()).instance!==instance)break;}catch{}}
    await page.reload();await page.waitForFunction(()=>connected()&&Object.keys(state.config.dmx_map||{}).length===3&&Object.values(state.config.dmx_map).every(p=>!p.stale));assert.deepEqual((await control()).config.groups,before.groups);
    await pick([1]);await page.locator('.c-dim').getByRole('button',{name:'25%',exact:true}).click();await page.waitForFunction(()=>state.simulation[1].dim===25);
   });
   await check('all-tools-hidden-locally-and-persisted',async()=>{
    await page.goto(url+'/settings.html');await page.locator('[data-tool="strobe"]').uncheck();
    await page.goto(url);await page.waitForFunction(()=>connected());await pick([1]);assert.equal(await page.locator('.c-strobe').count(),0);assert(await page.locator('.c-dim').isVisible());
    await page.goto(url+'/settings.html');for(const key of ['zoom','focus'])await page.locator(`[data-tool="${key}"]`).uncheck();
    await page.goto(url);await page.waitForFunction(()=>connected());await pick([1]);await page.getByRole('button',{name:'Движение',exact:true}).click();
    assert.equal(await page.locator('.move-optics .move-slider:visible').count(),0);
    await page.goto(url+'/settings.html');
    for(const key of ['dim','color','pos','zoom','focus'])await page.locator(`[data-tool="${key}"]`).uncheck();
    await page.reload();for(const key of ['strobe','dim','color','pos','zoom','focus'])assert.equal(await page.locator(`[data-tool="${key}"]`).isChecked(),false);
    await page.goto(url);await page.waitForFunction(()=>connected());await pick([1]);
    assert.equal(await page.getByRole('button',{name:'Движение',exact:true}).count(),0);
    for(const selector of ['.c-strobe','.c-dim','.c-color','.c-pos'])assert.equal(await page.locator(selector).count(),0);
    const s=await control();assert.equal(s.config.dmx_map['1 Profile A']?.r,2,'Confirmed RGB channel is missing');assert.equal(Object.keys(s.config.dmx_map).length,3);assert(s.config.dmx_map['1 Profile A'].has.includes('strobe'));
    await page.goto(url+'/settings.html');await page.getByRole('button',{name:'Показать все инструменты',exact:true}).click();await page.goto(url);await page.waitForFunction(()=>connected());await pick([1]);
    assert(await page.locator('.c-strobe').isVisible());assert(await page.locator('.c-color').isVisible());
   });
   await check('plan-selection-scenes-and-tablet-layout',async()=>{
    await page.waitForFunction(()=>Object.keys(state.config.dmx_map||{}).length===3&&Object.values(state.config.dmx_map).every(p=>!p.stale));
    await nav('prepare');await page.getByRole('button',{name:'План зала и группы',exact:true}).click();
    // Imported fixtures receive positions through the actual editor, never seeded config.
    await page.getByRole('button',{name:'Создать схему и начать расстановку',exact:true}).click();
    for(const id of [1,2]){
     const hall=page.locator('.hall'),bounds=await hall.boundingBox();assert(bounds&&bounds.width>0&&bounds.height>0);await hall.click({position:{x:bounds.width*(.3+id*.15),y:bounds.height*(.45+id*.08)}});
     await page.waitForFunction(id=>typeof state.config.fixtures.find(f=>f.id===id).x==='number',id);
    }
    await nav('light');await page.getByRole('button',{name:'План',exact:true}).click();await page.locator('.hall .fx[data-id="2"]').click();
    await page.waitForFunction(()=>state.selection.includes(2));
    for(const size of [{width:1366,height:768},{width:1024,height:768},{width:768,height:1024}]){await page.setViewportSize(size);await page.locator('#page').evaluate(el=>el.scrollTop=0);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert(await page.locator('.target-bar').getByRole('button',{name:'Снять выбор',exact:true}).isVisible());await page.screenshot({path:path.join(out,engine+'-'+size.width+'.png')});}
    await nav('scenes');assert.equal(await page.locator('.hall').count(),0);assert.equal(await page.locator('.live-plan').count(),0);
    assert.deepEqual(errors,[]);
   });
  }catch(e){await page.screenshot({path:path.join(out,engine+'-failure.png')}).catch(()=>{});throw e;}
  finally{await browser.close();fs.writeFileSync(path.join(out,'scenarios.json'),JSON.stringify(results,null,2));}
 }
 console.log(JSON.stringify({profile:'field-start',passed:results.length,engines:['chromium','webkit']}));
})().catch(e=>{console.error(e);process.exitCode=1;});
