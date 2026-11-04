'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const prefix=fs.readFileSync('tests/panel-v4.cjs','utf8').split('// Empty workspace:')[0];
const {context:c,document,ws}=new Function('require',prefix+'\nreturn {context,document,ws};')(require);
c.receive({config:{fixtures:[],groups:[],scenes:[{id:'one',label:'Сцена',exec:'1.1'}],presets:[],attrs:{}}});c.go('scenes');
const ids=new Map(); const doc={createElement:tag=>document.createElement(tag),getElementById:id=>{if(!ids.has(id))ids.set(id,document.createElement('div'));return ids.get(id);}};
let socket,reconnect;class Socket {static OPEN=1;constructor(){socket=this;this.readyState=1;this.sent=[];}send(raw){this.sent.push(JSON.parse(raw));}}
vm.runInNewContext(fs.readFileSync('static/simple.js','utf8'),{document:doc,WebSocket:Socket,location:{protocol:'http:',host:'local'},setInterval(){},setTimeout(fn){reconnect=fn;},confirm:()=>true});
function publish(active,file={}) {const status={ma2:'logged_in',mock:true,safety:{mode:'full'},show_file_active:active,show_file:file};c.receive({status});socket.onmessage({data:JSON.stringify({status,config:{scenes:[{id:'one',label:'Сцена',exec:'1.1'}]}})});}
function controls(blocked){
 assert.equal(document.getElementById('blackout').disabled,blocked);
 assert.equal(doc.getElementById('blackout').disabled,blocked);
 for(const button of doc.getElementById('scenes').all().filter(n=>n.tagName==='BUTTON'))assert.equal(button.disabled,blocked);
 const go=document.getElementById('page').all().find(n=>n.dataset.scene==='one');assert.equal(go.disabled,blocked);
}
publish(false);controls(false);
for(const kind of ['save','load','upload']) {
 publish(true,{kind,state:'running'});controls(true);
 assert.match(c.linkLine().text,/файл.*шоу/);
 assert.match(document.getElementById('banners').textContent,/файл.*шоу.*недоступно/);
 assert.match(doc.getElementById('connection').textContent,/файл.*шоу/);
 const before=socket.sent.length;doc.getElementById('blackout').click();assert.equal(socket.sent.length,before);
 for(const state of ['failed','unknown','done']) {
   publish(true,{kind,state});controls(true); // Never infer unlock from operation text.
   publish(false,{kind,state});controls(false);
   assert.doesNotMatch(document.getElementById('banners').textContent,/файл.*шоу/);
   assert.doesNotMatch(doc.getElementById('connection').textContent,/файл.*шоу/);
 }
}
publish(true);ws().onclose();socket.onclose();controls(true);
c.connect();reconnect();
publish(false);controls(false);
console.log('show-file busy: both panels, save/load/upload, terminal/unknown flags and disconnect passed');
