import { useLanguage } from "./Language.jsx";
import React, { useState } from "react";
import { DesignGlyph, TYPES } from "./DesignGlyphs.jsx";
import "./design-lab.css";
const CONCEPTS = {
  A: {
    name: "design.aName",
    line: "design.aHeadline",
    description: "design.aDescription",
    strength: "design.aPlus",
    tradeoff: "design.aTradeoff"
  },
  B: {
    name: "design.bName",
    line: "design.bHeadline",
    description: "design.bDescription",
    strength: "design.bPlus",
    tradeoff: "design.bTradeoff"
  },
  C: {
    name: "design.cName",
    line: "design.cHeadline",
    description: "design.cDescription",
    strength: "design.cPlus",
    tradeoff: "design.cTradeoff"
  }
};
const FIXTURES = [...[.27, .44, .61, .78].map((x, i) => ({
  id: 201 + i,
  kind: "bar",
  x,
  y: .09,
  color: "#e5ad6f",
  dim: .75
})), ...[.29, .48, .67].map((y, i) => ({
  id: 205 + i,
  kind: "bar",
  x: .07,
  y,
  color: "#69c7b6",
  dim: i === 1 ? .45 : .85
})),
// Manual graphic rotation wins over wall orientation. This is not MA2 Pan/Tilt.
{
  id: 208,
  kind: "bar",
  x: .92,
  y: .52,
  rotation: 32,
  color: "#aaa5e7",
  dim: .65
}, ...[.24, .43, .62, .81].map((x, i) => ({
  id: 101 + i,
  kind: "head",
  x,
  y: .32,
  rotation: [-32, 12, 38, -18][i],
  color: ["#69c7b6", "#e5ad6f", "#aaa5e7", "#69c7b6"][i],
  dim: [.55, .8, .65, .5][i]
})), {
  id: 301,
  kind: "profile",
  x: .25,
  y: .68,
  color: "#e5ad6f",
  dim: .7
}, {
  id: 302,
  kind: "washer",
  x: .42,
  y: .81,
  color: "#aaa5e7",
  dim: .65
}, {
  id: 303,
  kind: "fresnel",
  x: .48,
  y: .56,
  color: "#e5ad6f",
  dim: .5
}, {
  id: 401,
  kind: "par",
  x: .685,
  y: .70,
  color: "#69c7b6",
  dim: .7
}, {
  id: 402,
  kind: "par",
  x: .71,
  y: .70,
  color: "#e5ad6f",
  dim: .65
}, {
  id: 403,
  kind: "par",
  x: .735,
  y: .70,
  color: "#aaa5e7",
  dim: .8
}, {
  id: 404,
  kind: "fresnel",
  x: .78,
  y: .70,
  color: "#e5ad6f",
  dim: .5
}, {
  id: 501,
  kind: "par",
  x: .21,
  y: .89,
  inactive: true,
  color: "#69c7b6",
  dim: 0
}, {
  id: 901,
  kind: "generic",
  x: .87,
  y: .89,
  unknown: true,
  color: "#abb5c0",
  dim: 0
}];
const CLOSE = FIXTURES.filter(f => f.id >= 401 && f.id <= 404);
const orient = f => f.rotation ?? (f.kind === "bar" && (f.x < .12 || f.x > .88) ? 90 : 0);
function project(f, top) {
  return [top ? 10 + f.x * 80 : 50 + (f.x - .5) * (55 + f.y * 34), 22 + f.y * 65];
}
function Fixture({
  f,
  variant,
  selected,
  toggle,
  ids,
  context = "plan",
  interactive = true
}) {
  const { t } = useLanguage();
  let name = `${t(`kind.${f.kind}`)} ${f.id}`;
  if (f.inactive) name = t("design.fixtureInactive", { name });
  if (f.unknown) name = t("design.fixtureUnknown", { name });
  const Element = interactive ? "button" : "div";
  return <Element type={interactive ? "button" : undefined} className={`dl-fixture ${selected ? "is-selected" : ""} ${f.inactive ? "is-inactive" : ""} ${f.unknown ? "is-unknown" : ""}`} aria-label={name} aria-pressed={interactive ? selected : undefined} onClick={interactive ? () => toggle(f.id) : undefined} style={{
    "--dl-light": f.color
  }}>
    <span className="dl-fixture-art" style={{
      transform: `rotate(${orient(f)}deg)`
    }}><DesignGlyph kind={f.kind} variant={variant} context={context} /></span>
    {ids && <span className="dl-fixture-id">{f.id}</span>}
  </Element>;
}
function Room({
  top = false,
  variant,
  selected,
  toggle,
  ids,
  effects,
  surface,
  onClose
}) {
  const { t } = useLanguage();
  const corners = top ? "10,22 90,22 90,87 10,87" : "22.5,22 77.5,22 94.5,87 5.5,87";
  return <section className={`dl-room dl-surface-${surface}`} aria-label={top ? t("hall.top") : t("design.roomPerspective")}>
    <div className="dl-room-top"><span className="dl-room-label">{top ? t("design.roomTopLabel") : t("design.roomPerspectiveLabel")}</span><span>{t("design.dimensions")}</span></div>
    <svg className="dl-room-map" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
      <defs><pattern id={`grid-${top}`} width="6" height="8" patternUnits="userSpaceOnUse"><path d="M6 0H0V8" className="dl-map-grid" fill="none" /></pattern><clipPath id={`floor-${top}`}><polygon points={corners} /></clipPath></defs>
      {!top && <><path d="M22.5 22v-7h55v7M22.5 15 5.5 80v7M77.5 15l17 65v7" className="dl-wall" fill="none" /><path d="M22.5 15 5.5 80v7L22.5 22ZM77.5 15l17 65v7L77.5 22Z" className="dl-wall-fill" /></>}
      <polygon points={corners} className="dl-floor" />
      <polygon points={corners} fill={`url(#grid-${top})`} />
      <g clipPath={`url(#floor-${top})`}>
        <path d={top ? "M33 22h34v17H33Z" : "M35 22h30l2 17H33Z"} className="dl-stage-fill" />
        {effects && FIXTURES.filter(f => f.dim > 0 && f.kind !== "bar").map(f => {
          const [x, y] = project(f, top);
          if (f.kind === "head") {
            const dx = Math.sin(orient(f) * Math.PI / 180) * 12;
            return <g key={f.id} className="dl-head-effect" style={{
              color: f.color,
              opacity: f.dim * .17
            }}><path d={`M${x} ${y} ${x + dx - 3} ${y + 25} ${x + dx + 3} ${y + 25}Z`} fill="currentColor" /><ellipse cx={x + dx} cy={y + 25} rx="4" ry="2" fill="currentColor" /></g>;
          }
          return <ellipse key={f.id} cx={x} cy={y + 5} rx={f.kind === "washer" ? 8 : f.kind === "profile" ? 2.3 : 3.2} ry={f.kind === "washer" ? 1.8 : 3.8} fill={f.color} opacity={f.dim * .12} />;
        })}
      </g>
    </svg>
    <span className="dl-stage-label">{t("hall.stageLabel")}</span>
    {effects && FIXTURES.filter(f => f.kind === "bar").map(f => {
      const [x, y] = project(f, top);
      return <span key={f.id} className="dl-bar-halo" style={{
        left: `${x}%`,
        top: `${y}%`,
        transform: `translate(-50%, -50%) rotate(${orient(f)}deg)`,
        background: f.color,
        opacity: f.dim * .3
      }} />;
    })}
    {FIXTURES.map(f => {
      const [x, y] = project(f, top);
      return <div key={f.id} className={`dl-position ${f.id >= 401 && f.id <= 404 ? "dl-dense-position" : ""}`} style={{
        left: `${x}%`,
        top: `${y}%`
      }}><Fixture {...{
          f,
          variant,
          toggle
        }} selected={selected.includes(f.id)} ids={ids && !(f.id >= 401 && f.id <= 404)} /></div>;
    })}
    <button className="dl-cluster-link" type="button" onClick={onClose}>{t("design.cluster")}</button>
    <div className="dl-room-bottom"><span>{t("design.roomFixtures")}</span><span>{t("design.autoFit")}</span></div>
  </section>;
}
export default function DesignLab() {
  const { t } = useLanguage();
  const [variant, setVariant] = useState("B"),
    [ids, setIds] = useState(true),
    [effects, setEffects] = useState(true),
    [surface, setSurface] = useState("dark"),
    [selected, setSelected] = useState([102, 402]),
    [cluster, setCluster] = useState(true);
  const concept = CONCEPTS[variant];
  const toggle = id => setSelected(s => s.includes(id) ? s.filter(v => v !== id) : [...s, id]);
  return <div className="dl-page">
    <header className="dl-header"><a className="dl-brand" href="/" aria-label={t("design.back")}><span className="dl-brand-mark">L</span>LUMA<span className="dl-brand-lab">{t("design.lab")}</span></a><span className="dl-header-context">{t("design.shapeStudy")} <span>/</span> 01</span><span className="dl-local"><i />{t("design.prototype")}</span></header>
    <main className="dl-main">
      <div className="dl-intro"><div><p className="dl-eyebrow">{t("design.concepts")}</p><h1>{t("design.smallShapes")}<br className="dl-mobile-break" /> {t("design.clearPlan")}</h1><p className="dl-subtitle">{t("design.intro")}</p></div><div className="dl-version">LUMA <span>v2</span><small>{t("design.phase")}</small></div></div>
      <div className="dl-navigation" role="group" aria-label={t("design.iconSet")}>
        {Object.entries(CONCEPTS).map(([key, c]) => <button type="button" key={key} className={`dl-concept ${variant === key ? "is-active" : ""}`} aria-pressed={variant === key} onClick={() => setVariant(key)}><span className="dl-concept-letter">{key}</span><span><b>{t(c.name)}</b><small>{key === "A" ? t("design.outline") : key === "B" ? t("design.silhouette") : t("design.symbol")}</small></span><span className="dl-concept-dot" /></button>)}
      </div>
      <div className="dl-section-heading"><div><span className="dl-index">{variant}</span><h2>{t(concept.name)}</h2><span className="dl-heading-note">{t(concept.line)}</span></div><div className="dl-controls"><button type="button" aria-pressed={ids} onClick={() => setIds(v => !v)}>ID <span className={`dl-switch ${ids ? "on" : ""}`} /></button><button type="button" aria-pressed={effects} onClick={() => setEffects(v => !v)}>{t("groupIcon.sun")} <span className={`dl-switch ${effects ? "on" : ""}`} /></button><div className="dl-surface-toggle" role="group" aria-label={t("design.background")}><button type="button" aria-label={t("design.darkBackground")} aria-pressed={surface === "dark"} onClick={() => setSurface("dark")}>{t("design.dark")}</button><button type="button" aria-label={t("design.lightBackground")} aria-pressed={surface === "light"} onClick={() => setSurface("light")}>{t("design.light")}</button></div></div></div>
      <div className="dl-rooms"><Room {...{
          variant,
          selected,
          toggle,
          ids,
          effects,
          surface
        }} onClose={() => {
          setCluster(true);
          document.getElementById("dl-closeup")?.scrollIntoView({
            block: "nearest",
            behavior: "smooth"
          });
        }} /><Room top {...{
          variant,
          selected,
          toggle,
          ids,
          effects,
          surface
        }} onClose={() => setCluster(true)} /></div>
      <section className={`dl-library dl-surface-${surface}`} aria-label={t("design.familyHint")}><div className="dl-library-side"><span className="dl-mini-title">{t("design.family")}</span><b>{t("design.sevenShapes")}<br />{t("design.oneStyle")}</b><span className="dl-mini-note">{t("design.cssSizes")}</span></div><div className="dl-specimens">{TYPES.map(([kind, size]) => <div className="dl-specimen" key={kind}><div className="dl-specimen-icons"><div><DesignGlyph {...{
                  kind,
                  variant
                }} /><span>{t("design.plan")}</span></div><div><DesignGlyph {...{
                  kind,
                  variant
                }} context="catalog" /><span>{t("design.catalog")}</span></div></div><b>{t(`kind.${kind}`)}</b><small>{size} px</small></div>)}</div></section>
      <div className="dl-details">
        <section className={`dl-detail-card dl-closeup ${cluster ? "" : "is-collapsed"}`} id="dl-closeup" aria-label={t("design.denseArea")}><div className="dl-card-heading"><div><span className="dl-mini-title">{t("design.precise")}</span><h3>{t("design.closeTogether")}</h3></div><button type="button" aria-expanded={cluster} aria-label={cluster ? t("design.collapseDetail") : t("design.expandDetail")} onClick={() => setCluster(v => !v)}>{cluster ? "−" : "+"}</button></div>{cluster && <><div className={`dl-closeup-fixtures dl-surface-${surface}`}>{CLOSE.map(f => <div key={f.id}><Fixture {...{
                  f,
                  variant,
                  toggle,
                  ids
                }} context="catalog" selected={selected.includes(f.id)} /><span>{t(`kind.${f.kind}`)}</span></div>)}</div><p>{t("design.detailHint")}</p></>}</section>
        <section className="dl-detail-card dl-states"><span className="dl-mini-title">{t("design.states")}</span><h3>{t("design.readableShapes")}</h3><div className={`dl-state-samples dl-surface-${surface}`}>{[[t("design.normal"), {}], [t("design.selected"), {
              selected: true
            }], [t("design.inactive"), {
              inactive: true
            }], [t("design.unknown"), {
              unknown: true
            }]].map(([label, s], i) => <div key={label}><Fixture f={{
                id: 601 + i,
                kind: i === 3 ? "generic" : "head",
                color: "#69c7b6",
                ...s
              }} {...{
                variant
              }} selected={s.selected} interactive={false} ids={false} /><span>{label}</span></div>)}</div><p>{t("design.stateHint")}</p></section>
        <section className="dl-detail-card dl-inspector-demo"><span className="dl-mini-title">{t("design.inspectorSample")}</span><div className="dl-inspector-heading"><DesignGlyph kind="head" variant={variant} context="inspector" /><div><h3>{t("kind.head")} <span>102</span></h3><p>{t("design.opticsMovement")}</p></div><span className="dl-demo-pill">{t("design.demo")}</span></div><div className="dl-demo-values"><div><span>{t("tool.dim")}</span><b>80<small>%</small></b></div><div><span>Pan</span><b>−110<small>°</small></b></div><div><span>Tilt</span><b>32<small>°</small></b></div></div><p>{t("design.sampleValues")}</p></section>
      </div>
      <aside className="dl-concept-note" aria-live="polite"><span className="dl-note-letter">{variant}</span><p>{t(concept.description)}</p><div><span>{t("design.advantage")}</span>{t(concept.strength)}</div><div><span>{t("design.tradeoff")}</span>{t(concept.tradeoff)}</div></aside>
      <footer className="dl-footer"><span>{t("design.localOnly")}</span><a href="/">{t("design.openApp")}</a></footer>
    </main>
  </div>;
}
