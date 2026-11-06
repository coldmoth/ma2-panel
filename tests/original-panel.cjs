// Historical navigation and simultaneous selection/control surface.
'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs');
const prefix = fs.readFileSync('tests/panel-v4.cjs','utf8').split('// Empty workspace:')[0];
const {context:c,document,status,ws} = new Function('require',prefix+'\nreturn {context,document,status,ws};')(require);
const html=fs.readFileSync('static/index.html','utf8');
for(const sec of ['start','scenes','light','hall','patch','shows','history']) assert(html.includes('data-sec="'+sec+'"'),'direct historical navigation: '+sec);
assert(!html.includes('data-sec="prepare"'));
status();
c.receive({config:{revision:'test:1',show:'Mock show',fixtures:[1,2].map(id=>({id,label:'Head '+id,type:'Head',moves:true,x:id*.2,y:.3})),groups:[],scenes:[{id:'s',label:'Scene',exec:'1.1'}],presets:[],attrs:{pan:{min:-270,max:270},tilt:{min:-135,max:135}},hall:{w:18,d:14}}});
c.go('scenes');
const page=document.getElementById('page');
assert(page.all().some(n=>n.tagName==='BUTTON'&&n.textContent==='+ Добавить'),'scene store directly accessible');
c.go('light');c.selectFixtures([1,2]);c.lightUI.controlTab='movement';c.sectionKey=null;c.render();
assert(page.all().some(n=>n.classList.contains('pick')),'picker lives beside controls');
assert(!page.all().some(n=>n.tagName==='DIALOG'),'no modal picker');
assert(page.all().some(n=>n.getAttribute('aria-label')==='Пад Pan и Tilt'));
assert.equal(c.operationFeedback,null);
console.log('original panel: historical navigation, scene editing, inline picker and movement passed');
