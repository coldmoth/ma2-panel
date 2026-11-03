"""MA2 fixture export parsing and config persistence."""
import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET


def local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def describe(root) -> str:
    """What the file contains, for the error text and the diagnostics: the real MA2 XML layout has not been seen yet."""
    names = {}
    for e in root.iter():
        names[local(e.tag)] = names.get(local(e.tag), 0) + 1
    top = ", ".join(f"{n}×{c}" for n, c in sorted(names.items(), key=lambda kv: -kv[1])[:8])
    first = next((e for e in root.iter() if local(e.tag).endswith("Fixture")), None)
    attrs = f"; атрибуты первого {local(first.tag)}: {', '.join(first.attrib) or 'нет'}" if first is not None else ""
    return f"корень <{local(root.tag)}>, элементы: {top}{attrs}"


def dmx_address(text: str) -> str:
    """"200" -> "1.200", as List Fixture shows it. ponytail: absolute address assumed ((universe-1)*512 + channel), seen only in universe 1."""
    if not text.isdigit() or int(text) < 1:
        return text
    n = int(text) - 1
    return f"{n // 512 + 1}.{n % 512 + 1:03d}"


# ponytail: the 3.9 export names no attributes and channel counts do not separate heads from LED bars (hall: Oxygen and Mini-B both 14),
# so heads are guessed from the type name only. The operator corrects it with «Голова» (one fixture or the whole type).
HEAD_TYPE = re.compile(r"(?i)\b(?:moving|mover|beam|sharpy|pointe|oxygen|robin|viper|mac\s?\w+|mh\d*|head)\b")


def guess_head(type_name: str) -> bool:
    return bool(HEAD_TYPE.search(type_name or ""))


def parse_group_export(xml_text: str, listed: dict) -> dict:
    """{group number: [fixture ids]} from an `Export Group` XML. listed: {n: name} from List Group.
    ponytail: the 3.9 group XML is unseen on the desk; members are any `fix_id`/`fixture_id` under <Group>, and the
    pool position `index` is taken as 0-based unless the names say it is the number itself."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"битый XML: {e}") from e
    found = {}
    for elem in root.iter():
        if local(elem.tag) != "Group" or not elem.get("index", "").isdigit():
            continue
        i, name = int(elem.get("index")), elem.get("name")
        n = i if name is not None and listed.get(i) == name and listed.get(i + 1) != name else i + 1
        ids = [int(v) for e in elem.iter() for k in ("fix_id", "fixture_id") if (v := e.get(k, "")).isdigit()]
        found[n] = list(dict.fromkeys(ids))
    if not found:
        raise ValueError(f"в XML не найдено групп ({describe(root)})")
    return found


def parse_export(xml_text: str, skipped: list | None = None) -> list[dict]:
    """Fixtures with a Fixture ID. skipped, if given, gets the names of <Fixture> entries without one (a channel-only
    patch, hall 2026-10-21): the panel commands by `Fixture N`, so it cannot drive them, but it must say so."""
    # ponytail: the real MA2 3.9 fixture XML has not been seen; the layout below is still a guess (see describe() in errors)
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        raise ValueError(f"битый XML: {e}") from e
    found = []
    seen = set()
    for elem in root.iter():
        if local(elem.tag) != "Fixture":  # SubFixture, FixtureType and the like are not fixtures
            continue
        # The id the operator sees (FixId). A bare "index" is the 0-based pool position: using it would shift every id.
        raw_id = next((elem.get(key) for key in ("fixture_id", "id") if elem.get(key, "").isdigit()), None)
        if raw_id is None:
            if skipped is not None:
                skipped.append(elem.get("name") or "?")
            continue
        fid = int(raw_id)
        if fid in seen:
            raise ValueError(f"повтор id {fid}")
        seen.add(fid)
        params = list(dict.fromkeys(e.get("name") for e in elem.iter() if e is not elem
                                    and local(e.tag) in ("Attribute", "Channel", "SubAttribute") and e.get("name")))
        kind = next((e for e in elem.iter() if e is not elem and local(e.tag) == "FixtureType"), None)
        # MA2 3.9.60: <Patch><Address>200</Address></Patch>, the Patch element itself holds only whitespace
        texts = [e.text.strip() for e in elem.iter() if e is not elem and local(e.tag) in ("Address", "Patch") and (e.text or "").strip()]
        channels = sum(1 for e in elem.iter() if local(e.tag) == "Channel")
        entry = {"id": fid, "name": elem.get("name", ""),
                 "type": elem.get("type", elem.get("fixture_type", kind.get("name", "") if kind is not None else "")),
                 "params": params, "address": dmx_address(texts[0]) if texts else None}
        if channels and not params:
            entry["channels"] = channels  # the 3.9 export lists channels by index only, without attribute names
        found.append(entry)
    if not found:
        raise ValueError(f"в XML не найдено приборов с fixture_id ({describe(root)})")
    return found


# MA2 attribute names of the plan's read-back; RGB fixtures in the MA2 library use COLORRGB1-3 for red, green, blue.
TYPE_ATTRS = {"DIM": "dim", "COLORRGB1": "r", "COLORRGB2": "g", "COLORRGB3": "b"}


def parse_fixture_type(xml_text: str) -> dict:
    """{dim, r, g, b}: 1-based DMX channel of each attribute, from an Export FixtureType file (<ChannelType attribute=.. coarse=..>).
    ponytail: first module only; a multi-instance type with patch offsets is read as its first cell."""
    spec, root = {}, ET.fromstring(xml_text)
    has = set()
    module = next((e for e in root.iter() if local(e.tag) == "Module"), root)
    for e in module.iter():
        if local(e.tag) != "ChannelType":
            continue
        attr = e.get("attribute") or ""
        key = TYPE_ATTRS.get(attr.upper())
        if key and key not in spec and (e.get("coarse") or "").isdigit() and 1 <= int(e.get("coarse")) <= 64:
            spec[key] = int(e.get("coarse"))
        for name in ("zoom", "focus"):
            if attr.upper().startswith(name.upper()):
                has.add(name)
        if attr.upper().startswith(("SHUTTER", "STROBE")):
            strobe = {"attr": attr}
            for child in e.iter():
                if local(child.tag) not in ("ChannelFunction", "ChannelSet"):
                    continue
                bounds = {}
                for bound in ("from", "to"):
                    raw = next((child.get(k) for k in (f"{bound}_dmx", f"dmx_{bound}", bound) if child.get(k) is not None), None)
                    try:
                        dmx = float(raw)
                        if 0 <= dmx <= 255:
                            bounds[bound] = round(dmx * 100 / 255, 1)
                    except (TypeError, ValueError):
                        pass
                name = (child.get("name") or "").lower()
                if "strob" in name and "from" in bounds and "to" in bounds:
                    strobe.update(bounds)
                if "open" in name and "from" in bounds:
                    strobe["open"] = bounds["from"]
            if all(k in strobe for k in ("open", "from", "to")):
                spec["strobe"] = strobe
                has.add("strobe")
    spec["has"] = sorted(has)
    return spec


def merge_fixtures(old: list[dict], found: list[dict], *, choices=None) -> list[dict]:
    """Preserve placement; only a one-to-one name/type match can be automatic.

    Ambiguous entries carry candidates until every choice is explicit. JSON keys
    are strings; null means keep this fixture new. Never consume candidates while
    deciding which groups are ambiguous: two new fixtures can share one old one.
    """
    merged = {f["id"]: {**f, "missing": True} for f in old}
    found_ids = {f["id"] for f in found}
    candidates, ambiguous = {}, {}
    for f in found:
        if f["id"] in merged or not f["name"]:
            continue
        gone = [o for o in old if o["id"] not in found_ids
                and o.get("name") == f["name"] and o.get("type") == f["type"]]
        candidates[f["id"]] = gone
        peers = [n for n in found if n["id"] not in merged
                 and n["name"] == f["name"] and n["type"] == f["type"]]
        if gone and (len(gone) != 1 or len(peers) != 1):
            ambiguous[str(f["id"])] = gone
    if choices is not None:
        if not isinstance(choices, dict) or set(choices) != set(ambiguous):
            raise ValueError("нужен явный выбор для каждого неоднозначного прибора")
        used = set()
        for fid, selected in choices.items():
            if selected is None:
                continue
            if type(selected) is not int or selected not in {o["id"] for o in ambiguous[fid]}:
                raise ValueError("выбранный прибор не входит в список кандидатов")
            if selected in used:
                raise ValueError("старый прибор нельзя использовать дважды")
            used.add(selected)
    for f in found:
        fid = f["id"]
        key = str(fid)
        gone = candidates.get(fid, [])
        old_id = (choices[key] if choices is not None else None) if key in ambiguous else (gone[0]["id"] if gone else None)
        if old_id is not None:
            merged[fid] = {**merged.pop(old_id), "id": fid, "repatched_from": old_id}
        entry = merged.get(fid, {"id": fid, "label": f["name"] or f"#{fid}"})
        entry.update(type=f["type"], name=f["name"], params=f.get("params", []), address=f["address"])
        if "channels" in f:
            entry["channels"] = f["channels"]
        entry.pop("missing", None)
        entry.pop("ambiguous_candidates", None)
        if "moves" not in entry and guess_head(f["type"]):
            entry.update(moves=True, moves_auto=True)
        if key in ambiguous and choices is None:
            entry["ambiguous_candidates"] = [{"old_id": o["id"], "label": o.get("label", f"#{o['id']}")} for o in ambiguous[key]]
        merged[fid] = entry
    return [merged[fid] for fid in sorted(merged)]


def save_config(path: str, cfg: dict) -> None:
    folder = os.path.dirname(os.path.abspath(path))
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=folder, suffix=".tmp", delete=False) as f:
        try:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
            f.close()
            os.replace(f.name, path)
        finally:
            if os.path.exists(f.name):
                os.unlink(f.name)
