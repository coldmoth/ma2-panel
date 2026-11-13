'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('static/interface.js','utf8');
let saved=JSON.stringify({tools:{strobe:false,zoom:false},split:65}),handler,handlers={},cancelled=0,rendered=0;
const context=vm.createContext({document:{getElementById:()=>null},
 localStorage:{getItem:()=>saved,setItem:(key,value)=>{assert.equal(key,'ma2.interface');saved=value;}},
 cancelTargetControls:()=>cancelled++,render:()=>rendered++,sectionKey:'old',
 window:{addEventListener:(name,fn)=>{assert(['storage','pageshow'].includes(name));handlers[name]=fn;if(name==='storage')handler=fn;}}});
vm.runInContext(source,context);
assert.equal(context.toolVisible('strobe'),false);assert.equal(context.toolVisible('dim'),true);
context.displayPrefs.tools.color=false;context.saveDisplayPrefs();assert.equal(JSON.parse(saved).split,65);
vm.runInContext(source,context);assert.equal(context.toolVisible('color'),false);
for(const invalid of ['{broken','null','[]','false']){saved=invalid;handler({key:'ma2.interface'});assert.equal(context.toolVisible('strobe'),true);}
console.log('field interface: persisted visibility, existing layout preference, malformed storage and safe defaults passed');

saved=JSON.stringify({color:false,zoom:false,split:72});vm.runInContext(source,context);context.displayPrefs.tools.strobe=false;context.saveDisplayPrefs();assert.equal(context.toolVisible('color'),false);assert.equal(JSON.parse(saved).split,72);
saved=JSON.stringify({tools:{focus:false},split:72});context.sectionKey='old';handlers.pageshow({type:'pageshow'});assert.equal(context.toolVisible('focus'),false);assert.equal(context.sectionKey,null);assert(cancelled>0&&rendered>0);

const settings=fs.readFileSync('static/settings.html','utf8');assert.equal((settings.match(/id="interface-tools"/g)||[]).length,1);assert.equal((settings.match(/src="interface.js"/g)||[]).length,1);

assert.equal((fs.readFileSync('static/index.html','utf8').match(/src="interface.js"/g)||[]).length,1);
