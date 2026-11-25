import React, { useLayoutEffect, useRef, useState } from "react";
import { Icon } from "./Icons.jsx";
import { useLanguage } from "./Language.jsx";
import { clamp, inspectorLimits } from "./model.mjs";
import { useStored } from "./ui.jsx";

export function useInspectorSize() {
  const shell = useRef(null);
  const [preferred, setPreferred] = useStored("inspectorWidth", 360);
  const [geometry, setGeometry] = useState({ side: false, limits: { min: 280, max: 640 } });
  useLayoutEffect(() => {
    const element = shell.current;
    const sidebar = element.querySelector(".sidebar");
    const finePointer = matchMedia("(pointer: fine) and (hover: hover)");
    const update = () => {
      const limits = inspectorLimits(element.clientWidth, sidebar.getBoundingClientRect().width);
      setGeometry({ side: finePointer.matches && limits.max >= 280, limits });
    };
    const observer = new ResizeObserver(update);
    observer.observe(element);
    observer.observe(sidebar);
    finePointer.addEventListener("change", update);
    update();
    return () => {
      observer.disconnect();
      finePointer.removeEventListener("change", update);
    };
  }, []);
  const { side, limits } = geometry;
  const width = clamp(Number.isFinite(preferred) ? preferred : 360, limits.min, limits.max);
  return { shell, side, width, limits, setWidth: value => setPreferred(clamp(value, limits.min, limits.max)) };
}

function InspectorResizer({ size, launcher }) {
  const { t } = useLanguage();
  const handle = useRef(null);
  const drag = useRef(null);
  const [resizing, setResizing] = useState(false);
  useLayoutEffect(() => {
    const element = handle.current;
    return () => {
      if (document.activeElement === element) launcher.current?.focus();
    };
  }, [launcher]);
  const finish = () => {
    drag.current = null;
    setResizing(false);
  };
  return (
    <div ref={handle} className={`inspector-resizer ${resizing ? "resizing" : ""}`} role="separator"
      tabIndex={0} aria-label={t("inspector.width")} aria-orientation="vertical"
      aria-valuemin={Math.round(size.limits.min)} aria-valuemax={Math.round(size.limits.max)}
      aria-valuenow={Math.round(size.width)}
      onPointerDown={e => {
        if (e.button !== 0) return;
        e.preventDefault();
        e.currentTarget.focus();
        drag.current = { x: e.clientX, width: size.width };
        setResizing(true);
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={e => {
        if (drag.current) size.setWidth(drag.current.width + drag.current.x - e.clientX);
      }}
      onPointerUp={finish} onPointerCancel={finish} onLostPointerCapture={finish}
      onKeyDown={e => {
        const value = { ArrowLeft: size.width + 20, ArrowRight: size.width - 20,
          Home: size.limits.min, End: size.limits.max }[e.key];
        if (value == null) return;
        e.preventDefault();
        e.stopPropagation();
        size.setWidth(value);
      }}
    />
  );
}

export default function InspectorDock({ size, selected, show, groupLabel, selecting, selectionEditing, onClear, children }) {
  const { t } = useLanguage();
  const launcher = useRef(null);
  const count = selected.length;
  const hasSelection = count > 0;
  const [session, setSession] = useState(() => ({ show, hasSelection, expanded: hasSelection && size.side }));
  if (session.show !== show || session.hasSelection !== hasSelection) {
    setSession({ show, hasSelection, expanded: hasSelection && size.side });
  }

  const open = hasSelection && session.expanded;
  const emptyHint = !hasSelection && session.expanded;
  const label = t(open ? "inspector.collapse" : "inspector.open");
  const name = count === 1 ? selected[0].label : groupLabel || selected[0]?.label;
  return (
    <div className={open ? `inspector-dock ${size.side ? "side" : "bottom"}` : "inspector-strip"}>
      {open && size.side && <InspectorResizer size={size} launcher={launcher} />}
      <div className="inspector-toolbar">
        {!open && <div className="inspector-summary">
          {hasSelection ? <>
            <b title={name}>{name}</b>
            <span>{t("shell.fixtureCount", { count })}</span>
          </> : (emptyHint || selecting) && <span role="status">
            {t(selecting ? "inspector.confirmingSelection" : "inspector.selectFixtures")}
          </span>}
        </div>}
        <button ref={launcher} className="inspector-toggle" type="button" aria-expanded={hasSelection ? open : emptyHint}
          aria-controls={hasSelection ? "fixture-inspector" : undefined} onClick={() => {
            setSession(current => ({ ...current, expanded: !current.expanded }));
          }}>
          <Icon name={open ? "minus" : "plus"} size={15} />
          <span>{label}</span>
        </button>
        {hasSelection && <button className="unselect" type="button" disabled={selectionEditing} onClick={() => {
            launcher.current?.focus();
            onClear();
          }}>
          <Icon name="close" size={15} />
          <span>{t("common.clearSelection")}</span>
        </button>}
      </div>
      <div className="inspector-body" id="fixture-inspector" hidden={!open} inert={selectionEditing}>
        {open && children}
      </div>
    </div>
  );
}
