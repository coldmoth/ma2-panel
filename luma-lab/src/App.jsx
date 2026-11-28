import React, { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { bridge } from "./client.mjs";
import { Icon } from "./Icons.jsx";
import { Action, Range, Modal, ErrorDetails, useStored } from "./ui.jsx";
import FixturesWorkspace, { GroupEditor, groupColor, groupIcon, selectionGroups, availableGroupIds } from "./FixturesWorkspace.jsx";
import Stage from "./Stage.jsx";
import LayoutWorkspace from "./LayoutWorkspace.jsx";
import Inspector from "./Inspector.jsx";
import InspectorDock, { useInspectorSize } from "./InspectorDock.jsx";
import Scenes, { LiveSceneBar, RecordSceneModal, SceneCards } from "./Scenes.jsx";
import Settings, { LegacyFrame } from "./Settings.jsx";
import OnboardingWizard from "./OnboardingWizard.jsx";
import useHotkeys from "./useHotkeys.jsx";
import { FIXTURE_KINDS, fixtureKind } from "./model.mjs";
import { useLanguage } from "./Language.jsx";
import { errorMessage } from "./errors.mjs";
const NAV = ["hall", "fixtures", "scenes", "layout", "settings"];
const PAGE_SUBTITLE = {
  fixtures: "shell.subtitleFixtures",
  scenes: "shell.subtitleScenes",
  layout: "shell.subtitleLayout",
  settings: "shell.subtitleSettings",
};
export default function App() {
  const { t } = useLanguage();
  const inspectorSize = useInspectorSize();
  const state = useSyncExternalStore(bridge.subscribe, bridge.getSnapshot),
    [page, setPage] = useState("hall"),
    [settingsTab, setSettingsTab] = useState("interface"),
    [bridgeVersion, setBridgeVersion] = useState(""),
    [collapsed, setCollapsed] = useStored("sidebarCollapsed", false),
    [top, setTop] = useStored("topView", false),
    [ids, setIds] = useStored("showIds", true),
    [beams, setBeams] = useStored("showBeams", true),
    [tools, setTools] = useStored("tools", {}),
    [step, setStep] = useStored("moveStep", 0.15),
    [fade, setFade] = useStored("colorFade", 0),
    [visualSettings, setVisualSettings] = useStored("visualOverrides", {}),
    [shortcutSettings, setShortcutSettings] = useStored("sceneShortcuts", {}),
    [modal, setModal] = useState(null),
    [armed, setArmed] = useState(false),
    [groupLabel, setGroupLabel] = useState(""),
    [groupEditor, setGroupEditor] = useState(null),
    [editorPlan, setEditorPlan] = useState(null),
    [planNotice, setPlanNotice] = useState(null),
    [quickScenes, setQuickScenes] = useState(false),
    [hallDraft, setHallDraft] = useState(null),
    [undoing, setUndoing] = useState(false),
    [releasingHighlight, setReleasingHighlight] = useState(false),
    [wizardOpen, setWizardOpen] = useState(() => {
      try {
        return new URLSearchParams(window.location.search).get("setup") === "1";
      } catch {
        return false;
      }
    }),
    [wizardDismissed, setWizardDismissed] = useState(false);
  const selectedGroup = useRef(null), announcedPlan = useRef(null), autoWizardChecked = useRef(false);
  useEffect(() => {
    bridge.connect();
    return () => bridge.disconnect();
  }, []);
  useEffect(() => {
    if (__LUMA_HALL_VERSION__) return undefined;
    const abort = new AbortController();
    fetch("/api/diag", { signal: abort.signal, cache: "no-store" })
      .then((res) => (res.ok ? res.json().catch(() => null) : null))
      .then((data) => {
        if (data?.version) setBridgeVersion(data.version);
      })
      .catch(() => {});
    return () => abort.abort();
  }, []);
  function openSettings(tab = "interface") {
    setSettingsTab(tab);
    setPage("settings");
  }
  useEffect(() => {
    if (wizardOpen || wizardDismissed || autoWizardChecked.current) return;
    if (!state.status) return;
    if (state.status.mock === true) {
      autoWizardChecked.current = true;
      return;
    }
    const isLocal = ["localhost", "127.0.0.1", "[::1]", "::1"].includes(window.location.hostname);
    if (!isLocal) {
      autoWizardChecked.current = true;
      return;
    }
    autoWizardChecked.current = true;
    fetch("/api/settings", { cache: "no-store" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        const host = String(data?.settings?.ma2?.host ?? "").trim();
        if (!host || host === "ma2-unconfigured.invalid") {
          setWizardOpen(true);
        }
      })
      .catch(() => {});
  }, [state.status, wizardOpen, wizardDismissed]);
  const config = state.config,
    fixtures = config?.fixtures || [],
    groups = config?.groups || [],
    show = config?.show || "unknown",
    visuals = visualSettings[show] || {},
    scenes = config?.scenes || [],
    assignments = Array.isArray(shortcutSettings?.[show]) ? shortcutSettings[show] : [],
    slots = assignments.map((saved) => saved && scenes.find((scene) =>
      scene.identity && scene.identity === saved.identity && scene.id === saved.id && scene.exec === saved.exec)),
    invalidSlots = assignments.map((saved, i) => Boolean(saved && !slots[i])),
    slotIds = slots.map((scene) => scene?.id),
    selectionBlock = bridge.blockReason("select_fixtures"),
    ready = !selectionBlock;
  const hallGroups = selectionGroups(config, t);
  const draft = hallDraft?.context === bridge.context ? hallDraft : null;
  const draftIds = draft?.ids.filter(id => fixtures.some(f => f.id === id && !f.missing));
  useEffect(() => {
    if (hallDraft && !draft) setHallDraft(null);
  }, [hallDraft, draft]);
  const editorReady = editorPlan === show;
  useEffect(() => {
    selectedGroup.current = null;
    setGroupLabel("");
    setGroupEditor(null);
    setEditorPlan(null);
    setQuickScenes(false);
    setModal(value => ["recordScene", "sceneEditor", "preparation"].includes(value) ? null : value);
  }, [show]);

  const protectPlan = page === "layout" || !!groupEditor;
  const hallTrial = state.status?.hall_trial === true;
  const canProtect = state.connected && (state.status?.mock === true || hallTrial) && !!config;
  useEffect(() => {
    if (!protectPlan) {
      setEditorPlan(null);
      return;
    }
    if (!canProtect) return;
    let current = true;
    bridge.action({ a: "plan_editing", active: true }).then(() => {
      if (current) setEditorPlan(show);
    }).catch(error => {
      if (current) bridge.report(error);
    });
    return () => {
      current = false;
      if (bridge.state.connected) bridge.action({ a: "plan_editing", active: false }).catch(error => bridge.report(error));
    };
  }, [protectPlan, canProtect, show]);

  const planSelection = state.status?.plan_selection;
  useEffect(() => {
    if (planSelection?.state !== "loaded" || planSelection.name !== config?.show ||
        planSelection.revision === announcedPlan.current) return;
    announcedPlan.current = planSelection.revision;
    setPlanNotice({ name: planSelection.name, revision: planSelection.revision });
  }, [planSelection, config?.show]);
  useEffect(() => {
    if (!planNotice) return;
    const timer = setTimeout(() => setPlanNotice(null), 4500);
    return () => clearTimeout(timer);
  }, [planNotice]);
  useEffect(() => {
    const chosen = selectedGroup.current;
    if (!chosen || !config) return;
    const group = hallGroups.find(g => g.id === chosen.id);
    if (!group || JSON.stringify(group.fixtures || []) !== chosen.members ||
        String(availableGroupIds(group, fixtures)) !== String(chosen.ids)) {
      selectedGroup.current = null;
      setGroupLabel("");
      if (String(bridge.state.selected) === String(chosen.ids) && !bridge.state.selecting) bridge.forgetSelection();
    } else setGroupLabel(group.label);
  }, [config]);
  useHotkeys({
    state,
    step,
    slots,
    invalidSlots,
    onArm: setArmed,
    onHelp: () => setModal("shortcuts"),
    enabled: !wizardOpen && page !== "settings" && page !== "layout",
    movementEnabled: tools.pos !== false,
  });
  function action(a) {
    return bridge.action(a).catch((e) => bridge.report(e));
  }
  function select(id, shift) {
    selectedGroup.current = null;
    setGroupLabel("");
    const next = shift
      ? state.selected.includes(id)
        ? state.selected.filter((i) => i !== id)
        : [...state.selected, id]
      : [id];
    bridge.select(next).catch((e) => bridge.report(e));
  }
  function selectGroup(group) {
    if (page !== "hall" && page !== "fixtures") setPage("hall");
    return applySelection(availableGroupIds(group, fixtures), group);
  }
  async function applySelection(ids, group, { confirm = false } = {}) {
    const context = bridge.context;
    try {
      await bridge.select(ids, { confirm });
      if (bridge.context !== context || String(bridge.state.selected) !== String(ids)) return false;
      const current = group && selectionGroups(bridge.state.config, t).find(g => g.id === group.id);
      const members = JSON.stringify(group?.fixtures || []);
      if (group && (!current || JSON.stringify(current.fixtures || []) !== members ||
          String(availableGroupIds(current, bridge.state.config.fixtures)) !== String(ids))) {
        selectedGroup.current = null;
        setGroupLabel("");
        bridge.forgetSelection();
        return false;
      }
      selectedGroup.current = current ? { id: current.id, members, ids } : null;
      setGroupLabel(current?.label || "");
      return true;
    } catch (error) {
      bridge.report(error);
      return false;
    }
  }
  function toggleHallFixture(id, shift) {
    if (!draft) return select(id, shift);
    if (bridge.state.selecting || !fixtures.some(f => f.id === id && !f.missing)) return;
    setHallDraft(current => current && ({
      ...current,
      ids: current.ids.includes(id) ? current.ids.filter(i => i !== id) : [...current.ids, id],
    }));
  }
  const allCounts = Object.fromEntries(
    FIXTURE_KINDS.map((k) => [
      k,
      fixtures.filter((f) => (visuals[f.id] || fixtureKind(f)) === k).length,
    ]),
  );
  const phase = state.status?.blackout?.phase,
    blackoutUnknown = phase && !["idle", "active"].includes(phase),
    blackoutActive = phase === "active",
    blackoutBlock = bridge.blockReason("blackout"),
    masterBlock = bridge.blockReason("master"),
    undoBlock = bridge.blockReason("undo"),
    highlightOffBlock = bridge.blockReason("highlight_off");
  const hl = state.status?.highlight || { state: "idle", target: null, reason: "", zone: [], release_token: null };
  const hlState = hl.state || "idle";
  const hlFixture = hl.target != null ? fixtures.find((f) => f.id === hl.target) : null;
  async function turnOffHighlight(releaseToken = undefined) {
    if (releasingHighlight || highlightOffBlock) return;
    setReleasingHighlight(true);
    try {
      const payload = releaseToken ? { a: "highlight_off", release_token: releaseToken } : { a: "highlight_off" };
      await bridge.action(payload);
      if (releaseToken) setModal((m) => (m === "releaseHighlight" ? null : m));
    } catch (e) {
      bridge.report(e);
    } finally {
      setReleasingHighlight(false);
    }
  }
  const actionHistory = Array.isArray(state.actionHistory) ? state.actionHistory : [];
  const latestUndo = [...actionHistory].reverse().find((entry) => entry && entry.undo && !entry.done && entry.undo_state !== "in_progress") || null;
  const lastHistoryEntry = actionHistory.length ? actionHistory[actionHistory.length - 1] : null;
  const undoDisabled = undoing || !!undoBlock || !latestUndo || !!draft;
  const undoTitle = undoBlock
    ? errorMessage(undoBlock, t)
    : latestUndo
      ? t("shell.undoAction", { action: latestUndo.what || latestUndo.a })
      : lastHistoryEntry?.reason
        ? t("shell.undoUnavailableReason", { reason: lastHistoryEntry.reason })
        : t("shell.undoEmpty");
  async function runUndo() {
    if (undoDisabled || !latestUndo) return;
    setUndoing(true);
    try {
      await bridge.action({ a: "undo", n: latestUndo.n });
    } catch (e) {
      bridge.report(e);
    } finally {
      setUndoing(false);
    }
  }
  const planIssue = ["show_mismatch", "show_unbound"].includes(selectionBlock?.code);
  const deskShow = state.status?.readiness?.show?.name;
  const showLabel = t(deskShow ? "shell.show" : "shell.showPending", { deskShow, planShow: config?.show || "—" });
  const planDecision = planSelection?.state === "operator" ? planSelection : null;
  const planMessage = errorMessage(planDecision || selectionBlock, t);
  const canCreatePlan = planDecision?.code === "plan_missing" && !protectPlan && !bridge.blockReason("show_open_plan");
  const inspectorWorkspace = page === "hall" || page === "fixtures";
  const inspected = fixtures.filter(f => state.selected.includes(f.id));
  const inspectorGroup = groupLabel === null ? t("shell.allFixtures") : groupLabel?.kind ? t(`kind.${groupLabel.kind}`) : groupLabel;
  const masterEvidence = state.masterEvidence || {quality:"unknown"};
  return (
    <div
      ref={inspectorSize.shell}
      className={`shell ${collapsed ? "collapsed" : ""} ${hallTrial ? "hall-trial" : ""}`}
    >
      <aside className="sidebar" inert={!!draft}>
        <div className="brand">
          <div className="brand-mark">
            <svg width="25" height="25" viewBox="0 0 24 24" fill="none">
              <path
                d="M5 4v16h14 M10 4v11h9 M15 4v6h4"
                stroke="currentColor"
                strokeWidth="2.3"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
          </div>
          {!collapsed && (
            <div>
              <strong>
                LUMA{!hallTrial && <span>LAB</span>}
              </strong>
              <small>{t("shell.lightingControl")}</small>
            </div>
          )}
        </div>
        <button
          className="collapse-button"
          aria-label={t(collapsed ? "nav.expand" : "nav.collapse")}
          onClick={() => setCollapsed(!collapsed)}
        >
          <Icon name={collapsed ? "expand" : "collapse"} size={15} />
        </button>
        <nav className="main-nav" aria-label={t("nav.main")}>
          {NAV.map((id) => {
            const label = t(`nav.${id}`);
            return <button
              key={id}
              title={collapsed ? label : undefined}
              aria-label={label}
              aria-current={page === id ? "page" : undefined}
              className={page === id ? "active" : ""}
              onClick={() => {
                setPage(id);
              }}
            >
              <Icon name={id} />
              {!collapsed && <span>{label}</span>}
              {!collapsed && page === id && <i />}
            </button>
          })}
        </nav>
        {!collapsed && page !== "fixtures" && (
          <div className="sidebar-groups">
            <div className="nav-caption">
              {t("shell.groups")}
              <button
                aria-label={t("shell.createGroup")}
                disabled={!bridge.ready("group_save") || !state.selected.length}
                onClick={() => setGroupEditor({mode:"create",ids:[...state.selected]})}
              >
                <Icon name="plus" size={14} />
              </button>
            </div>
            <button
              className={
                state.selected.length === fixtures.length && fixtures.length
                  ? "selected"
                  : ""
              }
              onClick={() => {
                selectedGroup.current = null;
                setGroupLabel(null);
                bridge
                  .select(fixtures.filter((f) => !f.missing).map((f) => f.id))
                  .catch((e) => bridge.report(e));
              }}
              disabled={!fixtures.length}
            >
              <span className="group-square" style={{ "--group": "#b09be8" }} />
              {t("shell.allFixtures")}<small aria-label={t("shell.fixtureCount", { count: fixtures.length })}>{t("shell.number", { value: fixtures.length })}</small>
            </button>
            {groups.map((group, i) => (
              <button
                key={group.id}
                disabled={!group.fixtures?.length}
                className={
                  groupLabel === group.label && state.selected.length
                    ? "selected"
                    : ""
                }
                onClick={() => selectGroup(group)}
              >
                {group.icon ? <span style={{color:groupColor(group)}}><Icon name={groupIcon(group)} size={14}/></span> : <span className="group-square" style={{"--group":group.color || ["#9e8cef","#e287c5","#d6bb8e","#7ab7b0"][i % 4]}}/>}
                <span>{group.label}</span>
                <small>{t("shell.number", { value: group.fixtures?.length || 0 })}</small>
              </button>
            ))}
            <div className="auto-caption">{t("shell.byType")}</div>
            {Object.entries(allCounts)
              .filter(([, n]) => n > 0)
              .map(([kind, n]) => (
                <button
                  key={kind}
                  onClick={() => {
                    selectedGroup.current = null;
                    setGroupLabel({ kind });
                    bridge
                      .select(
                        fixtures
                          .filter(
                            (f) =>
                              (visuals[f.id] || fixtureKind(f)) === kind &&
                              !f.missing,
                          )
                          .map((f) => f.id),
                      )
                      .catch((e) => bridge.report(e));
                  }}
                >
                  <span className="group-square outline" />
                  {t(`kind.${kind}`)}
                  <small>{t("shell.number", { value: n })}</small>
                </button>
              ))}
          </div>
        )}
        <div className="sidebar-bottom">
          <button
            className="help-button"
            title={t("common.shortcuts")}
            aria-label={t("common.shortcuts")}
            onClick={() => setModal("shortcuts")}
          >
            <Icon name="keyboard" />
            {!collapsed && (
              <>
                {t("common.shortcuts")}<kbd>?</kbd>
              </>
            )}
          </button>
          <div className="lab-badge">
            <span className="status-led" />
            {!collapsed && (
              <>
                <b>{t(hallTrial ? "shell.hallTrial" : "shell.mockLab")}</b>
                {!hallTrial && <small>{t("shell.noHardware")}</small>}
              </>
            )}
          </div>
          {!collapsed && (
            <div className="sidebar-version">
              <span>ma2-panel</span>
              <span>{__LUMA_HALL_VERSION__ || bridgeVersion || "3.4.0"}</span>
            </div>
          )}
        </div>
      </aside>
      <header className="global-bar">
        <div className={`connection-pill ${ready ? "online" : ""}`}>
          <span className="status-led" />
          <span>
            {t(ready ? hallTrial ? "shell.liveReady" : "shell.selectionReady" : bridge.connectionKey())}
          </span>
        </div>
        <span className="show-name" title={deskShow && deskShow === config?.show ? `${showLabel} · ${t("shell.showMatched")}` : showLabel}>{showLabel}</span>
        {hallTrial && (
          <div className="hall-header-links">
            {state.status.manual && (
              <Action onClick={() => action({ a: "link_connect" })}>{t("shell.connectMa2")}</Action>
            )}
            <a className="help-button" href="/index.html">{t("shell.classic")}</a>
          </div>
        )}
        <div className="global-actions">
          {hlState !== "idle" && (
            <div
              className={`highlight-pill ${hlState}`}
              role="status"
              title={hlState === "stuck" ? (hl.reason || t("layout.highlightStuckDefault")) : t("shell.highlightActiveTitle", { target: hlFixture ? `#${hlFixture.id} ${hlFixture.label}` : `#${hl.target ?? "?"}` })}
            >
              <Icon name="sun" size={14} />
              <span>
                {hlState === "stuck"
                  ? t("shell.highlightStuckBadge")
                  : t("shell.highlightActiveBadge", { id: hl.target ?? "?" })}
              </span>
              <button
                type="button"
                disabled={releasingHighlight || !!highlightOffBlock}
                title={errorMessage(highlightOffBlock, t)}
                onClick={() => (hlState === "stuck" ? setModal("releaseHighlight") : turnOffHighlight())}
              >
                {hlState === "stuck" ? t("shell.highlightRelease") : t("shell.highlightOff")}
              </button>
            </div>
          )}
          <button
            type="button"
            className="undo-btn"
            disabled={undoDisabled}
            title={undoTitle}
            aria-label={latestUndo ? t("shell.undoAction", { action: latestUndo.what || latestUndo.a }) : t("shell.undo")}
            onClick={runUndo}
          >
            <Icon name="reset" size={14} />
            <span>{undoing ? t("shell.undoing") : t("shell.undo")}</span>
          </button>
          <div className="grandmaster" title={errorMessage(masterBlock, t)}>
            <Icon name="sun" size={16} />
            <Range
              label={t("tool.master")}
              value={masterEvidence.value ?? null}
              evidence={masterEvidence.quality}
              disabled={!!masterBlock || blackoutActive || !!draft}
              onCommit={(v) => action({ a: "master", v })}
            />
          </div>
          <button
            className={`blackout ${blackoutActive ? "active" : ""} ${armed ? "armed" : ""}`}
            disabled={!!blackoutBlock}
            title={errorMessage(blackoutBlock, t)}
            onClick={() => action({ a: "blackout" })}
          >
            <Icon name="power" size={16} />
            <span>
              {blackoutUnknown
                ? t("shell.checkMa2")
                : blackoutActive
                  ? t("shell.restore")
                  : armed
                    ? t("shell.pressBAgain")
                    : "Blackout"}
            </span>
            <kbd>B</kbd>
          </button>
        </div>
      </header>
      <div className={`workspace ${inspectorWorkspace ? "inspector-workspace" : ""}`}
        style={{ "--inspector-width": `${inspectorSize.width}px` }}>
        <main className={`main page-${page}`}>
          {page !== "hall" && <div className="page-heading">
            <div>
              <div className="eyebrow">
                LUMA /{" "}
                {String(NAV.indexOf(page) + 1).padStart(
                  2,
                  "0",
                )}
              </div>
              <h1>{t(`nav.${page}`)}</h1>
              <p>{PAGE_SUBTITLE[page] && t(PAGE_SUBTITLE[page])}</p>
            </div>
            {page === "hall" && (
              <div className="hall-summary">
                <span>
                  {t("shell.number", { value: fixtures.length })}
                  <small>{t("shell.fixtureCountLabel", { count: fixtures.length })}</small>
                </span>
                <span>
                  {t("shell.number", { value: groups.length })}
                  <small>{t("shell.groupCountLabel", { count: groups.length })}</small>
                </span>
                <span>
                  {t("shell.number", { value: scenes.length })}
                  <small>{t("shell.sceneCountLabel", { count: scenes.length })}</small>
                </span>
              </div>
            )}
            {page === "layout" && (
              <Action onClick={() => openSettings("preparation")}>
                {t("common.preparation")}
                <Icon name="arrow" size={15} />
              </Action>
            )}
          </div>}
          {planNotice && planNotice.name === config?.show && (
            <div className="inline-notice" role="status">{t("shell.planLoaded", { deskShow: planNotice.name })}</div>
          )}
          {hlState === "stuck" && (
            <div className="error-banner highlight-stuck-banner" role="alert">
              <Icon name="sun" />
              <span>
                {t("shell.highlightStuckBanner", { reason: hl.reason || t("layout.highlightStuckDefault") })}
              </span>
              <button
                type="button"
                disabled={releasingHighlight || !!highlightOffBlock}
                onClick={() => setModal("releaseHighlight")}
              >
                {t("shell.highlightRelease")}
              </button>
            </div>
          )}
          {state.skippedOff?.length > 0 && (
            <div className="error-banner" role="alert">
              {t("scenes.skippedOff", { executors: state.skippedOff.map(item => item.executor).join(", ") })}
            </div>
          )}
          {(state.error || planMessage || blackoutUnknown) && (
            <div className="error-banner" role="alert">
              <Icon name="info" />
              <span>
                {errorMessage(state.error, t) || planMessage ||
                  errorMessage(blackoutBlock, t)}
              </span>
              {!state.error && canCreatePlan && (
                <button onClick={() => setModal({ createPlanFor: deskShow })}>{t("shell.createPlan")}</button>
              )}
              {!state.error && planDecision && !bridge.blockReason("show_identify") && (
                <button onClick={() => action({ a: "show_identify" })}>{t("common.checkAgain")}</button>
              )}
              {(state.status?.mock === true || hallTrial || state.error) && (
                <button
                  onClick={() =>
                    openSettings((planDecision || planIssue) && !state.error ? "preparation" : "diagnostics")
                  }
                >
                  {t((planDecision || planIssue) && !state.error ? "common.preparation" : "common.diagnostics")}
                </button>
              )}
              {state.error && (
                <button
                  aria-label={t("common.dismiss")}
                  onClick={() => bridge.publish({ error: null })}
                >
                  <Icon name="close" size={14} />
                </button>
              )}
            </div>
          )}
          {armed && (
            <div className="arm-banner" role="status">
              {t("shell.blackoutArmed")}
            </div>
          )}
          {page === "hall" && (
            <>
              <Stage
                key={show}
                {...{
                  state,
                  top,
                  setTop,
                  ids,
                  setIds,
                  beams,
                  setBeams,
                  visuals,
                }}
                selection={draftIds ?? state.selected}
                onSelect={toggleHallFixture}
                groupOptions={hallGroups}
                selectionReady={ready} clearReady={bridge.ready("clear")}
                onSelectGroup={selectGroup}
                draftIds={draftIds}
                onStartDraft={() => {
                  setQuickScenes(false);
                  setHallDraft({ context: bridge.context, ids: bridge.state.selected });
                }}
                onCancelDraft={() => setHallDraft(null)}
                onApplyDraft={async () => {
                  if (!draft || bridge.state.selecting || bridge.context !== draft.context) return false;
                  if (!await applySelection(draftIds, null, { confirm: true })) return false;
                  setHallDraft(null);
                  return true;
                }}
              />
              <LiveSceneBar state={state} slots={slotIds} persistent inert={!!draft} />
              <div inert={!!draft} className={`quick-scenes ${quickScenes ? "open" : ""}`} data-shortcut-layer={quickScenes ? "" : undefined}>
                {quickScenes && <div className="quick-scenes-content" id="quick-scenes-content">
                  <div className="quick-scenes-head">
                    <button type="button" className="text-button" onClick={() => setModal("shortcuts")}>
                      <Icon name="keyboard" size={14} /> {t("scenes.assignKeys")}
                    </button>
                    <button type="button" className="text-button" onClick={()=>setPage("scenes")}>{t("scenes.all")} <Icon name="arrow" size={14}/></button>
                  </div>
                  <SceneCards state={state} slots={slotIds} />
                </div>}
                <button className="quick-scenes-toggle" data-shortcut-dismiss aria-expanded={quickScenes} aria-controls="quick-scenes-content" onClick={()=>setQuickScenes(v=>!v)}>
                  <Icon name="scenes" size={16}/><span>{t("scenes.quick")}</span><small>{scenes.length}</small><Icon name={quickScenes ? "chevronDown" : "chevronUp"} size={16} className="quick-scenes-caret" />
                </button>
              </div>
            </>
          )}
          {page === "fixtures" && <FixturesWorkspace key={show} {...{state,visuals}} onSelect={select} onSelectGroup={selectGroup} onEditor={setGroupEditor}
            onSelectAll={ids=>{selectedGroup.current=null;setGroupLabel("");bridge.select(ids).catch(e=>bridge.report(e));}}
            onDeleted={()=>{}}/>}
          {page === "scenes" && (
            <Scenes
              key={show}
              state={state}
              slots={slotIds}
              onRecord={() => setModal("recordScene")}
              onClassicEditor={state.status?.mock === true ? () => setModal("sceneEditor") : undefined}
              onShortcuts={() => setModal("shortcuts")}
            />
          )}
          {page === "layout" && editorReady && <LayoutWorkspace key={show} {...{state,visuals}} onVisualSaved={id=>{if(visuals[id])setVisualSettings(old=>({...old,[show]:{...old[show],[id]:undefined}}));}}/>}
          {page === "settings" && (
            <Settings
              {...{
                state,
                tools,
                setTools,
                top,
                setTop,
                beams,
                setBeams,
                ids,
                setIds,
              }}
              section={settingsTab}
              onSectionChange={setSettingsTab}
              onShortcuts={() => setModal("shortcuts")}
              onOpenWizard={() => setWizardOpen(true)}
            />
          )}
        </main>
        {inspectorWorkspace && (
          <InspectorDock size={inspectorSize} selected={inspected} show={show} groupLabel={inspectorGroup}
            selecting={state.selecting} selectionEditing={!!draft} onClear={() => {
              selectedGroup.current = null;
              setGroupLabel("");
              bridge.select([]).catch(e => bridge.report(e));
            }}>
            <Inspector
              key={`${show}:${state.selected.join(",")}`}
              {...{ state, step, setStep, tools, visuals, fade, setFade }}
              selected={inspected}
              groupLabel={inspectorGroup}
              selectionEditing={!!draft}
            />
          </InspectorDock>
        )}
      </div>
      {modal?.createPlanFor && (
        <Modal title={t("shell.confirmCreatePlan", { deskShow: modal.createPlanFor })} onClose={() => setModal(null)}>
          <Action onClick={() => setModal(null)}>{t("common.cancel")}</Action>
          <Action variant="primary" disabled={!canCreatePlan || deskShow !== modal.createPlanFor}
            onClick={() => {
              setModal(null);
              action({ a: "show_open_plan", name: modal.createPlanFor, create_only: true });
            }}>{t("common.confirm")}</Action>
        </Modal>
      )}
      {modal === "shortcuts" && (
        <Modal title={t("common.shortcuts")} onClose={() => setModal(null)}>
          <div className="shortcut-list">
            {[
              [t("shortcuts.shiftClick"), t("shortcuts.extendSelection")],
              ["Esc", t("common.clearSelection")],
              ["↑ ↓ ← →", t("shortcuts.nudge")],
              ["B, B", t("shortcuts.blackout")],
              [t("shortcuts.duringBlackout"), t("shortcuts.restore")],
            ].map(([key, text]) => (
              <div key={key}>
                <kbd>{key}</kbd>
                <span>{text}</span>
              </div>
            ))}
          </div>
          <h3>{t("scenes.quick")}</h3>
          <p className="muted">
            {t("shortcuts.slotHelp")}
          </p>
          <div className="shortcut-slots">
            {Array.from({ length: 9 }, (_, i) => (
              <label key={i}>
                <kbd>{i + 1}</kbd>
                <select
                  aria-label={t("shortcuts.sceneSlot", { slot: i + 1 })}
                  value={slots[i]?.id || ""}
                  onChange={(e) => {
                    const scene = scenes.find((row) => row.id === e.target.value && row.identity);
                    setShortcutSettings((previous) => {
                      const next = [...(Array.isArray(previous?.[show]) ? previous[show] : [])];
                      next[i] = scene ? { id: scene.id, identity: scene.identity, exec: scene.exec } : null;
                      return { ...previous, [show]: next };
                    });
                  }}
                >
                  <option value="">{t(invalidSlots[i] ? "shortcuts.invalidSlot" : "shortcuts.unassigned")}</option>
                  {scenes.filter((s) => s.identity).map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.label}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
          <p className="muted">
            {t("shortcuts.disabledHelp")}
          </p>
        </Modal>
      )}
      {modal === "releaseHighlight" && (
        <Modal title={t("shell.highlightReleaseTitle")} onClose={() => setModal(null)}>
          <p className="muted">{t("shell.highlightReleaseWarn", { count: hl.zone?.length || 0 })}</p>
          {hl.reason && <p className="record-scene-alert" role="status">{hl.reason}</p>}
          <div className="record-scene-actions">
            <Action type="button" onClick={() => setModal(null)}>{t("common.cancel")}</Action>
            <Action
              type="button"
              variant="primary"
              disabled={releasingHighlight || !!highlightOffBlock || hlState !== "stuck" || !hl.release_token}
              onClick={() => turnOffHighlight(hl.release_token)}
            >
              {releasingHighlight ? t("common.saving") : t("shell.highlightReleaseConfirm")}
            </Action>
          </div>
        </Modal>
      )}
      {modal === "recordScene" && (
        <RecordSceneModal key={show} state={state} onClose={() => setModal(null)} />
      )}
      {groupEditor && editorReady && <GroupEditor key={show} {...{state,visuals}} initial={groupEditor} onClose={()=>setGroupEditor(null)}/>}
      {state.status?.mock === true && modal === "sceneEditor" && (
        <Modal
          title={t("scenes.classicEditor")}
          onClose={() => setModal(null)}
        >
          <ErrorDetails error={state.error || selectionBlock} />
          <p className="muted">{t("settings.legacy")} · {t("settings.legacyScope")}</p>
          <LegacyFrame
            page="index.html"
            title={t("settings.legacy")}
            className="modal-frame"
          />
        </Modal>
      )}
      {wizardOpen && (
        <OnboardingWizard
          state={state}
          onClose={() => {
            setWizardOpen(false);
            setWizardDismissed(true);
          }}
          onOpenHall={() => {
            setWizardOpen(false);
            setWizardDismissed(true);
            setPage("hall");
          }}
          onOpenLayout={() => {
            setWizardOpen(false);
            setWizardDismissed(true);
            setPage("layout");
          }}
        />
      )}
    </div>
  );
}
