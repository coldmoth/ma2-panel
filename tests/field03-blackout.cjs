'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const prefix = fs.readFileSync('tests/panel-v4.cjs', 'utf8').split('// Empty workspace:')[0];
const {context:c, ws, document, Node, WebSocket} = new Function('require', prefix + '\nreturn {context, ws, document, Node, WebSocket};')(require);
const status = (epoch, mode='full') => c.receive({status:{ma2:'logged_in',blackout_epoch:epoch,safety:{mode,fixtures:[],scenes:[]}}});
c.receive({config:{fixtures:[],groups:[],scenes:[],presets:[],attrs:{}}});
status(0);
const raw = () => ws().sent;
// Reversible suppression cancels an unsent slider and a held joystick on its first tap.
c.sliderChannels.dim = {timer:1,latest:{a:'dim',v:100},sent:0};
c.moveState.drag = {timer:1,pointer:3};
const before = raw().length;
document.getElementById('blackout').click();
assert.deepEqual(Array.from(raw().slice(before),a=>a.a),['blackout']);
assert.equal(c.sliderChannels.dim.latest,null);
assert.equal(c.moveState.drag,null);
assert.equal(raw().at(-1).blackout_epoch,0);
const boRequest=raw().at(-1);
c.receive({a:'blackout',request_id:boRequest.request_id,ok:true,outcome:'completed',command_evidence:['sent']});
// A blackout from the teacher port stops this client's old gesture too.
c.sliderChannels.color = {timer:2,latest:{a:'color',r:100,g:0,b:0},sent:0};
c.moveState.drag = {timer:1,pointer:4};
status(1);
assert.equal(c.sliderChannels.color.latest,null);
assert.equal(c.moveState.drag,null);
c.send({a:'dim',v:40});
assert.equal(raw().at(-1).blackout_epoch,1,'new gestures carry the server barrier');
status(1,'test');
assert.equal(document.getElementById('blackout').disabled,true);
status(1,'full');
assert.equal(document.getElementById('blackout').disabled,false);

const ids = new Map();
const doc = {createElement:tag=>new Node(tag),getElementById:id=>{
  if(!ids.has(id)) ids.set(id,new Node('div')); return ids.get(id);
}};
let socket, confirmation;
class Socket extends WebSocket { constructor(){super();socket=this;} }
const simple = vm.createContext({document:doc,WebSocket:Socket,location:{protocol:'http:',host:'localhost'},setTimeout:()=>0,setInterval:()=>0,
  confirm:text=>{confirmation=text;return true;}});
for (const file of ['static/command-feedback.js','static/simple.js']) vm.runInContext(fs.readFileSync(file,'utf8'),simple);
const simpleStatus = (mode,epoch) => socket.onmessage({data:JSON.stringify({status:{ma2:'logged_in',blackout_epoch:epoch,safety:{mode}}})});
simpleStatus('test',1);
assert.equal(doc.getElementById('blackout').disabled,true);
simpleStatus('full',2);
assert.equal(doc.getElementById('blackout').disabled,false);
doc.getElementById('blackout').click();
assert.equal(confirmation,undefined,'Grand Master suppression keeps the stage1 reversible contract');
assert.equal(socket.sent.at(-1).a,'blackout');
assert.equal(socket.sent.at(-1).blackout_epoch,2);
console.log('FIELD-03: local/global gesture cancellation, epoch and both-port safety passed');
