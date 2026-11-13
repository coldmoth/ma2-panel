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
            if any(elem.get(key) for key in ("fixture_id", "id")):
                raise ValueError("неверный Fixture ID: импорт неполон")
            if skipped is not None:
                skipped.append(elem.get("name") or "?")
            continue
        fid = int(raw_id)
        if not 1 <= fid <= 9999:
            raise ValueError("Fixture ID вне поддерживаемого диапазона 1–9999")
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
        if len(texts) > 1 or sum(local(e.tag) == "SubFixture" for e in elem.iter()) > 1:
            entry["patch_unsupported"] = True
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
    Only a single unshifted module instance is supported."""
    spec, root = {}, ET.fromstring(xml_text)
    has = set()
    axes = set()
    instances = [e for e in root.iter() if local(e.tag) == "Instance"]
    if (sum(local(e.tag) == "Module" for e in root.iter()) > 1
            or len(instances) > 1
            or any(e.get("module_index") != "0" or e.get("patch") != "1" for e in instances)
            or any(local(e.tag) == "Instances" and not instances for e in root.iter())):
        return {"unsupported": True, "has": []}
    module = next((e for e in root.iter() if local(e.tag) == "Module"), root)
    for e in module.iter():
        if local(e.tag) != "ChannelType":
            continue
        attr = e.get("attribute") or ""
        if attr.upper().startswith("SHUTTER"):
            coarse = e.get("coarse", "")
            if coarse.isdigit() and 1 <= int(coarse) <= 64 and not e.get("fine"):
                spec["shutter"] = int(coarse)
                for child in e.iter():
                    name = (child.get("name") or "").strip().lower()
                    key = "shutter_open" if name in ("open", "shutter open") else "shutter_closed" if name in ("closed", "shutter closed") else None
                    lo, hi = child.get("from_dmx", ""), child.get("to_dmx", "")
                    if key and lo.isdigit() and hi.isdigit() and 0 <= int(lo) <= int(hi) <= 255:
                        spec.setdefault(key, []).append([int(lo), int(hi)])
            else:
                spec["unsupported"] = True
        if attr.upper() in ("PAN", "TILT"):
            axes.add(attr.upper())
        key = TYPE_ATTRS.get(attr.upper())
        # A wheel, CMY, white/amber emitter, etc. needs its own colour model.
        # A dimmer byte alone cannot prove white output for such a profile.
        if attr.upper().startswith("COLOR") and key not in ("r", "g", "b"):
            spec["unsupported"] = True
        if key and key not in spec and (e.get("coarse") or "").isdigit() and 1 <= int(e.get("coarse")) <= 64:
            spec[key] = int(e.get("coarse"))
        elif key:
            spec["unsupported"] = True
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
    if axes == {"PAN", "TILT"}:
        has.add("pos")
    spec["has"] = sorted(has)
    return spec


def merge_fixtures(old: list[dict], found: list[dict], *, choices=None) -> list[dict]:
    """Preserve placement; only a one-to-one name/type match can be automatic.

    Ambiguous entries carry candidates until every choice is explicit. JSON keys
    are strings; null means keep this fixture new. Never consume candidates while
    deciding which groups are ambiguous: two new fixtures can share one old one.
    """
    merged = {f["id"]: {**f, "missing": True} for f in old}
    old_by_id = {f["id"]: f for f in old}
    # Reserve unchanged identities first. An ID reused by another fixture is
    # available as a transfer source even though that number is still present.
    def unchanged(f):
        previous = old_by_id.get(f['id'])
        identity = (f.get('name'), f.get('type'))
        if not previous or not all(identity) or identity != (previous.get('name'), previous.get('type')):
            return False
        peers = [n for n in found if n['id'] != f['id'] and (n.get('name'), n.get('type')) == identity]
        # A new row with the same generic name/type may be the old fixture at
        # another ID. Reserve this number only with unique unchanged patch data.
        return not peers or (previous.get('address') and f.get('address') == previous['address']
                             and all(n.get('address') and n['address'] != previous['address'] for n in peers))
    stable = {f['id'] for f in found if unchanged(f)}
    candidates, ambiguous = {}, {}
    for f in found:
        fid = f['id']
        if fid in stable:
            continue
        peers = [o for o in old if o['id'] not in stable and f.get('name') and f.get('type')
                 and (o.get('name'), o.get('type')) == (f['name'], f['type'])]
        previous = old_by_id.get(fid)
        candidates[fid] = ([previous] if previous is not None else []) + [o for o in peers if o['id'] != fid]
    claims = {}
    for options in candidates.values():
        for previous in options:
            claims[previous['id']] = claims.get(previous['id'], 0) + 1
    for fid, options in candidates.items():
        if fid in old_by_id or len(options) > 1 or any(claims[o['id']] > 1 for o in options):
            ambiguous[str(fid)] = options
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
    resolved, consumed = {}, set()
    for f in found:
        fid = f["id"]
        key = str(fid)
        gone = candidates.get(fid, [])
        old_id = (choices[key] if choices is not None else None) if key in ambiguous else (gone[0]["id"] if gone else None)
        if old_id is not None:
            if old_id in consumed:
                raise ValueError("старый прибор нельзя использовать дважды")
            entry = {**old_by_id[old_id], "id": fid}
            if old_id != fid:
                entry["repatched_from"] = old_id
            consumed.add(old_id)
        elif key not in ambiguous and fid in old_by_id:
            if fid in consumed:
                raise ValueError("старый прибор нельзя использовать дважды")
            entry = dict(old_by_id[fid])
            consumed.add(fid)
        else:
            entry = {"id": fid, "label": f["name"] or f"#{fid}"}
            if fid in old_by_id:
                entry["identity_reset"] = True
        if any(entry.get(k) != f.get(k) for k in ("address", "type")) or old_id is not None:
            if entry.get("rdm"):
                entry["rdm"] = {k: v for k, v in entry["rdm"].items() if k != "address"}
                entry["rdm"]["stale"] = True
        entry.pop("footprint", None)  # export Channel count is not current profile evidence
        entry.pop("channels", None)
        entry.pop("patch_unsupported", None)
        if f.get("patch_unsupported"):
            entry["patch_unsupported"] = True
        entry.update(type=f["type"], name=f["name"], params=f.get("params", []), address=f["address"])
        if "channels" in f:
            entry["channels"] = f["channels"]
        entry.pop("missing", None)
        entry.pop("ambiguous_candidates", None)
        if "moves" not in entry and guess_head(f["type"]):
            entry.update(moves=True, moves_auto=True)
        if key in ambiguous and choices is None:
            entry["ambiguous_candidates"] = [{"old_id": o["id"], "label": o.get("label", f"#{o['id']}")} for o in ambiguous[key]]
        resolved[fid] = entry
    merged = {fid: f for fid, f in merged.items() if fid not in consumed}
    merged.update(resolved)
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
