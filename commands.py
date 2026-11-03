"""Panel action -> MA2 command lines. No network."""
import json
import math
import re

SIMPLE = {"scene_go", "scene_off", "blackout", "master", "page_go", "halt", "resume"}
FULL = {"select_group", "select_fixtures", "dim", "color", "clear", "store_scene", "layout_save", "fixtures_fetch", "show_identify", "show_bind", "show_open_plan", "shows_list", "show_load", "show_save",
        "nudge", "jog", "aim", "move_start", "move", "zoom", "focus", "strobe", "preset_save", "preset_go", "preset_delete",
        "group_save", "group_delete", "beam_home", "beam_invert", "scene_create", "scenes_import", "page_save",
        "scene_rename", "scene_delete", "hall_save", "fixture_flag", "ma2_read", "ma2_import",
        "ma2_group_go", "ma2_preset_go", "group_store_ma2", "plan_copy", "dmx_map", "undo",
        "scene_slot_find", "scene_slot_cancel", "rdm_list", "rdm_link", "rdm_identify", "patch_plan", "patch_apply", "import_confirm_merge",
        "rdm_prepare", "rdm_start", "rdm_stop", "rdm_check"}
SLIDERS = {"master", "dim", "color", "move", "jog", "zoom", "focus", "strobe"}
# Lines built from the plan's fixture and executor numbers: refused while the desk has another show open.
# Blackout, Master, page change and Stop stay available.
PLAN_WRITES = (SLIDERS - {"master"}) | {"select_group", "select_fixtures", "store_scene", "nudge", "aim", "move_start", "preset_go",
                                        "scene_go", "scene_off", "scene_create", "scene_rename", "page_save",
                                        "ma2_group_go", "ma2_preset_go", "group_store_ma2"}


class ActionError(Exception):
    pass


def nudge_step(action, cfg):
    attr = action.get("attr")
    if attr not in ("pan", "tilt"):
        raise ActionError("шаг: нужен attr pan/tilt")
    step = action.get("step", cfg["attrs"][attr].get("step", 2))
    if isinstance(step, bool) or not isinstance(step, (int, float)) or not math.isfinite(step) or not 0 < step <= 10:
        raise ActionError(f"шаг {attr} должен быть от 0 до 10 градусов (attrs.{attr}.step)")
    return step


def _value(action, key):
    v = action.get(key)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100:
        raise ActionError(f"{key}: нужно число 0-100")
    return f"{round(v, 1):g}"


def fade_suffix(action, cfg):
    """Programmer fade for dim and colour; "" when absent or 0. `At 50 Fade 2`: MA2 3.9 manual p. 466; fade_fmt in config.json."""
    s = action.get("fade", 0)
    if isinstance(s, bool) or not isinstance(s, (int, float)) or not 0 <= s <= 30:
        raise ActionError("fade: нужно число 0-30")
    return cfg.get("fade_fmt", " Fade {s}").format(s=f"{s:g}") if s else ""


def find(items, id_):
    for item in items:
        if item["id"] == id_:
            return item
    raise ActionError(f"неизвестный id: {id_!r}")


def page_number(action: dict, key: str = "n") -> int:
    n = action.get(key)
    if type(n) is not int or not 1 <= n <= 999:
        raise ActionError("страница: нужно число 1-999")
    return n


def exec_page(ex: str) -> int:
    return int(str(ex).split(".")[0])


def store_lines(ex: str, label: str) -> list[str]:
    """No SaveShow: saving the whole show is the operator's decision, never the panel's."""
    return [f"StoreLook Executor {ex} Cue 1 /Source=Output", f'Label Executor {ex} "{label}"']


ECHO = re.compile(r"(?i)\s*executing\s*:")  # MA2 3.9.60 starts every reply with "Executing : <the command>"


def _reply_lines(reply: str):
    """Ignore standalone prompts and List command echoes (possibly prefixed by a prompt)."""
    for line in reply.splitlines():
        line = re.sub(r"^(?:\s*\[[^\]]*\]>\s*)+", "", line).strip()
        if line and not ECHO.match(line) and not re.fullmatch(r"List Executor \d+\.\d+(?: Thru \d+\.\d+)?", line, re.I):
            yield line


def exec_verdict(reply: str, ex: str, empty_re: re.Pattern) -> tuple[str, str]:
    if any(e == ex for e, _ in parse_executors(reply)) or any(
        re.search(rf"(?<![\w.]){re.escape(ex)}(?![\w.])", line) for line in _reply_lines(reply)
    ):
        return "occupied", f"executor {ex} уже занят: перезапись запрещена"
    if empty_re.search(reply):
        return "empty", "пустое место подтверждено пультом"
    return "unknown", (f"ответ пульта на List Executor {ex} не распознан: место не считается свободным. "
                       "Сырой ответ — в Диагностике; если пульт так сообщает о пустом месте, "
                       "впишите шаблон в ma2.exec_empty_regex")


def unrecognised_lines(reply: str) -> int:
    return sum(not parse_executors(line) for line in _reply_lines(reply))


# An executor row: an optional leading word ("Executor", or "Exec" as the desk's other List replies use a short one),
# an optional pool number, the page.number, the same page.number once more if repeated, then the name.
# ponytail: real List Executor rows were never captured; widen here when the hall shows them.
EXEC_ROW = re.compile(r"\s*(?:[A-Za-z]+\s+)?(?:\d+\s+)?(\d+\.\d+)\s+(?:\1\s+)?(.+?)\s*$")


def parse_executors(reply: str) -> list[tuple[str, str]]:
    """(exec, label) from a `List Executor` reply. ponytail: reply format guessed, check in the hall."""
    found = []
    for line in reply.splitlines():
        m = EXEC_ROW.match(line)
        label = re.split(r"\s{2,}", m[2])[0].replace('"', "").strip() if m else ""
        if label:
            found.append((m[1], label))
    return found


def can_move(fixture: dict) -> bool:
    """Heads: the old moves flag, or Pan/Tilt among the parameters read from the MA2 export."""
    return fixture.get("moves") is True or any(re.search(r"pan|tilt", str(p), re.I) for p in fixture.get("params") or [])


def parse_ma2_objects(reply: str, pattern: str, preset_type: int | None = None) -> list[dict]:
    """Catalogue rows from the site's assumed List format; never infer fixture membership."""
    found = {}
    for match in re.finditer(pattern, reply):
        row = match.groupdict()
        if preset_type is not None and row.get("type") and int(row["type"]) != preset_type:
            continue
        n, name = int(row["n"]), (row["name"] or row.get("name2") or "").strip()
        if 1 <= n <= 999 and name:
            entry = {"n": n, "name": name}
            if row.get("ids") and re.fullmatch(r"\d+(?:[ ,+]+\d+)*", row["ids"]):
                entry["ids"] = list(dict.fromkeys(map(int, re.findall(r"\d+", row["ids"]))))
            found[n] = entry
    return list(found.values())


def group_slot_empty(reply: str, n: int, pattern: str, empty_pattern: str) -> bool:
    """Only an explicit empty response is safe; echoes/prompts alone prove nothing."""
    if is_error_reply(reply) or any(row["n"] == n for row in parse_ma2_objects(reply, pattern)):
        return False
    lines = []
    for line in reply.splitlines():
        line = re.sub(r"^(?:\s*\[[^\]]*\]>\s*)+", "", line).strip()
        if line and not ECHO.match(line) and line.lower() != f"List Group {n}".lower():
            if re.search(rf"(?i)\bgroup\b\D*\b{n}\b", line):  # any row naming this group: occupied, whatever the regexes say
                return False
            lines.append(line)
    return bool(lines) and all(re.fullmatch(empty_pattern, line) for line in lines)


def parse_running(reply: str) -> dict[str, bool]:
    """exec -> running, only for lines that carry a status word. ponytail: status word guessed, check in the hall."""
    state = {}
    for line in reply.splitlines():
        m = EXEC_ROW.match(line)
        cols = re.split(r"\s{2,}", m[2])[1:] if m else []
        words = {w.lower() for col in cols for w in col.split()}
        if words & {"running", "on", "active"}:
            state[m[1]] = True
        elif words & {"off", "stopped"}:
            state[m[1]] = False
    return state


def movers(ids: list[int], cfg: dict) -> list[int]:
    moving = {f["id"] for f in cfg["fixtures"] if can_move(f)}
    return [id_ for id_ in ids if id_ in moving]


def scale(attr: str, v: float, cfg: dict) -> str:
    spec = cfg["attrs"][attr]
    x = round(spec["min"] + v / 100 * (spec["max"] - spec["min"]), 1)
    return f"{x:g}" if x else "0"


def attr_lines(values: dict[str, float], cfg: dict) -> list[str]:
    return [cfg["attrs"][attr]["cmd"].format(v=scale(attr, values[attr], cfg))
            for attr in ("pan", "tilt", "zoom", "focus", "strobe") if attr in values]


def head_lines(values: dict[int, dict[str, float]], cfg: dict) -> list[str]:
    """Pan/Tilt/... lines, each group of attribute lines behind its own explicit `Fixture` line."""
    if not values:
        return []
    first = next(iter(values.values()))
    if all(value == first for value in values.values()):
        return [select_line(list(values))] + attr_lines(first, cfg)
    # ponytail: по строке выбора на голову; заменить на одну команду, если в зале найдётся синтаксис
    lines = []
    for id_, value in values.items():
        lines.append(select_line([id_]))
        lines.extend(attr_lines(value, cfg))
    return lines


def select_line(ids: list[int]) -> str:
    return "Fixture " + " + ".join(map(str, ids))


def apply_move(base: dict[int, dict[str, float]], dx: float, dy: float) -> dict[int, dict[str, float]]:
    return {id_: {"pan": round(min(100, max(0, value["pan"] + dx)), 1),
                  "tilt": round(min(100, max(0, value["tilt"] + dy)), 1)}
            for id_, value in base.items()}


def check_move(action: dict) -> tuple[float, float]:
    values = (action.get("dx"), action.get("dy"))
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not -100 <= v <= 100
           for v in values):
        raise ActionError("dx, dy: нужны числа -100…100")
    return tuple(float(v) for v in values)


def check_jog(action: dict) -> tuple[float, float]:
    """Joystick step in degrees since the last one: relative, so the desk and the panel can turn the same head."""
    values = (action.get("pan"), action.get("tilt"))
    if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not -45 <= v <= 45 for v in values):
        raise ActionError("jog: pan, tilt — числа -45…45 градусов")
    if type(action.get("mirror", False)) is not bool:
        raise ActionError("mirror: true или false")
    return tuple(round(float(v), 2) for v in values)


def mirrored(ids: list[int], cfg: dict) -> set[int]:
    """Mirror mode: the left half of the heads on the plan (by x; unplaced ones by number) turns Pan the other way, so the
    beams close in and open out instead of moving in parallel. With an odd count the middle head moves as usual."""
    place = sorted(ids, key=lambda i: (find(cfg["fixtures"], i).get("x", 0.5), i))
    return set(place[:len(place) // 2])


def pan_flip(fixture: dict, mirror: set[int]) -> bool:
    return (fixture.get("flip_pan") is True) != (fixture["id"] in mirror)


def rel_lines(ids: list[int], deltas: dict[str, float], cfg: dict, mirror: set[int] = frozenset()) -> list[str]:
    """Relative Pan/Tilt lines in degrees; a head marked flip_pan / flip_tilt (hung upside down) gets the opposite sign."""
    groups = {}
    for id_ in ids:
        f = find(cfg["fixtures"], id_)
        groups.setdefault((pan_flip(f, mirror), f.get("flip_tilt") is True), []).append(id_)
    lines = []
    for flips, group in groups.items():
        steps = [(attr, -v if flip else v) for (attr, v), flip in zip(((k, deltas.get(k, 0)) for k in ("pan", "tilt")), flips) if v]
        if steps:
            lines.append(select_line(group))
        for attr, v in steps:
            template = cfg["attrs"][attr].get("rel_cmd", f'Attribute "{attr.title()}" At {{sign}} {{v}}')
            lines.append(template.format(sign="+" if v > 0 else "-", v=f"{abs(v):g}"))
    return lines


def parse_label(action: dict) -> str:
    label = action.get("label")
    if not isinstance(label, str) or not 1 <= len(label.strip()) <= 30:
        raise ActionError("метка: нужна строка 1-30 символов")
    return label.strip()


def build(action: dict, cfg: dict) -> list[str]:
    if not isinstance(action, dict):
        raise ActionError("действие должно быть объектом")
    a = action.get("a")
    if a in ("halt", "resume", "clear", "undo", "layout_save", "fixtures_fetch", "show_identify", "show_bind", "show_open_plan", "shows_list", "show_load", "show_save", "move_start", "move", "preset_save", "preset_go",
             "preset_delete", "group_save", "group_delete", "beam_home", "beam_invert",
             "scene_create", "scenes_import", "page_save", "scene_rename", "scene_delete", "hall_save", "fixture_flag", "plan_copy"):
        return []
    if a == "page_go":
        return [f"Page {page_number(action)}"]
    if a in ("scene_go", "scene_off", "store_scene"):
        scene = find(cfg["scenes"], action.get("id"))
        ex = scene["exec"]
        if a == "scene_go":
            fade = fade_suffix(action, cfg)  # `Goto Cue 4 Executor 1.8 Fade 5`: MA2 3.9 manual p. 1110; not yet run on a console
            # ClearAll first: values left in the programmer would stay on top of the scene (owner 2026-10-21)
            return ["ClearAll", f"Goto Cue 1 Executor {ex}{fade}" if fade else f"Go Executor {ex}"]
        if a == "scene_off":
            return [f"Off Executor {ex}"]
        return store_lines(ex, scene["label"])
    if a == "blackout":
        return [f"Off Executor {s['exec']}" for s in cfg["scenes"]]
    if a == "master":
        return [cfg["master"]["cmd"].format(v=_value(action, "v"))]
    if a == "select_group":
        group = find(cfg["groups"], action.get("id"))  # always explicit fixture ids: MA2 group numbers are unverified
        return build({"a": "select_fixtures", "ids": group["fixtures"]}, cfg)
    if a == "select_fixtures":
        ids = action.get("ids")
        known = {f["id"] for f in cfg["fixtures"]}
        if not isinstance(ids, list) or not ids or any(type(i) is not int or i not in known for i in ids):
            raise ActionError("неизвестные приборы")
        return [select_line(ids)]
    if a == "dim":
        return [f"At {_value(action, 'v')}" + fade_suffix(action, cfg)]
    if a in ("zoom", "focus", "strobe"):
        _value(action, "v")
        return attr_lines({a: action["v"]}, cfg)
    if a == "jog":
        check_jog(action)
        return []
    if a == "nudge":
        attr, direction = action.get("attr"), action.get("dir")
        if attr not in ("pan", "tilt") or type(direction) is not int or direction not in (-1, 1):
            raise ActionError("шаг: нужны attr pan/tilt и dir 1/-1")
        spec = cfg["attrs"][attr]
        step = nudge_step(action, cfg)
        template = spec.get("rel_cmd", f'Attribute "{attr.title()}" At {{sign}} {{v}}')
        return [template.format(sign="+" if direction == 1 else "-", v=f"{step:g}")]
    if a == "aim":
        lines = []
        if not any(attr in action for attr in ("pan", "tilt")):
            raise ActionError("aim: нужен pan или tilt")
        for attr in ("pan", "tilt"):
            if attr not in action:
                continue
            v, spec = action.get(attr), cfg["attrs"][attr]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not spec["min"] <= v <= spec["max"]:
                raise ActionError(f'{attr}: нужно число {spec["min"]:g}…{spec["max"]:g} градусов')
            lines.append(spec["cmd"].format(v=f"{v:g}"))
        return lines
    if a == "color":
        fade = fade_suffix(action, cfg)
        spec = cfg.get("attrs", {}).get("color", {})
        names = spec.get("names", ["ColorRGB1", "ColorRGB2", "ColorRGB3"])
        values = [float(_value(action, k)) for k in ("r", "g", "b")]
        if spec.get("mode", "rgb") == "cmy":
            values = [100 - v for v in values]
        return [f'Attribute "{name}" At {v:g}{fade}' for name, v in zip(names, values)]
    raise ActionError(f"неизвестное действие: {a!r}")


def targets(action: dict, cfg: dict) -> list[int] | None:
    if not isinstance(action, dict):
        raise ActionError("действие должно быть объектом")
    if action.get("a") == "select_group":
        return list(find(cfg["groups"], action.get("id"))["fixtures"])
    if action.get("a") == "select_fixtures":
        build(action, cfg)
        return list(action["ids"])
    return None


def validate_hall(hall) -> dict:
    if not isinstance(hall, dict) or set(hall) != {"w", "d", "stage", "stageDepth"}:
        raise ActionError("hall: нужны w, d, stage, stageDepth")
    if any(type(hall[k]) not in (int, float) or not 2 <= hall[k] <= 80
           for k in ("w", "d", "stageDepth")):
        raise ActionError("hall: размеры должны быть числами 2–80 метров")
    if hall["stage"] not in ("top", "bottom", "left", "right"):
        raise ActionError("hall.stage: нужно top, bottom, left или right")
    side = hall["d"] if hall["stage"] in ("top", "bottom") else hall["w"]
    if hall["stageDepth"] >= side:
        raise ActionError("hall.stageDepth: глубина сцены должна быть меньше стороны зала")
    return dict(hall)


def parse_positions(action: dict, cfg: dict) -> dict[int, tuple[float, float] | None]:
    """x and y both null take the fixture off the plan, back to the tray."""
    if not isinstance(action, dict):
        raise ActionError("действие должно быть объектом")
    positions = action.get("pos")
    if not isinstance(positions, list) or not positions:
        raise ActionError("нужен непустой список позиций")
    known = {f["id"] for f in cfg["fixtures"]}
    result = {}
    for position in positions:
        if not isinstance(position, dict):
            raise ActionError("позиция должна быть объектом")
        id_ = position.get("id")
        if type(id_) is not int or id_ not in known:
            raise ActionError("неизвестный прибор")
        coordinates = (position.get("x"), position.get("y"))
        if coordinates == (None, None):
            result[id_] = None
            continue
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1
               for v in coordinates):
            raise ActionError("координаты: нужны числа 0-1")
        result[id_] = tuple(float(v) for v in coordinates)
    return result


# MA2 3.9: "Error #43: LOGIN NEEDED", "Error : ...", "Login incorrect". Only at a line start, and the bare phrases only in
# MA2's upper case: a group, show or fixture named "Terror" or "error test" in a List/ListVar reply is not an error.
ERROR_LINE = re.compile(r"(?im)^\s*(?:error\b|login incorrect)")
ERROR_PHRASES = re.compile(r"UNKNOWN COMMAND|ILLEGAL COMMAND|ILLEGAL CHARACTER|COMMAND NOT EXECUTED")


def is_error_reply(text: str) -> bool:
    return bool(ERROR_LINE.search(text) or ERROR_PHRASES.search(text))


def load_config(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise SystemExit(f"Нет файла конфига: {path}")
    except json.JSONDecodeError as e:
        raise SystemExit(f"Битый JSON в {path}: {e}")


# DMX read-back through MA2 Lua: the only way found to learn what the desk outputs (Telnet lists no values).
# Only the documented getdmx(recycle, address, amount) form, 1-based. Needs Admin rights over Telnet (Program: Error #44).
# Hall 2026-10-21 (v23, Admin): gma.feedback never reached Telnet and gma.show.setvar left nothing in ListVar, so the line
# runs the desk's own SetVar command (a global variable, which ListVar prints as "Global : $PANELDMX<address> = ...").
# The quotes come from %q and the dollar from string.char: a literal " would end the Lua argument, a $ would be substituted.
# One line per chunk of 32 values: the Lua line and the SetVar line it runs (32 values of up to 4 characters) both stay
# under 255 characters, the assumed MA2 command line limit.
DMX_CHUNK = 32
# Hall v24.1: the canary's SetVar reached ListVar, the data lines' did not; v26 (values rounded) reached it with every
# value -1 and $PANELST = -2: the undocumented getdmx(recycle, address, amount) form returns no table on onPC 3.9.60.
# So each address is read with the documented one-address form getdmx(address) -> 0-255 (also what MA's own Littlites
# plug-in uses), each call under pcall. Until values arrive the canary reports $PANELST (1 the call worked, -1 it failed)
# and $PANELV (the first address's raw value).
DMX_LUA = ("Lua \"local a,n={a},{n} local v={{}} for i=1,n do local ok,x=pcall(gma.show.getdmx,a+i-1) "
           "v[i]=ok and tonumber(x) and math.floor(x+.5) or -1 end "
           "gma.cmd(('SetVar %sPANELDMX%d = %q'):format(string.char(36),a,'T '..a..' '..table.concat(v,',')))\"")
DMX_CANARY = ("Lua \"local D='SetVar '..string.char(36)..'PANEL' local ok,v=pcall(gma.show.getdmx,{a}) "
              "gma.cmd(D..'ST = '..(ok and 1 or -1)) gma.cmd(D..'V = '..(ok and tonumber(v) or -1))\"")
DMX_ROW = re.compile(r"PANELDMX\d+\s*=\s*\"?([TS]) (\d+) (-?[\d.]+(?:,-?[\d.]+)*)")


def absolute(address) -> int | None:
    """"1.289" -> 289, "2.001" -> 513."""
    m = re.fullmatch(r"(\d+)\.(\d+)", str(address or ""))
    return (int(m[1]) - 1) * 512 + int(m[2]) if m else None


def dmx_intervals(fixtures: list[dict]) -> list[tuple[int, int]]:
    """Sorted (start, count) ranges, without reading holes in a sparse patch."""
    spans = sorted((a, a + f.get("channels", 1)) for f in fixtures
                   if not f.get("missing") and (a := absolute(f.get("address")))
                   and f.get("channels", 1) > 0)
    merged = []
    for start, end in spans:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return [(start, end - start) for start, end in merged]


def dmx_span(fixtures: list[dict]) -> tuple[int, int] | None:
    """(first address, count) covering every patched fixture of the plan."""
    spans = [(a, a + f.get("channels", 1) - 1) for f in fixtures if not f.get("missing") and (a := absolute(f.get("address")))]
    return (min(s for s, _ in spans), max(e for _, e in spans) - min(s for s, _ in spans) + 1) if spans else None


def dmx_lua(start: int, count: int) -> list[str]:
    """One Lua line per chunk of DMX_CHUNK addresses."""
    return [DMX_LUA.format(a=a, n=min(DMX_CHUNK, start + count - a)) for a in range(start, start + count, DMX_CHUNK)]


def parse_dmx(text: str, *, span: tuple[int, int] | None = None) -> dict[int, float]:
    """{absolute address: 0-255} from the Lua feedback or ListVar; -1 (unreadable) is left out."""
    out = {}
    for m in DMX_ROW.finditer(text):
        if span is not None and (int(re.match(r"PANELDMX(\d+)", m[0])[1]) != span[0]
                                 or int(m[2]) != span[0] or len(m[3].split(",")) != span[1]):
            continue
        for i, v in enumerate(m[3].split(",")):
            if float(v) >= 0:
                out[int(m[2]) + i] = float(v)
    return out


def live_from_dmx(fixtures: list[dict], dmx: dict[int, float], dmx_map: dict) -> dict[int, dict]:
    """What each fixture shows, from its type's channel numbers (1-based: dim, r, g, b). Without dim the level is the
    brightest colour; without colour channels it is white."""
    live = {}
    for f in fixtures:
        start, spec = absolute(f.get("address")), dmx_map.get(f.get("type") or "")
        if start is None or not spec:
            continue
        get = lambda key: dmx.get(start + spec[key] - 1) if spec.get(key) else None  # noqa: E731
        rgb = [get(k) for k in "rgb"]
        dim = get("dim")
        if dim is None and None in rgb:
            continue
        rgb = [100.0, 100.0, 100.0] if None in rgb else [round(v / 2.55, 1) for v in rgb]
        level = round(dim / 2.55, 1) if dim is not None else max(rgb)
        if dim is None and level:
            rgb = [round(v * 100 / level, 1) for v in rgb]
        live[f["id"]] = {"dim": level, "rgb": rgb}
    return live


def check_dmx_map(spec) -> dict:
    """{dim, r, g, b}: channel numbers 1-64 or absent."""
    if not isinstance(spec, dict) or set(spec) - {"dim", "r", "g", "b"}:
        raise ActionError("каналы: dim, r, g, b")
    if any(type(v) is not int or not 1 <= v <= 64 for v in spec.values()):
        raise ActionError("номер канала: целое 1-64")
    return spec


# Patch and RDM (spec section 21). Commands from the grandMA2 3.9 manual: keyword Dmx ("Assign Dmx 1.101 At Fixture 2";
# assigning a fixture to a start address removes its old patch) and RdmSetParameter (PIDs dmx_start_address, identify_device).
UID = re.compile(r"\b([0-9A-Fa-f]{4}):?([0-9A-Fa-f]{8})\b")


def dmx_text(start: int) -> str:
    """289 -> "1.289"."""
    return f"{(start - 1) // 512 + 1}.{(start - 1) % 512 + 1:03d}"


def parse_address(value) -> int:
    """"1.290", "290" or 290 -> absolute 1-based address; anything else is refused."""
    m = re.fullmatch(r"(?:(\d{1,3})\.)?(\d{1,3})", str(value).strip()) if isinstance(value, (str, int)) and type(value) is not bool else None
    if not m or not 1 <= int(m[2]) <= 512 or m[1] is not None and not 1 <= int(m[1]) <= 256:
        raise ActionError("адрес: 1-512 или вселенная.адрес, например 1.290")
    return (int(m[1] or 1) - 1) * 512 + int(m[2])


def check_uid(value) -> str:
    m = UID.fullmatch(value.strip()) if isinstance(value, str) else None
    if not m:
        raise ActionError("UID: 12 шестнадцатеричных знаков, например 43500F019FCB")
    return (m[1] + m[2]).upper()


def patch_rows(fixtures: list[dict]) -> list[dict]:
    """One row per patched fixture: MA2 range (profile footprint) and, when read by RDM or entered, the physical one.
    conflicts: ids whose MA2 or physical range shares an address with this one. An unknown footprint is never guessed."""
    rows = []
    for f in fixtures:
        start = absolute(f.get("address"))
        if f.get("missing") or start is None:
            continue
        rdm = f.get("rdm") or {}
        # RDM addresses are within the device's line (1-512); the device is taken to sit on its patch universe.
        phys_start = (start - 1) // 512 * 512 + rdm["address"] if rdm.get("address") else start
        rows.append({"id": f["id"], "start": start, "ma2": f.get("footprint") or f.get("channels"), "ma2_from": "List FixtureType" if f.get("footprint") else "экспорт" if f.get("channels") else None,
                     "phys_start": phys_start, "phys": rdm.get("footprint"),
                     "uid": rdm.get("uid"), "conflicts": []})
    spans = [(r["id"], r["start"], r["start"] + (r["ma2"] or 1) - 1) for r in rows]
    spans += [(r["id"], r["phys_start"], r["phys_start"] + r["phys"] - 1) for r in rows if r["phys"]]
    for r in rows:
        mine = [(s, e) for i, s, e in spans if i == r["id"]]
        r["conflicts"] = sorted({i for i, s, e in spans if i != r["id"] and any(s <= me and ms <= e for ms, me in mine)})
    return rows


def patch_plan(fixtures: list[dict], fid: int, start: int, patch: bool, physical: bool) -> dict:
    """What a readdress changes, checked against every other fixture of the plan. token: the plan's fingerprint, so a
    write is accepted only for the exact plan the operator saw."""
    f = next((x for x in fixtures if x["id"] == fid and not x.get("missing")), None)
    if f is None or absolute(f.get("address")) is None:
        raise ActionError(f"прибор {fid} не в патче плана: сначала «Получить приборы»")
    if not (f.get("footprint") or f.get("channels")):
        raise ActionError(f"число каналов прибора {fid} в MA2 не прочитано: перечитайте патч, без него пересечения не проверить")
    if not patch and not physical:
        raise ActionError("нечего менять: выберите патч MA2, физический адрес или оба")
    uid = (f.get("rdm") or {}).get("uid")
    if physical and not uid:
        raise ActionError("физический адрес меняется только у прибора, связанного с RDM-устройством (UID)")
    after = [dict(x, address=dmx_text(start)) if x["id"] == fid and patch else x for x in fixtures]
    if physical:
        after = [dict(x, rdm={**x["rdm"], "address": (start - 1) % 512 + 1}) if x["id"] == fid else x for x in after]
    row = next(r for r in patch_rows(after) if r["id"] == fid)
    old = absolute(f["address"])
    plan = {"id": fid, "name": f.get("name") or f.get("label"), "uid": uid, "patch": patch, "physical": physical,
            "old": dmx_text(old), "new": dmx_text(start), "old_phys": (f.get("rdm") or {}).get("address"),
            "ma2_range": [start if patch else old, (start if patch else old) + row["ma2"] - 1] if row["ma2"] else None,
            "phys_range": [row["phys_start"], row["phys_start"] + row["phys"] - 1] if row["phys"] else None,
            "conflicts": row["conflicts"], "lines": []}
    if physical:
        plan["lines"].append(f"RdmSetParameter dmx_start_address {(start - 1) % 512 + 1} / UID = {uid}")
    if patch:
        plan["lines"].append(f"Assign Fixture {fid} At Dmx {dmx_text(start)}")
    plan["token"] = f"{abs(hash(json.dumps([plan, f], sort_keys=True, ensure_ascii=False))):x}"
    return plan


def parse_type_footprints(text: str) -> dict[str, int]:
    """{type number: DMX footprint} from List FixtureType. Hall 2026-10-21 (3.9.60.68): fixed-width columns under a header
    "No.  LongName ... DMXFootprint  Instances ...", rows "FixtureType 4 4    Mini-B ... 17            1 ...". The export
    counts fewer channels than the profile takes (Mini-B: 14 in the export, 17 here and in the patch spacing)."""
    lines = text.splitlines()
    head = next((ln for ln in lines if "DMXFootprint" in ln and "Instances" in ln), None)
    if head is None:
        return {}
    a, b = head.index("DMXFootprint"), head.index("Instances")
    out = {}
    for ln in lines:
        m = re.match(r"FixtureType (\d+) ", ln)
        if m and ln[a:b].strip().isdigit():
            out[m[1]] = int(ln[a:b].strip())
    return out


def type_no(kind) -> str | None:
    m = re.match(r"(\d+) ", kind or "")
    return m[1] if m else None


def parse_rdm_list(text: str) -> list[dict]:
    """RdmList feedback -> [{uid, line}]. ponytail: the 3.9 manual gives no column layout, so only the UID is taken;
    the line is kept as the desk wrote it. Address and footprint are read only when the line labels them."""
    out, seen = [], set()
    for line in text.splitlines():
        m = UID.search(line)
        if not m or (uid := (m[1] + m[2]).upper()) in seen:
            continue
        seen.add(uid)
        row = {"uid": uid, "line": " ".join(line.split())[:300]}
        for key, label in (("address", r"(?:dmx\s*)?(?:start\s*)?addr(?:ess)?"), ("footprint", r"footprint")):
            v = re.search(rf"(?i)\b{label}\s*[:=]?\s*(\d+)\b", line)
            if v and 1 <= int(v[1]) <= 512:
                row[key] = int(v[1])
        out.append(row)
    return out
