"""Resolve per-show plans without filename collisions, retaining read-only legacy names."""
import errno
import hashlib
import json
from pathlib import Path


def _owner(path: Path) -> str:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (ValueError, UnicodeError) as e:
        raise ValueError(f"неверный файл плана шоу: {path.name}") from e
    if not isinstance(value, dict) or not isinstance(value.get("show"), str) or not value["show"].strip():
        raise ValueError(f"неверный файл плана шоу: {path.name}")
    return value["show"]


def plan_path(folder: str | Path, name: str, *, write: bool = False) -> Path:
    """Use a bounded ASCII SHA256 name; legacy names are read only and owner-checked.

    A foreign legacy file means this show has no saved plan. A foreign or damaged
    canonical file is an error, so neither reads nor writes silently use it.
    """
    if not isinstance(name, str) or not name.strip():
        raise ValueError("нужно имя шоу для плана")
    folder = Path(folder)
    target = folder / ("plan-" + hashlib.sha256(name.encode("utf-8")).hexdigest() + ".json")
    if target.exists():
        if _owner(target) != name:
            raise ValueError("файл плана принадлежит другому шоу")
        return target
    if not write:
        safe = "".join(c if c.isalpha() or c.isdigit() or c in "-_ " else "_" for c in name)
        legacy = folder / (safe + ".json")
        try:
            exists = legacy.exists()
        except OSError as e:
            # Component limits differ: bytes on POSIX, UTF-16 units on Windows.
            # Only the native filesystem can decide whether this name is too long.
            if e.errno != errno.ENAMETOOLONG and getattr(e, "winerror", None) != 206:
                raise
            exists = False
        if exists and _owner(legacy) == name:
            return legacy
    return target
