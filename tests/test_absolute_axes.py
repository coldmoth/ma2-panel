"""Absolute axis changes must leave the other desk axis untouched."""
import pytest
from commands import ActionError, build

CFG = {"attrs": {"pan": {"min": -270, "max": 270, "cmd": 'Attribute "Pan" At {v}'},
                 "tilt": {"min": -135, "max": 135, "cmd": 'Attribute "Tilt" At {v}'}}}

@pytest.mark.parametrize("axis,value", [("pan", -270), ("tilt", 135)])
def test_absolute_axis_does_not_write_other_axis(axis, value):
    assert build({"a": "aim", axis: value}, CFG) == [f'Attribute "{axis.title()}" At {value}']

@pytest.mark.parametrize("action", [{"a": "aim"}, {"a": "aim", "pan": None}, {"a": "aim", "tilt": True},
                                    {"a": "aim", "pan": float("nan")}, {"a": "aim", "tilt": 136}])
def test_absolute_axes_reject_invalid_or_empty_actions(action):
    with pytest.raises(ActionError):
        build(action, CFG)
