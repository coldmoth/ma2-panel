"""Unit tests for strengthened grandMA2 Telnet parsing (ANSI/IAC, prompts, errors, List tables)."""
import asyncio
import re

import pytest

from ma2panel.commands import (
    exec_verdict,
    group_slot_empty,
    is_error_reply,
    parse_error,
    parse_executors,
    parse_ma2_objects,
    parse_running,
    parse_type_footprints,
    parse_type_names,
)
from ma2panel.fixtures import merge_fixtures, parse_export
from ma2panel.link import MA2Link, PROMPT, VAR, clean, detect_console_menu, frame_reply
from ma2panel.safety import DEFAULT_MA2


def test_clean_strips_ansi_csi_osc_charset_nul_and_iac_subnegotiation():
    raw = (
        b"\xff\xfb\x01"                       # IAC WILL ECHO
        b"\xff\xfa\x18\x00xterm-256color\xff\xf0"  # IAC SB TERMINAL-TYPE ... IAC SE
        b"\x1b]0;grandMA2\x07"                # OSC window title
        b"\x1b(B"                             # G0 charset
        b"\x1b[32m[Group]>\x1b[37m\x1b[K\r\x00\n"
    )
    assert clean(raw) == b"[Group]>\n"


@pytest.mark.parametrize("sample", [
    b"OK\r\n[Channel]>",
    b"OK\r\n\x1b[32m[Group]>\x1b[37m\x1b[K",
    b"OK\r\n[Channel]>/",
    b"OK\r\nFixture>",
    b"OK\r\nRoot/LiveSetup>",
    b"OK\r\n  [LayoutSelection]>  ",
])
def test_prompt_matches_real_ma2_prompt_variants(sample):
    assert PROMPT.search(clean(sample))


@pytest.mark.parametrize("sample", [
    b"[Channel]> List Group",
    b"OK\r\n<Fixture fixture_id=\"1\"/>",
    b"OK\r\nvalue > 50",
    b"OK\r\nCue 1 ->",
    b"OK\r\n",
])
def test_prompt_does_not_false_match_non_prompts(sample):
    assert not PROMPT.search(clean(sample))


def test_detect_console_menu():
    assert detect_console_menu("Executing : ListVar\n[Setup]>") == "Setup"
    assert detect_console_menu("  [Patch]>/ ") == "Patch"
    assert detect_console_menu("[EditSetup]>") == "EditSetup"
    assert detect_console_menu("[Channel]>") is None


def test_var_matches_dollar_global_prefix():
    reply = (
        "$Global : $USER = Remote\n"
        "$Global : $USERRIGHTS = Admin\n"
        "Global : $SHOWFILE = Hall 2026\n"
        "[Channel]>"
    )
    found = {k.upper(): v.strip() for k, v in VAR.findall(reply)}
    assert found == {"USER": "Remote", "USERRIGHTS": "Admin", "SHOWFILE": "Hall 2026"}


def test_frame_reply_trims_cross_session_chatter_without_dropping_errors():
    noisy = (
        "Executing : Go Executor 1.5\n"
        "[Channel]>\n"
        "Executing : List Group 1 Thru 10\n"
        "Group 1 1    HEAD STAGE\n"
        "[Group]>"
    )
    framed = frame_reply(noisy, "List Group 1 Thru 10")
    assert framed.startswith("Executing : List Group 1 Thru 10")
    assert "Go Executor 1.5" not in framed

    with_prior_error = "Error #72: COMMAND NOT EXECUTED\nExecuting : List Group 1\n[Group]>"
    assert frame_reply(with_prior_error, "List Group 1") == with_prior_error


def test_parse_error_handles_prompt_prefix_numbered_bare_and_ignores_warnings_and_names():
    assert parse_error("[Channel]>Error #14: OBJECT DOES NOT EXIST\n[Channel]>") == {
        "code": 14,
        "text": "OBJECT DOES NOT EXIST",
    }
    assert parse_error("Executing : Store Group 1\nError : Store Group 1\n[Group]>") == {
        "code": None,
        "text": "Store Group 1",
    }
    assert parse_error("no login\n[Channel]>") is not None
    assert is_error_reply("Login incorrect\r\n")
    assert parse_error("Executing : List Group 99\nWARNING, NO OBJECTS FOUND FOR LIST\n[Group]>") is None
    assert parse_error("Group 1 1    TERROR STAGE\nGroup 2 2    Error FX\n[Group]>") is None


def test_guest_login_rejected_for_named_user():
    async def go():
        link = MA2Link("unused", 0, "Remote", "pw", lambda _: None, timeout=0.05)

        class DummyWriter:
            def write(self, _):
                link._buf += b"Logged in as User 'guest'\r\n[Channel]>"
                link._got.set()

            async def drain(self):
                pass

            def close(self):
                link._closed.set()

        link._writer = DummyWriter()
        assert await link._login() == "login_failed"

    asyncio.run(go())


def test_parse_executors_and_running_ignore_prompts_echoes_and_headers():
    reply = (
        "[Channel]>Executing : List Executor 1.101 Thru 1.103\n"
        "          No.    Name        Object      Status\n"
        "          ----   ----------  ----------  -------\n"
        "[Channel]>Executor 1.101 1.101  Pianist     Sequence 1  Running\n"
        "Exec 1.102 1.102  Rehearsal   Sequence 2  Off\n"
        "Error #9: NUMBER TOO LARGE\n"
        "[Channel]>"
    )
    assert parse_executors(reply) == [("1.101", "Pianist"), ("1.102", "Rehearsal")]
    assert parse_running(reply) == {"1.101": True, "1.102": False}


def test_exec_verdict_ignores_command_echo_and_detects_empty_and_occupied():
    empty_re = re.compile(r"(?i)(?:warning,?\s*)?no objects? found")
    empty = "[Channel]>Executing : List Executor 1.150\nWARNING, NO OBJECTS FOUND FOR LIST\n[Channel]>"
    assert exec_verdict(empty, "1.150", empty_re)[0] == "empty"
    occupied = "[Channel]>Exec 1.150 1.150  Warm Wash   Running\n[Channel]>"
    assert exec_verdict(occupied, "1.150", empty_re)[0] == "occupied"


def test_parse_ma2_objects_handles_prompt_prefix_and_dashed_table():
    prefixed = (
        "[Group]>Executing : List Group 1 Thru 10\n"
        "[Group]>Group 1 1    HEAD STAGE\n"
        "Fixture>Group 2 2    ACME FRONT   extra\n"
        "[Group]>"
    )
    assert parse_ma2_objects(prefixed, DEFAULT_MA2["group_regex"]) == [
        {"n": 1, "name": "HEAD STAGE"},
        {"n": 2, "name": "ACME FRONT"},
    ]

    dashed = (
        "No.   Name          Info\n"
        "----  ------------  ----\n"
        "1     Front Wash    ok\n"
        "2     Back Truss    ok\n"
        "[Group]>"
    )
    assert parse_ma2_objects(dashed, DEFAULT_MA2["group_regex"]) == [
        {"n": 1, "name": "Front Wash"},
        {"n": 2, "name": "Back Truss"},
    ]
    assert not group_slot_empty(prefixed, 1, DEFAULT_MA2["group_regex"], DEFAULT_MA2["group_empty_regex"])


def test_parse_fixture_type_with_prompt_prefix_and_separator():
    table = (
        "[Channel]>              No.  LongName               ShortName             Manufacturer  ShortManu  DMXFootprint  Instances  Mode\n"
        "              ---  ---------------------  --------------------  ------------  ---------  ------------  ---------  ----\n"
        "FixtureType 3 3    ARTIST_FL_1000         ARTIST                IMLIGHT       IMLIGHT    9             1          RGB_CT\n"
        "FixtureType 4 4    Mini-B                 MiniBB8               Clay Paky     Clay P     17            1          Basic RGBW\n"
        "FixtureType 5 5    MultiCell Bar          Bar4                  Acme          Acme       40            4          Mode 4\n"
        "[Channel]>"
    )
    assert parse_type_footprints(table) == {"3": 9, "4": 17}
    assert parse_type_names(table) == {
        "ARTIST_FL_1000": "3",
        "Mini-B": "4",
        "MultiCell Bar": "5",
    }


def test_parse_export_keeps_physical_pos_separate_from_plan_xy():
    xml = """<?xml version="1.0" encoding="utf-8"?>
    <MA xmlns="http://schemas.malighting.de/grandma2/xml/MA">
      <Fixture index="0" name="Head 1" fixture_id="10">
        <FixtureType name="4 Mini-B"/>
        <SubFixture index="0">
          <Patch><Address>101</Address></Patch>
          <AbsolutePosition>
            <Location x="2.5" y="-3.25" z="6.0" />
            <Rotation x="0" y="180" z="15" />
          </AbsolutePosition>
        </SubFixture>
      </Fixture>
    </MA>"""
    parsed = parse_export(xml)
    assert parsed[0]["physical_pos"] == {"x": 2.5, "y": -3.25, "z": 6.0, "rot_x": 0.0, "rot_y": 180.0, "rot_z": 15.0}
    assert "x" not in parsed[0] and "y" not in parsed[0]

    old = [{"id": 10, "label": "Head 1", "name": "Head 1", "type": "4 Mini-B", "x": 0.25, "y": 0.75}]
    merged = merge_fixtures(old, parsed)
    assert (merged[0]["x"], merged[0]["y"]) == (0.25, 0.75)
    assert merged[0]["physical_pos"]["z"] == 6.0
