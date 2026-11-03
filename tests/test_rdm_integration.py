"""Discovery through the real bridge/Telnet mock: no console or working show."""
import json
import time

import pytest

from safety import DEFAULT_SAFETY, make_guard
from test_bridge import ask, bridge_cfg, until  # noqa: F401

SETTINGS = {'safety': {'mode': 'full', 'allow_rdm': True, 'allow_patch': True,
                       'allow_fixture_read': True, 'allow_show_save': True}}
ON = 'Assign Root "Settings"."Global" /EnableRDM=On'
OFF = ON[:-2] + 'Off'


def test_search_commands_need_exact_coordinator_grant():
    enabled = {**DEFAULT_SAFETY, 'mode': 'full', 'allow_rdm': True}
    assert make_guard(enabled)(ON)
    assert make_guard(enabled, export_extra={ON})(ON)
    guard = make_guard(enabled, rdm_extra={ON, OFF})
    assert guard(ON) is None and guard(OFF) is None
    assert make_guard({**enabled, 'allow_rdm': False}, rdm_extra={ON})(ON)
    bad = 'Assign Root "Settings"."Global" /EnableRDM=On /Other=1'
    assert make_guard(enabled, rdm_extra={bad})(bad)


def test_discovery_requires_permission_before_any_read(bridge_cfg):
    with bridge_cfg(settings={'safety': {'mode': 'full'}}) as (ws, mock, _):
        result = ask(ws, {'a': 'rdm_prepare'})
        assert not result['ok'] and 'allow_rdm' in result['err']
        assert not any('PANELRDM' in x or 'EnableRDM' in x for x in mock.received)


def test_discovery_stop_conflicts_and_preserves_plan(bridge_cfg):
    with bridge_cfg(settings=SETTINGS) as (ws, mock, path):
        # Existing startup fixture/type reads may finish; capture plan after the prepare.
        offer = ask(ws, {'a': 'rdm_prepare'})
        assert offer['ok'], offer
        before = path.read_bytes()
        started = ask(ws, {'a': 'rdm_start', 'token': offer['offer']['token']})
        assert started['ok'], started
        for action in ({'a': 'rdm_prepare'}, {'a': 'dim', 'v': 100},
                       {'a': 'show_load', 'name': 'other'}, {'a': 'rdm_identify', 'uid': '43500F019FCB', 'on': True},
                       {'a': 'rdm_link', 'id': 1, 'uid': None}):
            r = ask(ws, action)
            assert not r['ok'] and 'RDM' in r['err'], r
        assert ask(ws, {'a': 'rdm_stop'})['ok']
        end = until(ws, lambda m: m.get('status', {}).get('rdm_search', {}).get('phase') == 'done')['status']['rdm_search']
        assert end['off_state'] == 'confirmed' and end['collection'] == 'stopped', end
        assert mock.received.count(ON) == mock.received.count(OFF) == 1
        assert path.read_bytes() == before
        assert not any(x.startswith(('RdmSetParameter', 'RdmAutopatch', 'RdmAutomatch', 'SaveShow', 'LoadShow')) for x in mock.received)


def test_halt_resume_never_runs_old_cleanup(bridge_cfg):
    with bridge_cfg(settings=SETTINGS) as (ws, mock, path):
        offer = ask(ws, {'a': 'rdm_prepare'})
        assert offer['ok'], offer
        assert ask(ws, {'a': 'rdm_start', 'token': offer['offer']['token']})['ok']
        until(ws, lambda m: m.get('status', {}).get('rdm_search', {}).get('phase') == 'collecting')
        assert ask(ws, {'a': 'halt'})['ok']
        assert ask(ws, {'a': 'resume'})['ok']
        assert ask(ws, {'a': 'rdm_stop'})['ok']
        end = until(ws, lambda m: m.get('status', {}).get('rdm_search', {}).get('phase') in ('done', 'unknown') and not m['status']['rdm_search']['active'])['status']['rdm_search']
        assert end['pending'] and end['off_state'] == 'unknown'
        assert OFF not in mock.received
        # Read-only check observes On and keeps the obligation. Manual console Off then read clears it.
        checked = ask(ws, {'a': 'rdm_check'})
        assert checked['search']['pending']
        mock.rdm_global = False
        mock.rdm_universes = {1: True}
        checked = ask(ws, {'a': 'rdm_check'})
        assert not checked['search']['pending'] and checked['search']['off_state'] == 'confirmed'
        assert OFF not in mock.received
