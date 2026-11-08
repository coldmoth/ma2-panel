/* Run via scripts/browser_smoke.py: copied data, isolated --mock, own process only. */
'use strict';
const assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path');
const playwright=require('./browser_smoke/node_modules/playwright');
const [url,,output]=process.argv.slice(2);
const results=[];
(async()=>{
 for(const engine of ['chromium','webkit']){
  const browser=await playwright[engine].launch({headless:true});
  try{
   const context=await browser.newContext({viewport:{width:1440,height:900},hasTouch:true});
   const page=await context.newPage(),errors=[],frames=[];
   page.setDefaultTimeout(12000);
   page.on('pageerror',e=>errors.push(e.message));
   page.on('websocket',s=>s.on('framesent',e=>{try{frames.push(JSON.parse(e.payload));}catch{}}));
   await page.goto(url);await page.waitForFunction(()=>connected());
   await page.evaluate(()=>{
    const config=JSON.parse(JSON.stringify(state.config));
    config.fixtures=Array.from({length:24},(_,i)=>({id:i+1,label:'Сценический прибор '+(i+1),type:'PAR',x:(i%8)/7,y:Math.floor(i/8)/2}));
    receive({config});go('light');lightUI.tab='plan';lightUI.picking=true;render();
   });
   const viewport=page.locator('.plan-viewport'), fit=page.getByRole('button',{name:'Вписать',exact:true});
   const zoom=page.getByRole('button',{name:'Увеличить план',exact:true});
   async function settled(){await page.waitForTimeout(180);}
   async function check(name){
    await settled();
    const geometry=await page.evaluate(()=>{
     const wrap=document.querySelector('.plan-viewport'),r=wrap.getBoundingClientRect();
     const buttons=[...wrap.querySelectorAll('.fx')].map(b=>{const x=b.getBoundingClientRect();return {id:b.dataset.id,left:x.left,right:x.right,top:x.top,bottom:x.bottom,w:x.width,h:x.height};});
     const toolbar=document.querySelector('.plan-toolbar').getBoundingClientRect();
     const dialog=document.querySelector('.pick').getBoundingClientRect();
     const body=wrap.parentNode.getBoundingClientRect();
     return {bodyBottom:body.bottom,dialogBottom:dialog.bottom,r:{left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height},buttons,toolbarBottom:toolbar.bottom,overflow:document.documentElement.scrollWidth>innerWidth,auto:planView.auto,zoom:planView.zoom};
    });
    assert.equal(geometry.buttons.length,24,'all test fixtures remain present');
    assert(geometry.r.bottom<=geometry.bodyBottom+1,`${engine}/${name}: viewport clipped by body`);
    assert(!geometry.overflow,`${engine}/${name}: page overflow`);
    assert(geometry.auto && geometry.zoom===1,`${engine}/${name}: automatic fit`);
    assert(geometry.r.height>=80,`${engine}/${name}: visible viewport ${JSON.stringify(geometry.r)}`);
    assert(geometry.r.bottom<=geometry.dialogBottom+1,`${engine}/${name}: plan clipped by dialog`);
    assert(geometry.toolbarBottom<=geometry.r.top+1,`${engine}/${name}: toolbar overlaps`);
    for(const b of geometry.buttons){
     assert(b.w>=44 && b.h>=44,`${name}: hit target ${b.id}`);
     assert(b.left>=geometry.r.left-1 && b.right<=geometry.r.right+1 && b.top>=geometry.r.top-1 && b.bottom<=geometry.r.bottom+1,`${engine}/${name}: clipped ${JSON.stringify(b)} / ${JSON.stringify(geometry.r)}`);
    }
    await page.screenshot({path:path.join(output,`${engine}-${name}.png`),fullPage:true});
    results.push({engine,name,viewport:geometry.r});
   }
   const start=frames.length;
   for(const [name,width,height] of [['pc',1440,900],['tablet-landscape',1024,768],['tablet-portrait',768,1024],['phone-portrait',390,844],['phone-landscape',844,390]]){
    await page.setViewportSize({width,height});await check(name);
   }
   assert.equal(frames.length,start,'fit/orientation sends no commands');
   await page.setViewportSize({width:1024,height:768});await settled();
   for(let i=0;i<4;i++)await zoom.click();
   await viewport.evaluate(el=>{el.scrollLeft=80;el.scrollTop=110;});await settled();
   const manual=await page.evaluate(()=>({...planView}));
   assert(!manual.auto && manual.zoom>1);
   assert(manual.x>0 || manual.y>0,'manual view has a real scroll offset');
   // Both nonstructural status and full config broadcasts occur in normal operation.
   await page.evaluate(()=>{receive({live:{1:{dim:50}},status:{ma2:'logged_in'}});receive({config:JSON.parse(JSON.stringify(state.config))});});
   await settled();
   assert.deepEqual(await page.evaluate(()=>({...planView})),manual,'background broadcasts preserve manual view');
   await page.evaluate(()=>{go('scenes');go('light');});await settled();
   const reopened=await viewport.evaluate(el=>({x:el.scrollLeft,y:el.scrollTop}));
   assert(Math.abs(reopened.x-manual.x)<=1 && Math.abs(reopened.y-manual.y)<=1,'reopening restores offset');
   assert.equal(frames.length,start,'manual zoom/scroll/rebuild sends no commands');
   await fit.click();await check('fit-restored');
   await page.setViewportSize({width:768,height:1024});await check('fit-rotation');
   // Explicit fixture selection is the sole intended action in this section.
   await page.locator('.plan-viewport .fx[data-id="1"]').click();
   await page.waitForFunction(()=>state.selection.includes(1));await settled();
   assert.equal(await page.evaluate(()=>planView.auto),true,'selection retains auto');
   assert(frames.slice(start).some(a=>a.a==='select_fixtures'),'fixture selection works');
   assert(!frames.slice(start).some(a=>/highlight|layout_save/.test(a.a)),'navigation never highlights or moves fixtures');
   let selectedStart=frames.length;
   for(let i=0;i<3;i++)await zoom.click();
   await viewport.evaluate(el=>{el.scrollLeft=40;el.scrollTop=60;});await settled();
   const selectedView=await page.evaluate(()=>({...planView}));
   await page.evaluate(()=>receive({config:JSON.parse(JSON.stringify(state.config)),live:{1:{dim:80}}}));await settled();
   assert.deepEqual(await page.evaluate(()=>({...planView})),selectedView);
   await page.screenshot({path:path.join(output,`${engine}-manual-selected.png`),fullPage:true});
   assert.equal(frames.length,selectedStart,'background updates of selected fixture send nothing');
   // Selection rebuilds the dialog too; it must keep the manual view.
   await page.evaluate(()=>tapFixture(1,'control'));await settled();
   assert.deepEqual(await page.evaluate(()=>({...planView})),selectedView,'selection preserves manual zoom and scroll');
   assert.equal(frames.length,selectedStart+1,'only the explicit selection action is sent');
   selectedStart=frames.length;
   await fit.click();
   // Synthetic two-finger events execute the real browser handlers in both engines.
   const box=await viewport.boundingBox();
   for(const [type,id,x] of [['pointerdown',41,.4],['pointerdown',42,.6],['pointermove',42,.8],['pointerup',42,.8],['pointerup',41,.4]]){
    await viewport.dispatchEvent(type,{pointerId:id,pointerType:'touch',button:0,clientX:box.x+box.width*x,clientY:box.y+box.height*.5});
   }
   assert((await page.evaluate(()=>planView.zoom))>1,'two-finger pinch enlarges');
   assert.equal(frames.length,selectedStart,'pinch sends no selection or Highlight');
   await fit.click();
   // A single pan gesture must not select the fixture below it.
   await page.getByRole('button',{name:'Перемещение',exact:true}).click();
   const r=await viewport.boundingBox();
   await page.mouse.move(r.x+r.width*.5,r.y+r.height*.5);await page.mouse.down();await page.mouse.move(r.x+r.width*.7,r.y+r.height*.6);await page.mouse.up();
   await settled();assert.equal(frames.length,selectedStart,'pan gesture sends no commands');
   assert.deepEqual(errors,[],'browser errors');
   await context.close();
  }finally{await browser.close();}
 }
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(results,null,2));
 console.log('FIELD-04 Chromium/WebKit: PC/tablet/phone, rotations, fit/manual/reopen/background/selection/no Highlight PASS');
})().catch(e=>{console.error(e);process.exitCode=1;});
