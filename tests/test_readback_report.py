"""Readback diagnostics survive the privacy boundary and the receiver."""
import copy
import json

import pytest
from fastapi.testclient import TestClient

from diagnostic_upload import build_report, collect_report
from relay.app import _valid_report, create_app
from test_diag import site  # noqa: F401


def snapshot():
    cfg = {'fixtures': [{'id': 912, 'label': 'Private fixture', 'type': '7 Private type',
                         'address': '2.100', 'footprint': 4}],
           'dmx_map': {'7 Private type': {'dim': 1, 'r': 2, 'g': 3, 'b': 4, 'has': []}}}
    diag = {'login_vars': {'USERRIGHTS': 'Admin', 'USER': 'Private operator'},
            'export': {'allow_fixture_read': True, 'dmx_seconds': 2,
                       'dmx_read': {'span': [612, 4], 'values': 0, 'chunks': 2, 't': '16:19:23',
                                    'pause_seconds': 1.0, 'read_seconds': 0.7,
                                    'cycle_seconds': None, 'max_age_seconds': None,
                                    'reason': 'неполный или недостоверный ответ DMX: маркер, диапазон или байты',
                                    'reply': 'ListVar: Global : $PANELST = 1 | Global : $PANELV = -1 | '
                                             'Global : $PANELDMX612 = "T0123456789abcdef 612 -1,-1,-1,-1"'},
                       'type_reads': {'7': {'file': 'C:/Private/path.xml', 'size': 400,
                                            'spec': {'dim': 1}, 'reply': 'Private operator'}}}}
    return diag, cfg


def test_unknown_output_keeps_read_failure_evidence_without_names_or_addresses(tmp_path):
    diag, cfg = snapshot()
    report = collect_report(diag, cfg)
    rb = report['readback']
    assert rb['rights'] == 'admin' and rb['enabled'] is True
    assert rb['poll_seconds'] == 2 and rb['dmx']['time'] == '16:19:23'
    assert rb['dmx']['reason'] == 'partial'
    assert rb['dmx']['values'] == 0 and rb['dmx']['read_seconds'] == 0.7
    assert rb['dmx']['canary_status'] == 1 and rb['dmx']['canary_value'] == -1
    assert rb['dmx']['rows'] == [{'marked': True, 'span_matches': True, 'bytes': [-1] * 4}]
    assert rb['fixtures'] == [{'type': 1, 'patched': True, 'missing': False, 'footprint': 4}]
    assert rb['types'][0]['channels'] == {'dim': 1, 'r': 2, 'g': 3, 'b': 4}
    assert rb['types'][0]['export'] == 'read'
    encoded = json.dumps(report)
    for private in ('Private', '912', '2.100', '612', '0123456789abcdef'):
        assert private not in encoded
    assert _valid_report(report)
    with TestClient(create_app(tmp_path / 'state', tmp_path / 'credentials.json', worker_interval=3600)) as client:
        identifier = 'f0e1d2c3-4567-4890-abcd-0123456789ab'
        response = client.put('/v1/reports/' + identifier, json={'report': report})
        assert response.status_code == 200
        assert response.json()['state'] == 'queued'
        assert client.put('/v1/reports/' + identifier, json={'report': report}).status_code == 200


@pytest.mark.parametrize('reply,reason', [('Error #44: PRIVATE', 'refused'), ('no data', 'partial')])
def test_error_codes_and_absent_canary_are_distinct_from_zero(reply, reason):
    diag, cfg = snapshot()
    diag['export']['dmx_read']['reply'] = reply
    if reason == 'refused':
        diag['export']['dmx_read']['reason'] = 'MA2 отказал в чтении DMX; следующая попытка не раньше чем через 30 с'
    dmx = build_report(diag, cfg)['readback']['dmx']
    assert dmx['reason'] == reason
    assert dmx['canary_status'] is None and dmx['canary_value'] is None
    assert dmx['errors'] == ([44] if reason == 'refused' else [])


def test_unsupported_and_stale_maps_do_not_look_readable():
    diag, cfg = snapshot()
    cfg['dmx_map']['7 Private type'] = {'unsupported': True, 'stale': True}
    row = build_report(diag, cfg)['readback']['types'][0]
    assert row['unsupported'] is True and row['stale'] is True and row['channels'] == {}


@pytest.mark.parametrize('value', ['Private', True, float('inf'), float('nan'), -2, 999999999])
def test_untrusted_numeric_fields_do_not_break_or_leak(value):
    diag, cfg = snapshot()
    diag['export']['dmx_read']['read_seconds'] = value
    cfg['fixtures'][0]['footprint'] = value
    cfg['dmx_map']['7 Private type']['dim'] = value
    report = build_report(diag, cfg)
    assert report['readback']['dmx']['read_seconds'] is None
    assert report['readback']['fixtures'][0]['footprint'] is None
    assert 'dim' not in report['readback']['types'][0]['channels']
    assert _valid_report(report)
    json.dumps(report, allow_nan=False)


def test_report_bounds_all_collections_and_keeps_dmx_evidence():
    diag, cfg = snapshot()
    cfg['fixtures'] *= 1000
    diag['raw'] = [{'cmd': 'ListVar', 'reply': 'private\n' * 500, 'status': 'sent'}] * 50
    report = collect_report(diag, cfg)
    assert report['readback']['truncated'] is True
    assert len(report['readback']['fixtures']) <= 64
    assert report['readback']['dmx']['canary_status'] == 1
    assert len(json.dumps(report, ensure_ascii=False)) <= 48000
    assert _valid_report(report)


@pytest.mark.parametrize('path,value', [
    (('rights',), 'Private operator'), (('enabled',), 1),
    (('dmx', 'read_seconds'), float('nan')), (('dmx', 'values'), True),
    (('dmx', 'reason'), 'Private path'), (('dmx', 'rows'), [{'bytes': [999]}]),
    (('fixtures',), [{'label': 'Private fixture'}]), (('types',), [{'path': 'C:/Private'}]),
    (('extra',), 'Private'),
    (('dmx', 'time'), 'Private'), (('poll_seconds',), -1),
])
def test_receiver_rejects_private_or_invalid_readback_extensions(path, value):
    diag, cfg = snapshot()
    report = copy.deepcopy(build_report(diag, cfg))
    target = report['readback']
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert not _valid_report(report)


def test_old_reports_remain_valid():
    report = build_report({}, {})
    report.pop('readback', None)
    assert _valid_report(report)


@pytest.mark.parametrize('password', ['0', '1', '2'])
def test_short_password_does_not_destroy_typed_measurements_or_versions(password):
    diag, cfg = snapshot()
    diag['version'] = '3.2.4+abc1234'
    diag['login_vars']['VERSION'] = '3.9.60.68'
    diag['raw'] = [{'cmd': 'Login "operator" "' + password + '"',
                    'reply': 'Login "operator" "' + password + '"', 'status': 'sent'}]
    report = build_report(diag, cfg, private=[password, 'operator'])
    assert report['panel_version'] == '3.2.4+abc1234'
    assert report['console_version'] == '3.9.60.68'
    assert report['readback']['dmx']['canary_status'] == 1
    assert report['readback']['dmx']['canary_value'] == -1
    assert report['readback']['dmx']['rows'][0]['bytes'] == [-1] * 4
    assert 'Login' not in json.dumps(report) and 'operator' not in json.dumps(report)
    assert _valid_report(report)


def test_actual_upload_endpoint_includes_fixture_maps_without_console_actions(site, monkeypatch):
    import diagnostic_relay
    received = []

    class Transport:
        def put(self, identifier, report):
            received.append(report)
            return {'report_id': identifier, 'state': 'sent', 'number': 100}

    monkeypatch.setattr(diagnostic_relay, 'Relay', Transport)
    with site(settings={'poll_seconds': 0, 'dmx_seconds': 0}) as s:
        before = list(s.link.raw)
        result = s.client.post('/api/diag/send', json={'report_id': 'f0e1d2c3-4567-4890-abcd-0123456789ab'},
                               headers={'X-Diag-Upload': '1', 'Host': 'localhost'})
        assert result.json()['number'] == 100
        fixtures = json.loads((s.folder / 'config.json').read_text())['fixtures']
        assert len(received[0]['readback']['fixtures']) == len(fixtures) > 0
        assert received[0]['readback']['poll_seconds'] == 0
        assert _valid_report(received[0])
        assert list(s.link.raw) == before
