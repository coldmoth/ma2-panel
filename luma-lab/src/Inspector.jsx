import { useLanguage } from "./Language.jsx";
import { errorMessage } from "./errors.mjs";
import React, { useEffect, useRef, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { ButtonGroup } from "@astryxdesign/core/ButtonGroup";
import { Action, EvidenceDot, Range, useStored } from "./ui.jsx";
import { FixtureGlyph, Icon } from "./Icons.jsx";
import { bridge } from "./client.mjs";
import {
  supports,
  fixtureKind,
  displayValues,
  commonValue,
  currentDimmer,
  dimmerSupportCount,
  rgbToHex,
  hexToRGB,
  hsvToHex,
  hexToHSV,
  clamp,
} from "./model.mjs";
const SWATCHES = [
  "#fff0d5",
  "#ffbd77",
  "#ff587d",
  "#aa87ff",
  "#568aff",
  "#39d8b5",
  "#ffffff",
];
function DimmerControl({ state, values, selectionSerial, send }) {
  const { t } = useLanguage();
  const current = currentDimmer(state);
  const count = dimmerSupportCount(state);
  const total = state.selected.length;
  const disabled = state.selecting || count !== total || !bridge.ready("dim");
  const roundedValues = values.map((v) => (typeof v.dim === "number" ? Math.round(v.dim) : null));
  const knownRounded = roundedValues.filter((v) => v !== null);
  const shownDim = current === "mixed"
    ? "mixed"
    : typeof current === "number"
      ? Math.round(current)
      : knownRounded.length === 0
        ? null
        : new Set(knownRounded).size > 1 || knownRounded.length !== values.length
          ? "mixed"
          : knownRounded[0];
  const sliderValue = typeof shownDim === "number" ? shownDim : shownDim === "mixed" ? "mixed" : null;
  const evidence = typeof current === "number" || current === "mixed"
    ? "confirmed"
    : values.some((v) => v.quality.dim === "pending")
      ? "pending"
      : values.some((v) => v.quality.dim === "unconfirmed")
        ? "unconfirmed"
        : shownDim !== null
          ? "last"
          : "unknown";

  function apply(value, basis = null) {
    const latest = bridge.state;
    if (bridge.selectionSerial !== selectionSerial || latest.selecting ||
        !latest.selected.length || dimmerSupportCount(latest) !== latest.selected.length ||
        !bridge.ready("dim")) return;
    send({ a: "dim", v: value },
      basis === null ? undefined : () => currentDimmer(bridge.state) === basis);
  }

  return (
    <section className="dimmer-control" aria-label={t("tool.dim")}
      title={errorMessage(bridge.blockReason("dim"), t)}>
      <div className="field-top dimmer-head">
        <span>{t("tool.dim")}</span>
        <span className="field-value-group">
          <output className="dimmer-readout">
            {shownDim === "mixed" ? t("common.mixed")
              : shownDim === null ? "—" : `${shownDim}%`}
          </output>
          <EvidenceDot evidence={evidence} />
        </span>
      </div>
      {count !== total && (
        <p className="capability-note">{t("inspector.dimUnavailable", { count, total })}</p>
      )}
      <Range label={t("tool.dim")} value={sliderValue} disabled={disabled}
        showCaption={false}
        keyboardBasis={() => typeof current === "number" &&
          bridge.selectionSerial === selectionSerial && currentDimmer(bridge.state) === current
          ? current : null}
        onCommit={(value, basis) => apply(Math.round(value), basis)} />
      <ButtonGroup
        className="dimmer-presets"
        label={t("inspector.dimPresets")}
        size="sm"
        isDisabled={disabled}
      >
        {[0, 25, 50, 75, 100].map((preset) => (
          <Button
            key={preset}
            label={`${preset}%`}
            variant={shownDim === preset ? "primary" : "secondary"}
            size="sm"
            isDisabled={disabled}
            aria-pressed={shownDim === preset}
            onClick={() => apply(preset)}
          />
        ))}
      </ButtonGroup>
    </section>
  );
}
function ColorControl({ value, disabled, send, fade, evidence, title }) {
  const { t } = useLanguage();
  const [draft, setDraft] = useState(value || "#aa87ff"),
    [recent, setRecent] = useStored("recentColors", []),
    [saved, setSaved] = useStored("savedColors", []);
  const [mode, setMode] = useState("RGB");
  const dragging = useRef(false);
  useEffect(() => {
    if (value) setDraft(value);
  }, [value]);
  const apply = (c) => {
    if (!/^#[0-9a-f]{6}$/i.test(c)) return;
    setDraft(c);
    const [r, g, b] = hexToRGB(c);
    send({ a: "color", r, g, b, fade });
    setRecent((v) => [c, ...v.filter((x) => x !== c)].slice(0, 7));
  };
  const hsv = hexToHSV(/^#[0-9a-f]{6}$/i.test(draft) ? draft : "#aa87ff"),
    rgb = hexToRGB(/^#[0-9a-f]{6}$/i.test(draft) ? draft : "#aa87ff");
  function wheel(e, commit = false) {
    const r = e.currentTarget.getBoundingClientRect(),
      x = e.clientX - r.left - r.width / 2,
      y = e.clientY - r.top - r.height / 2,
      h = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360,
      s = clamp((Math.hypot(x, y) / (r.width / 2)) * 100),
      c = hsvToHex(h, s, 100);
    setDraft(c);
    if (commit) apply(c);
  }
  return (
    <section className="color-control" title={title}>
      <div className="field-top">
        <span>{t("tool.color")}</span>
        <span className="field-value-group">
          <output>{value ? value.toUpperCase() : "—"}</output>
          <EvidenceDot evidence={value ? evidence : "unknown"} />
        </span>
      </div>
      <div className="swatches">
        {SWATCHES.map((c) => (
          <button
            key={c}
            aria-label={t("common.colorValue", { color: c })}
            disabled={disabled}
            style={{ "--swatch": c }}
            className={value === c ? "selected" : ""}
            onClick={() => apply(c)}
          />
        ))}
      </div>
      <div className="color-picker">
        <div
          className={`color-wheel ${disabled ? "disabled" : ""}`}
          role="group"
          aria-label={t("inspector.colorWheel")}
          onPointerDown={(e) => {
            if (disabled) return;
            dragging.current = true;
            e.currentTarget.setPointerCapture(e.pointerId);
            wheel(e);
          }}
          onPointerMove={(e) => {
            if (dragging.current && !disabled) wheel(e);
          }}
          onPointerUp={(e) => {
            if (dragging.current && !disabled) wheel(e, true);
            dragging.current = false;
          }}
          onPointerCancel={() => (dragging.current = false)}
        >
          <span
            style={{
              left: `calc(50% - 5px + ${Math.cos((hsv[0] * Math.PI) / 180) * hsv[1] * 0.46}%)`,
              top: `calc(50% - 5px + ${Math.sin((hsv[0] * Math.PI) / 180) * hsv[1] * 0.46}%)`,
            }}
          />
        </div>
        <div className="color-entry">
          <span>HEX</span>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              apply(draft);
            }}
          >
            <input
              aria-label={t("inspector.colorHex")}
              value={draft.toUpperCase()}
              maxLength={7}
              disabled={disabled}
              onChange={(e) => setDraft(e.target.value)}
            />
            <button
              aria-label={t("inspector.applyColor")}
              disabled={disabled || !/^#[0-9a-f]{6}$/i.test(draft)}
            >
              <Icon name="check" size={15} />
            </button>
          </form>
          <button
            className="text-button"
            disabled={disabled || !/^#[0-9a-f]{6}$/i.test(draft)}
            onClick={() =>
              setSaved((v) => [...new Set([...v, draft])].slice(-14))
            }
          >
            {t("inspector.saveColor")}
          </button>
        </div>
      </div>
      <details className="color-advanced">
        <summary>
          {t("inspector.exactValues")} <span>{mode} / HSV</span>
        </summary>
        <div className="segments">
          <button
            className={mode === "RGB" ? "active" : ""}
            onClick={() => setMode("RGB")}
          >
            RGB
          </button>
          <button
            className={mode === "HSV" ? "active" : ""}
            onClick={() => setMode("HSV")}
          >
            HSV
          </button>
        </div>
        <div className="color-numbers">
          {(mode === "RGB" ? ["R", "G", "B"] : ["H", "S", "V"]).map(
            (name, i) => (
              <label key={name}>
                {name}
                <input
                  aria-label={name}
                  type="number"
                  min="0"
                  max={mode === "HSV" && i === 0 ? 359 : 100}
                  value={(mode === "RGB" ? rgb : hsv)[i]}
                  disabled={disabled || !/^#[0-9a-f]{6}$/i.test(draft)}
                  onChange={(e) => {
                    const v = [...(mode === "RGB" ? rgb : hsv)];
                    v[i] = clamp(
                      Number(e.target.value),
                      0,
                      mode === "HSV" && i === 0 ? 359 : 100,
                    );
                    setDraft(mode === "RGB" ? rgbToHex(v) : hsvToHex(...v));
                  }}
                />
              </label>
            ),
          )}
        </div>
        <Action disabled={disabled} onClick={() => apply(draft)}>
          {t("common.apply")}
        </Action>
      </details>
      {(saved.length > 0 || recent.length > 0) && (
        <details className="color-advanced">
          <summary>{t("inspector.savedRecentColors")}</summary>
          {[
            [t("inspector.savedColors"), saved],
            [t("inspector.recent"), recent],
          ].map(([name, list]) => (
            <div key={name}>
              <small>{name}</small>
              <div className="swatches">
                {list.map((c) => (
                  <button
                    key={c}
                    style={{ "--swatch": c }}
                    aria-label={`${name}: ${c}`}
                    disabled={disabled}
                    onClick={() => apply(c)}
                  />
                ))}
              </div>
            </div>
          ))}
        </details>
      )}
    </section>
  );
}
export function Joystick({ disabled, step, send, identity }) {
  const { t } = useLanguage();
  const vector = useRef([0, 0]),
    timer = useRef(null),
    pending = useRef(false),
    [knob, setKnob] = useState([0, 0]);
  function stop() {
    clearInterval(timer.current);
    timer.current = null;
    vector.current = [0, 0];
    setKnob([0, 0]);
  }
  useEffect(() => {
    stop();
    window.addEventListener("blur", stop);
    const vis = () => {
      if (document.hidden) stop();
    };
    document.addEventListener("visibilitychange", vis);
    return () => {
      stop();
      window.removeEventListener("blur", stop);
      document.removeEventListener("visibilitychange", vis);
    };
  }, [identity, disabled]);
  function update(e) {
    const r = e.currentTarget.getBoundingClientRect(),
      x = clamp((e.clientX - r.left - r.width / 2) / (r.width / 2), -1, 1),
      y = clamp((r.top + r.height / 2 - e.clientY) / (r.height / 2), -1, 1);
    vector.current = [x, y];
    setKnob([x * r.width * .32, -y * r.height * .32]);
  }
  return (
    <div
      className={`joystick ${disabled ? "disabled" : ""}`}
      aria-label={t("inspector.joystick")}
      onPointerDown={(e) => {
        if (disabled) return;
        if (timer.current) return;
        update(e);
        e.currentTarget.setPointerCapture(e.pointerId);
        timer.current = setInterval(async () => {
          if (disabled || pending.current) return;
          const [x, y] = vector.current,
            curve = (n) => (Math.abs(n) < 0.08 ? 0 : Math.sign(n) * n * n);
          if (!curve(x) && !curve(y)) return;
          pending.current = true;
          try {
            const accepted = await send({
              a: "jog",
              pan: curve(x) * step,
              tilt: curve(y) * step,
            });
            if (accepted === false) stop();
          } catch {
            stop();
          } finally {
            pending.current = false;
          }
        }, 100);
      }}
      onPointerMove={(e) => {
        if (timer.current) update(e);
      }}
      onPointerUp={stop}
      onPointerCancel={stop}
      onLostPointerCapture={stop}
    >
      <span className="axis-h" />
      <span className="axis-v" />
      <span className="joystick-label">PAN / TILT</span>
      <span
        className="joystick-knob"
        style={{ transform: `translate(${knob[0]}px,${knob[1]}px)` }}
      >
        <Icon name="move" size={17} />
      </span>
    </div>
  );
}
export default function Inspector({
  selectionEditing,
  state,
  selected,
  step,
  setStep,
  tools,
  visuals,
  groupLabel,
  fade,
  setFade,
}) {
  const { t } = useLanguage();
  const values = selected.map(f => displayValues(state, f.id));
  const f = selected[0],
    common = (key) =>
      selected.length > 0 &&
      selected.every((f) => supports(f, key, state.config)) &&
      !selected.some((f) =>
        (state.status?.no_attr?.[key] || []).includes(f.type),
      );
  const editingSelection = useRef(selectionEditing);
  editingSelection.current = selectionEditing;
  function send(a, validate) {
    if (editingSelection.current) return Promise.resolve(false);
    return bridge.control(a, validate).then(() => true).catch((e) => {
      bridge.report(e);
      return false;
    });
  }
  const val = (key) => commonValue(values, key),
    rgb = val("rgb"),
    hex = Array.isArray(rgb) ? rgbToHex(rgb) : null,
    kind = visuals[f.id] || fixtureKind(f),
    fresh = values.every((v) => v.source === "readback"),
    headerEvidence = fresh
      ? "confirmed"
      : values.some((v) => v.source === "pending")
        ? "pending"
        : values.some((v) => v.source === "last")
          ? "last"
          : "unknown",
    source = fresh
      ? t("inspector.sourceFresh")
      : values.some((v) => v.source === "pending")
        ? t("inspector.sourcePending")
        : values.some((v) => v.source === "last") ? t("inspector.sourceLast")
        : t("inspector.sourceUnknown");
  const allowed = (key, action = key) => !state.selecting && common(key) && bridge.ready(action);
  const shownAngle = (key) => {
    const v = val(key),
      spec = state.config?.attrs?.[key];
    return typeof v === "number" && spec
      ? spec.min + (v / 100) * (spec.max - spec.min)
      : v;
  };
  return (
    <aside className="inspector">
      <div className="inspect-title">
        <div className="inspect-symbol">
          <FixtureGlyph kind={kind} size={32} />
        </div>
        <div>
          <h2>
            {selected.length === 1
              ? f.label
              : groupLabel || t("shell.fixtureCount", { count: selected.length })}
          </h2>
          <p>
            {selected.length === 1
              ? `ID ${String(f.id).padStart(2, "0")} · ${f.type}`
              : t("inspector.sharedControls", { count: selected.length })}
          </p>
        </div>
        <EvidenceDot evidence={headerEvidence} label={source} className="inspect-status-dot" />
      </div>
      {bridge.blockReason("dim") && (
        <p className="capability-note" role="status">{errorMessage(bridge.blockReason("dim"), t)}</p>
      )}
      <div className="inspect-controls">
        {tools.dim !== false && (
          <DimmerControl key={bridge.selectionSerial} selectionSerial={bridge.selectionSerial}
            state={state} values={values} send={send} />
        )}
        {tools.color !== false &&
          (common("color") ? (
            <ColorControl
              value={hex}
              evidence={values.every(v=>v.quality.rgb === "confirmed") ? "confirmed" : values.some(v=>v.quality.rgb === "pending") ? "pending" : "last"}
              disabled={!allowed("color")}
              title={errorMessage(bridge.blockReason("color"), t)}
              send={send}
              fade={fade}
            />
          ) : (
            <p className="capability-note">{t("inspector.colorUnavailable")}</p>
          ))}
        {tools.pos !== false && common("pos") && (
          <section className="movement" title={errorMessage(bridge.blockReason("jog"), t)}>
            <div className="field-top">
              <span>{t("inspector.position")}</span>
              <span className="value-muted">{step}{t("inspector.degreesPerStep")}</span>
            </div>
            <Joystick
              disabled={!allowed("pos", "jog")}
              step={step}
              send={send}
              identity={`${state.selected.join(",")}:${state.status?.blackout_epoch}:${state.status?.ma2}`}
            />
            <div className="segments precision">
              {[
                [0.15, t("inspector.fine")],
                [0.5, t("inspector.normal")],
                [2, t("inspector.coarse")],
              ].map(([v, label]) => (
                <button
                  key={v}
                  className={v === step ? "active" : ""}
                  onClick={() => setStep(v)}
                >
                  {label}
                </button>
              ))}
            </div>
            {["pan", "tilt"].map((key) => {
              const spec = state.config?.attrs?.[key] || { min: -90, max: 90 };
              return (
                <Range
                  key={key}
                  label={key === "pan" ? "Pan" : "Tilt"}
                  value={shownAngle(key)}
                  evidence={values.every(v=>v.quality[key] === "confirmed") ? "confirmed" : values.some(v=>v.quality[key] === "pending") ? "pending" : values.some(v=>v.quality[key] === "unconfirmed") ? "unconfirmed" : val(key) === null ? "unknown" : "last"}
                  min={spec.min}
                  max={spec.max}
                  step={0.1}
                  suffix="°"
                  disabled={!allowed("pos", "aim")}
                  title={errorMessage(bridge.blockReason("aim"), t)}
                  onCommit={(v) => send({ a: "aim", [key]: v })}
                />
              );
            })}
            <details className="color-advanced">
              <summary>{t("inspector.precision")}</summary>
              <label className="inline-field">
                {t("inspector.stepDegrees")}
                <input
                  aria-label={t("inspector.moveStep")}
                  type="number"
                  min="0.01"
                  max="5"
                  step="0.01"
                  value={step}
                  onChange={(e) =>
                    setStep(clamp(Number(e.target.value) || 0.15, 0.01, 5))
                  }
                />
              </label>
              <p>{t("inspector.invertHelp")}</p>
              {selected.map((head) => (
                <div className="inversion" key={head.id}>
                  <span>ID {head.id}</span>
                  {["pan", "tilt"].map((axis) => (
                    <button
                      disabled={!bridge.ready("fixture_flag")}
                      key={axis}
                      aria-pressed={!!head[`flip_${axis}`]}
                      className={head[`flip_${axis}`] ? "active" : ""}
                      onClick={() =>
                        bridge
                          .action({
                            a: "fixture_flag",
                            id: head.id,
                            [`flip_${axis}`]: !head[`flip_${axis}`],
                          })
                          .catch((e) => bridge.report(e))
                      }
                    >
                      {axis === "pan" ? "Pan" : "Tilt"} ↔
                    </button>
                  ))}
                </div>
              ))}
            </details>
          </section>
        )}
        {["zoom", "focus", "strobe"]
          .filter(
            (key) =>
              tools[key] !== false &&
              common(key) &&
              (key === "strobe" || common("pos")),
          )
          .map((key) => (
            <Range
              key={key}
              label={t(`tool.${key}`)}
              value={val(key)}
              evidence={values.every(v=>v.quality[key] === "confirmed") ? "confirmed" : values.some(v=>v.quality[key] === "pending") ? "pending" : values.some(v=>v.quality[key] === "unconfirmed") ? "unconfirmed" : val(key) === null ? "unknown" : "last"}
              disabled={!allowed(key)}
              title={errorMessage(bridge.blockReason(key), t)}
              onCommit={(v) => send({ a: key, v })}
            />
          ))}
        <details className="color-advanced">
          <summary>{t("inspector.colorFade")}</summary>
          <Range
            label={t("inspector.colorTransition")}
            min={0}
            max={10}
            step={0.1}
            value={fade}
            suffix={` ${t("common.secondsUnit")}`}
            onCommit={setFade}
          />
          <p>{t("inspector.colorFadeHelp")}</p>
        </details>
      </div>
      {tools.pos !== false && common("pos") && (
        <div className="inspect-bottom">
          <kbd>↑ ↓ ← →</kbd>
          <span>{t("inspector.preciseMovement")}</span>
        </div>
      )}
    </aside>
  );
}
