"""Import must keep one connection/show/plan context through its final save."""
import asyncio
import json
from pathlib import Path

import pytest

from test_status_evidence import context  # noqa: F401


@pytest.mark.parametrize("action", ["scenes_import", "ma2_import"])
@pytest.mark.parametrize("phase", ["pages", "first_page", "fallback", "last_page", "final_identity"])
@pytest.mark.parametrize("change", ["gen", "epoch"])
def test_import_discards_all_pages_when_context_changes(context, action, phase, change):
    c = context
    c.cfg["show"] = "Old"
    c.state["show"] = {"name": "Old", "source": "ma2"}
    path = Path(c.config_path)
    path.write_text(json.dumps(c.cfg))
    before = path.read_bytes()

    async def go():
        calls = []
        changed = False
        async def send(cmd, **kw):
            nonlocal changed
            calls.append((cmd, kw.get("gen")))
            trigger = (cmd == "List Page" if phase == "pages" else
                       cmd.startswith("List Executor 1.") if phase in ("first_page", "fallback") else
                       cmd.startswith("List Executor 2.") if phase == "last_page" else
                       cmd == "ListVar" and any(line.startswith("List Executor") for line, _ in calls))
            if trigger and not changed:
                changed = True
                if change == "gen":
                    c.link._gen += 1
                else:
                    c.state["plan_epoch"] += 1
            if cmd == "ListVar":
                return True, "Global : $SHOWFILE = Old\n[Group]>"
            if cmd == "List Page":
                return True, "Page 1 1 Page (1)\nPage 2 2 Page (1)\n[Group]>"
            if cmd.startswith("List Executor"):
                if phase == "fallback" and cmd.endswith("1.250"):
                    return False, "Error #9: NUMBER TOO LARGE\n[Group]>"
                page = cmd.split()[2].split(".")[0]
                return True, f"Executor {page}.102 {'OLD' if page == '1' else 'NEW'}\n[Group]>"
            if cmd.startswith('List Preset'):
                return True, 'No objects found\n[Group]>'
            return True, 'Group 1 "Existing"\n[Group]>'
        c.link.send = send
        ws = object()
        c.sessions[ws] = {"selection": [], "base": None}
        result = await c.handle(ws, json.dumps({"a": action, "groups": [], "scenes": True}))
        assert changed, (phase, calls)
        assert not result["ok"], result
        assert "отмен" in result["err"]
        assert path.read_bytes() == before
        assert not any(s["exec"] in ("1.102", "2.102") for s in c.cfg["scenes"])
        assert not c.state["read_freshness"]["scenes"]
        reads = [(cmd, gen) for cmd, gen in calls if cmd == "List Page" or cmd.startswith("List Executor")]
        assert all(gen == 0 for _, gen in reads)
        if phase == "fallback":
            assert not any(cmd.endswith("1.200") for cmd, _ in calls)
    asyncio.run(go())


@pytest.mark.parametrize("action", ["scenes_import", "ma2_import"])
def test_import_verifies_show_identity_again_before_save(context, action):
    c = context
    c.cfg["show"] = "Old"
    c.state["show"] = {"name": "Old", "source": "ma2"}
    path = Path(c.config_path)
    path.write_text(json.dumps(c.cfg))
    before = path.read_bytes()

    async def go():
        listed = False
        async def send(cmd, **kw):
            nonlocal listed
            if cmd == "ListVar":
                return True, f"Global : $SHOWFILE = {'New' if listed else 'Old'}\n[Group]>"
            if cmd == "List Page":
                return True, "Page 1 1 Page (1)\n[Group]>"
            if cmd.startswith("List Executor"):
                listed = True
                return True, "Executor 1.102 Mixed\n[Group]>"
            if cmd.startswith('List Preset'):
                return True, 'No objects found\n[Group]>'
            return True, 'Group 1 "Existing"\n[Group]>'
        c.link.send = send
        ws = object()
        c.sessions[ws] = {"selection": [], "base": None}
        result = await c.handle(ws, json.dumps({"a": action, "groups": [], "scenes": True}))
        assert not result["ok"] and "шоу" in result["err"]
        assert path.read_bytes() == before
        assert not c.state["read_freshness"]["scenes"]
    asyncio.run(go())
