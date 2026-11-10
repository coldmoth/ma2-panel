/* Actual browser + isolated mock. Synthetic readback is explicitly injected where noted. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const pw=require('./browser_smoke/node_modules/playwright');
const [url,,output]=process.argv.slice(2),results=[];
(async()=>{
 for(const engine of ['chromium','webkit']){
  const browser=await pw[engine].launch({headless:true});
  try{
   const ctx=await browser.newContext({viewport:{width:1366,height:768},hasTouch:true});
   const page=await ctx.newPage(),errors=[],frames=[];
   page.setDefaultTimeout(10000);
   page.on('pageerror',e=>errors.push(e.stack));
   page.on('websocket',s=>s.on('framesent',e=>{try{frames.push(JSON.parse(e.payload));}catch{}}));
   await page.goto(url);await page.waitForFunction(()=>connected() && state.config);
   await page.evaluate(()=>{window.originalConfig=JSON.parse(JSON.stringify(state.config));});
   const scene=page.locator('.tile[data-scene="smoke-scene"]');
   await scene.tap();
   await page.waitForFunction(()=>!busy('scene_go'));
   assert(frames.some(a=>a.a==='scene_go'&&a.id==='smoke-scene'),'manual scene command');
   const count=frames.filter(a=>a.a==='scene_go').length;
   await page.waitForTimeout(400);
   assert.equal(frames.filter(a=>a.a==='scene_go').length,count,'no automatic scene changes');
   const fade=page.getByRole('spinbutton',{name:'Время перехода, секунды'});
   await fade.fill('5');await fade.press('Tab');
   await scene.tap();await page.waitForFunction(()=>!busy('scene_go'));
   assert.equal(frames.filter(a=>a.a==='scene_go').at(-1).fade,5);

   // New scene: select fixtures, then real slot offer/token and output Store from mock backend.
   await page.locator('.live-plan .fx[data-id="1"]').tap();
   await page.waitForFunction(()=>state.selection.includes(1)&&!busy('select_fixtures'));
   await page.getByRole('button',{name:'Сохранить сцену',exact:true}).first().tap();
   await page.getByLabel('Название',{exact:true}).fill('Сцена '+engine);
   await page.getByRole('button',{name:'Найти место',exact:true}).tap();
   await page.getByRole('button',{name:'Записать',exact:true}).waitFor({state:'visible'});
   await page.getByRole('button',{name:'Записать',exact:true}).tap();
   await page.waitForFunction(()=>!busy('scene_create')&&!document.getElementById('dlg').open);
   assert(await page.locator('.scene-name').filter({hasText:'Сцена '+engine}).count(),'created scene appears');
   const created=await page.evaluate(name=>state.config.scenes.find(s=>s.label===name),'Сцена '+engine);
   await page.locator('.tile[data-scene="'+created.id+'"]').tap();await page.waitForFunction(()=>!busy('scene_go'));
   await page.getByRole('button',{name:'Изменить сцены',exact:true}).tap();
   await page.locator('.tile-wrap').filter({has:page.locator('.tile[data-scene="'+created.id+'"]')}).getByRole('button',{name:'Изменить',exact:true}).tap();
   page.once('dialog',d=>d.accept());
   await page.getByRole('button',{name:'Перезаписать текущим светом',exact:true}).tap();
   await page.waitForFunction(()=>!busy('scene_create')&&!document.getElementById('dlg').open);
   assert(frames.some(a=>a.a==='scene_create'&&a.replace===true),'rewrite is explicit');
   await page.getByRole('button',{name:'К исполнению',exact:true}).tap();

   // Controlled input/readback fixture: backend fixture 1 remains the real command target.
   await page.evaluate(()=>{
    const cfg=JSON.parse(JSON.stringify(state.config));
    cfg.fixtures=[{id:1,label:'Фронт',type:'RGB head',color:'rgb',moves:true,x:.35,y:.4,params:['Dimmer','ColorRGB_Red','ColorRGB_Green','ColorRGB_Blue','Pan','Tilt','Zoom','Focus','Strobe']}];
    receive({config:cfg});selectFixtures([1]);
   });
   await page.waitForFunction(()=>!busy('select_fixtures'));
   await page.getByRole('button',{name:'Красный',exact:true}).tap();
   for(let i=0;i<50&&!frames.some(a=>a.a==='color');i++) await page.waitForTimeout(20);
   assert.equal(frames.filter(a=>a.a==='color').at(-1).fade,5,'same Fade applies to colour');
   const lightConfig=await page.evaluate(()=>JSON.parse(JSON.stringify(state.config)));
   async function measured(dim,rgb=[100,0,0],freshness='fresh'){
    await page.evaluate(({dim,rgb,freshness})=>receive({live:{1:{dim,rgb}},values_meta:{live:{source:'ma2',freshness,updated_at:Date.now()/1000}}}),{dim,rgb,freshness});
   }
   await measured(20);
   assert(await page.locator('.live-plan .fx.lit').count(),'fresh measured light is visible');
   await measured(80,[0,0,100]);
   assert.match(await page.locator('.c-color').innerText(),/B 100/);
   await measured(100,[0,0,0]);
   assert.equal(await page.locator('.live-plan .fx.lit').count(),0,'confirmed RGB zero stays dark at Dimmer 100');
   assert.match(await page.locator('.c-dim').innerText(),/100%/,'measured dimmer is unchanged');
   await measured(0);
   assert.equal(await page.locator('.live-plan .fx.lit').count(),0,'measured zero is dark');
   await measured(80,[0,100,0],'stale');
   assert.equal(await page.locator('.live-plan .fx.lit').count(),0,'stale cannot glow');
   await measured(80,[0,100,0],'unknown');
   assert.equal(await page.locator('.live-plan .fx.lit').count(),0,'unknown cannot glow');

   // Native pointer gesture survives both incoming values and a changed config revision.
   const dim=page.getByRole('slider',{name:'Яркость',exact:true});await dim.scrollIntoViewIfNeeded();
   const box=await dim.boundingBox();
   await page.mouse.move(box.x+box.width*.73,box.y+box.height/2);await page.mouse.down();
   const before=await dim.inputValue();
   await page.evaluate(()=>{window.dragNode=document.querySelector('.c-dim input');const config=JSON.parse(JSON.stringify(state.config));config.revision+='-external';receive({config,live:{1:{dim:12,rgb:[0,100,0]}}});});
   await measured(12);
   assert(await dim.evaluate(el=>el===window.dragNode),'WS retains native pointer target');
   assert.equal(await dim.inputValue(),before,'WS does not move held thumb');
   await page.mouse.up();await page.waitForTimeout(150);
   // Restore actual server revision before further real commands.
   await page.evaluate(config=>receive({config}),lightConfig);

   // A text draft remains in its dialog while the rest of the UI updates.
   await page.getByRole('button',{name:'Сохранить сцену',exact:true}).first().tap();
   const name=page.getByLabel('Название',{exact:true});await name.fill('Не терять имя');
   await measured(35,[0,100,0]);
   assert.equal(await name.inputValue(),'Не терять имя');
   assert(await page.locator('.live-plan .fx.lit').count());
   // Inject an unknown outcome tied to a genuine pending request, with no write sent.
   await page.evaluate(()=>{
    const button=document.querySelector('#dlg button');const id='test:unknown';
    pending[id]={a:'scene_create',button,serial:999,label:'Сохранение сцены'};
    receive({ok:true,a:'scene_create',request_id:id,outcome:'unknown',command_evidence:['unknown']});
   });
   assert(await page.locator('#dlg').evaluate(d=>d.open));
   assert.equal(await name.inputValue(),'Не терять имя');
   assert.match(await page.locator('#dlg').innerText(),/неизвестен/);
   await page.getByRole('button',{name:'Отмена',exact:true}).tap();

   // Actual second client changes the config; stale revision is refused by the backend.
   const other=await ctx.newPage();await other.goto(url);await other.waitForFunction(()=>connected()&&state.config);
   const staleRevision=await page.evaluate(()=>state.config.revision);
   await other.evaluate(engine=>send({a:'scene_rename',id:'smoke-scene',label:'Другая вкладка '+engine}),engine);
   await other.waitForFunction(()=>!busy('scene_rename'));
   await page.waitForFunction(()=>state.config.scenes.some(s=>s.label.startsWith('Другая вкладка')));
   await page.evaluate(rev=>send({a:'scene_rename',id:'smoke-scene',label:'Старая правка',config_revision:rev}),staleRevision);
   await page.waitForFunction(()=>!busy('scene_rename'));
   assert.match(await page.locator('#errors').innerText(),/изменён другим клиентом|верси/i);
   assert.equal(await page.evaluate(()=>state.config.scenes.find(s=>s.id==='smoke-scene').label),'Другая вкладка '+engine);
   await other.close();

   await page.locator('#errors button').evaluateAll(buttons=>buttons.forEach(button=>button.click()));
   // Dense plan/long names exercise the actual responsive layout; values are controlled.
   await page.evaluate(()=>{
    const cfg=JSON.parse(JSON.stringify(state.config));
    cfg.fixtures=Array.from({length:24},(_,i)=>({id:i+1,label:'Прибор '+(i+1),type:'RGB',color:'rgb',params:['Dimmer','ColorRGB_Red','ColorRGB_Green','ColorRGB_Blue'],x:.1+(i%6)*.16,y:.15+Math.floor(i/6)*.2}));
    cfg.scenes=Array.from({length:12},(_,i)=>({id:'layout'+i,exec:'1.'+(i+1),label:'Сцена '+(i+1)+' — солист и группа'}));
    receive({config:cfg});state.selection=[1];render();
   });
   for(const [width,height] of [[1920,1080],[1366,768],[1024,768],[768,1024]]){
    await page.setViewportSize({width,height});await page.evaluate(()=>go('scenes'));await page.locator('#page').evaluate(el=>el.scrollTop=0);await page.waitForTimeout(120);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'no page overflow '+width);
    assert(await page.locator('#page').evaluate(el=>el.scrollWidth<=el.clientWidth+1),'no workspace overflow '+width);
    for(const id of ['halt','blackout']){const r=await page.locator('#'+id).boundingBox();assert(r.x>=0&&r.y>=0&&r.x+r.width<=width+1&&r.y+r.height<=height+1,id+' accessible');}
    const r=await page.locator('.tile').first().boundingBox();assert(r.width>=44&&r.height>=44);
    assert(r.y>=0&&r.y<height,'first scene remains visible beside the plan '+width);
    const planBox=await page.locator('.live-plan').boundingBox();assert(planBox && planBox.width>200 && planBox.y<height,'working plan is visible '+width);
    await page.locator('.scene-list').evaluate(el=>el.scrollTop=100);
    const scrollBefore=await page.locator('.scene-list').evaluate(el=>el.scrollTop);
    await page.evaluate(()=>{selectFixtures([]);selectFixtures([1]);});
    assert.equal(await page.locator('.scene-list').evaluate(el=>el.scrollTop),scrollBefore,'target change preserves the scene list position');
    await page.locator('.scene-list').evaluate(el=>el.scrollTop=0);
    await page.screenshot({path:path.join(output,engine+'-'+width+'x'+height+'.png'),fullPage:true});
    await page.locator('#rail [data-sec=light]').tap();
    assert(await page.locator('.live-plan').count());
    assert(await page.evaluate(()=>document.querySelector('#page').scrollWidth<=document.querySelector('#page').clientWidth+1));
    results.push({engine,width,height,layout:'pass'});
   }
   // Touch selects on the always-visible plan; no modal or hover is needed.
   await page.locator('.live-plan .fx[data-id="1"]').scrollIntoViewIfNeeded();
   await page.locator('.live-plan .fx[data-id="1"]').tap();
   assert.deepEqual(await page.evaluate(()=>state.selection),[]);
   await page.locator('.live-plan .fx[data-id="1"]').tap();assert.deepEqual(await page.evaluate(()=>state.selection),[1]);
   await page.evaluate(()=>{receive({config:originalConfig});go('scenes');});
   const bo=page.locator('#blackout'),beforeBO=frames.filter(a=>a.a==='blackout').length;
   await bo.tap();
   await page.waitForFunction(()=>!busy('blackout'));assert.equal(frames.filter(a=>a.a==='blackout').length,beforeBO+1);
   // Offline must clear measured light, pending gestures and expose reconnect status.
   await ctx.setOffline(true);await page.evaluate(()=>state.ws.close());
   await page.waitForFunction(()=>!connected() && document.getElementById('blackout').disabled);
   assert(await bo.isDisabled());assert.equal(await page.locator('.live-plan .fx.lit').count(),0);
   assert.match(await page.locator('#top-link').innerText(),/Нет связи/);
   assert.deepEqual(errors,[],'no browser errors');
   await ctx.close();
  }finally{await browser.close();}
 }
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(results,null,2));
 console.log('stage3 Chromium/WebKit PASS: scenes, shared Fade, store/rewrite/unknown, live/stale/unknown, WS+drag/text, real client conflict, 4 viewports, touch, Blackout, disconnect');
})().catch(e=>{console.error(e);process.exitCode=1;});
