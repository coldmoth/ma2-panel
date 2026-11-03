"""Finite, explicitly admitted RDM collection with durable unconfirmed-Off recovery.

The MA2 object paths/properties below are a compatibility candidate, not a verified
3.9.60 schema. Unknown reads fail closed before enabling RDM. No data is patched.
"""
import asyncio
import copy
import json
import logging
import os
from pathlib import Path
import re
import time
import uuid

from commands import ActionError, is_error_reply, parse_rdm_list
from safety import RDM_GLOBAL  # the exact global On/Off lines: the guard admits them only through this module's admission

log = logging.getLogger("bridge")
WINDOW_SECONDS = 18
INTERVAL_SECONDS = 6
OFFER_TTL = 60
MAX_REPLY = 256 * 1024
RECOVERY = ("Выключение RDM не подтверждено. RDM может оставаться включённым и вызывать мигание. "
            "На MA2: Setup → Console → Global Settings → RDM (Enable RDM) → Off. "
            "Затем восстановите связь и нажмите «Проверить выключение».")
ON, OFF = RDM_GLOBAL


def read_command(nonce):
    if not re.fullmatch(r"[0-9a-f]{32}", nonce):
        raise ValueError("invalid RDM read nonce")
    # The output prefix is only data when it starts a separate feedback line.
    # nil, missing children and non-On/Off enums are deliberately not normalized.
    script = ("local p='PANELRDM" + nonce + "';"
              "local o=gma.show.getobj;local g=o.handle('Root Settings.Global');"
              "local u=o.handle('Root LiveSetup.Universes');"
              "gma.feedback(p..' GLOBAL '..tostring(gma.show.property.get(g,'EnableRDM')));"
              "local n=o.amount(u);if n<1 or n>65536 then error('RDM universe count') end;"
              "for i=0,n-1 do local h=o.child(u,i);"
              "gma.feedback(p..' UNIVERSE '..tostring(o.number(h))..' '..tostring(gma.show.property.get(h,'RDM'))) end;"
              "gma.feedback(p..' END '..tostring(n))")
    return 'Lua "' + script + '"'


def is_read_command(line):
    if not isinstance(line, str):
        return False
    m = re.search(r"PANELRDM([0-9a-f]{32})", line)
    return bool(m and line == read_command(m[1]))


def parse_state(reply, nonce):
    if not isinstance(reply, str) or len(reply) > MAX_REPLY or is_error_reply(reply):
        raise ActionError("состояние RDM не подтверждено: ошибка или слишком большой ответ")
    prefix = "PANELRDM" + nonce
    rows = [ln.strip() for ln in reply.splitlines() if ln.strip().startswith(prefix)]
    global_on, universes, end = None, {}, None
    for row in rows:
        if m := re.fullmatch(re.escape(prefix) + r" GLOBAL (On|Off)", row, re.I):
            if global_on is not None or universes or end is not None:
                raise ActionError("состояние RDM не подтверждено: повтор или порядок GLOBAL")
            global_on = m[1].lower() == "on"
        elif m := re.fullmatch(re.escape(prefix) + r" UNIVERSE ([1-9]\d{0,4}) (On|Off)", row, re.I):
            n = int(m[1])
            if global_on is None or end is not None or n > 65536 or n in universes:
                raise ActionError("состояние RDM не подтверждено: номер/повтор вселенной")
            universes[n] = m[2].lower() == "on"
        elif m := re.fullmatch(re.escape(prefix) + r" END ([1-9]\d{0,4})", row):
            if end is not None:
                raise ActionError("состояние RDM не подтверждено: повтор END")
            end = int(m[1])
        else:
            raise ActionError("состояние RDM не подтверждено: неизвестный формат")
    if global_on is None or not universes or end != len(universes):
        raise ActionError("состояние RDM не подтверждено: нет полного ответа с маркером запроса")
    return {"global": global_on, "universes": universes}


class RDMSearch:
    def __init__(self, link, action_lock, journal_path, allowed, context, notify, busy):
        self.link, self.action_lock = link, action_lock
        self.path = Path(journal_path)
        self.allowed, self.context, self.notify, self.busy = allowed, context, notify, busy
        self.task = None
        self._active = False
        self._stop = asyncio.Event()
        self._offer = None
        self._used = {}
        self._target = self._current_target()
        self._state = {"id": None, "phase": "idle", "collection": "idle", "off_state": "unknown",
                       "pending": False, "universes": [], "devices": [], "lines": [],
                       "format": "unverified", "reason": "", "t": None}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if (not isinstance(data, dict) or data.get("version") != 1
                        or type(data.get("pending")) is not bool):
                    raise ValueError("неверный журнал RDM")
                if data["pending"]:
                    self._target = data.get("target")
                    self._state.update(pending=True, phase="unknown", collection="unknown",
                                       id=data.get("id"), reason="мост перезапущен до подтверждения выключения")
            except (OSError, ValueError):
                self._target = None
                self._state.update(pending=True, phase="unknown", collection="unknown",
                                   reason="журнал RDM не прочитан: выключение требует проверки оператором")

    def _current_target(self):
        return {"host": self.link.host, "port": self.link.port}

    @property
    def active(self):
        return self._active

    def snapshot(self):
        return copy.deepcopy({**self._state, "active": self.active,
                              "recovery": RECOVERY if self._state["pending"] else ""})

    async def _notify(self):
        try:
            await self.notify()
        except Exception:
            # A failed observer must not skip the finally block that disables RDM.
            log.warning("RDM: не удалось уведомить интерфейс")

    def _persist(self, pending):
        data = {"version": 1, "pending": pending, "id": self._state["id"], "target": self._target}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(self.path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temp.open("x", encoding="utf-8") as stream:
                json.dump(data, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, self.path)
            # Windows does not expose portable directory fsync. The file itself is
            # flushed before atomic replacement; POSIX also flushes the directory.
            if os.name != "nt":
                fd = os.open(self.path.parent, os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
        finally:
            temp.unlink(missing_ok=True)
        self._state["pending"] = pending

    def _ensure(self, context):
        if (not self.allowed() or not self.link.ready or self.link.halted
                or self.context() != context):
            raise ActionError("подключение, шоу или передача изменились; RDM не повторён")

    def _available(self):
        if not self.allowed():
            raise ActionError("поиск RDM запрещён: allow_rdm")
        if not self.link.ready or self.link.halted:
            raise ActionError("нет готовой связи MA2 или передача остановлена")
        if self.active or self.busy() or self.action_lock.locked():
            raise ActionError("MA2 занята другой операцией; поиск RDM не поставлен в очередь")

    async def _send(self, line, context):
        self._ensure(context)
        ok, reply = await self.link.send(line, gen=context[0])
        self._ensure(context)
        if not ok or is_error_reply(reply):
            raise ActionError("RDM: " + (" ".join(reply.split())[:300] or "ответ не получен"))
        return reply

    async def _read(self, context):
        nonce = uuid.uuid4().hex
        return parse_state(await self._send(read_command(nonce), context), nonce)

    @staticmethod
    def _preflight(state):
        if state["global"]:
            raise ActionError("RDM уже включён на MA2: завершите чужую операцию и выключите RDM перед поиском")
        enabled = sorted(n for n, on in state["universes"].items() if on)
        if not enabled:
            raise ActionError("нет разрешённых RDM-вселенных; настройте их отдельно на MA2")
        return enabled

    async def prepare(self):
        self._available()
        if self._state["pending"]:
            raise ActionError(RECOVERY)
        context = self.context()
        async with self.action_lock:
            state = await self._read(context)
            universes = self._preflight(state)
            self._offer = {"token": uuid.uuid4().hex, "context": context, "state": state,
                           "created": time.monotonic()}
        self._state.update(phase="confirm", universes=universes)
        await self._notify()
        return {"token": self._offer["token"], "universes": universes, "seconds": WINDOW_SECONDS}

    async def start(self, token):
        if isinstance(token, str) and token in self._used:
            return {**self.snapshot(), "id": self._used[token]}
        self._available()
        if self._state["pending"]:
            raise ActionError(RECOVERY)
        offer = self._offer
        if (not isinstance(token, str) or not offer or token != offer["token"]
                or time.monotonic() - offer["created"] > OFFER_TTL):
            raise ActionError("подтверждение поиска RDM устарело; подготовьте поиск заново")
        self._ensure(offer["context"])
        self._active = True  # No await between admission and reservation.
        self._stop = asyncio.Event()
        self._state.update(id=uuid.uuid4().hex, phase="preflight", collection="running",
                           off_state="unknown", devices=[], lines=[], format="unverified", reason="", t=None)
        self._target = self._current_target()
        self._used[token] = self._state["id"]
        if len(self._used) > 32:
            del self._used[next(iter(self._used))]
        self._offer = None
        self.task = asyncio.create_task(self._run(offer))
        return self.snapshot()

    async def _run(self, offer):
        context = offer["context"]
        try:
            async with self.action_lock:
                try:
                    state = await self._read(context)
                    self._preflight(state)
                    if state != offer["state"]:
                        raise ActionError("настройки RDM изменились после подтверждения; подготовьте поиск заново")
                    if self._stop.is_set():
                        self._state["collection"] = "stopped"
                        return
                    self._ensure(context)
                    self._persist(True)
                    self._state["phase"] = "enabling"
                    await self._notify()
                    await self._send(ON, context)
                    if not (await self._read(context))["global"]:
                        raise ActionError("включение RDM не подтверждено")
                    self._state["phase"] = "collecting"
                    await self._notify()
                    deadline = time.monotonic() + WINDOW_SECONDS
                    while not self._stop.is_set():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        try:
                            await asyncio.wait_for(self._stop.wait(), min(INTERVAL_SECONDS, remaining))
                        except TimeoutError:
                            pass
                        self._ensure(context)
                        if self._stop.is_set():
                            break
                        raw = await self._send("RdmList", context)
                        if len(raw) > MAX_REPLY:
                            raise ActionError("слишком большой ответ RdmList")
                        lines = [line[:500] for line in raw.splitlines() if line.strip()][:400]
                        devices = parse_rdm_list(raw)[:400]
                        self._state.update(lines=lines, devices=devices, format="uids" if devices else "unverified",
                                           t=time.strftime("%H:%M:%S"))
                        await self._notify()
                    self._state["collection"] = "stopped" if self._stop.is_set() else "completed"
                except asyncio.CancelledError:
                    self._state.update(collection="unknown", reason="операция RDM прервана")
                except (ActionError, OSError, ValueError, RuntimeError) as exc:
                    self._state.update(collection="unknown" if self._state["pending"] else "failed",
                                       reason=str(exc)[:500])
                finally:
                    if self._state["pending"]:
                        await self._cleanup(context)
        except (ActionError, OSError, ValueError, RuntimeError) as exc:
            self._state.update(collection="unknown" if self._state["pending"] else "failed", reason=str(exc)[:500])
        finally:
            self._active = False
            self._state["phase"] = "unknown" if self._state["pending"] else "done"
            await self._notify()

    async def _cleanup(self, context):
        self._state["phase"] = "disabling"
        try:
            self._ensure(context)
            await self._notify()
            await self._send(OFF, context)
            state = await self._read(context)
            if state["global"]:
                raise ActionError("MA2 всё ещё сообщает RDM On")
            self._persist(False)
            self._state["off_state"] = "confirmed"
        except (ActionError, OSError, ValueError, RuntimeError, asyncio.CancelledError) as exc:
            self._state.update(off_state="unknown", reason=(self._state["reason"] + "; " + str(exc)).strip("; ")[:500])

    async def stop(self):
        self._stop.set()
        return self.snapshot()

    async def check(self):
        self._available()
        if self._state["pending"] and self._target != self._current_target():
            raise ActionError("журнал RDM относится к другому или неизвестному подключению; проверьте исходную MA2 вручную")
        context = self.context()
        async with self.action_lock:
            state = await self._read(context)
            self._state["universes"] = sorted(n for n, on in state["universes"].items() if on)
            if state["global"]:
                self._state.update(off_state="unknown", reason="MA2 сообщает RDM On; выключите его на MA2")
            else:
                if self._state["pending"]:
                    self._persist(False)
                self._state.update(off_state="confirmed", reason="", phase="done")
        await self._notify()
        return self.snapshot()

    async def shutdown(self):
        self._stop.set()
        if self.task and not self.task.done():
            timeout = min(10, max(2, getattr(self.link, "timeout", 2) * 3 + 1))
            try:
                await asyncio.wait_for(asyncio.shield(self.task), timeout)
            except TimeoutError:
                self.task.cancel()
                try:
                    await asyncio.wait_for(self.task, timeout)
                except (TimeoutError, asyncio.CancelledError):
                    pass
