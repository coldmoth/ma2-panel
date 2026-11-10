import pytest

from ma2panel.commands import (ActionError, build, is_error_reply, targets, parse_positions,
                      FULL, SIMPLE, SLIDERS, scale, movers, apply_move, head_lines,
                      check_move, parse_label)

CFG = {
    "master": {"cmd": "Master 2.1 At {v}"},
    "groups": [{"id": "front", "n": 102, "label": "Фронт", "fixtures": [12, 14]}],
    "fixtures": [{"id": 12, "label": "ACME 1"}, {"id": 14, "label": "ACME 3"}],
    "scenes": [
        {"id": "pianist", "exec": "1.101", "label": "Pianist"},
        {"id": "choir", "exec": "1.102", "label": "Choir"},
    ],
}


def test_scene_go():   assert build({"a": "scene_go", "id": "pianist"}, CFG) == ["Goto Cue 1 Executor 1.101 Fade 0"]
def test_scene_go_fade():
    assert build({"a": "scene_go", "id": "pianist", "fade": 5}, CFG) == ["Goto Cue 1 Executor 1.101 Fade 5"]
    assert build({"a": "scene_go", "id": "pianist", "fade": 0}, CFG) == ["Goto Cue 1 Executor 1.101 Fade 0"]
    with pytest.raises(ActionError): build({"a": "scene_go", "id": "pianist", "fade": 99}, CFG)
def test_scene_off():  assert build({"a": "scene_off", "id": "pianist"}, CFG) == ["Masterfade 0 Executor 1.101", "Off Executor 1.101"]
def test_blackout():
    with pytest.raises(ActionError, match="Grand Master"): build({"a": "blackout"}, CFG)
def test_master():     assert build({"a": "master", "v": 40}, CFG) == ["Master 2.1 At 40"]
def test_group():      assert build({"a": "select_group", "id": "front"}, CFG) == ["Fixture 12 + 14"]  # never the unverified Group n
def test_fixtures():   assert build({"a": "select_fixtures", "ids": [12, 14]}, CFG) == ["Fixture 12 + 14"]
def test_dim():        assert build({"a": "dim", "v": 20}, CFG) == ["At 20"]
def test_color():      assert build({"a": "color", "r": 0, "g": 100, "b": 50}, CFG) == [
    'Attribute "ColorRGB1" At 0', 'Attribute "ColorRGB2" At 100', 'Attribute "ColorRGB3" At 50']
def test_removed_import():
    assert "import_fixtures" not in FULL
    with pytest.raises(ActionError): build({"a": "import_fixtures"}, CFG)


def test_clear():      assert build({"a": "clear"}, CFG) == []  # bridge-side only, the console's Clear is never sent
def test_store():
    from ma2panel.commands import store_lines
    assert build({"a": "store_scene", "id": "pianist"}, CFG) == store_lines("1.101", "Pianist") == [
        "StoreLook Executor 1.101 Cue 1 /Source=Output", 'Label Executor 1.101 "Pianist"']
    assert all("/Overwrite" not in line for line in store_lines("1.101", "P"))


@pytest.mark.parametrize("bad", [
    {"a": "clearall"}, {"a": "scene_go", "id": "nope"}, {"a": "dim", "v": "50; ClearAll"},
    {"a": "dim", "v": 101}, {"a": "dim", "v": -1}, {"a": "dim"}, {"a": "select_fixtures", "ids": [99]},
    {"a": "select_fixtures", "ids": []}, {"a": "color", "r": 0, "g": 0}, {}, ])
def test_rejects(bad):
    with pytest.raises(ActionError): build(bad, CFG)


def test_error_reply():
    assert is_error_reply("Error #3: ILLEGAL OBJECT") and is_error_reply("ILLEGAL COMMAND")
    assert is_error_reply("Executing : Fixture 1\r\nError : Fixture 1\r\nError #9: NUMBER TOO LARGE\r\n [Group]>")
    assert is_error_reply("Login incorrect\r\n")
    assert not is_error_reply("NO OBJECTS FOUND FOR FIXTURE 99")
    # names that contain the words are not errors (List Group / ListVar on the hall console)
    assert not is_error_reply("Executing : List Group 1 Thru 999\nGroup 1 1    TERROR STAGE\nGroup 2 2    Error FX\n [Group]>")
    assert not is_error_reply("Global : $SHOWFILE = illegal party\n [Group]>")
    assert not is_error_reply("[Channel]>")


def test_targets():
    assert targets({"a": "select_group", "id": "front"}, CFG) == [12, 14]
    assert targets({"a": "select_fixtures", "ids": [14]}, CFG) == [14]
    assert targets({"a": "dim", "v": 1}, CFG) is None


def test_layout_parse():
    assert parse_positions({"a": "layout_save", "pos": [{"id": 12, "x": 0.5, "y": 0}]}, CFG) == {12: (0.5, 0.0)}


@pytest.mark.parametrize("pos", [None, [], [{"id": 99, "x": 0, "y": 0}], [{"id": 12, "x": 5, "y": 0}],
                                 [{"id": 12, "x": True, "y": 0}], [{"id": 12, "x": "0.1", "y": 0}], [12]])
def test_layout_rejects(pos):
    with pytest.raises(ActionError): parse_positions({"a": "layout_save", "pos": pos}, CFG)


@pytest.mark.parametrize("bad", [[1], 5, "x", None])
def test_rejects_non_dict(bad):
    with pytest.raises(ActionError): build(bad, CFG)


ATTRS = {"pan": {"cmd": 'Attribute "Pan" At {v}', "min": -270, "max": 270},
         "tilt": {"cmd": 'Attribute "Tilt" At {v}', "min": -135, "max": 135},
         "zoom": {"cmd": 'Attribute "Zoom" At {v}', "min": 0, "max": 100},
         "focus": {"cmd": 'Attribute "Focus" At {v}', "min": 0, "max": 100}}
MCFG = {**CFG, "attrs": ATTRS,
        "fixtures": [{"id": 12, "label": "ACME 12", "moves": True}, {"id": 14, "label": "ACME 14", "moves": True},
                     {"id": 5, "label": "BAR 5"}],
        "groups": CFG["groups"] + [{"id": "g1", "label": "Мои", "fixtures": [12, 5]}]}

def test_scale():
    assert [scale("pan", v, MCFG) for v in (0, 50, 100)] == ["-270", "0", "270"]
    assert scale("tilt", 33.33, MCFG) == "-45"

def test_zoom_focus():
    assert build({"a": "zoom", "v": 50}, MCFG) == ['Attribute "Zoom" At 50']
    assert build({"a": "focus", "v": 0}, MCFG) == ['Attribute "Focus" At 0']

def test_movers():
    assert movers([5, 12, 14], MCFG) == [12, 14] and movers([5], MCFG) == []

def test_apply_move():
    base = {12: {"pan": 50, "tilt": 50}, 14: {"pan": 95, "tilt": 10}}
    assert apply_move(base, 10, -20) == {12: {"pan": 60, "tilt": 30}, 14: {"pan": 100, "tilt": 0}}

def test_head_lines_same():
    assert head_lines({12: {"pan": 50, "tilt": 0}}, MCFG) == ["Fixture 12", 'Attribute "Pan" At 0', 'Attribute "Tilt" At -135']

def test_head_lines_differ():
    assert head_lines({12: {"pan": 50, "tilt": 50}, 14: {"pan": 100, "tilt": 50}}, MCFG) == [
        "Fixture 12", 'Attribute "Pan" At 0', 'Attribute "Tilt" At 0',
        "Fixture 14", 'Attribute "Pan" At 270', 'Attribute "Tilt" At 0']

def test_group_without_n():
    assert build({"a": "select_group", "id": "g1"}, MCFG) == ["Fixture 12 + 5"]

def test_check_move():
    assert check_move({"a": "move", "dx": -100, "dy": 12.5}) == (-100, 12.5)

@pytest.mark.parametrize("bad", [{"a": "move", "dx": "5; ClearAll", "dy": 0}, {"a": "move", "dx": 101, "dy": 0},
                                 {"a": "move", "dx": 0}, {"a": "move", "dx": True, "dy": 0}])
def test_move_rejects(bad):
    with pytest.raises(ActionError): check_move(bad)

def test_label():
    assert parse_label({"label": "  Рояль "}) == "Рояль"

@pytest.mark.parametrize("bad", ["", "   ", "x" * 31, 5, None])
def test_label_rejects(bad):
    with pytest.raises(ActionError): parse_label({"label": bad})

def test_v2_actions_are_full():
    new = {"move_start", "move", "zoom", "focus", "preset_save", "preset_go", "preset_delete",
           "group_save", "group_delete", "beam_home", "beam_invert"}
    assert new <= FULL and not new & SIMPLE and {"move", "zoom", "focus"} <= SLIDERS
    for a in new - {"zoom", "focus"}:
        assert build({"a": a}, MCFG) == []

def test_zoom_rejects():
    with pytest.raises(ActionError): build({"a": "zoom", "v": "1; ClearAll"}, MCFG)

def test_pages():
    from ma2panel.commands import parse_executors
    assert build({"a": "page_go", "n": 4}, CFG) == ["Page 4"]
    assert parse_executors('  Executor 1.101  Pia"no  Sequence 1\r\nnoise\r\n 1.7   Go\r\n[Channel]>') == [("1.101", "Piano"), ("1.7", "Go")]

def test_parse_running():
    from ma2panel.commands import parse_running
    reply = "  Executor 1.101  Pianist  Sequence 1  Running\r\n  Executor 1.102  On  Sequence 2  Off\r\n  Executor 1.103  X\r\n"
    assert parse_running(reply) == {"1.101": True, "1.102": False}  # a label that says "On" is not a status
    assert parse_running("nothing useful") == {}


STROBE = {**MCFG, "attrs": {**MCFG["attrs"], "strobe": {"cmd": 'Attribute "Strobe" At {v}', "min": 0, "max": 100}}}

def test_strobe_and_fade():
    assert build({"a": "strobe", "v": 40}, STROBE) == ['Attribute "Strobe" At 40']
    assert build({"a": "dim", "v": 50, "fade": 3}, STROBE) == ["At 50 Fade 3"]
    assert build({"a": "dim", "v": 50}, STROBE) == ["At 50"]
    assert build({"a": "color", "r": 1, "g": 2, "b": 3, "fade": 1.5}, STROBE)[0] == 'Attribute "ColorRGB1" At 1 Fade 1.5'
    for bad in (-1, 31, "3; ClearAll", True):
        with pytest.raises(ActionError): build({"a": "dim", "v": 50, "fade": bad}, STROBE)
    with pytest.raises(ActionError): build({"a": "strobe", "v": 101}, STROBE)


def test_apply_move_requires_known_position():
    with pytest.raises(KeyError):
        apply_move({12: {}}, 1, 1)


def test_mapped_cmy_color():
    cfg = {"attrs": {"color": {"mode": "cmy", "names": ["Cyan", "Magenta", "Yellow"]}}}
    assert build({"a": "color", "r": 100, "g": 25, "b": 0, "fade": 2}, cfg) == [
        'Attribute "Cyan" At 0 Fade 2', 'Attribute "Magenta" At 75 Fade 2', 'Attribute "Yellow" At 100 Fade 2']


@pytest.mark.parametrize("step", [0, -1, 10.1, True, "2", float("nan")])
def test_nudge_step_rejected(step):
    cfg = {"attrs": {"pan": {"step": step}}}
    with pytest.raises(ActionError, match="attrs.pan.step"):
        build({"a": "nudge", "attr": "pan", "dir": 1}, cfg)


def test_aim_boundaries_and_nudge_mapping():
    cfg = {"attrs": {"pan": {"min": -90, "max": 90, "cmd": 'Attribute "Yaw" At {v}',
                             "rel_cmd": 'Attribute "Yaw" At {sign} {v}', "step": 1.5},
                     "tilt": {"min": -45, "max": 45, "cmd": 'Attribute "Pitch" At {v}'}}}
    assert build({"a": "aim", "pan": -90, "tilt": 45}, cfg) == ['Attribute "Yaw" At -90', 'Attribute "Pitch" At 45']
    assert build({"a": "nudge", "attr": "pan", "dir": -1}, cfg) == ['Attribute "Yaw" At - 1.5']


@pytest.mark.parametrize("reply, verdict", [
    ("Executor 2.150 Piano\r\n[Channel]>", "occupied"),
    ("Object: 2.150", "occupied"),
    ("List Executor 2.150 is occupied", "occupied"),
    ("List Executor 2.150\r\nNo objects found\r\n[Channel]>", "empty"),
    ("[Channel]> List Executor 2.150\r\nNothing found", "empty"),
    ("Executor 2.150 Piano\r\nNo objects found", "occupied"),
    ("", "unknown"), ("Error: illegal", "unknown"), ("???", "unknown"),
    ("List Executor 2.150\r\n[Channel]>", "unknown"),
])
def test_exec_verdict(reply, verdict):
    import re
    from ma2panel.commands import exec_verdict
    actual, reason = exec_verdict(reply, "2.150", re.compile(r"(?i)no objects? found|nothing found"))
    assert actual == verdict and reason


def test_unrecognised_lines():
    from ma2panel.commands import unrecognised_lines
    assert unrecognised_lines("[Channel]> List Executor 2.150\n\nExecutor 2.150 Piano\n???\n[Channel]>") == 1

@pytest.mark.parametrize('legacy', [2, 1.5])
def test_nudge_explicit_one_degree_ignores_legacy_step(legacy):
    cfg = {'attrs': {'pan': {'step': legacy}}}
    assert build({'a': 'nudge', 'attr': 'pan', 'dir': 1, 'step': 1}, cfg) == ['Attribute "Pan" At + 1']
    assert build({'a': 'nudge', 'attr': 'pan', 'dir': -1}, cfg) == [f'Attribute "Pan" At - {legacy:g}']

@pytest.mark.parametrize('step', [True, 0, -1, 11, '1', float('nan'), float('inf')])
def test_nudge_rejects_bad_explicit_step(step):
    with pytest.raises(ActionError):
        build({'a': 'nudge', 'attr': 'pan', 'dir': 1, 'step': step}, {'attrs': {'pan': {'step': 2}}})
