"""Bridge: panels over WebSocket, one Telnet link to grandMA2."""

import argparse
import asyncio
import json
import logging
import mimetypes
import os
import re
import shutil
import socket
import sys
import subprocess
import tempfile
from secrets import token_urlsafe
import time
import uuid
from contextvars import ContextVar
import xml.etree.ElementTree as ET
from collections import deque
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.parse import urlsplit

# Run the stable recovery copy before importing any replaceable application module.
if __name__ == '__main__':
    recovery = Path(__file__).parent / '.updates/recovery.py'
    if recovery.exists():
        version_file = Path(__file__).parent / 'VERSION'
        before_recovery = version_file.read_bytes() if version_file.exists() else b''
        subprocess.run([sys.executable, str(recovery), '--recover', str(Path(__file__).parent)], check=True)
        after_recovery = version_file.read_bytes() if version_file.exists() else b''
        if before_recovery != after_recovery:
            os.execv(sys.executable, [sys.executable, *sys.argv])

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from commands import (FULL, PLAN_WRITES, SIMPLE, SLIDERS, ActionError, apply_move, build, can_move, check_jog, check_move, exec_page, find, exec_verdict,
                      head_lines, is_error_reply, load_config, movers, page_number, parse_executors, parse_label, parse_running,
                      absolute, check_dmx_map, check_uid, parse_address, parse_rdm_list, parse_type_footprints, patch_plan, patch_rows, type_no, DMX_CANARY, DMX_CHUNK, dmx_lua, dmx_span, dmx_intervals, live_from_dmx, parse_dmx,
                      parse_positions, parse_ma2_objects, group_slot_empty, mirrored, pan_flip, rel_lines, select_line, store_lines, targets, unrecognised_lines, validate_hall)
from fixtures import merge_fixtures, parse_export, parse_group_export, save_config
from migrations import SITE_KEYS, legacy_archive_path, migrate_config, merge_settings
from show_plans import plan_path as show_plan_path
from api import DIAG_HINTS, PROBE_COMMANDS, register as register_api  # noqa: F401 (PROBE_COMMANDS: tests)
from link import HALTED, LOGIN_OK, NO_LINK, PROMPT, READY, STALE, UNKNOWN, VAR, MA2Link, Throttle, clean  # noqa: F401 (tests import several from here)
from scenes import canonical_exec, ordered_scenes, merge_scenes, slot_candidates
from status_evidence import Evidence
from commands import nudge_step
from mock import start_mock
import exports
import rdm_search
import diagnostic_upload
from types import SimpleNamespace
from safety import validate_settings, without_passwords, DEFAULT_MA2, effective_safety, load_secret, load_settings, make_guard, redact

log = logging.getLogger("bridge")
HERE = Path(__file__).parent
LOOPBACK = ("127.0.0.1", "::1")
SHOW_POLL_S = 2  # ListVar while waiting for a loaded show; tests shorten it
READ_RETRY_S = 30  # back off temporary profile/Lua failures without restarting the bridge
READ_ATTEMPTS = 3


def is_loopback(request: Request) -> bool:
    return (request.client.host if request.client else "") in LOOPBACK


# «История»: names, and which actions change only the desk (shown in the list, not undone by the panel)
HISTORY_NAMES = {"dim": "Яркость", "color": "Цвет", "move": "Позиция", "jog": "Позиция", "nudge": "Позиция", "aim": "Позиция",
                 "preset_go": "Пресет позиции", "zoom": "Zoom", "focus": "Focus", "strobe": "Стробоскоп", "scene_go": "Сцена",
                 "scene_off": "Сцена выкл", "blackout": "Затемнение", "scene_create": "Запись сцены", "scene_rename": "Имя сцены",
                 "scene_delete": "Удаление сцены", "page_save": "Имя страницы", "group_save": "Группа", "group_delete": "Удаление группы",
                 "group_store_ma2": "Группа в MA2", "preset_save": "Пресет", "preset_delete": "Удаление пресета", "layout_save": "Расстановка",
                 "hall_save": "Форма зала", "fixture_flag": "Прибор", "beam_home": "Луч", "beam_invert": "Луч", "dmx_map": "Каналы DMX",
                 "scenes_import": "Сцены из MA2", "fixtures_fetch": "Приборы из MA2", "ma2_import": "Группы и пресеты из MA2",
                 "show_load": "Загрузка шоу", "show_bind": "План шоу", "plan_copy": "Копия плана", "page_go": "Страница", "undo": "Откат"}
HISTORY_LIGHT = {"dim", "color", "move", "jog", "nudge", "aim", "preset_go", "zoom", "focus", "strobe"}
HISTORY_DESK = {"scene_go", "scene_off", "blackout", "scene_create", "scene_rename", "page_save", "group_store_ma2", "show_load",
                "show_bind", "plan_copy", "page_go"}
MISSING = object()


def create_app(cfg: dict, mock: bool, config_path: str, settings: dict | None = None, password: str = "",
               settings_path: str | Path | None = None, capture: bool = False) -> FastAPI:
    settings_path = Path(settings_path) if settings_path is not None else Path(config_path).parent / "settings.json"
    if Path(config_path).exists():
        archive = legacy_archive_path(config_path, cfg)
        cfg, migrated_settings = migrate_config(config_path, settings_path, archive_path=archive)
        settings = merge_settings(migrated_settings, settings or {})
    settings = settings or {}
    cfg = {**cfg, "scenes": ordered_scenes(cfg.get("scenes", []), cfg.get("scene_order_version") == 1), "scene_order_version": 1}
    config_attrs = cfg.get("attrs", {})
    settings_path = Path(settings_path)
    original_attrs = cfg.get("attrs", {})
    cfg = {**cfg, "attrs": {k: {**original_attrs.get(k, {}), **settings.get("attrs", {}).get(k, {})}
                            for k in original_attrs.keys() | settings.get("attrs", {}).keys()}}
    features = {k: settings.get("features", {}).get(k, True)
                for k in ("dim", "color", "move", "zoom", "focus", "strobe", "scenes", "store")}
    attr_names = set()

    def get_config_attrs():
        return original_attrs

    def refresh_attr_names():
        attr_names.clear()
        attr_names.update(cfg["attrs"].get("color", {}).get("names", ["ColorRGB1", "ColorRGB2", "ColorRGB3"]))
        for spec in cfg["attrs"].values():
            for key in ("cmd", "rel_cmd"):
                attr_names.update(re.findall(r'Attribute "([^"]+)"', spec.get(key, "")))
        add_strobe_attrs(cfg.get("dmx_map", {}))

    def add_strobe_attrs(maps):
        for spec in maps.values():
            name = spec.get("strobe", {}).get("attr", "")
            if re.fullmatch(r"[A-Za-z0-9_]+", name):
                attr_names.add(name)
    refresh_attr_names()
    ma2 = {**DEFAULT_MA2, **cfg.get("ma2", {}), **settings.get("ma2", {})}
    # a config.json written for the spec's draft carries /o: on the real MA2 that export silently writes no file
    ma2["export_cmd"] = re.sub(r"\s+/o(verwrite)?\s*$", "", ma2["export_cmd"], flags=re.I)
    types_tried: set[str] = set()  # successfully read fixture types in the current context
    type_retries: dict[str, tuple[int, float]] = {}  # failed attempts and next admissible read
    export_extra: set[str] = set()  # exact export lines of one diagnostics run, see /api/diag/export_probe
    guard = make_guard(effective_safety(settings), attr_names, ma2["export_cmd"], export_extra,
                       rdm_extra=rdm_search.RDM_GLOBAL)
    try:
        empty_re = re.compile(ma2.get("exec_empty_regex", r"(?i)no objects? found|nothing found"))
    except (re.error, TypeError) as e:
        raise SystemExit(f"неверный ma2.exec_empty_regex: {e}") from e
    cfg.get("ma2", {}).pop("password", None)  # never used, never written back into config.json (main() refuses it earlier)
    safety = effective_safety(settings)
    mode = safety["mode"]
    allowed_fixtures, allowed_scenes = set(safety["allowed_fixtures"]), {str(e) for e in safety["allowed_scenes"]}
    store_execs = {str(e) for e in safety["store_execs"]}
    rate_hz = min(10, max(1, settings.get("rate_hz", cfg.get("rate_hz", 5))))
    poll_seconds = settings.get("poll_seconds", 2)
    dmx_seconds = settings.get("dmx_seconds", 0 if mock else 2)  # read-back of the desk's output for the plan; 0 = off
    export_dir = ma2.get("export_dir") or str(Path(config_path).parent / "importexport")
    if mock and not Path(export_dir).is_dir():
        export_dir = tempfile.mkdtemp()
    scene_evidence = Evidence()
    value_evidence = Evidence()
    sent_evidence = Evidence("panel")
    poll_wake = asyncio.Event()
    broadcast_lock = asyncio.Lock()
    scene_revision: dict[str, int] = {}  # only actions involving this scene supersede its pending Off
    clients: set[WebSocket] = set()
    sessions: dict[WebSocket, dict] = {}  # per tab: selection and the pan/tilt the gesture started from
    state = {"values_revision": 0, "plan_epoch": 0, "master": None, "read_freshness": {"fixtures": False, "ma2": False, "scenes": False}, "shown": {}, "tracked": True, "page": None, "show": {"name": None, "source": "unknown"}, "export_file": None, "loading": None, "live": {}, "dmx": {}, "dmx_read": None, "type_reads": {}, "rdm": None, "export_trace": None, "export_probe": None,
             "show_load": {"state": "idle", "name": None, "reason": ""}, "shows": {},
             "sent": {}, "no_attr": {}}  # what the panels display, shared; sent: {fid: attrs the panel itself put into its programmer}
    active_operations = {}
    operation = ContextVar("operation", default=None)
    bridge_epoch = uuid.uuid4().hex
    config_writes = {"layout_save", "hall_save", "fixture_flag", "group_save", "group_delete",
                     "preset_save", "preset_delete", "beam_home", "beam_invert", "dmx_map", "rdm_link",
                     "scene_create", "scene_rename", "scene_delete", "page_save", "scenes_import",
                     "ma2_import", "fixtures_fetch", "import_confirm_merge", "plan_copy", "show_bind",
                     "show_open_plan", "show_load", "patch_apply", "undo"}

    def revision_token():
        return f"{bridge_epoch}:{config_revision()}"

    class ActionLock(asyncio.Lock):
        async def __aenter__(self):
            await super().__aenter__()
            op = operation.get()
            if op and op["a"] in config_writes and not op.get("revision_checked"):
                if op["revision"] != revision_token():
                    op["conflict"] = True
                    self.release()
                    raise ActionError("план изменён другим клиентом; обновите данные и повторите правку")
                op["revision_checked"] = True
            if op and op.get("revision_checked"):
                op["lock_revision"] = revision_token()
                op["lock_config"] = json.loads(json.dumps({k: v for k, v in cfg.items() if k != "attrs"}))
            return self

        async def __aexit__(self, *exc):
            if (op := operation.get()) and op.get("revision_checked"):
                snap = op.pop("lock_config")
                changed = {k: snap.get(k, MISSING) for k in (set(snap) | set(cfg)) - {"attrs"}
                           if snap.get(k, MISSING) != cfg.get(k, MISSING)}
                for key, value in changed.items():
                    op.setdefault("history_before", {}).setdefault(key, value)
                if changed:
                    op["history_context"] = history_context()
                op["result_revision"] = revision_token()
                op["local_changed"] = op.get("local_changed", False) or op["result_revision"] != op["lock_revision"]
            return await super().__aexit__(*exc)

    action_lock = ActionLock()  # validate the shared-plan revision inside the same critical section
    bg: set[asyncio.Task] = set()
    journal: deque[dict] = deque(maxlen=300)  # who pressed what; sliders are left out (10 per second)
    # «История»: the last 100 changes with what undoes them. ponytail: in memory, a restart forgets it.
    history: deque[dict] = deque(maxlen=100)
    history_n = [0]

    highlight_path = Path(config_path).parent / "highlight.json"
    highlight = {"state": "idle", "owner": None}
    if highlight_path.exists():
        try:
            saved = json.loads(highlight_path.read_text(encoding="utf-8"))
            if not isinstance(saved, dict) or not isinstance(saved.get("zone"), list):
                raise ValueError("неверный журнал подсветки")
            highlight.update({k: saved.get(k) for k in ("show", "zone", "target", "t")})
            highlight.update(state="stuck", reason="подсветка ожидает снятия после входа", restore_invalid=True, release_token=uuid.uuid4().hex)
        except (OSError, ValueError) as e:
            highlight.update(state="stuck", reason=str(e), restore_invalid=True, release_token=uuid.uuid4().hex)

    def status_msg():
        return {"status": {"show_file_active": bool(state.get("show_file_active")), "show_file": state.get("show_file"), "operations": [{"request_id": op["id"], "a": op["a"], "stage": op.get("stage", "running")} for op in active_operations.values()], "read_freshness": dict(state["read_freshness"]), "show_load": state["show_load"], "highlight": highlight_status(), "show": state["show"], "features": features, "no_attr": state["no_attr"], "ma2": link.state, "login": {k: link.vars.get(k) for k in ("USER", "USERRIGHTS", "USERPROFILE", "VERSION")} if link.ready else None, "mock": mock, "halted": link.halted, "last": link.last, "manual": link.manual,
                           "rdm_search": rdm.snapshot(),
                           "safety": {"mode": mode, "fixtures": sorted(allowed_fixtures), "scenes": sorted(allowed_scenes),
                                      "store": sorted(store_execs), "master": safety["allow_master"] or mode == "full",
                                      "page": safety["allow_page_change"] or mode == "full",
                                      **{k: safety[k] for k in ("allow_fixture_read", "allow_highlight", "allow_show_load", "allow_show_save", "allow_group_store", "allow_patch", "allow_rdm")}}}}

    def config_revision():
        snapshot = json.dumps(cfg, sort_keys=True, ensure_ascii=False)
        if snapshot != state.get("config_snapshot"):
            state["config_snapshot"] = snapshot
            state["config_revision"] = state.get("config_revision", 0) + 1
        return state["config_revision"]

    def config_msg():
        config_revision()
        plans = []
        for p in sorted((Path(config_path).parent / "shows").glob("*.json")):
            try:
                name = json.loads(p.read_text(encoding="utf-8-sig")).get("show")
            except (OSError, ValueError, AttributeError):
                continue
            if isinstance(name, str) and name != cfg.get("show") and name not in plans:
                plans.append(name)
        return {"config": {**{k: cfg.get(k) for k in ("groups", "ma2groups", "ma2presets", "fixtures", "scenes", "plan", "hall", "presets", "attrs", "pages", "show", "fixtures_read", "dmx_map", "scene_order_version")},
                           "dmx_map": {k: v for k, v in cfg.get("dmx_map", {}).items() if not v.get("stale") and not v.get("unsupported")},
                           "plans": plans, "revision": revision_token(), "patch": patch_rows(cfg["fixtures"])}}

    def scenes_msg():
        values, meta = scene_evidence.snapshot(sc["id"] for sc in cfg["scenes"])
        return {"running": values, "running_meta": meta}

    def values_meta():
        attrs = sent_evidence.snapshot(k for k in sent_evidence.records if k.startswith("sent:"))[1]
        records = list(attrs.values())
        summary = ({"source": "panel", "freshness": "fresh" if any(m["freshness"] == "fresh" for m in records) else "stale",
                    "updated_at": max(m["updated_at"] for m in records)} if records else
                   {"source": "unknown", "freshness": "unknown", "updated_at": None})
        return {**attrs, "shown": summary,
                "master": sent_evidence.snapshot(["master"])[1]["master"],
                "live": value_evidence.snapshot(["live"])[1]["live"]}

    def known_shown():
        """Only unexpired panel-sent attributes; this is never output readback."""
        values = sent_evidence.snapshot(k for k in sent_evidence.records if k.startswith("sent:"))[0]
        known = {}
        for fid, entry in state["shown"].items():
            fresh = {attr: value for attr, value in entry.items() if values.get(f"sent:{fid}:{attr}") is not None}
            if fresh:
                known[fid] = fresh
        return known

    def invalidate_evidence():
        had_evidence = bool(scene_evidence.records or value_evidence.records or sent_evidence.records
                            or state["shown"] or state["live"] or state["dmx"] or state["master"] is not None)
        scene_evidence.invalidate()
        value_evidence.invalidate()
        sent_evidence.invalidate()
        state["shown"], state["sent"], state["live"], state["dmx"] = {}, {}, {}, {}
        state["master"], state["tracked"] = None, False
        for session in sessions.values():
            session["base"] = None
        if had_evidence:
            spawn_broadcast({**scenes_msg(), **shown_msg(), "dmx": {}})

    def shown_msg():
        state["values_revision"] += 1
        # Panel-sent values only; none of these are physical readback.
        sent = {fid: {k: v for k, v in entry.items() if k in state["sent"].get(fid, ())} for fid, entry in known_shown().items()}
        return {"values_revision": state["values_revision"], "master": state["master"], "shown": {fid: entry for fid, entry in sent.items() if entry}, "tracked": state["tracked"], "page": state["page"], "live": state["live"], "values_meta": values_meta()}

    def session_msg(ws, msg):
        if sessions.get(ws, {}).get("simple") and "config" in msg:
            return {"config": {k: msg["config"].get(k) for k in ("scenes", "pages")}}
        return msg

    async def broadcast(msg, skip=None):
        # Preserve publication order across clients, including a disconnect's invalidation.
        # A stalled browser is removed rather than holding up later snapshots indefinitely.
        async with broadcast_lock:
            for ws in list(clients):
                if ws is skip:
                    continue
                try:
                    await asyncio.wait_for(ws.send_json(session_msg(ws, msg)), timeout=.5)
                except Exception:
                    clients.discard(ws)
                    try:
                        await asyncio.wait_for(ws.close(code=1013), timeout=.5)
                    except Exception:
                        pass

    def spawn_broadcast(msg):
        task = asyncio.create_task(broadcast(msg))
        bg.add(task)
        task.add_done_callback(bg.discard)

    def history_context():
        return (state["plan_epoch"], state["show"].get("name"), cfg.get("show"), link._gen)

    def history_reason(entry, owner=False):
        if not owner and entry.get("undo_state") == "in_progress":
            return "откат выполняется"
        if entry.get("undo_error"):
            return "откат прерван: " + entry["undo_error"]
        if any(sent_evidence.clock() - stamp >= 6 for stamp in entry.get("basis_times", {}).values()):
            return "прежние отправленные значения устарели"
        if entry.get("context") != history_context():
            return "изменилось шоу, план или соединение"
        if state["show"].get("name") and cfg.get("show") and state["show"]["name"] != cfg["show"]:
            return "на пульте другое шоу"
        return ""

    def history_msg():
        return {"history": [{**{k: e[k] for k in ("n", "t", "a", "what", "undo", "done")},
                             "undo": e["undo"] and not bool(history_reason(e)), "reason": history_reason(e),
                             "undo_state": e.get("undo_state"), "undo_steps": e.get("undo_steps", [])} for e in history]}

    def add_history(a, what, kind=None, before=None, ids=(), context=None, basis_times=None):
        """kind: "config" (before = changed config keys) or "light" (before = {fid: values}); None: not undoable."""
        context = history_context() if context is None else context
        basis_times = basis_times if basis_times is not None else ({f"sent:{fid}:{attr}": sent_evidence.clock()
                       for fid, values in (before or {}).items() for attr in values} if kind == "light" else {})
        last = history[-1] if history else None
        if kind == "light" and last and not last["done"] and not last.get("undo_state") and last["context"] == context and last["kind"] == "light" and last["a"] == a and last["ids"] == set(ids) and time.monotonic() - last["ts"] < 3:
            for fid, v in before.items():  # one slider drag is one change: the oldest values win
                for attr, value in v.items():
                    last["before"].setdefault(fid, {}).setdefault(attr, value)
            for key, stamp in basis_times.items():
                last["basis_times"].setdefault(key, stamp)
            last["t"], last["ts"], last["undo"], last["what"] = time.strftime("%H:%M:%S"), time.monotonic(), bool(last["before"]), what
        else:
            history_n[0] += 1
            history.append({"n": history_n[0], "t": time.strftime("%H:%M:%S"), "ts": time.monotonic(), "a": a, "what": what,
                            "kind": kind, "before": before, "ids": set(ids), "undo": bool(kind and before), "done": False, "context": context, "basis_times": basis_times})
        spawn_broadcast(history_msg())

    def light_diff(before):
        """{fid: the old values of what changed since the snapshot}; a value the panel did not know before is left out."""
        changed = {}
        for fid, now in known_shown().items():
            old = before.get(fid, {})
            if diff := {k: old[k] for k in now if k in old and old[k] != now[k]}:
                changed[fid] = diff
        return changed

    def light_what(a, action, ids):
        name = HISTORY_NAMES.get(a, a)
        detail = f" {action['v']:g} %" if a == "dim" and isinstance(action.get("v"), (int, float)) else ""
        return f"{name}{detail} · приборов: {len(ids)}" if ids else name

    async def undo_light(before, s, expected_context=None, inverse=None, stages=None, inverse_times=None, expected_basis=None):
        """Send the old values back, fixture by fixture; the first refusal stops it."""
        for fid, v in before.items():
            steps = [(k, {"a": k, "v": v[k]}) for k in ("dim", "zoom", "focus", "strobe") if k in v]
            if "rgb" in v:
                steps.append(("color", {"a": "color", "r": v["rgb"][0], "g": v["rgb"][1], "b": v["rgb"][2]}))
            if pos := {k: v[k] for k in ("pan", "tilt") if k in v}:
                steps.append(("restore_pos", {"a": "restore_pos", "pos": {fid: pos}}))
            for a, action in steps:
                if err := await execute(a, action, s, [fid], log_history=False, expected_context=expected_context, inverse=inverse, stages=stages, inverse_times=inverse_times, expected_basis=expected_basis):
                    return err
        return None


    def forget_positions():
        for entry in state["shown"].values():
            entry.pop("pan", None)
            entry.pop("tilt", None)
        for session in sessions.values():
            session["base"] = None

    def highlight_zone():
        excluded = settings.get("highlight", {}).get("exclude", [])
        return [f["id"] for f in cfg["fixtures"] if not f.get("missing") and not f.get("service")
                and f["id"] not in excluded and (mode == "full" or f["id"] in allowed_fixtures)]

    def highlight_status():
        return {"state": highlight["state"], "zone": highlight.get("zone", []),
                "target": highlight.get("target"), "reason": highlight.get("reason", ""),
                "available": highlight_zone(), "release_token": highlight.get("release_token")}

    def highlight_stuck(reason):
        highlight.update(state="stuck", reason=reason, restore_invalid=True, release_token=uuid.uuid4().hex)
        spawn_broadcast(status_msg())

    def highlight_record(reason, err=None):
        entry = {"t": time.strftime("%H:%M:%S"), "ip": "bridge", "a": "highlight_off",
                 "what": {"reason": reason}, "ok": err is None, "err": err}
        journal.append(entry)
        log.info("action %s", json.dumps(entry, ensure_ascii=False))

    async def highlight_lines(lines):
        # Callers hold action_lock. Preflight the whole operation, including restoration templates.
        zone = highlight["zone"]
        off = "Off " + select_line(zone)
        for line in lines:
            selection = re.fullmatch(r"Fixture (\d+(?: \+ \d+)*)", line)
            in_zone = selection and all(int(fid) in zone for fid in selection[1].split(" + "))
            if not in_zone and line != off and not re.fullmatch(
                    r'At \d+(?:\.\d+)?|Attribute "[A-Za-z0-9_]+" At -?\d+(?:\.\d+)?', line):
                raise ActionError("недопустимая строка подсветки")
            if why := guard(line):
                raise ActionError(why)
        link.new_action()
        gen = link._gen
        context = (gen, link._stop_epoch, state["plan_epoch"])
        for line in lines:
            if context != (link._gen, link._stop_epoch, state["plan_epoch"]):
                raise ActionError("контекст подсветки изменился; автоматическое снятие запрещено")
            ok, reply = await link.send(line, gen=gen)
            if context != (link._gen, link._stop_epoch, state["plan_epoch"]):
                raise ActionError("контекст подсветки изменился; результат неизвестен")
            if not ok:
                if link.last and link.last.get("status") == "unknown":
                    link.close()  # reopen the session; never retry an uncertain line here
                raise ActionError(reply.strip() or "ошибка пульта")

    async def release_highlight(reason, manual_token=None):
        """Caller holds action_lock; only the recorded zone and known panel values may leave here."""
        if highlight["state"] == "idle":
            return
        try:
            manual = manual_token is not None
            if not manual and highlight.get("context") is not None and highlight["context"] != (link._gen, link._stop_epoch, state["plan_epoch"]):
                raise ActionError("контекст прежней подсветки устарел; требуется ручное подтверждение")
            if manual and (highlight["state"] != "stuck" or manual_token != highlight.get("release_token")):
                raise ActionError("подтверждение снятия подсветки устарело; подтвердите текущее предупреждение")
            if highlight.get("restore_invalid") and not manual:
                raise ActionError("подсветка устарела: автоматические Off и восстановление запрещены; проверьте Programmer на MA2")
            current = state["show"]["name"]
            if current and highlight.get("show") and current != highlight["show"]:
                raise ActionError("на пульте другое шоу: подсветка не снята")
            zone = highlight.get("zone", [])
            if not zone or any(type(fid) is not int for fid in zone):  # the recorded zone, even if the plan changed since: guard still checks every line
                raise ActionError("зона подсветки в highlight.json повреждена")
            lines = [select_line(zone), "Off " + select_line(zone)]
            for fid in zone:
                values = {} if manual else highlight.get("restore", {}).get(fid, {})
                if "dim" in values:
                    lines += [select_line([fid])] + build({"a": "dim", "v": values["dim"]}, cfg)
                color_mode = find(cfg["fixtures"], fid).get("color", cfg["attrs"].get("color", {}).get("mode", "rgb"))
                if "rgb" in values and color_mode != "none":
                    color_lines, _ = lines_for("color", dict(a="color", **dict(zip(("r", "g", "b"), values["rgb"]))), {}, [fid])
                    lines += color_lines
                attrs = {k: v for k, v in values.items() if k in ("pan", "tilt", "zoom", "focus")}
                if attrs:
                    lines += head_lines({fid: attrs}, cfg)
                if "strobe" in values:  # the attribute and range of the fixture's type (spec 24), like the slider
                    lines += lines_for("strobe", {"a": "strobe", "v": values["strobe"]}, {}, [fid])[0]
            await highlight_lines(lines)
            highlight_path.unlink(missing_ok=True)
        except (ActionError, OSError, ValueError) as e:
            highlight_stuck(str(e))
            highlight_record(reason, str(e))
            raise ActionError(str(e)) from e
        if "restore" not in highlight:
            reason += ": прежние значения панели неизвестны и не восстановлены"
            log.warning("Подсветка снята после запуска: %s", reason)
        highlight.clear()
        highlight.update(state="idle", owner=None)
        highlight_record(reason)
        await broadcast(status_msg())

    async def highlight_action(ws, action):
        a, s = action["a"], sessions[ws]
        if rdm.active and a != "highlight_off":  # light must not queue behind the search's lock (spec «Изоляция RDM»)
            raise ActionError("идёт поиск RDM; подсветка сейчас недоступна")
        await throttle.flush_all()
        async with action_lock:
            if state["loading"]:
                raise ActionError("идёт загрузка шоу")
            if a == "edit_begin":
                s["editing"] = True
            elif a == "edit_end":
                s["editing"] = False
                if highlight.get("owner") is ws:
                    await release_highlight(a)
            else:
                owner = highlight.get("owner")
                if owner is not None and owner is not ws:
                    raise ActionError("подсветкой управляет другое устройство")
                if a == "highlight_off":
                    await release_highlight(a, action.get("release_token"))
                elif a == "highlight_ping":
                    if highlight["state"] != "active" or owner is not ws or not s.get("editing"):
                        raise ActionError("нет активной подсветки этой вкладки")
                    highlight["ping"] = time.monotonic()
                else:
                    if safety["allow_highlight"] is not True:
                        raise ActionError("подсветка заблокирована: allow_highlight")
                    if not s.get("editing"):
                        raise ActionError("подсветка доступна только в редакторе плана")
                    if highlight["state"] == "stuck":
                        raise ActionError("Подсветка не снята: сначала снимите подсветку")
                    zone = highlight.get("zone") if highlight["state"] == "active" else highlight_zone()
                    fid = action.get("id")
                    if not zone or type(fid) is not int or fid not in zone:
                        raise ActionError("прибор вне зоны подсветки или зона пуста")
                    level = settings.get("highlight", {}).get("level", 100)
                    at = build({"a": "dim", "v": level}, cfg)
                    first = highlight["state"] == "idle"
                    old = [i for i in zone if i != fid] if first else [highlight["target"]]
                    lines = ([select_line(old), "At 0"] if old else []) + [select_line([fid])] + at
                    # Persist before the very first dimming line; also keep the current target on changes.
                    saved = {"show": state["show"]["name"] or cfg.get("show"), "zone": zone, "target": fid, "t": time.time()}
                    save_config(str(highlight_path), saved)
                    if first:
                        # only what the panel itself sent: a default shown for display (dim 100 after a colour) is not restored
                        highlight.update(context=(link._gen, link._stop_epoch, state["plan_epoch"]), restore={i: {k: v for k, v in known_shown().get(i, {}).items()
                                                      if k in state["sent"].get(i, ())} for i in zone})
                    highlight.update(saved, state="active", owner=ws, ping=time.monotonic())
                    try:
                        await highlight_lines(lines)
                    except ActionError as e:
                        highlight_stuck(str(e))
                        raise
            await broadcast(status_msg())
        return {"ok": True, "a": a}

    async def highlight_disconnect(ws):
        async with action_lock:
            if highlight.get("owner") is ws:
                try:
                    await release_highlight("disconnect")
                except ActionError:
                    pass
                highlight["owner"] = None

    async def highlight_lease():
        while True:
            await asyncio.sleep(.5)
            async with action_lock:
                if highlight["state"] == "active" and time.monotonic() - highlight["ping"] > settings.get("highlight", {}).get("lease_s", 10):
                    try:
                        await release_highlight("lease")
                    except ActionError:
                        pass

    def show_from(reply):
        try:
            match = re.search(ma2["showfile_regex"], reply)
            name = match[1].strip() if match else ""
            return {"name": name, "source": "ma2"} if name else {"name": None, "source": "unknown"}
        except (re.error, IndexError, TypeError):
            log.warning("имя шоу не распознано: проверьте ma2.showfile_regex")
            return {"name": None, "source": "unknown"}

    def invalidate_profiles():
        state["no_attr"] = {}
        # Keep operator maps for recovery, but never use them as evidence of this context.
        state["dmx"], state["live"] = {}, {}
        value_evidence.invalidate(["live"])
        for f in cfg["fixtures"]:
            f.pop("footprint", None)
        saved = cfg.setdefault("dmx_map_saved", {}) if cfg.get("dmx_map") else {}
        for k, v in cfg.get("dmx_map", {}).items():
            if not v.get("stale"):
                versions = saved.setdefault(k, [])
                if isinstance(versions, dict):  # earlier plans may hold one saved map
                    versions = saved[k] = [versions]
                if v not in versions:
                    versions.append(dict(v))
        if "dmx_map" in cfg:
            cfg["dmx_map"] = {k: {**v, "stale": True} for k, v in cfg["dmx_map"].items()}
        types_tried.clear()
        type_retries.clear()
        state.pop("dmx_retry", None)
        state.pop("types_context", None)

    def update_show(show):
        if state["show"].get("name") != show.get("name"):
            if highlight["state"] != "idle":
                highlight_stuck("изменился контекст шоу")
            invalidate_profiles()
            state["plan_epoch"] += 1
            invalidate_scene_offers()
            invalidate_evidence()
            state["master"] = None
            state["read_freshness"] = dict.fromkeys(("fixtures", "ma2", "scenes"), False)
        state["show"] = show
        if history:
            spawn_broadcast(history_msg())

    async def identify_show(recover=False, reply=None):
        async with action_lock:
            ok, reply = (True, reply) if reply else await link.send("ListVar")
            if ok:
                update_show(show_from(reply))
            else:
                update_show({"name": None, "source": "unknown"})
            if recover and highlight["state"] != "idle":
                # Never on its own at start or reconnect: "Off Fixture <zone>" also wipes what the operator set by hand
                # in the programmer since (hall 2026-10-21). The operator removes it with the banner button.
                highlight.update(state="stuck", reason="осталась после перезапуска или обрыва связи")
        await broadcast(status_msg())
        poll_wake.set()

    # ---- raw replies for the hall (owner 2026-10-22): main() turns this on, tests and --mock do not ------------------

    captured = {"file": None, "start": False, "execs": set()}

    async def capture_replies(cmds, title):
        """Read-only lines whose reply format the code still guesses; replies go to field-data/auto/ and diag.zip."""
        out = [f"## {title} {time.strftime('%H:%M:%S')}, пульт: {link.state}"]
        async with action_lock:
            for cmd in cmds:
                if not link.ready:
                    out.append("(связь пропала)")
                    break
                ok, reply = await link.send(cmd, quiet=True)
                out.append(f"### {cmd}  (ok={ok})\n{reply!r}")
        folder = HERE / "field-data" / "auto"
        try:  # a full or read-only disk loses the capture, never the bridge
            folder.mkdir(parents=True, exist_ok=True)
            captured["file"] = captured["file"] or folder / f"{time.strftime('%Y%m%d-%H%M%S')}.txt"
            with captured["file"].open("a", encoding="utf-8") as f:
                f.write(mask("\n".join(out)) + "\n\n")
            for old in sorted(folder.glob("*.txt"))[:-20]:
                old.unlink()
        except OSError as e:
            log.warning("ответы пульта не записаны в field-data/auto: %s", e)

    def spawn_capture(cmds, title):
        task = asyncio.create_task(capture_replies(cmds, title))
        bg.add(task)
        task.add_done_callback(bg.discard)

    def on_state(new):
        invalidate_profiles()
        invalidate_scene_offers()
        if new in READY and capture and not captured["start"]:  # once per run: a reconnect does not repeat it
            captured["start"] = True
            execs = sorted({sc["exec"] for sc in cfg.get("scenes", []) if isinstance(sc.get("exec"), str)})[:10]
            spawn_capture([*PROBE_COMMANDS, "ListShows", *(f"List Executor {e}" for e in execs)], "старт моста")
        if new in READY:
            task = asyncio.create_task(identify_show(recover=True, reply=link.listvar))
            bg.add(task)
            task.add_done_callback(bg.discard)
            return
        invalidate_evidence()
        state["show"] = {"name": None, "source": "unknown"}
        spawn_broadcast(history_msg())
        state["master"] = None
        state["read_freshness"] = dict.fromkeys(("fixtures", "ma2", "scenes"), False)
        if highlight["state"] == "active":
            highlight_stuck("нет связи с пультом")
        if new not in READY:
            forget_positions()
            spawn_broadcast(shown_msg())
            throttle.clear()  # old movements must not reach the console after it comes back
            for s in sessions.values():
                s["base"] = None
        spawn_broadcast(status_msg())

    # ---- what a tab may do in this mode -------------------------------------------------------------------------

    def blocked(a):
        """Reason an action is refused in the current mode, else None. link.guard repeats this for every line."""
        if rdm.active and a not in ("rdm_stop", "rdm_check"):
            # The search owns the desk; light/patch/show operations must not queue behind its lock (spec «Изоляция RDM»).
            return "идёт поиск RDM; свет, патч, Identify и файлы шоу сейчас недоступны (RDM)"
        if a in ('show_load', 'show_save') and state.get('show_file_active'):
            return 'выполняется операция файла шоу; дождитесь результата'
        if a == "store_scene":
            return "перезапись существующей сцены отключена: запишите новую сцену в пустой executor"
        feature = {"move_start": "move", "nudge": "move", "jog": "move", "aim": "move", "preset_go": "move", "preset_save": "move",
                   "scene_go": "scenes", "scene_off": "scenes", "blackout": "scenes",
                   "scene_slot_find": "store", "scene_create": "store", "store_scene": "store"}.get(a, a)
        value = features.get(feature, True)
        if value is False:
            return f"функция «{feature}» отключена в настройках (features.{feature})"
        if isinstance(value, str):
            return f"функция «{feature}» заблокирована: {value}"
        if mode == "full":
            return None
        if a in ("store_scene", "scene_create", "scene_slot_find") and mode == "store":
            return None
        if a in ("store_scene", "scene_create", "scene_slot_find", "scene_rename", "page_save"):
            return f"запись в пульт и служебные действия заблокированы в режиме {mode}"
        if a == "master" and not safety["allow_master"]:
            return "общая яркость (Master 2.1) заблокирована: allow_master в settings.json"
        if a == "page_go" and not safety["allow_page_change"]:
            return "смена страницы пульта заблокирована: allow_page_change в settings.json"
        return None

    def check_ids(ids):
        if mode == "full":
            return
        bad = [i for i in ids if i not in allowed_fixtures]
        if bad:
            raise ActionError(f"прибор {bad[0]} не разрешён: впишите его в allowed_fixtures (settings.json)")

    def check_scene(ex):
        if mode != "full" and str(ex) not in allowed_scenes:
            raise ActionError(f"сцена {ex} не разрешена: впишите её в allowed_scenes (settings.json)")

    def heads(s, ids=None):
        found = movers(s["selection"] if ids is None else ids, cfg)
        if not found:
            raise ActionError("нет подвижных приборов: отметьте головы в «Зале» (Расстановка, кнопка «Голова»)")
        return found

    def selected(s):
        if not s["selection"]:
            raise ActionError("ничего не выбрано")
        check_ids(s["selection"])
        return list(s["selection"])

    def remember(a, action, ids, values, s):
        if a == "master":
            state["master"] = float(action["v"])
            sent_evidence.observe("master", state["master"])
        elif a == "preset_go":
            s["selection"], s["base"] = list(values), None
        elif a in ("dim", "color"):
            for fid in ids:
                if a == "color" and find(cfg["fixtures"], fid).get("color", cfg["attrs"].get("color", {}).get("mode", "rgb")) == "none":
                    continue
                entry = state["shown"].setdefault(fid, {})  # may already hold pan/tilt from movement
                state["sent"].setdefault(fid, set()).add("dim" if a == "dim" else "rgb")
                if a == "dim":
                    entry["dim"] = float(action["v"])
                else:
                    entry["rgb"] = [action["r"], action["g"], action["b"]]
                attr = "dim" if a == "dim" else "rgb"
                sent_evidence.observe(f"sent:{fid}:{attr}", entry[attr])
            state["tracked"] = True
        elif a == "blackout":
            state["shown"] = {}
        elif a == "scene_go":  # the line starts with ClearAll: nothing the panel sent is on the desk any more
            forget_positions()
            state["shown"], state["tracked"] = {}, False
        elif a == "page_go":
            state["page"] = action["n"]
        for fid, v in values.items():
            state["shown"].setdefault(fid, {}).update(v)
            state["sent"].setdefault(fid, set()).update(v)
            for attr, value in v.items():
                sent_evidence.observe(f"sent:{fid}:{attr}", value)

    def lines_for(a, action, s, ids):
        """MA2 lines for the action and the head values they set: {id: {attr: 0-100}}.

        Every value line sits behind an explicit `Fixture` line built from ids: the console's own selection is never relied on.
        """
        if a == "move":
            if sent_evidence.clock() >= s.get("base_expires", float("inf")):
                s["base"] = None
            if s["base"] is None:
                raise ActionError("нет move_start")
            values = apply_move(s["base"], *check_move(action))
            check_ids(values)
            return head_lines(values, cfg), values
        if a in ("nudge", "jog"):
            if a == "nudge":
                ids = heads(s, selected(s))
                build(action, cfg)  # checks attr, dir and step
                deltas = {action["attr"]: action["dir"] * nudge_step(action, cfg)}
            else:
                deltas = dict(zip(("pan", "tilt"), check_jog(action)))
            check_ids(ids)
            if type(action.get("mirror", False)) is not bool:
                raise ActionError("mirror: true или false")
            mirror = mirrored(ids, cfg) if action.get("mirror") else set()
            values = {}
            for fid in ids:  # a known position follows the step, so the plan's beam keeps up
                shown, f = known_shown().get(fid, {}), find(cfg["fixtures"], fid)
                flip = {"pan": pan_flip(f, mirror), "tilt": f.get("flip_tilt") is True}
                if "pan" in shown and "tilt" in shown:
                    values[fid] = {attr: min(100, max(0, shown[attr] + (-d if flip[attr] else d) * 100 /
                                                      (cfg["attrs"][attr]["max"] - cfg["attrs"][attr]["min"]))) for attr, d in deltas.items()}
            s["base"] = None
            return rel_lines(ids, deltas, cfg, mirror), values
        if a == "aim":
            ids = heads(s, selected(s))
            check_ids(ids)
            lines = build(action, cfg)
            values = {fid: {attr: (action[attr] - cfg["attrs"][attr]["min"]) * 100 /
                           (cfg["attrs"][attr]["max"] - cfg["attrs"][attr]["min"]) for attr in ("pan", "tilt") if attr in action} for fid in ids}
            s["base"] = None
            return [select_line(ids)] + lines, values
        if a == "color":
            check_ids(ids)
            spec = cfg["attrs"].get("color", {})
            lines = []
            for color_mode in ("rgb", "cmy"):
                group = [fid for fid in ids if find(cfg["fixtures"], fid).get("color", spec.get("mode", "rgb")) == color_mode]
                if group:
                    color_cfg = {**cfg, "attrs": {**cfg["attrs"], "color": {**spec, "mode": color_mode}}}
                    lines.extend([select_line(group)] + build(action, color_cfg))
            if not lines:
                raise ActionError("у выбранных приборов нет управляемого цвета (color: none)")
            return lines, {}
        if a in ("zoom", "focus"):
            ids = heads(s, ids)
            check_ids(ids)
            return [select_line(ids)] + build(action, cfg), {fid: {a: float(action["v"])} for fid in ids}
        if a == "strobe":  # any selected fixture, not only heads
            check_ids(ids)
            v = action.get("v")
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 100:
                raise ActionError("v: нужно число 0-100")
            groups, lines, values = {}, [], {}
            for fid in ids:
                kind = find(cfg["fixtures"], fid).get("type")
                groups.setdefault(kind, []).append(fid)
            for kind, group in groups.items():
                profile = cfg.get("dmx_map", {}).get(kind, {})
                spec = profile.get("strobe") if not profile.get("stale") and not profile.get("unsupported") else None
                if not isinstance(spec, dict) or not all(isinstance(spec.get(k), (int, float)) for k in ("open", "from", "to")) \
                        or not re.fullmatch(r"[A-Za-z0-9_]+", str(spec.get("attr", ""))):
                    continue  # unread type, or a hand-edited entry without its range
                value = spec["open"] if v == 0 else spec["from"] + (spec["to"] - spec["from"]) * (v - 1) / 99
                lines.extend([select_line(group), f'Attribute "{spec["attr"]}" At {round(value, 1):g}'])
                values.update({fid: {a: float(v)} for fid in group})
            if not lines:
                raise ActionError("у выбранных приборов нет стробоскопа (тип не прочитан или без Strobe)")
            return lines, values
        if a in ("dim", "color"):
            check_ids(ids)
            return [select_line(ids)] + build(action, cfg), {}
        if a == "restore_pos":  # undo only: not a panel action (not in FULL)
            values = action["pos"]
            check_ids(values)
            return head_lines(values, cfg), values
        if a == "preset_go":
            preset = find(cfg.get("presets", []), action.get("id"))
            present = {f["id"] for f in cfg["fixtures"] if not f.get("missing")}
            values = {int(k): v for k, v in preset["pos"].items() if int(k) in present}
            if not values:
                raise ActionError("в пульте нет приборов пресета")
            check_ids(values)  # the whole preset or nothing: no silent subset
            return head_lines(values, cfg), values
        if a in ("scene_go", "scene_off"):
            scene = find(cfg["scenes"], action.get("id"))
            if a == "scene_go" and scene.get("write_error"):
                raise ActionError("запись сцены не подтверждена: проверьте её в редакторе")
            check_scene(scene["exec"])
        if a == "blackout":
            # Off for the panel's scenes, then dimmer 0 for every fixture of the plan: a plan without scenes (a new show)
            # or light set from the panel / programmer used to stay on (hall 2026-10-21). Undo: Oops on the desk.
            lines = [f"Off Executor {sc['exec']}" for sc in cfg["scenes"] if mode == "full" or str(sc["exec"]) in allowed_scenes]
            dark = [f["id"] for f in cfg["fixtures"] if not f.get("missing") and not f.get("service") and (mode == "full" or f["id"] in allowed_fixtures)]
            if dark:
                lines += [select_line(dark), "At 0"]
            if not lines:
                raise ActionError("нечего гасить: в плане нет сцен и приборов (или они не разрешены в settings.json)")
            return lines, {fid: {"dim": 0.0} for fid in dark}
        return build(action, {**cfg, "master": settings.get("master", cfg.get("master", {"cmd": "Master 2.1 At {v}"}))}), {}

    def action_ticket(ws):
        return (ws, sessions.get(ws), state["plan_epoch"], link._gen, link._stop_epoch)

    def ticket_valid(ticket):
        ws, session, epoch, gen, stop = ticket
        return (session is not None and sessions.get(ws) is session
                and (epoch, gen, stop) == (state["plan_epoch"], link._gen, link._stop_epoch))

    async def execute(a, action, s, ids, log_history=True, scene_ticket=None, expected_context=None, inverse=None, stages=None, inverse_times=None, expected_basis=None, ticket=None):
        """Send the action's lines; None on success, else the error text."""
        async with action_lock:
            if ticket is not None and not ticket_valid(ticket):
                return "устаревшее действие клиента"
            if expected_basis and any(sent_evidence.clock() - stamp >= 6 for stamp in expected_basis.values()):
                return "прежние отправленные значения устарели"
            if expected_context is not None and expected_context != history_context():
                return "изменилось шоу, план или соединение"
            if state["loading"]:
                return "идёт загрузка шоу"
            before = {fid: dict(v) for fid, v in known_shown().items()} if (log_history and a in HISTORY_LIGHT) or inverse is not None else None
            basis_times = {f"sent:{fid}:{attr}": sent_evidence.records[f"sent:{fid}:{attr}"][1]
                           for fid, values_before in (before or {}).items() for attr in values_before
                           if f"sent:{fid}:{attr}" in sent_evidence.records}
            if scene_ticket is not None:
                sid = action["id"]
                if scene_ticket != (state["plan_epoch"], scene_revision.get(sid, 0), link._gen, link._stop_epoch):
                    return "устаревший переход сцены"
            link.new_action()
            gen = link._gen  # a drop and reconnect in the middle must not let the second half of the lines through
            stop_epoch = link._stop_epoch
            try:
                lines, values = lines_for(a, action, s, ids)
            except ActionError as e:
                return str(e)
            # A newer mutation owns the light even when its result is partial/unknown.
            # Do not let a later release wipe it with either Off Fixture or saved At.
            if highlight["state"] != "idle" and a in HISTORY_LIGHT | {"restore_pos", "scene_go", "scene_off", "blackout", "clear", "master"}:
                highlight_stuck("новое действие со светом; прежнее снятие подсветки запрещено")
            # Invalidate before the first send: even a partially failed newer action owns the scene.
            if a in ("scene_go", "scene_off", "blackout"):
                touched = ({sc["id"] for sc in cfg["scenes"]} if a == "blackout" else
                           {action["id"], *action.get("swap", [])})
                for sid in touched:
                    scene_revision[sid] = scene_revision.get(sid, 0) + 1
                scene_evidence.invalidate(touched)
                spawn_broadcast(scenes_msg())
            selected_ids = []
            for line in lines:
                if ticket is not None and not ticket_valid(ticket):
                    return "устаревшее действие клиента"
                if expected_basis and any(sent_evidence.clock() - stamp >= 6 for stamp in expected_basis.values()):
                    return "прежние отправленные значения устарели"
                if expected_context is not None and expected_context != history_context():
                    return "изменилось шоу, план или соединение"
                ok, reply = await link.send(line, gen=gen)
                if stages is not None:
                    last = link.last or {}
                    stages.append({"cmd": line, "status": last.get("status") if last.get("cmd") == line else "sent" if ok else "error"})
                if gen != link._gen:
                    invalidate_evidence()
                    return "соединение изменилось во время операции"
                if not ok:
                    for session in sessions.values():
                        session["base"] = None
                    await broadcast(shown_msg())
                    if a in ("zoom", "focus", "strobe") and "#14" in reply:
                        return no_attribute(a, ids)
                    return reply.strip() or "ошибка пульта"
                if line == "ClearAll":
                    # Even if the subsequent Go fails, this programmer is no longer
                    # a usable basis. Output readback is independent of ClearAll.
                    state["shown"], state["sent"], state["tracked"] = {}, {}, False
                    sent_evidence.invalidate([k for k in sent_evidence.records if k.startswith("sent:")])
                    for session in sessions.values():
                        session["base"] = None
                elif re.fullmatch(r"Fixture \d+(?: \+ \d+)*", line):
                    selected_ids = [int(fid) for fid in line[8:].split(" + ")]
                elif a in HISTORY_LIGHT or a == "restore_pos":
                    # A successful prefix must never leave the previous complete value
                    # available to replay if a later line fails. RGB is indivisible.
                    attrs = (["rgb"] if a == "color" else [a] if a in ("dim", "zoom", "focus", "strobe") else
                             [k for k in ("pan", "tilt", "zoom", "focus", "strobe")
                              if line.startswith(cfg["attrs"][k]["cmd"].split("{v}")[0])])
                    for fid in selected_ids:
                        for attr in attrs:
                            state["shown"].get(fid, {}).pop(attr, None)
                            state["sent"].get(fid, set()).discard(attr)
                            sent_evidence.invalidate([f"sent:{fid}:{attr}"])
            remember(a, action, ids, values, s)
            if a == "scene_go" and action.get("swap"):
                # A reconnect may reach READY before identify_show has acquired this lock.
                tickets = {sid: (state["plan_epoch"], scene_revision.get(sid, 0), gen, stop_epoch)
                           for sid in action["swap"] if sid != action["id"]}
                if (op := operation.get()) and op["id"] is not None:
                    op.update(retain=True, deferred=True, stage="transition")
                task = asyncio.create_task(swap_off(tickets, action.get("fade") or 0, s))
                bg.add(task)
                task.add_done_callback(bg.discard)
            if a in ("scene_go", "scene_off", "blackout"):
                poll_wake.set()
            if before is not None:
                changed = light_diff(before)
                if inverse is not None:
                    for fid, values_before in changed.items():
                        for attr, value in values_before.items():
                            inverse.setdefault(fid, {}).setdefault(attr, value)
                            if inverse_times is not None:
                                key = f"sent:{fid}:{attr}"
                                inverse_times.setdefault(key, basis_times[key])
                else:
                    times = {f"sent:{fid}:{attr}": basis_times[f"sent:{fid}:{attr}"] for fid, v in changed.items() for attr in v}
                    add_history(a, light_what(a, action, changed or values or ids), "light", changed, changed or values or ids, basis_times=times)
        await broadcast(shown_msg())
        return None

    def no_attribute(a, ids):
        """Error #14 OBJECT DOES NOT EXIST on Zoom/Focus/Strobe: this fixture type has no such attribute on this console.
        Learned per type until restart, so the panel greys the slider instead of failing on every move."""
        kinds = {find(cfg["fixtures"], fid).get("type") for fid in ids}
        known = state["no_attr"].setdefault(a, [])
        if len(kinds) == 1 and None not in kinds and not kinds <= set(known):  # a mixed selection proves nothing per type
            known.append(kinds.pop())
            spawn_broadcast(status_msg())
        name = re.search(r'Attribute "([^"]+)"', cfg["attrs"][a]["cmd"])
        return (f"у выбранных приборов на пульте нет атрибута «{name[1] if name else a}» (MA2: Error #14). "
                f"Имя атрибута меняется в настройках: attrs.{a}.cmd")

    async def swap_off(tickets, seconds, s):
        await asyncio.sleep(seconds)
        err = None
        for sid, ticket in tickets.items():
            err = await execute("scene_off", {"a": "scene_off", "id": sid}, s, [], scene_ticket=ticket)
            if err == "устаревший переход сцены":
                err = None  # only this scene was superseded; independent tickets remain valid
                continue
            if err:
                break
        if op := operation.get():
            await finish_operation(op, {"ok": not bool(err), **({"err": err} if err else {})})

    async def throttled(key, intent):
        ws = intent["ws"]
        op = intent.get("operation")
        if ws not in sessions or (op and op.get("finished")):
            if op:
                await finish_operation(op, {"ok": False, "err": "клиент отключён"})
            return
        token = operation.set(op)
        if op:
            op["stage"] = "running"
        try:
            err = await execute(intent["a"], intent["action"], sessions[ws], intent["ids"], ticket=intent["ticket"])
            reply = {"ok": not bool(err), "a": intent["a"], **({"err": err} if err else {})}
            if op and (err or not op.get("deferred")):
                if op["id"] is None and err and ws in clients:
                    await ws.send_json(reply)
                await finish_operation(op, reply)
            elif err and ws in clients:
                await ws.send_json(reply)
        except asyncio.CancelledError:
            if op:
                op["evidence"].append("unknown")
            raise
        finally:
            operation.reset(token)

    def fade_starts(a, ids):
        """[(start, ids)] for a fade the bridge plays itself, or None when a start is unknown (then the desk's Fade).
        hall 2026-10-21: `At V Fade T` is accepted by MA2 but the programmer value jumps."""
        key = "dim" if a == "dim" else "rgb"
        known = known_shown()
        if not ids or state["tracked"] is False or any(key not in known.get(fid, {}) for fid in ids):
            return None
        groups = {}
        for fid in ids:
            groups.setdefault(json.dumps(known[fid][key]), []).append(fid)
        return [(json.loads(k), v) for k, v in groups.items()]

    async def play_fade(key, ws, a, action, starts, ticket):
        """Values from each start to the target, one per throttle tick; the throttle sends them like a slider."""
        target = action["v"] if a == "dim" else [action["r"], action["g"], action["b"]]
        steps = max(1, round(action["fade"] * rate_hz))
        plain = {k: v for k, v in action.items() if k != "fade"}
        op = operation.get()
        if op:
            op.update(retain=True, deferred=True, stage="fade")
        cancelled = True
        try:
            for i in range(1, steps + 1):
                await asyncio.sleep(action["fade"] / steps)
                if not ticket_valid(ticket) or (op and op.get("finished")):
                    return
                t = i / steps
                for n, (start, ids) in enumerate(starts):
                    if a == "dim":
                        value = {"v": round(start + (target - start) * t, 1)}
                    else:
                        value = dict(zip("rgb", (round(s0 + (s1 - s0) * t, 1) for s0, s1 in zip(start, target))))
                    throttle.put(f"{key}:{n}", {"ws": ws, "a": a, "action": {**plain, **value}, "ids": ids, "operation": op, "ticket": ticket})
            for n in range(len(starts)):
                await throttle.flush(f"{key}:{n}")
            cancelled = False
        finally:
            if op and not op.get("finished"):
                await finish_operation(op, {"ok": not cancelled, **({"err": "плавный переход прерван"} if cancelled else {})})
            if throttle.fades.get(key) is asyncio.current_task():
                del throttle.fades[key]

    def layout_save(action):
        pos = parse_positions(action, cfg)
        fixtures = [f if f["id"] not in pos else
                    {k: v for k, v in f.items() if k not in ("x", "y")} if pos[f["id"]] is None else
                    {**f, "x": pos[f["id"]][0], "y": pos[f["id"]][1]}
                    for f in cfg["fixtures"]]
        save_config(config_path, {**cfg, "attrs": original_attrs, "fixtures": fixtures})
        cfg["fixtures"] = fixtures

    def new_id(items, prefix):
        nums = [int(i["id"][1:]) for i in items if re.fullmatch(prefix + r"\d+", str(i["id"]))]
        return f"{prefix}{max(nums, default=0) + 1}"

    def mover(action):
        fixture = find(cfg["fixtures"], action.get("id"))
        if not can_move(fixture):
            raise ActionError("прибор не двигается")
        return fixture, {"home": 50, "invert": False, **fixture.get("beam", {})}

    def config_edit(a, action, s):
        """New values for the changed config keys; raises ActionError before anything changes."""
        presets, groups, fixtures = cfg.get("presets", []), cfg["groups"], cfg["fixtures"]
        if a == "preset_save":
            label = parse_label(action)
            pos = {}
            for fid in heads(s):
                shown = known_shown().get(fid, {})
                if "pan" not in shown or "tilt" not in shown:
                    raise ActionError("сначала наведите головы")
                pos[str(fid)] = {"pan": shown["pan"], "tilt": shown["tilt"]}
            old = next((p for p in presets if p["label"] == label), None)
            entry = {"id": old["id"] if old else new_id(presets, "p"), "label": label, "pos": pos}
            return {"presets": [entry if p is old else p for p in presets] + ([] if old else [entry])}
        if a == "preset_delete":
            preset = find(presets, action.get("id"))
            return {"presets": [p for p in presets if p is not preset]}
        if a == "group_save":
            label = parse_label(action)
            build({"a": "select_fixtures", "ids": action.get("ids")}, cfg)  # same checks as a selection
            return {"groups": groups + [{"id": new_id(groups, "g"), "label": label, "fixtures": list(action["ids"])}]}
        if a == "rdm_link":  # the operator's own match of an RDM device to a plan fixture; uid null forgets it
            f = next((x for x in fixtures if x["id"] == action.get("id")), None)
            if f is None:
                raise ActionError("нет такого прибора")
            if action.get("uid") is None:
                return {"fixtures": [{k: v for k, v in x.items() if k != "rdm"} if x is f else x for x in fixtures]}
            uid = check_uid(action["uid"])
            if any((x.get("rdm") or {}).get("uid") == uid for x in fixtures if x is not f):
                raise ActionError(f"UID {uid} уже связан с другим прибором")
            seen = next((d for d in (state["rdm"] or {}).get("devices", []) if d["uid"] == uid), {})
            fp = action.get("footprint", seen.get("footprint"))
            if fp is not None and (type(fp) is not int or not 1 <= fp <= 512):
                raise ActionError("footprint: целое 1-512")
            rdm = {"uid": uid, **({"footprint": fp, "footprint_from": "RdmList" if "footprint" not in action else "оператор"} if fp else {}),
                   **({"address": seen["address"]} if "address" in seen else {})}
            return {"fixtures": [{**x, "rdm": rdm} if x is f else x for x in fixtures]}
        if a == "dmx_map":  # channel numbers of one fixture type, for the plan's read-back; {} forgets them
            kind = action.get("type")
            if not any(f.get("type") == kind for f in fixtures):
                raise ActionError("нет приборов такого типа")
            spec = check_dmx_map(action.get("map"))
            maps = {k: v for k, v in cfg.get("dmx_map", {}).items() if k != kind}
            return {"dmx_map": {**maps, kind: spec} if spec else maps}
        if a == "group_delete" and "n" in action:  # an imported MA2 group: forgotten by the panel, the desk keeps it
            n = page_number(action)
            ma2groups = cfg.get("ma2groups", [])
            if not any(g["n"] == n for g in ma2groups):
                raise ActionError("группа не импортирована из MA2")
            return {"ma2groups": [g for g in ma2groups if g["n"] != n]}
        if a == "group_delete":
            group = find(groups, action.get("id"))
            if "n" in group:
                raise ActionError("группа из пульта")
            return {"groups": [g for g in groups if g is not group]}
        fixture, beam = mover(action)
        if a == "beam_home":
            pan = known_shown().get(fixture["id"], {}).get("pan")
            if pan is None:
                raise ActionError("сначала наведите голову")
            beam["home"] = pan
        else:
            beam["invert"] = not beam["invert"]
        return {"fixtures": [{**f, "beam": beam} if f is fixture else f for f in fixtures]}

    def scene_pages():
        return sorted({exec_page(s["exec"]) for s in cfg["scenes"]} | {p["n"] for p in cfg.get("pages", [])} | {1})

    def list_cmd(page, top=250):
        return ma2.get("list_cmd", "List Executor {page}.1 Thru {page}.{top}").format(page=page, top=top)

    async def list_execs(page, context):
        """onPC 3.9.60 answers "List Executor 1.1 Thru 1.250" with Error #9: NUMBER TOO LARGE (hall 2026-10-18).
        A smaller accepted range is diagnostic evidence, never proof of complete coverage."""
        top = 250
        while True:
            require_scene_context(context)
            cmd = list_cmd(page, top)
            ok, reply = await link.send(cmd, gen=context[0])
            require_scene_context(context)
            lower = [n for n in (200, 128, 100, 90, 60, 30, 15) if n < top]
            if ok or "too large" not in reply.lower() or not lower:
                if ok and top < 250:
                    raise ActionError(f"List Executor {page}: охват не подтверждён после уменьшения диапазона до {top}; "
                                      "сцены не импортированы. Нужна проверка адресов на MA2; сырой ответ — в Диагностике")
                return ok, reply
            if list_cmd(page, lower[0]) == cmd:
                return False, f"{reply.strip()}\nma2.list_cmd не меняет диапазон при уменьшении top; повторный запрос не отправлен"
            log.warning("List Executor до %s: пульт ответил NUMBER TOO LARGE, пробую до %s", top, lower[0])
            top = lower[0]

    async def poll_running():
        """One shared reader. Exact configured addresses avoid guessed range boundaries."""
        while True:
            try:
                try:
                    await asyncio.wait_for(poll_wake.wait(), timeout=poll_seconds)
                except asyncio.TimeoutError:
                    pass
                poll_wake.clear()
                if state["loading"] or not link.ready or action_lock.locked():
                    continue
                async with action_lock:
                    epoch, gen = state["plan_epoch"], link._gen
                    ok, reply = await link.send("ListVar", quiet=True)
                    if gen != link._gen or epoch != state["plan_epoch"] or not link.ready:
                        continue
                    if not ok:
                        continue
                    update_show(show_from(reply))
                    epoch = state["plan_epoch"]
                    spawn_broadcast(status_msg())
                    if cfg.get("show") and cfg["show"] != state["show"].get("name"):
                        continue
                    scenes = [(sc["id"], str(sc["exec"])) for sc in cfg["scenes"]]
                for sid, ex in scenes:
                    # Yield between reads: user actions acquire the same lock first.
                    await asyncio.sleep(0)
                    if action_lock.locked():
                        break
                    async with action_lock:
                        if (epoch != state["plan_epoch"] or gen != link._gen
                                or state["loading"] or not link.ready):
                            break
                        ok, reply = await link.send(f"List Executor {ex}", quiet=True)
                        if epoch != state["plan_epoch"] or gen != link._gen or not link.ready:
                            break
                        parsed = parse_running(reply) if ok and not is_error_reply(reply) else {}
                        if ex in parsed:
                            scene_evidence.observe(sid, parsed[ex])
                        else:
                            scene_evidence.invalidate([sid])
                        spawn_broadcast(scenes_msg())
            except Exception:
                log.exception("чтение статусов сцен не удалось")
                await asyncio.sleep(poll_seconds)

    async def expire_evidence():
        last = (scenes_msg(), values_meta(), history_msg())
        while True:
            await asyncio.sleep(.5)
            dmx_changed = expire_dmx()
            scenes = scenes_msg()
            meta = values_meta()
            if meta["live"]["freshness"] != "fresh":
                state["live"], state["dmx"] = {}, {}
            signature = (scenes, meta, history_msg())
            if signature != last or dmx_changed:
                last = signature
                await broadcast({**scenes, **shown_msg(), **history_msg(), "dmx": {} if not state["dmx"] else {
                    f["id"]: [state["dmx"].get(a + i) for i in range(f.get("footprint") or 0)]
                    for f in cfg["fixtures"] if (a := absolute(f.get("address")))}})

    async def poll_dmx():
        """What the desk outputs, read by Lua chunks with dmx_seconds idle time per sweep: the plan shows every lit fixture, not only the panel's.
        Needs allow_fixture_read; read only (getdmx). Failed reads back off; refusals have a bounded retry budget."""
        wait = dmx_seconds
        while True:
            await asyncio.sleep(wait)
            try:
                wait = await read_dmx()
            except Exception:  # one bad reply must not end the read-back until restart
                log.exception("чтение DMX не удалось")
                wait = 30

    dmx_cycle = {"key": None, "index": 0, "initial": True, "seen": {}, "started": None, "seconds": None}

    def expire_dmx():
        before = dict(state["dmx"])
        key = (state["plan_epoch"], link._gen, tuple(dmx_intervals(cfg["fixtures"])))
        if dmx_cycle["key"] != key:
            dmx_cycle.update(key=key, index=0, initial=True, seen={}, started=None, seconds=None)
            state["dmx"] = {}
        now = time.monotonic()
        for a in list(state["dmx"]):
            if now - dmx_cycle["seen"].get(a, 0) >= 6:
                state["dmx"].pop(a, None)
                dmx_cycle["seen"].pop(a, None)
        changed = before != state["dmx"]
        if changed:
            state["live"] = live_from_dmx(cfg["fixtures"], state["dmx"], cfg.get("dmx_map", {}))
        return changed

    async def read_dmx():
        """One read; refusals back off and stop sending after READ_ATTEMPTS until a context reset."""
        if expire_dmx():
            await broadcast(shown_msg())
        if safety["allow_fixture_read"] is not True or state["loading"] or not link.ready or action_lock.locked():
            return dmx_seconds
        epoch, gen = state["plan_epoch"], link._gen
        try:
            state["background_type_read"] = True
            await read_types(max_types=1, background=True)
        except ActionError:
            return dmx_seconds
        finally:
            state["background_type_read"] = False
        if epoch != state["plan_epoch"] or gen != link._gen or not link.ready:
            return dmx_seconds
        retry = state.get("dmx_retry")
        if retry is None or retry["context"] != (epoch, gen):
            retry = state["dmx_retry"] = {"context": (epoch, gen), "failures": 0, "after": 0}
        if retry["failures"] >= READ_ATTEMPTS or time.monotonic() < retry["after"]:
            return READ_RETRY_S
        intervals = dmx_intervals(cfg["fixtures"])
        if not intervals:
            return dmx_seconds
        key = (epoch, gen, tuple(intervals))
        if dmx_cycle["key"] != key:
            dmx_cycle.update(key=key, index=0, initial=True, seen={}, started=None, seconds=None)
            # A new show (even with identical addresses) must not inherit old output.
            state["dmx"] = {}
            state["live"] = {}
        chunks = [(a, min(DMX_CHUNK, start + count - a))
                  for start, count in intervals for a in range(start, start + count, DMX_CHUNK)]
        span = chunks[dmx_cycle["index"]]
        pause = dmx_seconds / len(chunks)
        nonce = uuid.uuid4().hex[:16]
        lines = ([DMX_CANARY.format(a=span[0])] if dmx_cycle["initial"] else []) + dmx_lua(*span, nonce=nonce)
        export_extra.update(lines)
        replies, refused, dmx, listvar = [], False, {}, ""
        try:
            async with action_lock:
                if epoch != state["plan_epoch"] or gen != link._gen or state["loading"] or not link.ready:
                    return dmx_seconds
                sampled_at = time.monotonic()
                if dmx_cycle["index"] == 0:
                    if dmx_cycle["started"] is not None:
                        dmx_cycle["seconds"] = sampled_at - dmx_cycle["started"]
                    dmx_cycle["started"] = sampled_at
                dmx_cycle["initial"] = False
                dmx_cycle["index"] = (dmx_cycle["index"] + 1) % len(chunks)
                for line in lines:
                    ok, text = await link.send(line, quiet=True, gen=gen)
                    replies.append(" ".join(text.split())[-300:])
                    refused = refused or is_error_reply(text)
                    if not ok:
                        break
            if not refused and ok:
                # Lua can finish after Telnet's reply. Let manual actions use the link during that wait.
                await asyncio.sleep(.2)
                async with action_lock:
                    if epoch != state["plan_epoch"] or gen != link._gen or state["loading"] or not link.ready:
                        return dmx_seconds
                    ok, listvar = await link.send("ListVar", quiet=True, gen=gen)
                    # ListVar retains other chunks indefinitely; only this chunk is evidence for this poll.
                    dmx = parse_dmx(listvar, span=span, nonce=nonce) if ok else {}
        finally:
            export_extra.difference_update(lines)
        if epoch != state["plan_epoch"] or gen != link._gen or state["loading"] or not link.ready:
            return dmx_seconds
        now = time.monotonic()
        sample_age = now - sampled_at
        if sample_age >= 6:
            dmx = {}
        panel_vars = " | ".join(ln.strip()[:200] for ln in listvar.splitlines() if "$PANEL" in ln)
        state["dmx_read"] = {"t": time.strftime("%H:%M:%S"), "span": span, "values": len(dmx),
                             "chunks": len(chunks), "pause_seconds": pause,
                             "read_seconds": sample_age, "cycle_seconds": dmx_cycle["seconds"],
                             "reason": "ответ DMX старше 6 с" if sample_age >= 6 else "" if len(dmx) == span[1] else "неполный или недостоверный ответ DMX: маркер, диапазон или байты",
                             "reply": " || ".join(replies) + " || ListVar: " + (panel_vars or "нет $PANELDMX")}
        if refused:
            retry["failures"] += 1
            retry["after"] = time.monotonic() + READ_RETRY_S
            dmx_cycle["initial"] = True
            if retry["failures"] >= READ_ATTEMPTS:
                state["dmx_read"]["reason"] = "MA2 отказал в чтении DMX трижды; переподключитесь или получите приборы заново"
                log.warning("чтение DMX приостановлено после трёх отказов MA2; ответ в диагностике")
            else:
                state["dmx_read"]["reason"] = "MA2 отказал в чтении DMX; следующая попытка не раньше чем через 30 с"
            return READ_RETRY_S
        # Missing/unreadable channels cease to be evidence. Other chunks age independently.
        for a in list(state["dmx"]):
            if span[0] <= a < span[0] + span[1] or now - dmx_cycle["seen"].get(a, 0) >= 6:
                state["dmx"].pop(a, None)
                dmx_cycle["seen"].pop(a, None)
        dmx_cycle["seen"].update({a: sampled_at for a in dmx})
        state["dmx_read"]["max_age_seconds"] = max((now - t for t in dmx_cycle["seen"].values()), default=None)
        state["dmx"].update(dmx)
        if not dmx:
            state["live"] = live_from_dmx(cfg["fixtures"], state["dmx"], cfg.get("dmx_map", {}))
            await broadcast({"live": state["live"], "values_meta": values_meta()})
            return 30
        value_evidence.observe("live", True)
        retry.update(failures=0, after=0)
        dmx = state["dmx"]
        live = live_from_dmx(cfg["fixtures"], dmx, cfg.get("dmx_map", {}))
        state["live"] = live
        await broadcast({"live": live, "values_meta": values_meta()})
        await broadcast({"dmx": {f["id"]: [dmx.get(a + i) for i in range(f.get("footprint") or 0)]
                                 for f in cfg["fixtures"] if (a := absolute(f.get("address")))}})
        return pause

    def require_scene_context(context):
        if context != offer_context() or not link.ready or state["loading"]:
            state["read_freshness"]["scenes"] = False
            raise ActionError("чтение сцен отменено: изменилось соединение, шоу или план; повторите чтение явно")

    async def confirm_scene_show(context):
        require_scene_context(context)
        ok, reply = await link.send("ListVar", gen=context[0])
        require_scene_context(context)
        name = show_from(reply)["name"] if ok else None
        if not name or name != context[2] or (context[3] and name != context[3]):
            state["read_freshness"]["scenes"] = False
            raise ActionError("чтение сцен отменено: имя шоу не подтверждено или изменилось; повторите чтение явно")

    async def read_scenes(context=None):
        """Existing scenes_import reader; caller holds action_lock and saves atomically."""
        context = offer_context() if context is None else context
        state["read_freshness"]["scenes"] = False
        await broadcast(status_msg())
        await confirm_scene_show(context)
        scenes = list(cfg["scenes"])
        incoming = []
        added = 0
        unrecognised = 0
        # Pages that hold objects on the desk, not only those the plan already knows: hall 2026-10-18 `List Page` shows
        # "Page  2 2    Page         (7)" for a page with 7 objects. ponytail: only the count column is trusted.
        ok, reply = await link.send("List Page", gen=context[0])
        require_scene_context(context)
        filled = {int(m[1]) for m in re.finditer(r"(?m)^Page\s+(\d+)\s.*\(\d+\)\s*$", reply)} if ok else set()
        if not ok or not filled:
            reason = " ".join(reply.split())[:200] or "ответ не распознан"
            raise ActionError(f"List Page: список страниц не подтверждён ({reason}); план не изменён, повторите импорт вручную")
        for page in sorted(set(scene_pages()) | filled):
            ok, reply = await list_execs(page, context)
            if not ok:
                raise ActionError(reply.strip() or "ошибка пульта")
            unrecognised += unrecognised_lines(reply)
            incoming.extend(parse_executors(reply))
        scenes, added = merge_scenes(scenes, incoming)
        await confirm_scene_show(context)
        return scenes, added, unrecognised

    async def read_ma2():
        """Read all three pools under action_lock; raw replies also stay in link diagnostics."""
        result = {"groups": [], "colors": [], "positions": [], "raw": {}}
        gen = link._gen
        requests = [("groups", ma2["list_group_cmd"], "group_regex", None)]
        for kind, pool in (("color", "colors"), ("position", "positions")):
            typ = ma2["preset_types"][kind]
            requests.append((pool, ma2["list_preset_cmd"].format(type=typ), "preset_regex", typ))
        for pool, cmd, regex, typ in requests:
            ok, reply = await link.send(cmd, gen=gen)
            result["raw"][pool] = reply
            if not ok:
                return {**result, "ok": False, "err": reply.strip() or "ошибка пульта"}
            result[pool] = parse_ma2_objects(reply, ma2[regex], typ)
        result["ok"] = any(result[pool] for pool in ("groups", "colors", "positions"))
        if not result["ok"]:
            result["err"] = "ответ MA2 не распознан: сырой ответ в Диагностике"
        return result

    async def send_ma2_lines(lines, gen):
        # Preflight the whole operation so a bad store template cannot first change selection.
        for line in lines:
            if why := guard(line):
                raise ActionError(f"заблокировано защитой: {why}")
        for line in lines:
            ok, reply = await link.send(line, gen=gen)
            if not ok:
                raise ActionError(reply.strip() or "ошибка пульта")

    async def ma2_action(a, action, s):
        async with action_lock:
            if state["loading"]:
                raise ActionError("идёт загрузка шоу")
            link.new_action()
            gen = link._gen
            scene_context = offer_context()
            if a in ("ma2_read", "ma2_import"):
                if a == "ma2_import":
                    nums = action.get("groups", [])
                    if not isinstance(nums, list) or any(type(n) is not int or not 1 <= n <= 999 for n in nums):
                        raise ActionError("groups: нужен список номеров 1-999")
                    if any(type(action.get(k, False)) is not bool for k in ("colors", "positions", "scenes")):
                        raise ActionError("colors, positions, scenes: требуется bool")
                result = await read_ma2()
                state["read_freshness"]["ma2"] = bool(result["ok"])
                await broadcast(status_msg())
                if a == "ma2_read" or not result["ok"]:
                    return {**result, "a": a}
                if set(nums) - {g["n"] for g in result["groups"]}:
                    raise ActionError("выбранная группа не найдена в MA2")
                presets = cfg.get("ma2presets", {})
                groups = [g for g in result["groups"] if g["n"] in nums]
                if any(not g.get("ids") for g in groups):
                    try:
                        listed = {g["n"]: g["name"] for g in result["groups"]}
                        members = await export_once(ma2["group_export_cmd"], "group", lambda text, file: parse_group_export(text, listed), "group_export_trace.json")
                        groups = [{**g, "ids": members[g["n"]]} if members.get(g["n"]) else g for g in groups]
                    except (ActionError, ValueError) as e:
                        result["members_err"] = f"состав групп не прочитан: {e}"
                changes = {
                    "ma2groups": groups,
                    "ma2presets": {pool: result[pool] if action.get(pool, False) else presets.get(pool, [])
                                   for pool in ("colors", "positions")},
                }
                if action.get("scenes", False):
                    scenes, added, unrecognised = await read_scenes(scene_context)
                    require_scene_context(scene_context)
                    changes["scenes"] = scenes
                    result.update(added=added, unrecognised=unrecognised)
                save_config(config_path, {**cfg, "attrs": original_attrs, **changes})
                cfg.update(changes)
                if action.get("scenes", False):
                    state["read_freshness"]["scenes"] = unrecognised == 0
                    await broadcast(status_msg())
            elif a == "ma2_group_go":
                n = page_number(action)
                group = next((g for g in cfg.get("ma2groups", []) if g["n"] == n), None)
                if group is None:
                    raise ActionError("группа не импортирована из MA2")
                ids = group.get("ids", [])
                if not ids:  # Group n would select fixtures the panel cannot see or check
                    raise ActionError("состав группы MA2 не прочитан: выберите приборы в панели")
                check_ids(ids)
                if any(find(cfg["fixtures"], fid).get("missing") for fid in ids):
                    raise ActionError("приборов группы нет в шоу")
                await send_ma2_lines([ma2["group_go_cmd"].format(n=n)], gen)
                s["selection"], s["base"] = list(ids), None
                result = {"ok": True, "a": a}
            elif a == "ma2_preset_go":
                n, kind = page_number(action), action.get("type")
                if kind not in ("color", "position"):
                    raise ActionError("type: требуется color или position")
                if why := blocked("color" if kind == "color" else "move"):
                    raise ActionError(why)
                pool = "colors" if kind == "color" else "positions"
                if not any(p["n"] == n for p in cfg.get("ma2presets", {}).get(pool, [])):
                    raise ActionError("пресет не импортирован из MA2")
                ids = selected(s)
                if any(find(cfg["fixtures"], fid).get("missing") for fid in ids):
                    raise ActionError("выбранного прибора нет в шоу")
                if highlight["state"] != "idle":
                    highlight_stuck("новый пресет MA2; прежнее снятие подсветки запрещено")
                await send_ma2_lines([select_line(ids), ma2["preset_go_cmd"].format(type=ma2["preset_types"][kind], n=n)], gen)
                # A named preset gives no numerical feedback; forget only affected values.
                for fid in ids:
                    for key in (("rgb",) if kind == "color" else ("pan", "tilt")):
                        state["shown"].get(fid, {}).pop(key, None)
                if kind == "position":
                    forget_positions()
                result = {"ok": True, "a": a}
            else:  # group_store_ma2: the safety flag is mandatory even in full mode.
                if safety["allow_group_store"] is not True:
                    raise ActionError("запись группы заблокирована: allow_group_store")
                n = page_number(action)
                if type(action.get("confirm")) is not int or action["confirm"] != n:
                    raise ActionError("confirm должен совпасть с номером группы")
                group = find(cfg["groups"], action.get("id"))
                ids = targets({"a": "select_fixtures", "ids": group["fixtures"]}, cfg)
                check_ids(ids)
                if any(find(cfg["fixtures"], fid).get("missing") for fid in ids):
                    raise ActionError("приборов группы нет в шоу")
                name = group["label"]
                if not isinstance(name, str) or not name.strip() or re.search(r'[";\x00-\x1f\x7f-\x9f]', name):
                    raise ActionError("небезопасное имя группы")
                lines = [select_line(ids), ma2["group_store_cmd"].format(n=n, name=name)]
                for line in lines:
                    if why := guard(line):
                        raise ActionError(f"заблокировано защитой: {why}")
                ok, reply = await link.send(f"List Group {n}", gen=gen)
                if not ok or not group_slot_empty(reply, n, ma2["group_regex"], ma2["group_empty_regex"]):
                    raise ActionError("группа занята или ответ не распознан: запись отменена; сырой ответ в Диагностике")
                await send_ma2_lines(lines, gen)
                result = {"ok": True, "a": a}
        if a == "ma2_import":
            await broadcast(config_msg())
        if a == "ma2_preset_go":
            await broadcast(shown_msg())
        return {**result, "a": a}

    def invalidate_scene_offers():
        for session in sessions.values():
            session.pop("scene_offer", None)
            if job := session.get("scene_search"):
                job["cancelled"] = True

    def offer_context():
        return (link._gen, state["plan_epoch"], state["show"].get("name"), cfg.get("show"))

    async def find_scene_slot(ws, job):
        session = sessions.get(ws)
        candidates = slot_candidates(mode, store_execs, {sc["exec"] for sc in cfg["scenes"]})[:250]
        context = offer_context()
        deadline = time.monotonic() + 30
        async def emit(kind, **values):
            if ws in clients:
                try:
                    await ws.send_json({"scene_slot": {"request": job["request"], "state": kind,
                                                      "checked": job["checked"], "total": len(candidates), **values}})
                except (WebSocketDisconnect, RuntimeError):
                    job["cancelled"] = True
        try:
            await emit("searching")
            for ex in candidates:
                if job["cancelled"] or sessions.get(ws) is not session:
                    return
                if time.monotonic() >= deadline:
                    raise ActionError("поиск занял слишком много времени; запись не выполнялась")
                async with action_lock:
                    if job["cancelled"]:
                        return
                    if offer_context() != context or not link.ready or link.halted or state["loading"]:
                        raise ActionError("связь или шоу изменились; выполните поиск заново")
                    if why := blocked("scene_slot_find"):
                        raise ActionError(why)
                    # A concurrent scene write can occupy a slot while this search yielded.
                    if ex in {sc["exec"] for sc in cfg["scenes"]}:
                        continue
                    ok, reply = await link.send(f"List Executor {ex}", gen=context[0])
                    if not ok:
                        raise ActionError(reply.strip() or "проверка места не удалась")
                    verdict, reason = exec_verdict(reply, ex, empty_re)
                    job["checked"] += 1
                    if verdict == "empty":
                        if job["cancelled"] or offer_context() != context or sessions.get(ws) is not session:
                            return
                        token = token_urlsafe(24)
                        session["scene_offer"] = {"token": token, "exec": ex, "context": context,
                                                  "expires": time.monotonic() + 60, "request": job["request"]}
                        await emit("ready", exec=ex, token=token)
                        return
                    if verdict != "occupied":
                        raise ActionError(reason)
                await emit("searching")
                await asyncio.sleep(0)
            raise ActionError("свободное место не найдено в разрешённом диапазоне")
        except (ActionError, OSError, ValueError) as error:
            if not job["cancelled"]:
                await emit("error", err=str(error))
        finally:
            if session and session.get("scene_search") is job:
                session.pop("scene_search", None)

    async def store_checked(ex, action, gen=None):
        """Check fresh console data while the caller holds action_lock, in every write mode."""
        if str(action.get("confirm")) != ex:
            raise ActionError("запись не подтверждена: confirm должен совпасть с номером executor")
        if mode == "store" and ex not in store_execs:
            raise ActionError(f"{ex} не входит в store_execs (settings.json)")
        ok, reply = await link.send(f"List Executor {ex}", gen=gen)
        if not ok:
            if reply.startswith("результат неизвестен"):
                raise ActionError("проверка места не удалась: пульт не ответил вовремя — запись отменена")
            raise ActionError(reply.strip() or "ошибка пульта")
        verdict, reason = exec_verdict(reply, ex, empty_re)
        if verdict != "empty":
            raise ActionError(reason)

    def record(ws, text, reply):
        try:
            action = json.loads(text)
        except ValueError:
            return
        if reply is None or not isinstance(action, dict):
            return
        what = {k: v for k, v in action.items() if k in ("id", "ids", "label", "on", "n", "name", "confirm", "hall", "service", "moves", "rot", "same_type", "fade", "swap", "type", "groups", "colors", "positions", "scenes")}
        entry = {"t": time.strftime("%H:%M:%S"), "ip": ws.client.host if ws.client else "?", "a": action.get("a"),
                 "what": what, "ok": reply.get("ok", False), "err": reply.get("err")}
        journal.append(entry)
        log.info("action %s", json.dumps(entry, ensure_ascii=False))

    def show_name(action):
        name = action.get("name")
        if not isinstance(name, str) or not name.strip() or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in name) or '"' in name:
            raise ActionError("нужно имя шоу без кавычек и управляющих символов")
        return name

    def plan_path(name, write=False):
        return show_plan_path(Path(config_path).parent / "shows", name, write=write)

    def check_show():
        current, bound = state["show"]["name"], cfg.get("show")
        if not current and not bound:
            raise ActionError("привяжите план к шоу")
        if current and bound and current != bound:
            raise ActionError("на пульте другое шоу, откройте его план")

    def import_context():
        return (state["plan_epoch"], state["show"]["name"], link._gen, config_revision())

    def import_xml(xml_text, source, file=None):
        # Each prepare replaces the previous request, even when parsing fails.
        state.pop("pending_import", None)
        no_id = []
        found = parse_export(xml_text, no_id)
        diag = Path(config_path).parent / "diag"
        diag.mkdir(exist_ok=True)
        (diag / "last_export.xml").write_text(xml_text, encoding="utf-8")
        fixtures = merge_fixtures(cfg["fixtures"], found)
        ambiguous = [{"new_id": f["id"], "label": f.get("label", f"#{f['id']}"), "candidates": f["ambiguous_candidates"]}
                     for f in fixtures if "ambiguous_candidates" in f]
        if ambiguous:
            token = uuid.uuid4().hex
            state["pending_import"] = {"source": source, "file": file, "found": found,
                                       "no_id": no_id, "request_token": token, "context": import_context()}
            return {"ok": False, "ambiguous": ambiguous, "request_token": token,
                    "err": "Неоднозначная перепривязка: подтвердите выбор", "no_id": no_id[:50]}
        invalidate_profiles()
        return commit_import(fixtures, found, source, file, no_id)

    def confirm_import(action):
        # Caller holds action_lock. A request cannot cross plan/show/config changes.
        pending = state.get("pending_import")
        if not pending or action.get("request_token") != pending["request_token"]:
            raise ActionError("импорт устарел: получите приборы заново")
        if state["loading"] or pending["context"] != import_context():
            state.pop("pending_import", None)
            raise ActionError("план или шоу изменились: получите приборы заново")
        check_show()
        if "choices" not in action or action["choices"] is None:
            raise ActionError("нужен явный выбор для каждого прибора")
        fixtures = merge_fixtures(cfg["fixtures"], pending["found"], choices=action["choices"])
        invalidate_profiles()
        return commit_import(fixtures, pending["found"], pending["source"], pending["file"], pending["no_id"])

    def commit_import(fixtures, found, source, file, no_id):
        moved = {f.pop("repatched_from"): f["id"] for f in fixtures if "repatched_from" in f}
        for f in fixtures:
            f.pop("ambiguous_candidates", None)  # clean up if any remain
        old_ids = {f["id"] for f in cfg["fixtures"]} | set(moved.values())  # a re-patched fixture is not new
        groups = [{**g, "fixtures": [moved.get(i, i) for i in g["fixtures"]]} if "n" not in g else g for g in cfg["groups"]]
        changes = {"fixtures": fixtures, "groups": groups, "fixtures_read": {"t": time.strftime("%Y-%m-%d %H:%M:%S"), "source": source, "count": len(found)}}
        # An unbound plan takes the console's show name, so a later show switch saves it instead of dropping it.
        if not cfg.get("show") and state["show"]["name"]:
            changes["show"] = state["show"]["name"]
        save_config(config_path, {**cfg, "attrs": original_attrs, **changes})
        cfg.update(changes)
        state.pop("pending_import", None)
        if file:
            state["export_file"] = file
        state["read_freshness"]["fixtures"] = source == "ma2"
        spawn_broadcast(status_msg())
        return {"ok": True, "added": sum(f["id"] not in old_ids for f in fixtures),
                "missing": sum(bool(f.get("missing")) for f in fixtures), "total": len(fixtures), "source": source, "file": file,
                "no_id": no_id[:50]}

    async def open_show_plan(name):
        nonlocal original_attrs
        if highlight["state"] != "idle":  # no Off on a plan switch: it would wipe what the operator set on the desk
            highlight_stuck("план переключён")
        target = plan_path(name, write=False)
        if cfg.get("show"):
            old = plan_path(cfg["show"], write=True)
            old.parent.mkdir(exist_ok=True)
            save_config(str(old), {**cfg, "attrs": original_attrs})
        if target.exists():
            target = plan_path(name)  # resolve again after saving this same show
            loaded = json.loads(target.read_text(encoding="utf-8-sig"))
            if not isinstance(loaded, dict) or loaded.get("show") != name or any(not isinstance(loaded.get(k), list) for k in ("fixtures", "groups", "scenes", "presets")):
                raise ActionError("неверный файл плана шоу")
        else:
            loaded = {**cfg, "attrs": original_attrs, "fixtures": [], "groups": [], "ma2groups": [], "ma2presets": {"colors": [], "positions": []},
                      "scenes": [], "presets": [], "pages": {}, "show": name}
        version = loaded.get("version", 3)
        if type(version) is not int or not 1 <= version <= 5:
            raise ActionError("неподдерживаемая версия плана шоу")
        # Site settings belong to this installation, never to an archived show.
        loaded = {k: v for k, v in loaded.items() if k not in SITE_KEYS}
        loaded["version"] = 5
        save_config(config_path, loaded)
        original_attrs = loaded.get("attrs", {})
        state["plan_epoch"] += 1
        invalidate_scene_offers()
        cfg.clear()
        cfg.update(loaded)
        invalidate_profiles()
        cfg["scenes"] = ordered_scenes(cfg["scenes"], cfg.get("scene_order_version") == 1)
        cfg["scene_order_version"] = 1
        cfg["attrs"] = {k: {**original_attrs.get(k, {}), **settings.get("attrs", {}).get(k, {})}
                        for k in original_attrs.keys() | settings.get("attrs", {}).keys()}
        refresh_attr_names()
        throttle.clear()
        for session in sessions.values():
            session["selection"], session["base"] = [], None
        state["master"] = None
        state["read_freshness"] = dict.fromkeys(("fixtures", "ma2", "scenes"), False)
        state["shown"], state["sent"] = {}, {}
        state["tracked"], state["page"] = True, None
        spawn_broadcast(history_msg())
        invalidate_evidence()
        await broadcast(scenes_msg())

    async def follow_desk_show():
        """Caller holds action_lock. A show made or loaded on the desk since: read its name now and move to its plan,
        so what is read from the desk lands there. Returns the name moved to, or None."""
        listed, listvar = await link.send("ListVar") if link.ready else (False, "")
        if listed and show_from(listvar)["name"]:
            update_show(show_from(listvar))
        current = state["show"]["name"]
        if current and cfg.get("show") and current != cfg["show"]:
            await open_show_plan(current)
            return current
        return None

    def plan_copy(action):
        """Placement and marks from another show's plan for fixtures with the same number here. Nothing goes to MA2:
        a fixture missing from this show's patch is skipped (the panel never patches)."""
        source = show_name({"name": action.get("from")})
        path = plan_path(source)
        if source == cfg.get("show") or not path.exists():
            raise ActionError(f"нет плана шоу «{source}»")
        other = json.loads(path.read_text(encoding="utf-8-sig"))
        if other.get("show") != source:
            raise ActionError("файл плана принадлежит другому шоу")
        ids = action.get("ids") or []
        if not isinstance(ids, list) or any(type(i) is not int for i in ids):
            raise ActionError("ids: список номеров приборов")
        theirs = {f["id"]: f for f in other.get("fixtures", []) if isinstance(f, dict) and type(f.get("id")) is int}
        keys = ("x", "y", "label", "moves", "moves_auto", "service", "rot", "beam", "flip_pan", "flip_tilt", "color")
        fixtures, copied = [], 0
        for f in cfg["fixtures"]:
            if f["id"] in theirs and (not ids or f["id"] in ids):
                f = {**{k: v for k, v in f.items() if k not in keys}, **{k: v for k, v in theirs[f["id"]].items() if k in keys}}
                copied += 1
            fixtures.append(f)
        here = {f["id"] for f in fixtures}
        groups = list(cfg["groups"])
        for g in other.get("groups", []):
            members = [i for i in g.get("fixtures", []) if i in here and (not ids or i in ids)]
            if "n" not in g and members and g.get("label") not in {x.get("label") for x in groups}:
                groups.append({"id": new_id(groups, "g"), "label": g.get("label", "группа"), "fixtures": members})
        skipped = [i for i in (ids or theirs) if i not in here]
        return {"fixtures": fixtures, "groups": groups}, copied, len(groups) - len(cfg["groups"]), skipped

    async def fetch_fixtures(validate=lambda: None, applied=lambda: None):
        if not link.ready:  # before the show check: a dropped link also forgets the show name, which would hide the real cause
            raise ActionError(f"{NO_LINK}: проверьте вход на странице диагностики")
        check_show()
        validate()
        def apply(text, file):
            validate()
            result = import_xml(text, "ma2", file)
            applied()  # synchronous import can bind an unbound plan to the confirmed show
            return result
        result = await export_once(ma2["export_cmd"], "fixture", apply, "export_trace.json", gen=link._gen, validate=validate)
        validate()
        if result.get("ok"):
            await read_types(force=True, validate=validate)
            validate()
        return result

    async def read_types(force=False, max_types=None, validate=lambda: None, background=False):
        """Channel numbers (dim, r, g, b) of every fixture type of the plan, from one Export FixtureType per type: the
        fixture export names no attributes. Foreground caller holds action_lock; background locks only sends. Best effort: a failure leaves the plan without colours
        and is logged; failed reads have a bounded retry budget per context."""
        validate()
        epoch, gen = state["plan_epoch"], link._gen
        refresh = force or state.get("types_context") != (epoch, gen)
        if refresh:
            invalidate_profiles()
        if state.get("types_context") != (epoch, gen):
            types_tried.clear()
            state["types_context"] = (epoch, gen)
        if background:
            original_validate = validate
            context = (epoch, gen, link._stop_epoch, config_revision())

            def validate():
                original_validate()
                if (context != (state["plan_epoch"], link._gen, link._stop_epoch, config_revision())
                        or not link.ready or link.halted or state["loading"] or rdm.active or updating()):
                    raise ActionError("фоновое чтение типа отменено: контекст изменился")

        async def send(line, **kwargs):
            if background:
                async with action_lock:
                    validate()
                    return await link.send(line, **kwargs)
            return await link.send(line, **kwargs)

        maps, changed = dict(cfg.get("dmx_map", {})), refresh

        def can_retry(kind):
            attempts, after = type_retries.get(kind, (0, 0))
            return attempts < READ_ATTEMPTS and time.monotonic() >= after

        def failed(kind):
            attempts = type_retries.get(kind, (0, 0))[0] + 1
            type_retries[kind] = (attempts, time.monotonic() + READ_RETRY_S)

        attempted = 0
        for kind in sorted({f.get("type") or "" for f in cfg["fixtures"] if not f.get("missing")}):
            m = re.match(r"(\d+) ", kind)
            if not m or (not force and ("has" in maps.get(kind, {}) and not maps[kind].get("stale") or kind in types_tried or not can_retry(kind))):
                continue
            if max_types is not None and attempted >= max_types:
                break
            attempted += 1
            try:
                validate()
                spec = await export_type(int(m[1]), gen=gen, validate=validate, send=send)
                validate()
            except (ActionError, OSError, ValueError, ET.ParseError) as e:
                validate()
                if epoch != state["plan_epoch"] or gen != link._gen:
                    return
                failed(kind)
                log.warning("каналы типа «%s» не прочитаны: %s", kind, e)
                break  # the same folder or refusal for the next type: each try holds the desk for up to export_wait
            if epoch != state["plan_epoch"] or gen != link._gen:
                return
            types_tried.add(kind)
            type_retries.pop(kind, None)
            if spec and maps.get(kind) != spec:
                maps[kind], changed = spec, True
        fixtures = cfg["fixtures"]
        if force or " list" not in types_tried and can_retry(" list") and any(type_no(f.get("type")) and "footprint" not in f for f in fixtures if not f.get("missing")):
            validate()
            ok, reply = await send("List FixtureType", quiet=True, gen=gen)
            validate()
            if epoch != state["plan_epoch"] or gen != link._gen:
                return
            sizes = parse_type_footprints(reply) if ok else {}
            if sizes:
                types_tried.add(" list")
                type_retries.pop(" list", None)
            else:
                failed(" list")
            new = [{**f, "footprint": sizes[type_no(f.get("type"))]} if type_no(f.get("type")) in sizes and not maps.get(f.get("type"), {}).get("unsupported") else f for f in fixtures]
            if new != fixtures:
                fixtures, changed = new, True
        def commit():
            validate()
            if changed:
                save_config(config_path, {**cfg, "attrs": original_attrs, "dmx_map": maps, "fixtures": fixtures})
                cfg.update(dmx_map=maps, fixtures=fixtures)
                add_strobe_attrs(maps)

        if background:
            async with action_lock:
                commit()
        else:
            commit()
        if changed:
            await broadcast(config_msg())

    def require_patch_context(context):
        if context != (*offer_context(), link._stop_epoch) or not link.ready or link.halted or state["loading"]:
            raise ActionError("контекст патча изменился: соединение, шоу, план или остановка; подготовьте новый план вручную")

    async def send_planned(line, context=None):
        """One write line of a confirmed patch/RDM plan: the guard lets out exactly this line, once."""
        export_extra.add(line)
        try:
            if context is not None:
                require_patch_context(context)
            if highlight["state"] != "idle":
                highlight_stuck("запись патча/RDM; прежнее снятие подсветки запрещено")
            previous = link.admission
            if context is not None:
                def admission():
                    require_patch_context(context)
                    return previous()
                link.admission = admission
            try:
                ok, reply = await link.send(line, gen=context[0] if context is not None else None)
            finally:
                link.admission = previous
        finally:
            export_extra.discard(line)
        return ok and not is_error_reply(reply), " ".join(reply.split())[:400]

    async def rdm_read(uid=None, context=None):
        if context is not None:
            require_patch_context(context)
        ok, reply = await link.send("RdmList" + (f" / UID = {uid}" if uid else ""), gen=context[0] if context is not None else None)
        if context is not None:
            require_patch_context(context)
        if not ok:
            raise ActionError(f"RdmList не выполнен: {' '.join(reply.split())[:200] or 'ошибка пульта'}")
        lines = [ln for ln in reply.splitlines() if ln.strip()][:400]
        devices = parse_rdm_list(reply)
        if not uid:
            state["rdm"] = {"t": time.strftime("%H:%M:%S"), "lines": lines, "devices": devices, "format": "uids" if devices else "unverified"}
            await broadcast({"rdm": state["rdm"]})
        return devices, lines

    def patch_offer(action):
        plan = patch_plan(cfg["fixtures"], action.get("id"), parse_address(action.get("address")),
                          action.get("patch") is True, action.get("physical") is True)
        context = (bridge_epoch, *offer_context(), link._stop_epoch)
        plan["token"] = uuid.uuid5(uuid.NAMESPACE_OID, repr((context, plan["token"]))).hex
        return plan

    async def patch_action(a, action):
        """Раздел «Патч» (spec 21). Every write needs its flag, a fresh plan token and the action lock; nothing is
        retried after a failure or a timeout, and both sides are read back after a write."""
        if a == "patch_plan":
            return {"ok": True, "a": a, "plan": patch_offer(action),
                    "rows": patch_rows(cfg["fixtures"])}
        if safety["allow_rdm" if a != "patch_apply" else "allow_patch"] is not True and (a != "patch_apply" or action.get("patch") is True):
            raise ActionError("заблокировано: " + ("allow_patch" if a == "patch_apply" else "allow_rdm") + " в настройках")
        if a == "patch_apply" and action.get("physical") is True and safety["allow_rdm"] is not True:
            raise ActionError("заблокировано: allow_rdm в настройках")
        if not link.ready:
            raise ActionError(NO_LINK)
        if a == "patch_apply":
            check_show()  # fixture numbers of this plan must not land in another show's patch
        context = (*offer_context(), link._stop_epoch)
        async with action_lock:
            require_patch_context(context)
            if a == "patch_apply":
                check_show()
            if a == "rdm_list":
                devices, lines = await rdm_read()
                return {"ok": True, "a": a, "devices": len(devices), "format": "uids" if devices else "unverified",
                        "note": "Формат ответа не подтверждён; отсутствие UID не доказывает отсутствие устройств. Выключите RDM на пульте, если он больше не нужен"}
            if a == "rdm_identify":
                uid = check_uid(action.get("uid"))
                on = action.get("on")
                if type(on) is not bool:
                    raise ActionError("Identify: on должен быть true/false")
                line = f"RdmSetParameter identify_device {1 if on else 0} / UID = {uid}"
                outcome = "unknown"
                try:
                    ok, reply = await send_planned(line, context)
                    last = link.last or {}
                    outcome = (last.get("status") if last.get("cmd") == line else None) or ("sent" if ok else "error")
                    require_patch_context(context)
                    if not ok:
                        raise ActionError(f"Identify не выполнен: {reply or 'нет ответа'}")
                    return {"ok": True, "a": a, "reply": reply, "status": "sent", "verified": False}
                except ActionError:
                    if context != (*offer_context(), link._stop_epoch):
                        outcome = "unknown"
                    raise
                finally:
                    add_history(a, f"RDM Identify {uid} · {'On' if on else 'Off'} · {outcome} (физическое состояние не подтверждено)")
            plan = patch_offer(action)
            if action.get("token") != plan["token"]:
                raise ActionError("план устарел: данные патча изменились, постройте план заново")
            if plan["conflicts"] and action.get("accept_conflicts") is not True:
                raise ActionError(f"пересечение с приборами {', '.join(map(str, plan['conflicts']))}: подтвердите явно")
            steps, fid = [], plan["id"]
            context_error = None
            for line in plan["lines"]:
                try:
                    ok, reply = await send_planned(line, context)
                except ActionError as e:
                    context_error = str(e)
                    break
                last = link.last or {}
                step_status = last.get("status") if last.get("cmd") == line else ("sent" if ok else "error")
                steps.append({"line": line, "ok": ok, "reply": reply, "status": step_status})
                try:
                    require_patch_context(context)
                except ActionError as e:
                    context_error = str(e)
                    break
                if not ok:
                    break  # no blind retry: the next line would act on an unknown state
            done = [st["line"] for st in steps if st["ok"]]
            check, observed, verified_sides = {}, set(), set()
            def applied():
                nonlocal context
                context = (*context[:3], cfg.get("show"), context[4])
            try:  # never apply readback from another operation context
                require_patch_context(context)
                if plan["physical"] and steps:
                    # Once attempted, the old address is no longer current evidence.
                    for fixture in cfg["fixtures"]:
                        if fixture["id"] == fid:
                            fixture["rdm"].pop("address", None)
                    save_config(config_path, {**cfg, "attrs": original_attrs})
                if plan["patch"] and safety["allow_fixture_read"] is True:
                    try:
                        fetched = await fetch_fixtures(validate=lambda: require_patch_context(context), applied=applied)
                        if not fetched.get("ok"):
                            raise ActionError(fetched.get("err") or "патч не перечитан")
                        now = next((f for f in cfg["fixtures"] if f["id"] == fid and not f.get("missing")), {})
                        check["patch"] = now.get("address")
                        if absolute(now.get("address")) is not None:
                            observed.add("patch")
                            if absolute(now["address"]) == parse_address(plan["new"]):
                                verified_sides.add("patch")
                    except (ActionError, OSError, ValueError) as e:
                        check["error"] = str(e)
                    require_patch_context(context)
                if plan["physical"]:
                    devices, lines = await rdm_read(plan["uid"], context)
                    check["rdm"] = lines[-5:]
                    device = next((d for d in devices if d["uid"] == plan["uid"]), {})
                    check["physical"] = device.get("address")
                    if "address" in device:
                        observed.add("physical")
                        if device["address"] == (parse_address(plan["new"]) - 1) % 512 + 1:
                            verified_sides.add("physical")
                        for fixture in cfg["fixtures"]:
                            if fixture["id"] == fid:
                                fixture["rdm"]["address"] = device["address"]
                        save_config(config_path, {**cfg, "attrs": original_attrs})
                require_patch_context(context)
            except (ActionError, OSError, ValueError) as e:
                check["error"] = str(e)
                context_error = str(e) if "контекст" in str(e) else context_error
            requested = {side for side in ("patch", "physical") if plan[side]}
            full_sent = len(done) == len(plan["lines"])
            uncertain = context_error or any(st["status"] == "unknown" for st in steps)
            verified = bool(full_sent and not uncertain and requested == verified_sides)
            result_status = ("verified" if verified else "unknown" if uncertain else
                             "partial" if (done and not full_sent) or verified_sides else
                             "sent" if full_sent and requested == observed else "unknown")
            check["verified"] = sorted(verified_sides) if not context_error else []
            undo = []
            if any(ln.startswith("RdmSetParameter") for ln in done) and plan["old_phys"]:
                undo.append(f"RdmSetParameter dmx_start_address {(plan['old_phys'] - 1) % 512 + 1} / UID = {plan['uid']}")
            if any(ln.startswith("Assign") for ln in done):
                undo.append(f"Assign Fixture {fid} At Dmx {plan['old']}")
            if any(ln.startswith("RdmSetParameter") for ln in done) and not plan["old_phys"]:
                undo.append("прежний физический адрес не был прочитан: вернуть его панель не может, выставьте на приборе вручную")
            if result_status == "unknown":
                undo = []  # never offer a compensating command for an uncertain operation
            add_history(a, f"Патч: прибор {fid} {plan['old']} → {plan['new']} · {result_status} ({', '.join(done) or 'нет подтверждённых отправок'})")
            log.warning("патч: %s; сделано: %s; проверка: %s", plan["lines"], done, check)
        await broadcast(config_msg())
        return {"ok": verified, "a": a, "status": result_status, "sent": full_sent, "verified": verified,
                "steps": steps, "check": check, "undo": undo, "plan": plan,
                **({} if verified else {"err": context_error or "Запись не подтверждена · " + result_status + ". Проверьте readback; автоматического повтора нет"}),
                "note": "Выключите RDM на пульте, если он больше не нужен" if plan["physical"] else None}

    async def list_shows():
        # ponytail: ListShows text format is unconfirmed; tune ma2.listshows_regex in the hall.
        ok, reply = await link.send("ListShows")
        if not ok:
            raise ActionError(reply.strip() or "ошибка пульта")
        names = []
        for match in re.finditer(ma2["listshows_regex"], reply):
            name = next((v for v in match.groups() if v is not None), match[0]).strip()
            try:
                show_name({"name": name})
            except ActionError:
                continue
            if name not in names:
                names.append(name)
        folder = Path(ma2["shows_dir"]) if ma2.get("shows_dir") else None
        local = sorted(p.name[:-8] for p in folder.glob("*.show.gz")) if folder and folder.is_dir() else []
        state["shows"] = {"names": names, "raw_lines": reply.splitlines(), "t": time.time(), "local_names": local}
        return state["shows"]

    async def load_show(action, before=None, sent=None, verify=None, expected_gen=None):
        name = show_name(action)
        if len(name) > 100:
            raise ActionError("имя шоу: от 1 до 100 символов")
        if safety["allow_show_load"] is not True:
            raise ActionError("загрузка заблокирована: allow_show_load")
        if action.get("confirm_name") != name or action.get("ack_unsaved") is not True:
            raise ActionError("подтвердите имя шоу и потерю несохранённых изменений")
        async with action_lock:
            if state["loading"]:
                raise ActionError("идёт загрузка шоу")
            if link.halted or not link.ready:
                raise ActionError(HALTED if link.halted else NO_LINK)
            if before:
                await before()
            if name not in (await list_shows())["names"]:
                raise ActionError("имя не найдено в свежем ListShows; загрузка отменена")
            # Finish the old highlight in its original plan context, before invalidating it.
            try:
                await release_highlight("show_load")
            except ActionError as e:
                state["show_load"].update(state="failed", name=name, reason=str(e))
                await broadcast(status_msg())
                raise
            state["plan_epoch"] += 1
            invalidate_scene_offers()
            state["master"] = None
            state["read_freshness"] = dict.fromkeys(("fixtures", "ma2", "scenes"), False)
            state["loading"] = name
            invalidate_evidence()
            state["show_load"] = {"state": "loading", "name": name, "reason": ""}
            throttle.clear()
            for session in sessions.values():
                session["selection"], session["base"] = [], None
            await broadcast(status_msg())
            try:
                cmd = ma2["loadshow_cmd"].format(name=name)
                # The template must retain the name checked in this action's fresh ListShows.
                target = re.match(r'LoadShow "([^"\r\n]+)"(?: |$)', cmd)
                if not target or target[1] != name:
                    raise ActionError("ma2.loadshow_cmd: имя не совпадает с проверенным шоу")
                if why := guard(cmd):
                    raise ActionError(why)
                previous, gen0 = state["show"]["name"], link._gen
                if verify:
                    verify()
                ok, reply = await link.send(cmd, gen=expected_gen)
                if sent:
                    sent(not (not ok and (is_error_reply(reply) or (link.last and link.last['status'] == 'not_sent'))))
                if not ok and (is_error_reply(reply) or (link.last and link.last["cmd"] == cmd and link.last["status"] == "not_sent")):
                    raise ActionError(reply.strip() or "ошибка пульта")
            except (ActionError, ValueError, KeyError, IndexError, TypeError, OSError) as e:
                state["loading"] = None
                state["show_load"].update(state="failed", reason=str(e))
                await broadcast(status_msg())
                raise ActionError(str(e)) from e
        # No action_lock while awaiting relogin: halt/resume/link controls remain available.
        deadline = time.monotonic() + float(ma2["load_timeout"])
        login_failed = False
        try:
            while time.monotonic() < deadline:
                if link.state == "login_failed":  # may be transient while MA2 loads: keep waiting, report it at the end
                    login_failed = True
                if link.ready and not link.halted:
                    try:
                        await asyncio.wait_for(identify_show(), max(0, deadline - time.monotonic()))
                    except TimeoutError:
                        link.close()  # a cancelled read must not leave a late reply for the next action
                        break
                    current = state["show"]["name"]
                    # MA2 may still report the old show for a while; reloading the same show is accepted only after a relogin
                    if current == name and (name != previous or link._gen != gen0):
                        async with action_lock:
                            await open_show_plan(name)
                            if safety["allow_fixture_read"]:
                                try:
                                    await fetch_fixtures()
                                except (ActionError, OSError, ValueError) as e:
                                    state["show_load"]["reason"] = f"шоу загружено; приборы не получены: {e}"
                        await broadcast(config_msg())
                        await broadcast(shown_msg())
                        state["show_load"]["state"] = "done"
                        return {"ok": True, "a": "show_load"}
                    if current and current not in (name, previous):
                        raise ActionError(f"MA2 сообщает другое имя шоу: {current}")
                # ListVar every SHOW_POLL_S; while logged out look often, so a short login_failed is not missed
                await asyncio.sleep(min(SHOW_POLL_S if link.ready else .1, max(0, deadline - time.monotonic())))
            state["show_load"].update(state="unknown", reason="вход после загрузки не удался: проверьте пользователя panel в новом шоу"
                                      if login_failed else "таймаут подтверждения имени шоу через ListVar"
                                      + (" (то же имя без переподключения подтвердить нельзя)" if name == previous else ""))
            raise ActionError(state["show_load"]["reason"])
        except (ActionError, OSError, ValueError) as e:
            if state["show_load"]["state"] == "loading":
                state["show_load"].update(state="failed", reason=str(e))
            raise
        finally:
            state["loading"] = None
            await broadcast(status_msg())

    async def handle(ws, text):
        nonlocal original_attrs
        try:
            action = json.loads(text)
        except ValueError:
            return {"ok": False, "err": "не JSON"}
        if not isinstance(action, dict) or not isinstance(action.get("a"), str):
            return {"ok": False, "err": "нужен объект с полем a"}
        a = action["a"]
        s = sessions[ws]
        if s.get("simple") and a not in ("scene_go", "scene_off", "blackout"):
            return {"ok": False, "a": a, "err": "в простом режиме недоступно"}
        if a == "scene_slot_cancel":
            request = action.get("request")
            if (job := s.get("scene_search")) and job["request"] == request:
                job["cancelled"] = True
            if (offer := s.get("scene_offer")) and offer["request"] == request:
                s.pop("scene_offer", None)
            await ws.send_json({"scene_slot": {"request": request, "state": "cancelled"}})
            return {"ok": True, "a": a}
        if a == "halt":  # before everything else, no locks: it must work even when the console hangs
            link.halted = True
            invalidate_scene_offers()
            throttle.clear()
            for session in sessions.values():
                session["base"] = None
            log.warning("ПЕРЕДАЧА ОСТАНОВЛЕНА (%s)", ws.client.host if ws.client else "?")
            if highlight["state"] != "idle":
                highlight_stuck(HALTED)
            await broadcast(status_msg())
            return {"ok": True, "a": a}
        if a == "resume":
            link.halted = False
            log.warning("передача возобновлена (%s)", ws.client.host if ws.client else "?")
            await broadcast(status_msg())
            return {"ok": True, "a": a}
        if a in ("link_drop", "link_connect"):  # only this bridge's own Telnet session: the console is not touched
            throttle.clear()
            link.disconnect() if a == "link_drop" else link.connect()
            log.warning("связь с MA2 %s вручную (%s)", "разорвана" if a == "link_drop" else "включена",
                        ws.client.host if ws.client else "?")
            await broadcast(status_msg())
            return {"ok": True, "a": a}
        if a == "show_status":
            return {"ok": True, "a": a, "show": state["show"], "show_load": state["show_load"]}
        if state["loading"]:
            return {"ok": False, "a": a, "err": "идёт загрузка шоу"}
        if state.get('show_file_active'):
            return {"ok": False, "a": a, "err": "выполняется операция файла шоу; управление временно недоступно"}
        if a == "mock_drop" and mock:
            app.state.mock.drop()
            return {"ok": True, "a": a}
        if a in ("edit_begin", "edit_end", "highlight", "highlight_off", "highlight_ping"):
            try:
                return await highlight_action(ws, action)
            except (ActionError, OSError, ValueError) as e:
                return {"ok": False, "a": a, "err": str(e)}
        if a in ("rdm_prepare", "rdm_start", "rdm_stop", "rdm_check"):
            # One RDM coordinator for every client; the actions bypass the halted check on purpose:
            # rdm_stop ends the window, rdm_check only reads (the coordinator itself refuses writes without a link).
            if safety["allow_rdm"] is not True and a != "rdm_stop":
                return {"ok": False, "a": a, "err": "заблокировано: allow_rdm в настройках"}
            try:
                if a == "rdm_prepare":
                    return {"ok": True, "a": a, "offer": await rdm.prepare()}
                if a == "rdm_start":
                    return {**{"ok": True, "a": a}, "search": await rdm.start(action.get("token"))}
                if a == "rdm_stop":
                    return {**{"ok": True, "a": a}, "search": await rdm.stop()}
                return {**{"ok": True, "a": a}, "search": await rdm.check()}
            except ActionError as e:
                return {"ok": False, "a": a, "err": str(e), **({"search": rdm.snapshot()} if a != "rdm_prepare" else {})}
        if a not in SIMPLE | FULL:
            return {"ok": False, "a": a, "err": "неизвестное действие"}
        if link.halted:
            return {"ok": False, "a": a, "err": HALTED}
        if why := blocked(a):
            return {"ok": False, "a": a, "err": why}
        deleted_scene = None
        try:
            if a == "scene_slot_find":
                request = action.get("request")
                if not isinstance(request, str) or not 1 <= len(request) <= 100:
                    raise ActionError("поиск: нужен идентификатор запроса")
                if not link.ready:
                    raise ActionError(NO_LINK)
                if job := s.get("scene_search"):
                    job["cancelled"] = True
                s.pop("scene_offer", None)
                job = {"request": request, "checked": 0, "cancelled": False}
                s["scene_search"] = job
                task = asyncio.create_task(find_scene_slot(ws, job))
                bg.add(task); task.add_done_callback(bg.discard)
                return {"ok": True, "a": a}
            if a == "undo":  # «История»: put back what one change replaced
                async with action_lock:
                    entry = next((e for e in history if e["n"] == action.get("n")), None)
                    if not entry or not entry["undo"] or entry["done"]:
                        raise ActionError("это изменение не откатывается" if entry else "изменения нет в истории")
                    if reason := history_reason(entry):
                        raise ActionError(reason)
                    entry["undo_state"], entry["undo_steps"] = "in_progress", []
                    spawn_broadcast(history_msg())
                undo_error = "операция прервана; результат неизвестен"
                try:
                    if entry["kind"] == "light":
                        changed, inverse_times = {}, {}
                        err = await undo_light(entry["before"], s, entry["context"], changed, entry["undo_steps"], inverse_times, entry["basis_times"])
                        if changed:
                            add_history("undo", "Откат: " + entry["what"], "light", changed, changed, context=entry["context"], basis_times=inverse_times)
                        if err:
                            undo_error = err
                            raise ActionError(err)
                    else:
                        async with action_lock:
                            if reason := history_reason(entry, owner=True):
                                raise ActionError(reason)
                            if state["loading"]:
                                raise ActionError("идёт загрузка шоу")
                            new = {k: v for k, v in {**cfg, **entry["before"]}.items() if v is not MISSING}
                            save_config(config_path, {**new, "attrs": original_attrs})
                            for k, v in entry["before"].items():
                                cfg.pop(k, None) if v is MISSING else cfg.__setitem__(k, v)
                        await broadcast(config_msg())
                    undo_error = None
                finally:
                    entry["done"] = True
                    statuses = {step["status"] for step in entry["undo_steps"]}
                    entry["undo_state"] = ("completed" if not undo_error else "unknown" if "unknown" in statuses
                                           or undo_error == "операция прервана; результат неизвестен" else
                                           "partial" if "sent" in statuses else "failed")
                    if undo_error:
                        entry["undo_error"] = undo_error
                    spawn_broadcast(history_msg())
                return {"ok": True, "a": a}
            if a == "shows_list":
                async with action_lock:
                    if state["loading"]:
                        raise ActionError("идёт загрузка шоу")
                    result = await list_shows()
                return {"ok": True, "a": a, **result}
            if a == "show_load":
                return await load_show(action)
            if a == "show_save":
                if safety["allow_show_save"] is not True:
                    raise ActionError("сохранение заблокировано: allow_show_save")
                async with action_lock:
                    if state["loading"]:
                        raise ActionError("идёт загрузка шоу")
                    # One button, owner's request 2026-10-21: SaveShow writes over the show open on the desk, whatever its name.
                    # The name is read fresh only to say what was saved.
                    listed, listvar = await link.send("ListVar")
                    if listed:
                        update_show(show_from(listvar))
                    ok, reply = await link.send("SaveShow")
                await broadcast(status_msg())
                return {"ok": ok, "a": a, "reply": reply, "name": state["show"]["name"], **({} if ok else {"err": reply})}
            if a == "show_identify":
                await identify_show()
                return {"ok": True, "a": a}
            if a == "import_confirm_merge":
                async with action_lock:
                    result = confirm_import(action)
                await broadcast(config_msg())
                return {**result, "a": a}
            if a in ("show_bind", "show_open_plan"):
                name = show_name(action)
                async with action_lock:
                    if state["loading"]:
                        raise ActionError("идёт загрузка шоу")
                    if a == "show_bind":
                        if cfg.get("show") and cfg["show"] != name and action.get("confirm") is not True:
                            raise ActionError("подтвердите смену привязки плана (confirm: true)")
                        save_config(config_path, {**cfg, "attrs": original_attrs, "show": name})
                        cfg["show"] = name
                    else:
                        await open_show_plan(name)
                await broadcast(config_msg())
                if a == "show_open_plan":
                    await broadcast(shown_msg())
                return {"ok": True, "a": a}
            if a in PLAN_WRITES and state["show"]["name"] and cfg.get("show") and state["show"]["name"] != cfg["show"]:
                raise ActionError("на пульте другое шоу: откройте его план (кнопка в баннере сверху)")
            if a in SLIDERS:
                check_move(action) if a == "move" else build(action, {**cfg, "master": settings.get("master", cfg.get("master", {"cmd": "Master 2.1 At {v}"}))})  # reject bad values now, not on the tick
                if a == "master":
                    ids = []
                elif a == "move":
                    if s["base"] is None:
                        raise ActionError("нет move_start")
                    ids = list(s["base"])
                elif a in ("zoom", "focus", "jog"):
                    ids = heads(s, selected(s))
                else:
                    ids = selected(s)  # the tab's selection at this moment: a later group change cannot redirect this value
                key = f"{id(ws)}:{a}"
                if a in ("dim", "color"):
                    throttle.stop(key + ":fade")  # a new value of this tab ends its running fade
                    if action.get("fade") and (starts := fade_starts(a, ids)):
                        if op := operation.get():
                            op.update(retain=True, deferred=True, stage="fade")
                        throttle.fades[key + ":fade"] = asyncio.create_task(play_fade(key + ":fade", ws, a, action, starts, action_ticket(ws)))
                        return None
                merged = False
                prev = throttle.pending(key) if a == "jog" else None
                total = {k: prev["action"][k] + action[k] for k in ("pan", "tilt")} if prev else {}
                if prev and prev["ids"] == ids and prev["action"].get("mirror") == action.get("mirror") and all(abs(v) <= 45 for v in total.values()):
                    # Joystick steps are relative: those waiting for the tick add up, none is dropped.
                    action = {**action, **total}
                    merged = True
                elif prev:
                    await throttle.flush(key)  # selection or mirror changed, or the sum is too big: the waiting steps go out first
                old = throttle.pending(key)
                if old and (old_op := old.get("operation")):
                    if merged and operation.get():
                        operation.get().setdefault("coalesced", []).append(old_op)
                    else:
                        await finish_operation(old_op, {"ok": False, "err": "заменено более новым значением до отправки"})
                if op := operation.get():
                    op.update(retain=True, stage="queued")
                throttle.put(key, {"ws": ws, "a": a, "action": action, "ids": ids, "operation": operation.get(), "ticket": action_ticket(ws)})
                return None
            if a in ("blackout", "scene_go", "scene_off"):  # a fade still running would light the fixtures again
                for k in list(throttle.fades):
                    throttle.stop(k)
            # Waiting slider values land before anything sent after them: a new gesture, a scene, a preset, a selection.
            await throttle.flush_all()
            if state["loading"]:
                raise ActionError("идёт загрузка шоу")
            if a in ("ma2_read", "ma2_import", "ma2_group_go", "ma2_preset_go", "group_store_ma2"):
                return await ma2_action(a, action, s)
            if a in ("select_group", "select_fixtures"):
                ids = targets(action, cfg)
                missing = [i for i in ids if next(f for f in cfg["fixtures"] if f["id"] == i).get("missing")]
                if missing:
                    raise ActionError(f"прибора {missing[0]} нет в шоу")
                check_ids(ids)
                s["selection"], s["base"] = ids, None  # bridge-side only: nothing is sent to MA2 until a value is set
                return {"ok": True, "a": a}
            if a == "clear":
                s["selection"], s["base"] = [], None
                return {"ok": True, "a": a}
            if a == "move_start":
                async with action_lock:  # waits for a move the throttle is sending right now
                    ids = heads(s, selected(s))
                    s["base"] = None
                    for fid in ids:
                        if any(k not in known_shown().get(fid, {}) for k in ("pan", "tilt")):
                            raise ActionError(f"позиция головы {fid} неизвестна: пульт не сообщает текущее положение. Используйте шаги ←→↑↓ или «Задать позицию»")
                    s["base"] = {fid: {k: v for k, v in known_shown().get(fid, {}).items() if k in ("pan", "tilt")}
                                 for fid in ids}
                    s["base_expires"] = min(sent_evidence.records[f"sent:{fid}:{attr}"][1] + 6 for fid in ids for attr in ("pan", "tilt"))
                return {"ok": True, "a": a}
            if a in ("preset_save", "preset_delete", "group_save", "group_delete", "beam_home", "beam_invert", "dmx_map", "rdm_link"):
                async with action_lock:  # same wait: presets and beam_home read the heads' final pan/tilt
                    changes = config_edit(a, action, s)
                    save_config(config_path, {**cfg, "attrs": original_attrs, **changes})
                    cfg.update(changes)
                await broadcast(config_msg())
                return {"ok": True, "a": a}
            if a in ("scene_create", "page_save"):
                label = parse_label(action)
                if '"' in label:
                    raise ActionError("в имени нельзя кавычки")
                page = page_number(action, "page" if a == "scene_create" else "n")
                async with action_lock:
                    if state["loading"]:
                        raise ActionError("идёт загрузка шоу")
                    scenes, pages = cfg["scenes"], cfg.get("pages", [])
                    gen = link._gen
                    if a == "scene_create":
                        ex = canonical_exec(str(action.get("exec")))
                        old = None
                        if "token" in action:
                            offer = s.pop("scene_offer", None)
                            if (not offer or action.get("token") != offer["token"] or ex != offer["exec"]
                                    or offer_context() != offer["context"] or time.monotonic() >= offer["expires"]):
                                raise ActionError("предложение места устарело; выполните поиск заново")
                            if action.get("replace") is True:
                                raise ActionError("предложение места не предназначено для перезаписи")
                        if not re.fullmatch(r"\d+\.\d+", ex):
                            raise ActionError("executor: нужен номер в формате 1.101")
                        if action.get("replace") is True:  # overwrite (owner 2026-10-21): Delete Executor, then the same checked store; never /Overwrite
                            old = next((s for s in scenes if str(s["exec"]) == ex), None)
                            if not old:
                                raise ActionError(f"сцены {ex} нет в панели")
                            if str(action.get("confirm")) != ex:
                                raise ActionError("запись не подтверждена: confirm должен совпасть с номером executor")
                            if highlight["state"] != "idle":
                                highlight_stuck("перезапись сцены; прежнее снятие подсветки запрещено")
                            ok, reply = await link.send(f"Delete Executor {ex}", gen=gen)
                            if not ok:
                                raise ActionError(reply.strip() or "ошибка пульта")
                            deleted_scene = old
                            scene_evidence.invalidate([old["id"]])
                            await broadcast(scenes_msg())
                        await store_checked(ex, action, gen=gen)
                        lines = store_lines(ex, label)
                        entry = {"id": old["id"] if old else new_id(scenes, "s"), "exec": ex, "label": label, "named": True}
                        changes = {"scenes": [entry if sc is old else sc for sc in scenes] if old else scenes + [entry]}
                    else:
                        lines = [f'Label Page {page} "{label}"']
                        changes = {"pages": [p for p in pages if p["n"] != page] + [{"n": page, "label": label}]}
                    label_error = None
                    for i, line in enumerate(lines):
                        ok, reply = await link.send(line, gen=gen)
                        if not ok:
                            if a == "scene_create" and i == 0 and reply.startswith("результат неизвестен"):
                                raise ActionError(f"результат записи неизвестен: проверьте Executor {ex} на пульте. Повторно не отправлено")
                            if a == "scene_create" and i == 1:
                                label_error = f"сцена записана в {ex}, но имя не подтверждено: {reply.strip() or 'ошибка пульта'}"
                                break
                            raise ActionError(reply.strip() or "ошибка пульта")
                    save_config(config_path, {**cfg, "attrs": original_attrs, **changes})
                    cfg.update(changes)
                await broadcast(config_msg())
                return {"ok": False, "a": a, "err": label_error} if label_error else {"ok": True, "a": a}
            if a == "scenes_import":
                async with action_lock:
                    if state["loading"]:
                        raise ActionError("идёт загрузка шоу")
                    gen = link._gen
                    switched = await follow_desk_show()
                    if gen != link._gen:
                        state["read_freshness"]["scenes"] = False
                        raise ActionError("чтение сцен отменено: изменилось соединение; повторите чтение явно")
                    context = offer_context()
                    scenes, added, unrecognised = await read_scenes(context)
                    require_scene_context(context)
                    if scenes != cfg["scenes"]:
                        save_config(config_path, {**cfg, "attrs": original_attrs, "scenes": scenes})
                        cfg["scenes"] = scenes
                    state["read_freshness"]["scenes"] = unrecognised == 0
                    await broadcast(status_msg())
                await broadcast(config_msg())
                if switched:
                    await broadcast(shown_msg())
                    await broadcast(status_msg())
                return {"ok": True, "a": a, "added": added, "unrecognised": unrecognised, "total": len(cfg["scenes"]), "switched": switched}
            if a in ("scene_rename", "scene_delete"):
                async with action_lock:
                    if state["loading"]:
                        raise ActionError("идёт загрузка шоу")
                    scene = find(cfg["scenes"], action.get("id"))
                    if a == "scene_rename":
                        label = parse_label(action)
                        if '"' in label:
                            raise ActionError("в имени нельзя кавычки")
                        ok, reply = await link.send(f'Label Executor {scene["exec"]} "{label}"')
                        if not ok:
                            raise ActionError(reply.strip() or "ошибка пульта")
                        scenes = [{**s, "label": label, "named": True} if s is scene else s for s in cfg["scenes"]]
                    else:  # desk: true also deletes the executor on the console (owner 2026-10-21), else only the panel forgets it
                        if action.get("desk") is True:
                            if mode not in ("full", "store"):
                                raise ActionError(f"удаление на пульте заблокировано в режиме {mode}")
                            if highlight["state"] != "idle":
                                highlight_stuck("удаление сцены на MA2; прежнее снятие подсветки запрещено")
                            ok, reply = await link.send(f'Delete Executor {scene["exec"]}')
                            if not ok:
                                raise ActionError(reply.strip() or "ошибка пульта")
                        scenes = [s for s in cfg["scenes"] if s is not scene]
                    save_config(config_path, {**cfg, "attrs": original_attrs, "scenes": scenes})
                    cfg["scenes"] = scenes
                await broadcast(config_msg())
                return {"ok": True, "a": a}
            if a in ("layout_save", "hall_save", "fixture_flag"):
                async with action_lock:
                    if state["loading"]:
                        raise ActionError("идёт загрузка шоу")
                    if a == "layout_save":
                        layout_save(action)
                    else:
                        if a == "hall_save":
                            changes = {"hall": validate_hall(action.get("hall"))}
                        else:
                            # service: not dimmed by the highlight; moves: the operator marks a head (the 3.9 export has no attribute names)
                            fid = action.get("id")
                            flags = {k: action[k] for k in ("service", "moves", "rot", "flip_pan", "flip_tilt", "icon") if k in action}
                            same_type = action.get("same_type", False)
                            if type(fid) is not int or len(flags) != 1 or type(same_type) is not bool or (same_type and "moves" not in flags) or any(
                                    (v not in (0, 90) or type(v) is not int) if k == "rot" else v not in ("par", "bar", "head", "fresnel") if k == "icon"
                                    else type(v) is not bool for k, v in flags.items()):
                                raise ActionError("fixture_flag: нужен id прибора и service, moves, flip_pan или flip_tilt: bool, rot: 0 или 90, или icon: par/bar/head/fresnel (same_type только с moves)")
                            kind = find(cfg["fixtures"], fid).get("type")
                            hit = lambda f: f["id"] == fid or (same_type and kind and f.get("type") == kind)
                            changes = {"fixtures": [{k: v for k, v in {**f, **flags}.items() if k != "moves_auto" or "moves" not in flags} if hit(f) else f
                                                    for f in cfg["fixtures"]]}
                        save_config(config_path, {**cfg, "attrs": original_attrs, **changes})
                        cfg.update(changes)
                await broadcast(config_msg())
                if a == "fixture_flag":
                    await broadcast(status_msg())
                return {"ok": True, "a": a}
            if a == "plan_copy":
                async with action_lock:
                    changes, copied, groups, skipped = plan_copy(action)
                    save_config(config_path, {**cfg, "attrs": original_attrs, **changes})
                    cfg.update(changes)
                await broadcast(config_msg())
                return {"ok": True, "a": a, "copied": copied, "groups": groups, "skipped": skipped[:50]}
            if a in ("rdm_list", "rdm_identify", "patch_plan", "patch_apply"):
                return await patch_action(a, action)
            if a == "fixtures_fetch":
                if safety["allow_fixture_read"] is not True:
                    raise ActionError("получение приборов заблокировано: allow_fixture_read")
                async with action_lock:
                    if state["loading"]:
                        raise ActionError("идёт загрузка шоу")
                    switched = await follow_desk_show()
                    result = await fetch_fixtures()
                await broadcast(config_msg())
                if switched:
                    await broadcast(shown_msg())
                    await broadcast(status_msg())
                return {**result, "a": a, "switched": switched}
            swap = []
            if a == "scene_go":  # crossfade: the scenes the operator sees running go Off when the fade ends
                swap = action.get("swap", [])
                if (not isinstance(swap, list) or len(swap) > len(cfg["scenes"])
                        or any(type(i) is not str for i in swap) or len(set(swap)) != len(swap)):
                    raise ActionError("swap: нужен список id сцен")
                for sid in swap:
                    check_scene(find(cfg["scenes"], sid)["exec"])
            err = await execute(a, action, s, [])
            if not err and a == "scene_go" and capture and len(captured["execs"]) < 3:  # a running scene's row: the status word is a guess
                exec_ = find(cfg["scenes"], action["id"])["exec"]
                if exec_ not in captured["execs"]:
                    captured["execs"].add(exec_)
                    spawn_capture([f"List Executor {exec_}"], f"после Go сцены {exec_}")
        except (ActionError, ValueError) as e:
            err = str(e)
            if deleted_scene:
                err = "Предыдущая сцена удалена, новая запись не подтверждена: " + err
                async with action_lock:
                    cfg["scenes"] = [{**sc, "write_error": err} if sc["id"] == deleted_scene["id"] else sc for sc in cfg["scenes"]]
                    try:
                        save_config(config_path, {**cfg, "attrs": original_attrs})
                    except OSError:
                        err += ". Не удалось сохранить отметку ошибки"
                await broadcast(config_msg())
        except OSError as e:
            log.error("config save failed: %s", e)
            err = "не удалось сохранить конфиг"
        if err:
            log.warning("%s rejected: %s", a, err)
            return {"ok": False, "a": a, "err": err}
        return {"ok": True, "a": a}

    def on_result(entry):
        if op := operation.get():
            # Read replies do not establish that any mutation has succeeded.
            if entry.get("status") == "unknown" or not re.match(r"^(?:List|Get|cd |CD )", entry.get("cmd", "")):
                op["evidence"].append(entry["status"])
        app.state.last_send = time.monotonic()
        if entry.get("status") == "unknown":
            invalidate_evidence()
        spawn_broadcast({"last": entry})

    link = MA2Link(ma2["host"], ma2["port"], ma2["user"], password, on_state, guard, ma2["require_prompt"],
                   re.compile(ma2["prompt_regex"].encode()) if ma2.get("prompt_regex") else PROMPT,
                   re.compile(ma2["login_ok_regex"]) if ma2.get("login_ok_regex") else LOGIN_OK,
                   float(ma2.get("timeout", 2)), on_result)

    # RDM discovery (spec, «Поиск RDM»): one coordinator owns the exact global On/Off lines and the state read.
    # Journal next to config: survives reload/restart, so an unconfirmed Off stays visible to every client.
    def rdm_busy():
        # Queued/fade operations (retain) outlive their action: only running ones must block the search.
        # The rdm_* action itself is running: it must not block its own prepare/start/check.
        own = {id(op) for op in active_operations.values() if op.get("a", "").startswith("rdm_")}
        return bool(state["loading"] or state.get("show_file_active")
                    or any(id(op) not in own and not op.get("finished") and op.get("stage") != "queued"
                           for op in active_operations.values()))

    rdm = rdm_search.RDMSearch(link, action_lock, Path(config_path).parent / "rdm-search.json",
                               allowed=lambda: safety["allow_rdm"] is True,
                               context=lambda: (link._gen, link._stop_epoch, *offer_context()),
                               notify=lambda: spawn_broadcast(status_msg()),
                               busy=rdm_busy)
    rdm_shutdown = rdm.shutdown  # lifespan's finally calls it: the window gets its bounded finishing attempt

    class ProtocolThrottle(Throttle):
        def clear(self):
            pending = list(self._pending.values())
            super().clear()
            for intent in pending:
                op = intent.get("operation")
                if op and not op.get("deferred"):
                    task = asyncio.create_task(finish_operation(op, {"ok": False, "err": "передача отменена до отправки"}))
                    bg.add(task)
                    task.add_done_callback(bg.discard)

    throttle = ProtocolThrottle(rate_hz, throttled)
    diagnostic_uploader = diagnostic_upload.Uploader(Path(config_path).parent / "diag" / "upload-state.json",
                                                      settings_path.parent / "diagnostic-upload.json")

    @asynccontextmanager
    async def lifespan(app):
        log.addHandler(diag_handler)
        tasks = []
        try:
            if mock:
                app.state.mock = await start_mock(0, ma2["user"], export_dir)  # never the real console: a free local port
                link.host, link.port = "127.0.0.1", app.state.mock.port
            tasks = [asyncio.create_task(browser_update.watch_orphan(app, HERE)), asyncio.create_task(link.run()), asyncio.create_task(throttle.run()), asyncio.create_task(highlight_lease()), asyncio.create_task(expire_evidence())]
            tasks.append(asyncio.create_task(diagnostic_uploader.run()))
            if poll_seconds:
                tasks.append(asyncio.create_task(poll_running()))
            if dmx_seconds:
                tasks.append(asyncio.create_task(poll_dmx()))
            yield
        finally:
            await rdm_shutdown()
            tasks.extend(bg)
            for t in tasks:
                t.cancel()
            link.close()
            await asyncio.gather(*tasks, return_exceptions=True)
            if workspace := getattr(app.state, 'show_files_workspace', None):
                workspace.cleanup()
            log.removeHandler(diag_handler)

    secrets = {password, load_secret(settings_path.parent)} - {""}

    def mask(text):
        return redact(text, secrets | {link.password})

    def safe_data(value):
        # Mask strings before serialising, including quotes/newlines in passwords.
        if isinstance(value, str):
            return mask(value)
        if isinstance(value, dict):
            return {mask(k): safe_data(v) for k, v in value.items()}
        if isinstance(value, list):
            return [safe_data(v) for v in value]
        return value

    errors = deque(maxlen=100)

    class DiagnosticHandler(logging.Handler):
        def emit(self, record):
            msg = mask(self.format(record))
            hint = next((advice for pattern, advice in DIAG_HINTS if re.search(pattern, msg, re.I)), "")
            errors.append({"t": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(record.created)),
                           "level": record.levelname, "msg": msg, "hint": hint})

    diag_handler = DiagnosticHandler(level=logging.WARNING)
    app = FastAPI(lifespan=lifespan)
    app.state.updating = bool(os.environ.get('MA2_UPDATE_ID'))
    app.state.update_hold = os.environ.get('MA2_UPDATE_ID')
    app.state.active_actions = 0
    app.state.active_http = 0
    app.state.last_action = -1e9
    app.state.instance = token_urlsafe(18)

    def updating():
        if app.state.updating and app.state.update_hold:
            import browser_update
            current = browser_update.status(HERE)
            if current.get('id') == app.state.update_hold and current['phase'] in browser_update.TERMINAL:
                app.state.updating = False
        return app.state.updating

    link.admission = lambda: not updating()

    def update_busy():
        return (updating() or action_lock.locked() or link._lock.locked()
                or app.state.active_actions or app.state.active_http or active_operations or rdm.active or throttle._pending or throttle.fades
                or any(not task.done() for task in bg) or state['loading'] or state.get('background_type_read')
                or highlight['state'] != 'idle' or time.monotonic() - app.state.last_action < 10
                or time.monotonic() - getattr(app.state, 'last_send', -1e9) < 10)

    async def update_gate():
        if update_busy():
            return False
        # No await between checking admitted work and closing the physical send gate.
        app.state.updating = True
        return True

    def update_reopen():
        app.state.updating = False
        app.state.update_hold = None

    def update_stop():
        app.state.exit_code = 0  # code 3 would let start.bat race the external updater
        app.state.server.should_exit = True


    async def perform_action_inner(ws, text):
        try:
            a = json.loads(text).get("a")
        except (ValueError, AttributeError):
            a = None
        try:
            reply = await handle(ws, text)
        except Exception:  # one bad message must not kill the panel's connection
            log.exception("action failed: %.200s", text)
            reply = {"ok": False, "err": "внутренняя ошибка моста"}
        if isinstance(a, str) and a not in SLIDERS and reply and reply.get("ok"):
            op = operation.get() or {}
            changed = op.get("history_before", {})
            if a == "undo" and changed:
                target = next((e for e in history if e["n"] == json.loads(text).get("n")), None)
                add_history(a, "Откат: " + (target["what"] if target else "?"), "config", changed, context=op.get("history_context"))
            elif changed or a in HISTORY_DESK:
                what = HISTORY_NAMES.get(a, a)
                if a in HISTORY_DESK or (a == "scene_delete" and json.loads(text).get("desk") is True):
                    add_history(a, what + (" (на пульте: панель не откатывает)" if a not in ("scene_go", "scene_off", "blackout", "page_go") else ""))
                else:
                    add_history(a, what, "config", changed, context=op.get("history_context"))
        if op := operation.get():
            if reply is None or op.get("deferred"):
                # The throttle or delayed transition owns the terminal response, not this admission stage.
                return
            reply = operation_reply(op, reply)
            if op["a"] in config_writes and ws in sessions and op.get("result_revision") and (reply.get("ok") or op.get("local_changed")):
                # A refused desk write may still refresh this request's own read-back metadata.
                # Never advance to a later revision published by another client during broadcast.
                sessions[ws]["legacy_revision"] = op["result_revision"]
        record(ws, text, reply)
        try:
            if reply and ws in clients:
                await ws.send_json(reply)
        except (WebSocketDisconnect, RuntimeError):
            pass
    def operation_reply(op, reply):
        if op["id"] is None:
            return reply
        evidence = op["evidence"]
        outcome = ("unknown" if "unknown" in evidence or (op["a"] == "show_load" and state["show_load"].get("state") == "unknown") else
                   "completed" if reply.get("ok") else
                   "partial" if "sent" in evidence or op.get("local_changed") else "failed")
        return {**reply, "a": op["a"], "request_id": op["id"], "outcome": outcome,
                "command_evidence": list(evidence),
                **({"config_revision": op["result_revision"]} if op.get("result_revision") else {}),
                **({"conflict": True, "config_revision": revision_token()} if op.get("conflict") else {})}

    async def finish_operation(op, reply):
        if op.get("finished"):
            return
        op["finished"] = True
        for previous in op.get("coalesced", []):
            previous["evidence"].extend(op["evidence"])
            await finish_operation(previous, reply)
        active_operations.pop(op["key"], None)
        if op["ws"] in clients and op["id"] is not None:
            try:
                await op["ws"].send_json(operation_reply(op, reply))
            except (WebSocketDisconnect, RuntimeError):
                pass
        if op["id"] is not None:
            await broadcast(status_msg())

    async def perform_action(ws, text):
        try:
            action = json.loads(text)
        except ValueError:
            action = {}
        if not isinstance(action, dict):
            action = {}
        action_name = action.get("a") if isinstance(action.get("a"), str) else None
        rid = action.get("request_id")
        if "request_id" in action and (not isinstance(rid, str) or not 1 <= len(rid) <= 100):
            await ws.send_json({"ok": False, "a": action_name, "request_id": None,
                                "outcome": "failed", "command_evidence": [], "err": "request_id: нужна строка длиной 1–100"})
            return
        session = sessions.get(ws)
        if session is None:
            return
        if rid is not None:
            if rid in session["requests"]:
                await ws.send_json({"ok": False, "a": action_name, "request_id": rid,
                                    "outcome": "failed", "command_evidence": [], "err": "request_id уже использован; повтор не отправлен"})
                return
            # Bound memory without forgetting old IDs and permitting duplicate execution.
            if len(session["requests"]) >= 20000:
                await ws.close(code=1008)
                return
            session["requests"].add(rid)
        op = {"id": rid, "a": action_name, "evidence": [], "ws": ws, "key": uuid.uuid4().hex,
              "revision": action.get("config_revision", session["legacy_revision"] if rid is None else None)}
        token = operation.set(op)
        active_operations[op["key"]] = op
        if rid is not None:
            await broadcast(status_msg())
        try:
            if updating():
                await ws.send_json(operation_reply(op, {"ok": False, "err": "идёт обновление программы"}))
            else:
                await perform_action_inner(ws, text)
        finally:
            if not op.get("retain"):
                active_operations.pop(op["key"], None)
                if rid is not None:
                    await broadcast(status_msg())
            operation.reset(token)

    async def handle_load(ws, text):
        app.state.active_actions += 1
        app.state.last_action = time.monotonic()
        try:
            await perform_action(ws, text)
        finally:
            app.state.active_actions -= 1

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await serve_ws(ws, simple=False)

    async def simple_ws_endpoint(ws: WebSocket):
        await serve_ws(ws, simple=True)

    async def serve_ws(ws: WebSocket, simple: bool):
        origin = ws.headers.get("origin")
        if origin and urlsplit(origin).netloc != ws.headers.get("host"):  # a web page on another site must not drive the lights
            await ws.close(code=1008)
            return
        await ws.accept()
        clients.add(ws)
        sessions[ws] = {"selection": [], "base": None, "simple": simple, "requests": set(), "legacy_revision": revision_token()}
        queue = asyncio.Queue()

        async def worker():
            while (text := await queue.get()) is not None and ws in clients:
                await handle_load(ws, text)

        def spawn(coro):
            task = asyncio.create_task(coro)
            bg.add(task)
            task.add_done_callback(bg.discard)

        spawn(worker())  # not cancelled on disconnect: a line already going to the console finishes, nothing queued runs
        try:
            for msg in (status_msg(), config_msg()) if simple else (status_msg(), config_msg(), shown_msg(), history_msg()):
                await ws.send_json(session_msg(ws, msg))
            await ws.send_json(scenes_msg())
            while True:
                text = await ws.receive_text()
                try:
                    a = json.loads(text).get("a")
                except (ValueError, AttributeError):
                    a = None
                if a == "halt":
                    await handle_load(ws, text)
                elif a == "show_load":
                    spawn(handle_load(ws, text))
                else:
                    queue.put_nowait(text)
        except WebSocketDisconnect:
            pass
        finally:
            queue.put_nowait(None)
            clients.discard(ws)
            for key, op in list(active_operations.items()):
                if op["ws"] is ws and op.get("stage") == "queued":
                    active_operations.pop(key, None)
            session = sessions.pop(ws, None)
            if session and (job := session.get("scene_search")):
                job["cancelled"] = True
            if highlight.get("owner") is ws:
                # Retain cleanup beyond the WebSocket's cancellation scope.
                task = asyncio.create_task(highlight_disconnect(ws))
                bg.add(task)
                task.add_done_callback(bg.discard)

    files = exports.bind(link, ma2, export_dir, export_extra, state, config_path, safe_data)
    export_folders, listing, save_diag_json, export_type, export_once, run_export_probe = (
        files.export_folders, files.listing, files.save_diag_json, files.export_type, files.export_once, files.run_export_probe)

    register_api(app, SimpleNamespace(**locals(), HERE=HERE), lambda request: is_loopback(request))  # looked up per call: tests patch bridge.is_loopback
    import show_transfer
    show_transfer.register(app, SimpleNamespace(**locals()))
    import onboarding
    onboarding.register(app, {**(settings or {}), 'port': (settings or {}).get('port', cfg.get('port', 8080))},
                        link, lambda request: is_loopback(request), lambda: local_addresses(), mock=mock)

    @app.middleware("http")
    async def no_cache(request, call_next):  # tablets revalidate, so a panel update shows on the next reload
        mutation = request.method not in ('GET', 'HEAD', 'OPTIONS') and not request.url.path.startswith('/api/update/')
        if mutation and updating():
            from fastapi.responses import JSONResponse
            return JSONResponse({'ok': False, 'err': 'идёт обновление программы'}, status_code=409)
        tracked_mutation = mutation and request.url.path != '/api/restart'
        if tracked_mutation:
            app.state.active_http += 1
            app.state.last_action = time.monotonic()
        try:
            response = await call_next(request)
        finally:
            if tracked_mutation:
                app.state.active_http -= 1
        response.headers.setdefault("Cache-Control", "no-cache")
        return response

    simple_app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    simple_app.add_api_websocket_route("/ws", simple_ws_endpoint)

    @simple_app.get("/")
    async def simple_index():
        return FileResponse(HERE / "static" / "simple.html", headers={"Cache-Control": "no-cache"})

    @simple_app.get("/style.css")
    async def simple_style():
        return FileResponse(HERE / "static" / "style.css", media_type="text/css", headers={"Cache-Control": "no-cache"})

    @simple_app.get("/simple.js")
    async def simple_script():
        return FileResponse(HERE / "static" / "simple.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})

    @simple_app.get("/command-feedback.js")
    async def simple_feedback_script():
        return FileResponse(HERE / "static" / "command-feedback.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})

    @simple_app.get('/api/update/health')
    def simple_health():
        return update_health()

    import browser_update
    def update_health():
        import update
        return {'version': update.version(HERE), 'pid': os.getpid(), 'instance': app.state.instance,
                'operation': os.environ.get('MA2_UPDATE_ID', '')}

    browser_update.register(app, HERE, is_loopback, update_gate, update_reopen, update_stop,
                            update_health, lambda: getattr(app.state, 'update_launch', None), update_busy)
    app.state.simple_app = simple_app
    app.mount("/", StaticFiles(directory=HERE / "static", html=True))
    return app


async def probe(cfg: dict, settings: dict | None = None, password: str = "") -> None:
    """Send read-only commands and write the raw replies to probe.txt: the replies are the formats to check in the hall."""
    m = {**DEFAULT_MA2, **cfg.get("ma2", {}), **(settings or {}).get("ma2", {})}
    link = MA2Link(m["host"], m["port"], m["user"], password or m.get("password", ""), lambda state: None,
                   make_guard({**effective_safety(settings or {}), "mode": "test", "allowed_fixtures": [], "allowed_scenes": []}),
                   m["require_prompt"])
    task = asyncio.create_task(link.run())
    for _ in range(100):
        if link.ready or link.state == "login_failed":
            break
        await asyncio.sleep(0.1)
    out = [f"ma2 state: {link.state}"]
    if link.ready:
        for cmd in PROBE_COMMANDS:
            ok, reply = await link.send(cmd)
            out.append(f"### {cmd}  (ok={ok})\n{reply!r}\n{reply}")
    task.cancel()
    link.close()
    (HERE / "probe.txt").write_text("\n".join(out), encoding="utf-8")
    print("\n".join(out[:1]), "-> probe.txt")


def backup_config(path: str, keep: int = 7) -> None:
    """One copy of config.json per day in backups/, the last `keep` days."""
    src = Path(path)
    folder = HERE / "backups"
    folder.mkdir(exist_ok=True)
    today = folder / f"config-{time.strftime('%Y%m%d')}.json"
    if src.exists() and not today.exists():
        shutil.copy(src, today)
    for old in sorted(folder.glob("config-*.json"))[:-keep]:
        old.unlink()


def local_addresses() -> list[str]:
    try:
        return sorted({i[4][0] for i in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET)})
    except OSError:
        return []


def check(cfg: dict, settings: dict, password: str) -> None:
    """Read nothing from the console: only prints the settings and tests that the Telnet port accepts a connection."""
    m = {**DEFAULT_MA2, **cfg.get("ma2", {}), **settings.get("ma2", {})}
    safety = effective_safety(settings)
    mine = local_addresses()
    print(f"Адреса этого компьютера: {', '.join(mine) or 'не определены'}")
    print(f"Пульт (Telnet): {m['host']}:{m['port']}, пользователь {m['user']!r}, пароль {'задан' if password else 'НЕ задан (пусто)'}")
    if m["host"] not in mine and m["host"] not in ("127.0.0.1", "localhost"):
        print(f"ВНИМАНИЕ: адреса {m['host']} нет среди адресов этого компьютера. Если MA2 стоит на этом ПК, адрес сменился: "
              f"поправьте ma2.host в settings.json (или поставьте 127.0.0.1).")
    try:
        with socket.create_connection((m["host"], m["port"]), timeout=3):
            print("Порт Telnet принимает соединение (вход в пульт не выполнялся, команды не отправлялись).")
    except OSError as e:
        print(f"Порт Telnet недоступен: {e}. Включён ли Telnet Remote на пульте и верен ли ma2.host в settings.json?")
    print(f"Панель: {settings.get('bind', '127.0.0.1')}:{settings.get('port', cfg.get('port', 8080))}")
    print(f"Режим защиты: {safety['mode']}; разрешены приборы {safety['allowed_fixtures'] or 'НИ ОДИН'}, "
          f"сцены {safety['allowed_scenes'] or 'НИ ОДНА'}")


def stop_running(settings: dict, cfg: dict) -> None:
    import urllib.error
    import urllib.request
    port = settings.get("port", cfg.get("port", 8080))
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/stop", method="POST", headers={"X-Stop": "1"})
    try:
        urllib.request.urlopen(req, timeout=5).read()
        print("Мост остановлен.")
    except (urllib.error.URLError, OSError):
        print("Мост не отвечает (уже остановлен?). Если окно моста ещё открыто, закройте его.")


async def open_start_page(server, port, opener=None):
    """Open only after the listener is ready; failure does not stop the bridge."""
    import webbrowser
    while not server.started:
        if server.should_exit:
            return
        await asyncio.sleep(0.1)
    try:
        await asyncio.to_thread(opener or webbrowser.open, f'http://127.0.0.1:{port}/setup.html')
    except Exception:
        log.warning('Не удалось открыть браузер. Откройте http://127.0.0.1:%s/setup.html', port)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # the Windows console may be cp1251/cp866: never die on Russian text
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    for ext, kind in ((".js", "text/javascript"), (".css", "text/css"), (".svg", "image/svg+xml"),
                      (".json", "application/json"), (".html", "text/html")):
        mimetypes.add_type(kind, ext)  # Windows takes types from the registry; a wrong .js type blanks the page
    p = argparse.ArgumentParser(description="MA2 panel bridge")
    p.add_argument("--config", default=str(HERE / "config.json"))
    p.add_argument("--settings", default=str(HERE / "settings.json"))
    p.add_argument("--probe", action="store_true", help="send read-only commands to MA2, save raw replies to probe.txt")
    p.add_argument("--check", action="store_true", help="print addresses and settings, test the Telnet port, send nothing")
    p.add_argument("--stop", action="store_true", help="ask a running bridge on this PC to stop")
    p.add_argument("--mock", action="store_true", help="fake MA2 on a free local port instead of the real console")
    p.add_argument("--open-browser", action="store_true", help="open the local connection wizard after HTTP startup")
    args = p.parse_args()
    import browser_update
    browser_update.recover_pending(HERE)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[RotatingFileHandler(HERE / "bridge.log", maxBytes=1_000_000, backupCount=3,
                                                      encoding="utf-8"), logging.StreamHandler()])
    cfg = load_config(args.config)
    if cfg.get("ma2", {}).get("password"):
        raise SystemExit("В config.json задан ma2.password: удалите его, пароль хранится только в secret.env (MA2_PASSWORD=...)")
    settings = load_settings(Path(args.settings))
    password = load_secret(Path(args.settings).parent)
    if args.stop:
        return stop_running(settings, cfg)
    if args.check:
        return check(cfg, settings, password)
    if args.probe:
        return asyncio.run(probe(cfg, settings, password))
    try:
        archive = legacy_archive_path(args.config, cfg)
        cfg, settings = migrate_config(args.config, args.settings, archive_path=archive)
    except (ValueError, OSError) as e:
        raise SystemExit(f"Миграция данных: {e}") from e
    port, bind = settings.get("port", cfg.get("port", 8080)), settings.get("bind", "127.0.0.1")
    simple_port = settings.get("simple_port", 8090)
    # Port 0 remains available for an ephemeral primary listener in local checks.
    try:
        validate_settings({"port": port if port != 0 else 8080, "simple_port": simple_port})
    except ValueError as e:
        raise SystemExit(f"Настройки: {e}")
    for listen_port in (port, simple_port):
        if listen_port is None:
            continue
        with socket.socket() as probe_socket:  # refuse before opening a second Telnet session
            if os.name != "nt":  # TIME_WAIT reuse; on Windows this could share a live listener
                probe_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                probe_socket.bind((bind, listen_port))
            except OSError as e:
                raise SystemExit(f"Порт {listen_port} занят ({e}). Мост уже запущен? Остановите его (stop.bat) и повторите.")
    safety = effective_safety(settings)
    version_file = HERE / "VERSION"
    log.info("старт: версия %s, режим %s, приборы %s, сцены %s, панель %s:%s, пульт %s:%s%s",
             version_file.read_text(encoding="utf-8-sig").strip() if version_file.exists() else "dev", safety["mode"], safety["allowed_fixtures"],
             safety["allowed_scenes"], bind, port, settings.get("ma2", cfg.get("ma2", {})).get("host"),
             settings.get("ma2", cfg.get("ma2", {})).get("port"), " (ИМИТАЦИЯ)" if args.mock else "")
    backup_config(args.config)
    app = create_app(cfg, args.mock, args.config, settings, password, settings_path=args.settings, capture=not args.mock)
    server = uvicorn.Server(uvicorn.Config(app, host=bind, port=port, log_level="info"))
    app.state.server = server
    app.state.update_launch = {'args': [a for a in sys.argv[1:] if a != '--open-browser'], 'ports': [port] + ([simple_port] if simple_port is not None else [])}
    pid = HERE / "bridge.pid"
    pid.write_text(str(os.getpid()))
    try:
        async def serve():
            servers = [server]
            if simple_port is not None:
                servers.append(uvicorn.Server(uvicorn.Config(app.state.simple_app, host=bind, port=simple_port,
                                                            log_level="info", lifespan="off")))
            async def run_server(current):
                try:
                    await current.serve()
                finally:
                    for other in servers:
                        other.should_exit = True
            tasks = [asyncio.create_task(run_server(current)) for current in servers]
            browser_task = None
            if args.open_browser and port and bind in ('127.0.0.1', '0.0.0.0', 'localhost'):
                browser_task = asyncio.create_task(open_start_page(server, port))
            try:
                await asyncio.gather(*tasks)
            finally:
                for current in servers:
                    current.should_exit = True
                await asyncio.gather(*tasks, return_exceptions=True)
                if browser_task:
                    browser_task.cancel()
                    await asyncio.gather(browser_task, return_exceptions=True)
        asyncio.run(serve())
        sys.exit(getattr(app.state, "exit_code", 0))
    finally:
        pid.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
