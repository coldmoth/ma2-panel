"""Bidirectional grandMA2 Layout XML import, lossless patch export, and fresh generation.

Coordinate conventions:
- grandMA2 Layout canvas uses Cartesian coordinates (X right, Y up, arbitrary float units).
- LUMA 2D hall plan uses normalized coordinates (X in [0..1] left->right, Y in [0..1] top->bottom).
- Physical 3D mounting positions (`fixture["physical_pos"]`) are never mixed with 2D plan icon coordinates (`x`, `y`).
"""
from __future__ import annotations

import datetime
import math
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from .fixtures import local

MA2_NS = "http://schemas.malighting.de/grandma2/xml/MA"
DEFAULT_PAD = 0.08
MOVE_EPS = 1e-5
ROT_ATTRS = ("angle", "rotation", "obj_rotation")

# Matches a <LayoutSubFix ...>...</LayoutSubFix> (or LayoutSubFixture) or self-closing tag while
# leaving surrounding XML formatting, comments, namespaces, and <CObjects> completely untouched.
_LAYOUT_SUBFIX_BLOCK = re.compile(
    r"(<(?P<tag>(?:[A-Za-z_][\w.-]*:)?LayoutSubFix(?:ture)?)(?P<attrs>\b[^>]*)>)(?P<body>.*?)(</(?P=tag)>)"
    r"|(<(?P<stag>(?:[A-Za-z_][\w.-]*:)?LayoutSubFix(?:ture)?)(?P<sattrs>\b[^>]*)/\s*>)",
    re.S,
)
_ATTR_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _attr_pattern(name: str) -> re.Pattern[str]:
    pat = _ATTR_RE_CACHE.get(name)
    if pat is None:
        pat = re.compile(rf'(\b{re.escape(name)}\s*=\s*)(["\'])([^"\']*)\2')
        _ATTR_RE_CACHE[name] = pat
    return pat


def _parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        num = float(value.strip())
    except (ValueError, AttributeError):
        return None
    return num if math.isfinite(num) else None


def _extract_fixture_id(elem: ET.Element) -> tuple[int | None, bool]:
    """Return (fixture_id, is_channel_only) for a <LayoutSubFix> element."""
    for key in ("fix_id", "fixture_id"):
        raw = elem.get(key)
        if raw and raw.strip().isdigit():
            fid = int(raw.strip())
            return (fid if fid > 0 else None), False
    has_cha = False
    for child in elem.iter():
        if child is elem:
            continue
        if local(child.tag).lower() == "subfixture":
            for key in ("fix_id", "fixture_id"):
                raw = child.get(key)
                if raw and raw.strip().isdigit():
                    fid = int(raw.strip())
                    if fid > 0:
                        return fid, False
            if child.get("cha_id") is not None:
                has_cha = True
    return None, has_cha


def _extract_coords(elem: ET.Element) -> tuple[float, float, str] | None:
    """Return (x, y, coord_mode) from center_x/center_y or pos_x/pos_y."""
    cx, cy = _parse_float(elem.get("center_x")), _parse_float(elem.get("center_y"))
    if cx is not None and cy is not None:
        return cx, cy, "center"
    px, py = _parse_float(elem.get("pos_x")), _parse_float(elem.get("pos_y"))
    if px is not None and py is not None:
        return px, py, "pos"
    return None


def _extract_rotation(elem: ET.Element) -> tuple[float | None, str | None]:
    for attr in ROT_ATTRS:
        val = _parse_float(elem.get(attr))
        if val is not None:
            return val, attr
    return None, None


def parse_layout_xml(xml_text: str) -> dict:
    """Parse a grandMA2 Layout XML file into fixture placements and preserved metadata."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"битый XML Layout: {e}") from e

    layout_name = ""
    for elem in root.iter():
        tag = local(elem.tag)
        if tag in ("Group", "Layout") and elem.get("name"):
            layout_name = elem.get("name", "").strip()
            break
    if not layout_name:
        info = next((e for e in root.iter() if local(e.tag) == "Info"), None)
        if info is not None and info.get("showfile"):
            layout_name = info.get("showfile", "").strip()

    items: list[dict] = []
    skipped_channel_only = 0
    extra_elements = 0
    layout_datas = [e for e in root.iter() if local(e.tag) == "LayoutData"]
    containers = layout_datas or [root]

    for container in containers:
        for child in container:
            ctag = local(child.tag)
            if ctag in ("SubFixtures", "Subfixtures"):
                for item in child:
                    if local(item.tag) not in ("LayoutSubFix", "LayoutSubFixture"):
                        extra_elements += 1
            elif ctag == "CObjects":
                extra_elements += len(list(child))
            elif ctag not in ("LayoutSubFix", "LayoutSubFixture"):
                extra_elements += 1

    seen_index = 0
    for elem in root.iter():
        tag = local(elem.tag)
        if tag not in ("LayoutSubFix", "LayoutSubFixture"):
            continue
        coords = _extract_coords(elem)
        if coords is None:
            continue
        fid, is_cha = _extract_fixture_id(elem)
        if fid is None:
            if is_cha:
                skipped_channel_only += 1
            continue
        mx, my, coord_mode = coords
        rot_val, rot_attr = _extract_rotation(elem)
        items.append({
            "fixture_id": fid,
            "ma2_x": mx,
            "ma2_y": my,
            "coord_mode": coord_mode,
            "ma2_rot": rot_val,
            "rot_attr": rot_attr,
            "element_index": seen_index,
        })
        seen_index += 1

    if not items:
        raise ValueError("в Layout XML не найдено приборов с fix_id (LayoutSubFix)")

    return {
        "layout_name": layout_name,
        "items": items,
        "extra_elements": extra_elements,
        "skipped_channel_only": skipped_channel_only,
    }


def compute_bounds(items: list[dict], *, pad: float = DEFAULT_PAD) -> dict:
    """Compute bounding box & affine parameters for exact MA2 <-> LUMA round-trip."""
    xs = [float(i["ma2_x"]) for i in items]
    ys = [float(i["ma2_y"]) for i in items]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    if max_x - min_x < 1e-6:
        min_x -= 0.5
        max_x += 0.5
    if max_y - min_y < 1e-6:
        min_y -= 0.5
        max_y += 0.5
    return {
        "min_x": min_x,
        "max_x": max_x,
        "min_y": min_y,
        "max_y": max_y,
        "pad": pad,
        "y_invert": True,
    }


def ma2_to_luma(mx: float, my: float, bounds: dict) -> tuple[float, float]:
    """Map MA2 Layout coordinates -> LUMA normalized [0..1] plan coordinates."""
    pad = float(bounds.get("pad", DEFAULT_PAD))
    inner = max(1e-6, 1.0 - 2.0 * pad)
    span_x = max(1e-9, float(bounds["max_x"]) - float(bounds["min_x"]))
    span_y = max(1e-9, float(bounds["max_y"]) - float(bounds["min_y"]))
    u = pad + ((mx - float(bounds["min_x"])) / span_x) * inner
    if bounds.get("y_invert", True):
        v = pad + ((float(bounds["max_y"]) - my) / span_y) * inner
    else:
        v = pad + ((my - float(bounds["min_y"])) / span_y) * inner
    u = min(1.0, max(0.0, u))
    v = min(1.0, max(0.0, v))
    return round(u, 6), round(v, 6)


def luma_to_ma2(u: float, v: float, bounds: dict) -> tuple[float, float]:
    """Exact inverse: LUMA normalized [0..1] plan coordinates -> MA2 Layout coordinates."""
    pad = float(bounds.get("pad", DEFAULT_PAD))
    inner = max(1e-6, 1.0 - 2.0 * pad)
    span_x = max(1e-9, float(bounds["max_x"]) - float(bounds["min_x"]))
    span_y = max(1e-9, float(bounds["max_y"]) - float(bounds["min_y"]))
    mx = float(bounds["min_x"]) + ((u - pad) / inner) * span_x
    if bounds.get("y_invert", True):
        my = float(bounds["max_y"]) - ((v - pad) / inner) * span_y
    else:
        my = float(bounds["min_y"]) + ((v - pad) / inner) * span_y
    return round(mx, 3), round(my, 3)


def preview_layout_import(xml_text: str, fixtures: list[dict]) -> dict:
    """Preview importing a grandMA2 Layout XML into the current LUMA fixture plan without mutating it."""
    parsed = parse_layout_xml(xml_text)
    items = parsed["items"]
    bounds = compute_bounds(items)

    # First occurrence per Fixture ID defines its anchor on the 2D plan (multi-instance shifts stay relative on export).
    by_fid: dict[int, dict] = {}
    for item in items:
        by_fid.setdefault(item["fixture_id"], item)

    plan_by_id = {f["id"]: f for f in fixtures if not f.get("missing")}
    matched = []
    unmatched_xml_ids = []
    imported_positions: dict[str, dict] = {}

    for fid, item in sorted(by_fid.items()):
        u, v = ma2_to_luma(item["ma2_x"], item["ma2_y"], bounds)
        if fid in plan_by_id:
            f = plan_by_id[fid]
            old_x, old_y = f.get("x"), f.get("y")
            moved = old_x is None or old_y is None or abs(old_x - u) > MOVE_EPS or abs(old_y - v) > MOVE_EPS
            entry = {
                "id": fid,
                "label": f.get("label") or f.get("name") or f"#{fid}",
                "old_x": old_x,
                "old_y": old_y,
                "new_x": u,
                "new_y": v,
                "ma2_x": item["ma2_x"],
                "ma2_y": item["ma2_y"],
                "moved": moved,
            }
            if item["ma2_rot"] is not None:
                entry["ma2_rot"] = item["ma2_rot"]
                entry["rot_attr"] = item["rot_attr"]
            matched.append(entry)
            imported_positions[str(fid)] = {
                "x": u,
                "y": v,
                "ma2_x": item["ma2_x"],
                "ma2_y": item["ma2_y"],
                "ma2_rot": item["ma2_rot"],
                "rot_attr": item["rot_attr"],
                "coord_mode": item["coord_mode"],
            }
        else:
            unmatched_xml_ids.append(fid)

    matched_ids = {m["id"] for m in matched}
    unplaced_plan_ids = sorted(fid for fid in plan_by_id if fid not in matched_ids)

    return {
        "layout_name": parsed["layout_name"],
        "bounds": bounds,
        "extra_elements": parsed["extra_elements"],
        "skipped_channel_only": parsed["skipped_channel_only"],
        "xml_fixture_count": len(by_fid),
        "matched": matched,
        "unmatched_xml_ids": unmatched_xml_ids,
        "unplaced_plan_ids": unplaced_plan_ids,
        "imported_positions": imported_positions,
    }


def _replace_attr(open_tag: str, attr: str, value: str) -> str:
    pat = _attr_pattern(attr)
    if pat.search(open_tag):
        return pat.sub(rf"\g<1>\g<2>{value}\g<2>", open_tag, count=1)
    return open_tag


def patch_layout_xml(template_xml: str, fixtures: list[dict], layout_meta: dict) -> tuple[str, dict]:
    """Patch ONLY moved fixtures in *template_xml*, leaving every other XML node untouched.

    Non-moved fixtures and all non-fixture Layout objects (<CObjects>, borders, labels, macros,
    groups, cameras, grid settings, XML headers/stylesheets) are preserved verbatim.
    """
    try:
        ET.fromstring(template_xml)
    except ET.ParseError as e:
        raise ValueError(f"исходный шаблон Layout XML повреждён: {e}") from e

    bounds = layout_meta.get("bounds")
    if not isinstance(bounds, dict) or not {"min_x", "max_x", "min_y", "max_y"} <= set(bounds):
        raise ValueError("отсутствуют границы координат (bounds) для обратного пересчёта")

    imported_positions = layout_meta.get("imported_positions") or {}
    fixtures_by_id = {f["id"]: f for f in fixtures if not f.get("missing")}
    updated_ids: list[int] = []
    unchanged_ids: list[int] = []

    def _patch_block(match: re.Match[str]) -> str:
        full = match.group(0)
        is_self_closing = match.group("stag") is not None
        open_tag = full if is_self_closing else match.group(1)
        body = "" if is_self_closing else match.group("body")
        close_tag = "" if is_self_closing else match.group(5)

        try:
            elem = ET.fromstring(full)
        except ET.ParseError:
            return full

        fid, _ = _extract_fixture_id(elem)
        if fid is None or fid not in fixtures_by_id:
            return full
        coords = _extract_coords(elem)
        if coords is None:
            return full
        orig_mx, orig_my, coord_mode = coords
        f = fixtures_by_id[fid]
        fx, fy = f.get("x"), f.get("y")
        if fx is None or fy is None:
            return full

        baseline = imported_positions.get(str(fid))
        pos_changed = True
        rot_changed = False
        new_rot_val: float | None = None
        orig_rot, rot_attr = _extract_rotation(elem)

        if baseline is not None:
            pos_changed = abs(float(fx) - float(baseline["x"])) > MOVE_EPS or abs(float(fy) - float(baseline["y"])) > MOVE_EPS
            if rot_attr is not None and f.get("rot") is not None:
                base_rot = baseline.get("ma2_rot")
                if base_rot is None or abs(float(f["rot"]) - float(base_rot)) > 1e-3:
                    rot_changed = True
                    new_rot_val = float(f["rot"])
        else:
            # Fixture was in XML and later added to plan: compute target position and compare.
            cand_mx, cand_my = luma_to_ma2(float(fx), float(fy), bounds)
            pos_changed = abs(cand_mx - orig_mx) > 0.001 or abs(cand_my - orig_my) > 0.001

        if not pos_changed and not rot_changed:
            if fid not in unchanged_ids:
                unchanged_ids.append(fid)
            return full

        patched_open = open_tag
        if pos_changed:
            target_mx, target_my = luma_to_ma2(float(fx), float(fy), bounds)
            if baseline is not None:
                # Preserve relative offset for multi-instance subfixtures sharing one fix_id.
                dx = target_mx - float(baseline["ma2_x"])
                dy = target_my - float(baseline["ma2_y"])
                new_mx = round(orig_mx + dx, 3)
                new_my = round(orig_my + dy, 3)
            else:
                new_mx, new_my = target_mx, target_my
            x_attr, y_attr = ("center_x", "center_y") if coord_mode == "center" else ("pos_x", "pos_y")
            patched_open = _replace_attr(patched_open, x_attr, f"{new_mx:.3f}")
            patched_open = _replace_attr(patched_open, y_attr, f"{new_my:.3f}")

        if rot_changed and rot_attr is not None and new_rot_val is not None:
            patched_open = _replace_attr(patched_open, rot_attr, f"{new_rot_val:.3f}")

        if fid not in updated_ids:
            updated_ids.append(fid)
        return patched_open if is_self_closing else patched_open + body + close_tag

    patched = _LAYOUT_SUBFIX_BLOCK.sub(_patch_block, template_xml)
    try:
        ET.fromstring(patched)
    except ET.ParseError as e:
        raise ValueError(f"внутренняя ошибка генерации патча XML: {e}") from e

    return patched, {
        "mode": "patch",
        "updated_ids": sorted(updated_ids),
        "unchanged_ids": sorted(set(unchanged_ids) - set(updated_ids)),
        "extra_elements": layout_meta.get("extra_elements", 0),
    }


def generate_layout_xml(fixtures: list[dict], *, hall: dict | None = None, name: str = "LUMA Plan", show_name: str = "") -> tuple[str, dict]:
    """Generate a fresh valid grandMA2 3.9 Layout XML from LUMA plan coordinates."""
    width = float((hall or {}).get("w") or 16.0)
    depth = float((hall or {}).get("d") or 12.0)
    placed = [f for f in fixtures if not f.get("missing") and f.get("x") is not None and f.get("y") is not None]
    if not placed:
        raise ValueError("на плане нет размещённых приборов для экспорта в Layout XML")

    now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    safe_name = escape(name or "LUMA Plan", {'"': "&quot;"})
    safe_show = escape(show_name or "", {'"': "&quot;"})

    lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        f'<MA xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns="{MA2_NS}" '
        f'xsi:schemaLocation="{MA2_NS} http://schemas.malighting.de/grandma2/xml/3.9.60/MA.xsd" '
        'major_vers="3" minor_vers="9" stream_vers="60">',
        f'\t<Info datetime="{now}" showfile="{safe_show}" />',
        f'\t<Group index="0" name="{safe_name}">',
        '\t\t<LayoutData index="0" marker_visible="true" background_color="000000" '
        'visible_grid_h="1" visible_grid_w="0" snap_grid_h="0.5" snap_grid_w="0.5">',
        '\t\t\t<SubFixtures>',
    ]
    exported_ids = []
    for f in sorted(placed, key=lambda item: item["id"]):
        mx = round((float(f["x"]) - 0.5) * width, 3)
        my = round((0.5 - float(f["y"])) * depth, 3)
        exported_ids.append(f["id"])
        lines.append(
            f'\t\t\t\t<LayoutSubFix center_x="{mx:.3f}" center_y="{my:.3f}" '
            'size_w="0.800" size_h="0.800" border_color="5a5a5a" background_color="3c3c3c" font_size="Small">'
        )
        lines.append(f'\t\t\t\t\t<Subfixture fix_id="{int(f["id"])}" />')
        lines.append('\t\t\t\t</LayoutSubFix>')

    lines += [
        '\t\t\t</SubFixtures>',
        '\t\t</LayoutData>',
        '\t</Group>',
        '</MA>',
        '',
    ]
    xml_text = "\n".join(lines)
    ET.fromstring(xml_text)  # self-verify well-formed XML
    return xml_text, {
        "mode": "new",
        "updated_ids": exported_ids,
        "unchanged_ids": [],
        "extra_elements": 0,
    }
