'use strict';
const assert = require('node:assert/strict');
const path = require('node:path');
module.exports = async function(context, url, output, engine) {
  const page = await context.newPage();
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  try {
    await page.goto(url);
    await page.waitForFunction(()=>connected() && state.mock);
    // Browser-only state; no commands, no calibration or layout writes.
    await page.evaluate(()=>{
      state.config=Object.assign({},state.config,{hall:{w:20,d:10,stage:'top',stageDepth:3},attrs:{pan:{min:-270,max:270}},
        fixtures:[{id:1,label:'Оценка A',moves:true,x:.3,y:.6,beam:{home:50}},
          {id:2,label:'Оценка B',moves:true,x:.7,y:.6,beam:{home:50,invert:true}}]});
      state.shown={1:{pan:60},2:{pan:60}};state.selection=[1];state.valuesMeta={};
      // Freeze only this throwaway page's transport so polling cannot replace synthetic evidence.
      state.ws.onmessage=()=>{};
      state.ws.send=()=>{};
    });
    for(const mode of ['control','edit']) {
      await page.evaluate(mode=>{
        lightUI.tab='plan';lightUI.picking=mode==='control';go(mode==='control'?'light':'hall');
        sectionKey=null;render();updaters.forEach(fn=>fn());
      },mode);
      if(mode==='edit') assert(await page.locator('.planbox').evaluate(box=>{
        const note=box.querySelector('p.note');return note.getBoundingClientRect().bottom<=box.getBoundingClientRect().bottom+1;
      }), 'beam legend stays inside the plan area');
      const beams=page.locator('.plan-beam');assert.equal(await beams.count(),2);
      assert(await beams.nth(0).isVisible());assert(await beams.nth(1).isVisible());
      const transforms=await beams.evaluateAll(ns=>ns.map(n=>n.style.transform));assert.notEqual(...transforms);
      for(const stage of ['top','right','bottom','left']) {
        await page.evaluate(stage=>{state.config.hall.stage=stage;updaters.forEach(fn=>fn());},stage);
        assert(await beams.nth(0).isVisible());
      }
      await page.screenshot({path:path.join(output,engine+'-beams-'+mode+'.png')});
      const before=await beams.nth(0).boundingBox();
      await page.setViewportSize({width:768,height:1024});
      await page.evaluate(()=>updaters.forEach(fn=>fn()));
      const after=await beams.nth(0).boundingBox();assert(after.width>0 && before.width>0);
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
      await page.evaluate(()=>{state.config.fixtures[0].beam.home=60;updaters.forEach(fn=>fn());});
      assert.notEqual(await beams.nth(0).evaluate(n=>n.style.transform),transforms[0]);
      await page.evaluate(()=>{delete state.shown[1].pan;updaters.forEach(fn=>fn());});
      assert(await beams.nth(0).isHidden());
      await page.evaluate(()=>{state.shown[1].pan=60;state.config.fixtures[0].beam.home=50;});
      await page.setViewportSize({width:1024,height:768});
    }
    assert.deepEqual(errors,[]);
    console.log('PASS '+engine+': schematic beams in control/edit, calibration, stages, unknown Pan, resize');
  } finally {await page.close();}
};
