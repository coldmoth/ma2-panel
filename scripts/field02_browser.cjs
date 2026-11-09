const {chromium,webkit}=require(process.cwd()+'/scripts/browser_smoke/node_modules/playwright');
const assert=require('node:assert/strict');
const [url,,out]=process.argv.slice(2);
(async()=>{for(const [name,engine] of [['chromium',chromium],['webkit',webkit]]){
 const browser=await engine.launch({headless:true});try{
 const page=await browser.newPage({viewport:{width:1024,height:768}});
 const open=async()=>{await page.goto(url);await page.waitForFunction(()=>typeof connected==='function'&&connected());await page.evaluate(()=>{selectFixtures([1]);lightUI.controlTab='movement';go('light');});await page.locator('.move-settings').evaluate(el=>el.open=true);};
 await open();const pan=page.getByRole('button',{name:'Pan наоборот',exact:true});
 assert(await pan.isEnabled());
 // Reset only this isolated mock flag, regardless of previous engine.
 if(await pan.getAttribute('aria-pressed')==='true'){await pan.click();await page.waitForFunction(()=>!busy('fixture_flag'));}
 await page.screenshot({path:out+'/'+name+'-before.png',fullPage:true});
 await pan.click();await page.waitForFunction(()=>!busy('fixture_flag'));
 assert(await pan.isEnabled());assert.equal(await pan.getAttribute('aria-pressed'),'true');
 await page.waitForTimeout(250);
 console.log(name+' flipped style',await pan.evaluate(el=>({background:getComputedStyle(el).backgroundColor,color:getComputedStyle(el).color,disabled:el.disabled})));
 await page.screenshot({path:out+'/'+name+'-flipped.png',fullPage:true});
 await open();assert.equal(await pan.getAttribute('aria-pressed'),'true','flag survives reload');
 await pan.click();await page.waitForFunction(()=>!busy('fixture_flag'));
 assert.equal(await pan.getAttribute('aria-pressed'),'false');
 await page.evaluate(()=>{state.features.move=false;render();});assert(await pan.isDisabled());assert.match(await page.locator('.move-settings').innerText(),/features.move/);
 await page.evaluate(()=>{state.features.move=true;state.ma2='down';render();});assert(await pan.isDisabled());assert.match(await page.locator('.move-settings').innerText(),/Нет связи/);
 await page.screenshot({path:out+'/'+name+'-disconnected.png',fullPage:true});
 console.log('PASS '+name+': available, toggle, acknowledgement, reload, reverse, feature restriction, disconnect');
 }finally{await browser.close();}
}})().catch(e=>{console.error(e);process.exitCode=1});
