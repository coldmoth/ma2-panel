import React, { useEffect, useState } from "react";
import { Switch } from "@astryxdesign/core/Switch";
import { Theme } from "@astryxdesign/core/theme";
import { lumaTheme } from "./theme/luma.js";
import "./theme/luma.css";
import { Action, ErrorDetails } from "./ui.jsx";
import { Icon } from "./Icons.jsx";
import { useLanguage } from "./Language.jsx";
const FRAME_CSS = `:root{color-scheme:dark;--bg:#10121b;--panel:#171a26;--line:#303044;--text:#ece9f5;--muted:#a09aaf;--accent:#b29bee}body{background:#10121b!important;color:#ece9f5!important;font-family:Inter,system-ui,sans-serif!important}.sx{max-width:1100px!important;padding:20px!important}h1{font-size:22px!important}fieldset,.importbox{border:1px solid #343043!important;border-radius:14px!important;background:#151721!important;padding:18px!important}input,select,textarea{background:#1c1c2a!important;color:#f0eafc!important;border-color:#484155!important;border-radius:7px!important}.btn,button{border-radius:8px!important;background:#2a253d!important;color:#d6c9fa!important;border-color:#4e426c!important}.muted,.t,.lbl,legend{color:#b9b0c7!important}a{color:#c2a9ff!important}.toplinks{display:none!important}details{border-color:#393145!important}table{background:#151721!important}th,td{border-color:#393145!important}`;
export function LegacyFrame({
  page = "settings.html",
  title,
  className = "",
}) {
  const { t } = useLanguage();
  return (
    <iframe
      className={`legacy-frame ${className}`}
      src={`${__LUMA_HALL_VERSION__ ? "" : "/legacy"}/${page}`}
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
const sections = [
  ["interface", "settings.interface", "layers"],
  ["system", "settings.system", "link"],
  ["diagnostics", "common.diagnostics", "info"],
  ["preparation", "common.preparation", "layout"],
];
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
}) {
  const { t, language, changeLanguage } = useLanguage();
  const [section, setSection] = useState("interface"),
    [settings, setSettings] = useState(null);
  useEffect(() => {
    const abort = new AbortController();
    fetch("/api/settings", { signal: abort.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d) => setSettings(d.settings))
      .catch(() => {});
    return () => abort.abort();
  }, []);
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
            <section className="settings-section">{languagePicker}</section>
            <Theme theme={lumaTheme} mode="dark">
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
            </Theme>
            <section className="settings-section">
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
            <section className="settings-section shortcut-setting">
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
                <p>React 19 · Astryx 0.7.16 · ma2-panel v{__LUMA_HALL_VERSION__ || "3.3.3-rc.1"}</p>
              </div>
              {state.status.mock && <span>MOCK</span>}
            </div>
          </>
        ) : section === "system" ? (
          <>
            <div className="section-heading">
              <div>
                <h2>{t("settings.system")}</h2>
                <p>
                  {t("settings.classicSystemHint")}
                </p>
              </div>
            </div>
            {state.status.mock && <div className="inline-notice">{t("settings.mockHint")}</div>}
            <p className="muted">{t("settings.legacy")}</p>
            <LegacyFrame title={t("settings.legacy")} />
          </>
        ) : section === "diagnostics" ? (
          <>
            <div className="section-heading">
              <div>
                <h2>{t("common.diagnostics")}</h2>
                <p>
                  {t("settings.classicDiagnosticsHint")}
                </p>
              </div>
            </div>
            <ErrorDetails error={state.error} />
            <p className="muted">{t("settings.legacy")}</p>
            <LegacyFrame page="diag.html" title={t("settings.legacy")} />
          </>
        ) : (
          <>
            <div className="section-heading">
              <div>
                <h2>{t("common.preparation")}</h2>
                <p>
                  {t("settings.classicPanelHint")}
                </p>
              </div>
            </div>
            <p className="muted">{t("settings.legacy")}</p>
            <LegacyFrame page="index.html" title={t("settings.legacy")} />
          </>
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
