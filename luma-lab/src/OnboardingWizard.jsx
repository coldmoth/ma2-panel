import React, { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "@astryxdesign/core/Badge";
import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Card } from "@astryxdesign/core/Card";
import { Collapsible } from "@astryxdesign/core/Collapsible";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { InternationalizationProvider } from "@astryxdesign/core/i18n";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { SelectableCard } from "@astryxdesign/core/SelectableCard";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Step, Stepper } from "@astryxdesign/core/Stepper";
import { Switch } from "@astryxdesign/core/Switch";
import { TextInput } from "@astryxdesign/core/TextInput";
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
import { SAFETY_FLAGS, SAFETY_PRESETS } from "./Settings.jsx";

const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1", "[::1]", "::1"]);
const UNCONFIGURED_HOST = "ma2-unconfigured.invalid";
const RESTART_TIMEOUT_MS = 25000;

function MenuPath({ items }) {
  return (
    <span className="wizard-menu-path" aria-label={items.join(" -> ")}>
      {items.map((item, idx) => (
        <React.Fragment key={`${item}-${idx}`}>
          {idx > 0 && <span className="wizard-menu-sep" aria-hidden="true">→</span>}
          <span className="wizard-path-chip">{item}</span>
        </React.Fragment>
      ))}
    </span>
  );
}

export default function OnboardingWizard({ state, onClose, onOpenHall, onOpenLayout }) {
  const { t, language } = useLanguage();
  const isLocal = LOCAL_HOSTNAMES.has(window.location.hostname);

  const [step, setStep] = useState(0);
  const [setupData, setSetupData] = useState(null);
  const [setupError, setSetupError] = useState("");
  const [setupErrorCode, setSetupErrorCode] = useState("");
  const [settingsData, setSettingsData] = useState(null);
  const [settingsError, setSettingsError] = useState("");
  const [settingsLocalOnly, setSettingsLocalOnly] = useState(!isLocal);

  const [draft, setDraft] = useState(null);
  const [password, setPassword] = useState("");
  const [passwordTouched, setPasswordTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveNotice, setSaveNotice] = useState("");
  const [saveError, setSaveError] = useState("");
  const [restartNeeded, setRestartNeeded] = useState(false);

  const [restarting, setRestarting] = useState(false);
  const [autoConnectPending, setAutoConnectPending] = useState(false);
  const [connectBusy, setConnectBusy] = useState(false);
  const restartBaseRef = useRef(null);
  const restartTimeoutRef = useRef(null);
  const restartErrorSetterRef = useRef(null);
  const inFlightRef = useRef(false);
  const initializedRef = useRef(false);

  const [prepBusy, setPrepBusy] = useState("");
  const [prepNotice, setPrepNotice] = useState("");
  const [prepError, setPrepError] = useState("");
  const [grantBusy, setGrantBusy] = useState(false);

  const [lanBusy, setLanBusy] = useState(false);
  const [lanNotice, setLanNotice] = useState("");
  const [lanError, setLanError] = useState("");

  const clearRestartWatch = useCallback(() => {
    restartBaseRef.current = null;
    restartErrorSetterRef.current = null;
    if (restartTimeoutRef.current) {
      clearTimeout(restartTimeoutRef.current);
      restartTimeoutRef.current = null;
    }
    setRestarting(false);
  }, []);

  useEffect(() => {
    return () => {
      if (restartTimeoutRef.current) {
        clearTimeout(restartTimeoutRef.current);
        restartTimeoutRef.current = null;
      }
    };
  }, []);

  const loadSettings = useCallback(async (forceResetDraft = false) => {
    if (!isLocal) {
      setSettingsLocalOnly(true);
      setSettingsError(t("wizard.localOnly"));
      return null;
    }
    try {
      const res = await fetch("/api/settings", { cache: "no-store" });
      if (res.status === 403) {
        setSettingsLocalOnly(true);
        setSettingsError(t("wizard.localOnly"));
        return null;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSettingsData(data);
      setSettingsLocalOnly(false);
      setSettingsError("");
      if (!initializedRef.current || forceResetDraft) {
        const ma2 = { ...(data.defaults?.ma2 || {}), ...(data.settings?.ma2 || {}) };
        const safety = { ...(data.defaults?.safety || {}), ...(data.settings?.safety || {}) };
        const rawHost = String(ma2.host || "").trim();
        const isFresh = !rawHost || rawHost === UNCONFIGURED_HOST;
        const freshDefaultPreset = SAFETY_PRESETS.find((p) => p.id === "store");
        const useSuggestedMode =
          isFresh &&
          (safety.mode || "test") === "test" &&
          !(safety.allowed_fixtures?.length) &&
          !(safety.allowed_scenes?.length);
        setDraft({
          host: isFresh ? "127.0.0.1" : rawHost,
          port: Number(ma2.port) || 30000,
          user: ma2.user || "Remote",
          auto_launch: ma2.auto_launch !== false,
          mode: useSuggestedMode ? "store" : (safety.mode || "test"),
          flags: useSuggestedMode && freshDefaultPreset
            ? { ...freshDefaultPreset.flags }
            : Object.fromEntries(SAFETY_FLAGS.map((k) => [k, Boolean(safety[k])])),
          allowed_fixtures_text: formatFixtureRange(safety.allowed_fixtures || []),
          allowed_scenes_text: formatExecRange(safety.allowed_scenes || []),
          store_execs_text: formatExecRange(safety.store_execs || []),
        });
        initializedRef.current = true;
      }
      return data;
    } catch (e) {
      setSettingsError(e.message || String(e));
      return null;
    }
  }, [isLocal, t]);

  const pollSetup = useCallback(async () => {
    if (!isLocal) {
      setSetupErrorCode("localOnly");
      setSetupError(t("wizard.localOnly"));
      return;
    }
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    try {
      const res = await fetch("/api/setup", { cache: "no-store", signal: AbortSignal.timeout(4000) });
      if (res.status === 403) {
        setSetupErrorCode("localOnly");
        setSetupError(t("wizard.localOnly"));
        return;
      }
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        throw new Error(data.err || `HTTP ${res.status}`);
      }
      setSetupData(data);
      setSetupError("");
      setSetupErrorCode("");
      if (restartBaseRef.current && data.instance && data.instance !== restartBaseRef.current) {
        clearRestartWatch();
        setRestartNeeded(false);
        setSaveNotice(t("wizard.step1.restarted"));
        setLanNotice("");
        loadSettings(true);
        const manualAfterRestart =
          !data.mock &&
          (data.ma2?.state === "manual_off" ||
            bridge.state.status?.manual === true ||
            bridge.state.status?.ma2 === "manual_off");
        if (manualAfterRestart) {
          setAutoConnectPending(true);
        }
      }
    } catch (e) {
      if (e.name !== "AbortError") {
        setSetupErrorCode("network");
        setSetupError(e.message || String(e));
      }
    } finally {
      inFlightRef.current = false;
    }
  }, [clearRestartWatch, isLocal, loadSettings, t]);

  useEffect(() => {
    loadSettings(false);
    pollSetup();
  }, [loadSettings, pollSetup]);

  useEffect(() => {
    if (!isLocal) return undefined;
    const ms = restarting ? 1000 : 2500;
    const timer = setInterval(pollSetup, ms);
    return () => clearInterval(timer);
  }, [isLocal, restarting, pollSetup]);

  async function requestRestart(setNoticeFn, setErrorFn = setSaveError) {
    try {
      const res = await fetch("/api/restart", {
        method: "POST",
        headers: { "X-Stop": "1" },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || data.ok === false) {
        setRestartNeeded(true);
        setNoticeFn(data.err || t("wizard.step1.restartManual"));
        return false;
      }
      if (restartTimeoutRef.current) clearTimeout(restartTimeoutRef.current);
      restartBaseRef.current = data.instance || setupData?.instance || "pending";
      restartErrorSetterRef.current = setErrorFn;
      setRestarting(true);
      setNoticeFn(t("wizard.step1.savedRestarting"));
      restartTimeoutRef.current = setTimeout(() => {
        const errSetter = restartErrorSetterRef.current;
        clearRestartWatch();
        setRestartNeeded(true);
        setNoticeFn("");
        errSetter?.(t("wizard.step1.restartTimeout"));
      }, RESTART_TIMEOUT_MS);
      return true;
    } catch {
      setRestartNeeded(true);
      setNoticeFn(t("wizard.step1.restartManual"));
      return false;
    }
  }

  async function handleConnectMa2() {
    if (connectBusy) return;
    setConnectBusy(true);
    setSaveError("");
    try {
      await bridge.action({ a: "link_connect" });
    } catch (e) {
      setSaveError(e.err || errorMessage(e, t) || e.message || String(e));
    } finally {
      setConnectBusy(false);
    }
  }

  async function handleSaveConnect(event) {
    event?.preventDefault();
    if (!draft || saving || restarting) return;
    setSaving(true);
    setSaveError("");
    setSaveNotice("");
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

      const freshRes = await fetch("/api/settings", { cache: "no-store" });
      if (!freshRes.ok) throw new Error(`HTTP ${freshRes.status}`);
      const freshData = await freshRes.json();
      const next = structuredClone(freshData.settings || {});
      const prevMa2 = freshData.settings?.ma2 || {};
      const prevSafety = freshData.settings?.safety || {};
      const nextHost = draft.host.trim() || "127.0.0.1";
      const nextPort = Number(draft.port) || 30000;
      const nextUser = draft.user.trim() || "Remote";
      const allowlistChanged =
        JSON.stringify(prevSafety.allowed_fixtures || []) !== JSON.stringify(parsedFixtures.values) ||
        JSON.stringify(prevSafety.allowed_scenes || []) !== JSON.stringify(parsedScenes.values) ||
        JSON.stringify(prevSafety.store_execs || []) !== JSON.stringify(parsedStore.values);
      const connectionChanged =
        (prevMa2.host || "") !== nextHost ||
        Number(prevMa2.port || 30000) !== nextPort ||
        (prevMa2.user || "") !== nextUser ||
        (passwordTouched && Boolean(password)) ||
        (prevSafety.mode || "test") !== draft.mode ||
        allowlistChanged ||
        SAFETY_FLAGS.some((k) => Boolean(prevSafety[k]) !== Boolean(draft.flags[k]));

      next.ma2 = {
        ...(next.ma2 || {}),
        host: nextHost,
        port: nextPort,
        user: nextUser,
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
      const body = { settings: next };
      if (passwordTouched && password) body.password = password;

      const saveRes = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const saveJson = await saveRes.json().catch(() => ({}));
      if (!saveRes.ok || saveJson.ok === false) {
        throw new Error(saveJson.err || `HTTP ${saveRes.status}`);
      }
      setPassword("");
      setPasswordTouched(false);
      await loadSettings(true);
      if (connectionChanged) {
        await requestRestart(setSaveNotice, setSaveError);
      } else {
        setSaveNotice(t("wizard.step1.savedOnly"));
      }
    } catch (e) {
      setSaveError(e.message || String(e));
    } finally {
      setSaving(false);
    }
  }

  async function handleAllowLoadedInSettings() {
    if (!isLocal || grantBusy || restarting) return;
    setGrantBusy(true);
    setPrepError("");
    setPrepNotice("");
    try {
      const freshRes = await fetch("/api/settings", { cache: "no-store" });
      if (freshRes.status === 403) {
        throw new Error(t("wizard.localOnly"));
      }
      if (!freshRes.ok) throw new Error(`HTTP ${freshRes.status}`);
      const freshData = await freshRes.json();
      const next = structuredClone(freshData.settings || {});
      const prevSafety = next.safety || {};
      const mergedFixtures = [
        ...new Set([
          ...(Array.isArray(prevSafety.allowed_fixtures) ? prevSafety.allowed_fixtures.map(Number) : []),
          ...fixtures.map((f) => Number(f.id)).filter((n) => Number.isInteger(n) && n >= 1),
        ]),
      ].sort((a, b) => a - b);
      const mergedScenes = [
        ...new Set([
          ...(Array.isArray(prevSafety.allowed_scenes) ? prevSafety.allowed_scenes.map(String) : []),
          ...scenes.map((s) => String(s.exec || "")).filter((e) => /^\d+\.\d+$/.test(e)),
        ]),
      ];
      next.safety = {
        ...prevSafety,
        allowed_fixtures: mergedFixtures,
        allowed_scenes: mergedScenes,
      };
      const saveRes = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: next }),
      });
      const saveJson = await saveRes.json().catch(() => ({}));
      if (!saveRes.ok || saveJson.ok === false) {
        throw new Error(saveJson.err || `HTTP ${saveRes.status}`);
      }
      await loadSettings(true);
      const ok = await requestRestart(setPrepNotice, setPrepError);
      if (ok) {
        setPrepNotice(t("wizard.step2.allowLoadedSaved", { fixtures: mergedFixtures.length, scenes: mergedScenes.length }));
      }
    } catch (e) {
      setPrepError(e.message || String(e));
    } finally {
      setGrantBusy(false);
    }
  }

  async function handleLanToggle(enabled) {
    if (lanBusy || restarting) return;
    setLanBusy(true);
    setLanError("");
    setLanNotice("");
    try {
      const freshRes = await fetch("/api/settings", { cache: "no-store" });
      if (!freshRes.ok) throw new Error(`HTTP ${freshRes.status}`);
      const freshData = await freshRes.json();
      const next = structuredClone(freshData.settings || {});
      next.bind = enabled ? "0.0.0.0" : "127.0.0.1";
      const saveRes = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ settings: next }),
      });
      const saveJson = await saveRes.json().catch(() => ({}));
      if (!saveRes.ok || saveJson.ok === false) {
        throw new Error(saveJson.err || `HTTP ${saveRes.status}`);
      }
      await loadSettings(false);
      await requestRestart(setLanNotice, setLanError);
    } catch (e) {
      setLanError(e.message || String(e));
    } finally {
      setLanBusy(false);
    }
  }

  async function runPrepAction(key, payload, successMsg) {
    if (prepBusy) return;
    setPrepBusy(key);
    setPrepNotice("");
    setPrepError("");
    try {
      const res = await bridge.action(payload);
      setPrepNotice(typeof successMsg === "function" ? successMsg(res) : successMsg);
    } catch (e) {
      setPrepError(e.err || errorMessage(e, t) || e.message || String(e));
    } finally {
      setPrepBusy("");
    }
  }

  const isMock = Boolean(setupData?.mock || state.status?.mock);
  const ma2Info = setupData?.ma2 || null;
  const ma2Ready = Boolean(ma2Info?.ready && !ma2Info?.halted);
  const ma2State = ma2Info?.state || state.status?.ma2 || "down";
  const isManualOff = !isMock && (ma2State === "manual_off" || state.status?.manual === true);
  const deskShow = state.status?.readiness?.show?.name || null;
  const showState = state.status?.readiness?.show?.state || "pending";
  const planShow = state.config?.show || "—";
  const planSelection = state.status?.plan_selection;
  const planDecision = planSelection?.state === "operator" ? planSelection : null;
  const fixtures = state.config?.fixtures || [];
  const scenes = state.config?.scenes || [];
  const ma2Layout = state.config?.ma2_layout || null;
  const connectBlock = bridge.blockReason("link_connect");
  const canConnectMa2 = connectBlock === null;

  useEffect(() => {
    if (!autoConnectPending) return;
    if (ma2Ready) {
      setAutoConnectPending(false);
      return;
    }
    if (isManualOff && canConnectMa2) {
      setAutoConnectPending(false);
      bridge.action({ a: "link_connect" }).catch(() => {});
    }
  }, [autoConnectPending, canConnectMa2, isManualOff, ma2Ready]);

  const identifyBlock = bridge.blockReason("show_identify");
  const bindBlock = bridge.blockReason("show_bind");
  const openPlanBlock = bridge.blockReason("show_open_plan");
  const fetchBlock = bridge.blockReason("fixtures_fetch");
  const importScenesBlock = bridge.blockReason("scenes_import");

  const canCreatePlan = planDecision?.code === "plan_missing" && Boolean(deskShow) && !openPlanBlock;
  const canBindPlan = Boolean(deskShow) && deskShow !== state.config?.show && !bindBlock && !canCreatePlan;
  const showMatched = Boolean(deskShow && deskShow === state.config?.show);

  const activeSafetyMode =
    draft?.mode ||
    settingsData?.settings?.safety?.mode ||
    state.status?.safety?.mode ||
    "test";

  const savedSafety = settingsData?.settings?.safety || {};
  const savedAllowedFixtures = new Set(
    Array.isArray(savedSafety.allowed_fixtures) ? savedSafety.allowed_fixtures.map(Number) : [],
  );
  const savedAllowedScenes = new Set(
    Array.isArray(savedSafety.allowed_scenes) ? savedSafety.allowed_scenes.map(String) : [],
  );
  const hasUnallowedLoaded =
    (activeSafetyMode === "test" || activeSafetyMode === "store") &&
    ((fixtures.length > 0 && fixtures.some((f) => !savedAllowedFixtures.has(Number(f.id)))) ||
      (scenes.length > 0 && scenes.some((s) => s.exec && !savedAllowedScenes.has(String(s.exec)))));

  const draftFixturesCheck = draft ? parseFixtureRange(draft.allowed_fixtures_text) : { ok: true, values: [] };
  const draftScenesCheck = draft ? parseExecRange(draft.allowed_scenes_text) : { ok: true, values: [] };
  const draftStoreCheck = draft ? parseExecRange(draft.store_execs_text) : { ok: true, values: [] };
  const draftAllowlistEmpty =
    Boolean(draft) &&
    (draft.mode === "test" || draft.mode === "store") &&
    draftFixturesCheck.ok &&
    draftScenesCheck.ok &&
    draftFixturesCheck.values.length === 0 &&
    draftScenesCheck.values.length === 0;

  const connectionStepStatus = restarting
    ? undefined
    : setupErrorCode === "localOnly"
      ? undefined
      : isMock
        ? "success"
        : ma2Ready
          ? "success"
          : ma2State === "login_failed"
            ? "error"
            : undefined;

  function renderLiveStatus() {
    if (restarting) {
      return {
        dot: "warning",
        pulsing: true,
        badgeVariant: "warning",
        badgeLabel: t("connection.connecting"),
        title: t("wizard.step1.liveRestarting"),
        desc: `${draft?.host || ma2Info?.host || "127.0.0.1"}:${draft?.port || ma2Info?.port || 30000}`,
      };
    }
    if (setupErrorCode === "localOnly") {
      return {
        dot: "neutral",
        pulsing: false,
        badgeVariant: "info",
        badgeLabel: t("wizard.localOnlyBadge"),
        title: t("wizard.localOnlyTitle"),
        desc: t("wizard.localOnly"),
      };
    }
    if (setupError && !setupData) {
      return {
        dot: "error",
        pulsing: false,
        badgeVariant: "error",
        badgeLabel: t("connection.bridge_disconnected"),
        title: t("wizard.step1.liveOfflineTitle"),
        desc: setupError || t("wizard.step1.liveOfflineDesc"),
      };
    }
    if (isMock) {
      return {
        dot: "success",
        pulsing: false,
        badgeVariant: "info",
        badgeLabel: t("wizard.step1.liveMockBadge"),
        title: t("wizard.step1.liveMockTitle"),
        desc: t("wizard.step1.liveMockDesc"),
      };
    }
    if (ma2Info?.halted) {
      return {
        dot: "warning",
        pulsing: false,
        badgeVariant: "warning",
        badgeLabel: "HALT",
        title: t("wizard.step1.liveHaltedTitle"),
        desc: t("wizard.step1.liveHaltedDesc"),
      };
    }
    if (ma2Ready) {
      const version = ma2Info?.version || state.status?.login?.VERSION || "onPC";
      const user = ma2Info?.user || state.status?.login?.USER || draft?.user || "Remote";
      const showName = deskShow || planShow;
      return {
        dot: "success",
        pulsing: false,
        badgeVariant: "success",
        badgeLabel: t("wizard.step1.liveConnectedBadge"),
        title: t("wizard.step1.liveConnected", { version, user, show: showName }),
        desc: ma2Info?.profile
          ? `${ma2Info.host}:${ma2Info.port} · ${ma2Info.profile}`
          : t("wizard.step1.liveConnectedHint"),
      };
    }
    if (isManualOff) {
      return {
        dot: "warning",
        pulsing: false,
        badgeVariant: "warning",
        badgeLabel: t("wizard.step1.liveManualOffBadge"),
        title: t("wizard.step1.liveManualOffTitle"),
        desc: t("wizard.step1.liveManualOffDesc"),
        showConnectAction: true,
      };
    }
    if (ma2State === "login_failed") {
      return {
        dot: "error",
        pulsing: false,
        badgeVariant: "error",
        badgeLabel: t("connection.login_failed"),
        title: t("wizard.step1.liveLoginFailedTitle"),
        desc: t("wizard.step1.liveLoginFailedDesc"),
      };
    }
    if (ma2State === "tcp" || ma2State === "login_unknown") {
      return {
        dot: "warning",
        pulsing: true,
        badgeVariant: "warning",
        badgeLabel: t("connection.login_check"),
        title: t("wizard.step1.liveTcpTitle"),
        desc: t("wizard.step1.liveTcpDesc"),
      };
    }
    const hostDisplay = ma2Info?.host || draft?.host || "127.0.0.1";
    const portDisplay = ma2Info?.port || draft?.port || 30000;
    return {
      dot: "error",
      pulsing: false,
      badgeVariant: "error",
      badgeLabel: t("connection.disconnected"),
      title: t("wizard.step1.liveDownTitle", { host: hostDisplay, port: portDisplay }),
      desc: t("wizard.step1.liveDownDesc"),
    };
  }

  const live = renderLiveStatus();
  const hostIsLocal = ["", "127.0.0.1", "localhost", "::1"].includes((draft?.host || "").trim().toLowerCase());
  const lanEnabled = Boolean(setupData?.lan_enabled);
  const lanUrls = Array.isArray(setupData?.urls) ? setupData.urls : [];

  return (
    <InternationalizationProvider
      locale={language}
      overrides={{ "@astryx.dialog.close": t("common.close") }}
    >
      <Dialog
        isOpen
        onOpenChange={(open) => {
          if (!open) onClose();
        }}
        width={880}
        maxHeight="90dvh"
        purpose="form"
        padding={0}
        className="onboarding-wizard-dialog"
      >
        <div className="wizard-shell">
          <div className="wizard-header-wrap">
            <DialogHeader
              title={t("wizard.title")}
              subtitle={t("wizard.subtitle")}
              onOpenChange={(open) => {
                if (!open) onClose();
              }}
              hasDivider={false}
              className="wizard-dialog-header"
            />
          </div>

          <div className="wizard-stepper-bar">
            <Stepper
              activeStep={step}
              onStepClick={setStep}
              density="compact"
              label={t("wizard.stepsLabel")}
              horizontalOptions={{ minimumStepWidth: 120, collapsedVariant: "withLabelAndControls" }}
            >
              <Step step={0} label={t("wizard.step0.short")} />
              <Step step={1} label={t("wizard.step1.short")} status={connectionStepStatus} />
              <Step step={2} label={t("wizard.step2.short")} status={fixtures.length > 0 ? "success" : undefined} />
              <Step step={3} label={t("wizard.step3.short")} />
            </Stepper>
          </div>

          <div className="wizard-body">
            {step === 0 && (
              <div className="wizard-step-pane" data-wizard-step="0">
                <div className="wizard-step-head">
                  <h3>{t("wizard.step0.title")}</h3>
                  <p>{t("wizard.step0.intro")}</p>
                </div>

                <div className="wizard-guide-list">
                  <Card variant="default" padding={4} className="wizard-guide-card">
                    <div className="wizard-guide-num">1</div>
                    <div className="wizard-guide-content">
                      <div className="wizard-guide-top">
                        <strong>{t("wizard.step0.card1Title")}</strong>
                        <MenuPath items={["Backup", "Save Show"]} />
                      </div>
                      <p>{t("wizard.step0.card1Desc")}</p>
                    </div>
                  </Card>

                  <Card variant="default" padding={4} className="wizard-guide-card">
                    <div className="wizard-guide-num">2</div>
                    <div className="wizard-guide-content">
                      <div className="wizard-guide-top">
                        <strong>{t("wizard.step0.card2Title")}</strong>
                        <MenuPath items={["Setup", "User & Profiles Setup"]} />
                      </div>
                      <p>{t("wizard.step0.card2Desc")}</p>
                      <small className="wizard-guide-note">{t("wizard.step0.card2Note")}</small>
                    </div>
                  </Card>

                  <Card variant="default" padding={4} className="wizard-guide-card">
                    <div className="wizard-guide-num">3</div>
                    <div className="wizard-guide-content">
                      <div className="wizard-guide-top">
                        <strong>{t("wizard.step0.card3Title")}</strong>
                        <MenuPath items={["Setup", "Console", "Global Settings", "Telnet"]} />
                      </div>
                      <p>{t("wizard.step0.card3Desc")}</p>
                    </div>
                  </Card>
                </div>

                <Banner
                  status="info"
                  title={t("wizard.step0.autoLaunchTipTitle")}
                  description={t("wizard.step0.autoLaunchTipDesc")}
                  className="wizard-banner"
                />

                <Card variant="muted" padding={3} className="wizard-collapsible-card">
                  <Collapsible trigger={t("wizard.step0.docsTrigger")} defaultIsOpen={false}>
                    <div className="wizard-docs-body">
                      <p>{t("wizard.step0.docsOffline")}</p>
                      <a
                        href="https://help2.malighting.com/Page/grandMA2/remote_control_telnet/en/3.9"
                        target="_blank"
                        rel="noopener noreferrer"
                        className="wizard-doc-link"
                      >
                        <span>{t("wizard.step0.docsOfficial")}</span>
                        <Icon name="arrow" size={14} />
                      </a>
                    </div>
                  </Collapsible>
                </Card>
              </div>
            )}

            {step === 1 && (
              <div className="wizard-step-pane" data-wizard-step="1">
                <div className="wizard-step-head">
                  <h3>{t("wizard.step1.title")}</h3>
                  <p>{t("wizard.step1.intro")}</p>
                </div>

                {settingsError && (
                  <Banner
                    status={settingsLocalOnly ? "info" : "warning"}
                    title={settingsLocalOnly ? t("wizard.localOnlyTitle") : settingsError}
                    description={settingsLocalOnly ? t("wizard.localOnly") : undefined}
                    className="wizard-banner"
                  />
                )}

                {draft && (
                  <form className="wizard-connect-form" onSubmit={handleSaveConnect}>
                    <Card variant="default" padding={4} className="wizard-form-card">
                      <div className="wizard-fields-grid">
                        <TextInput
                          label={t("settings.ma2Host")}
                          description={hostIsLocal ? t("wizard.step1.localHint") : t("wizard.step1.remoteHint")}
                          value={draft.host}
                          onChange={(value) => setDraft((d) => ({ ...d, host: value }))}
                          placeholder="127.0.0.1"
                          isDisabled={saving || restarting}
                          size="md"
                          width="100%"
                        />
                        <NumberInput
                          label={t("settings.ma2Port")}
                          description={t("wizard.step1.portDesc")}
                          value={draft.port}
                          min={1}
                          max={65535}
                          step={1}
                          isIntegerOnly
                          isDisabled={saving || restarting}
                          onChange={(value) => setDraft((d) => ({ ...d, port: value }))}
                          size="md"
                          width="100%"
                        />
                        <TextInput
                          label={t("settings.ma2User")}
                          description={t("wizard.step1.userDesc")}
                          value={draft.user}
                          onChange={(value) => setDraft((d) => ({ ...d, user: value }))}
                          placeholder="Remote"
                          isDisabled={saving || restarting}
                          size="md"
                          width="100%"
                        />
                        <TextInput
                          type="password"
                          label={t("settings.ma2Password")}
                          description={
                            settingsData?.password_set
                              ? t("wizard.step1.passwordSetDesc")
                              : t("wizard.step1.passwordEmptyDesc")
                          }
                          value={password}
                          placeholder={t("settings.ma2PasswordPlaceholder")}
                          autoComplete="new-password"
                          isDisabled={saving || restarting}
                          onChange={(value) => {
                            setPassword(value);
                            setPasswordTouched(true);
                          }}
                          size="md"
                          width="100%"
                        />
                      </div>

                      <div className="wizard-switch-row">
                        <Switch
                          label={t("settings.ma2AutoLaunch")}
                          description={t("settings.ma2AutoLaunchDesc")}
                          value={Boolean(draft.auto_launch)}
                          isDisabled={saving || restarting}
                          labelPosition="start"
                          labelSpacing="spread"
                          width="100%"
                          onChange={(checked) => setDraft((d) => ({ ...d, auto_launch: checked }))}
                        />
                      </div>

                      <div className="wizard-safety-block">
                        <div className="wizard-safety-label">{t("wizard.step1.safetyTitle")}</div>
                        <div className="wizard-preset-grid" role="radiogroup" aria-label={t("settings.safetyMode")}>
                          {SAFETY_PRESETS.map((preset) => {
                            const selected = draft.mode === preset.id;
                            return (
                              <SelectableCard
                                key={preset.id}
                                label={t(`settings.preset.${preset.id}.title`)}
                                isSelected={selected}
                                isDisabled={saving || restarting}
                                padding={3}
                                className="wizard-preset-card"
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
                                <div className="wizard-preset-head">
                                  <strong>{t(`settings.preset.${preset.id}.title`)}</strong>
                                  <Badge
                                    variant={preset.id === "store" ? "info" : preset.badgeVariant}
                                    label={
                                      preset.id === "store"
                                        ? t("wizard.step1.recommended")
                                        : t(`settings.preset.${preset.id}.badge`)
                                    }
                                  />
                                </div>
                                <p className="wizard-preset-desc">{t(`settings.preset.${preset.id}.desc`)}</p>
                              </SelectableCard>
                            );
                          })}
                        </div>
                      </div>

                      {(draft.mode === "test" || draft.mode === "store") ? (
                        <div className="wizard-allowlist-block">
                          <div className="wizard-safety-label">{t("settings.accessScopeTitle")}</div>
                          <div className="wizard-fields-grid">
                            <div className="allowlist-field-group">
                              <TextInput
                                label={t("settings.allowedFixtures")}
                                description={t("settings.allowedFixturesDesc")}
                                value={draft.allowed_fixtures_text}
                                onChange={(value) => setDraft((d) => ({ ...d, allowed_fixtures_text: value }))}
                                placeholder="1-20, 25"
                                isDisabled={saving || restarting}
                                status={
                                  !draftFixturesCheck.ok
                                    ? { type: "error", message: t("settings.allowlistInvalidFixtures", { token: draftFixturesCheck.invalid }) }
                                    : undefined
                                }
                                size="md"
                                width="100%"
                              />
                              {fixtures.length > 0 && (
                                <Button
                                  type="button"
                                  label={t("settings.fillAllFromPlan")}
                                  variant="secondary"
                                  size="sm"
                                  isDisabled={saving || restarting}
                                  onClick={() =>
                                    setDraft((d) => ({
                                      ...d,
                                      allowed_fixtures_text: formatFixtureRange(fixtures.map((f) => f.id)),
                                    }))
                                  }
                                />
                              )}
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
                                  !draftScenesCheck.ok
                                    ? { type: "error", message: t("settings.allowlistInvalidScenes", { token: draftScenesCheck.invalid }) }
                                    : undefined
                                }
                                size="md"
                                width="100%"
                              />
                              {scenes.length > 0 && (
                                <Button
                                  type="button"
                                  label={t("settings.fillAllFromPlan")}
                                  variant="secondary"
                                  size="sm"
                                  isDisabled={saving || restarting}
                                  onClick={() =>
                                    setDraft((d) => ({
                                      ...d,
                                      allowed_scenes_text: formatExecRange(scenes.map((s) => s.exec)),
                                    }))
                                  }
                                />
                              )}
                            </div>
                            {draft.mode === "store" && (
                              <TextInput
                                label={t("settings.storeExecs")}
                                description={t("settings.storeExecsDesc")}
                                value={draft.store_execs_text}
                                onChange={(value) => setDraft((d) => ({ ...d, store_execs_text: value }))}
                                placeholder="1.101-1.120"
                                isDisabled={saving || restarting}
                                status={
                                  !draftStoreCheck.ok
                                    ? { type: "error", message: t("settings.allowlistInvalidStore", { token: draftStoreCheck.invalid }) }
                                    : undefined
                                }
                                size="md"
                                width="100%"
                              />
                            )}
                          </div>
                          {draftAllowlistEmpty && (
                            <Banner
                              status="info"
                              title={t("wizard.step1.emptyAllowlistTitle")}
                              description={t("wizard.step1.emptyAllowlistDesc")}
                              className="wizard-banner"
                            />
                          )}
                        </div>
                      ) : (
                        <small className="wizard-guide-note">{t("wizard.step1.fullAllowlistNote")}</small>
                      )}

                      <div className="wizard-form-actions">
                        <Button
                          type="submit"
                          label={t("wizard.step1.saveConnect")}
                          variant="primary"
                          size="md"
                          isLoading={saving || restarting}
                          isDisabled={saving || restarting}
                        />
                        {restartNeeded && !restarting && (
                          <Button
                            type="button"
                            label={t("wizard.step1.restartBridge")}
                            variant="secondary"
                            size="md"
                            onClick={() => requestRestart(setSaveNotice, setSaveError)}
                          />
                        )}
                      </div>

                      {saveError && <Banner status="error" title={saveError} className="wizard-banner" />}
                      {saveNotice && (
                        <Banner
                          status={restartNeeded ? "warning" : "success"}
                          title={saveNotice}
                          className="wizard-banner"
                        />
                      )}
                    </Card>
                  </form>
                )}

                <Card variant="muted" padding={4} className="wizard-live-card">
                  <div className="wizard-live-head">
                    <div className="wizard-live-title-row">
                      <StatusDot variant={live.dot} label={live.badgeLabel} isPulsing={live.pulsing} />
                      <span className="wizard-live-caption">{t("wizard.step1.liveTitle")}</span>
                    </div>
                    <Badge variant={live.badgeVariant} label={live.badgeLabel} />
                  </div>
                  <strong className="wizard-live-main">{live.title}</strong>
                  <p className="wizard-live-desc">{live.desc}</p>
                  {live.showConnectAction && (
                    <div className="wizard-live-actions">
                      <Button
                        type="button"
                        label={t("wizard.step1.connectMa2")}
                        variant="primary"
                        size="sm"
                        isLoading={connectBusy}
                        isDisabled={connectBusy || Boolean(connectBlock)}
                        tooltip={errorMessage(connectBlock, t) || undefined}
                        onClick={handleConnectMa2}
                      />
                    </div>
                  )}
                </Card>
              </div>
            )}

            {step === 2 && (
              <div className="wizard-step-pane" data-wizard-step="2">
                <div className="wizard-step-head">
                  <h3>{t("wizard.step2.title")}</h3>
                  <p>{t("wizard.step2.intro")}</p>
                </div>

                {prepNotice && <Banner status="success" title={prepNotice} className="wizard-banner" />}
                {prepError && <Banner status="error" title={prepError} className="wizard-banner" />}

                <Card variant="muted" padding={4} className="wizard-show-card">
                  <div className="wizard-show-head">
                    <div>
                      <span className="wizard-show-eyebrow">{t("wizard.step2.showTitle")}</span>
                      <div className="wizard-show-meta">
                        <span>
                          <small>{t("wizard.step2.deskShow")}:</small>{" "}
                          <strong>{deskShow || t("settings.statusShowPending")}</strong>
                        </span>
                        <span>
                          <small>{t("wizard.step2.localPlan")}:</small>{" "}
                          <strong>{planShow}</strong>
                        </span>
                      </div>
                    </div>
                    <Badge
                      variant={showMatched ? "success" : showState === "pending" ? "warning" : "error"}
                      label={
                        showMatched
                          ? t("shell.showMatched")
                          : showState === "pending"
                            ? t("settings.statusShowPending")
                            : t("settings.prepShowMismatch")
                      }
                    />
                  </div>
                  <div className="wizard-show-actions">
                    <Button
                      label={t("settings.prepCheckShow")}
                      variant="secondary"
                      size="sm"
                      isLoading={prepBusy === "show_identify"}
                      isDisabled={Boolean(prepBusy) || Boolean(identifyBlock)}
                      tooltip={errorMessage(identifyBlock, t) || undefined}
                      onClick={() => runPrepAction("show_identify", { a: "show_identify" }, t("settings.prepShowChecked"))}
                    />
                    {canCreatePlan && (
                      <Button
                        label={t("wizard.step2.createPlanBtn", { show: deskShow })}
                        variant="primary"
                        size="sm"
                        isLoading={prepBusy === "show_open_plan"}
                        isDisabled={Boolean(prepBusy)}
                        onClick={() =>
                          runPrepAction(
                            "show_open_plan",
                            { a: "show_open_plan", name: deskShow, create_only: true },
                            t("wizard.step2.planCreated", { show: deskShow }),
                          )
                        }
                      />
                    )}
                    {canBindPlan && (
                      <Button
                        label={t("wizard.step2.bindPlanBtn", { show: deskShow })}
                        variant="primary"
                        size="sm"
                        isLoading={prepBusy === "show_bind"}
                        isDisabled={Boolean(prepBusy)}
                        onClick={() =>
                          runPrepAction(
                            "show_bind",
                            { a: "show_bind", name: deskShow, confirm: true },
                            t("settings.prepPlanBound", { show: deskShow }),
                          )
                        }
                      />
                    )}
                  </div>
                </Card>

                <div className="wizard-checklist">
                  <Card variant="default" padding={4} className="wizard-check-card">
                    <div className={`wizard-check-mark ${fixtures.length > 0 ? "done" : ""}`} aria-hidden="true">
                      <Icon name="check" size={16} />
                    </div>
                    <div className="wizard-check-body">
                      <div className="wizard-check-top">
                        <strong>{t("wizard.step2.fixturesTitle")}</strong>
                        <Badge
                          variant={fixtures.length > 0 ? "success" : "neutral"}
                          label={t("shell.fixtureCount", { count: fixtures.length })}
                        />
                      </div>
                      <p>{t("wizard.step2.fixturesDesc")}</p>
                      {fetchBlock && (
                        <small className="wizard-block-reason">{errorMessage(fetchBlock, t)}</small>
                      )}
                    </div>
                    <div className="wizard-check-action">
                      <Button
                        label={t("wizard.step2.fixturesAction")}
                        variant="primary"
                        size="sm"
                        isLoading={prepBusy === "fixtures_fetch"}
                        isDisabled={Boolean(prepBusy) || Boolean(fetchBlock)}
                        tooltip={errorMessage(fetchBlock, t) || undefined}
                        onClick={() =>
                          runPrepAction("fixtures_fetch", { a: "fixtures_fetch" }, (res) =>
                            t("settings.prepFixturesFetched", { count: res?.total ?? res?.added ?? fixtures.length }),
                          )
                        }
                      />
                    </div>
                  </Card>

                  <Card variant="default" padding={4} className="wizard-check-card">
                    <div className={`wizard-check-mark ${scenes.length > 0 ? "done" : ""}`} aria-hidden="true">
                      <Icon name="check" size={16} />
                    </div>
                    <div className="wizard-check-body">
                      <div className="wizard-check-top">
                        <strong>{t("wizard.step2.scenesTitle")}</strong>
                        <div className="wizard-check-badges">
                          <Badge variant="neutral" label={t("wizard.step2.optional")} />
                          <Badge
                            variant={scenes.length > 0 ? "success" : "neutral"}
                            label={t("wizard.sceneCount", { count: scenes.length })}
                          />
                        </div>
                      </div>
                      <p>{t("wizard.step2.scenesDesc")}</p>
                      {importScenesBlock && (
                        <small className="wizard-block-reason">{errorMessage(importScenesBlock, t)}</small>
                      )}
                    </div>
                    <div className="wizard-check-action">
                      <Button
                        label={t("wizard.step2.scenesAction")}
                        variant="secondary"
                        size="sm"
                        isLoading={prepBusy === "scenes_import"}
                        isDisabled={Boolean(prepBusy) || Boolean(importScenesBlock)}
                        tooltip={errorMessage(importScenesBlock, t) || undefined}
                        onClick={() =>
                          runPrepAction("scenes_import", { a: "scenes_import" }, (res) =>
                            t("settings.prepScenesImported", {
                              added: res?.added ?? 0,
                              total: res?.total ?? scenes.length,
                            }),
                          )
                        }
                      />
                    </div>
                  </Card>

                  <Card variant="default" padding={4} className="wizard-check-card">
                    <div className={`wizard-check-mark ${ma2Layout || fixtures.length > 0 ? "done" : ""}`} aria-hidden="true">
                      <Icon name="check" size={16} />
                    </div>
                    <div className="wizard-check-body">
                      <div className="wizard-check-top">
                        <strong>{t("wizard.step2.layoutTitle")}</strong>
                        <Badge
                          variant={ma2Layout ? "success" : "neutral"}
                          label={ma2Layout ? t("wizard.step2.layoutImported", { name: ma2Layout.name || "XML" }) : t("wizard.step2.optional")}
                        />
                      </div>
                      <p>{t("wizard.step2.layoutDesc")}</p>
                      <small className="wizard-guide-note">{t("wizard.step2.layoutReadyHint")}</small>
                    </div>
                    <div className="wizard-check-action">
                      <Button
                        label={t("wizard.step2.layoutAction")}
                        variant="secondary"
                        size="sm"
                        onClick={onOpenLayout}
                      />
                    </div>
                  </Card>

                  {isLocal && hasUnallowedLoaded && (
                    <Banner
                      status="warning"
                      title={t("wizard.step2.allowLoadedTitle")}
                      description={t("wizard.step2.allowLoadedDesc")}
                      className="wizard-banner"
                      endContent={
                        <Button
                          type="button"
                          label={t("wizard.step2.allowLoadedBtn")}
                          variant="primary"
                          size="sm"
                          isLoading={grantBusy || restarting}
                          isDisabled={grantBusy || restarting}
                          onClick={handleAllowLoadedInSettings}
                        />
                      }
                    />
                  )}
                  {activeSafetyMode === "full" && (
                    <small className="wizard-guide-note">{t("wizard.step1.fullAllowlistNote")}</small>
                  )}
                </div>
              </div>
            )}

            {step === 3 && (
              <div className="wizard-step-pane" data-wizard-step="3">
                <div className="wizard-step-head">
                  <h3>{t("wizard.step3.title")}</h3>
                  <p>{t("wizard.step3.intro")}</p>
                </div>

                <Card variant="default" padding={4} className="wizard-summary-card">
                  <div className="wizard-summary-grid">
                    <div className="wizard-summary-tile">
                      <small>{t("wizard.step3.summaryShow")}</small>
                      <strong>{deskShow || planShow}</strong>
                      <Badge
                        variant={isMock ? "info" : ma2Ready ? "success" : "warning"}
                        label={isMock ? t("wizard.step1.liveMockBadge") : ma2Ready ? t("wizard.step1.liveConnectedBadge") : t(bridge.connectionKey())}
                      />
                    </div>
                    <div className="wizard-summary-tile">
                      <small>{t("wizard.step3.summaryFixtures")}</small>
                      <strong>{t("shell.number", { value: fixtures.length })}</strong>
                      <span>{t("shell.fixtureCountLabel", { count: fixtures.length })}</span>
                    </div>
                    <div className="wizard-summary-tile">
                      <small>{t("wizard.step3.summaryScenes")}</small>
                      <strong>{t("shell.number", { value: scenes.length })}</strong>
                      <span>{t("shell.sceneCountLabel", { count: scenes.length })}</span>
                    </div>
                    <div className="wizard-summary-tile">
                      <small>{t("wizard.step3.summarySafety")}</small>
                      <strong>{t(`settings.preset.${activeSafetyMode}.title`)}</strong>
                      <span>{t(`settings.preset.${activeSafetyMode}.badge`)}</span>
                    </div>
                  </div>
                </Card>

                <Card variant="muted" padding={4} className="wizard-tablet-card">
                  <div className="wizard-tablet-head">
                    <div>
                      <h4>{t("wizard.step3.tabletTitle")}</h4>
                      <p>{t("wizard.step3.tabletDesc")}</p>
                    </div>
                  </div>

                  <div className="wizard-switch-row">
                    <Switch
                      label={t("wizard.step3.lanSwitch")}
                      description={t("wizard.step3.lanSwitchDesc")}
                      value={lanEnabled}
                      isDisabled={!isLocal || lanBusy || restarting}
                      isLoading={lanBusy || restarting}
                      labelPosition="start"
                      labelSpacing="spread"
                      width="100%"
                      onChange={handleLanToggle}
                    />
                  </div>

                  {lanError && <Banner status="error" title={lanError} className="wizard-banner" />}
                  {lanNotice && <Banner status="info" title={lanNotice} className="wizard-banner" />}

                  {!lanEnabled ? (
                    <p className="wizard-tablet-hint">{t("wizard.step3.lanOffHint")}</p>
                  ) : lanUrls.length === 0 ? (
                    <p className="wizard-tablet-hint">{t("wizard.step3.lanNoUrls")}</p>
                  ) : (
                    <>
                      <p className="wizard-tablet-hint">{t("wizard.step3.lanUrlsHint")}</p>
                      <div className="wizard-qr-grid">
                        {lanUrls.map((url) => {
                          let hostname = "";
                          try {
                            hostname = new URL(url).hostname;
                          } catch {}
                          const qrSrc = hostname
                            ? `/api/setup/qr?address=${encodeURIComponent(hostname)}`
                            : "";
                          return (
                            <div className="wizard-qr-item" key={url}>
                              {qrSrc && (
                                <div className="wizard-qr-frame">
                                  <img
                                    src={qrSrc}
                                    alt={t("wizard.step3.qrAlt", { url })}
                                    className="wizard-qr-img"
                                    onError={(e) => {
                                      e.currentTarget.style.display = "none";
                                    }}
                                  />
                                </div>
                              )}
                              <a href={url} target="_blank" rel="noopener noreferrer" className="wizard-qr-url">
                                {url}
                              </a>
                            </div>
                          );
                        })}
                      </div>
                    </>
                  )}

                  <div className="wizard-tablet-help">
                    <Collapsible trigger={t("wizard.step3.tabletHelpTrigger")} defaultIsOpen={false}>
                      <ul className="wizard-help-list">
                        <li>{t("wizard.step3.tabletHelpFirewall")}</li>
                        <li>{t("wizard.step3.tabletHelpPrivate")}</li>
                      </ul>
                    </Collapsible>
                  </div>
                </Card>
              </div>
            )}
          </div>

          <div className="wizard-footer">
            <div className="wizard-footer-left">
              {step > 0 && (
                <Button
                  label={t("wizard.back")}
                  variant="secondary"
                  size="md"
                  onClick={() => setStep((s) => Math.max(0, s - 1))}
                />
              )}
              <Button
                label={t("wizard.skip")}
                variant="ghost"
                size="md"
                onClick={onClose}
              />
            </div>
            <div className="wizard-footer-right">
              {step === 0 && (
                <Button
                  label={t("wizard.step0.next")}
                  variant="primary"
                  size="md"
                  onClick={() => setStep(1)}
                />
              )}
              {step === 1 && (
                <Button
                  label={t("wizard.step1.next")}
                  variant="primary"
                  size="md"
                  onClick={() => setStep(2)}
                />
              )}
              {step === 2 && (
                <Button
                  label={t("wizard.step2.next")}
                  variant="primary"
                  size="md"
                  onClick={() => setStep(3)}
                />
              )}
              {step === 3 && (
                <Button
                  label={t("wizard.step3.openConsole")}
                  variant="primary"
                  size="md"
                  onClick={onOpenHall}
                />
              )}
            </div>
          </div>
        </div>
      </Dialog>
    </InternationalizationProvider>
  );
}
