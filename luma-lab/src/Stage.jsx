import { useLanguage } from "./Language.jsx";
import React, { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { deskOnline } from "./client.mjs";
import { DesignGlyph } from "./DesignGlyphs.jsx";
import { availableGroupIds, isLocal } from "./FixturesWorkspace.jsx";
import { Icon } from "./Icons.jsx";
import { project, unproject, fixtureKind, fixtureAngle, stageRect, stageViewBox, rgbToHex, displayValues, clamp, DEFAULT_HALL } from "./model.mjs";
const sizes = {
  head: [24, 24],
  par: [18, 18],
  bar: [26, 6],
  fresnel: [22, 22],
  profile: [24, 24],
  washer: [24, 20],
  generic: [20, 20]
};
export default function Stage({
  state,
  top,
  setTop,
  ids,
  setIds,
  beams,
  setBeams,
  onSelect,
  editing = false,
  onPlace,
  onPreview,
  onClear,
  locked = false,
  visuals = {},
  groupOptions, onSelectGroup, selectionReady, clearReady, draftIds, onStartDraft, onCancelDraft, onApplyDraft,
  selection = state.selected
}) {
  const { t } = useLanguage();
  const [zoom, setZoom] = useState(1),
    [offset, setOffset] = useState([0, 0]),
    [ghost, setGhost] = useState(null),
    [detail, setDetail] = useState(null),
    [groupsOpen, setGroupsOpen] = useState(false),
    [candidate, setCandidate] = useState(null),
    [fittedViewBox, setFittedViewBox] = useState(null);
  const groupPopupId = useId();
  const groupToggle = useRef(null), groupPopup = useRef(null),
    multiToggle = useRef(null), draftControls = useRef(null), detailsPanel = useRef(null),
    wasPicking = useRef(false);
  const drag = useRef(null),
    svg = useRef(null),
    viewport = useRef(null),
    geometry = useRef(null),
    detailOpener = useRef(null),
    gestureCallbacks = useRef({ onPreview });
  gestureCallbacks.current = { onPreview };
  const hall = state.config?.hall ?? DEFAULT_HALL,
    fixtures = state.config?.fixtures || [],
    positioned = fixtures.filter(f => Number.isFinite(f.x) && Number.isFinite(f.y));
  const z = editing ? zoom : 1,
    off = editing ? offset : [0, 0];
  const box=(fittedViewBox || stageViewBox(hall,top,positioned)).split(' ').map(Number), area=viewport.current?.getBoundingClientRect(),
    editorScale=area ? Math.min(area.width/box[2],area.height/box[3])*z : 1,
    touchTarget=matchMedia('(any-pointer: coarse)').matches;
  const p = (x, y) => project(x, y, top, hall);
  const polygon = (x, y, w, h) => [p(x, y), p(x + w, y), p(x + w, y + h), p(x, y + h)].map(v => v.join(',')).join(' ');
  const [ax, ay, aw, ah] = stageRect(hall),
    label = p(ax + aw / 2, ay + ah / 2);
  useLayoutEffect(() => {
    let disposed = false;
    function fit() {
      if (disposed) return;
      const { width, height } = viewport.current.getBoundingClientRect();
      const base = stageViewBox(hall, top, []).split(" ").map(Number);
      const b = editing ? {x:base[0],y:base[1],width:base[2],height:base[3]} : geometry.current.getBBox();
      if (width <= 40 || height <= 40 || !b.width || !b.height) return;
      // A single native SVG scale, based on rendered room/fixtures/beams/labels.
      // Keep margins in CSS pixels, independent of projection and window size.
      const margin = editing ? 76 : 36;
      const scale = Math.min((width - margin) / b.width, (height - margin) / b.height);
      const w = width / scale, h = height / scale;
      const next = [b.x + (b.width - w) / 2, b.y + (b.height - h) / 2, w, h].join(' ');
      setFittedViewBox(previous => previous === next ? previous : next);
    }
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(viewport.current);
    // Text bounds can change when the UI font finishes loading.
    document.fonts.ready.then(fit);
    return () => { disposed = true; observer.disconnect(); };
  }, [editing, hall, top, fixtures, ids, beams, visuals, state.history, state.simulation]);
  function values(f) {
    return state.status?.mock === true && state.simulation?.[f.id] && deskOnline(state.status) && state.status.readiness?.show?.state === "matched" ? {
      ...state.simulation[f.id],
      source: "simulation"
    } : displayValues(state, f.id);
  }
  function point(e) {
    const pt = svg.current.createSVGPoint();
    pt.x = e.clientX;
    pt.y = e.clientY;
    return pt.matrixTransform(svg.current.getScreenCTM().inverse());
  }
  function localPoint(e) {
    const pt = svg.current.createSVGPoint();
    pt.x = e.clientX; pt.y = e.clientY;
    return pt.matrixTransform(geometry.current.getScreenCTM().inverse());
  }
  function cancelGesture() {
    const d = drag.current;
    drag.current = null;
    setGhost(null);
    gestureCallbacks.current.onPreview?.(null);
    if (d?.kind === "pan") setOffset(d.offset);
    if (d && svg.current?.hasPointerCapture(d.pointerId)) svg.current.releasePointerCapture(d.pointerId);
  }
  useEffect(() => {
    const escape = e => {
      if (e.key === "Escape" && drag.current) {e.preventDefault(); cancelGesture();}
    };
    document.addEventListener("keydown", escape);
    return () => {document.removeEventListener("keydown", escape); gestureCallbacks.current.onPreview?.(null);};
  }, []);
  function begin(e, kind, f) {
    if (!editing || locked || drag.current || !e.isPrimary || e.button !== 0) return;
    e.preventDefault(); e.stopPropagation();
    const q = localPoint(e), center = f && p(f.x, f.y);
    drag.current = {kind, f, pointerId:e.pointerId, start:point(e), local:q,
      client:[e.clientX,e.clientY], offset, angle:f && fixtureAngle(f, visuals[f.id] || fixtureKind(f), hall),
      bearing:center && Math.atan2(q.y-center[1],q.x-center[0])};
    svg.current.setPointerCapture(e.pointerId);
  }
  function move(e) {
    const d = drag.current;
    if (!d || d.pointerId !== e.pointerId) return;
    if (Math.hypot(e.clientX-d.client[0], e.clientY-d.client[1]) < 5 && !d.moved) return;
    d.moved = true;
    if (d.kind === "pan") {
      const q=point(e);
      setOffset([d.offset[0]+q.x-d.start.x, d.offset[1]+q.y-d.start.y]);
      return;
    }
    const q=localPoint(e), center=p(d.f.x,d.f.y);
    if (d.kind === "rotate") {
      let angle=d.angle+(Math.atan2(q.y-center[1],q.x-center[0])-d.bearing)*180/Math.PI;
      angle=((angle%360)+360)%360;
      const rot=e.shiftKey ? Math.round(angle/15)*15%360 : Math.round(angle*10)/10%360;
      d.pos={id:d.f.id,x:d.f.x,y:d.f.y,rot};
    } else {
      const [x,y]=unproject(center[0]+q.x-d.local.x,center[1]+q.y-d.local.y,top,hall);
      d.pos={id:d.f.id,x,y};
    }
    setGhost(d.pos);
    onPreview?.(d.pos);
  }
  function finish(e) {
    const d=drag.current;
    if (!d || d.pointerId !== e.pointerId) return;
    drag.current=null;
    if (d.pos) {
      onPlace?.({id:d.f.id,x:d.f.x,y:d.f.y,rot:d.f.rot ?? null,icon:d.f.icon ?? null,...d.pos});
      if (!selection.includes(d.f.id)) onSelect(d.f.id,false);
    } else if (d.kind === "move") choose(d.f,e);
    else if (d.kind === "pan" && !d.moved) {onClear?.();setDetail(null);}
    setGhost(null);onPreview?.(null);
    if (svg.current.hasPointerCapture(e.pointerId)) svg.current.releasePointerCapture(e.pointerId);
  }
  function headDirection(f, v) {
    const spec = state.config?.attrs?.pan;
    if (v.pan == null || !spec) return null;
    const base = Math.atan2((ay + ah / 2 - f.y) * (hall?.d || 1), (ax + aw / 2 - f.x) * (hall?.w || 1));
    return base + (v.pan - (f.beam?.home ?? 50)) / 100 * (spec.max - spec.min) * Math.PI / 180 * (f.beam?.invert ? -1 : 1);
  }
  function nearby(f, e) {
    const m = geometry.current?.getScreenCTM();
    const radius = editing && m ? 30 / Math.hypot(m.a,m.b) : 38;
    const q = editing && Number.isFinite(e?.clientX) && e.clientX !== 0 ? localPoint(e) : null,
      anchor=q ? [q.x,q.y] : p(f.x,f.y);
    return positioned.filter(g => Math.hypot(...p(g.x, g.y).map((v, i) => v - anchor[i])) < radius);
  }
  const pickingMany = draftIds !== undefined;
  const selectable = positioned.length > 0;
  const busy = state.selecting;
  const candidates = detail && fixtures.filter(f => detail.includes(f.id) && (editing || !f.missing));
  useEffect(() => {
    if (groupsOpen) groupPopup.current?.focus();
  }, [groupsOpen]);
  useEffect(() => {
    if (!groupsOpen) return;
    function closeOutside(event) {
      if (!groupPopup.current?.contains(event.target) && !groupToggle.current?.contains(event.target)) {
        setGroupsOpen(false);
      }
    }
    document.addEventListener("pointerdown", closeOutside, true);
    document.addEventListener("focusin", closeOutside, true);
    return () => {
      document.removeEventListener("pointerdown", closeOutside, true);
      document.removeEventListener("focusin", closeOutside, true);
    };
  }, [groupsOpen]);
  useLayoutEffect(() => {
    if (pickingMany) {
      const first = svg.current?.querySelector('.stage-fixture[aria-disabled="false"]');
      (first || draftControls.current)?.focus();
    } else if (wasPicking.current) {
      setDetail(null);
      setCandidate(null);
      multiToggle.current?.focus();
    }
    wasPicking.current = pickingMany;
  }, [pickingMany]);
  useEffect(() => {
    if (detail && !editing) detailsPanel.current?.querySelector(".detail-fixtures button")?.focus();
  }, [detail, editing]);

  function closeDetail(restoreFocus = true) {
    setDetail(null);
    setCandidate(null);
    if (restoreFocus) detailOpener.current?.focus();
  }
  function choose(f, e) {
    if (!editing) {
      if (busy || f.missing || !selectable) return;
      // Keyboard activation names a single fixture. For pointer input, test the actual hit areas.
      const choices = e.detail > 0 ? [...svg.current.querySelectorAll("[data-hall-hit]")].flatMap(hit => {
        const { left, top, right, bottom } = hit.getBoundingClientRect();
        if (e.clientX < left || e.clientX > right || e.clientY < top || e.clientY > bottom) return [];
        return [{
          id: Number(hit.parentElement.dataset.fixture),
          distance: Math.hypot(e.clientX - (left + right) / 2, e.clientY - (top + bottom) / 2),
        }];
      }).sort((a, b) => a.distance - b.distance) : [];
      // Expanded touch targets can share an edge even when the glyphs are distinct.
      const nearest = choices[0];
      const ambiguous = choices.filter(choice => choice.distance - nearest.distance < 8);
      if (ambiguous.length > 1) {
        detailOpener.current = e.currentTarget;
        setCandidate(null);
        setDetail(ambiguous.map(choice => choice.id));
        return;
      }
      closeDetail(false);
      onSelect(nearest?.id ?? f.id, e.shiftKey);
      return;
    }

    const close = nearby(f,e);
    if (Number.isFinite(e.clientX) && e.clientX !== 0 && close.length) {
      const q=localPoint(e), distance=g=>Math.hypot(p(g.x,g.y)[0]-q.x,p(g.x,g.y)[1]-q.y);
      f=close.reduce((best,g)=>distance(g)<distance(best)?g:best,f);
    }
    onSelect(f.id, e.shiftKey);
    if (close.length > 1) {
      detailOpener.current = svg.current.querySelector(`[data-fixture="${f.id}"]`);
      setDetail(close.map(g => g.id));
    } else closeDetail(false);
  }
  function glyph(f, context = "plan") {
    const kind = visuals[f.id] || fixtureKind(f),
      [w, h] = sizes[kind],
      v = values(f),
      c = v.rgb ? rgbToHex(v.rgb) : "#b1a3d0";
    return <DesignGlyph kind={kind} context={context} variant="B" width={context === "plan" ? w : kind === "bar" ? 52 : kind === "par" ? 30 : 40} height={context === "plan" ? h : kind === "bar" ? 12 : kind === "par" ? 30 : 40} style={{
      color: f.missing ? "#625f72" : c,
      "--dl-solid": "#282637",
      "--dl-surface": "#151722"
    }} />;
  }
  return <section className={`stage-card ${editing ? "stage-editing" : ""}`} aria-label={t("hall.plan")} data-shortcut-layer={pickingMany ? "hall-draft" : undefined}>
    <div className="stage-heading"><div className="stage-label"><i /><b>{editing ? t("hall.fixtureLayout") : state.config?.show ? t("hall.namedPlan", { name: state.config.show }) : t("nav.hall")}</b><span>{t("hall.dimensions", { width: hall?.w || "—", depth: hall?.d || "—" })}</span></div>
      <div className="stage-tools"><div className="segments"><button className={!top ? "active" : ""} aria-pressed={!top} onClick={() => setTop(false)}>{t("hall.perspective")}</button><button className={top ? "active" : ""} aria-pressed={top} onClick={() => setTop(true)}>{t("hall.top")}</button></div>{!editing && <div className="segments"><button aria-pressed={ids} className={ids?'active':''} onClick={()=>setIds(!ids)}>ID</button><button aria-pressed={beams} className={beams?'active':''} onClick={()=>setBeams(!beams)}>{t("hall.beams")}</button></div>}
        {groupOptions && <div className="hall-selection-tools">
          <button ref={groupToggle} className="hall-tool" aria-expanded={groupsOpen} aria-controls={groupsOpen ? groupPopupId : undefined}
            disabled={pickingMany || busy}
            onClick={() => {
              closeDetail(false);
              setGroupsOpen(open => !open);
            }}>{t("hall.groups")}</button>
          <button ref={multiToggle} className="hall-tool" aria-pressed={pickingMany}
            disabled={pickingMany || busy || !selectable}
            onClick={() => {
              closeDetail(false);
              setGroupsOpen(false);
              onStartDraft();
            }}>{t("hall.multiSelect")}</button>
        </div>}
      </div>
    </div>
    <div ref={viewport} className="stage-viewport">
      <svg ref={svg} viewBox={fittedViewBox || stageViewBox(hall,top,positioned)} preserveAspectRatio="xMidYMid meet" aria-label={t("hall.interactivePlan")} onPointerDown={e => {
        if (e.target.closest('[data-fixture], [data-rotation]')) return;
        begin(e,"pan");
      }} onPointerMove={move} onPointerUp={finish} onPointerCancel={cancelGesture}
      onLostPointerCapture={() => {if(drag.current) cancelGesture();}} onWheel={e => {
        if (editing && !drag.current) setZoom(v => clamp(v - e.deltaY * .001, .5, 4));
      }}>
        <defs><linearGradient id="floor" x2=".2" y2="1"><stop stopColor="#252536" /><stop offset="1" stopColor="#191b27" /></linearGradient><filter id="halo"><feGaussianBlur stdDeviation="5" /></filter>
          {positioned.map(f => <linearGradient key={f.id} id={`beam-${f.id}`} x2="0" y2="1"><stop stopColor={values(f).rgb ? rgbToHex(values(f).rgb) : "#b5a0e8"} stopOpacity=".45" /><stop offset="1" stopColor="#b5a0e8" stopOpacity="0" /></linearGradient>)}
        </defs>
        <g ref={geometry} data-hall-geometry transform={`translate(${off[0]} ${off[1]}) translate(470 280) scale(${z}) translate(-470 -280)`}>
          {!top && <polygon points={`${p(0, 0)} ${p(1, 0)} ${p(1, 0)[0]},${p(1, 0)[1] - 38} ${p(0, 0)[0]},${p(0, 0)[1] - 38}`} fill="#252137" stroke="#474058" />}
          <polygon data-room points={polygon(0, 0, 1, 1)} fill="url(#floor)" stroke="#4b465f" />
          <g stroke="#a7a0cc" strokeOpacity=".08">{Array.from({
              length: 9
            }, (_, i) => <React.Fragment key={i}><path d={`M${p(i / 8, 0)}L${p(i / 8, 1)}`} /><path d={`M${p(0, i / 8)}L${p(1, i / 8)}`} /></React.Fragment>)}</g>
          <polygon data-stage-area points={polygon(ax, ay, aw, ah)} fill="#9e84d5" fillOpacity=".09" stroke="#9c81cb" strokeOpacity=".45" />
          <text x={label[0]} y={label[1]} textAnchor="middle" fill="#b4a7cb" fontSize="11" letterSpacing="5">{t("hall.stageLabel")}</text>
          <g pointerEvents="none">{beams && positioned.map(f => {
              const v = values(f),
                kind = visuals[f.id] || fixtureKind(f);
              if (typeof v.dim !== "number" || v.dim <= 0 || f.missing) return null;
              const [sx, sy] = p(ghost?.id === f.id ? ghost.x : f.x, ghost?.id === f.id ? ghost.y : f.y),
                c = v.rgb ? rgbToHex(v.rgb) : "#b4a0db",
                opacity = clamp(v.dim / 100, 0, 1) * (v.source === "last" ? .18 : .5);
              if (kind === "bar") return <ellipse data-bar-glow={f.id} key={f.id} cx={sx} cy={sy} rx="19" ry="7" transform={`rotate(${fixtureAngle(f, kind, hall)} ${sx} ${sy})`} fill={c} opacity={opacity} filter="url(#halo)" />;
              if (kind === "head" && (v.pan == null || v.tilt == null)) return null;
              const direction = kind === "head" ? headDirection(f, v) : null;
              if (kind === "head" && direction == null) return null;
              const [tx, ty] = direction == null ? p(ax + aw / 2, ay + ah / 2) : p(clamp(f.x + Math.cos(direction) * .28, .02, .98), clamp(f.y + Math.sin(direction) * .28, .02, .98));
              return <g key={f.id} opacity={opacity}><path data-beam={f.id} d={`M${sx} ${sy}L${tx - 13} ${ty}Q${tx} ${ty + 9} ${tx + 13} ${ty}Z`} fill={`url(#beam-${f.id})`} /><ellipse cx={tx} cy={ty} rx="20" ry="7" fill={c} opacity=".25" filter="url(#halo)" /></g>;
            })}</g>
          {(editing ? [...positioned].sort((a,b)=>Number(selection.includes(a.id))-Number(selection.includes(b.id))) : positioned).map(f => {
            const kind = visuals[f.id] || fixtureKind(f),
              [w, h] = sizes[kind],
              v = values(f),
              [sx, sy] = p(ghost?.id === f.id ? ghost.x : f.x, ghost?.id === f.id ? ghost.y : f.y),
              on = selection.includes(f.id),
              hit=(touchTarget ? 22 : kind === "par" ? 12 : 15)/editorScale,
              angle = fixtureAngle(ghost?.id === f.id ? {...f,...ghost} : f, kind, hall) + (!editing && kind === "head" && headDirection(f, v) != null ? headDirection(f, v) * 180 / Math.PI + 90 : 0);
            return <g key={f.id} data-fixture={f.id} data-kind={kind} data-missing={!editing && f.missing ? "" : undefined} role="button" tabIndex={!editing && f.missing ? -1 : 0} aria-disabled={!editing && (busy || f.missing || !selectable)} aria-label={`${f.label || f.id}, ID ${f.id}`} aria-pressed={on} className={`stage-fixture ${on ? "selected" : ""}`} transform={`translate(${sx} ${sy})`} onClick={e => {if (!editing || e.detail === 0) choose(f,e);}} onKeyDown={e => {
              if (["Enter", " "].includes(e.key)) {
                e.preventDefault();
                choose(f, e);
              }
            }} onPointerDown={e => begin(e,"move",f)}>
              <title>{f.label} · {v.source === "simulation" ? t("hall.mockModel") : v.source === "readback" ? t("hall.readback") : v.source === "last" ? t("hall.lastKnown") : t("evidence.unconfirmed")}</title>
              <rect data-hall-hit={!editing && !f.missing ? "" : undefined}
                x={editing || touchTarget ? -hit : -16} y={editing || touchTarget ? -hit : -16}
                width={editing || touchTarget ? hit*2 : 32} height={editing || touchTarget ? hit*2 : 38}
                rx="6" fill={on ? "#ae91f51f" : "transparent"}
                stroke={candidate === f.id ? "#f7de9e" : on ? "#c1a5ff" : "none"}
                strokeWidth={candidate === f.id || (on && pickingMany) ? 2 : 1} />
              <g transform={`rotate(${angle}) translate(${-w / 2} ${-h / 2})`}>{glyph(f)}</g>
              {ids && <text x="0" y="25" textAnchor="middle" fontSize="9" fill={on ? "#e3d5ff" : "#b0a6c1"}>{f.id}</text>}
            </g>;
          })}
          {editing && selection.length === 1 && positioned.filter(f=>selection.includes(f.id)).map(f=>{
            const shown=ghost?.id===f.id ? {...f,...ghost} : f, [x,y]=p(shown.x,shown.y),
              angle=fixtureAngle(shown,visuals[f.id] || fixtureKind(f),hall),
              scale=editorScale,
              radius=42/scale, r=angle*Math.PI/180, hx=x+Math.sin(r)*radius, hy=y-Math.cos(r)*radius;
            return <g key={f.id} data-rotation={f.id} className="rotation-control">
              <path d={`M${x},${y}L${hx},${hy}`} stroke="#d4b7ff" strokeWidth={1/scale} pointerEvents="none"/>
              <g transform={`translate(${hx} ${hy})`} role="slider" tabIndex={locked ? -1 : 0} aria-label={t("hall.rotateFixture")} aria-description={t("hall.rotateKeys")} aria-valuemin={0} aria-valuemax={360} aria-valuenow={angle} aria-disabled={locked}
                onPointerDown={e=>begin(e,"rotate",f)} onKeyDown={e=>{
                  if (!locked && ["ArrowLeft","ArrowDown","ArrowRight","ArrowUp"].includes(e.key)) {
                    e.preventDefault();e.stopPropagation();
                    const delta=(e.key==="ArrowLeft" || e.key==="ArrowDown" ? -1 : 1)*(e.shiftKey ? 15 : .1);
                    onPlace?.({id:f.id,x:f.x,y:f.y,rot:Math.round(((angle+delta+360)%360)*10)/10});
                  }
                }}>
                <circle r={22/scale} fill="transparent"/>
                <circle r={8/scale} fill="#d4b7ff" stroke="#20192e" strokeWidth={2/scale} pointerEvents="none"/>
                <text x={13/scale} y={-10/scale} fontSize={11/scale} fill="#f0e4ff" pointerEvents="none">{angle.toFixed(1)}°</text>
              </g>
            </g>;
          })}
        </g>
      </svg>
      {!state.config && <div className="stage-empty">{t("hall.connectingMock")}</div>}
      {editing && <div className="zoom-controls"><button aria-label={t("hall.zoomOut")} onClick={() => setZoom(v => clamp(v - .15, .5, 4))}><Icon name="minus" size={14} /></button><span>{Math.round(z * 100)}%</span><button aria-label={t("hall.zoomIn")} onClick={() => setZoom(v => clamp(v + .15, .5, 4))}><Icon name="plus" size={14} /></button><button aria-label={t("common.resetView")} onClick={() => {
          setZoom(1);
          setOffset([0, 0]);
        }}><Icon name="reset" size={14} /></button></div>}
      <div className="model-label"><span className="model-dot" />{state.status?.mock ? t("hall.mockLightingHint") : t("hall.liveLightingHint")}</div>
      {groupsOpen && <div ref={groupPopup} id={groupPopupId} tabIndex={-1} role="region"
        className="local-detail hall-popup hall-groups" data-shortcut-layer="hall-groups" aria-label={t("hall.groups")}>
        <div><b>{t("hall.groups")}</b><button data-shortcut-dismiss aria-label={t("common.close")} onClick={() => {
          setGroupsOpen(false);
          groupToggle.current?.focus();
        }}>×</button></div>
        <div className="hall-group-list">{groupOptions.map(group => {
          const available = availableGroupIds(group, fixtures).length;
          const total = group.fixtures?.length || 0;
          return <button key={group.id} data-hall-group={group.id}
            disabled={!selectable || busy || available === 0} onClick={async () => {
              setGroupsOpen(false);
              await onSelectGroup(group);
              if (document.activeElement === document.body) groupToggle.current?.focus();
            }}>
            <strong>{group.label}</strong>
            <small>{t(isLocal(group) ? "fixtures.localGroup" : "fixtures.consoleGroup")} · {t("shell.fixtureCount", { count: total })}</small>
            {available !== total && <small>{t("hall.availableCount", { count: available })}</small>}
          </button>;
        })}</div>
        {!groupOptions.length && <small>{t("hall.noGroups")}</small>}
      </div>}
      {candidates?.length > 0 && <div ref={detailsPanel} className={`local-detail ${editing ? "" : "hall-popup hall-candidates"}`}
        data-shortcut-layer="local-area" role="region" aria-label={t(editing ? "hall.zoomedArea" : "hall.chooseFixture")}>
        <div><b>{t(editing ? "hall.preciseSelection" : "hall.chooseFixture")}</b><button data-shortcut-dismiss aria-label={t("hall.closeArea")}
          onClick={() => closeDetail()}>×</button></div>
        <div className="detail-fixtures">{candidates.map(f => <button key={f.id}
          aria-label={editing ? t("hall.pickFixtureId", { id: f.id }) : `${f.label || f.id}, ID ${f.id}`}
          aria-pressed={selection.includes(f.id)} disabled={!editing && (busy || !selectable)}
          onFocus={() => !editing && setCandidate(f.id)} onBlur={() => setCandidate(null)}
          onPointerEnter={() => !editing && setCandidate(f.id)} onPointerLeave={e => {
            if (document.activeElement !== e.currentTarget) setCandidate(null);
          }}
          onClick={e => {
            onSelect(f.id, e.shiftKey);
            if (!editing) closeDetail();
          }}>{glyph(f, "catalog")}<span>{!editing && <strong>{f.label || f.id}</strong>}ID {f.id}</span></button>)}</div>
        {editing && <small>{t("hall.areaHint")}</small>}
      </div>}
    </div>
    {pickingMany && <div className="hall-draft" ref={draftControls} tabIndex={-1}>
      <output aria-live="polite">{t("hall.draftCount", { count: draftIds.length })}</output>
      <div className="hall-draft-actions">
        <button className="hall-tool" data-shortcut-dismiss disabled={busy} onClick={onCancelDraft}>{t("common.cancel")}</button>
        <button className="hall-tool hall-apply" disabled={busy} onClick={async () => {
          if (!await onApplyDraft()) draftControls.current?.focus();
        }}>{t(busy ? "inspector.confirmingSelection" : "hall.applySelection")}</button>
      </div>
    </div>}
    {editing && <div className="stage-footer"><span><kbd>Shift</kbd> {t("hall.gestureHint")}</span><div><button aria-pressed={ids} className={ids ? "on" : ""} onClick={() => setIds(!ids)}>ID</button><button aria-pressed={beams} className={beams ? "on" : ""} onClick={() => setBeams(!beams)}>{t("hall.beams")}</button></div></div>}
  </section>;
}
