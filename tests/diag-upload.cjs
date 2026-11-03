// Browser contract for diagnostic sends: no MA2 actions and durable retry identity.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const SOURCE = fs.readFileSync('static/diag-upload.js', 'utf8');
const ID = 'f0e1d2c3-4567-4890-abcd-0123456789ab';
function boot(initial = {ok:true, configured:true, state:'idle'}, storageFails=false, initialId=null) {
  const elements = Object.fromEntries(['upload-send','upload-status','upload-refresh','upload-description'].map(id => [id, {
    disabled:false, textContent:'', value:'', attrs:{}, listeners:{},
    setAttribute(k,v){this.attrs[k]=v;}, addEventListener(k,v){this.listeners[k]=v;}
  }]));
  const saved = new Map(initialId ? [['ma2.diag-report-id',initialId]] : []);
  const calls=[], polls=[];
  const box = {document:{getElementById:id=>elements[id]},
    localStorage:{getItem:k=>saved.get(k)||null, setItem(k,v){if(storageFails)throw Error('no storage');saved.set(k,v);},removeItem:k=>saved.delete(k)},
    crypto:{randomUUID:()=>ID}, setInterval:fn=>{polls.push(fn);},
    fetch:async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>initial};}};
  vm.runInNewContext(SOURCE, box);
  return {elements,saved,calls,box,polls,tick:()=>new Promise(resolve=>setImmediate(resolve))};
}
(async()=>{
  let accepted=boot({ok:true,configured:true,state:'accepted',report_id:ID,automatic:true,transport:'relay'});await accepted.tick();
  assert.match(accepted.elements['upload-status'].textContent,/принят сервером/i);
  assert.doesNotMatch(accepted.elements['upload-status'].textContent,/отправлен в|не настроен/i);
  assert.equal(accepted.elements['upload-send'].disabled,true);
  let fresh=boot({ok:true,configured:true,state:'idle',transport:'relay'});await fresh.tick();
  assert.equal(fresh.elements['upload-send'].disabled,false);
  assert.doesNotMatch(fresh.elements['upload-status'].textContent,/токен|diagnostic_setup|не настроен/i);
  let b=boot(); await b.tick();
  assert.equal(b.calls.length,1);assert.equal(b.calls[0].url,'/api/diag/upload');
  assert.equal(b.elements['upload-send'].disabled,false);
  let resolve;
  b.box.fetch=(url,options)=>{b.calls.push({url,options});return new Promise(r=>{resolve=r;});};
  b.elements['upload-description'].value='Голова дёрнулась';
  const pending=b.elements['upload-send'].listeners.click();
  b.elements['upload-send'].listeners.click();
  assert.equal(b.calls.length,2);assert.equal(b.elements['upload-send'].disabled,true);
  const req=b.calls[1];assert.equal(req.url,'/api/diag/queue');
  assert.equal(JSON.parse(req.options.body).description,'Голова дёрнулась');
  assert.equal(req.options.headers['X-Diag-Upload'],'1');
  assert.equal(JSON.parse(req.options.body).report_id,ID);assert.equal([...b.saved.values()][0],'pending:'+ID);
  resolve({ok:true,json:async()=>({ok:true,configured:true,state:'pending',report_id:ID})});await pending;
  assert.match(b.elements['upload-status'].textContent,/неизвест|подтвержд/i);
  assert.match(b.elements['upload-send'].textContent,/Проверить/);
  b.box.fetch=async(url,options)=>{b.calls.push({url,options});throw Error('offline');};
  await b.elements['upload-send'].listeners.click();
  assert.equal(JSON.parse(b.calls.at(-1).options.body).report_id,ID);
  assert.match(b.elements['upload-status'].textContent,/не подтверждена/i);
  assert.equal([...b.saved.values()][0],'pending:'+ID);
  b=boot({ok:false,configured:true,state:'pending',report_id:ID,err:'Ошибка связи с GitHub.'});await b.tick();
  assert.equal([...b.saved.values()][0],ID);assert.match(b.elements['upload-send'].textContent,/Проверить/);assert.equal(b.elements['upload-send'].disabled,false);
  b.box.fetch=async()=>({ok:true,json:async()=>({ok:true,configured:true,state:'sent',report_id:ID,number:23})});
  await b.elements['upload-send'].listeners.click();assert.match(b.elements['upload-status'].textContent,/#23/);
  assert.match(b.elements['upload-send'].textContent,/новый/);
  b=boot({ok:true,configured:true,state:'rejected',report_id:ID});await b.tick();assert.match(b.elements['upload-status'].textContent,/отклон/i);
  b=boot({ok:true,configured:true,state:'prepared',report_id:ID});await b.tick();assert.match(b.elements['upload-status'].textContent,/сохран/i);
  b=boot({ok:true,configured:false,state:'idle'});await b.tick();assert.equal(b.elements['upload-send'].disabled,false);
  assert.match(b.elements['upload-status'].textContent,/настро/i);
  b=boot({ok:false,err:'Только с ПК'});await b.tick();assert.equal(b.elements['upload-send'].disabled,true);
  b=boot({ok:true,configured:true,state:'queued',automatic:true,report_id:ID});await b.tick();
  assert.match(b.elements['upload-status'].textContent,/сохранён.*интернет/i);
  assert.equal(b.elements['upload-description'].disabled,true);
  assert.equal(b.elements['upload-send'].disabled,true);
  assert.equal(b.polls.length,1);
  b.box.fetch=async(url,options)=>{b.calls.push({url,options});return {ok:true,json:async()=>({ok:true,configured:true,state:'sent',report_id:ID,number:24})};};
  await b.polls[0]();
  assert.match(b.elements['upload-status'].textContent,/#24/);
  assert.equal(b.calls.filter(call=>call.options?.method==='POST').length,0);
  // A lost queue response after a previous sent report must reuse the NEW UUID.
  b=boot({ok:true,configured:true,state:'sent',report_id:'old-report',number:1});await b.tick();
  let sequence=0;
  b.box.crypto.randomUUID=()=>`new-report-${++sequence}`;
  const queuedIds=[];
  b.box.fetch=async(url,options)=>{
    if (!options) return {ok:true,json:async()=>({ok:true,configured:true,state:'sent',report_id:'old-report',number:1})};
    queuedIds.push(JSON.parse(options.body).report_id);throw Error('lost receipt');
  };
  await b.elements['upload-send'].listeners.click();
  await b.elements['upload-send'].listeners.click();
  await b.polls[0]();
  await b.elements['upload-send'].listeners.click();
  assert.deepEqual(queuedIds,['new-report-1','new-report-1','new-report-1']);
  b=boot({ok:true,configured:true,state:'sent',report_id:'old-report',number:1},false,'pending:'+ID);await b.tick();
  assert.match(b.elements['upload-status'].textContent,/не подтверждено/i);
  b.box.fetch=async(url,options)=>{
    assert.equal(JSON.parse(options.body).report_id,ID);
    return {ok:true,json:async()=>({ok:true,configured:true,state:'queued',report_id:ID,automatic:true})};
  };
  await b.elements['upload-send'].listeners.click();
  assert.equal(b.saved.get('ma2.diag-report-id'),ID);
  // A definite pre-save rejection must allow editing and retrying the same report.
  b=boot();await b.tick();
  b.box.fetch=async()=>({ok:true,json:async()=>({ok:false,configured:true,state:'idle',error:'collection',err:'Не удалось собрать отчёт.'})});
  await b.elements['upload-send'].listeners.click();
  assert.equal(b.elements['upload-description'].disabled,false);
  assert.equal(b.elements['upload-send'].disabled,false);
  // A slow status poll started before a click must not overwrite the queued receipt.
  b=boot();await b.tick();
  let finishStatus;
  b.box.fetch=async(url,options)=>{
    if (!options) return new Promise(resolve=>{finishStatus=resolve;});
    return {ok:true,json:async()=>({ok:true,configured:true,state:'queued',automatic:true,report_id:ID})};
  };
  const oldPoll=b.polls[0]();
  await b.elements['upload-send'].listeners.click();
  finishStatus({ok:true,json:async()=>({ok:true,configured:true,state:'idle'})});await oldPoll;
  assert.match(b.elements['upload-status'].textContent,/сохранён.*интернет/i);
  assert.equal(b.elements['upload-description'].disabled,true);
  b=boot(undefined,true);await b.tick();await b.elements['upload-send'].listeners.click();assert.equal(b.calls.length,1);
  console.log('diag-upload: passed (identity, double click, restart, offline, setup, storage)');
})().catch(error=>{console.error(error);process.exitCode=1;});
