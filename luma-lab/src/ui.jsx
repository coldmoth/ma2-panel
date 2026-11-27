import React, { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Button } from "@astryxdesign/core/Button";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Icon } from "./Icons.jsx";
import { useLanguage } from "./Language.jsx";
import { errorDetails } from "./errors.mjs";

const EVIDENCE_VARIANT = {
  confirmed: "success",
  pending: "warning",
  unconfirmed: "warning",
  last: "accent",
  unknown: "neutral",
};

export function EvidenceDot({ evidence = "unknown", label, className = "" }) {
  const { t } = useLanguage();
  const text = label || t(`evidence.${evidence}`);
  return (
    <span className={`evidence-dot ${evidence} ${className}`.trim()} title={text}>
      <StatusDot
        variant={EVIDENCE_VARIANT[evidence] || "neutral"}
        label={text}
        tooltip={text}
        isPulsing={evidence === "pending"}
      />
    </span>
  );
}
export function useStored(key, initial) {
  const [value, set] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(`luma.${key}`)) ?? initial;
    } catch {
      return initial;
    }
  });
  function update(next) {
    set((v) => {
      const n = typeof next === "function" ? next(v) : next;
      try {
        localStorage.setItem(`luma.${key}`, JSON.stringify(n));
      } catch {}
      return n;
    });
  }
  return [value, update];
}
export function Action({
  children,
  onClick,
  disabled,
  variant = "secondary",
  className = "",
  ...props
}) {
  return (
    <Button
      className={`ax-btn ${className}`}
      variant={variant}
      size="sm"
      isDisabled={disabled}
      onClick={onClick}
      {...props}
    >
      <span className="button-content">{children}</span>
    </Button>
  );
}
const RANGE_KEYS = new Set([
  "ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End", "PageUp", "PageDown",
]);

export function Range({
  label,
  value,
  min = 0,
  max = 100,
  step = 1,
  suffix = "%",
  disabled,
  onCommit,
  evidence,
  title,
  inputRef,
  showCaption = true,
  keyboardBasis,
}) {
  const { t } = useLanguage();
  const [draft, setDraft] = useState(null);
  const dragging = useRef(false);
  const keyBasis = useRef(null);
  useEffect(() => {
    if (!dragging.current) setDraft(null);
  }, [value, min, max, disabled]);
  const known = typeof value === "number",
    n = draft ?? (known ? value : min === 0 ? 0 : (min + max) / 2);
  const text =
    draft !== null || known
      ? `${t("shell.number", { value: Math.round(n * 10) / 10 })}${suffix}`
      : value === "mixed"
        ? t("common.mixed")
        : "—";
  const commit = (basis = null) => {
    dragging.current = false;
    if (draft !== null && !disabled) {
      onCommit(draft, basis);
      setDraft(null);
    }
  };
  return (
    <label className={`range-field ${disabled ? "disabled" : ""}`} title={title}>
      {showCaption && <span className="field-top">
        <span>{label}</span>
        <span className="field-value-group">
          <output>{text}</output>
          {evidence && <EvidenceDot evidence={evidence} />}
        </span>
      </span>}
      <input
        ref={inputRef}
        aria-label={label}
        type="range"
        min={min}
        max={max}
        step={step}
        value={n}
        aria-valuetext={known || draft !== null || value === "mixed" ? text : t("common.unknownValue")}
        data-unknown={!known && draft === null}
        disabled={disabled}
        style={{ "--progress": `${((n - min) / (max - min)) * 100}%` }}
        onPointerDown={() => {
          keyBasis.current = null;
          setDraft(null);
          dragging.current = true;
        }}
        onChange={(e) => setDraft(Number(e.target.value))}
        onPointerUp={() => commit()}
        onKeyDown={(e) => {
          if (!keyboardBasis || !RANGE_KEYS.has(e.key)) return;
          const basis = keyboardBasis();
          if (!dragging.current && basis !== null && keyBasis.current === null && !e.repeat)
            keyBasis.current = basis;
          if (dragging.current || basis === null || keyBasis.current !== basis)
            e.preventDefault();
        }}
        onKeyUp={(e) => {
          if (!RANGE_KEYS.has(e.key) || (keyboardBasis && dragging.current)) return;
          const basis = keyBasis.current;
          keyBasis.current = null;
          if (!keyboardBasis || (basis !== null && keyboardBasis() === basis)) commit(basis);
          else setDraft(null);
        }}
        onPointerCancel={() => { dragging.current = false; setDraft(null); }}
        onBlur={() => { dragging.current = false; keyBasis.current = null; setDraft(null); }}
      />
    </label>
  );
}
export function Modal({ title, onClose, children }) {
  const { t } = useLanguage();
  const titleId = useId();
  const ref = useRef(null);
  useLayoutEffect(() => {
    const dialog = ref.current;
    dialog.showModal();
    return () => dialog.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="modal"
      aria-labelledby={titleId}
      onCancel={(e) => { e.preventDefault(); onClose(); }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="modal-head">
        <h2 id={titleId}>{title}</h2>
        <button aria-label={t("common.close")} onClick={onClose}>
          <Icon name="close" />
        </button>
      </div>
      {children}
    </dialog>
  );
}
export function Empty({ title, children }) {
  return (
    <div className="empty">
      <Icon name="layers" size={32} />
      <h3>{title}</h3>
      <p>{children}</p>
    </div>
  );
}

export function ErrorDetails({ error }) {
  const { t } = useLanguage();
  const details = errorDetails(error);
  if (!details) return null;
  return (
    <details>
      <summary>{t("common.technicalDetails")}</summary>
      <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{JSON.stringify(details, null, 2)}</pre>
    </details>
  );
}
