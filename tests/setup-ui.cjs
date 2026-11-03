// First-run form preserves unrelated settings; a lost bridge invalidates QR and status.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
function boot() {
  class Element {
    constructor() { this.value=''; this.hidden=false; this.disabled=false; this.checked=false; this.children=[]; this.listeners={}; this.textContent=''; }
    addEventListener(k,v) { this.listeners[k]=v; }
    replaceChildren(...v) { this.children=v; }
    append(...v) { this.children.push(...v); }
    reportValidity() { return true; }
  }
  const elements={}; const el=id=>elements[id] ||= new Element();
  const settings={bind:'127.0.0.1',port:8080,simple_port:8090,ma2:{user:'Remote',host:'127.0.0.1',port:30000,timeout:9},safety:{mode:'test'},custom:{keep:true}};
  const live={ok:true,instance:'one',bind:'127.0.0.1',port:8080,lan_enabled:false,urls:[],mock:false,ma2:{state:'down',host:'127.0.0.1',port:30000,user:'Remote',ready:false}};
  const calls=[],timers=[];
  let offline=false;
  const box={URL,AbortSignal,structuredClone,location:{hostname:'127.0.0.1',origin:'http://127.0.0.1:8080'},
    document:{getElementById:el,createElement:()=>new Element()},setInterval:fn=>timers.push(fn),
    fetch:async(url,options={})=>{
      calls.push({url,options}); if(offline)throw Error('offline');
      return {ok:true,status:200,json:async()=>url==='/api/setup'?structuredClone(live):options.method==='POST'?{ok:true}: {settings:structuredClone(settings),password_set:true}};
    }};
  vm.runInNewContext(fs.readFileSync('static/setup.js','utf8'),box);
  return {el,settings,live,calls,timers,offline:v=>{offline=v;},tick:async()=>{for(let i=0;i<8;i++)await new Promise(r=>setImmediate(r));}};
}
(async()=>{
  const b=boot();await b.tick();
  assert.equal(b.el('setup-form').hidden,false);
  assert.equal(b.el('setup-user').value,'Remote');
  b.el('setup-host').value='127.0.0.1';b.el('setup-port').value='30000';
  b.el('setup-user').value='SchoolPanel';b.el('setup-lan').checked=true;
  // Another local settings page changed this after the wizard loaded.
  b.settings.ma2.timeout=15;b.settings.custom.keep='new';
  await b.el('setup-form').listeners.submit({preventDefault(){}});
  let req=b.calls.find(c=>c.url==='/api/settings'&&c.options.method==='POST');
  const body=JSON.parse(req.options.body);
  assert.deepEqual(body.settings.custom,{keep:'new'});
  assert.equal(body.settings.ma2.timeout,15);
  assert.equal(body.settings.ma2.user,'SchoolPanel');
  assert.equal(body.settings.bind,'0.0.0.0');
  assert.equal(body.settings.safety.mode,'test');
  assert.equal('password' in body,false);
  assert.equal('clear_password' in body,false);
  assert.equal(b.el('setup-restart').hidden,false);
  assert.doesNotMatch(b.el('setup-live').textContent,/вход подтверждён/i);
  b.live.urls=['http://192.168.5.2:8080/'];b.live.lan_enabled=true;
  await b.timers[0]();assert.equal(b.el('setup-addresses').children.length,1);
  b.offline(true);await b.timers[0]();
  assert.equal(b.el('setup-addresses').children.length,0);
  assert.match(b.el('setup-live').textContent,/недоступ|потерян/i);
  assert.equal(b.el('setup-save').disabled,true);
  b.offline(false);await b.timers[0]();
  assert.equal(b.el('setup-save').disabled,false);
  b.el('setup-password').value='new secret';
  await b.el('setup-form').listeners.submit({preventDefault(){}});
  req=b.calls.filter(c=>c.url==='/api/settings'&&c.options.method==='POST').at(-1);
  assert.equal(JSON.parse(req.options.body).password,'new secret');
  assert.equal(b.el('setup-password').value,'');
  assert.equal(b.calls.some(c=>c.url.includes('probe')||c.url.includes('link_test')),false);
  const explicit=boot();explicit.settings.bind='192.168.5.2';await explicit.tick();
  assert.equal(explicit.el('setup-lan').checked,true);
  await explicit.el('setup-form').listeners.submit({preventDefault(){}});
  const saved=explicit.calls.find(c=>c.options.method==='POST');
  assert.equal(JSON.parse(saved.options.body).settings.bind,'192.168.5.2');
  b.live.ma2.ready=true;b.live.ma2.halted=true;
  await b.timers[0]();
  assert.match(b.el('setup-live').textContent,/Передача остановлена/);
  console.log('setup form preservation and offline status passed');
})().catch(error=>{console.error(error);process.exitCode=1;});
