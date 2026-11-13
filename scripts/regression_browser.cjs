'use strict';
// No mocked receive(), route.fulfill() or HTTP-success-only action checks.
const assert = require('node:assert/strict'), fs=require('node:fs'), path=require('node:path');
const {chromium,webkit}=require('./browser_smoke/node_modules/playwright');
const [url,,out]=process.argv.slice(2), profile=process.env.MA2_TEST_PROFILE;
assert(['localhost','127.0.0.1'].includes(new URL(url).hostname));
const results=[];
const headers={'x-ma2-test':process.env.MA2_TEST_TOKEN};
(async()=>{
 for(const [engine,type] of Object.entries({chromium,webkit})){
  const browser=await type.launch();
  const context=await browser.newContext({viewport:{width:1366,height:768},hasTouch:true});
  const page=await context.newPage(), errors=[];
  page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));
  let promptReply='';
  page.on('dialog',d=>d.accept(d.type()==='prompt'?promptReply:undefined));
  async function control(mode){const response=mode?await context.request.post(url+'/__quality/control',{headers,data:{mode}}):await context.request.get(url+'/__quality/control',{headers});assert(response.ok());return response.json();}
  async function check(name,fn){try{await fn();results.push({engine,profile,name,status:'success',evidence:'isolated mock, not physical MA2'});}catch(e){results.push({engine,profile,name,status:'failure',error:e.message});throw e;}}
  async function output(id,dim,rgb){
   await page.waitForFunction(({id,dim,rgb})=>{const v=state.simulation?.[id];return v&&Math.abs(v.dim-dim)<.1&&(!rgb||v.rgb.every((x,i)=>Math.abs(x-rgb[i])<.1));},{id,dim,rgb});
   const backend=await control();assert(Math.abs(backend.output[id].dim-dim)<.1,JSON.stringify({id,expected:dim,backend:backend.output[id],browser:await page.evaluate(id=>state.simulation[id],id)}));
   if(rgb)assert.deepEqual(backend.output[id].rgb,rgb);
   assert.equal(await page.evaluate(()=>state.valuesMeta.live.source),'unknown','simulation never becomes real readback');
  }
  async function nav(section){await page.locator(`#rail [data-sec="${section}"]`).click();}
  async function select(ids){
   await nav('light');
   if(await page.evaluate(()=>state.selection.length)){await page.getByRole('button',{name:'Группы',exact:true}).click();await page.locator('.target-bar').getByRole('button',{name:'Снять выбор',exact:true}).click();}
   await page.getByRole('button',{name:'План',exact:true}).click();
   for(const id of ids)await page.locator(`.hall .fx[data-id="${id}"]`).click();
   await page.waitForFunction(ids=>JSON.stringify(state.selection.slice().sort((a,b)=>a-b))===JSON.stringify(ids),ids.slice().sort((a,b)=>a-b));
  }
  async function save(label){
   await page.getByRole('button',{name:'Сохранить сцену',exact:true}).click();
   await page.locator('#store-name').fill(label);
   await page.getByRole('button',{name:'Найти место',exact:true}).click();
   await page.getByRole('button',{name:'Записать',exact:true}).click();
   await page.waitForFunction(label=>state.config.scenes.some(s=>s.label===label),label);
   return page.evaluate(label=>state.config.scenes.find(s=>s.label===label).id,label);
  }
  async function go(id){await nav('scenes');await page.locator(`button.tile[data-scene="${id}"]`).click();}
  try{
   if(engine==='webkit'){
    // Browser contexts isolate localStorage, not backend layout/groups/scenes.
    const previous=(await control()).instance;await control('reset');let fresh=false;
    for(let n=0;n<150;n++){await new Promise(r=>setTimeout(r,100));try{if((await control()).instance!==previous){fresh=true;break;}}catch{}}
    assert(fresh,'fresh fixture profile did not start for the second engine');
   }
   await page.goto(url);await page.waitForFunction(()=>connected()&&state.mock);
   if(profile==='synthetic')await page.waitForFunction(()=>Object.keys(state.config.dmx_map||{}).length===3&&Object.values(state.config.dmx_map).every(p=>!p.stale));
   if(profile==='clean'){
    await check('first-run-empty',async()=>{const s=await control();assert.deepEqual(s.config.fixtures,[]);assert.deepEqual(s.config.groups,[]);assert.deepEqual(s.config.scenes,[]);assert.equal(s.safety_mode,'test','fresh install must retain safe template permissions');});
    await check('first-run-wizard',async()=>{
     await page.goto(url+'/setup.html');await page.locator('#setup-save').waitFor();
     for(const size of [{width:1366,height:768},{width:1024,height:768}]){await page.setViewportSize(size);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));}
     await page.locator('#setup-save').click();await page.locator('#setup-restart').waitFor({state:'visible'});
     assert.match(await page.locator('#setup-saved').textContent(),/сохранены/i);
     assert.equal((await control()).safety_mode,'test','wizard must not enable full access');
    });
   }else if(profile==='field-v2'){
    await check('real-v2-patch-import',async()=>{
     assert.deepEqual((await control()).config.fixtures,[], 'V2 must also begin without imported fixtures');
     await nav('prepare');await page.getByRole('button',{name:'Шоу',exact:true}).click();
     await page.getByRole('button',{name:/^Привязать план к «/}).click();
     await page.waitForFunction(()=>state.config.show===state.show.name);
     await nav('prepare');await page.getByRole('button',{name:'Подключение и синхронизация',exact:true}).click();
     await page.getByRole('button',{name:'Получить оборудование из MA2',exact:true}).click();
     await page.waitForFunction(()=>state.readFreshness.fixtures===true);
     const fixtures=(await control()).config.fixtures;
     assert.equal(fixtures.length,24);assert.equal(fixtures.find(f=>f.id===1).address,'1.200');assert.equal(fixtures.find(f=>f.id===30).address,'1.360');
     assert.equal(await page.evaluate(()=>state.show.name),'big room v2');
    });
   }else{
    await check('correct-show-and-patch',async()=>{assert.equal(await page.evaluate(()=>state.show.name),'Mock show');const s=await control();assert.equal(s.config.fixtures.length,60);assert(s.config.fixtures.every(f=>f.address));});
    await check('import-console-groups-through-ui',async()=>{
     assert.deepEqual((await control()).config.ma2groups,[], 'panel must start without imported console groups');
     await nav('prepare');await page.getByRole('button',{name:'Подключение и синхронизация',exact:true}).click();
     await page.getByRole('button',{name:'Прочитать из MA2',exact:true}).click();
     await page.waitForFunction(()=>state.ma2read?.ok===true&&state.ma2read.groups.length>0);
     assert.deepEqual((await control()).config.ma2groups,[], 'reading must not silently import');
     await page.getByRole('button',{name:'Добавить отмеченное',exact:true}).click();
     await page.waitForFunction(()=>state.config.ma2groups?.length===2);
     const imported=(await control()).config.ma2groups;
     assert.deepEqual(imported.map(g=>[g.n,g.ids]),[[1,[1,2]],[2,[55,56]]]);
     assert.deepEqual((await control()).config.groups[0].fixtures,[1,2,3]);
     await nav('light');await page.getByRole('button',{name:'Группы',exact:true}).click();
     await page.locator('.pick').getByText('Фронт',{exact:true}).click();
     await page.waitForFunction(()=>JSON.stringify(state.selection)==='[1,2,3]');
     await page.locator('.c-dim').getByRole('button',{name:'25%',exact:true}).click();
     for(const id of [1,2,3])await output(id,25);
     await page.getByRole('button',{name:'Группы',exact:true}).click();
     promptReply='QA-'+engine+'-group';await page.getByRole('button',{name:'Группа из выбранных (3)',exact:true}).click();
     await page.waitForFunction(label=>state.config.groups.some(g=>g.label===label),promptReply);promptReply='';
     await page.getByText('Фронт MA2',{exact:true}).click();
     await page.waitForFunction(()=>JSON.stringify(state.selection)==='[1,2]');
     let groupBefore;for(let n=0;n<100;n++){groupBefore=await control();if(JSON.stringify(groupBefore.selection)==='[1,2]')break;await page.waitForTimeout(20);}assert.deepEqual(groupBefore.selection,[1,2]);
     await page.locator('.c-dim').getByRole('button',{name:'50%',exact:true}).click();
     for(const id of [1,2])await output(id,50);await output(3,25);
     const groupAfter=await control();for(const [id,values] of Object.entries(groupBefore.output))if(!['1','2'].includes(id))assert.deepEqual(groupAfter.output[id],values);
    });
    await check('selection-plan-clear-and-single-output',async()=>{
     const unselected=(await control()).output[2];
     await select([1]);
     await page.locator('.c-dim').getByRole('button',{name:'100%',exact:true}).click();
     const red=page.locator('.primary-colors').getByRole('button',{name:'Красный',exact:true});assert(await red.isEnabled(),'compatible RGB control unavailable');await red.click();
     await output(1,100,[100,0,0]);assert.deepEqual((await control()).output[2],unselected);
     await page.waitForFunction(()=>document.querySelector('.hall .fx[data-id="1"]').classList.contains('lit'));
     assert.match(await page.locator('.hall .fx[data-id="1"] .g').evaluate(el=>getComputedStyle(el).backgroundColor),/255, 0, 0/);
     await page.getByRole('button',{name:'Группы',exact:true}).click();await page.locator('.target-bar').getByRole('button',{name:'Снять выбор',exact:true}).click();await page.waitForFunction(()=>state.selection.length===0);
     await output(1,100,[100,0,0]);
    });
    await check('multiple-heads-pan-tilt',async()=>{
     await select([1,2]);await page.getByRole('button',{name:'Движение',exact:true}).click();await page.getByRole('button',{name:'Положение',exact:true}).click();
     for(const axis of ['Pan','Tilt']){const slider=page.getByRole('slider',{name:axis+' — абсолютное положение',exact:true});assert(await slider.isEnabled());await slider.focus();await slider.press('Home');await slider.press('ArrowRight');}
     await page.waitForFunction(()=>[1,2].every(id=>state.simulation[id].pan<10&&state.simulation[id].tilt<10));
     const s=await control();for(const id of [1,2]){assert(s.output[id].pan<10);assert(s.output[id].tilt<10);}assert.equal(s.output[3].pan,50);
    });
    let a,b;
    await check('store-two-scenes-and-output',async()=>{
     await select([1]);await page.locator('.control-tabs').getByRole('button',{name:'Свет',exact:true}).click();
     const dim=page.locator('.c-dim');
     await dim.getByRole('button',{name:'100%',exact:true}).click();await page.locator('.primary-colors').getByRole('button',{name:'Красный',exact:true}).click();await output(1,100,[100,0,0]);
     a=await save('QA-'+engine+'-A');
     await page.locator('.primary-colors').getByRole('button',{name:'Синий',exact:true}).click();await dim.getByRole('button',{name:'50%',exact:true}).click();await output(1,50,[0,0,100]);
     b=await save('QA-'+engine+'-B');
     const commands=(await control()).received;assert(commands.filter(c=>/^Store Executor \d+\.\d+ Cue 1 \/Source=Output \/Use=Allforselected$/.test(c)).length>=2);
    });
    await check('scene-go-A-B-A-and-blackout-restore',async()=>{
     // Native playback preserves Programmer. The console operator releases it explicitly.
     await control('clear-programmer');
     await go(a);await output(1,100,[100,0,0]);await go(b);await output(1,50,[0,0,100]);await go(a);await output(1,100,[100,0,0]);
     const beforeBlackout=(await control()).output[1];
     const blackoutCutoff=(await control()).received.length;
     await page.locator('#blackout').click();await page.waitForFunction(()=>state.blackout.phase==='active');await output(1,0);
     assert.equal((await control()).received.slice(blackoutCutoff).filter(c=>c==='SpecialMaster 2.1 At 0').length,1);
     await page.locator('#blackout').click();await page.waitForFunction(()=>state.blackout.phase==='idle');await output(1,beforeBlackout.dim,beforeBlackout.rgb);
     await go(b);await output(1,50,[0,0,100]);
    });
    await check('scene-fade-intermediate-output',async()=>{
     await page.getByRole('button',{name:'2 с',exact:true}).click();
     await go(a);
     await page.waitForFunction(()=>state.simulation[1].dim>50.1&&state.simulation[1].dim<99.9);
     await output(1,100,[100,0,0]);
     await page.getByRole('button',{name:'Сразу',exact:true}).click();
    });
    await check('external-console-change',async()=>{await control('external');await output(1,17);});
    await check('disconnect-reconnect-without-action-replay',async()=>{
     const before=(await control()).received.length;
     await control('disconnect');await page.waitForFunction(()=>!connected());assert(await page.locator('#blackout').isDisabled());
     await control('connect');await page.waitForFunction(()=>connected());
     await page.waitForFunction(()=>Object.keys(state.config.dmx_map||{}).length===3);
     const after=await control();
     assert.deepEqual(after.received.slice(before).filter(c=>!after.read_only.includes(c)),[], 'every reconnect command must be explicitly read-only');
    });
    await check('save-layout-through-editor',async()=>{
     const original=(await control()).config.fixtures.find(f=>f.id===1);
     await nav('prepare');await page.getByRole('button',{name:'План зала и группы',exact:true}).click();
     const fixture=page.locator('.hall .fx[data-id="1"]'),hall=page.locator('.hall');
     const bounds=await hall.boundingBox(),hit=await fixture.boundingBox();assert(bounds&&hit&&bounds.width>0&&bounds.height>0);
     // Dense public editor: neighbouring 52px targets overlap; use fixture 1 exposed left edge.
     await fixture.dragTo(hall,{sourcePosition:{x:8,y:hit.height/2},targetPosition:{x:bounds.width*.6,y:bounds.height*.6}});
     await page.waitForFunction(({x,y})=>{const f=state.config.fixtures.find(f=>f.id===1);return f.x!==x||f.y!==y;},{x:original.x,y:original.y});
     const moved=(await control()).config.fixtures.find(f=>f.id===1);
     assert.notDeepEqual([moved.x,moved.y],[original.x,original.y]);
    });
    await check('reload-and-real-process-restart-preserve-panel-data',async()=>{
     const saved=(await control()).config;await page.reload();await page.waitForFunction(()=>connected());
     assert.deepEqual((await control()).config.groups,saved.groups);
     const previous=(await control()).instance;await control('restart');
     let restarted=false;
     for(let n=0;n<150;n++){await new Promise(r=>setTimeout(r,100));try{if((await control()).instance!==previous){restarted=true;break;}}catch{}}
     assert(restarted,'new bridge process did not become ready');
     await page.reload();await page.waitForFunction(()=>connected());const after=await control();assert.notEqual(after.instance,previous);
     for(const key of ['groups','ma2groups','scenes'])assert.deepEqual(after.config[key],saved[key]);
     assert.deepEqual(after.config.fixtures.map(f=>[f.id,f.x,f.y]),saved.fixtures.map(f=>[f.id,f.x,f.y]));
    });
    await check('scenes-without-hall',async()=>{await nav('scenes');assert.equal(await page.locator('.hall').count(),0);});
    await check('laptop-and-tablet-layout',async()=>{
     await nav('light');await page.getByRole('button',{name:'Группы',exact:true}).click();
     if(await page.locator('.target-bar').getByRole('button',{name:'Снять выбор',exact:true}).isEnabled())await page.locator('.target-bar').getByRole('button',{name:'Снять выбор',exact:true}).click();
     await page.getByRole('button',{name:'Приборы',exact:true}).click();
     await page.locator('.fixture-row').filter({has:page.locator('.id',{hasText:/^1$/})}).click();

     await page.waitForFunction(()=>JSON.stringify(state.selection)==='[1]');
     for(const size of [{width:1366,height:768},{width:1024,height:768},{width:768,height:1024}]){
      await page.setViewportSize(size);
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      const color=page.locator('.primary-colors').getByRole('button',{name:'Красный',exact:true});assert(await color.isEnabled());await color.scrollIntoViewIfNeeded();
      const box=await color.boundingBox();assert(box.x>=0&&box.y>=0&&box.x+box.width<=size.width+1&&box.y+box.height<=size.height+1);
      await page.screenshot({path:path.join(out,engine+'-'+size.width+'.png')});
     }
    });
   }
   await check('passive-diagnostics-preview-and-download',async()=>{
    const before=(await control()).received.filter(c=>!c.startsWith('List'));
    await page.goto(url+'/diag.html');await page.locator('#quality-checks li').first().waitFor();
    await page.locator('#testing-preview').click();await page.locator('#testing-download').waitFor({state:'visible'});
    assert.match(await page.locator('#testing-preview-content').textContent(),/SHA256/);
    const response=await context.request.get(url+await page.locator('#testing-download').getAttribute('href'));assert(response.ok());assert((await response.body()).length>100);
    assert.deepEqual((await control()).received.filter(c=>!c.startsWith('List')),before);
    await page.screenshot({path:path.join(out,engine+'-diagnostics.png')});
   });
   assert.deepEqual(errors,[]);
  }catch(e){await page.screenshot({path:path.join(out,engine+'-failure.png')}).catch(()=>{});throw e;}
  finally{await browser.close();fs.writeFileSync(path.join(out,'scenarios.json'),JSON.stringify(results,null,2));}
 }
 console.log(JSON.stringify({profile,passed:results.length,engines:['chromium','webkit']}));
})().catch(e=>{console.error(e);process.exitCode=1;});
