import React, { useCallback, useEffect, useId, useState } from "react";
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

function ConnectionSafetySection({ state, settingsData, settingsError, onSaved, onOpenWizard }) {
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
  const [linkTesting, setLinkTesting] = useState(false);
  const [linkTestResult, setLinkTestResult] = useState(null);
  const [linkTestError, setLinkTestError] = useState("");
  const [linkBusy, setLinkBusy] = useState(false);

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
  const connectBlock = bridge.blockReason("link_connect");
  const dropBlock = bridge.blockReason("link_drop");
  const identifyBlock = bridge.blockReason("show_identify");

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
    setLinkTesting(true);
    setLinkTestError("");
    try {
      const res = await fetch("/api/diag/link_test", { method: "POST" });
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

  async function saveSettings(event) {
    event.preventDefault();
    if (!draft || !settingsData?.settings || saving) return;
    setSaving(true);
    setSaveNotice("");
    setSaveError("");
    try {
      const next = structuredClone(settingsData.settings);
      next.ma2 = {
        ...(next.ma2 || {}),
        host: draft.host.trim(),
        port: Number(draft.port),
        user: draft.user,
        auto_launch: Boolean(draft.auto_launch),
      };
      next.safety = { ...(next.safety || {}), mode: draft.mode, ...draft.flags };
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

  const ma2BadgeClass = ma2State === "logged_in" ? "ok" : ma2State === "tcp" ? "warn" : "bad";
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
            <strong className={`badge-${ma2BadgeClass}`}>{t(bridge.connectionKey())}</strong>
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
          <Action type="button" disabled={linkTesting} onClick={runLinkTest}>
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
          <div className="record-scene-alert" role="alert">{settingsError}</div>
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
                  disabled={saving}
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
                  disabled={saving}
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
                  disabled={saving}
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
                  disabled={saving || clearPassword}
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
                disabled={saving}
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
                isDisabled={saving}
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
                    isDisabled={saving}
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
                      isDisabled={saving}
                      onChange={(value) =>
                        setDraft((d) => ({ ...d, flags: { ...d.flags, [flag]: value } }))
                      }
                    />
                  </div>
                ))}
              </div>
            </Collapsible>
          </section>

          {saveError && <div className="record-scene-err" role="alert">{saveError}</div>}
          {saveNotice && <div className="inline-notice" role="status">{saveNotice}</div>}

          <div className="native-save-bar">
            <Action type="submit" variant="primary" disabled={saving}>
              <Icon name="check" size={14} />
              {saving ? t("common.saving") : t("settings.saveBridgeSettings")}
            </Action>
            {settingsData?.path && <small className="muted">{settingsData.path}</small>}
          </div>
        </form>
      )}

      <ClassicFallbackTools />
    </>
  );
}

function DiagnosticsSection({ state }) {
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
    setLinkTesting(true);
    try {
      const res = await fetch("/api/diag/link_test", { method: "POST" });
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
          <Action type="button" disabled={linkTesting} onClick={runLinkTest}>
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
              {rawLines.map((row) => (typeof row === "string" ? row : `${row.t || ""} ${row.dir || ""} ${row.text || row.line || JSON.stringify(row)}`)).join("\n")}
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
                t("settings.prepFixturesFetched", { count: res?.count ?? fixtures.length }),
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
}) {
  const { t, language, changeLanguage } = useLanguage();
  const [section, setSection] = useState("interface");
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
        <div className="inline-notice">{t("settings.waitMock")}</div>
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
            onSaved={loadSettings}
            onOpenWizard={onOpenWizard}
          />
        ) : section === "diagnostics" ? (
          <DiagnosticsSection state={state} />
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
