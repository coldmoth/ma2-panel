import { DesignGlyph } from "./DesignGlyphs.jsx";
import React from "react";
const paths = {
  more: "M5 11h.01 M12 11h.01 M19 11h.01 M5 13h.01 M12 13h.01 M19 13h.01",
  hall: "M3 5h18v14H3z M3 9h18 M7 5v14 M17 5v14",
  fixtures: "M5 8h14v9H5z M8 4v4 M16 4v4 M8 17v3 M16 17v3 M9 11h6v3H9z",
  scenes: "m9 5 11 7-11 7z M4 5v14",
  layout: "M3 3h7v7H3z M14 3h7v7h-7z M3 14h7v7H3z M14 14h7v7h-7z",
  settings:
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.08a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.08a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v.08a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z",
  collapse: "m14 6-6 6 6 6",
  expand: "m10 6 6 6-6 6",
  power: "M12 2.5v9.5 M6.34 5.64a8.5 8.5 0 1 0 11.32 0",
  sun: "M12 3v2.2 M12 18.8V21 M3 12h2.2 M18.8 12H21 M5.64 5.64l1.56 1.56 M16.8 16.8l1.56 1.56 M5.64 18.36l1.56-1.56 M16.8 7.2l1.56-1.56 M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0",
  keyboard: "M2 6h20v12H2z M5 9h1 M9 9h1 M13 9h1 M17 9h2 M6 14h12",
  plus: "M12 5v14 M5 12h14",
  minus: "M5 12h14",
  reset: "M3 10a9 9 0 1 1 2 8 M3 3v7h7",
  search: "M16 16l5 5 M18 10a8 8 0 1 1-16 0 8 8 0 0 1 16 0",
  check: "m5 12 4 4 10-10",
  close: "m6 6 12 12 M6 18 18 6",
  arrow: "M5 12h14 m-5-5 5 5-5 5",
  link: "M10 13a5 5 0 0 0 7 0l4-4a4 4 0 0 0-6-6l-2 2 M14 11a5 5 0 0 0-7 0l-4 4a4 4 0 0 0 6 6l2-2",
  layers: "m12 3 10 6-10 6L2 9z M2 13l10 6 10-6 M2 17l10 6 10-6",
  info: "M12 10v7 M12 6v1 M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0",
  move: "M12 3v18 M3 12h18 M9 6l3-3 3 3 M9 18l3 3 3-3 M6 9l-3 3 3 3 M18 9l3 3-3 3",
  stop: "M6.5 6.5h11v11h-11z",
  play: "M8 5.5v13l10.5-6.5z",
  chevronUp: "m6 15 6-6 6 6",
  chevronDown: "m6 9 6 6 6-6",
  undo: "M4 9h10a5 5 0 1 1 0 10H10 M8 5 4 9l4 4",
  redo: "M20 9H10a5 5 0 1 0 0 10h4 M16 5l4 4-4 4",
  download: "M12 3v12 M7 10l5 5 5-5 M4 19h16",
};
const FILLED_ICONS = new Set(["stop", "play"]);
export function Icon({ name, size = 18, ...props }) {
  const filled = FILLED_ICONS.has(name);
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={filled ? "1.2" : "1.65"}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d={paths[name] || paths.info} />
    </svg>
  );
}
export function FixtureGlyph({kind="head",size=32,color="currentColor"}) {
  const compact = kind === "par" ? size*.75 : size;
  return <DesignGlyph kind={kind} variant="B" context="catalog" width={kind === "bar" ? size : compact} height={kind === "bar" ? Math.max(6,size*.22) : compact} style={{color,"--dl-solid":"#222638","--dl-surface":"#131620","--optic":color}} />;
}
