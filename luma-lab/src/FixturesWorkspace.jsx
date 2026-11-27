import { useLanguage } from "./Language.jsx";
import { TextInput } from "@astryxdesign/core/TextInput";
import { InternationalizationProvider } from "@astryxdesign/core/i18n";
import { errorMessage } from "./errors.mjs";
import React, { useEffect, useRef, useState } from "react";
import { bridge } from "./client.mjs";
import { Icon, FixtureGlyph } from "./Icons.jsx";
import { Action, Empty, Modal } from "./ui.jsx";
import { FIXTURE_KINDS, fixtureKind } from "./model.mjs";
import "./groups.css";

const COLORS = ["#9e8cef", "#e287c5", "#d6bb8e", "#7ab7b0", "#8cb9ef", "#ed997e"];
const ICONS = ["layers", "sun", "fixtures", "hall", "scenes", "layout"];
export const groupColor = g => /^#[\da-f]{6}$/i.test(g?.color || "") ? g.color : COLORS[0];
export const groupIcon = g => ICONS.includes(g?.icon) ? g.icon : "layers";
export const isLocal = g => !("n" in g);
export function selectionGroups(config, t) {
  const groups = config?.groups || [];
  return [
    ...groups.filter(isLocal),
    ...groups.filter(g => !isLocal(g)),
    ...(config?.ma2groups || []).map(g => ({
      ...g, id: `ma2:${g.n}`, label: g.name || g.label || t("fixtures.unnamedConsoleGroup", { number: String(g.n) }),
      fixtures: g.ids || g.fixtures || [],
    })),
  ];
}
export function availableGroupIds(group, fixtures) {
  return [...new Set(group.fixtures || [])].filter(id => fixtures.some(f => f.id === id && !f.missing));
}
function kind(f, visuals) {return visuals[f.id] || fixtureKind(f);}
function matches(f, query, visuals, t) {
  return `${f.id} ${f.label || ""} ${f.type || ""} ${t(`kind.${kind(f, visuals)}`)}`.toLowerCase().includes(query.trim().toLowerCase());
}
export function GroupEditor({state, visuals, initial, onClose, onSaved}) {
  const { t } = useLanguage();
  const [target, setTarget] = useState(initial.group || null);
  const [choosing, setChoosing] = useState(initial.mode === "choose");
  const [revision, setRevision] = useState(state.config.revision);
  const [label, setLabel] = useState(initial.group?.label || "");
  const [color, setColor] = useState(groupColor(initial.group));
  const [icon, setIcon] = useState(groupIcon(initial.group));
  const [members, setMembers] = useState([...new Set(initial.group?.fixtures || initial.ids || [])]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const fixtures = state.config.fixtures || [], groups = state.config.groups || [];
  const stale = revision !== state.config.revision;
  function load(g) {
    setTarget(g); setLabel(g?.label || ""); setColor(groupColor(g)); setIcon(groupIcon(g));
    setMembers([...new Set([...(g?.fixtures || []), ...(initial.mode === "choose" ? initial.ids : [])])]);
    setRevision(state.config.revision); setError(""); setChoosing(false);
  }
  const visible = fixtures.filter(f => matches(f, query, visuals, t));
  async function save(e) {
    e.preventDefault();
    if(lock.current) return;
    lock.current=true; setBusy(true); setError("");
    try {
      await bridge.action({a:"group_save", ...(target ? {id:target.id} : {}), label:label.trim(), ids:members,
        color, icon, config_revision:revision});
      onSaved?.(target?.id); onClose();
    } catch(e) {setError(e);} finally {lock.current=false; setBusy(false);}
  }
  return <Modal title={choosing ? t("fixtures.addToGroup") : target ? t("fixtures.editGroup") : t("fixtures.newGroup")} onClose={()=>{if(!lock.current)onClose();}}>
    <div className="group-editor">
      {choosing ? <>
        <p className="muted">{t("fixtures.chooseHint", { count: initial.ids.length })}</p>
        <div className="group-destinations">{groups.filter(isLocal).map(g=><button key={g.id} onClick={()=>load(g)}>
          <span className="group-emblem" style={{"--group":groupColor(g)}}><Icon name={groupIcon(g)}/></span>
          <span><b>{g.label}</b><small>{t("shell.fixtureCount", { count: g.fixtures?.length || 0 })}</small></span><Icon name="plus"/>
        </button>)}</div>
        {!groups.filter(isLocal).length && <p className="muted">{t("fixtures.noLocalGroups")}</p>}
        <Action variant="primary" onClick={()=>load(null)}><Icon name="plus"/>{t("fixtures.createGroup")}</Action>
      </> : <form onSubmit={save}>
        <div className="group-identity">
          <span className="group-emblem large" style={{"--group":color}}><Icon name={icon} size={25}/></span>
          <label>{t("fixtures.groupName")}<input autoFocus required maxLength={60} value={label} onChange={e=>setLabel(e.target.value)} disabled={busy}/></label>
        </div>
        <fieldset disabled={busy} className="group-appearance"><legend>{t("fixtures.appearance")}</legend>
          <div className="group-swatches">{COLORS.map(c=><button type="button" key={c} aria-label={t("common.colorValue", { color: c })} aria-pressed={c===color} style={{"--group":c}} onClick={()=>setColor(c)}>{c===color && <Icon name="check" size={16}/>}</button>)}
            <label className="custom-color">{t("fixtures.customColor")}<input aria-label={t("fixtures.customGroupColor")} type="color" value={color} onChange={e=>setColor(e.target.value)}/></label>
          </div>
          <div className="group-icons">{ICONS.map(i=><button type="button" aria-label={t("fixtures.iconOption", { name: t(`groupIcon.${i}`) })} aria-pressed={i===icon} key={i} onClick={()=>setIcon(i)}><Icon name={i}/></button>)}</div>
        </fieldset>
        <div className="group-members-heading"><h3>{t("fixtures.members")} <span>{members.length}</span></h3><span>{t("fixtures.multipleGroups")}</span></div>
        <label className="search-input"><Icon name="search"/><input aria-label={t("fixtures.searchMembers")} placeholder={t("fixtures.searchPlaceholder")} value={query} onChange={e=>setQuery(e.target.value)}/></label>
        <div className="group-members" aria-label={t("fixtures.groupFixtures")}>{visible.map(f=>{
          const checked=members.includes(f.id), already=target?.fixtures?.includes(f.id);
          return <label className={`group-member ${checked ? "included" : ""}`} key={f.id}>
            <input type="checkbox" aria-label={t("fixtures.memberName", { name: f.label || f.id })} checked={checked} disabled={busy || (!checked && f.missing)} onChange={()=>setMembers(old=>checked ? old.filter(id=>id!==f.id) : [...new Set([...old,f.id])])}/>
            <FixtureGlyph kind={kind(f,visuals)} size={27}/><span><b>{f.label || f.id}</b><small>ID {f.id} · {t(`kind.${kind(f,visuals)}`)} · {f.type}</small></span>
            <small className="member-state">{f.missing ? t("fixtures.missing") : already ? checked ? t("fixtures.alreadyMember") : t("fixtures.willRemove") : checked ? t("fixtures.willAdd") : t("common.add")}</small>
          </label>;
        })}{!visible.length && <p className="muted">{t("fixtures.noSearchResults")}</p>}
        {members.filter(id=>!fixtures.some(f=>f.id===id)).map(id=><label className="group-member" key={id}><input type="checkbox" checked disabled={busy} aria-label={t("fixtures.removeUnavailable", { id: id })} onChange={()=>setMembers(old=>old.filter(i=>i!==id))}/><span>ID {id}<small>{t("fixtures.unavailableHint")}</small></span></label>)}
        </div>
        {stale && !busy && <div className="group-warning">{t("fixtures.staleGroup")}<button type="button" disabled={!!target && !groups.some(g=>g.id===target.id)} onClick={()=>load(target ? groups.find(g=>g.id===target.id) : null)}>{t("fixtures.reloadGroup")}</button>{target && !groups.some(g=>g.id===target.id) && <span>{t("fixtures.deletedElsewhere")}</span>}</div>}
        {error && <p role="alert" className="group-error">{t("fixtures.saveError", { error: errorMessage(error, t) })}</p>}
        <footer className="group-form-footer"><span>{t("fixtures.localOnly")}</span><Action type="button" disabled={busy} onClick={onClose}>{t("common.cancel")}</Action><Action type="submit" variant="primary" disabled={busy || !bridge.ready("group_save") || !label.trim() || stale}>{busy ? t("common.saving") : t("fixtures.saveGroup")}</Action></footer>
      </form>}
    </div>
  </Modal>;
}

export default function FixturesWorkspace({state, visuals, onSelect, onSelectGroup, onEditor, onDeleted, onSelectAll}) {
  const { language, t } = useLanguage();
  const fixtures=state.config?.fixtures || [], groups=state.config?.groups || [], ready=bridge.ready("select_fixtures"), groupReady=bridge.ready("group_save"),
    deleteReady=bridge.ready("group_delete");
  const [scope,setScope]=useState("all"), [query,setQuery]=useState(""), [confirm,setConfirm]=useState(null);
  const [error,setError]=useState(""), [busy,setBusy]=useState(false);
  const [deleteRevision,setDeleteRevision]=useState(null);
  const deleteLock=useRef(false);
  const allGroups = selectionGroups(state.config, t);
  const local = allGroups.filter(isLocal), deskGroups = allGroups.filter(g => !isLocal(g));
  const active=scope.startsWith("group:") ? allGroups.find(g=>`group:${g.id}`===scope) : null;
  useEffect(()=>{if(scope.startsWith("group:") && !allGroups.some(g=>`group:${g.id}`===scope))setScope("all");},[scope,state.config]);
  const filtered=fixtures.filter(f=>(scope==="all" || scope===`type:${kind(f,visuals)}` || active?.fixtures?.includes(f.id)) && matches(f,query,visuals,t));
  const title=active?.label || (scope.startsWith("type:") ? t(`kind.${scope.slice(5)}`) : t("shell.allFixtures"));
  async function remove() {
    if(deleteLock.current)return;
    deleteLock.current=true;setBusy(true);setError("");
    try {await bridge.action({a:"group_delete",id:confirm.id,config_revision:deleteRevision});onDeleted(confirm.id);setConfirm(null);setScope("all");}
    catch(e){setError(e);}finally{deleteLock.current=false;setBusy(false);}
  }
  function closeGroupActions(button) {
    const menu = button.closest("details");
    menu.open = false;
    menu.querySelector("summary").focus();
  }
  function nav(g){return <button key={g.id} title={g.label} aria-pressed={scope===`group:${g.id}`} onClick={()=>{setScope(`group:${g.id}`);setQuery("");}}><span className="group-emblem" style={{"--group":groupColor(g)}}><Icon name={groupIcon(g)} size={16}/></span><span>{g.label}</span><small>{g.fixtures?.length || 0}</small></button>;}
  return <div className="fixtures-workspace">
    <aside className="fixture-navigation" aria-label={t("fixtures.categories")}>
      <button aria-pressed={scope==="all"} onClick={()=>{setScope("all");setQuery("");}}><Icon name="fixtures"/><span>{t("shell.allFixtures")}</span><small>{fixtures.length}</small></button>
      <h3>{t("shell.byType")}</h3>{FIXTURE_KINDS.map(k=>{const count=fixtures.filter(f=>kind(f,visuals)===k).length;return count>0 && <button key={k} aria-pressed={scope===`type:${k}`} onClick={()=>{setScope(`type:${k}`);setQuery("");}}><FixtureGlyph kind={k} size={22}/><span>{t(`kind.${k}`)}</span><small>{count}</small></button>;})}
      <h3>{t("fixtures.myGroups")} <button aria-label={t("fixtures.newGroup")} disabled={!groupReady} onClick={()=>onEditor({mode:"create",ids:[]})}><Icon name="plus" size={16}/></button></h3>
      {local.map(nav)}{!local.length && <p className="muted">{t("fixtures.createHint")}</p>}
      {!!deskGroups.length && <><h3>{t("fixtures.consoleGroups")} <Icon name="link" size={13}/></h3>{deskGroups.map(nav)}<p className="muted">{t("fixtures.readOnlyHint")}</p></>}
    </aside>
    <section className="fixture-catalog">
      <header className="fixture-section-head"><div>{active && <span className="eyebrow">{isLocal(active) ? t("fixtures.localGroup") : t("fixtures.consoleGroup")}</span>}<h2>{title}</h2><p>{t(active ? "fixtures.countInGroup" : "fixtures.countInCatalog", { fixtures: t("shell.fixtureCount", { count: active?.fixtures?.length ?? filtered.length }) })}</p></div>
        {active && isLocal(active) && <details className="group-actions" data-shortcut-layer key={active.id}><summary aria-label={t("fixtures.groupActions")}><Icon name="more"/></summary><div>
          <button disabled={!groupReady} onClick={e=>{closeGroupActions(e.currentTarget);onEditor({group:active});}}><Icon name="settings"/>{t("fixtures.editAppearance")}</button>
          <button className="danger" disabled={!deleteReady} onClick={e=>{closeGroupActions(e.currentTarget);setConfirm(active);setDeleteRevision(state.config.revision);setError("");}}><Icon name="close"/>{t("fixtures.deleteGroup")}</button>
        </div></details>}
      </header>
      {active && <div className="group-primary-actions">{isLocal(active) && <><Action variant="primary" disabled={!groupReady} onClick={()=>onEditor({group:active})}><Icon name="plus"/>{t("fixtures.addFixtures")}</Action><Action disabled={!groupReady} onClick={()=>onEditor({group:active})}>{t("fixtures.editMembers")}</Action></>}<Action disabled={!availableGroupIds(active, fixtures).length} onClick={()=>onSelectGroup(active)}>{t("fixtures.selectGroup")}</Action></div>}
      <div className="catalog-toolbar">
        <div className="catalog-search">
          <InternationalizationProvider locale={language} overrides={{
            [language]: {
              "@astryx.textInput.clearLabel": t("fixtures.clearSearch"),
              "@astryx.inputClearButton.tooltip": t("fixtures.clearSearch"),
            },
          }}>
            <TextInput
              type="search"
              enterKeyHint="search"
              size="lg"
              controlClassName="catalog-search-control"
              label={t("fixtures.find")}
              isLabelHidden
              placeholder={t("fixtures.searchPlaceholder")}
              startIcon={<Icon name="search"/>}
              value={query}
              onChange={setQuery}
              hasClear
            />
          </InternationalizationProvider>
        </div>
        <Action disabled={!filtered.some(f=>!f.missing)} onClick={()=>onSelectAll(filtered.filter(f=>!f.missing).map(f=>f.id))}>{t("fixtures.selectAll")}</Action>
      </div>
      <div className="catalog-caption"><span>{t("fixtures.results", { found: filtered.length, selected: state.selected.length })}<small>{t("fixtures.multiSelect")}</small></span><Action disabled={!groupReady || !state.selected.length || state.selecting} onClick={()=>onEditor({mode:"choose",ids:[...state.selected]})}>{t("fixtures.addToGroup")}<Icon name="plus" size={15}/></Action></div>
      <div className="fixture-grid">{filtered.map(f=><button key={f.id} data-catalog-fixture={f.id} disabled={f.missing} aria-pressed={state.selected.includes(f.id)} className={`fixture-card ${state.selected.includes(f.id) ? "selected" : ""}`} onClick={e=>onSelect(f.id,e.shiftKey)}>
        <span className="fixture-card-glyph"><FixtureGlyph kind={kind(f,visuals)} size={32}/></span><div><b>{f.label || f.id}</b><span>ID {String(f.id).padStart(2,"0")} · {t(`kind.${kind(f,visuals)}`)}</span><small>{[f.type, f.missing && t("fixtures.missing")].filter(Boolean).join(" · ")}</small><span className="fixture-memberships">{local.filter(g=>g.fixtures?.includes(f.id)).map(g=><span key={g.id} style={{"--group":groupColor(g)}}><Icon name={groupIcon(g)} size={10}/>{g.label}</span>)}</span></div><span className="selection-check">{state.selected.includes(f.id) && <Icon name="check" size={13}/>}</span>
      </button>)}</div>
      {!filtered.length && <Empty title={active && !active.fixtures?.length ? t("fixtures.emptyGroup") : t("fixtures.emptyCatalog")}>{active && !active.fixtures?.length ? t("fixtures.emptyGroupHint") : t("fixtures.emptyCatalogHint")}</Empty>}
    </section>
    {confirm && <Modal title={t("fixtures.confirmDelete")} onClose={()=>{if(!deleteLock.current)setConfirm(null);}}><div className="group-editor"><p>{t("fixtures.deleteHint", { name: confirm.label })}</p>{error && <p role="alert" className="group-error">{t("fixtures.deleteError", { error: errorMessage(error, t) })}</p>}<footer className="group-form-footer"><Action disabled={busy} onClick={()=>setConfirm(null)}>{t("common.cancel")}</Action><Action className="danger" disabled={busy || !deleteReady} onClick={remove}>{busy ? t("fixtures.deleting") : t("fixtures.deleteGroup")}</Action></footer></div></Modal>}
  </div>;
}
