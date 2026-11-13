import io
import json
from types import SimpleNamespace
import zipfile

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ma2panel import quality_diagnostics as quality
from test_onboarding import running


def inputs():
    return ({'version': 5, 'show': 'big room v3', 'fixtures': [
        {'id': 1, 'label': 'PERSON', 'type': 'PRIVATE-TYPE', 'address': '1.001', 'params': []}],
        'groups': [{'id': 'private', 'label': 'PERSON', 'fixtures': [1]}], 'scenes': [],
        'dmx_map': {'PRIVATE-TYPE': {'dim': 1, 'r': 2, 'g': 3, 'b': 4, 'has': []}}},
        {'safety': {'mode': 'full', 'allow_fixture_read': True}, 'dmx_seconds': 1,
         'ma2': {'password': 'SECRET', 'host': '192.168.99.99', 'user': 'PERSON'}},
        {'show': {'name': 'big room v3'}, 'read_freshness': {'fixtures': True, 'ma2': True},
         'values_meta': {'live': {'source': 'ma2', 'freshness': 'fresh'}}},
        SimpleNamespace(ready=True, state='logged_in', vars={'VERSION': '3.9.60', 'USER': 'PERSON'}, halted=False))


def rows(report):
    return {r['id']: r for r in report['checks']}


def test_readiness_never_promotes_unknown_or_wrong_show():
    cfg, settings, state, link = inputs()
    assert rows(quality.readiness(cfg, settings, state, link))['show']['status'] == 'pass'
    state['show']['name'] = 'another'
    assert rows(quality.readiness(cfg, settings, state, link))['show']['status'] == 'fail'
    cfg.pop('show')
    assert rows(quality.readiness(cfg, settings, state, link))['show']['status'] == 'unknown'
    link.ready = False
    report = quality.readiness(cfg, settings, state, link)
    assert not report['ready']
    assert rows(report)['connection']['status'] == 'fail'


def test_capabilities_distinguish_failed_pending_unsupported_hidden_and_blocked():
    cfg, settings, state, link = inputs()
    assert quality.capability(cfg, settings, state, link, 1, 'color') == 'supported'
    assert quality.capability(cfg, settings, state, link, 1, 'color', hidden=True) == 'hidden'
    settings['features'] = {'color': False}
    assert quality.capability(cfg, settings, state, link, 1, 'color') == 'blocked'
    settings['features'] = {}
    settings['safety']['mode'] = 'test'
    assert quality.capability(cfg, settings, state, link, 1, 'color') == 'blocked'
    settings['safety']['mode'] = 'full'
    cfg['dmx_map'].clear()
    assert quality.capability(cfg, settings, state, link, 1, 'color') == 'pending'
    state['type_reads'] = {'1': {'error': 'PRIVATE', 'kind': 'PRIVATE-TYPE'}}
    assert quality.capability(cfg, settings, state, link, 1, 'color') == 'read_error'
    cfg['dmx_map'] = {'PRIVATE-TYPE': {'has': [], 'dim': 1}}
    assert quality.capability(cfg, settings, state, link, 1, 'color') == 'unsupported'
    link.ready = False
    assert quality.capability(cfg, settings, state, link, 1, 'color') == 'disconnected'


def test_archive_is_structured_sanitized_and_explicitly_incomplete():
    cfg, settings, state, link = inputs()
    cfg['password'] = 'SECRET'
    state['raw'] = [{'reply': 'SECRET PERSON 192.168.99.99 /Users/PERSON'}]
    files = quality.collect(cfg, settings, state, link)
    packed = quality.pack(files)
    with zipfile.ZipFile(io.BytesIO(packed)) as archive:
        text = '\n'.join(archive.read(n).decode() for n in archive.namelist())
        assert set(archive.namelist()) == {'dataset.json', 'readiness.json', 'manifest.json'}
        for value in ('SECRET', 'PERSON', 'PRIVATE-TYPE', '192.168.99.99', '/Users/'):
            assert value not in text
        manifest = json.loads(archive.read('manifest.json'))
        assert manifest['complete'] is False and manifest['missing']
        dataset = json.loads(archive.read('dataset.json'))
        assert dataset['fixtures'][0]['address'] == '1.001'
        assert dataset['groups'][0]['fixtures'] == [1]


def test_available_xml_is_collected_without_private_names_paths_or_commands(tmp_path):
    cfg, settings, state, link = inputs()
    diag = tmp_path / 'diag'; diag.mkdir()
    (diag / 'last_export.xml').write_text('<MA><Info showfile="PERSON"/><Fixture fixture_id="1" name="SECRET"><FixtureType name="PRIVATE-TYPE"/><Address>1</Address></Fixture></MA>')
    files = quality.collect(cfg, settings, state, link, root=tmp_path)
    assert 'captures/last_export.xml' in files
    xml = files['captures/last_export.xml'].decode()
    assert 'fixture_id="1"' in xml and '<Address>1</Address>' in xml
    assert 'SECRET' not in xml and 'PERSON' not in xml and 'PRIVATE-TYPE' not in xml
    (diag / 'fixture_type_3.xml').symlink_to(diag / 'last_export.xml')
    assert 'captures/fixture_type_3.xml' not in quality.collect(cfg, settings, state, link, root=tmp_path)


def test_sanitized_fixture_type_preserves_rgb_channels_and_instance_semantics():
    from ma2panel.fixtures import parse_fixture_type
    xml = '<MA><FixtureType name="PRIVATE"><Instances><Instance module_index="0" patch="1"/></Instances><Module><ChannelType attribute="Dim" coarse="1"/><ChannelType attribute="ColorRGB1" coarse="2"/><ChannelType attribute="ColorRGB2" coarse="3"/><ChannelType attribute="ColorRGB3" coarse="4"/></Module></FixtureType></MA>'
    assert parse_fixture_type(quality._xml(xml, {})) == parse_fixture_type(xml)


def test_preview_and_download_are_same_snapshot_and_no_console_calls():
    cfg, settings, state, link = inputs()
    def forbidden(*args, **kwargs):
        raise AssertionError('diagnostics sent a command')
    link.send = forbidden
    app = FastAPI()
    quality.register(app, lambda: (cfg, settings, state, link), lambda request: True)
    with TestClient(app, base_url='http://localhost') as client:
        preview = client.post('/api/testing/preview').json()
        assert preview['files'] and preview['missing']
        cfg['fixtures'].clear()
        result = client.get('/api/testing/download/' + preview['token'])
        assert result.status_code == 200
        assert quality.digest(result.content) == preview['sha256']
        assert client.get('/api/testing/download/not-a-token').status_code == 404
        assert client.post('/api/testing/preview', headers={'Host': 'evil.example'}).status_code == 403
        assert client.get('/api/quality/readiness', headers={'Host': 'evil.example'}).status_code == 403
    app = FastAPI()
    quality.register(app, lambda: inputs(), lambda request: False)
    with TestClient(app, base_url='http://localhost') as client:
        assert client.post('/api/testing/preview').status_code == 403


def test_real_bridge_registers_passive_routes(running):
    client, _ = running
    mock = client.app.state.mock
    before = len(mock.received)
    assert client.app.state.quality['checks']
    assert client.get('/api/quality/readiness').status_code == 200
    preview = client.post('/api/testing/preview')
    assert preview.status_code == 200
    downloaded = client.get('/api/testing/download/' + preview.json()['token'])
    assert downloaded.status_code == 200
    with zipfile.ZipFile(io.BytesIO(downloaded.content)) as packed:
        manifest = json.loads(packed.read('manifest.json'))
        assert manifest['mock'] is True and manifest['origin'] == 'mock-panel-snapshot'
    assert len(mock.received) == before
