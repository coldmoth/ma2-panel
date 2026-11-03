---
name: Свет · MA2 panel
description: A dark, neutral working panel for running stage light from a tablet; colour carries state only.
colors:
  ground: "#111315"
  s1: "#191c1f"
  s2: "#23272b"
  s3: "#30363b"
  s4: "#424950"
  ink: "#ebe7e0"
  ink-2: "#aeaaa2"
  ink-3: "#7b7871"
  sel: "#dbb76e"
  sel-ink: "#1b1305"
  live: "#99c5a2"
  live-ink: "#0b1a0c"
  edit: "#84b6bd"
  edit-ink: "#06191c"
  edit-ground: "#0f2427"
  warn: "#e8a33c"
  warn-soft: "#2e2413"
  warn-text: "#f4c784"
  bad: "#d9443a"
  bad-ink: "#fff4f1"
  bad-text: "#ff9f93"
  bad-soft: "#351816"
typography:
  body:
    fontFamily: "system-ui, -apple-system, \"Segoe UI\", Roboto, sans-serif"
    fontSize: "16px"
    lineHeight: 1.4
  page-title: { fontSize: "24px", fontWeight: 750 }
  card-title: { fontSize: "18px", fontWeight: 650 }
  control: { fontSize: "15px", fontWeight: 600 }
  label: { fontSize: "14px", fontWeight: 600 }
  small: { fontSize: "13px" }
  readout: { fontSize: "26px", fontWeight: 650, fontFeature: "\"tnum\"" }
rounded:
  r: "7px"
  card: "8px"
  rail: "7px"
  round: "50%"
---

# Design System: Свет · MA2 panel

## Overview

A working tool, not a themed object. The ground is a near-black neutral so the screen does not light the hall; surfaces step up in tone (`s1`–`s4`) instead of using lines or shadows. Colour is reserved for state, and each state has one colour:

- **Amber `sel`** — what the controls act on: selected fixtures and groups, slider fill, focus ring.
- **Green `live`** — running scene, link online.
- **Cyan `edit`** — venue preparation (Площадка, Зал, Шоу): the rail group, the mode chip, Зал's bar, plan frame and highlight target.
- **Orange `warn`** — transmission stopped, show loading, unknown login, mismatched show.
- **Red `bad`** — «Погасить свет» and errors only.

## Layout

Two modes, told apart by the whole frame, not by a label alone:

- **Концерт** (Сцены, Свет): top of the rail, neutral ground.
- **Подготовка** (Площадка, Зал, Шоу): bottom of the rail under a cyan «Подготовка» divider; the working area takes a cool ground (`#0b1214`), the top bar `edit-ground` and a «Подготовка» chip. The current setup section has a cyan ring in the rail.

Rail 96 px (84 px under 1100 px, a bottom bar with a divider between the two groups under 860 px, 56 px buttons when the window is under 680 px tall). Top bar: show name, link state, selection pill (live mode only), «Стоп передачи» (outlined) and «Погасить свет» (filled red); under 520 px both buttons share their own row. Banners for link, halt, load, highlight and show mismatch sit under the top bar. A reload keeps the section it came back to; until the plan arrives the page says «Загружаю план панели…».

Свет: picker column 260 px (240 px at 1024), tabs Группы / Приборы / План. Shared selection and fade above two control tabs: Свет (brightness, strobe, colour) and Движение (joystick, fine step cross, optics). Movement modes Точно / Зеркально are matching toggle buttons; inversions live in collapsed Настройки движения; presets in collapsed Пресеты with explicit management. No numeric absolute Pan/Tilt entry. The joystick and 1° step cross fit 1024×768 and 1280×720 without scrolling when secondary settings are closed.

Площадка: four preparation steps (link, fixtures, MA2 data, hall), each with its state; the hall step opens Зал. The fixture table scrolls with the page, not inside it.

Зал: plan and a 320 px list, a cyan bar with tabs and the highlight checkbox, and a compact current-fixture bar at the bottom for step-by-step placement. Icon, rotation and flags live in collapsed Настройки прибора. A plan smaller than 440 × 380 px shows fixture numbers instead of names.

## Components

- **Buttons**: 48 px tall, 7 px corners, `s3` fill; `primary` amber, `edit` cyan, `blackout` red, `stop` outlined. Disabled: `s2` fill, `ink-3` text. A pending action has aria-busy; its label keeps its meaning. Result notices use separate info/success/warning/error styles; important errors remain until dismissed.
- **Row item**: 52 px, checkbox square + ID + name; selected = amber wash with an amber inset ring; in Зал the current fixture is cyan instead.
- **Slider**: 12 px track, 36 px thumb; unknown value = striped track and a hollow grey thumb, readout «неизвестно».
- **Colour picker**: a wheel (hue by angle, saturation by radius, centre snaps to white) beside a preview chip, Насыщенность and Светлота цвета sliders and ten quick swatches (44 px minimum). Светлота darkens the wheel through a black shade. It sends `color` only; brightness stays on its own slider. Unknown colour = striped chip, no marker, sliders disabled until a hue is picked; different colours across the selection say so. A selection without RGB/CMY mixing gets no wheel, only MA2 colour presets or a plain statement that colour is not controlled.
- **Plan fixture**: 52 px hit area; shape by kind (round PAR, rounded square head, bar, diamond fresnel); selected = amber ring with a gap; lit = its last sent colour; missing = red outline at 45 %; service = hatched.
- **Scene tile**: a simple display number and scene name, no console address or page headers. Running uses a muted green surface and state label. Off and Edit are separate controls below the launch target; deletion and overwrite are inside Edit. The teacher panel uses the same order.

## Rules

- Never pure white text or a pure black ground.
- No shadows at rest; only dialogs float.
- Values the panel sent are labelled as such; the panel never presents them as the console's value.
- Every touch target is at least 44 × 44 px, main controls 48 px.

## 2026-10-30 implementation

Graphite work surfaces, radii 6–10 px. Connection text remains visible on tablet/phone; banners explain problems. Preserve 48 px main and 44 px secondary touch targets, keyboard focus and reduced motion. For the accepted behavior see docs/superpowers/specs/2026-10-30-tablet-ui-design.md.
