import { useLanguage } from "./Language.jsx";
import { errorMessage } from "./errors.mjs";
import React, {useEffect, useRef, useState} from 'react';
import { Badge } from "@astryxdesign/core/Badge";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Card } from "@astryxdesign/core/Card";
import { CheckboxInput } from "@astryxdesign/core/CheckboxInput";
import { Collapsible } from "@astryxdesign/core/Collapsible";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { InternationalizationProvider } from "@astryxdesign/core/i18n";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl";
import { Selector } from "@astryxdesign/core/Selector";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Theme } from "@astryxdesign/core/theme";
import { lumaTheme } from "./theme/luma.js";
import "./theme/luma.css";
import { Icon } from "./Icons.jsx";
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
  const hlPing=useRef(null), hlEditing=useRef(false), hlOwned=useRef(false);
  const [hlBusy,setHlBusy]=useState(false), [hlError,setHlError]=useState('');
  const [xmlModalOpen, setXmlModalOpen] = useState(false);
  current.current=state.config;
  const fixtures=state.config?.fixtures || [], hall=state.config?.hall ?? DEFAULT_HALL,
    fixture=fixtures.find(f=>f.id===selection.at(-1)), busy=status==='saving';
  const hl = state.status?.highlight || { state: "idle", available: [], zone: [], target: null, reason: "" };
  const hlState = hl.state || "idle";
  const allowHighlight = state.status?.safety?.allow_highlight === true;
  const highlightBlock = bridge.blockReason("highlight");
  const highlightOffBlock = bridge.blockReason("highlight_off");

  function clearHighlightTimer() {
    if (hlPing.current) {
      clearInterval(hlPing.current);
      hlPing.current = null;
    }
  }

  useEffect(() => {
    if (hlState !== "active") {
      clearHighlightTimer();
      hlOwned.current = false;
    }
  }, [hlState]);

  useEffect(() => {
    return () => {
      clearHighlightTimer();
      const wasOwned = hlOwned.current;
      const wasEditing = hlEditing.current;
      hlOwned.current = false;
      hlEditing.current = false;
      if (bridge.state.connected) {
        if (wasOwned && !bridge.blockReason("highlight_off")) {
          bridge.action({ a: "highlight_off" }).catch(() => {});
        }
        if (wasEditing && !bridge.blockReason("edit_end")) {
          bridge.action({ a: "edit_end" }).catch(() => {});
        }
      }
    };
  }, []);

  async function startHighlight(fid) {
    if (hlBusy || !fid) return;
    setHlBusy(true);
    setHlError('');
    try {
      await bridge.action({ a: "edit_begin" });
      hlEditing.current = true;
      await bridge.action({ a: "highlight", id: fid });
      hlOwned.current = true;
      clearHighlightTimer();
      hlPing.current = setInterval(() => {
        if (bridge.state.connected && !bridge.blockReason("highlight_ping")) {
          bridge.action({ a: "highlight_ping" }).catch(() => {});
        }
      }, 3000);
    } catch (e) {
      setHlError(e.err || errorMessage(e, t) || e.message || String(e));
    } finally {
      setHlBusy(false);
    }
  }

  async function stopHighlight() {
    if (hlBusy) return;
    setHlBusy(true);
    setHlError('');
    try {
      clearHighlightTimer();
      await bridge.action({ a: "highlight_off" });
      hlOwned.current = false;
      if (hlEditing.current && bridge.state.connected && !bridge.blockReason("edit_end")) {
        await bridge.action({ a: "edit_end" }).catch(() => {});
        hlEditing.current = false;
      }
    } catch (e) {
      setHlError(e.err || errorMessage(e, t) || e.message || String(e));
    } finally {
      setHlBusy(false);
    }
  }
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
      <div className="layout-toolbar-right">
        <span className={`layout-status ${error?'error':''}`} role="status" aria-live="polite">{message}</span>
        <Theme theme={lumaTheme} mode="dark">
          <Button
            label={t("layout.ma2Xml")}
            variant="secondary"
            size="sm"
            icon={<Icon name="layout" size={14} />}
            isDisabled={busy}
            onClick={() => setXmlModalOpen(true)}
          />
        </Theme>
      </div>
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
      {fixture && (
        <HighlightPanel
          fixture={fixture}
          hl={hl}
          allowHighlight={allowHighlight}
          highlightBlock={highlightBlock}
          highlightOffBlock={highlightOffBlock}
          hlBusy={hlBusy}
          hlError={hlError}
          onStart={() => startHighlight(fixture.id)}
          onStop={stopHighlight}
        />
      )}
      {fixture ? <LayoutFields key={fixture.id} fixture={fixture} hall={hall} ready={ready&&!busy} visual={visuals[fixture.id]} gesture={preview}
        onPreview={setPreview} onDirty={setFixtureDirty} onSave={saveFixture}/> : <p className="layout-hint">{t("layout.selectHint")}</p>}
      <details className="layout-fixture-list"><summary>{t("shell.allFixtures")} · {t("shell.number", { value: fixtures.length })}</summary><div>{fixtures.map(f=><button key={f.id} aria-pressed={selection.includes(f.id)} onClick={e=>select(f.id,e.shiftKey)}>#{f.id} <span>{f.label}</span></button>)}</div></details>
      <p className="layout-hint">{t("layout.rotationHint")}</p>
    </aside>
    {xmlModalOpen && (
      <Ma2LayoutXmlModal
        state={state}
        disabled={busy}
        onClose={() => setXmlModalOpen(false)}
      />
    )}
  </div>;
}

function HighlightPanel({ fixture, hl, allowHighlight, highlightBlock, highlightOffBlock, hlBusy, hlError, onStart, onStop }) {
  const { t } = useLanguage();
  const hlState = hl.state || "idle";
  const isTarget = hlState === "active" && hl.target === fixture.id;
  const zoneList = hlState === "active" && Array.isArray(hl.zone) && hl.zone.length ? hl.zone : (hl.available || []);
  const inZone = zoneList.includes(fixture.id);
  const blockText = !allowHighlight
    ? t("layout.highlightBlockedFlag")
    : hlState === "stuck"
      ? t("layout.highlightStuckNote", { reason: hl.reason || t("layout.highlightStuckDefault") })
      : highlightBlock
        ? errorMessage(highlightBlock, t)
        : !inZone
          ? t("layout.highlightOutsideZone")
          : "";
  const canHighlight = !hlBusy && !blockText;
  return (
    <section className={`layout-highlight ${hlState !== "idle" ? hlState : ""}`} aria-label={t("layout.highlightTitle")}>
      <div className="layout-highlight-head">
        <b>{t("layout.highlightTitle")}</b>
        <span className={`layout-highlight-state ${hlState}`}>
          {t(hlState === "active" ? "layout.highlightActive" : hlState === "stuck" ? "layout.highlightStuck" : "layout.highlightIdle")}
        </span>
      </div>
      <small>
        {isTarget
          ? t("layout.highlightCurrentFixture", { id: fixture.id, count: zoneList.length })
          : t("layout.highlightZoneInfo", { id: fixture.id, count: zoneList.length })}
      </small>
      {blockText && <small className="layout-highlight-note">{blockText}</small>}
      {hlError && <div className="layout-ma2-err" role="alert">{hlError}</div>}
      <div className="layout-highlight-actions">
        {isTarget ? (
          <button
            type="button"
            className="layout-highlight-stop"
            disabled={hlBusy || !!highlightOffBlock}
            title={errorMessage(highlightOffBlock, t)}
            onClick={onStop}
          >
            {hlBusy ? t("common.saving") : t("layout.highlightTurnOff")}
          </button>
        ) : (
          <button
            type="button"
            className="layout-highlight-btn"
            disabled={!canHighlight}
            title={blockText || undefined}
            onClick={onStart}
          >
            {hlBusy ? t("common.saving") : t("layout.highlightBtn")}
          </button>
        )}
      </div>
    </section>
  );
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

function Ma2LayoutXmlModal({ state, disabled, onClose }) {
  const { t, language } = useLanguage();
  const current = state.config?.ma2_layout || null;
  const fileInputRef = useRef(null);
  const [tab, setTab] = useState("import");
  const [files, setFiles] = useState([]);
  const [selectedFile, setSelectedFile] = useState("");
  const [hasTemplate, setHasTemplate] = useState(Boolean(current?.template_file));
  const [previewData, setPreviewData] = useState(null);
  const [fileName, setFileName] = useState(current?.name || state.config?.show || "luma_layout");
  const [slot, setSlot] = useState(99);
  const [confirmImport, setConfirmImport] = useState(false);
  const [working, setWorking] = useState(false);
  const [notice, setNotice] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => {
    setHasTemplate(Boolean(current?.template_file));
    if (!fileName && (current?.name || state.config?.show)) {
      setFileName(current?.name || state.config?.show || "luma_layout");
    }
  }, [current?.template_file, current?.name, state.config?.show]);

  async function refreshFiles() {
    try {
      const res = await fetch("/api/layout/ma2/files");
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        return;
      }
      const list = data.files || [];
      setFiles(list);
      setHasTemplate(Boolean(data.has_template));
      if (list.length && !selectedFile) {
        setSelectedFile(`${list[0].folder_index}:${list[0].name}`);
      }
    } catch {}
  }

  useEffect(() => {
    refreshFiles();
  }, []);

  async function runPreview(payload) {
    setWorking(true);
    setErr("");
    setNotice("");
    try {
      const res = await fetch("/api/layout/ma2/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.err || `HTTP ${res.status}`);
      setPreviewData(data);
    } catch (e) {
      setErr(e.message || String(e));
      setPreviewData(null);
    } finally {
      setWorking(false);
    }
  }

  async function onUpload(e) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const xml = await file.text();
    await runPreview({ xml, filename: file.name });
  }

  async function onPreviewFolderFile() {
    if (!selectedFile) return;
    const sep = selectedFile.indexOf(":");
    const folder_index = Number(selectedFile.slice(0, sep));
    const file = selectedFile.slice(sep + 1);
    await runPreview({ file, folder_index });
  }

  async function onApply() {
    if (!previewData?.preview_token) return;
    setWorking(true);
    setErr("");
    setNotice("");
    try {
      const res = await fetch("/api/layout/ma2/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ preview_token: previewData.preview_token }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.err || `HTTP ${res.status}`);
      setNotice(t("layout.ma2Applied", { count: data.applied }));
      setPreviewData(null);
      setHasTemplate(true);
      if (data.layout?.name) setFileName(data.layout.name);
    } catch (e) {
      setErr(e.message || String(e));
    } finally {
      setWorking(false);
    }
  }

  async function onExport(mode) {
    setWorking(true);
    setErr("");
    setNotice("");
    try {
      const body = { mode, filename: fileName.trim() || undefined };
      if (mode === "import_to_ma2") {
        body.slot = Number(slot);
        body.confirm_import = confirmImport;
      }
      const res = await fetch("/api/layout/ma2/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (mode === "download") {
        if (!res.ok) {
          const fail = await res.json().catch(() => ({}));
          throw new Error(fail.err || `HTTP ${res.status}`);
        }
        const blob = await res.blob();
        const disp = res.headers.get("content-disposition") || "";
        const match = disp.match(/filename="([^"]+)"/);
        const dlName = match ? match[1] : `${fileName.trim() || "luma_layout"}.xml`;
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = dlName;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
        const modeLabel = res.headers.get("x-luma-layout-mode") === "patch" ? t("layout.ma2ModePatch") : t("layout.ma2ModeNew");
        const updated = res.headers.get("x-luma-layout-updated") || "0";
        setNotice(t("layout.ma2Downloaded", { filename: dlName, mode: modeLabel, updated }));
        return;
      }
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.err || `HTTP ${res.status}`);
      const modeLabel = data.summary?.mode === "patch" ? t("layout.ma2ModePatch") : t("layout.ma2ModeNew");
      const updated = String(data.summary?.updated_ids?.length ?? 0);
      if (mode === "save_importexport") {
        setNotice(t("layout.ma2SavedFile", { filename: data.filename, mode: modeLabel, updated }));
        refreshFiles();
      } else {
        setNotice(t("layout.ma2Imported", { slot: data.slot, filename: data.filename }));
        setConfirmImport(false);
        refreshFiles();
      }
    } catch (e) {
      setErr(e.message || String(e));
    } finally {
      setWorking(false);
    }
  }

  const allowImport = state.status?.safety?.allow_layout_import === true;
  const ma2Ready = state.status?.ma2 === "logged_in" && !state.status?.halted;
  const importBlockReason = !allowImport
    ? t("layout.ma2BlockedFlag")
    : !ma2Ready
      ? t("layout.ma2BlockedLink")
      : "";
  const fileOptions = files.map((f) => ({
    value: `${f.folder_index}:${f.name}`,
    label: f.name,
  }));

  return (
    <Theme theme={lumaTheme} mode="dark">
      <InternationalizationProvider
        locale={language}
        overrides={{ "@astryx.dialog.close": t("common.close") }}
      >
        <Dialog
          isOpen
          onOpenChange={(open) => {
            if (!open) onClose();
          }}
          width={520}
          purpose="form"
          className="ma2-xml-dialog"
        >
          <DialogHeader
            title={t("layout.ma2Xml")}
            subtitle={t("layout.ma2ModalSubtitle")}
            onOpenChange={(open) => {
              if (!open) onClose();
            }}
            hasDivider
          />
          <div className="ma2-xml-modal-body">
            <SegmentedControl
              value={tab}
              onChange={(next) => {
                setTab(next);
                setErr("");
                setNotice("");
              }}
              label={t("layout.ma2Xml")}
              layout="fill"
              size="md"
            >
              <SegmentedControlItem value="import" label={t("layout.ma2TabImport")} />
              <SegmentedControlItem value="export" label={t("layout.ma2TabExport")} />
            </SegmentedControl>

            {notice && <Banner status="success" title={notice} />}
            {err && <Banner status="error" title={err} />}

            {tab === "import" ? (
              <div className="ma2-xml-pane">
                <p className="ma2-xml-intro">{t("layout.ma2ImportIntro")}</p>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".xml,application/xml,text/xml"
                  hidden
                  disabled={disabled || working}
                  onChange={onUpload}
                />
                <Button
                  label={t("layout.ma2ChooseFile")}
                  variant="primary"
                  size="md"
                  width="100%"
                  isDisabled={disabled || working}
                  isLoading={working && !previewData}
                  onClick={() => fileInputRef.current?.click()}
                />

                {files.length > 0 && (
                  <Card variant="muted" padding={3} className="ma2-xml-folder-card">
                    <div className="ma2-xml-folder-head">
                      <span>{t("layout.ma2FromFolder")}</span>
                      <Button
                        label={t("layout.ma2RefreshFiles")}
                        variant="ghost"
                        size="sm"
                        isDisabled={disabled || working}
                        onClick={refreshFiles}
                      />
                    </div>
                    <div className="ma2-xml-folder-row">
                      <Selector
                        label={t("layout.ma2FromFolder")}
                        isLabelHidden
                        options={fileOptions}
                        value={selectedFile}
                        onChange={setSelectedFile}
                        isDisabled={disabled || working}
                        size="sm"
                      />
                      <Button
                        label={t("layout.ma2PreviewFile")}
                        variant="secondary"
                        size="sm"
                        isDisabled={disabled || working || !selectedFile}
                        onClick={onPreviewFolderFile}
                      />
                    </div>
                  </Card>
                )}

                {previewData && (
                  <Card variant="default" padding={4} className="ma2-xml-preview-card">
                    <div className="ma2-xml-preview-head">
                      <strong>{previewData.layout_name || previewData.source_name || "Layout XML"}</strong>
                      <Badge
                        variant={previewData.matched_count > 0 ? "success" : "warning"}
                        label={t("layout.ma2MatchedBadge", { matched: previewData.matched_count })}
                      />
                    </div>
                    <p className="ma2-xml-preview-summary">
                      {t("layout.ma2PreviewSummary", {
                        found: previewData.xml_fixture_count,
                        matched: previewData.matched_count,
                      })}
                    </p>
                    {previewData.unmatched_xml_ids?.length > 0 && (
                      <small className="ma2-xml-preview-meta">
                        {t("layout.ma2UnmatchedIds", {
                          ids: previewData.unmatched_xml_ids.slice(0, 10).map((id) => `#${id}`).join(", "),
                        })}
                      </small>
                    )}
                    <div className="ma2-xml-preview-actions">
                      <Button
                        label={t("layout.ma2Apply")}
                        variant="primary"
                        size="md"
                        isDisabled={disabled || working || !previewData.matched_count}
                        isLoading={working}
                        onClick={onApply}
                      />
                      <Button
                        label={t("common.cancel")}
                        variant="ghost"
                        size="md"
                        isDisabled={working}
                        onClick={() => setPreviewData(null)}
                      />
                    </div>
                  </Card>
                )}
              </div>
            ) : (
              <div className="ma2-xml-pane">
                <p className="ma2-xml-intro">
                  {hasTemplate ? t("layout.ma2ExportPatchSimple") : t("layout.ma2ExportNewSimple")}
                </p>
                <TextInput
                  label={t("layout.ma2FileName")}
                  value={fileName}
                  onChange={setFileName}
                  placeholder="luma_layout"
                  isDisabled={disabled || working}
                  size="md"
                />
                <Button
                  label={t("layout.ma2DownloadForMa2")}
                  variant="primary"
                  size="md"
                  width="100%"
                  isDisabled={disabled || working}
                  isLoading={working}
                  onClick={() => onExport("download")}
                />

                <Collapsible
                  trigger={t("layout.ma2DirectSendTitle")}
                  defaultIsOpen={false}
                  className="ma2-xml-collapsible"
                >
                  <div className="ma2-xml-direct">
                    <Button
                      label={t("layout.ma2SaveImportExport")}
                      variant="secondary"
                      size="sm"
                      width="100%"
                      isDisabled={disabled || working}
                      onClick={() => onExport("save_importexport")}
                    />
                    <NumberInput
                      label={t("layout.ma2Slot")}
                      value={slot}
                      min={1}
                      max={999}
                      step={1}
                      isIntegerOnly
                      size="sm"
                      isDisabled={disabled || working}
                      onChange={(value) => setSlot(Math.max(1, Math.min(999, Math.round(value || 99))))}
                    />
                    <CheckboxInput
                      label={t("layout.ma2ConfirmImport", { slot })}
                      value={confirmImport}
                      isDisabled={disabled || working || Boolean(importBlockReason)}
                      onChange={setConfirmImport}
                    />
                    {importBlockReason && <Banner status="warning" title={importBlockReason} />}
                    <Button
                      label={t("layout.ma2ImportBtn")}
                      variant="secondary"
                      size="sm"
                      width="100%"
                      isDisabled={disabled || working || Boolean(importBlockReason) || !confirmImport}
                      onClick={() => onExport("import_to_ma2")}
                    />
                  </div>
                </Collapsible>
              </div>
            )}
          </div>
        </Dialog>
      </InternationalizationProvider>
    </Theme>
  );
}
