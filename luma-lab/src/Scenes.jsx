import { useLanguage } from "./Language.jsx";
import { errorMessage } from "./errors.mjs";
import React, { useEffect, useId, useRef, useState } from "react";
import { Card } from "@astryxdesign/core/Card";
import { Action, Range, Empty, Modal } from "./ui.jsx";
import { Icon } from "./Icons.jsx";
import { bridge } from "./client.mjs";
import { sceneActive } from "./model.mjs";
const colors = [
  ["#f6b76c", "#ac5779"],
  ["#4c83ff", "#7966ed"],
  ["#a77bff", "#ff6aa5"],
  ["#f1dbb1", "#9a798c"],
  ["#ff5e77", "#a8558e"],
  ["#31a3a6", "#707ac4"],
];
const stoppingIds = new Set();
const stoppingTimers = new Map();
const stoppingListeners = new Set();
let launchingId = null;
let launchingTimer = null;

function notifyStopping() {
  stoppingListeners.forEach((fn) => fn());
}

function markSceneLaunching(id) {
  launchingId = id;
  clearTimeout(launchingTimer);
  launchingTimer = setTimeout(() => {
    launchingId = null;
    launchingTimer = null;
    notifyStopping();
  }, 1800);
  notifyStopping();
}

function clearSceneLaunching(id = null) {
  if (id !== null && launchingId !== id) return;
  clearTimeout(launchingTimer);
  launchingTimer = null;
  if (launchingId !== null) {
    launchingId = null;
    notifyStopping();
  }
}

function markSceneStopping(id, fadeSeconds = 0) {
  clearSceneLaunching(id);
  stoppingIds.add(id);
  clearTimeout(stoppingTimers.get(id));
  const waitMs = Math.max(4000, Math.round((Number(fadeSeconds || 0) + 3.5) * 1000));
  stoppingTimers.set(
    id,
    setTimeout(() => {
      stoppingTimers.delete(id);
      if (stoppingIds.delete(id)) notifyStopping();
    }, waitMs),
  );
  notifyStopping();
}

function clearSceneStopping(id) {
  clearTimeout(stoppingTimers.get(id));
  stoppingTimers.delete(id);
  if (stoppingIds.delete(id)) notifyStopping();
}

function useSceneTransitions(state) {
  const [, bump] = useState(0);
  useEffect(() => {
    const fn = () => bump((n) => n + 1);
    stoppingListeners.add(fn);
    return () => stoppingListeners.delete(fn);
  }, []);
  useEffect(() => {
    for (const id of [...stoppingIds]) {
      if (sceneActive(state, id) === false) {
        clearSceneStopping(id);
      }
    }
    if (launchingId && sceneActive(state, launchingId) === true) {
      clearSceneLaunching(launchingId);
    }
  }, [state.running, state.running_meta]);
  useEffect(() => {
    for (const id of [...stoppingIds]) {
      clearSceneStopping(id);
    }
    clearSceneLaunching();
  }, [state.config?.show]);
  return { stopping: stoppingIds, launching: launchingId };
}

export function LiveSceneBar({ state, slots = [], persistent = false }) {
  const { t } = useLanguage();
  const { stopping, launching } = useSceneTransitions(state);
  const offBlock = bridge.blockReason("scene_off");
  const scenes = state.config?.scenes || [];
  let activeScenes = scenes.filter(
    (scene) => sceneActive(state, scene.id) === true || stopping.has(scene.id),
  );
  if (!activeScenes.length && launching) {
    const nextScene = scenes.find((scene) => scene.id === launching);
    if (nextScene) activeScenes = [nextScene];
  }
  if (!activeScenes.length && !persistent) return null;
  async function stopScene(scene) {
    if (stopping.has(scene.id)) return;
    markSceneStopping(scene.id, state.config?.scene_fade);
    try {
      await bridge.action({
        a: "scene_off",
        id: scene.id,
        scene_identity: scene.identity,
        config_revision: state.config.revision,
      });
    } catch (e) {
      clearSceneStopping(scene.id);
      bridge.report(e);
    }
  }
  const isLive = activeScenes.length > 0;
  return (
    <div
      className={`live-scenes-bar ${persistent ? "persistent" : ""} ${isLive ? "live" : "idle"}`.trim()}
      role="region"
      aria-label={t("scenes.onAir")}
    >
      <span className="live-scenes-badge">
        <i className="live-pulse" aria-hidden="true" />
        <span>{isLive ? t("scenes.onAir") : t("scenes.standby")}</span>
      </span>
      {isLive ? (
        <div className="live-scenes-list">
          {activeScenes.map((scene) => {
            const index = scenes.indexOf(scene);
            const label = scene.label || t("scenes.unnamed", { index: index + 1 });
            const slot = slots.indexOf(scene.id) + 1;
            const isStopping = stopping.has(scene.id);
            const isSwitching = launching === scene.id && sceneActive(state, scene.id) !== true;
            return (
              <div className="live-scene-pill" key={scene.id}>
                {slot > 0 && <kbd title={t("shortcuts.sceneSlot", { slot })}>{slot}</kbd>}
                <span className="live-scene-name" title={`Executor ${scene.exec}`}>
                  <b>{label}</b>
                  <small>{scene.exec}</small>
                </span>
                <button
                  type="button"
                  className="live-stop-btn"
                  disabled={!!offBlock || isStopping || isSwitching}
                  title={errorMessage(offBlock, t) ?? t("scenes.stopName", { name: label })}
                  aria-label={t("scenes.stopName", { name: label })}
                  onClick={() => stopScene(scene)}
                >
                  <Icon name="stop" size={9} />
                  <span>{isStopping ? t("scenes.stopping") : t("scenes.stop")}</span>
                </button>
              </div>
            );
          })}
        </div>
      ) : (
        <span className="live-scenes-idle-text">{t("scenes.idleAir")}</span>
      )}
    </div>
  );
}
export function SceneCards({ state, slots, full = false }) {
  const { t } = useLanguage();
  const [pending, setPending] = useState(null);
  const { stopping } = useSceneTransitions(state);
  const goBlock = bridge.blockReason("scene_go"),
    offBlock = bridge.blockReason("scene_off");
  async function run(a, scene) {
    if (a === "scene_off") {
      if (stopping.has(scene.id)) return;
      markSceneStopping(scene.id, state.config?.scene_fade);
      try {
        await bridge.action({ a, id: scene.id, scene_identity: scene.identity, config_revision: state.config.revision });
      } catch (e) {
        clearSceneStopping(scene.id);
        bridge.report(e);
      }
      return;
    }
    clearSceneStopping(scene.id);
    markSceneLaunching(scene.id);
    setPending(scene.id);
    try {
      await bridge.action({ a, id: scene.id, scene_identity: scene.identity, config_revision: state.config.revision });
    } catch (e) {
      clearSceneLaunching(scene.id);
      bridge.report(e);
    } finally {
      setPending(null);
    }
  }
  const scenes = state.config?.scenes || [];
  if (!scenes.length)
    return (
      <Empty title={t("scenes.empty")}>
        {t("scenes.emptyHint")}
      </Empty>
    );
  return (
    <div className={`scene-grid ${full ? "full" : ""}`}>
      {scenes.map((scene, i) => {
        const active = sceneActive(state, scene.id),
          palette = colors[i % colors.length],
          slot = slots.indexOf(scene.id) + 1,
          label = scene.label || t("scenes.unnamed", { index: i + 1 }),
          isStopping = stopping.has(scene.id);
        return (
          <Card
            key={scene.id}
            className={`scene-card ${active === true ? "active" : ""}`}
            style={{ "--scene-a": palette[0], "--scene-b": palette[1] }}
          >
            <button
              className="scene-launch"
              disabled={!!goBlock || pending !== null}
              aria-label={t("scenes.play", { name: label })}
              onClick={() => run("scene_go", scene)}
              title={errorMessage(goBlock, t) ?? t("scenes.executorHint", { executor: scene.exec })}
            >
              <div className="scene-art">
                <svg viewBox="0 0 180 92" aria-hidden="true">
                  <defs>
                    <linearGradient id={`scene-${i}`} x2=".3" y2="1">
                      <stop stopColor={palette[0]} stopOpacity=".48" />
                      <stop offset="1" stopColor={palette[1]} stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <path
                    d="M20 16H160L176 80H4Z"
                    fill="#141722"
                    stroke="#a1a0b6"
                    strokeOpacity=".16"
                  />
                  <path
                    d={`M29 10 95 81H7Z M82 10 139 81H41Z M145 10 175 81H89Z`}
                    fill={`url(#scene-${i})`}
                  />
                  <ellipse
                    cx="85"
                    cy="75"
                    rx="59"
                    ry="8"
                    fill={palette[0]}
                    opacity=".13"
                  />
                  {[29, 82, 145].map((x) => (
                    <rect
                      key={x}
                      x={x - 4}
                      y="7"
                      width="8"
                      height="4"
                      rx="1"
                      fill={palette[0]}
                    />
                  ))}
                </svg>
                {slot > 0 && <kbd className="scene-hotkey" title={t("shortcuts.sceneSlot", { slot })}>{slot}</kbd>}
                <span className="scene-play">
                  <Icon name="play" size={14} />
                </span>
              </div>
              <div className="scene-info">
                <div className="scene-title-row">
                  <b>{label}</b>
                  {slot > 0 && !full && (
                    <kbd className="scene-inline-key" title={t("shortcuts.sceneSlot", { slot })}>
                      {slot}
                    </kbd>
                  )}
                </div>
                <span>
                  <i className={active === true ? "active-dot" : active === false ? "inactive-dot" : "unknown-dot"} />
                  {isStopping
                    ? t("scenes.stopping")
                    : pending === scene.id
                      ? t("scenes.pending")
                      : active === true
                        ? t("scenes.active")
                        : active === false
                          ? t("scenes.inactive")
                          : t("scenes.unknown")}
                </span>
              </div>
            </button>
            <div className={`scene-detail ${!full ? "compact" : ""} ${active === true || isStopping ? "is-live" : ""}`}>
              <span className="scene-detail-meta">
                {full
                  ? `Executor ${scene.exec}`
                  : active === true || isStopping
                    ? t("scenes.onAir")
                    : scene.exec}
              </span>
              <button
                type="button"
                className={`scene-stop-btn ${active === true || isStopping ? "is-live" : "is-idle"} ${!full && active !== true && !isStopping ? "is-ghost-slot" : ""}`}
                tabIndex={!full && active !== true && !isStopping ? -1 : undefined}
                aria-hidden={!full && active !== true && !isStopping ? true : undefined}
                disabled={!!offBlock || isStopping || pending !== null || (!full && active !== true && !isStopping)}
                title={errorMessage(offBlock, t) ?? t("scenes.stopName", { name: label })}
                aria-label={t("scenes.stopName", { name: label })}
                onClick={() => run("scene_off", scene)}
              >
                <Icon name="stop" size={9} />
                <span>{isStopping ? t("scenes.stopping") : t("scenes.stop")}</span>
              </button>
            </div>
          </Card>
        );
      })}
    </div>
  );
}
let slotRequestSeq = 0;

export function RecordSceneModal({ state, onClose }) {
  const { t } = useLanguage();
  const nameId = useId();
  const pageId = useId();
  const fixtures = state.config?.fixtures || [];
  const selectedFixtures = fixtures.filter((f) => state.selected.includes(f.id) && !f.missing);
  const storeExecs = state.status?.safety?.store || [];
  const mode = state.status?.safety?.mode;
  const storePages = [...new Set(storeExecs.map((ex) => Number(String(ex).split(".")[0])).filter((n) => Number.isInteger(n) && n >= 1 && n <= 999))].sort((a, b) => a - b);
  const defaultPage = storePages[0] || Number(state.config?.pages?.[0]?.n) || 1;
  const [name, setName] = useState("");
  const [page, setPage] = useState(defaultPage);
  const [requestId, setRequestId] = useState(null);
  const [localError, setLocalError] = useState("");
  const [saving, setSaving] = useState(false);
  const activeRequest = useRef(null);
  const consumed = useRef(false);

  const slot = requestId && state.sceneSlot?.request === requestId ? state.sceneSlot : null;
  const findBlock = bridge.blockReason("scene_slot_find");
  const createBlock = bridge.blockReason("scene_create");
  const highlightBusy = state.status?.highlight?.state && state.status.highlight.state !== "idle";
  const trimmedName = name.trim();
  const hasQuotes = trimmedName.includes('"');
  const pageInt = Number(page);
  const validPage = Number.isInteger(pageInt) && pageInt >= 1 && pageInt <= 999;

  function cancelOffer(req = activeRequest.current) {
    if (!req || consumed.current) return;
    activeRequest.current = null;
    if (bridge.state.connected && !bridge.blockReason("scene_slot_cancel")) {
      bridge.action({ a: "scene_slot_cancel", request: req }).catch(() => {});
    }
  }

  useEffect(() => {
    return () => {
      cancelOffer();
    };
  }, []);

  async function findSlot() {
    setLocalError("");
    if (!validPage) {
      setLocalError(t("scenes.recordInvalidPage"));
      return;
    }
    if (findBlock) {
      setLocalError(errorMessage(findBlock, t));
      return;
    }
    cancelOffer();
    const nextReq = `luma-slot-${Date.now()}-${++slotRequestSeq}`;
    consumed.current = false;
    activeRequest.current = nextReq;
    setRequestId(nextReq);
    try {
      await bridge.action({ a: "scene_slot_find", request: nextReq, page: pageInt });
    } catch (e) {
      activeRequest.current = null;
      setLocalError(errorMessage(e, t) || e.message || String(e));
    }
  }

  async function recordScene(event) {
    event.preventDefault();
    setLocalError("");
    if (!trimmedName || hasQuotes) {
      setLocalError(t(hasQuotes ? "scenes.recordNoQuotes" : "scenes.recordNameRequired"));
      return;
    }
    if (!selectedFixtures.length) {
      setLocalError(t("scenes.recordSelectFixtures"));
      return;
    }
    if (highlightBusy) {
      setLocalError(t("scenes.recordHighlightActive"));
      return;
    }
    if (slot?.state !== "ready" || !slot.exec || !slot.token) {
      setLocalError(t("scenes.recordFindFirst"));
      return;
    }
    setSaving(true);
    const offerPage = Number(String(slot.exec).split(".")[0]) || pageInt;
    try {
      await bridge.control({
        a: "scene_create",
        label: trimmedName,
        page: offerPage,
        exec: slot.exec,
        confirm: slot.exec,
        token: slot.token,
      });
      consumed.current = true;
      activeRequest.current = null;
      onClose();
    } catch (e) {
      consumed.current = true;
      activeRequest.current = null;
      setRequestId(null);
      setLocalError(e.err || errorMessage(e, t) || e.message || String(e));
    } finally {
      setSaving(false);
    }
  }

  const searching = slot?.state === "searching";
  const readyOffer = slot?.state === "ready" && slot.exec && slot.token;
  const canRecord =
    !saving &&
    !createBlock &&
    !highlightBusy &&
    selectedFixtures.length > 0 &&
    Boolean(trimmedName) &&
    !hasQuotes &&
    Boolean(readyOffer);

  return (
    <Modal title={t("scenes.recordTitle")} onClose={() => { cancelOffer(); onClose(); }}>
      <form className="record-scene-form" onSubmit={recordScene}>
        <p className="muted">{t("scenes.recordIntro")}</p>
        {(findBlock || createBlock) && (
          <div className="record-scene-alert" role="alert">
            {errorMessage(findBlock || createBlock, t)}
          </div>
        )}
        {highlightBusy && (
          <div className="record-scene-alert" role="alert">
            {t("scenes.recordHighlightActive")}
          </div>
        )}
        <div className="record-scene-selection">
          <span>{t("scenes.recordSelected")}</span>
          {selectedFixtures.length > 0 ? (
            <strong>
              {t("shell.fixtureCount", { count: selectedFixtures.length })}
              <small>
                {" · "}
                {selectedFixtures.slice(0, 4).map((f) => `#${f.id} ${f.label}`).join(", ")}
                {selectedFixtures.length > 4 ? ` +${selectedFixtures.length - 4}` : ""}
              </small>
            </strong>
          ) : (
            <strong className="warn">{t("scenes.recordSelectFixtures")}</strong>
          )}
        </div>
        <div className="record-scene-grid">
          <label htmlFor={nameId}>
            <span>{t("scenes.recordName")}</span>
            <input
              id={nameId}
              type="text"
              maxLength={30}
              autoComplete="off"
              disabled={saving}
              placeholder={t("scenes.recordNamePlaceholder")}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
            {hasQuotes && <small className="field-err">{t("scenes.recordNoQuotes")}</small>}
          </label>
          <label htmlFor={pageId}>
            <span>{t("scenes.recordPage")}</span>
            <input
              id={pageId}
              type="number"
              min={1}
              max={999}
              step={1}
              disabled={saving || searching}
              value={page}
              onChange={(e) => {
                const next = e.target.value;
                setPage(next === "" ? "" : Number(next));
                if (activeRequest.current) {
                  cancelOffer();
                  setRequestId(null);
                }
              }}
            />
            {mode === "store" && storePages.length > 0 && (
              <small className="muted">{t("scenes.recordAllowedPages", { pages: storePages.join(", ") })}</small>
            )}
          </label>
        </div>

        <div className="record-slot-box" role="status" aria-live="polite">
          <div className="record-slot-row">
            <div>
              <span className="record-slot-label">{t("scenes.recordTargetSlot")}</span>
              {readyOffer ? (
                <strong className="record-slot-exec">Executor {slot.exec}</strong>
              ) : searching ? (
                <span className="record-slot-status">
                  {t("scenes.recordSearching", { checked: slot.checked || 0, total: slot.total || 0 })}
                </span>
              ) : (
                <span className="record-slot-status">{t("scenes.recordNoSlotYet")}</span>
              )}
            </div>
            <Action
              type="button"
              disabled={saving || searching || !!findBlock || !validPage}
              onClick={findSlot}
            >
              <Icon name="search" size={14} />
              {readyOffer ? t("scenes.recordSearchAgain") : t("scenes.recordFindSlot")}
            </Action>
          </div>
          {readyOffer && <small className="record-slot-safe">{t("scenes.recordNoOverwriteHint")}</small>}
          {slot?.state === "error" && (
            <p className="record-scene-err" role="alert">{slot.err || t("error.action_failed")}</p>
          )}
        </div>

        {localError && (
          <div className="record-scene-err" role="alert">{localError}</div>
        )}

        <div className="record-scene-actions">
          <Action type="button" onClick={() => { cancelOffer(); onClose(); }}>
            {t("common.cancel")}
          </Action>
          <Action type="submit" variant="primary" disabled={!canRecord}>
            <Icon name="check" size={14} />
            {saving ? t("scenes.recording") : t("scenes.recordConfirm")}
          </Action>
        </div>
      </form>
    </Modal>
  );
}

export default function Scenes({ state, slots, onRecord, onClassicEditor, onShortcuts }) {
  const { t } = useLanguage();
  const recordBlock = bridge.blockReason("scene_slot_find") || bridge.blockReason("scene_create");
  return (
    <>
      <div className="section-heading">
        <div>
          <h2>
            {t("scenes.library")} <span>{state.config?.scenes?.length || 0}</span>
          </h2>
          <p>{t("scenes.readback")}</p>
        </div>
        <div className="button-row">
          <Action onClick={onShortcuts}>
            <Icon name="keyboard" />
            {t("scenes.assignKeys")}
          </Action>
          <Action
            variant="primary"
            title={errorMessage(recordBlock, t)}
            onClick={onRecord}
          >
            <Icon name="plus" />
            {t("scenes.recordScene")}
          </Action>
          {onClassicEditor && (
            <button type="button" className="text-button classic-fallback-btn" onClick={onClassicEditor}>
              {t("scenes.classicEditor")}
              <Icon name="arrow" size={13} />
            </button>
          )}
        </div>
      </div>
      <LiveSceneBar state={state} slots={slots} persistent />
      <div className="scene-fade">
        <Range
          label={t("scenes.fade")}
          value={state.config?.scene_fade ?? null}
          max={30}
          step={0.5}
          suffix={` ${t("common.secondsUnit")}`}
          disabled={!bridge.ready("scene_fade")}
          onCommit={(fade) =>
            bridge
              .action({ a: "scene_fade", fade })
              .catch((e) => bridge.report(e))
          }
        />
        <p>
          {t("scenes.fadeHint")}
        </p>
      </div>
      <SceneCards state={state} slots={slots} full />
    </>
  );
}
