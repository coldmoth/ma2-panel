export const clamp = (v, lo = 0, hi = 100) => Math.max(lo, Math.min(hi, v));
export const FIXTURE_KINDS = ["head", "bar", "profile", "fresnel", "par", "washer", "generic"];
export function fixtureKind(f) {
  if (FIXTURE_KINDS.includes(f.icon)) return f.icon;
  const name = (f.type || "").toLowerCase();
  if (/bar|баттен|линей/.test(name)) return "bar";
  if (/wash.*wall|wall.*wash|панель/.test(name)) return "washer";
  if (/fresnel|френел/.test(name)) return "fresnel";
  if (/profile|профил|ellipsoid|source four/.test(name)) return "profile";
  if (
    f.moves ||
    /moving|beam|head/.test(name) ||
    ((f.params || []).some((p) => /^pan$/i.test(p)) &&
      (f.params || []).some((p) => /^tilt$/i.test(p)))
  )
    return "head";
  if (/par|залив/.test(name)) return "par";
  return "generic";
}
export function supports(f, key, config = {}) {
  if (f.missing) return false;
  const params = f.params || [];
  if (key === "pos")
    return (
      f.moves === true ||
      ["Pan", "Tilt"].every((p) =>
        params.some((v) => v.toLowerCase() === p.toLowerCase()),
      )
    );
  if (key === "color" && f.color === "none") return false;
  if (key === "color" && ["rgb", "cmy"].includes(f.color)) return true;
  const re = {
    dim: /dim|intens/i,
    color: /colorrgb|red|green|blue|cyan|magenta|yellow/i,
    zoom: /^zoom$/i,
    focus: /^focus$/i,
    strobe: /strob|shutter/i,
  }[key];
  if (re && params.some((p) => re.test(p))) return true;
  const map = config.dmx_map?.[f.type];
  if (!map || map.stale) return false;
  if (key === "dim") return Number.isInteger(map.dim) && map.dim > 0;
  if (key === "color")
    return ["r", "g", "b"].every((k) => Number.isInteger(map[k]) && map[k] > 0);
  return (map.has || []).includes(key);
}
export function displayValues(state, id) {
  const out = {}, quality = {};
  for (const [key, entry] of Object.entries(state.history?.[id] || {})) {
    out[key] = entry.value;
    quality[key] = entry.quality;
  }
  return {...out, quality, source: Object.values(quality).some(q => ["pending","unconfirmed"].includes(q)) ? "pending"
    : Object.values(quality).includes("last") ? "last"
    : Object.values(quality).includes("confirmed") ? "readback" : "unknown"};
}
export function currentDimmer(state, now = Date.now()) {
  const meta = state.values_meta?.live;
  if (meta?.source !== "ma2" || meta.freshness !== "fresh") return null;
  const values = state.selected.map((id) => {
    const entry = state.history?.[id]?.dim;
    return entry?.quality === "confirmed" && now - entry.confirmedAt <= 6000 &&
      Number.isFinite(entry.value) && entry.value >= 0 && entry.value <= 100 &&
      state.live?.[id]?.dim === entry.value ? entry.value : null;
  });
  const distinct = new Set(values.filter((value) => value !== null));
  if (distinct.size > 1) return "mixed";
  return values.includes(null) ? null : values[0] ?? null;
}
export function dimmerSupportCount(state) {
  const fixtures = state.config?.fixtures || [];
  const blockedTypes = state.status?.no_attr?.dim || [];
  return state.selected.filter((id) => {
    const fixture = fixtures.find((f) => f.id === id);
    return fixture && supports(fixture, "dim", state.config) && !blockedTypes.includes(fixture.type);
  }).length;
}
export function fixtureAngle(f, kind, hall = {}) {
  if (Number.isFinite(f.rot)) return f.rot;
  return kind === "bar" && Math.min(f.x, 1-f.x) * (hall.w || 1) < Math.min(f.y, 1-f.y) * (hall.d || 1) ? 90 : 0;
}
export const DEFAULT_HALL = {w: 18, d: 24, stage: "top", stageDepth: 4};

export function stageRect(hall = DEFAULT_HALL) {
  const horizontal = !["left","right"].includes(hall.stage),
    width = horizontal ? (hall.w || 18) : (hall.d || 24),
    depth = horizontal ? (hall.d || 24) : (hall.w || 18),
    span = clamp((hall.stageWidth ?? width)/width,0,1),
    thick = clamp((hall.stageDepth || 4)/depth,0,1),
    start = (1-span)*(hall.stageOffset ?? .5);
  return horizontal ? [start, hall.stage === "bottom" ? 1-thick : 0, span, thick]
    : [hall.stage === "right" ? 1-thick : 0, start, thick, span];
}
export function commonValue(values, key) {
  if (!values.length) return null;
  const vs = values.map((v) => v[key] ?? null);
  if (vs.every((v) => v === null)) return null;
  return vs.every((v) => JSON.stringify(v) === JSON.stringify(vs[0]))
    ? vs[0]
    : "mixed";
}
export function blackoutKey(phase, armedAt, now) {
  if (phase === "active") return { armedAt: null, send: true };
  if (phase !== "idle") return { armedAt: null, send: false };
  if (armedAt !== null && now - armedAt <= 600 && now >= armedAt)
    return { armedAt: null, send: true };
  return { armedAt: now, send: false };
}
export function hexToRGB(hex) {
  return [1, 3, 5].map(
    (i) => Math.round((parseInt(hex.slice(i, i + 2), 16) / 255) * 1000) / 10,
  );
}
export function rgbToHex(rgb) {
  return (
    "#" +
    rgb
      .map((n) =>
        Math.round(clamp(n) * 2.55)
          .toString(16)
          .padStart(2, "0"),
      )
      .join("")
  );
}
export function hsvToHex(h, s, v) {
  const c = ((v / 100) * s) / 100,
    x = c * (1 - Math.abs(((h / 60) % 2) - 1)),
    m = v / 100 - c;
  const p =
    h < 60
      ? [c, x, 0]
      : h < 120
        ? [x, c, 0]
        : h < 180
          ? [0, c, x]
          : h < 240
            ? [0, x, c]
            : h < 300
              ? [x, 0, c]
              : [c, 0, x];
  return rgbToHex(p.map((n) => (n + m) * 100));
}
export function hexToHSV(hex) {
  const [r, g, b] = hexToRGB(hex).map((v) => v / 100),
    max = Math.max(r, g, b),
    min = Math.min(r, g, b),
    d = max - min;
  let h =
    d === 0
      ? 0
      : max === r
        ? 60 * (((g - b) / d) % 6)
        : max === g
          ? 60 * ((b - r) / d + 2)
          : 60 * ((r - g) / d + 4);
  return [
    Math.round((h + 360) % 360),
    Math.round(max === 0 ? 0 : (d / max) * 100),
    Math.round(max * 100),
  ];
}
export function project(x, y, top, hall) {
  if (hall) {
    const ratio = hall.w/hall.d, h = Math.min(380,720/ratio), w = h*ratio;
    return [470+(x-.5)*w*(top?1:.72+y*.28),280+(y-.5)*h];
  }
  return top
    ? [110 + x * 720, 90 + y * 380]
    : [470 + (x - 0.5) * (510 + y * 290), 90 + y * 380];
}
// Bounds cover the room wall, rotated fixture bodies and ID labels, in SVG units.
export function stageViewBox(hall, top, fixtures = []) {
  const p = (x,y) => project(x,y,top,hall);
  const points = [[0,0],[1,0],[1,1],[0,1]].map(([x,y])=>p(x,y));
  if (!top) points.push(...[p(0,0),p(1,0)].map(([x,y])=>[x,y-38]));
  for (const f of fixtures) {
    const [x,y]=p(f.x,f.y);
    points.push([x-23,y-23],[x+23,y+31]);
  }
  const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]),pad=14;
  return [Math.min(...xs)-pad,Math.min(...ys)-pad,Math.max(...xs)-Math.min(...xs)+pad*2,Math.max(...ys)-Math.min(...ys)+pad*2].join(' ');
}
export function inspectorLimits(viewport, sidebar) {
  const max = Math.max(120, Math.min(640, viewport * .48, viewport-sidebar-500));
  return {min:Math.min(280,max),max};
}
export function unproject(x, y, top, hall) {
  if (hall) {
    const ratio = hall.w/hall.d, h = Math.min(380,720/ratio), w = h*ratio,
      ny=clamp(.5+(y-280)/h,0,1);
    return [clamp(.5+(x-470)/(w*(top?1:.72+ny*.28)),0,1),ny];
  }
  const ny = clamp((y - 90) / 380, 0, 1);
  return [
    clamp(top ? (x - 110) / 720 : 0.5 + (x - 470) / (510 + ny * 290), 0, 1),
    ny,
  ];
}
export function sceneActive(state, id) {
  return state.running_meta?.[id]?.freshness === "fresh" &&
    typeof state.running?.[id] === "boolean"
    ? state.running[id]
    : null;
}
