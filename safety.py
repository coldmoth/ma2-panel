"""Site settings (settings.json + secret.env) and the last line of defence: what may leave the bridge for MA2.

The guard works on the final text line, whatever code built it. In "test" and "store" modes a line that is not in the
allowlist below is never sent. Nothing here talks to the network.
"""
import ipaddress
import json
import math
import os
import re
from pathlib import Path

MODES = ("test", "store", "full")

DEFAULT_SAFETY = {
    "mode": "test",              # test: live light only | store: + writing into store_execs | full: everything the panel can do
    "allowed_fixtures": [],      # fixture ids the panel may touch in test/store; empty = none
    "allowed_scenes": [],        # executors ("1.101") the panel may Go/Off in test/store; empty = none
    "store_execs": [],           # store mode only: executors the panel may write into
    "allow_master": False,       # Master 2.1 is a real fader on the console: off until checked
    "allow_page_change": False,  # Page N switches the console's executor page for everybody
    "allow_fixture_read": False,
    "allow_highlight": False,
    "allow_show_load": False,
    "allow_show_save": False,
    "allow_group_store": False,
    "allow_patch": False,        # Assign Fixture N At Dmx: changes the show's patch (spec 21)
    "allow_rdm": False,          # RdmList and RdmSetParameter by UID: changes real devices, every show (spec 21)
    "extra_allowed_regex": [],   # whole-line patterns added to the allowlist (e.g. a different attribute name)
}
# ponytail: ListShows formatting must be checked on MA2; both common filename and quoted forms are accepted.
DEFAULT_MA2 = {"listshows_regex": r'(?im)"([^"\r\n]+?)"(?:\.show(?:\.gz)?)?|^\s*(.+?)\.show(?:\.gz)?\s*$|^\s*(.+?)\s+\d{1,2}:\d{2}\s+\d{1,2}\.\S+?\.\d{4}\s+\d+\s*[KMG]?B\s*$',
               "loadshow_cmd": 'LoadShow "{name}" /nosave', "load_timeout": 120, "shows_dir": "",
               "export_cmd": 'Export Fixture 1 Thru 9999 "panel_fixtures"',
               "export_wait": 5, "export_search": ["C:/ProgramData/MA Lighting Technologies/grandma/*/importexport"],
               "showfile_regex": r'(?im)\$?SHOWFILE\s*[=:]\s*"?([^"\r\n]+?)"?\s*$',
               "host": "127.0.0.1", "port": 30000, "user": "Remote", "require_prompt": True}
# MA2 3.9.60.68 (hall 2026-10-18): "Group 1 1    HEAD STAGE", "Color 4.1 4.1  red      Normal" (columns 2+ spaces apart),
# empty: "WARNING, NO OBJECTS FOUND FOR LIST". The older quoted form Group n "Name" / Preset t.n "Name" still parses.
DEFAULT_MA2.update({
    "list_group_cmd": "List Group 1 Thru 999",
    "list_preset_cmd": "List Preset {type}.1 Thru {type}.999",
    "preset_types": {"color": 4, "position": 2},
    "group_regex": r'(?im)^[ \t]*Group[ \t]+(?P<n>\d+)[ \t]+(?:"(?P<name>[^"\r\n]+)"|\d+[ \t]+(?P<name2>\S(?:[^\r\n]*?\S)??)(?:[ \t]{2,}[^\r\n]*)?)[ \t]*$',
    "preset_regex": r'(?im)^[ \t]*(?:Preset|[A-Za-z]+)[ \t]+(?P<type>\d+)\.(?P<n>\d+)[ \t]+(?:"(?P<name>[^"\r\n]+)"|\d+\.\d+[ \t]+(?P<name2>\S(?:[^\r\n]*?\S)??)(?:[ \t]{2,}[^\r\n]*)?)[ \t]*$',
    "group_empty_regex": r'(?i)(?:warning,?\s*)?no objects? found(?: for list)?|nothing found',
    "group_go_cmd": "Group {n}",
    "preset_go_cmd": "At Preset {type}.{n}",
    "group_store_cmd": 'Store Group {n} "{name}"',
    # List Group gives no members; the group export does (one-off name like the fixture export).
    "group_export_cmd": 'Export Group 1 Thru 999 "panel_groups"',
})

NUM = r"\d+(?:\.\d+)?"
FADE = rf"(?: Fade {NUM})?"
LIVE = [
    r"Fixture \d+(?: \+ \d+)*",
    rf"At {NUM}{FADE}",
    rf'Attribute "(?:ColorRGB[123]|Pan|Tilt|Zoom|Focus|Strobe)" At -?{NUM}{FADE}',
]
READ = [r"ListVar", r"ListShows", r"List Executor \d+\.\d+(?: Thru \d+\.\d+)?", r"List (?:Group|Sequence|Page|Layout|Macro|User|Fixture|FixtureType|Attribute)"]
READ += [r"List Group \d+(?: Thru \d+)?", r"List Preset \d+\.\d+(?: Thru \d+\.\d+)?"]
SCENE = r"(Go|Off) Executor (\d+\.\d+)"
SCENE_FADE = rf"Goto Cue 1 Executor (\d+\.\d+) Fade {NUM}"


def load_secret(folder: Path) -> str:
    """Password from the MA2_PASSWORD variable or secret.env (one line MA2_PASSWORD=...). Never goes into settings or logs."""
    if os.environ.get("MA2_PASSWORD") is not None:
        return os.environ["MA2_PASSWORD"]
    path = folder / "secret.env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            key, _, value = line.partition("=")
            if key.strip() == "MA2_PASSWORD":
                return value.strip().strip('"')
    return ""


def load_settings(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"Битый JSON в {path}: {e}")
    if "password" in json.dumps(data.get("ma2", {})).lower():
        raise SystemExit(f"Пароль нельзя хранить в {path}: положите его в secret.env (MA2_PASSWORD=...)")
    return data


def effective_safety(settings: dict) -> dict:
    safety = {**DEFAULT_SAFETY, **settings.get("safety", {})}
    if safety["mode"] not in MODES:
        raise SystemExit(f"safety.mode должен быть один из {MODES}, а не {safety['mode']!r}")
    safety["allowed_fixtures"] = [int(i) for i in safety["allowed_fixtures"]]
    return safety


LOGIN_ECHO = re.compile(r'(?i)(\blogin\s+"[^"\r\n]*"\s+)"[^"\r\n]*"')
ENV_SECRET = re.compile(r"(?im)^(\s*MA2_PASSWORD\s*=).*$")
MIN_LITERAL_SECRET = 6


def redact(text: str, secrets=()) -> str:
    """Hide the password in diagnostics without eating ordinary text.

    Login echoes and MA2_PASSWORD= lines are hidden by shape. A literal search for the password is only safe for a
    long one: a one-character password like "1" would otherwise blank every 1 in addresses, dates and fixture ids.
    """
    for secret in sorted(secrets, key=len, reverse=True):
        if len(secret) >= MIN_LITERAL_SECRET:
            text = text.replace(secret, "***")
    return ENV_SECRET.sub(r"\1***", LOGIN_ECHO.sub(r'\1"***"', text))


def make_guard(safety: dict, attr_names=None, export_cmd=None, export_extra=()):
    """guard(line) -> None when the line may be sent, else the reason it is blocked.

    attr_names: a set the bridge may grow later with names read from fixture type exports (checked at call time).
    export_extra: a set the bridge fills with the exact export lines of one diagnostics run (checked at call time)."""
    names = attr_names if attr_names is not None else ["ColorRGB1", "ColorRGB2", "ColorRGB3", "Pan", "Tilt", "Zoom", "Focus", "Strobe"]
    if any(not isinstance(n, str) or not re.fullmatch(r"[A-Za-z0-9_]+", n) for n in names):
        raise SystemExit("имя атрибута должно содержать только A-Z, a-z, 0-9 и _")
    attribute = re.compile(rf'Attribute "([A-Za-z0-9_]+)" At (?:-?{NUM}|[+-] {NUM}){FADE}')
    execs = {str(e) for e in safety["allowed_scenes"]}
    stores = {str(e) for e in safety["store_execs"]} if safety["mode"] == "store" else set()
    fixtures = set(safety["allowed_fixtures"])
    patterns = [re.compile(p) for p in LIVE[:2] + READ +
                [r"Group \d+", r"At Preset \d+\.\d+", r"ClearAll"] + safety["extra_allowed_regex"]]  # ClearAll: programmer only, before a scene
    master = re.compile(rf"Master \d+\.\d+ At {NUM}") if safety["allow_master"] else None
    page = re.compile(r"Page \d+") if safety["allow_page_change"] else None
    store = [re.compile(rf"StoreLook Executor ({re.escape(e)}) Cue 1 /Source=Output"
                        rf"|Label Executor ({re.escape(e)}) \"[^\"\r\n]*\"") for e in stores]

    def guard(line: str):
        if re.search(r"/Overwrite\b", line, re.I):
            return "перезапись запрещена"
        if not line or line != line.strip() or "\n" in line or "\r" in line:
            return "пустая или многострочная команда"
        # Check privileged families before full mode or extra_allowed_regex can allow them.
        low = line.lower()
        if re.match(r"store\s+group\b", low):
            valid = re.fullmatch(r'Store Group [1-9]\d* "[^";\x00-\x1f\x7f-\x9f]+"', line)
            return None if safety.get("allow_group_store") is True and valid else "запись группы заблокирована: allow_group_store и безопасная команда Store Group"
        if low.startswith("export"):
            return None if safety.get("allow_fixture_read") is True and (line == export_cmd or line in export_extra) else "экспорт заблокирован: allow_fixture_read и ma2.export_cmd"
        if low.startswith("lua"):  # only the bridge's own read lines (DMX read-back), never a free Lua line
            return None if safety.get("allow_fixture_read") is True and line in export_extra else "Lua заблокирован: только чтение DMX мостом при allow_fixture_read"
        if re.match(r"assign\b", low):  # patch: only the bridge's line for one confirmed plan, never in a free form
            valid = re.fullmatch(r"Assign Fixture \d+ At Dmx \d+\.\d{3}", line) and line in export_extra
            return None if safety.get("allow_patch") is True and valid else "патч заблокирован: allow_patch и подтверждённый план"
        if low.startswith("rdm"):  # RdmList reads; RdmSetParameter only for a confirmed plan; Autopatch and the rest never
            if safety.get("allow_rdm") is not True:
                return "RDM заблокирован: allow_rdm"
            if re.fullmatch(r"RdmList(?: / UID = [0-9A-F]{12})?", line):
                return None
            valid = re.fullmatch(r"RdmSetParameter (?:dmx_start_address \d{1,3}|identify_device [01]) / UID = [0-9A-F]{12}", line)
            return None if valid and line in export_extra else "RDM: только RdmList и RdmSetParameter подтверждённого плана"
        if re.match(r"off\s+fixture\b", low):
            m = re.fullmatch(r"Off Fixture (\d+(?: \+ \d+)*)", line)
            if safety.get("allow_highlight") is not True or not m:
                return "подсветка заблокирована: allow_highlight"
            if safety["mode"] != "full" and any(int(i) not in fixtures for i in m[1].split(" + ")):
                return "прибор не разрешён (allowed_fixtures)"
            return None
        if low.startswith("loadshow"):
            valid = re.fullmatch(r'LoadShow "[^"\x00-\x1f\x7f-\x9f]+"(?: /nosave)?', line)
            return None if safety.get("allow_show_load") is True and valid else "загрузка шоу заблокирована: allow_show_load"
        if low.startswith("saveshow"):
            return None if safety.get("allow_show_save") is True and line == "SaveShow" else "сохранение шоу заблокировано: allow_show_save"
        if re.match(r"delete\s+executor\b", low):  # scene_delete with desk: only one executor, only where storing is allowed
            m = re.fullmatch(r"Delete Executor (\d+\.\d+)", line)
            return None if m and (safety["mode"] == "full" or m[1] in stores) else "удаление сцены на пульте: только режим full или store_execs"
        if safety["mode"] == "full":
            return None
        m = re.fullmatch(r"Fixture (\d+(?: \+ \d+)*)", line)
        if m:
            bad = [i for i in map(int, m[1].split(" + ")) if i not in fixtures]
            return f"прибор {bad[0]} не разрешён (allowed_fixtures)" if bad else None
        m = re.fullmatch(SCENE_FADE, line)
        if m:
            return None if m[1] in execs else f"сцена {m[1]} не разрешена (allowed_scenes)"
        m = re.fullmatch(SCENE, line)
        if m:
            return None if m[2] in execs else f"сцена {m[2]} не разрешена (allowed_scenes)"
        if any(p.fullmatch(line) for p in patterns):
            return None
        m = attribute.fullmatch(line)
        if m and m[1] in names:
            return None
        if master and master.fullmatch(line) or page and page.fullmatch(line):
            return None
        if any(p.fullmatch(line) for p in store):
            return None
        return f"команда не в списке разрешённых режима {safety['mode']}"

    return guard


def without_passwords(value):
    if isinstance(value, dict):
        return {k: without_passwords(v) for k, v in value.items() if "password" not in k.lower()}
    if isinstance(value, list):
        return [without_passwords(v) for v in value]
    return value


def validate_settings(value):
    """Validate the entire replacement before touching disk or the running link."""
    if not isinstance(value, dict):
        raise ValueError("settings должен быть объектом")
    if without_passwords(value) != value:
        raise ValueError("Пароль нельзя хранить в настройках: используйте отдельное поле пароля")
    for key in ("ma2", "safety", "attrs", "features"):
        if key in value and not isinstance(value[key], dict):
            raise ValueError(f"{key} должен быть объектом")
    effective_safety(value)  # SystemExit is translated by the endpoint
    for key in ("allow_fixture_read", "allow_highlight", "allow_show_load", "allow_show_save", "allow_group_store", "allow_patch", "allow_rdm"):
        if key in value.get("safety", {}) and type(value["safety"][key]) is not bool:
            raise ValueError(f"safety.{key}: требуется bool")
    ma2 = value.get("ma2", {})
    for label, obj in (("port", value), ("ma2.port", ma2)):
        if "port" in obj and (type(obj["port"]) is not int or not 1 <= obj["port"] <= 65535):
            raise ValueError(f"{label}: требуется целое число от 1 до 65535")
    simple_port = value.get("simple_port", 8090)
    if simple_port is not None:
        if type(simple_port) is not int or not 1 <= simple_port <= 65535:
            raise ValueError("simple_port: требуется целое число от 1 до 65535 или null")
        if simple_port == value.get("port", 8080):
            raise ValueError("simple_port должен отличаться от port")
    if "bind" in value:
        try:
            if not isinstance(value["bind"], str):
                raise ValueError("bind")
            ipaddress.IPv4Address(value["bind"])
        except (ValueError, TypeError):
            raise ValueError("bind: требуется IPv4-адрес, например 127.0.0.1 или 0.0.0.0") from None
    for key, obj, low, high in (("rate_hz", value, 1, 10), ("poll_seconds", value, 0, math.inf), ("dmx_seconds", value, 0, math.inf),
                                 ("timeout", ma2, 0.001, math.inf), ("load_timeout", ma2, 0.001, math.inf)):
        if key in obj and (type(obj[key]) not in (int, float) or not math.isfinite(obj[key]) or not low <= obj[key] <= high):
            raise ValueError(f"{key}: требуется число от {low} до {high}")
    for key, pattern in ma2.items():
        if key.endswith("_regex"):
            try:
                compiled = re.compile(pattern)
                if key in ("group_regex", "preset_regex") and not {"n", "name"} <= compiled.groupindex.keys():
                    raise ValueError(f"ma2.{key}: нужны именованные группы n и name")
                # An empty-slot pattern that also fits an occupied row would let Store Group overwrite it.
                if key == "group_empty_regex" and any(compiled.fullmatch(t) for t in ("", 'Group 1 "Front"', "1 Front")):
                    raise ValueError(f"ma2.{key}: шаблон пустого ответа подходит и к занятой группе")
            except (re.error, TypeError):
                raise ValueError(f"ma2.{key}: неверное регулярное выражение") from None
    for name, attr in value.get("attrs", {}).items():
        if not isinstance(attr, dict):
            raise ValueError(f"attrs.{name} должен быть объектом")
        for key in ("cmd", "rel_cmd"):
            if key in attr and (not isinstance(attr[key], str) or "{v}" not in attr[key]
                                or not re.search(r'Attribute "[A-Za-z0-9_]+"', attr[key])):
                raise ValueError(f'attrs.{name}.{key}: требуется Attribute "Имя" и {{v}}; имя содержит только A-Z, a-z, 0-9, _')
    if any(type(v) not in (bool, str) for v in value.get("features", {}).values()):
        raise ValueError("Функции: требуется флажок или строка с причиной блокировки")
