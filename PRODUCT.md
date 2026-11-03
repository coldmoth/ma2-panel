# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

- **Operator** (the project owner) and **helpers** who understand what stage light is for but do not want to learn grandMA2 internals. They set up a venue from an empty panel, place fixtures on a hall plan, make their own groups, and during a show both run recorded scenes and adjust fixtures live.

## Product Purpose

A local-network web panel for grandMA2 that starts empty for each new show: it reads the patch from MA2, lets the operator draw the hall and place real fixtures (with the selected fixture lit in the hall), and then controls light through that plan, groups and scenes. Browsers send actions over WebSocket to a bridge on the MA2 Windows machine, which turns them into Telnet commands.

## Operating Context

- Mostly a tablet held by fingers in a darkened hall during shows; also a laptop with a mouse during setup. The screen must not glare, actions must be fast and predictable.
- Primary device: tablet in landscape (iPad, Android tablet). Also phone and MacBook. Safari and Chrome. Touch and mouse.
- Hall Wi-Fi password is the only access control; there is no PIN.

## Capabilities and Constraints

- Sections in a side rail: Сцены (one ordered list of numbered, named scenes with Go/Off; console addresses live in the editor, master), Свет (pick groups, fixtures or on the plan; brightness, colour, Pan/Tilt joystick and 1° step cross in a separate movement tab, Zoom, Focus, strobe), Зал (layout editor: hall shape, step-by-step placement with highlight, panel groups, write a group to MA2, beam calibration), Шоу (current show, show files, explicit load and save), Площадка (link, fetch fixtures from MA2, read MA2 groups/presets/scenes). Pages `log.html`, `diag.html`, `settings.html`.
- Panel data (layout, hall, panel groups) lives in the panel per show; MA2 groups and presets are read-only copies, marked "MA2".
- No frameworks, no build step: plain `static/index.html`, `app.js`, `light.js`, `plan.js`, `move.js`, `style.css`.
- The panel shows what it last sent ("отправлено панелью"), never claims it as the console's value, except scene running state which is polled.
- Mock mode (`bridge.py --mock`) shows an "Имитация" badge.
- UI language: Russian.

## Product Principles

1. An operator who knows light but not MA2 gets from an empty panel to a working plan without reading a manual.
2. Nothing destructive happens on a single accidental tap: blackout needs a second press, store and show load show their target and ask first.
3. Connection state is always visible; a control that cannot act looks disabled.
4. Fits a dark hall: low glare, high legibility, big targets.

## Accessibility & Inclusion

Touch targets at least 48 px; works with mouse and keyboard; respects reduced motion.

## UI revision 2026-10-30

The operator sees one scene list independent of MA2 pages. New scene storage is proposed by the bridge, checked empty again after explicit confirmation, never overwritten automatically. Movement settings and panel presets are collapsed with explicit deletion; no absolute numerical Pan/Tilt entry. Preparation distinguishes saved data from successful reads of the current connection. Master shows only the last value sent successfully by the panel.
