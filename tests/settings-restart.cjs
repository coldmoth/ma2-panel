const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function boot({busy=false, old=false, offline=false, loadFails=false, port=8080}={}) {
  class Element {
    constructor(){this.value='';this.hidden=false;this.disabled=false;this.children=[];this.listeners={};this.textContent='';}
    addEventListener(k,v){this.listeners[k]=v;}
    replaceChildren(...v){this.children=v;}
    append(...v){this.children.push(...v);}
  }
  let now=0, reads=0, post=0, moved;
  const elements={}, el=id=>elements[id] ||= new Element();
  const location={href:'http://127.0.0.1:8080/settings.html',origin:'http://127.0.0.1:8080',port:'8080',assign:url=>{moved=url;}};
  const box={URL,AbortSignal,Date:{now:()=>now},location,
    document:{getElementById:el,createElement:()=>new Element()},
    setTimeout:fn=>{now+=2000;queueMicrotask(fn);},
    fetch:async(url,options={})=>{
      assert.ok(options.signal,'every restart/load request has a timeout');
      let body,ok=true;
      if(url==='/api/settings'){
        reads++;
        if(loadFails && reads>1) return {ok:false,status:500};
        body={settings:{port},defaults:{ma2:{},safety:{allowed_fixtures:[],allowed_scenes:[],store_execs:[]}}};
      } else if(url==='/api/restart'){
        post++;ok=!busy;body=busy?{ok:false,err:'Перезапуск отложен: выполняется поиск RDM'}:{ok:true,instance:'old'};
      } else {
        if(offline)throw Error('connection refused');
        body={ok:true,instance:old?'old':'new'};
      }
      return {ok,status:ok?200:409,json:async()=>body};
    }};
  vm.runInNewContext(fs.readFileSync('static/settings.js','utf8'),box);
  return {el,box,run:()=>el('restart').listeners.click(),setBusy:v=>{busy=v;},get reads(){return reads;},get post(){return post;},get moved(){return moved;}};
}
(async()=>{
  const tick=()=>new Promise(r=>setImmediate(r));
  let b=boot({busy:true});await tick();await b.run();
  assert.match(b.el('save-status').textContent,/RDM/);assert.equal(b.el('restart').disabled,false);
  b.setBusy(false);await b.run();assert.equal(b.reads,2);assert.equal(b.post,2);assert.match(b.el('save-status').textContent,/настройки загружены/);
  for(const options of [{old:true},{offline:true}]){
    b=boot(options);await tick();await b.run();
    assert.match(b.el('save-status').textContent,/45|время ожидания/i);assert.equal(b.el('restart').disabled,false);assert.equal(b.reads,1);
  }
  b=boot({loadFails:true});await tick();await b.run();
  assert.match(b.el('save-status').textContent,/загрузить настройки/);assert.equal(b.el('restart').disabled,false);
  b=boot({port:8081});await tick();vm.runInNewContext('savedPort = 8081',b.box);await b.run();
  assert.equal(b.moved,'http://127.0.0.1:8081/settings.html');
  console.log('settings-restart: PASS (busy/retry, new instance, bounded old/offline, failed settings, port change)');
})().catch(e=>{console.error(e);process.exitCode=1;});
