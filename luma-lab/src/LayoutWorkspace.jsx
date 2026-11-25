import { useLanguage } from "./Language.jsx";
import { errorMessage } from "./errors.mjs";
import React, {useEffect, useRef, useState} from 'react';
import Stage from './Stage.jsx';
import {bridge} from './client.mjs';
import {fixtureAngle, fixtureKind, FIXTURE_KINDS, DEFAULT_HALL} from './model.mjs';
import './layout.css';

const visualState = f => ({id:f.id,x:f.x ?? null,y:f.y ?? null,rot:f.rot ?? null,icon:f.icon ?? null});
const copy = v => JSON.parse(JSON.stringify(v));
const metres = (v,size) => Number(((v ?? .5)*size).toFixed(2));

export default function LayoutWorkspace({state,visuals,onVisualSaved}) {
  const { t } = useLanguage();
  const ready = bridge.ready("layout_save");
  const hallReady = bridge.ready("hall_save");
  const [top,setTop]=useState(true),[ids,setIds]=useState(true),[beams,setBeams]=useState(false);
  const [selection,setSelection]=useState([]), [preview,setPreview]=useState(null),
    [pending,setPending]=useState(null), [status,setStatus]=useState('idle'),
    [error,setError]=useState(''), [geometryDirty,setGeometryDirty]=useState(false), [fixtureDirty,setFixtureDirty]=useState(false), [history,setHistory]=useState({past:[],future:[]});
  const saving=useRef(false), current=useRef(state.config);
  current.current=state.config;
  const fixtures=state.config?.fixtures || [], hall=state.config?.hall ?? DEFAULT_HALL,
    fixture=fixtures.find(f=>f.id===selection.at(-1)), busy=status==='saving';
  async function write(change, mode='edit') {
    const action = change.kind === "hall" ? "hall_save" : "layout_save";
    if (saving.current || !bridge.ready(action)) return false;
    saving.current=true;setStatus('saving');setError('');setPending(change.after);setPreview(null);
    try {
      await bridge.action(change.kind==='hall' ? {a:'hall_save',hall:change.after} : {a:'layout_save',pos:change.after});
      setHistory(h=>mode==='undo' ? {past:h.past.slice(0,-1),future:[...h.future,change.original]}
        : mode==='redo' ? {past:[...h.past,change.original],future:h.future.slice(0,-1)}
        : {past:[...h.past,change].slice(-100),future:[]});
      if(change.kind==='fixtures')for(const f of change.after)onVisualSaved?.(f.id);
      setStatus('saved');return true;
    } catch(e) {setError(e);setStatus('error');return false;}
    finally {saving.current=false;setPending(null);}
  }
  function saveFixture(patch) {
    const f=current.current.fixtures.find(f=>f.id===patch.id);
    if (!f) return Promise.resolve(false);
    const before=visualState(f), after={...before,...patch};
    if (JSON.stringify(before)===JSON.stringify(after)) {setPreview(null);setStatus('saved');setError('');return Promise.resolve(true);}
    return write({kind:'fixtures',before:[before],after:[after]});
  }
  function undo() {
    const entry=history.past.at(-1);
    if(entry && !preview && !geometryDirty && !fixtureDirty) write({...entry,after:entry.before,original:entry},'undo');
  }
  function redo() {
    const entry=history.future.at(-1);
    if(entry && !preview && !geometryDirty && !fixtureDirty) write({...entry,original:entry},'redo');
  }
  useEffect(()=>{
    const key=e=>{
      if(e.target.closest('input,textarea,select,[contenteditable=true]'))return;
      if((e.ctrlKey || e.metaKey) && ['z','y'].includes(e.key.toLowerCase())){
        e.preventDefault();if(e.key.toLowerCase()==='y' || e.shiftKey)redo();else undo();
      }
    };
    document.addEventListener('keydown',key);return()=>document.removeEventListener('keydown',key);
  },[history,preview,geometryDirty,fixtureDirty,hallReady,ready]);
  const patch=Array.isArray(pending)?pending[0]:preview,
    rendered={...state,config:{...state.config,fixtures:fixtures.map(f=>patch?.id===f.id ? {...f,...patch,rot:patch.rot===null?undefined:patch.rot ?? f.rot} : f)}};
  function select(id,shift) {
    if(saving.current)return;
    setPreview(null);
    setSelection(old=>shift ? old.includes(id)?old.filter(i=>i!==id):[...old,id] : [id]);
  }
  const message=busy?t("common.saving"):error?t("layout.saveFailed"):preview || geometryDirty || fixtureDirty?t("layout.unsaved"):status==='saved'?t("common.saved"):t("layout.localPlan");
  return <div className="layout-workspace">
    <div className="layout-toolbar">
      <div className="layout-history"><button aria-label={t("layout.undo")} disabled={!ready || busy || !!preview || geometryDirty || fixtureDirty || !history.past.length} onClick={undo} title="Ctrl/⌘+Z">↶ {t("layout.undo")}</button><button aria-label={t("layout.redo")} disabled={!ready || busy || !!preview || geometryDirty || fixtureDirty || !history.future.length} onClick={redo} title="Ctrl/⌘+Shift+Z">↷ {t("layout.redo")}</button></div>
      <span className={`layout-status ${error?'error':''}`} role="status" aria-live="polite">{message}</span>
    </div>
    {error && <div className="layout-error" role="alert">{t("layout.saveFailedHint", { error: errorMessage(error, t) })}</div>}
    <div className="layout-canvas">
      <Stage {...{top,setTop,ids,setIds,beams,setBeams}} visuals={patch?.icon ? {...visuals,[patch.id]:patch.icon} : visuals} state={rendered} selection={selection} onSelect={select} onClear={()=>{setSelection([]);setPreview(null);}}
        editing locked={!ready || busy} onPlace={saveFixture} onPreview={setPreview}/>
    </div>
    <aside className="layout-inspector" aria-label={t("layout.properties")}>
      <div className="layout-inspector-title"><b>{t("layout.fixtureProperties")}</b><span>{selection.length ? t("common.selectedCount", { count: selection.length }) : t("common.noSelection")}</span></div>
      <details className="layout-geometry"><summary>{t("layout.geometry")} <span>{t("layout.roomStage")}</span></summary>
        <HallGeometry hall={hall} ready={hallReady&&!busy} onDirty={setGeometryDirty} onSave={after=>write({kind:'hall',before:copy(hall),after})}/>
      </details>
      {fixture ? <LayoutFields key={fixture.id} fixture={fixture} hall={hall} ready={ready&&!busy} visual={visuals[fixture.id]} gesture={preview}
        onPreview={setPreview} onDirty={setFixtureDirty} onSave={saveFixture}/> : <p className="layout-hint">{t("layout.selectHint")}</p>}
      <details className="layout-fixture-list"><summary>{t("shell.allFixtures")} · {t("shell.number", { value: fixtures.length })}</summary><div>{fixtures.map(f=><button key={f.id} aria-pressed={selection.includes(f.id)} onClick={e=>select(f.id,e.shiftKey)}>#{f.id} <span>{f.label}</span></button>)}</div></details>
      <p className="layout-hint">{t("layout.rotationHint")}</p>
    </aside>
  </div>;
}

function LayoutFields({fixture:f,hall,ready,visual,gesture,onPreview,onSave,onDirty}) {
  const { t } = useLanguage();
  const [draft,setDraft]=useState(null), [dirty,setDirty]=useState(false), form=useRef(null);
  useEffect(()=>{onDirty(dirty);},[dirty]);
  useEffect(()=>()=>onDirty(false),[]);
  const reset=()=>{setDraft({x:metres(f.x,hall.w),y:metres(f.y,hall.d),rot:f.rot ?? '',icon:f.icon ?? visual ?? fixtureKind(f)});setDirty(false);};
  useEffect(reset,[f.id,f.x,f.y,f.rot,f.icon,hall.w,hall.d]);
  useEffect(()=>{
    if(gesture?.id===f.id && !dirty)setDraft(d=>({...d,x:metres(gesture.x,hall.w),y:metres(gesture.y,hall.d),rot:gesture.rot ?? f.rot ?? ''}));
    else if(!gesture && !dirty)reset();
  },[gesture]);
  if(!draft)return null;
  function data(d) {return {id:f.id,x:Number(d.x)===metres(f.x,hall.w) && f.x!=null ? f.x : Number(d.x)/hall.w,y:Number(d.y)===metres(f.y,hall.d) && f.y!=null ? f.y : Number(d.y)/hall.d,rot:d.rot===''?null:Number(d.rot),icon:d.icon};}
  function change(key,value) {
    const next={...draft,[key]:value};setDraft(next);setDirty(true);
    if(next.x!=='' && next.y!=='' && Number(next.x)>=0 && Number(next.x)<=hall.w && Number(next.y)>=0 && Number(next.y)<=hall.d && (next.rot==='' || Number.isFinite(Number(next.rot)) && Math.abs(Number(next.rot))<=360))onPreview(data(next));
  }
  async function save(d=draft) {
    if(d.x==='' || d.y==='' || !Number.isFinite(Number(d.x)) || !Number.isFinite(Number(d.y)) || Number(d.x)<0 || Number(d.x)>hall.w || Number(d.y)<0 || Number(d.y)>hall.d || d.rot!=='' && (!Number.isFinite(Number(d.rot)) || Math.abs(Number(d.rot))>360)){form.current.reportValidity();return;}
    if(await onSave(data(d))){setDirty(false);onPreview(null);}}
  const shownAngle=fixtureAngle({...f,rot:draft.rot===''?undefined:Number(draft.rot)},draft.icon,hall);
  return <form ref={form} className="layout-fields" onSubmit={e=>{e.preventDefault();save();}} onKeyDown={e=>{if(e.key==='Escape'){e.preventDefault();reset();onPreview(null);}}}>
    <div className="layout-fixture-name"><b>{f.label}</b><small>ID {f.id} · {f.type}</small></div>
    <fieldset disabled={!ready}><legend>{t("layout.positionMetres")}</legend>
      <div className="layout-xy">{[['x','X',hall.w],['y','Y',hall.d]].map(([key,label,max])=><label key={key}>{t("layout.axisMetres", { axis: label })}<input aria-label={t("layout.axisMetres", { axis: label })} type="number" min="0" max={max} step=".01" required value={draft[key]} onChange={e=>change(key,e.target.value)}/></label>)}</div>
      <small>{t("layout.origin")}</small>
    </fieldset>
    <fieldset disabled={!ready}><legend>{t("layout.planRotation")}</legend>
      <label>{t("layout.mode")}<select aria-label={t("layout.orientationMode")} value={draft.rot===''?'auto':'manual'} onChange={e=>{const d={...draft,rot:e.target.value==='auto'?'':shownAngle};setDraft(d);save(d);}}><option value="auto">{t("layout.autoOrient")}</option><option value="manual">{t("layout.manual")}</option></select></label>
      <label>{t("layout.angle")}<input aria-label={t("layout.rotation")} type="number" min="-360" max="360" step=".1" value={draft.rot} placeholder={t("layout.autoAngle", { angle: shownAngle })} onChange={e=>change('rot',e.target.value)}/></label>
      <div className="layout-presets">{[0,45,90,180].map(rot=><button type="button" key={rot} onClick={()=>{const d={...draft,rot};setDraft(d);save(d);}}>{rot}°</button>)}</div>
      <button type="button" className="layout-align" onClick={()=>{const d={...draft,rot:fixtureAngle({...f,x:Number(draft.x)/hall.w,y:Number(draft.y)/hall.d,rot:undefined},'bar',hall)};setDraft(d);save(d);}}>{t("layout.alignWall")}</button>
      <small>{t("layout.rotationKeys")}</small>
    </fieldset>
    <label>{t("layout.icon")}<select aria-label={t("layout.fixtureIcon")} disabled={!ready} value={draft.icon} onChange={e=>change('icon',e.target.value)}>{FIXTURE_KINDS.map(k=><option key={k} value={k}>{t(`kind.${k}`)}</option>)}</select></label>
    <div className="layout-form-actions"><button type="submit" disabled={!ready || !dirty}>{t("common.save")}</button><button type="button" disabled={!dirty} onClick={()=>{reset();onPreview(null);}}>{t("common.reset")}</button></div>
  </form>;
}

function HallGeometry({hall,ready,onSave,onDirty}) {
  const { t } = useLanguage();
  const [draft,setDraft]=useState(hall),[dirty,setDirty]=useState(false);
  useEffect(()=>{setDraft(hall);setDirty(false);},[hall]);
  useEffect(()=>onDirty(dirty),[dirty]);
  if(!draft)return null;
  const horizontal=['top','bottom'].includes(draft.stage),span=horizontal?Number(draft.w):Number(draft.d),depth=horizontal?Number(draft.d):Number(draft.w);
  function change(key,value){setDraft(d=>({...d,[key]:value}));setDirty(true);}
  return <form className="layout-geometry-form" onSubmit={async e=>{e.preventDefault();const after={...draft};for(const key of ['w','d','stageWidth','stageDepth','stageOffset'])after[key]=Number(after[key] ?? (key==='stageOffset'?.5:key==='stageWidth'?span:4));if(await onSave(after))setDirty(false);}} onKeyDown={e=>{if(e.key==='Escape'){setDraft(hall);setDirty(false);}}}>
    <fieldset disabled={!ready}><legend>{t("layout.dimensions")}</legend>
      {[['w',t("layout.roomWidth"),2,80],['d',t("layout.roomLength"),2,80],['stageWidth',t("layout.stageWidth"),.1,span],['stageDepth',t("layout.stageDepth"),2,depth-.1]].map(([key,label,min,max])=><label key={key}>{label}<input aria-label={label} type="number" required min={min} max={max} step=".1" value={draft[key] ?? (key==='stageWidth'?span:4)} onChange={e=>change(key,e.target.value)}/></label>)}
      <label>{t("layout.stageWall")}<select aria-label={t("layout.stageWall")} value={draft.stage} onChange={e=>{const stage=e.target.value;setDraft({...draft,stage,stageWidth:Math.min(Number(draft.stageWidth)||span,['top','bottom'].includes(stage)?Number(draft.w):Number(draft.d)),stageDepth:Math.min(Number(draft.stageDepth)||4,(['top','bottom'].includes(stage)?Number(draft.d):Number(draft.w))-.1)});setDirty(true);}}>{[['top',t("layout.backWall")],['bottom',t("layout.frontWall")],['left',t("layout.leftWall")],['right',t("layout.rightWall")]].map(([k,n])=><option value={k} key={k}>{n}</option>)}</select></label>
      <label>{t("layout.stageOffset")}<input aria-label={t("layout.stageOffset")} type="number" required min="0" max="100" step=".1" value={Number(((draft.stageOffset ?? .5)*100).toFixed(1))} onChange={e=>change('stageOffset',Number(e.target.value)/100)}/></label>
    </fieldset>
    <small>{t("layout.resizeHint")}</small>
    <div className="layout-form-actions"><button type="submit" disabled={!ready || !dirty}>{t("layout.saveGeometry")}</button><button type="button" disabled={!dirty} onClick={()=>{setDraft(hall);setDirty(false);}}>{t("layout.resetGeometry")}</button></div>
  </form>;
}
