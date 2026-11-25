import React from "react";
export const TYPES = [["head", "24 × 24"], ["bar", "26 × 6"], ["fresnel", "22 × 22"], ["profile", "26 × 20"], ["par", "18 × 18"], ["washer", "22 × 16"], ["generic", "18 × 18"]];
const planSizes = {
  head: [24, 24],
  bar: [26, 6],
  fresnel: [22, 22],
  profile: [26, 20],
  par: [18, 18],
  washer: [22, 16],
  generic: [18, 18]
};

// Three independent drawing systems. These glyphs belong only to /design-lab.
function Technical({
  kind
}) {
  switch (kind) {
    case "head":
      return <><path d="M5 12v9a11 7 0 0 0 22 0v-9M12 28v2h8v-2" /><rect x="10" y="3" width="12" height="20" rx="5" /><ellipse cx="16" cy="9" rx="4" ry="3" className="dl-optic" /><path d="M13 19h6M8 30h16" /></>;
    case "fresnel":
      return <><path d="M10 9 6 5v9l-3 2 3 2v9l4-4h12l4 4v-9l3-2-3-2V5l-4 4Z" /><circle cx="16" cy="16" r="6" /><circle cx="16" cy="16" r="3" className="dl-optic" /></>;
    case "profile":
      return <><path d="M3 11h12l5 3h8v9h-8l-5 3H3ZM7 11V7h8v4M10 26v3h8M22 14v9M28 13h3v11h-3M5 14v9" /><path d="M16 14v9" className="dl-optic" /></>;
    case "par":
      return <><path d="M7 12 10 26h12l3-14M4 16v9l12 5 12-5v-9" /><ellipse cx="16" cy="11" rx="9" ry="6" /><ellipse cx="16" cy="11" rx="5" ry="3" className="dl-optic" /></>;
    case "washer":
      return <><path d="M3 8h26v15H3ZM8 23v5h16v-5M7 12h18M7 16h18M7 20h18" /><path d="M7 16h18" className="dl-optic" /></>;
    default:
      return <><path d="m16 3 12 13-12 13L4 16ZM12 7h8M12 25h8" /><path d="M13 13a3 3 0 1 1 5 2l-2 2v2M16 23h.01" /></>;
  }
}
function Premium({
  kind
}) {
  const body = {
    fill: "var(--dl-solid)"
  };
  switch (kind) {
    case "head":
      return <><path d="M4 12h4v10q8 9 16 0V12h4v12q-3 5-10 5h-4Q7 29 4 24ZM11 29h10v2H11Z" fill="currentColor" stroke="none" /><rect x="9" y="2" width="14" height="22" rx="6" {...body} /><ellipse cx="16" cy="9" rx="5" ry="3.5" className="dl-optic dl-optic-fill" /><path d="M13 19h6" /></>;
    case "fresnel":
      return <><path d="m9 7-6-4v9l4 4-4 4v9l6-4h14l6 4v-9l-4-4 4-4V3l-6 4Z" {...body} /><circle cx="16" cy="16" r="8" /><circle cx="16" cy="16" r="5" className="dl-optic dl-optic-fill" /><circle cx="16" cy="16" r="2" fill="var(--dl-surface)" stroke="none" /></>;
    case "profile":
      return <><path d="M2 10h13l7 4h7v11h-7l-7 3H2ZM8 28v3h11" {...body} /><path d="M5 7h9v3M8 10v17M20 14v11M29 13h2v13h-2" /><path d="M24 17v5" className="dl-optic" strokeWidth="3" /></>;
    case "par":
      return <><path d="m6 12 5 16h10l5-16Z" {...body} /><path d="M3 16v9l13 6 13-6v-9" /><ellipse cx="16" cy="10" rx="10" ry="7" {...body} /><ellipse cx="16" cy="10" rx="6" ry="4" className="dl-optic dl-optic-fill" /></>;
    case "washer":
      return <><path d="M2 7h28v18H2ZM9 25v5h14v-5" {...body} />{[8, 16, 24].map(x => <path key={x} d={`M${x} 12v8`} className="dl-optic" strokeWidth="3" />)}<path d="M5 4h22" /></>;
    default:
      return <><path d="m16 2 14 14-14 14L2 16Z" {...body} /><path d="M12 12a4 4 0 0 1 8 0c0 3-4 3-4 6M16 23v.1" strokeWidth="2" /></>;
  }
}
function Plot({
  kind,
  detailed
}) {
  switch (kind) {
    case "head":
      return <><path d="M5 11v12l7 4h8l7-4V11M12 27v3h8v-3" /><path d="m10 5 12-2 3 15-12 2Z" fill="var(--dl-solid)" /><path d="m11 7 11-2" className="dl-optic" strokeWidth="3" />{detailed && <path d="m14 15 6-1M8 30h16" />}</>;
    case "fresnel":
      return <><path d="M9 8h14v16H9ZM9 8 5 4v8M23 8l4-4v8M9 24l-4 4v-8M23 24l4 4v-8" /><circle cx="16" cy="16" r="4" className="dl-optic" />{detailed && <circle cx="16" cy="16" r="6" />}</>;
    case "profile":
      return <><path d="M3 9h10l8 5h10v9H21l-8 5H3ZM10 9v19M25 14v9M7 28v3h10" fill="var(--dl-solid)" />{detailed && <path d="M4 5h8v4M17 16v6" />}<path d="M29 16v5" className="dl-optic" /></>;
    case "par":
      return <><path d="m8 12 3 14h10l3-14M5 16v9l11 5 11-5v-9" /><ellipse cx="16" cy="10" rx="8" ry="5" className="dl-optic" />{detailed && <ellipse cx="16" cy="10" rx="4" ry="2" />}</>;
    case "washer":
      return <><path d="m2 8 28 0-4 16H6ZM10 24v5h12v-5" fill="var(--dl-solid)" /><path d="M6 12h20" className="dl-optic" strokeWidth="2" />{detailed && <path d="M10 16v4M16 16v4M22 16v4" />}</>;
    default:
      return <><path d="m16 3 13 13-13 13L3 16Z" /><path d="M12 12a4 4 0 0 1 8 0c0 3-4 3-4 6M16 23h.01" /></>;
  }
}
export function DesignGlyph({
  kind = "head",
  variant = "B",
  context = "plan",
  ...props
}) {
  const detailed = context !== "plan";
  const [w, h] = kind === "bar" ? detailed ? [36, 8] : [26, 6] : detailed ? [context === "inspector" ? 36 : 32, context === "inspector" ? 36 : 32] : planSizes[kind];
  return <svg width={w} height={h} viewBox={kind === "bar" ? "0 0 36 8" : "0 0 32 32"} fill="none" stroke="currentColor" strokeWidth={variant === "A" ? 1.35 : variant === "B" ? 1.2 : 1.6} strokeLinejoin="round" strokeLinecap="round" aria-hidden="true" {...props}>
    {kind === "bar" ? <>
      {variant === "A" && <><rect x="1" y="1.5" width="34" height="5" rx=".5" /><path d="M4 4h28" className="dl-optic" /></>}
      {variant === "B" && <><rect x=".5" y=".5" width="35" height="7" rx="2" fill="var(--dl-solid)" /><path d="M4 4h28" className="dl-optic" strokeWidth="2" /></>}
      {variant === "C" && <><path d="M1 1v6M35 1v6M1 4h34" /><path d="M4 4h7m2 0h10m2 0h7" className="dl-optic" strokeWidth="2" /></>}
    </> : variant === "A" ? <Technical kind={kind} /> : variant === "B" ? <Premium kind={kind} /> : <Plot kind={kind} detailed={detailed} />}
  </svg>;
}
