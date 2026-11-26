"""Resolve per-show plans without filename collisions, retaining read-only legacy names."""
import errno
import hashlib
import json
from pathlib import Path

from .commands import ActionError, patch_rows, validate_hall


def read_plan(path: Path):
    """Read the revision and owner from the same file contents."""
    try:
        text = path.read_text(encoding="utf-8-sig")
        value = json.loads(text)
    except FileNotFoundError:
        return None, None
    except ValueError as e:
        raise ValueError(f"неверный файл плана шоу: {path.name}") from e
    if not isinstance(value, dict) or not isinstance(value.get("show"), str) or not value["show"].strip():
        raise ValueError(f"неверный файл плана шоу: {path.name}")
    return text, value


def _plan_paths(folder, name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("нужно имя шоу для плана")
    folder = Path(folder)
    target = folder / ("plan-" + hashlib.sha256(name.encode("utf-8")).hexdigest() + ".json")
    safe = "".join(c if c.isalpha() or c.isdigit() or c in "-_ " else "_" for c in name)
    return target, folder / (safe + ".json")


def _read_legacy(path):
    try:
        return read_plan(path)
    except OSError as e:
        # Component limits differ: bytes on POSIX, UTF-16 units on Windows.
        if e.errno != errno.ENAMETOOLONG and getattr(e, "winerror", None) != 206:
            raise
        return None, None


def plan_path(folder: str | Path, name: str, *, write: bool = False) -> Path:
    """Prefer the canonical name, with a read-only owner-checked legacy fallback."""
    target, legacy = _plan_paths(folder, name)
    _, value = read_plan(target)
    if value is not None and value["show"] != name:
        raise ValueError(f"файл плана принадлежит другому шоу: {target.name}")
    if value is None and not write:
        _, value = _read_legacy(legacy)
        if value is not None and value["show"] == name:
            return legacy
    return target


def auto_plan(folder: str | Path, name: str):
    """Resolve an existing plan with a revision, refusing conflicting same-owner copies."""
    target, legacy = _plan_paths(folder, name)
    text, value = read_plan(target)
    if value is not None and value["show"] != name:
        raise ValueError(f"файл плана принадлежит другому шоу: {target.name}")
    legacy_text, legacy_value = _read_legacy(legacy)
    if legacy_value is not None and legacy_value["show"] == name:
        if value is None:
            return legacy, legacy_text, legacy_value
        if value != legacy_value:
            raise ValueError(f"расходятся копии плана: {target.name} и {legacy.name}")
    return target, text, value


def validate_auto_plan(data, prepared):
    def require(valid, field):
        if not valid:
            raise ActionError(f"неверные данные плана: {field}")

    def rows(key, identity, valid_id):
        items = data.get(key)
        require(isinstance(items, list) and all(isinstance(row, dict) for row in items), key)
        ids = [row.get(identity) for row in items]
        require(all(valid_id(i) for i in ids) and len(ids) == len(set(ids)), key)
        return items

    def positive(i):
        return type(i) is int and i > 0

    def named(i):
        return isinstance(i, str) and bool(i.strip())

    def string_fields(row, fields):
        return all(isinstance(row[key], str) for key in fields if row.get(key) is not None)

    fixtures = rows("fixtures", "id", positive)
    for fixture in fixtures:
        require(string_fields(fixture, ("label", "name", "type", "address")), "fixtures")
        require(isinstance(fixture.get("beam", {}), dict), "fixtures.beam")
        require(fixture.get("rdm") is None or isinstance(fixture["rdm"], dict), "fixtures.rdm")
        require(fixture.get("physical_pos") is None or isinstance(fixture["physical_pos"], dict), "fixtures.physical_pos")
    for group in rows("groups", "id", named):
        members = group.get("fixtures")
        require(isinstance(members, list) and all(positive(i) for i in members), "groups.fixtures")
        require(string_fields(group, ("label",)), "groups.label")
    for scene in rows("scenes", "id", named):
        require(string_fields(scene, ("label",)), "scenes.label")
    for preset in rows("presets", "id", named):
        require(isinstance(preset.get("pos"), dict), "presets.pos")
    for key in ("plan", "pages", "dmx_map", "dmx_map_saved", "ma2presets", "attrs"):
        require(isinstance(data.get(key, {}), dict), key)
    for key in ("dmx_map", "attrs"):
        require(all(isinstance(v, dict) for v in data.get(key, {}).values()), key)
    require(isinstance(data.get("ma2groups", []), list)
            and all(isinstance(g, dict) for g in data.get("ma2groups", [])), "ma2groups")
    for value in data.get("dmx_map", {}).values():
        strobe = value.get("strobe", {})
        require(isinstance(strobe, dict) and isinstance(strobe.get("attr", ""), str), "dmx_map.strobe")
    for versions in data.get("dmx_map_saved", {}).values():
        require(isinstance(versions, dict) or isinstance(versions, list)
                and all(isinstance(v, dict) for v in versions), "dmx_map_saved")
    color_names = prepared["attrs"].get("color", {}).get("names", [])
    require(isinstance(color_names, list) and all(isinstance(n, str) for n in color_names), "attrs.color.names")
    for key in ("colors", "positions"):
        items = data.get("ma2presets", {}).get(key, [])
        require(isinstance(items, list) and all(isinstance(p, dict) for p in items), f"ma2presets.{key}")
    if data.get("hall") is not None:
        validate_hall(data["hall"])
    if data.get("ma2_layout") is not None:
        require(isinstance(data["ma2_layout"], dict), "ma2_layout")
    # Exercise the bridge's real derived data before either file is replaced.
    patch_rows(fixtures)
    for spec in prepared["attrs"].values():
        require(all(isinstance(spec.get(key, ""), str) for key in ("cmd", "rel_cmd")), "attrs")
    json.dumps(data, allow_nan=False)
