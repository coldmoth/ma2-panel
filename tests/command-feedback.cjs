'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const prefix = fs.readFileSync('tests/panel-v4.cjs', 'utf8').split('// Empty workspace:')[0];
const {context:c, ws, document} = new Function('require', prefix + '\nreturn {context,ws,document};')(require);
const status = extra => c.receive({status:{ma2:'logged_in',safety:{mode:'full'},features:{},...extra}});
status();
c.receive({config:{revision:'test:1',fixtures:[],groups:[],scenes:[{id:'one',label:'Рояль',exec:'1.1'}],presets:[],pages:{},attrs:{}}});
const line = document.getElementById('operation-status');
const errors = document.getElementById('errors');
const send = (a='scene_go', button) => { assert(c.send({a,id:'one'},button)); return ws().sent.at(-1); };
const reply = (action, fields={}) => c.receive({request_id:action.request_id,a:action.a,ok:true,outcome:'completed',...fields});

const button = document.createElement('button'); button.textContent='Запустить';
const first = send('scene_go',button);
assert.equal(line.hidden,false);
assert.match(line.textContent,/Рояль.*ждём ответ/i,'sending has visible feedback without implying bridge admission');
assert.equal(button.getAttribute('aria-busy'),'true');
assert.equal(button.textContent,'Запустить');
status({operations:[{request_id:'other-client',stage:'running'}]});
assert.doesNotMatch(line.textContent,/зарегистрирован/,'another request cannot acknowledge ours');
status({operations:[{request_id:first.request_id,stage:'running'}]});
assert.match(line.textContent,/зарегистрирован.*мост/i);
c.receive({running:{one:true}});
assert.equal(c.sceneEvidence('one').value,null,'bare running is not readback evidence');
assert.match(line.textContent,/зарегистрирован/,'running never completes an operation');
c.receive({running:{one:true},running_meta:{one:{source:'ma2',freshness:'fresh',updated_at:123}}});
assert.equal(c.sceneEvidence('one').value,true);
assert.match(line.textContent,/зарегистрирован/,'independent readback does not complete this request');
reply(first,{command_evidence:['sent','sent']});
assert.match(line.textContent,/MA2 ответила без ошибки.*не подтверждено/);
assert.equal(line.classList.contains('success'),false);
assert.equal(button.getAttribute('aria-busy'),null);

// Old server without the additive field, and an empty evidence list, cannot prove MA2 sent.
for (const fields of [{},{command_evidence:[]}]) {
 const a=send(); reply(a,fields);
 assert.match(line.textContent,/Обработка завершена.*не подтверждено/);
 assert.doesNotMatch(line.textContent,/MA2 ответила/);
}

// An older terminal reply may clear only its own request, not the new operation's feedback.
const older=send(), newer=send('scene_off');
reply(older,{command_evidence:['sent']});
assert.match(line.textContent,/Выключение сцены.*ждём ответ/);
reply(newer,{command_evidence:['sent']});
reply(older,{ok:false,outcome:'unknown'});
assert.match(line.textContent,/Выключение сцены.*MA2 ответила/);

const beforeSuperseded=errors.children.length;
const sliderOld=send('dim'), sliderNew=send('dim');
reply(sliderOld,{ok:false,outcome:'failed',command_evidence:[],err:'заменено более новым значением до отправки'});
assert.equal(errors.children.length,beforeSuperseded,'ordinary latest-value replacement must not flood errors');
assert(c.pending[sliderNew.request_id]);
reply(sliderNew,{command_evidence:['sent','sent']});

for (const [fields,pattern,kind] of [
 [{ok:false,outcome:'failed',command_evidence:['not_sent'],err:'Запрещено'},/не отправлена.*Запрещено/,'error'],
 [{ok:false,outcome:'failed',command_evidence:['error'],err:'Error #9'},/Ошибка.*Error #9/,'error'],
 [{ok:false,outcome:'failed',command_evidence:[],err:'Нет прав'},/отклонён.*Нет прав/,'error'],
 [{ok:false,outcome:'partial',command_evidence:['sent','error']},/часть обработки.*не подтверждён/,'warning'],
 // Even inconsistent ok=true must not turn unknown/partial into success.
 [{outcome:'unknown',command_evidence:['sent','unknown']},/Результат неизвестен.*повтора нет/,'warning'],
 [{outcome:'partial',command_evidence:['sent']},/часть обработки/,'warning'],
 [{command_evidence:['unknown']},/Результат неизвестен/,'warning']
]) {
 const a=send(); reply(a,fields);
 const row=errors.children.at(-1);
 assert.match(row.textContent,pattern); assert(row.classList.contains(kind));
 assert.match(row.getAttribute('title'),new RegExp(a.request_id));
 assert.doesNotMatch(row.textContent,/успешно|свет изменён/i);
}
// An edit cancelled behind a failed save was never sent to the bridge.
const failedSave=send('fixture_flag'); send('fixture_flag');
reply(failedSave,{ok:false,outcome:'failed',command_evidence:[],err:'План устарел'});
assert.match(errors.textContent,/очереди панели не отправлены/);
assert.equal(Object.keys(c.pending).length,0);
const count=errors.children.length;
const a=send(); reply(a,{command_evidence:['sent']});
assert.equal(errors.children.length,count,'subsequent neutral result does not dismiss warnings/errors');

let now=100000; c.Date={now:()=>now};
const late=send(); now+=31000; c.renderOperationFeedback();
assert.match(line.textContent,/Ответ задерживается.*неизвестен/);
assert(c.pending[late.request_id],'delay preserves correlation');
const sentBefore=ws().sent.length;
reply(late,{command_evidence:['sent']});
assert.match(line.textContent,/MA2 ответила без ошибки/);
assert.equal(ws().sent.length,sentBefore,'late reply never retries');

// A queued local edit is distinguished from a sent request on disconnect.
send('fixture_flag'); const localSent=ws().sent.length;
send('fixture_flag'); assert.equal(ws().sent.length,localSent);
ws().onclose();
assert.match(errors.textContent,/неизвестен/);
assert.match(errors.textContent,/не отправлен/);
c.connect(); c.receive({config:{fixtures:[],groups:[],scenes:[],attrs:{}}}); status();
assert.equal(ws().sent.length,0,'reconnect never replays');
assert.equal(errors.children.length,count+2,'disconnect preserves previous warnings and explains both queues');
assert.equal(line.hidden,true,'reconnect does not restore a prior success notice');

// A local WebSocket send exception must clear busy and surface failure.
const prior=send(); reply(prior,{command_evidence:['sent']});
ws().send=()=>{throw new Error('closed');};
assert.equal(c.send({a:'scene_go',id:'one'},button),false);
assert.equal(button.getAttribute('aria-busy'),null);
assert.match(errors.children.at(-1).textContent,/не отправлен/);
assert.equal(line.hidden,true,'send failure cannot leave the preceding result on screen');
console.log('command feedback: admission, neutral result, readback isolation, legacy fallback, partial/unknown, delay/late reply, queues and reconnect passed');

const ids=new Map(); const doc={createElement:tag=>document.createElement(tag),getElementById:id=>{
 if(!ids.has(id))ids.set(id,document.createElement('div'));return ids.get(id);
}};
let socket; const intervals=[];
class Socket {static OPEN=1;constructor(){socket=this;this.readyState=1;this.sent=[];}send(raw){this.sent.push(JSON.parse(raw));}}
const simple=vm.createContext({document:doc,WebSocket:Socket,location:{protocol:'http:',host:'localhost'},setInterval:fn=>intervals.push(fn),setTimeout(){},confirm:()=>true,Date:{now:()=>now}});
vm.runInContext(fs.readFileSync('static/command-feedback.js','utf8'),simple);
vm.runInContext(fs.readFileSync('static/simple.js','utf8'),simple);
const publish=msg=>socket.onmessage({data:JSON.stringify(msg)});
const click=()=>doc.getElementById('scenes').all().find(n=>n.tagName==='BUTTON').click();
publish({status:{ma2:'logged_in'},config:{scenes:[{id:'one',label:'Рояль',exec:'1.1'}]}});
click(); const simpleAction=socket.sent.at(-1);
const simpleLine=doc.getElementById('operation-status');
assert.match(simpleLine.textContent,/ждём ответ/);
publish({status:{ma2:'logged_in',operations:[{request_id:simpleAction.request_id,stage:'running'}]}});
assert.match(simpleLine.textContent,/зарегистрирован/);
now+=31000; intervals.forEach(fn=>fn());
assert.match(simpleLine.textContent,/задерживается/);
publish({...simpleAction,ok:true,outcome:'completed',command_evidence:['sent']});
assert.match(simpleLine.textContent,/MA2 ответила.*не подтверждено/);
click(); publish({...socket.sent.at(-1),ok:true});
assert.match(simpleLine.textContent,/Обработка завершена/);
click(); publish({status:{ma2:'down'}});
assert.match(doc.getElementById('errors').textContent,/неизвестен/);
publish({status:{ma2:'logged_in'}}); click();
assert.equal(socket.sent.length,4,'MA2 reconnect clears busy without replay');
socket.onclose();
assert.match(doc.getElementById('errors').textContent,/неизвестен/);
console.log('teacher feedback: waiting/admission, delay/late reply, neutral/legacy result, MA2 disconnect and no replay passed');
