/* Display regression only: simulated readback, actual UI, isolated --mock. */
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const playwright=require('./browser_smoke/node_modules/playwright');
const [url,,output]=process.argv.slice(2);
(async()=>{
 const results=[];
 for(const engine of ['chromium','webkit']){
  const browser=await playwright[engine].launch({headless:true});
  try{
   const page=await browser.newPage({viewport:{width:1024,height:768}}),errors=[],sent=[];
   page.on('pageerror',e=>errors.push(e.message));
   page.on('websocket',socket=>socket.on('framesent',frame=>sent.push(frame.payload)));
   await page.goto(url);await page.waitForFunction(()=>connected());
   await page.evaluate(()=>{
    // Keep the mock's empty output from replacing the explicit regression sample.
    const original=receive;
    receive=function(message){if(!message.displayTest && ('live' in message || message.values_meta))return;original(message);};
    receive({displayTest:true,config:{...state.config,fixtures:[{id:1,label:'Тестовый LED',type:'LED',x:.4,y:.4}],groups:[],scenes:[],presets:[],attrs:{}}});
    state.selection=[1];lightUI.picking=false;lightUI.tab='plan';go('light');
    receive({displayTest:true,tracked:false,shown:{},live:{1:{dim:10,rgb:[0,100,0]}},values_meta:{shown:{source:'unknown',freshness:'unknown'},live:{source:'ma2',freshness:'fresh',updated_at:Date.now()/1000}}});
   });
   const before=sent.length;
   await page.locator('.c-color details').evaluateAll(nodes=>nodes.forEach(node=>{node.open=true;}));
   assert.match(await page.locator('.c-color').innerText(),/R 0 · G 100 · B 0/);
   assert.match(await page.locator('.c-color').innerText(),/прочитано с MA2/i);
   assert.equal(await page.getByRole('slider',{name:'Яркость',exact:true}).inputValue(),'10');
   await page.screenshot({path:path.join(output,engine+'-controls.png'),fullPage:true});
   await page.evaluate(()=>{
    const root=document.createElement('section');root.id='display-test-plan';root.style.height='360px';
    document.getElementById('page').append(root);hallPlan(root,'control');updaters.forEach(fn=>fn());
   });
   const dot=page.locator('#display-test-plan .fx.lit');
   assert.equal(await dot.count(),1);
   assert.equal(await dot.evaluate(el=>el.style.getPropertyValue('--c')),'rgba(0,255,0,0.1)');
   assert.equal(await dot.locator('.g').evaluate(el=>getComputedStyle(el).backgroundColor),'rgba(0, 255, 0, 0.1)');
   await page.locator('#display-test-plan').screenshot({path:path.join(output,engine+'-plan.png')});
   await page.evaluate(()=>receive({displayTest:true,live:{1:{dim:0,rgb:[0,100,0]}}}));
   assert.equal(await page.locator('#display-test-plan .fx.lit').count(),0);
   await page.evaluate(()=>receive({displayTest:true,live:{1:{dim:10,rgb:[0,100,0]}},values_meta:{live:{source:'ma2',freshness:'stale'}}}));
   assert.equal(await page.locator('#display-test-plan .fx.lit').count(),0);
   assert.equal(await page.evaluate(()=>known('dim')),null);
   assert.equal(sent.length,before,'display-only readback must not send commands');
   assert.deepEqual(errors,[]);
   results.push({engine,controls:true,plan:true,zero:true,stale:true,noCommands:true});
  }finally{await browser.close();}
 }
 fs.writeFileSync(path.join(output,'verification.json'),JSON.stringify(results,null,2));
 console.log('Chromium/WebKit: live dim/RGB, source, proportional glow, zero/stale and no commands passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
