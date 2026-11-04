const assert=require('node:assert/strict'), fs=require('node:fs'), vm=require('node:vm');
const source=fs.readFileSync('static/update.js','utf8');
function boot(){
 const elements=Object.fromEntries(['update-check','update-start','update-state','update-version','update-notes'].map(id=>[id,{disabled:false,textContent:'',listeners:{},addEventListener(k,f){this.listeners[k]=f;}}]));
 const calls=[],timers=[];
 const box={document:{getElementById:id=>elements[id]},setTimeout:fn=>timers.push(fn),fetch:async(url,options)=>{calls.push({url,options});return{ok:true,json:async()=>({ok:true,current:'v1',phase:'idle'})};}};
 vm.runInNewContext(source,box);return{box,elements,calls,timers,tick:()=>new Promise(r=>setImmediate(r))};
}
(async()=>{
 let b=boot();await b.tick();assert.equal(b.calls[0].url,'/api/update/status');
 assert.equal(b.elements['update-start'].disabled,true);
 b.box.fetch=async(url,options)=>{b.calls.push({url,options});return{ok:true,json:async()=>({ok:true,current:'v1',available:{version:'v2',notes:'<script>plain text</script>'},compatible_installation:true})};};
 await b.elements['update-check'].listeners.click();
 assert.equal(b.elements['update-start'].disabled,false);
 assert.equal(b.elements['update-notes'].textContent,'<script>plain text</script>');
 let resolve;
 b.box.fetch=(url,options)=>{b.calls.push({url,options});return new Promise(r=>resolve=r);};
 const pending=b.elements['update-start'].listeners.click();b.elements['update-start'].listeners.click();
 assert.equal(b.calls.filter(c=>c.url==='/api/update/start').length,1);
 assert.equal(b.calls.at(-1).options.headers['X-Update'],'1');
 assert.equal(JSON.parse(b.calls.at(-1).options.body).version,'v2');
 resolve({ok:true,json:async()=>({ok:true,phase:'downloading'})});await pending;
 b.box.fetch=async()=>{throw Error('offline');};await b.timers.pop()();
 assert.match(b.elements['update-state'].textContent,/соединен|соединён|перезапуск/i);
 b.box.fetch=async(url,options)=>{b.calls.push({url,options});return{ok:true,json:async()=>({ok:true,phase:'rolled_back',current:'v1',error:'health failed'})};};
 await b.timers.pop()();assert.match(b.elements['update-state'].textContent,/возвращ|восстанов|откат/i);
 assert.equal(b.calls.filter(c=>c.url==='/api/update/start').length,1);
 b.box.fetch=async()=>({ok:true,json:async()=>({ok:true,current:'v1',available:null,compatible_installation:true})});
 await b.elements['update-check'].listeners.click();
 assert.equal(b.elements['update-start'].disabled,true);
 assert.match(b.elements['update-state'].textContent,/нет/i);
 console.log('browser update UI: stages, one POST, recovery GET passed');
})().catch(e=>{console.error(e);process.exitCode=1;});
