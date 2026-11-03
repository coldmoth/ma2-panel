"""Safety contract for the finite RDM collection window, independent of HTTP/UI."""
import asyncio
import json
import re

import pytest

from commands import ActionError
import rdm_search as rdm


NONCE = "a" * 32


def reply(nonce=NONCE, global_on=False, universes=None):
    universes = {1: True, 2: False} if universes is None else universes
    return "\n".join([f"PANELRDM{nonce} GLOBAL {'On' if global_on else 'Off'}",
                      *(f"PANELRDM{nonce} UNIVERSE {n} {'On' if on else 'Off'}" for n, on in universes.items()),
                      f"PANELRDM{nonce} END {len(universes)}"])


class Desk:
    def __init__(self):
        self._gen = self._stop_epoch = 0
        self.ready = True
        self.halted = False
        self.host, self.port = "127.0.0.1", 30000
        self.on = False
        self.universes = {1: True, 2: False}
        self.lines = []
        self.hook = None
        self.rdm_reply = "43500F019FCB BAR Address 289 Footprint 10"

    async def send(self, line, *, gen=None):
        assert gen == self._gen
        self.lines.append(line)
        if self.hook:
            result = await self.hook(line)
            if result is not None:
                return result
        if line == rdm.ON:
            self.on = True
        elif line == rdm.OFF:
            self.on = False
        elif line == "RdmList":
            return True, self.rdm_reply
        else:
            nonce = re.search(r"PANELRDM([0-9a-f]{32})", line)[1]
            return True, reply(nonce, self.on, self.universes)
        return True, "Executing : " + line


def controller(tmp_path, desk=None, notify=None, **kw):
    desk = desk or Desk()
    return rdm.RDMSearch(desk, asyncio.Lock(), tmp_path / "rdm-search.json",
                         allowed=lambda: True,
                         context=lambda: (desk._gen, desk._stop_epoch, "show"),
                         notify=notify or noop, busy=lambda: False, **kw), desk


async def noop():
    pass


async def finish(c):
    await asyncio.wait_for(c.task, 2)
    return c.snapshot()


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(rdm, "WINDOW_SECONDS", .025)
    monkeypatch.setattr(rdm, "INTERVAL_SECONDS", .008)


def test_state_read_requires_matching_complete_bounded_evidence():
    assert rdm.parse_state(reply(), NONCE) == {"global": False, "universes": {1: True, 2: False}}
    assert rdm.is_read_command(rdm.read_command(NONCE))
    assert not rdm.is_read_command(rdm.read_command(NONCE) + "; evil()")
    assert not rdm.is_read_command('Lua "gma.cmd(\'ClearAll\')"')


@pytest.mark.parametrize("body", ["", "Executing : " + "PANELRDM" + NONCE + " GLOBAL Off",
    reply("b" * 32), reply().replace("GLOBAL Off", "GLOBAL nil"), reply().replace("END 2", "END 1"),
    reply() + "\n" + reply(), reply().replace("UNIVERSE 2 Off", "UNIVERSE 1 Off"),
    reply().replace("UNIVERSE 1 On", "UNIVERSE 0 On"), reply().replace("END 2", "END 65537"),
    "Executing : " + rdm.read_command(NONCE), reply() + "\nError #1", reply() + "x" * 1000000])
def test_unknown_state_never_proves_off(body):
    with pytest.raises(ActionError):
        rdm.parse_state(body, NONCE)


def test_one_window_one_on_one_off_and_data_not_patched(tmp_path):
    async def run():
        c, d = controller(tmp_path)
        offer = await c.prepare()
        assert offer["universes"] == [1]
        started = await c.start(offer["token"])
        assert started["active"]
        same = await c.start(offer["token"])
        assert same["id"] == started["id"]
        state = await finish(c)
        assert state["collection"] == "completed" and state["off_state"] == "confirmed"
        assert not state["pending"] and not state["active"]
        assert state["devices"][0]["uid"] == "43500F019FCB"
        assert d.lines.count(rdm.ON) == d.lines.count(rdm.OFF) == 1
        assert all(line in (rdm.ON, rdm.OFF, "RdmList") or rdm.is_read_command(line) for line in d.lines)
        assert json.loads((tmp_path / "rdm-search.json").read_text())["pending"] is False
    asyncio.run(run())


@pytest.mark.parametrize("case", ["global_on", "none_enabled", "bad_read", "permission", "busy", "locked"])
def test_preflight_refuses_without_writes(tmp_path, case):
    async def run():
        c, d = controller(tmp_path)
        if case == "global_on": d.on = True
        if case == "none_enabled": d.universes = {1: False}
        if case == "bad_read":
            async def bad(line): return True, "unknown schema"
            d.hook = bad
        if case == "permission": c.allowed = lambda: False
        if case == "busy": c.busy = lambda: True
        if case == "locked": await c.action_lock.acquire()
        with pytest.raises(ActionError): await c.prepare()
        assert rdm.ON not in d.lines and rdm.OFF not in d.lines
        assert not (tmp_path / "rdm-search.json").exists()
    asyncio.run(run())


@pytest.mark.parametrize("change", ["reconnect", "stop_ticket", "universe", "already_on"])
def test_offer_rechecked_before_any_write(tmp_path, change):
    async def run():
        c, d = controller(tmp_path)
        offer = await c.prepare()
        if change == "reconnect": d._gen += 1
        if change == "stop_ticket": d._stop_epoch += 1
        if change == "universe": d.universes[2] = True
        if change == "already_on": d.on = True
        try:
            await c.start(offer["token"])
        except ActionError:
            pass
        if c.task: await finish(c)
        assert rdm.ON not in d.lines and rdm.OFF not in d.lines
    asyncio.run(run())


def test_journal_written_before_on_and_failure_prevents_it(tmp_path, monkeypatch):
    async def run():
        c, d = controller(tmp_path)
        offer = await c.prepare()
        def fail(*args): raise OSError("disk full")
        monkeypatch.setattr(c, "_persist", fail)
        await c.start(offer["token"])
        state = await finish(c)
        assert rdm.ON not in d.lines and rdm.OFF not in d.lines
        assert state["collection"] == "failed"
    asyncio.run(run())


@pytest.mark.parametrize("stage", ["on", "confirm_on", "list", "off", "confirm_off"])
@pytest.mark.parametrize("fault", ["error", "unknown", "disconnect", "halt_resume"])
def test_faults_never_repeat_and_unknown_off_is_persistent(tmp_path, stage, fault):
    async def run():
        c, d = controller(tmp_path)
        offer = await c.prepare()
        fired = False
        async def hook(line):
            nonlocal fired
            at = (stage == "on" and line == rdm.ON or
                  stage == "confirm_on" and d.on and rdm.is_read_command(line) or
                  stage == "list" and line == "RdmList" or
                  stage == "off" and line == rdm.OFF or
                  stage == "confirm_off" and rdm.OFF in d.lines and rdm.is_read_command(line))
            if fired or not at: return None
            fired = True
            if fault == "disconnect": d._gen += 1; d.ready = False
            if fault == "halt_resume": d._stop_epoch += 1
            return False, "Error #1" if fault == "error" else "результат неизвестен"
        d.hook = hook
        await c.start(offer["token"])
        state = await finish(c)
        assert fired
        assert d.lines.count(rdm.ON) == 1 and d.lines.count(rdm.OFF) <= 1
        if fault in ("disconnect", "halt_resume") or stage in ("off", "confirm_off"):
            assert state["off_state"] == "unknown" and state["pending"]
            restarted, _ = controller(tmp_path)
            assert restarted.snapshot()["pending"] and restarted.snapshot()["recovery"]
            with pytest.raises(ActionError): await restarted.prepare()
    asyncio.run(run())


def test_stop_ends_window_but_confirms_off(tmp_path):
    async def run():
        c, d = controller(tmp_path)
        offer = await c.prepare()
        async def stop_list(line):
            if line == "RdmList": await c.stop()
        d.hook = stop_list
        await c.start(offer["token"])
        state = await finish(c)
        assert state["collection"] == "stopped" and state["off_state"] == "confirmed"
        assert not d.on
    asyncio.run(run())


def test_unknown_format_is_not_reported_as_zero_devices(tmp_path):
    async def run():
        c, d = controller(tmp_path)
        d.rdm_reply = "unrecognized columns without UID"
        await c.start((await c.prepare())["token"])
        state = await finish(c)
        assert state["format"] == "unverified" and state["lines"]
        assert state["off_state"] == "confirmed"
    asyncio.run(run())


def test_recovery_check_only_reads_and_clears_pending_after_off(tmp_path):
    async def run():
        c, d = controller(tmp_path)
        await c.prepare()
        c._persist(True)
        restored, desk = controller(tmp_path)
        desk.on = True
        await restored.check()
        assert restored.snapshot()["pending"]
        desk.on = False
        await restored.check()
        assert not restored.snapshot()["pending"] and restored.snapshot()["off_state"] == "confirmed"
        assert all(rdm.is_read_command(line) for line in desk.lines)
    asyncio.run(run())


def test_notification_failure_does_not_cancel_cleanup(tmp_path):
    async def run():
        async def broken(): raise RuntimeError("websocket gone")
        c, d = controller(tmp_path, notify=broken)
        await c.start((await c.prepare())["token"])
        assert (await finish(c))["off_state"] == "confirmed" and not d.on
    asyncio.run(run())


def test_shutdown_stops_collection_and_runs_bounded_cleanup(tmp_path):
    async def run():
        c, d = controller(tmp_path)
        await c.start((await c.prepare())["token"])
        while not d.on: await asyncio.sleep(0)
        await c.shutdown()
        assert not c.active and not d.on
        assert c.snapshot()["off_state"] == "confirmed"
    asyncio.run(run())
