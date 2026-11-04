"""Раздел «Патч» (spec 21): patch rows, plans, the guard, and readdress through the mock desk."""
from pathlib import Path
from contextlib import contextmanager

import pytest

from commands import ActionError, parse_address, parse_rdm_list, parse_type_footprints, patch_plan, patch_rows
from safety import DEFAULT_SAFETY, make_guard
from test_bridge import ask, bridge_cfg, until  # noqa: F401

HALL = [(9, "R-1 WINDOW", 280), (23, "L-4 WINDOW", 289), (24, "R-4 WINDOW", 298)]  # hall 2026-10-21, an example only


def export(rows):
    return ('<MA xmlns="http://schemas.malighting.de/grandma2/xml/MA">' + "".join(
        f'<Fixture name="{name}" fixture_id="{fid}"><FixtureType name="3 ARTIST_FL_1000 RGB_CT"><No>3</No></FixtureType>'
        f'<SubFixture><Patch><Address>{a}</Address></Patch>' + '<Channel index="0" />' * 9 + '</SubFixture></Fixture>'
        for fid, name, a in rows) + "</MA>")


def plan_fixtures(**rdm):
    return [{"id": fid, "name": name, "type": "3 ARTIST_FL_1000 RGB_CT", "address": f"1.{a:03d}", "footprint": 9, **({"rdm": rdm[str(fid)]} if str(fid) in rdm else {})}
            for fid, name, a in HALL]


def test_footprints_come_from_the_type_list():
    text = (Path(__file__).parent / "list_fixturetype_3.9.60.txt").read_text(encoding="utf-8")
    assert parse_type_footprints(text) == {"1": 0, "2": 1, "3": 9, "4": 17, "5": 17, "6": 9, "7": 2, "8": 10}


def test_a_physical_footprint_shows_the_overlap_the_patch_hides():
    assert all(not r["conflicts"] for r in patch_rows(plan_fixtures()))  # 9 channels each: 280-288, 289-297, 298-306
    rows = {r["id"]: r for r in patch_rows(plan_fixtures(**{"9": {"uid": "43500F019FCB", "address": 280, "universe": 1, "footprint": 10}}))}
    assert rows[9]["conflicts"] == [23] and rows[23]["conflicts"] == [9]  # the device takes 280-289
    assert rows[24]["conflicts"] == [] and rows[24]["phys"] is None  # unknown size is not guessed


def test_plan_checks_and_lines():
    assert parse_address("1.290") == 290 and parse_address("2.001") == 513 and parse_address(290) == 290
    for bad in ("0", "1.513", "x", True, "257.1"):
        with pytest.raises(ActionError):
            parse_address(bad)
    plan = patch_plan(plan_fixtures(), 23, 290, patch=True, physical=False)
    assert plan["lines"] == ["Assign Fixture 23 At Dmx 1.290"] and plan["ma2_range"] == [290, 298] and plan["conflicts"] == [24]
    with pytest.raises(ActionError, match="не прочитано"):  # an unknown size never passes as one channel
        patch_plan([{**f, "footprint": None} for f in plan_fixtures()], 23, 290, patch=True, physical=False)
    with pytest.raises(ActionError, match="RDM"):
        patch_plan(plan_fixtures(), 23, 290, patch=False, physical=True)  # no UID linked
    both = patch_plan(plan_fixtures(**{"23": {"uid": "43500F019FCB", "address": 289, "footprint": 10, "universe": 1}}), 23, 290, patch=True, physical=True)
    assert both["lines"] == ["RdmSetParameter dmx_start_address 290 / UID = 43500F019FCB", "Assign Fixture 23 At Dmx 1.290"]
    assert patch_plan(plan_fixtures(), 23, 290, True, False)["token"] != patch_plan(plan_fixtures(), 23, 291, True, False)["token"]


def test_rdm_list_takes_uids_only_when_present():
    rows = parse_rdm_list("Executing : RdmList\n43500F019FCB  BAR  Address 289  Footprint 10\n4350:0F019FCC something\nno uid here")
    assert rows == [{"uid": "43500F019FCB", "line": "43500F019FCB BAR Address 289 Footprint 10", "address": 289, "footprint": 10},
                    {"uid": "43500F019FCC", "line": "4350:0F019FCC something"}]


def test_guard_lets_out_only_the_planned_patch_and_rdm_lines():
    line = "Assign Fixture 23 At Dmx 1.290"
    rdm = "RdmSetParameter dmx_start_address 290 / UID = 43500F019FCB"
    full = {**DEFAULT_SAFETY, "mode": "full"}
    assert make_guard(full, export_extra={line})(line)  # full mode is not enough
    assert make_guard({**full, "allow_patch": True})(line)  # a line nobody planned
    assert make_guard({**full, "allow_patch": True}, export_extra={line})(line) is None
    assert make_guard({**full, "allow_patch": True}, export_extra={"Assign Dmx 1.1 At Fixture 1"})("Assign Dmx 1.1 At Fixture 1")
    on = {**full, "allow_rdm": True}
    assert make_guard(full)("RdmList") and make_guard(on)("RdmList") is None
    assert make_guard(on)(rdm) and make_guard(on, export_extra={rdm})(rdm) is None
    for never in ("RdmAutopatch", "RdmAutomatch Fixture 1", "RdmSetParameter factory_defaults 1 / UID = 43500F019FCB"):
        assert make_guard(on, export_extra={never})(never)


SETTINGS = {"safety": {"mode": "full", "allow_fixture_read": True, "allow_patch": True, "allow_rdm": True}}


@contextmanager
def start(bridge_cfg, settings=SETTINGS):
    def edit(cfg):
        cfg["fixtures"] = [{"id": fid, "label": name, "name": name, "type": "3 ARTIST_FL_1000 RGB_CT", "address": f"1.{a:03d}", "channels": 9, "footprint": 9}
                           for fid, name, a in HALL]
        cfg["groups"] = [{"id": "w", "label": "Окна", "fixtures": [9, 23, 24]}]
    with bridge_cfg(edit, settings=settings) as result:
        ws, mock, _ = result
        mock.export_text = export(HALL)
        assert ask(ws, {"a": "fixtures_fetch"})["ok"]
        yield result


def test_patch_write_reads_back_and_keeps_groups(bridge_cfg):
    with start(bridge_cfg) as (ws, mock, path):
        mock.export_text = export(HALL)
        plan = ask(ws, {"a": "patch_plan", "id": 23, "address": "1.400", "patch": True})["plan"]
        assert plan["conflicts"] == [] and plan["lines"] == ["Assign Fixture 23 At Dmx 1.400"]
        r = ask(ws, {"a": "patch_apply", "id": 23, "address": "1.400", "patch": True, "token": plan["token"]})
        assert r["ok"] and r["check"]["patch"] == "1.400" and r["undo"] == ["Assign Fixture 23 At Dmx 1.289"]
        assert "Assign Fixture 23 At Dmx 1.400" in mock.received
        cfg = __import__("json").loads(path.read_text())
        assert cfg["groups"][0]["fixtures"] == [9, 23, 24] and next(f for f in cfg["fixtures"] if f["id"] == 23)["footprint"] == 9


def test_stale_plan_and_conflicts_are_refused(bridge_cfg):
    with start(bridge_cfg) as (ws, mock, _):
        plan = ask(ws, {"a": "patch_plan", "id": 23, "address": "1.290", "patch": True})["plan"]
        assert plan["conflicts"] == [24]
        r = ask(ws, {"a": "patch_apply", "id": 23, "address": "1.290", "patch": True, "token": plan["token"]})
        assert not r["ok"] and "пересечение" in r["err"]
        assert ask(ws, {"a": "rdm_link", "id": 23, "uid": "43500F019FCB", "footprint": 10})["ok"]  # fixture 23 changed after the plan
        r = ask(ws, {"a": "patch_apply", "id": 23, "address": "1.290", "patch": True, "token": plan["token"], "accept_conflicts": True})
        assert not r["ok"] and "устарел" in r["err"]
        assert not any(line.startswith("Assign") for line in mock.received)


def test_refused_write_and_a_break_between_the_two_steps(bridge_cfg):
    with start(bridge_cfg) as (ws, mock, _):
        mock.export_text = export(HALL)
        mock.assign_error = True
        plan = ask(ws, {"a": "patch_plan", "id": 23, "address": "1.400", "patch": True})["plan"]
        r = ask(ws, {"a": "patch_apply", "id": 23, "address": "1.400", "patch": True, "token": plan["token"]})
        assert not r["ok"] and r["steps"][0]["ok"] is False and r["undo"] == [] and r["check"]["patch"] == "1.289"
        assert ask(ws, {"a": "rdm_list"})["devices"] == 1
        assert ask(ws, {"a": "rdm_link", "id": 23, "uid": "43500F019FCB"})["ok"]  # address 289 and footprint 10 from RdmList
        before = len(mock.received)
        result = ask(ws, {"a": "patch_plan", "id": 23, "address": "1.400", "patch": True, "physical": True})
        assert not result["ok"] and "линия" in result["err"]
        assert len(mock.received) == before  # UID/address are not evidence of a physical universe



def test_patch_and_rdm_need_their_flags(bridge_cfg):
    with start(bridge_cfg, settings={"safety": {"mode": "full", "allow_fixture_read": True}}) as (ws, mock, _):
        plan = ask(ws, {"a": "patch_plan", "id": 23, "address": "1.400", "patch": True})["plan"]  # planning only reads
        r = ask(ws, {"a": "patch_apply", "id": 23, "address": "1.400", "patch": True, "token": plan["token"]})
        assert not r["ok"] and "allow_patch" in r["err"]
        assert "allow_rdm" in ask(ws, {"a": "rdm_list"})["err"]
        assert not any(line.startswith(("Assign", "Rdm")) for line in mock.received)


def test_patch_is_refused_on_another_show(bridge_cfg):
    def edit(cfg):
        cfg["fixtures"] = [{"id": 23, "label": "L-4", "name": "L-4", "type": "3 X", "address": "1.289", "channels": 9, "footprint": 9}]
        cfg["show"] = "другое шоу"
    with bridge_cfg(edit, settings=SETTINGS) as (ws, mock, _):
        r = ask(ws, {"a": "patch_apply", "id": 23, "address": "1.400", "patch": True, "token": "old"})
        assert not r["ok"] and "другое шоу" in r["err"] and not any(line.startswith("Assign") for line in mock.received)


@pytest.mark.parametrize('echo', ['Executing : RdmList / UID = 43500F019FCB',
                                  '[Channel]> RdmList / UID = 43500F019FCB',
                                  'RdmList / UID = 43500F019FCB',
                                  'Error : UID = 43500F019FCB'])
def test_rdm_request_is_not_device_evidence(echo):
    assert parse_rdm_list(echo) == []
    rows = parse_rdm_list(echo + '\n43500F019FCB BAR Address 289 Footprint 10')
    assert rows[0].get('address') == 289 and rows[0].get('footprint') == 10


def test_rdm_conflicting_or_truncated_properties_are_unknown():
    rows = parse_rdm_list('43500F019FCB BAR Address 28x Footprint 10x')
    assert 'address' not in rows[0] and 'footprint' not in rows[0]
    rows = parse_rdm_list('43500F019FCB Address 289 Footprint 10\n43500F019FCB Address 290 Footprint 10')
    assert 'address' not in rows[0]


@pytest.mark.parametrize('start, size, allowed', [(496, 17, True), (497, 17, False),
                                                  (512, 1, True), (512, 2, False),
                                                  (131072, 1, True), (131072, 2, False)])
def test_patch_rejects_block_crossing_universe(start, size, allowed):
    fixtures = [{'id': 1, 'address': '1.001', 'footprint': size}]
    if allowed:
        assert patch_plan(fixtures, 1, start, True, False)['lines']
    else:
        with pytest.raises(ActionError, match='границ'):
            patch_plan(fixtures, 1, start, True, False)


@pytest.mark.parametrize('physical, footprint, universe, target', [
    (True, None, 1, 400), (True, 10, None, 400), (True, 10, 1, 912),
    (True, 10, 1, 510)])
def test_physical_write_requires_size_and_known_matching_line(physical, footprint, universe, target):
    fixtures = plan_fixtures(**{'23': {'uid': '43500F019FCB', 'address': 289,
                                     'footprint': footprint, 'universe': universe}})
    with pytest.raises(ActionError):
        patch_plan(fixtures, 23, target, False, physical)


def test_physical_rows_do_not_guess_line_from_patch():
    rows = patch_rows(plan_fixtures(**{'23': {'uid': '43500F019FCB', 'address': 289, 'footprint': 10}}))
    assert next(r for r in rows if r['id'] == 23)['phys_start'] is None


def test_known_physical_line_stays_fixed_after_patch_move():
    fixtures = plan_fixtures(**{'23': {'uid': '43500F019FCB', 'address': 289, 'footprint': 10, 'universe': 1}})
    plan = patch_plan(fixtures, 23, 912, True, False)
    assert plan['phys_range'] == [289, 298]


def test_multiple_patch_addresses_never_authorize_flat_write():
    from fixtures import parse_export, merge_fixtures
    xml = export([(1, 'Complex', 100)]).replace('</Patch>', '</Patch><Patch><Address>600</Address></Patch>')
    found = parse_export(xml)
    fixtures = merge_fixtures([], found)
    fixtures[0]['footprint'] = 17
    with pytest.raises(ActionError, match='структур'):
        patch_plan(fixtures, 1, 200, True, False)


def test_rdm_repeated_incomplete_records_do_not_synthesize_properties():
    rows = parse_rdm_list('43500F019FCB Address 289\n43500F019FCB Footprint 10')
    assert 'address' not in rows[0] and 'footprint' not in rows[0]
    rows = parse_rdm_list('43500F019FCB Address ' + '9' * 5000)
    assert 'address' not in rows[0]


def test_unsupported_neighbor_cannot_hide_extra_patch_ranges():
    fixtures = [{'id': 1, 'address': '1.100', 'footprint': 17},
                {'id': 2, 'address': '1.200', 'footprint': 17, 'patch_unsupported': True}]
    with pytest.raises(ActionError):
        patch_plan(fixtures, 1, 300, True, False)
