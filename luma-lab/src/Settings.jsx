import React, { useCallback, useEffect, useId, useRef, useState } from "react";
import { Badge } from "@astryxdesign/core/Badge";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Card } from "@astryxdesign/core/Card";
import { Collapsible } from "@astryxdesign/core/Collapsible";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { SelectableCard } from "@astryxdesign/core/SelectableCard";
import { Switch } from "@astryxdesign/core/Switch";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Action, ErrorDetails } from "./ui.jsx";
import { Icon } from "./Icons.jsx";
import { useLanguage } from "./Language.jsx";
import { bridge } from "./client.mjs";
import { errorMessage } from "./errors.mjs";
import {
  formatExecRange,
  formatFixtureRange,
  parseExecRange,
  parseFixtureRange,
} from "./allowlist.mjs";

const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);
const RESTART_TIMEOUT_MS = 25000;
const UPDATE_TERMINAL_PHASES = new Set(["idle", "completed", "rolled_back", "failed"]);
const UPDATE_KNOWN_PHASES = new Set([
  "idle",
  "manual",
  "downloading",
  "validated",
  "waiting",
  "installing",
  "starting",
  "verifying",
  "rolling_back",
  "completed",
  "rolled_back",
  "failed",
]);

export function formatRawReply(row) {
  if (typeof row === "string") return row;
  if (!row || typeof row !== "object") return String(row ?? "");
  if ("cmd" in row || "reply" in row || "status" in row) {
    const timePart = row.t ? `[${row.t}]` : "[--:--:--]";
    const statusPart = row.status ? `[${row.status}]` : "";
    const cmdPart = row.cmd ? String(row.cmd) : "";
    const cleanReply =
      row.reply != null && String(row.reply).trim() !== ""
        ? ` → ${String(row.reply).replace(/\r?\n+/g, " ⏎ ").trim()}`
        : "";
    return `${[timePart, statusPart, cmdPart].filter(Boolean).join(" ")}${cleanReply}`;
  }
  const timePart = row.t ? `[${row.t}]` : "";
  const dirPart = row.dir ? `[${row.dir}]` : "";
  const textPart = row.text || row.line || JSON.stringify(row);
  return [timePart, dirPart, textPart].filter(Boolean).join(" ");
}

const FRAME_CSS = `:root{color-scheme:dark;--bg:#10121b;--panel:#171a26;--line:#303044;--text:#ece9f5;--muted:#a09aaf;--accent:#b29bee}body{background:#10121b!important;color:#ece9f5!important;font-family:Inter,system-ui,sans-serif!important}.sx{max-width:1100px!important;padding:20px!important}h1{font-size:22px!important}fieldset,.importbox{border:1px solid #343043!important;border-radius:14px!important;background:#151721!important;padding:18px!important}input,select,textarea{background:#1c1c2a!important;color:#f0eafc!important;border-color:#484155!important;border-radius:7px!important}.btn,button{border-radius:8px!important;background:#2a253d!important;color:#d6c9fa!important;border-color:#4e426c!important}.muted,.t,.lbl,legend{color:#b9b0c7!important}a{color:#c2a9ff!important}.toplinks{display:none!important}details{border-color:#393145!important}table{background:#151721!important}th,td{border-color:#393145!important}`;

const LEGACY_BASE = __LUMA_HALL_VERSION__ ? "" : "/legacy";

export function LegacyFrame({
  page = "settings.html",
  title,
  className = "",
}) {
  const { t } = useLanguage();
  return (
    <iframe
      className={`legacy-frame ${className}`}
      src={`${LEGACY_BASE}/${page}`}
      title={title ?? t("settings.legacy")}
      onLoad={(e) => {
        try {
          const doc = e.currentTarget.contentDocument;
          if (!doc.getElementById("luma-frame-style")) {
            const s = doc.createElement("style");
            s.id = "luma-frame-style";
            s.textContent = FRAME_CSS;
            doc.head.appendChild(s);
          }
        } catch {}
      }}
    />
  );
}

export const SAFETY_FLAGS = [
  "allow_master",
  "allow_page_change",
  "allow_fixture_read",
  "allow_highlight",
  "allow_group_store",
  "allow_layout_import",
  "allow_show_load",
  "allow_show_save",
  "allow_patch",
  "allow_rdm",
];

export const SAFETY_PRESETS = [
  {
    id: "test",
    badgeVariant: "success",
    flags: Object.fromEntries(SAFETY_FLAGS.map((k) => [k, false])),
  },
  {
    id: "store",
    badgeVariant: "info",
    flags: {
      ...Object.fromEntries(SAFETY_FLAGS.map((k) => [k, false])),
      allow_fixture_read: true,
      allow_highlight: true,
      allow_group_store: true,
    },
  },
  {
    id: "full",
    badgeVariant: "warning",
    flags: {
      allow_master: true,
      allow_page_change: true,
      allow_fixture_read: true,
      allow_highlight: true,
      allow_group_store: true,
      allow_layout_import: true,
      allow_show_load: true,
      allow_show_save: true,
      allow_patch: true,
      allow_rdm: true,
    },
  },
];

const sections = [
  ["interface", "settings.interface", "layers"],
  ["system", "settings.system", "link"],
  ["diagnostics", "common.diagnostics", "info"],
  ["preparation", "common.preparation", "layout"],
];

function ClassicFallbackTools({ withEmbedded = false }) {
  const { t } = useLanguage();
  const [embedOpen, setEmbedOpen] = useState(false);
  const links = [
    { href: `${LEGACY_BASE}/index.html`, label: t("settings.proClassicPanel"), desc: t("settings.proClassicPanelDesc") },
    { href: `${LEGACY_BASE}/settings.html`, label: t("settings.proClassicSettings"), desc: t("settings.proClassicSettingsDesc") },
    { href: `${LEGACY_BASE}/diag.html`, label: t("settings.proClassicDiag"), desc: t("settings.proClassicDiagDesc") },
    { href: `${LEGACY_BASE}/log.html`, label: t("settings.proClassicLog"), desc: t("settings.proClassicLogDesc") },
  ];
  return (
      <Card variant="muted" padding={3} className="classic-tools-card">
        <Collapsible trigger={t("settings.backupClassicTools")} defaultIsOpen={false}>
          <div className="classic-tools-body">
            <p className="muted">{t("settings.proToolsHint")}</p>
            <div className="pro-tools-grid">
              {links.map((item) => (
                <a
                  key={item.href}
                  className="pro-tool-card"
                  href={item.href}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  <div>
                    <b>{item.label}</b>
                    <small>{item.desc}</small>
                  </div>
                  <Icon name="arrow" size={14} />
                </a>
              ))}
            </div>
            {withEmbedded && (
              <Collapsible
                trigger={t("settings.openEmbeddedClassic")}
                isOpen={embedOpen}
                onOpenChange={setEmbedOpen}
                className="classic-embed-collapsible"
              >
                {embedOpen && (
                  <div className="classic-embed-wrap">
                    <p className="muted">{t("settings.legacy")}</p>
                    <LegacyFrame page="index.html" title={t("settings.legacy")} />
                  </div>
                )}
              </Collapsible>
            )}
          </div>
        </Collapsible>
      </Card>
  );
}

function ProgramUpdateCard({ state, bridgeVersion, isLocal }) {
  const { t } = useLanguage();
  const isMock = Boolean(state.status?.mock);

  const [localOnly403, setLocalOnly403] = useState(false);
  const [phase, setPhase] = useState("idle");
  const [currentVersion, setCurrentVersion] = useState(
    bridgeVersion || __LUMA_HALL_VERSION__ || "3.4.0",
  );
  const [phaseError, setPhaseError] = useState("");
  const [message, setMessage] = useState("");
  const [available, setAvailable] = useState(null);
  const [compatibleInstallation, setCompatibleInstallation] = useState(false);
  const [testUpdates, setTestUpdates] = useState(false);
  const [channelReady, setChannelReady] = useState(false);
  const [posting, setPosting] = useState(false);
  const [checking, setChecking] = useState(false);
  const [starting, setStarting] = useState(false);
  const [channelSaving, setChannelSaving] = useState(false);

  const mountedRef = useRef(true);
  const pollTimerRef = useRef(null);
  const pollInFlightRef = useRef(false);
  const busyRef = useRef(false);

  useEffect(() => {
    if (bridgeVersion && !currentVersion) setCurrentVersion(bridgeVersion);
  }, [bridgeVersion, currentVersion]);

  const clearPoll = useCallback(() => {
    if (pollTimerRef.current) {
      clearTimeout(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const updateRequest = useCallback(async (url, post = false, body = undefined) => {
    const res = await fetch(
      url,
      post
        ? {
            method: "POST",
            headers: { "X-Update": "1", "Content-Type": "application/json" },
            body: body === undefined ? undefined : JSON.stringify(body),
          }
        : { cache: "no-store" },
    );
    if (res.status === 403) {
      const err = new Error(t("settings.updateLocalOnlyDesc"));
      err.status = 403;
      throw err;
    }
    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      const err = new Error(data.err || `HTTP ${res.status}`);
      err.status = res.status;
      throw err;
    }
    return data;
  }, [t]);

  const pollStatus = useCallback(async () => {
    if (!mountedRef.current || pollInFlightRef.current) return;
    pollInFlightRef.current = true;
    try {
      const data = await updateRequest("/api/update/status");
      if (!mountedRef.current) return;
      const nextPhase = UPDATE_KNOWN_PHASES.has(data.phase) ? data.phase : "idle";
      const isBusy = !UPDATE_TERMINAL_PHASES.has(nextPhase);
      busyRef.current = isBusy;
      setPhase(nextPhase);
      if (data.current) setCurrentVersion(data.current);
      setPhaseError(data.error ? String(data.error) : "");
      setMessage("");
      if (UPDATE_TERMINAL_PHASES.has(nextPhase)) {
        if (nextPhase !== "idle") setAvailable(null);
      }
      if (isBusy) {
        clearPoll();
        pollTimerRef.current = setTimeout(pollStatus, 1500);
      }
    } catch (error) {
      if (!mountedRef.current) return;
      if (error?.status === 403) {
        setLocalOnly403(true);
        busyRef.current = false;
        clearPoll();
        return;
      }
      if (busyRef.current) {
        setMessage(t("settings.updateWaitingReconnect"));
        clearPoll();
        // Never repeat POST /api/update/start after a lost response; poll persisted status only.
        pollTimerRef.current = setTimeout(pollStatus, 1500);
      } else {
        setPhaseError(error?.message || String(error));
      }
    } finally {
      pollInFlightRef.current = false;
    }
  }, [clearPoll, t, updateRequest]);

  useEffect(() => {
    mountedRef.current = true;
    if (!isLocal || isMock) {
      return () => {
        mountedRef.current = false;
        clearPoll();
      };
    }
    updateRequest("/api/update/channel")
      .then((data) => {
        if (!mountedRef.current) return;
        setTestUpdates(data.test_updates === true);
        setChannelReady(true);
      })
      .catch((error) => {
        if (!mountedRef.current) return;
        if (error?.status === 403) {
          setLocalOnly403(true);
        } else {
          setPhaseError(error?.message || String(error));
        }
      });
    pollStatus();
    return () => {
      mountedRef.current = false;
      clearPoll();
    };
  }, [clearPoll, isLocal, isMock, pollStatus, updateRequest]);

  const busy = !UPDATE_TERMINAL_PHASES.has(phase);
  const canStartUpdate =
    Boolean(compatibleInstallation) &&
    Boolean(available?.version) &&
    available.version !== currentVersion &&
    !busy &&
    !posting;

  async function handleChannelChange(checked) {
    if (busy || posting || !channelReady) return;
    const prev = testUpdates;
    setTestUpdates(checked);
    setPosting(true);
    setChannelSaving(true);
    setAvailable(null);
    setPhaseError("");
    setMessage("");
    try {
      await updateRequest("/api/update/channel", true, { test_updates: checked });
      if (!mountedRef.current) return;
      setMessage(t("settings.updateChannelSaved"));
    } catch (error) {
      if (!mountedRef.current) return;
      setTestUpdates(prev);
      if (error?.status === 403) {
        setLocalOnly403(true);
      } else {
        setPhaseError(error?.message || String(error));
      }
    } finally {
      if (mountedRef.current) {
        setPosting(false);
        setChannelSaving(false);
      }
    }
  }

  async function handleCheckUpdates() {
    if (busy || posting || !channelReady) return;
    setPosting(true);
    setChecking(true);
    setPhaseError("");
    setMessage("");
    try {
      const data = await updateRequest("/api/update/check", true);
      if (!mountedRef.current) return;
      if (data.current) setCurrentVersion(data.current);
      const found = data.available || null;
      const compatible = Boolean(data.compatible_installation);
      setAvailable(found);
      setCompatibleInstallation(compatible);
      if (!found) {
        setMessage(t("settings.updateUpToDate"));
      } else if (found.version === data.current) {
        setMessage(t("settings.updateUpToDate"));
      } else if (compatible) {
        setMessage(t("settings.updateReadyHint"));
      } else {
        setMessage(t("settings.updateIncompatibleHint"));
      }
    } catch (error) {
      if (!mountedRef.current) return;
      setAvailable(null);
      if (error?.status === 403) {
        setLocalOnly403(true);
      } else {
        setPhaseError(error?.message || String(error));
      }
    } finally {
      if (mountedRef.current) {
        setPosting(false);
        setChecking(false);
      }
    }
  }

  async function handleStartUpdate() {
    if (!canStartUpdate || !available?.version) return;
    const chosenVersion = available.version;
    setPosting(true);
    setStarting(true);
    busyRef.current = true;
    setPhaseError("");
    setMessage("");
    try {
      const data = await updateRequest("/api/update/start", true, { version: chosenVersion });
      if (!mountedRef.current) return;
      const nextPhase = UPDATE_KNOWN_PHASES.has(data.phase) ? data.phase : "downloading";
      busyRef.current = !UPDATE_TERMINAL_PHASES.has(nextPhase);
      setPhase(nextPhase);
      if (data.current) setCurrentVersion(data.current);
      if (data.error) setPhaseError(String(data.error));
      if (busyRef.current) {
        clearPoll();
        pollTimerRef.current = setTimeout(pollStatus, 1500);
      }
    } catch (error) {
      if (!mountedRef.current) return;
      if (error?.status === 403) {
        busyRef.current = false;
        setLocalOnly403(true);
      } else {
        // Never retry POST /api/update/start — only poll GET /api/update/status.
        setPhase("waiting");
        setMessage(t("settings.updateLostResponse"));
        clearPoll();
        pollTimerRef.current = setTimeout(pollStatus, 1500);
      }
    } finally {
      if (mountedRef.current) {
        setPosting(false);
        setStarting(false);
      }
    }
  }

  const phaseBadgeVariant =
    phase === "completed"
      ? "success"
      : phase === "failed"
        ? "error"
        : phase === "rolled_back" || phase === "rolling_back" || busy
          ? "warning"
          : "neutral";

  const statusText = message || t(`settings.updatePhase.${phase}`);

  return (
    <Card variant="default" padding={4} className="update-program-card">
      <div className="prep-card-head">
        <div className="settings-section-title">
          <Icon name="download" />
          <div>
            <h3>{t("settings.updateTitle")}</h3>
            <p>{t("settings.updateHint")}</p>
          </div>
        </div>
        <div className="update-card-badges">
          <Badge variant="neutral" label={t("settings.updateInstalledVersion", { version: currentVersion })} />
          {!isMock && isLocal && !localOnly403 && (
            <Badge variant={phaseBadgeVariant} label={t(`settings.updatePhaseBadge.${phase}`)} />
          )}
        </div>
      </div>

      {!isLocal || localOnly403 ? (
        <Banner
          status="info"
          title={t("settings.updateLocalOnlyTitle")}
          description={t("settings.updateLocalOnlyDesc")}
        />
      ) : isMock ? (
        <Banner
          status="info"
          title={t("settings.updateMockTitle")}
          description={t("settings.updateMockDesc")}
        />
      ) : (
        <div className="update-card-body">
          <div className="settings-row update-channel-row">
            <div>
              <b>{t("settings.updateTestChannel")}</b>
              <small>{t("settings.updateTestChannelDesc")}</small>
            </div>
            <Switch
              label={t("settings.updateTestChannel")}
              isLabelHidden
              value={testUpdates}
              isDisabled={busy || posting || !channelReady}
              isLoading={channelSaving}
              onChange={handleChannelChange}
            />
          </div>

          <p className="update-status-line" role="status">
            {statusText}
          </p>

          {phaseError && <Banner status="error" title={phaseError} />}

          {available && (
            <div className="update-available-box">
              <div className="update-available-head">
                <strong>{t("settings.updateAvailableVersion", { version: available.version })}</strong>
                <Badge
                  variant={available.version !== currentVersion ? "info" : "success"}
                  label={
                    available.version !== currentVersion
                      ? t("settings.updateNewBadge")
                      : t("settings.updateCurrentBadge")
                  }
                />
              </div>
              {available.notes && <p className="update-notes">{available.notes}</p>}
            </div>
          )}

          <div className="prep-actions-row">
            <Button
              type="button"
              label={t("settings.updateCheck")}
              variant="secondary"
              size="sm"
              isLoading={checking}
              isDisabled={busy || posting || !channelReady}
              onClick={handleCheckUpdates}
            />
            <Button
              type="button"
              label={t("settings.updateStart")}
              variant="primary"
              size="sm"
              isLoading={starting || busy}
              isDisabled={!canStartUpdate}
              onClick={handleStartUpdate}
            />
          </div>
        </div>
      )}
    </Card>
  );
}

function ConnectionSafetySection({ state, settingsData, settingsError, bridgeVersion, isLocal, onSaved, onOpenWizard }) {
  const { t } = useLanguage();
  const hostId = useId();
  const portId = useId();
  const userId = useId();
  const passId = useId();

  const [draft, setDraft] = useState(null);
  const [password, setPassword] = useState("");
  const [passwordTouched, setPasswordTouched] = useState(false);
  const [clearPassword, setClearPassword] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveNotice, setSaveNotice] = useState("");
  const [saveError, setSaveError] = useState("");
  const [restartNeeded, setRestartNeeded] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [restartError, setRestartError] = useState("");
  const [linkTesting, setLinkTesting] = useState(false);
  const [linkTestResult, setLinkTestResult] = useState(null);
  const [linkTestError, setLinkTestError] = useState("");
  const [linkBusy, setLinkBusy] = useState(false);

  const restartBaseRef = useRef(null);
  const restartIntervalRef = useRef(null);
  const restartTimeoutRef = useRef(null);
  const restartInFlightRef = useRef(false);

  const stopRestartWatch = useCallback(() => {
    restartBaseRef.current = null;
    restartInFlightRef.current = false;
    if (restartIntervalRef.current) {
      clearInterval(restartIntervalRef.current);
      restartIntervalRef.current = null;
    }
    if (restartTimeoutRef.current) {
      clearTimeout(restartTimeoutRef.current);
      restartTimeoutRef.current = null;
    }
    setRestarting(false);
  }, []);

  useEffect(() => () => stopRestartWatch(), [stopRestartWatch]);

  useEffect(() => {
    if (!settingsData?.settings) return;
    const ma2 = { ...(settingsData.defaults?.ma2 || {}), ...(settingsData.settings.ma2 || {}) };
    const safety = { ...(settingsData.defaults?.safety || {}), ...(settingsData.settings.safety || {}) };
    setDraft({
      host: ma2.host ?? "127.0.0.1",
      port: ma2.port ?? 30000,
      user: ma2.user ?? "Remote",
      auto_launch: ma2.auto_launch !== false,
      mode: safety.mode ?? "test",
      flags: Object.fromEntries(SAFETY_FLAGS.map((k) => [k, Boolean(safety[k])])),
      allowed_fixtures_text: formatFixtureRange(safety.allowed_fixtures || []),
      allowed_scenes_text: formatExecRange(safety.allowed_scenes || []),
      store_execs_text: formatExecRange(safety.store_execs || []),
    });
    setPassword("");
    setPasswordTouched(false);
    setClearPassword(false);
  }, [settingsData]);

  const ma2State = state.status?.ma2 || "down";
  const loginInfo = state.status?.login || null;
  const deskShow = state.status?.readiness?.show?.name || null;
  const showState = state.status?.readiness?.show?.state || "pending";
  const planShow = state.config?.show || "—";
  const fixtures = state.config?.fixtures || [];
  const scenes = state.config?.scenes || [];
  const connectBlock = bridge.blockReason("link_connect");
  const dropBlock = bridge.blockReason("link_drop");
  const identifyBlock = bridge.blockReason("show_identify");

  const fixturesCheck = draft ? parseFixtureRange(draft.allowed_fixtures_text) : { ok: true, values: [] };
  const scenesCheck = draft ? parseExecRange(draft.allowed_scenes_text) : { ok: true, values: [] };
  const storeCheck = draft ? parseExecRange(draft.store_execs_text) : { ok: true, values: [] };
  const showAllowlists = draft && (draft.mode === "test" || draft.mode === "store");
  const allowlistsHaveEmpty =
    Boolean(showAllowlists) &&
    ((fixturesCheck.ok && fixturesCheck.values.length === 0) ||
      (scenesCheck.ok && scenesCheck.values.length === 0) ||
      (draft.mode === "store" && storeCheck.ok && storeCheck.values.length === 0));

  async function runWsAction(payload) {
    setLinkBusy(true);
    try {
      await bridge.action(payload);
    } catch (e) {
      bridge.report(e);
    } finally {
      setLinkBusy(false);
    }
  }

  async function runLinkTest() {
    if (!isLocal) return;
    setLinkTesting(true);
    setLinkTestError("");
    try {
      const res = await fetch("/api/diag/link_test", { method: "POST" });
      if (res.status === 403) {
        throw new Error(t("settings.loopbackOnlyAction"));
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        throw new Error(data.err || `HTTP ${res.status}`);
      }
      setLinkTestResult(data);
    } catch (e) {
      setLinkTestError(e.message || String(e));
    } finally {
      setLinkTesting(false);
    }
  }

  async function restartBridge() {
    if (!isLocal || restarting) return;
    setRestartError("");
    try {
      const res = await fetch("/api/restart", {
        method: "POST",
        headers: { "X-Stop": "1" },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        throw new Error(data.err || `HTTP ${res.status}`);
      }
      stopRestartWatch();
      restartBaseRef.current = data.instance || "pending";
      setRestarting(true);
      setSaveNotice(t("settings.restartingBridge"));

      const pollOnce = async () => {
        if (restartInFlightRef.current || !restartBaseRef.current) return;
        restartInFlightRef.current = true;
        try {
          const setupRes = await fetch("/api/setup", {
            cache: "no-store",
            signal: AbortSignal.timeout(4000),
          });
          if (!setupRes.ok) return;
          const setupJson = await setupRes.json().catch(() => ({}));
          if (setupJson.instance && setupJson.instance !== restartBaseRef.current) {
            stopRestartWatch();
            setRestartNeeded(false);
            setSaveNotice(t("settings.bridgeRestarted"));
            onSaved?.();
          }
        } catch {
          // Bridge is restarting; keep polling until timeout.
        } finally {
          restartInFlightRef.current = false;
        }
      };

      restartIntervalRef.current = setInterval(pollOnce, 1000);
      restartTimeoutRef.current = setTimeout(() => {
        stopRestartWatch();
        setRestartNeeded(true);
        setSaveNotice("");
        setRestartError(t("wizard.step1.restartTimeout"));
      }, RESTART_TIMEOUT_MS);
    } catch (e) {
      stopRestartWatch();
      setRestartError(e.message || String(e));
    }
  }

  async function saveSettings(event) {
    event.preventDefault();
    if (!draft || !settingsData?.settings || saving || restarting) return;
    setSaving(true);
    setSaveNotice("");
    setSaveError("");
    setRestartError("");
    try {
      const parsedFixtures = parseFixtureRange(draft.allowed_fixtures_text);
      if (!parsedFixtures.ok) {
        throw new Error(t("settings.allowlistInvalidFixtures", { token: parsedFixtures.invalid }));
      }
      const parsedScenes = parseExecRange(draft.allowed_scenes_text);
      if (!parsedScenes.ok) {
        throw new Error(t("settings.allowlistInvalidScenes", { token: parsedScenes.invalid }));
      }
      const parsedStore = parseExecRange(draft.store_execs_text);
      if (!parsedStore.ok) {
        throw new Error(t("settings.allowlistInvalidStore", { token: parsedStore.invalid }));
      }

      const next = structuredClone(settingsData.settings);
      next.ma2 = {
        ...(next.ma2 || {}),
        host: draft.host.trim(),
        port: Number(draft.port),
        user: draft.user,
        auto_launch: Boolean(draft.auto_launch),
      };
      next.safety = {
        ...(next.safety || {}),
        mode: draft.mode,
        ...draft.flags,
        allowed_fixtures: parsedFixtures.values,
        allowed_scenes: parsedScenes.values,
        store_execs: parsedStore.values,
      };
      const body = { settings: next, clear_password: clearPassword };
      if (passwordTouched && password) body.password = password;
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) {
        throw new Error(data.err || `HTTP ${res.status}`);
      }
      setSaveNotice(t("settings.savedRestartNeeded"));
      setRestartNeeded(true);
      setPassword("");
      setPasswordTouched(false);
      setClearPassword(false);
      onSaved?.();
    } catch (e) {
      setSaveError(e.message || String(e));
    } finally {
      setSaving(false);
    }
  }

  const ma2BadgeClass =
    ma2State === "logged_in"
      ? "ok"
      : ma2State === "tcp" || ma2State === "manual_off"
        ? "warn"
        : "bad";
  const showBadgeClass = showState === "matched" ? "ok" : showState === "pending" ? "warn" : "bad";

  return (
    <>
      <div className="section-heading">
        <div>
          <h2>{t("settings.system")}</h2>
          <p>{t("settings.nativeSystemHint")}</p>
        </div>
        {onOpenWizard && (
          <Button
            label={t("settings.openWizard")}
            variant="primary"
            size="sm"
            isDisabled={!isLocal}
            tooltip={!isLocal ? t("settings.loopbackOnlyAction") : undefined}
            onClick={onOpenWizard}
          />
        )}
      </div>
      {state.status?.mock && <div className="inline-notice">{t("settings.mockHint")}</div>}

      <section className="settings-section">
        <div className="settings-section-title">
          <Icon name="link" />
          <div>
            <h3>{t("settings.linkStatusTitle")}</h3>
            <p>{t("settings.linkStatusHint")}</p>
          </div>
        </div>
        <div className="native-status-grid">
          <div className="native-status-card">
            <small>{t("settings.statusTcpLogin")}</small>
            <strong className={`badge-${ma2BadgeClass}`}>
              {ma2State === "manual_off" ? t("wizard.step1.liveManualOffBadge") : t(bridge.connectionKey())}
            </strong>
            <span>{draft ? `${draft.host}:${draft.port}` : "—"}</span>
          </div>
          <div className="native-status-card">
            <small>{t("settings.statusUser")}</small>
            <strong>{loginInfo?.USER || draft?.user || "—"}</strong>
            <span>{loginInfo?.VERSION ? `MA2 ${loginInfo.VERSION}` : t("settings.statusNoVersion")}</span>
          </div>
          <div className="native-status-card">
            <small>{t("settings.statusShow")}</small>
            <strong className={`badge-${showBadgeClass}`}>{deskShow || t("settings.statusShowPending")}</strong>
            <span>{t("settings.statusLocalPlan", { plan: planShow })}</span>
          </div>
        </div>
        <div className="native-actions-row">
          <Action
            type="button"
            variant="primary"
            disabled={linkBusy || !!connectBlock}
            title={errorMessage(connectBlock, t)}
            onClick={() => runWsAction({ a: "link_connect" })}
          >
            <Icon name="reset" size={14} />
            {t("settings.reconnectMa2")}
          </Action>
          <Action
            type="button"
            disabled={linkBusy || !!dropBlock}
            title={errorMessage(dropBlock, t)}
            onClick={() => runWsAction({ a: "link_drop" })}
          >
            {t("settings.disconnectMa2")}
          </Action>
          <Action
            type="button"
            disabled={linkBusy || !!identifyBlock}
            title={errorMessage(identifyBlock, t)}
            onClick={() => runWsAction({ a: "show_identify" })}
          >
            {t("common.checkAgain")}
          </Action>
          <Action
            type="button"
            disabled={linkTesting || !isLocal}
            title={!isLocal ? t("settings.loopbackOnlyAction") : undefined}
            onClick={runLinkTest}
          >
            <Icon name="search" size={14} />
            {linkTesting ? t("settings.linkTesting") : t("settings.testLink")}
          </Action>
        </div>
        {linkTestError && <div className="record-scene-err" role="alert">{linkTestError}</div>}
        {linkTestResult && (
          <div className="link-test-result" role="status">
            <div>
              <b>{t("settings.linkTestResultTitle", { target: linkTestResult.target || "—" })}</b>
              <small>{linkTestResult.t} · {linkTestResult.state}</small>
            </div>
            <p>
              {typeof linkTestResult.bare_connect === "string"
                ? linkTestResult.bare_connect
                : linkTestResult.bare_connect
                  ? `${linkTestResult.bare_connect.end} (${linkTestResult.bare_connect.bytes ?? 0} B · ${linkTestResult.bare_connect.ms ?? 0} ms)`
                  : "OK"}
            </p>
          </div>
        )}
      </section>

      {settingsError ? (
        <section className="settings-section">
          <Banner
            status={isLocal ? "warning" : "info"}
            title={settingsError}
          />
        </section>
      ) : draft && (
        <form onSubmit={saveSettings}>
          <section className="settings-section">
            <div className="settings-section-title">
              <Icon name="settings" />
              <div>
                <h3>{t("settings.ma2ConnectionTitle")}</h3>
                <p>{t("settings.ma2ConnectionHint")}</p>
              </div>
            </div>
            <div className="native-form-grid">
              <label htmlFor={hostId}>
                <span>{t("settings.ma2Host")}</span>
                <input
                  id={hostId}
                  type="text"
                  required
                  disabled={saving || restarting}
                  value={draft.host}
                  onChange={(e) => setDraft((d) => ({ ...d, host: e.target.value }))}
                />
              </label>
              <label htmlFor={portId}>
                <span>{t("settings.ma2Port")}</span>
                <input
                  id={portId}
                  type="number"
                  min={1}
                  max={65535}
                  step={1}
                  required
                  disabled={saving || restarting}
                  value={draft.port}
                  onChange={(e) => setDraft((d) => ({ ...d, port: e.target.value }))}
                />
              </label>
              <label htmlFor={userId}>
                <span>{t("settings.ma2User")}</span>
                <input
                  id={userId}
                  type="text"
                  required
                  disabled={saving || restarting}
                  value={draft.user}
                  onChange={(e) => setDraft((d) => ({ ...d, user: e.target.value }))}
                />
              </label>
              <label htmlFor={passId}>
                <span>
                  {t("settings.ma2Password")}{" "}
                  <small className="muted">
                    ({settingsData?.password_set ? t("settings.passwordSet") : t("settings.passwordNotSet")})
                  </small>
                </span>
                <input
                  id={passId}
                  type="password"
                  autoComplete="new-password"
                  disabled={saving || restarting || clearPassword}
                  placeholder={t("settings.ma2PasswordPlaceholder")}
                  value={password}
                  onChange={(e) => {
                    setPassword(e.target.value);
                    setPasswordTouched(true);
                  }}
                />
              </label>
            </div>
            <label className="native-checkbox-row">
              <input
                type="checkbox"
                disabled={saving || restarting}
                checked={clearPassword}
                onChange={(e) => setClearPassword(e.target.checked)}
              />
              <span>{t("settings.clearPassword")}</span>
            </label>
            <div className="settings-row settings-autolaunch-row">
              <div>
                <b>{t("settings.ma2AutoLaunch")}</b>
                <small>{t("settings.ma2AutoLaunchDesc")}</small>
              </div>
              <Switch
                value={Boolean(draft.auto_launch)}
                label={t("settings.ma2AutoLaunch")}
                isLabelHidden
                isDisabled={saving || restarting}
                onChange={(value) => setDraft((d) => ({ ...d, auto_launch: value }))}
              />
            </div>
          </section>

          <section className="settings-section hall-view-settings">
            <div className="settings-section-title">
              <Icon name="power" />
              <div>
                <h3>{t("settings.safetyTitle")}</h3>
                <p>{t("settings.safetyHint")}</p>
              </div>
            </div>
            <div className="safety-mode-cards" role="radiogroup" aria-label={t("settings.safetyMode")}>
              {SAFETY_PRESETS.map((preset) => {
                const selected = draft.mode === preset.id;
                return (
                  <SelectableCard
                    key={preset.id}
                    label={t(`settings.preset.${preset.id}.title`)}
                    isSelected={selected}
                    isDisabled={saving || restarting}
                    padding={3}
                    className="safety-mode-card"
                    onChange={(isSelected) => {
                      if (isSelected) {
                        setDraft((d) => ({
                          ...d,
                          mode: preset.id,
                          flags: { ...preset.flags },
                        }));
                      }
                    }}
                  >
                    <div className="safety-card-head">
                      <strong>{t(`settings.preset.${preset.id}.title`)}</strong>
                      <Badge
                        variant={preset.badgeVariant}
                        label={t(`settings.preset.${preset.id}.badge`)}
                      />
                    </div>
                    <p className="safety-card-desc">{t(`settings.preset.${preset.id}.desc`)}</p>
                  </SelectableCard>
                );
              })}
            </div>
            {showAllowlists && (
              <div className="access-scope-block">
                <div className="access-scope-head">
                  <strong>{t("settings.accessScopeTitle")}</strong>
                  <small>{t("settings.accessScopeHint")}</small>
                </div>
                <div className="access-scope-grid">
                  <div className="allowlist-field-group">
                    <TextInput
                      label={t("settings.allowedFixtures")}
                      description={t("settings.allowedFixturesDesc")}
                      value={draft.allowed_fixtures_text}
                      onChange={(value) => setDraft((d) => ({ ...d, allowed_fixtures_text: value }))}
                      placeholder="1-20, 25"
                      isDisabled={saving || restarting}
                      status={
                        !fixturesCheck.ok
                          ? { type: "error", message: t("settings.allowlistInvalidFixtures", { token: fixturesCheck.invalid }) }
                          : undefined
                      }
                      size="md"
                      width="100%"
                    />
                    <Button
                      type="button"
                      label={t("settings.fillAllFromPlan")}
                      variant="secondary"
                      size="sm"
                      isDisabled={saving || restarting || fixtures.length === 0}
                      onClick={() =>
                        setDraft((d) => ({
                          ...d,
                          allowed_fixtures_text: formatFixtureRange(fixtures.map((f) => f.id)),
                        }))
                      }
                    />
                  </div>
                  <div className="allowlist-field-group">
                    <TextInput
                      label={t("settings.allowedScenes")}
                      description={t("settings.allowedScenesDesc")}
                      value={draft.allowed_scenes_text}
                      onChange={(value) => setDraft((d) => ({ ...d, allowed_scenes_text: value }))}
                      placeholder="1.101-1.110, 2.1"
                      isDisabled={saving || restarting}
                      status={
                        !scenesCheck.ok
                          ? { type: "error", message: t("settings.allowlistInvalidScenes", { token: scenesCheck.invalid }) }
                          : undefined
                      }
                      size="md"
                      width="100%"
                    />
                    <Button
                      type="button"
                      label={t("settings.fillAllFromPlan")}
                      variant="secondary"
                      size="sm"
                      isDisabled={saving || restarting || scenes.length === 0}
                      onClick={() =>
                        setDraft((d) => ({
                          ...d,
                          allowed_scenes_text: formatExecRange(scenes.map((s) => s.exec)),
                        }))
                      }
                    />
                  </div>
                  {draft.mode === "store" && (
                    <div className="allowlist-field-group">
                      <TextInput
                        label={t("settings.storeExecs")}
                        description={t("settings.storeExecsDesc")}
                        value={draft.store_execs_text}
                        onChange={(value) => setDraft((d) => ({ ...d, store_execs_text: value }))}
                        placeholder="1.101-1.120"
                        isDisabled={saving || restarting}
                        status={
                          !storeCheck.ok
                            ? { type: "error", message: t("settings.allowlistInvalidStore", { token: storeCheck.invalid }) }
                            : undefined
                        }
                        size="md"
                        width="100%"
                      />
                    </div>
                  )}
                </div>
                {allowlistsHaveEmpty && (
                  <Banner
                    status="warning"
                    title={t("settings.allowlistEmptyTitle")}
                    description={t("settings.allowlistEmptyDesc")}
                  />
                )}
              </div>
            )}
            {draft.mode === "full" && (
              <div className="safety-full-banner">
                <Banner
                  status="warning"
                  title={t("settings.fullModeBannerTitle")}
                  description={t("settings.fullModeWarning")}
                />
              </div>
            )}
            <Collapsible
              trigger={t("settings.fineGrainedPermissions")}
              defaultIsOpen={false}
              className="safety-collapsible"
            >
              <div className="safety-flags-grid">
                {SAFETY_FLAGS.map((flag) => (
                  <div className="settings-row" key={flag}>
                    <div>
                      <b>{t(`settings.flag.${flag}`)}</b>
                      <small>{t(`settings.flagDesc.${flag}`)}</small>
                    </div>
                    <Switch
                      value={Boolean(draft.flags[flag])}
                      label={t(`settings.flag.${flag}`)}
                      isLabelHidden
                      isDisabled={saving || restarting}
                      onChange={(value) =>
                        setDraft((d) => ({ ...d, flags: { ...d.flags, [flag]: value } }))
                      }
                    />
                  </div>
                ))}
              </div>
            </Collapsible>
          </section>

          {saveError && <Banner status="error" title={saveError} className="prep-banner" />}
          {restartError && <Banner status="error" title={restartError} className="prep-banner" />}
          {saveNotice && (
            <Banner
              status={restartNeeded ? "warning" : "success"}
              title={saveNotice}
              className="prep-banner"
              endContent={
                restartNeeded ? (
                  <Button
                    type="button"
                    label={t("settings.restartBridge")}
                    variant="primary"
                    size="sm"
                    isLoading={restarting}
                    isDisabled={restarting || !isLocal}
                    tooltip={!isLocal ? t("settings.loopbackOnlyAction") : undefined}
                    onClick={restartBridge}
                  />
                ) : undefined
              }
            />
          )}

          <div className="native-save-bar">
            <Action type="submit" variant="primary" disabled={saving || restarting}>
              <Icon name="check" size={14} />
              {saving ? t("common.saving") : t("settings.saveBridgeSettings")}
            </Action>
            {settingsData?.path && <small className="muted">{settingsData.path}</small>}
          </div>
        </form>
      )}

      <ProgramUpdateCard state={state} bridgeVersion={bridgeVersion} isLocal={isLocal} />

      <ClassicFallbackTools />
    </>
  );
}

function DiagnosticsSection({ state, isLocal }) {
  const { t } = useLanguage();
  const [diag, setDiag] = useState(null);
  const [logEntries, setLogEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [linkTesting, setLinkTesting] = useState(false);
  const [linkTestResult, setLinkTestResult] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setLoadError("");
    try {
      const [diagRes, logRes] = await Promise.all([
        fetch("/api/diag", { cache: "no-store" }),
        fetch("/api/log", { cache: "no-store" }),
      ]);
      if (!diagRes.ok) throw new Error(`HTTP ${diagRes.status}`);
      const diagJson = await diagRes.json();
      setDiag(diagJson);
      if (logRes.ok) {
        const logJson = await logRes.json();
        setLogEntries(Array.isArray(logJson) ? logJson.slice(0, 30) : []);
      }
    } catch (e) {
      setLoadError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function runLinkTest() {
    if (!isLocal) return;
    setLinkTesting(true);
    try {
      const res = await fetch("/api/diag/link_test", { method: "POST" });
      if (res.status === 403) {
        throw new Error(t("settings.loopbackOnlyAction"));
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data.ok) throw new Error(data.err || `HTTP ${res.status}`);
      setLinkTestResult(data);
      refresh();
    } catch (e) {
      setLoadError(e.message || String(e));
    } finally {
      setLinkTesting(false);
    }
  }

  const recentErrors = Array.isArray(diag?.errors) ? diag.errors.slice(0, 15) : [];
  const rawLines = Array.isArray(diag?.raw) ? diag.raw.slice(-25).reverse() : [];

  return (
    <>
      <div className="section-heading">
        <div>
          <h2>{t("common.diagnostics")}</h2>
          <p>{t("settings.nativeDiagnosticsHint")}</p>
        </div>
        <div className="button-row">
          <Action type="button" disabled={loading} onClick={refresh}>
            <Icon name="reset" size={14} />
            {t("settings.diagRefresh")}
          </Action>
          <Action
            type="button"
            disabled={linkTesting || !isLocal}
            title={!isLocal ? t("settings.loopbackOnlyAction") : undefined}
            onClick={runLinkTest}
          >
            <Icon name="search" size={14} />
            {linkTesting ? t("settings.linkTesting") : t("settings.testLink")}
          </Action>
          <a className="diag-download-btn" href="/api/diag.zip" download>
            <Icon name="download" size={14} />
            <span>{t("settings.diagDownloadZip")}</span>
          </a>
        </div>
      </div>

      <ErrorDetails error={state.error} />
      {loadError && <div className="record-scene-err" role="alert">{loadError}</div>}

      {diag && (
        <section className="settings-section">
          <div className="native-status-grid">
            <div className="native-status-card">
              <small>{t("settings.diagVersion")}</small>
              <strong>{diag.version || "—"}</strong>
              <span>{t("settings.diagMode", { mode: diag.mode || "—" })}</span>
            </div>
            <div className="native-status-card">
              <small>{t("settings.diagTarget")}</small>
              <strong>{diag.host || "—"}</strong>
              <span>{diag.ma2 || "—"} · {diag.user || "—"}</span>
            </div>
            <div className="native-status-card">
              <small>{t("settings.diagLastCmd")}</small>
              <strong>{diag.last?.cmd || "—"}</strong>
              <span>{diag.last?.status || t("settings.diagNoReply")}</span>
            </div>
          </div>
          {linkTestResult && (
            <div className="link-test-result" role="status">
              <b>{t("settings.linkTestResultTitle", { target: linkTestResult.target || "—" })}</b>
              <p>
                {typeof linkTestResult.bare_connect === "string"
                  ? linkTestResult.bare_connect
                  : linkTestResult.bare_connect?.end || "OK"}
              </p>
            </div>
          )}
        </section>
      )}

      <section className="settings-section">
        <div className="settings-section-title">
          <Icon name="info" />
          <div>
            <h3>{t("settings.diagErrorsTitle")} ({recentErrors.length})</h3>
            <p>{t("settings.diagErrorsHint")}</p>
          </div>
        </div>
        {recentErrors.length === 0 ? (
          <p className="muted">{t("settings.diagNoErrors")}</p>
        ) : (
          <ul className="diag-log-list">
            {recentErrors.map((entry, idx) => (
              <li key={idx} className="diag-log-item err">
                <time>{entry.t || "—"}</time>
                <span>{typeof entry === "string" ? entry : entry.msg || entry.err || JSON.stringify(entry)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="settings-section">
        <div className="settings-section-title">
          <Icon name="layers" />
          <div>
            <h3>{t("settings.diagCommandsTitle")} ({logEntries.length})</h3>
            <p>{t("settings.diagCommandsHint")}</p>
          </div>
        </div>
        {logEntries.length === 0 ? (
          <p className="muted">{t("settings.diagNoCommands")}</p>
        ) : (
          <ul className="diag-log-list">
            {logEntries.map((entry, idx) => (
              <li key={idx} className={`diag-log-item ${entry.ok === false ? "err" : "ok"}`}>
                <time>{entry.t || "—"}</time>
                <b>{entry.a || "—"}</b>
                <span>{entry.err || (typeof entry.what === "string" ? entry.what : entry.what ? JSON.stringify(entry.what) : "OK")}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="settings-section">
        <details className="diag-raw-details">
          <summary>{t("settings.diagRawReplies")} ({rawLines.length})</summary>
          {rawLines.length === 0 ? (
            <p className="muted">{t("settings.diagNoRaw")}</p>
          ) : (
            <pre className="diag-raw-pre">
              {rawLines.map((row) => formatRawReply(row)).join("\n")}
            </pre>
          )}
        </details>
      </section>

      <ClassicFallbackTools />
    </>
  );
}

function PreparationSection({ state }) {
  const { t } = useLanguage();
  const [busyAction, setBusyAction] = useState("");
  const [notice, setNotice] = useState("");
  const [err, setErr] = useState("");
  const [fadeDraft, setFadeDraft] = useState(state.config?.scene_fade ?? 0);
  const [renamingId, setRenamingId] = useState(null);
  const [renameDraft, setRenameDraft] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);

  useEffect(() => {
    setFadeDraft(state.config?.scene_fade ?? 0);
  }, [state.config?.scene_fade]);

  const deskShow = state.status?.readiness?.show?.name || null;
  const showState = state.status?.readiness?.show?.state || "pending";
  const planShow = state.config?.show || "—";
  const fixtures = state.config?.fixtures || [];
  const scenes = state.config?.scenes || [];

  const identifyBlock = bridge.blockReason("show_identify");
  const bindBlock = bridge.blockReason("show_bind");
  const fetchBlock = bridge.blockReason("fixtures_fetch");
  const importScenesBlock = bridge.blockReason("scenes_import");
  const fadeBlock = bridge.blockReason("scene_fade");
  const renameBlock = bridge.blockReason("scene_rename");
  const deleteBlock = bridge.blockReason("scene_delete");

  async function runPrep(key, payload, successMessage) {
    if (busyAction) return;
    setBusyAction(key);
    setNotice("");
    setErr("");
    try {
      const res = await bridge.action(payload);
      if (typeof successMessage === "function") {
        setNotice(successMessage(res));
      } else if (successMessage) {
        setNotice(successMessage);
      }
      return res;
    } catch (e) {
      setErr(e.err || errorMessage(e, t) || e.message || String(e));
      return null;
    } finally {
      setBusyAction("");
    }
  }

  async function saveRename(scene) {
    const trimmed = renameDraft.trim();
    if (!trimmed) return;
    if (trimmed.includes('"')) {
      setErr(t("scenes.recordNoQuotes"));
      return;
    }
    const ok = await runPrep(
      `rename:${scene.id}`,
      { a: "scene_rename", id: scene.id, label: trimmed },
      t("settings.prepSceneRenamed", { name: trimmed }),
    );
    if (ok) {
      setRenamingId(null);
      setRenameDraft("");
    }
  }

  async function confirmDelete(scene) {
    const ok = await runPrep(
      `delete:${scene.id}`,
      { a: "scene_delete", id: scene.id, desk: false },
      t("settings.prepSceneDeleted", { name: scene.label || scene.exec }),
    );
    if (ok) setConfirmDeleteId(null);
  }

  const showBadgeVariant = showState === "matched" ? "success" : showState === "pending" ? "warning" : "error";
  const showBadgeLabel = showState === "matched"
    ? t("shell.showMatched")
    : showState === "pending"
      ? t("settings.statusShowPending")
      : t("settings.prepShowMismatch");
  const alreadyBound = Boolean(deskShow && deskShow === state.config?.show);
  const fadeChanged = Number(fadeDraft) !== Number(state.config?.scene_fade ?? 0);

  return (
    <>
      <div className="section-heading">
        <div>
          <h2>{t("common.preparation")}</h2>
          <p>{t("settings.prepHint")}</p>
        </div>
      </div>

      {notice && <Banner status="success" title={notice} className="prep-banner" />}
      {err && <Banner status="error" title={err} className="prep-banner" />}

      <Card variant="default" padding={4} className="prep-card">
        <div className="prep-card-head">
          <div className="settings-section-title">
            <Icon name="fixtures" />
            <div>
              <h3>{t("settings.prepShowCardTitle")}</h3>
              <p>{t("settings.prepShowCardHint")}</p>
            </div>
          </div>
          <Badge variant={showBadgeVariant} label={showBadgeLabel} />
        </div>

        <div className="native-status-grid">
          <div className="native-status-card">
            <small>{t("settings.statusShow")}</small>
            <strong className={showState === "matched" ? "badge-ok" : "badge-warn"}>
              {deskShow || t("settings.statusShowPending")}
            </strong>
            <span>{t(bridge.connectionKey())}</span>
          </div>
          <div className="native-status-card">
            <small>{t("settings.prepLocalPlanLabel")}</small>
            <strong>{planShow}</strong>
            <span>{t("settings.prepFixturesCount", { count: fixtures.length })}</span>
          </div>
          <div className="native-status-card">
            <small>{t("nav.scenes")}</small>
            <strong>{t("settings.prepScenesCount", { count: scenes.length })}</strong>
            <span>{t("settings.prepFadeSummary", { fade: state.config?.scene_fade ?? 0 })}</span>
          </div>
        </div>

        <div className="prep-actions-row">
          <Button
            label={t("settings.prepCheckShow")}
            variant="secondary"
            size="sm"
            isDisabled={Boolean(busyAction) || Boolean(identifyBlock)}
            isLoading={busyAction === "show_identify"}
            tooltip={errorMessage(identifyBlock, t) || undefined}
            onClick={() => runPrep("show_identify", { a: "show_identify" }, t("settings.prepShowChecked"))}
          />
          <Button
            label={t("settings.prepBindPlan")}
            variant="secondary"
            size="sm"
            isDisabled={Boolean(busyAction) || Boolean(bindBlock) || !deskShow || alreadyBound}
            isLoading={busyAction === "show_bind"}
            tooltip={
              errorMessage(bindBlock, t) ||
              (alreadyBound ? t("shell.showMatched") : !deskShow ? t("settings.statusShowPending") : undefined)
            }
            onClick={() =>
              runPrep(
                "show_bind",
                { a: "show_bind", name: deskShow, confirm: true },
                t("settings.prepPlanBound", { show: deskShow }),
              )
            }
          />
          <Button
            label={t("settings.prepFetchFixtures")}
            variant="primary"
            size="sm"
            isDisabled={Boolean(busyAction) || Boolean(fetchBlock)}
            isLoading={busyAction === "fixtures_fetch"}
            tooltip={errorMessage(fetchBlock, t) || undefined}
            onClick={() =>
              runPrep("fixtures_fetch", { a: "fixtures_fetch" }, (res) =>
                t("settings.prepFixturesFetched", { count: res?.total ?? res?.added ?? fixtures.length }),
              )
            }
          />
        </div>
      </Card>

      <Card variant="default" padding={4} className="prep-card">
        <div className="prep-card-head">
          <div className="settings-section-title">
            <Icon name="scenes" />
            <div>
              <h3>{t("settings.prepScenesCardTitle")}</h3>
              <p>{t("settings.prepScenesCardHint")}</p>
            </div>
          </div>
          <Badge variant="neutral" label={String(scenes.length)} />
        </div>

        <div className="prep-scenes-toolbar">
          <Button
            label={t("settings.prepImportScenes")}
            variant="primary"
            size="sm"
            isDisabled={Boolean(busyAction) || Boolean(importScenesBlock)}
            isLoading={busyAction === "scenes_import"}
            tooltip={errorMessage(importScenesBlock, t) || undefined}
            onClick={() =>
              runPrep("scenes_import", { a: "scenes_import" }, (res) =>
                t("settings.prepScenesImported", {
                  added: res?.added ?? 0,
                  total: res?.total ?? scenes.length,
                }),
              )
            }
          />
          <div className="prep-fade-control">
            <NumberInput
              label={t("scenes.fade")}
              value={fadeDraft}
              min={0}
              max={30}
              step={0.5}
              units={t("common.secondsUnit")}
              size="sm"
              width={176}
              isDisabled={Boolean(busyAction) || Boolean(fadeBlock)}
              onChange={(value) => setFadeDraft(Math.max(0, Math.min(30, Number(value) || 0)))}
            />
            <Button
              label={t("common.apply")}
              variant="secondary"
              size="sm"
              isDisabled={Boolean(busyAction) || Boolean(fadeBlock) || !fadeChanged}
              isLoading={busyAction === "scene_fade"}
              tooltip={errorMessage(fadeBlock, t) || undefined}
              onClick={() =>
                runPrep(
                  "scene_fade",
                  { a: "scene_fade", fade: Number(fadeDraft) || 0 },
                  t("settings.prepFadeSaved", { fade: Number(fadeDraft) || 0 }),
                )
              }
            />
          </div>
        </div>

        {scenes.length === 0 ? (
          <p className="muted prep-empty">{t("settings.prepNoScenes")}</p>
        ) : (
          <div className="prep-scenes-list">
            {scenes.map((scene, index) => {
              const label = scene.label || t("scenes.unnamed", { index: index + 1 });
              const isRenaming = renamingId === scene.id;
              const isConfirmingDelete = confirmDeleteId === scene.id;
              return (
                <div className="prep-scene-row" key={scene.id}>
                  <div className="prep-scene-main">
                    <Badge variant="neutral" label={scene.exec} />
                    {isRenaming ? (
                      <div className="prep-scene-rename">
                        <TextInput
                          label={t("scenes.recordName")}
                          isLabelHidden
                          size="sm"
                          value={renameDraft}
                          onChange={setRenameDraft}
                          onEnter={() => saveRename(scene)}
                          isDisabled={Boolean(busyAction)}
                        />
                        <Button
                          label={t("common.save")}
                          variant="primary"
                          size="sm"
                          isDisabled={Boolean(busyAction) || !renameDraft.trim()}
                          isLoading={busyAction === `rename:${scene.id}`}
                          onClick={() => saveRename(scene)}
                        />
                        <Button
                          label={t("common.cancel")}
                          variant="ghost"
                          size="sm"
                          isDisabled={Boolean(busyAction)}
                          onClick={() => {
                            setRenamingId(null);
                            setRenameDraft("");
                          }}
                        />
                      </div>
                    ) : (
                      <strong className="prep-scene-label">{label}</strong>
                    )}
                  </div>
                  {!isRenaming && (
                    <div className="prep-scene-actions">
                      {isConfirmingDelete ? (
                        <>
                          <Button
                            label={t("settings.prepDeleteConfirm")}
                            variant="destructive"
                            size="sm"
                            isDisabled={Boolean(busyAction) || Boolean(deleteBlock)}
                            isLoading={busyAction === `delete:${scene.id}`}
                            onClick={() => confirmDelete(scene)}
                          />
                          <Button
                            label={t("common.cancel")}
                            variant="ghost"
                            size="sm"
                            isDisabled={Boolean(busyAction)}
                            onClick={() => setConfirmDeleteId(null)}
                          />
                        </>
                      ) : (
                        <>
                          <Button
                            label={t("settings.prepRename")}
                            variant="ghost"
                            size="sm"
                            isDisabled={Boolean(busyAction) || Boolean(renameBlock)}
                            tooltip={errorMessage(renameBlock, t) || undefined}
                            onClick={() => {
                              setConfirmDeleteId(null);
                              setRenamingId(scene.id);
                              setRenameDraft(scene.label || "");
                            }}
                          />
                          <Button
                            label={t("settings.prepDelete")}
                            variant="ghost"
                            size="sm"
                            isDisabled={Boolean(busyAction) || Boolean(deleteBlock)}
                            tooltip={errorMessage(deleteBlock, t) || undefined}
                            onClick={() => setConfirmDeleteId(scene.id)}
                          />
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>

      <ClassicFallbackTools withEmbedded />
    </>
  );
}

export default function Settings({
  state,
  tools,
  setTools,
  top,
  setTop,
  beams,
  setBeams,
  ids,
  setIds,
  onShortcuts,
  onOpenWizard,
  section: controlledSection,
  onSectionChange,
}) {
  const { t, language, changeLanguage } = useLanguage();
  const isLocal = LOCAL_HOSTNAMES.has(window.location.hostname);
  const [internalSection, setInternalSection] = useState("interface");
  const section = controlledSection ?? internalSection;
  const setSection = onSectionChange ?? setInternalSection;
  const [settingsData, setSettingsData] = useState(null);
  const [settingsError, setSettingsError] = useState("");
  const [bridgeVersion, setBridgeVersion] = useState("");

  const loadSettings = useCallback(() => {
    const abort = new AbortController();
    fetch("/api/settings", { signal: abort.signal, cache: "no-store" })
      .then(async (r) => {
        if (r.status === 403) {
          setSettingsError(t("settings.loopbackOnly"));
          return null;
        }
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => {
        if (d) {
          setSettingsData(d);
          setSettingsError("");
        }
      })
      .catch((e) => {
        if (e.name !== "AbortError") setSettingsError(e.message || String(e));
      });
    fetch("/api/diag", { signal: abort.signal, cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (d?.version) setBridgeVersion(d.version);
      })
      .catch(() => {});
    return () => abort.abort();
  }, [t]);

  useEffect(() => loadSettings(), [loadSettings]);

  const settings = settingsData?.settings || null;
  const languagePicker = (
    <div className="settings-row">
      <label htmlFor="luma-language"><b>{t("settings.language")}</b></label>
      <select id="luma-language" value={language} onChange={(event) => changeLanguage(event.target.value)}>
        <option value="en" lang="en">EN</option>
        <option value="ru" lang="ru">RU</option>
      </select>
    </div>
  );
  if (state.status?.mock !== true && state.status?.hall_trial !== true)
    return (
      <div className="settings-content">
        {languagePicker}
        <div className="inline-notice">{t("settings.waitBridge")}</div>
      </div>
    );
  return (
    <div className="settings-layout">
      <nav className="settings-nav" aria-label={t("settings.categories")}>
        {sections.map(([id, label, icon]) => (
          <button
            key={id}
            className={section === id ? "active" : ""}
            onClick={() => setSection(id)}
          >
            <Icon name={icon} />
            {t(label)}
          </button>
        ))}
      </nav>
      <div className="settings-content">
        {section === "interface" ? (
          <>
            <div className="section-heading">
              <div>
                <h2>{t("settings.workspace")}</h2>
                <p>{t("settings.workspaceHint")}</p>
              </div>
            </div>
            <section className="settings-section hall-view-settings">{languagePicker}</section>
            <section className="settings-section hall-view-settings">
              <div className="settings-section-title">
                <Icon name="hall" />
                <div>
                  <h3>{t("hall.plan")}</h3>
                  <p>{t("settings.viewsHint")}</p>
                </div>
              </div>
              <div className="settings-row">
                <div>
                  <b>{t("settings.defaultPerspective")}</b>
                  <small>{t("settings.perspectiveHint")}</small>
                </div>
                <Switch
                  value={!top}
                  onChange={(v) => setTop(!v)}
                  label={t("settings.perspectiveView")}
                  isLabelHidden
                />
              </div>
              <div className="settings-row">
                <div>
                  <b>{t("settings.lightBeams")}</b>
                  <small>{t("settings.beamsHint")}</small>
                </div>
                <Switch
                  value={beams}
                  onChange={setBeams}
                  label={t("settings.lightBeams")}
                  isLabelHidden
                />
              </div>
              <div className="settings-row">
                <div>
                  <b>{t("settings.fixtureNumbers")}</b>
                  <small>{t("settings.idsHint")}</small>
                </div>
                <Switch
                  value={ids}
                  onChange={setIds}
                  label={t("settings.fixtureNumbers")}
                  isLabelHidden
                />
              </div>
            </section>
            <section className="settings-section hall-view-settings">
              <div className="settings-section-title">
                <Icon name="sun" />
                <div>
                  <h3>{t("settings.controls")}</h3>
                  <p>{t("settings.controlsHint")}</p>
                </div>
              </div>
              <div className="tool-settings">
                {["dim", "color", "pos", "zoom", "focus", "strobe"].map(key => (
                  <div className="settings-row" key={key}>
                    <b>{t(`tool.${key}`)}</b>
                    <Switch
                      value={tools[key] !== false}
                      label={t(`tool.${key}`)}
                      isLabelHidden
                      onChange={(v) => setTools({ ...tools, [key]: v })}
                    />
                  </div>
                ))}
              </div>
            </section>
            <section className="settings-section hall-view-settings shortcut-setting">
              <div className="settings-section-title">
                <Icon name="keyboard" />
                <div>
                  <h3>{t("common.shortcuts")}</h3>
                  <p>{t("settings.hotkeyHint")}</p>
                </div>
              </div>
              <Action onClick={onShortcuts}>
                {t("settings.configure")}
                <Icon name="arrow" size={15} />
              </Action>
            </section>
            <div className="settings-status">
              <span className="status-led" />
              <div>
                <b>{t(state.status.mock ? "settings.isolatedLab" : "shell.hallTrial")}</b>
                <p>React 19 · Astryx 0.7.16 · ma2-panel v{bridgeVersion || __LUMA_HALL_VERSION__ || "3.4.0"}</p>
              </div>
              {state.status.mock && <span>MOCK</span>}
            </div>
          </>
        ) : section === "system" ? (
          <ConnectionSafetySection
            state={state}
            settingsData={settingsData}
            settingsError={settingsError}
            bridgeVersion={bridgeVersion}
            isLocal={isLocal}
            onSaved={loadSettings}
            onOpenWizard={onOpenWizard}
          />
        ) : section === "diagnostics" ? (
          <DiagnosticsSection state={state} isLocal={isLocal} />
        ) : (
          <PreparationSection state={state} />
        )}
        {section === "interface" && settings && (
          <p className="settings-port-note">
            {t("settings.bridgeFooter", { port: String(settings.port), safety: settings.safety?.mode ?? "—" })}
          </p>
        )}
      </div>
    </div>
  );
}
