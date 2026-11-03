import json
import pytest
import firewall


def test_rules_follow_saved_ports_and_disabled_simple(tmp_path, monkeypatch):
    (tmp_path / 'settings.json').write_text(json.dumps({'port': 18080, 'simple_port': None}))
    calls = []
    monkeypatch.setattr(firewall.subprocess, 'run', lambda args, **kwargs: calls.append(args))
    firewall.apply(tmp_path)
    additions = [args for args in calls if 'add' in args]
    assert len(additions) == 1
    assert 'localport=18080' in additions[0]
    assert 'remoteip=LocalSubnet' in additions[0]
    assert f'program={tmp_path / "python/python.exe"}' in additions[0]
    assert any('name=MA2 simple panel' in args and 'delete' in args for args in calls)


def test_two_custom_ports(tmp_path, monkeypatch):
    (tmp_path / 'settings.json').write_text('{"port": 18080, "simple_port": 18090}')
    calls = []
    monkeypatch.setattr(firewall.subprocess, 'run', lambda args, **kwargs: calls.append(args))
    firewall.apply(tmp_path)
    assert {arg for args in calls if 'add' in args for arg in args if arg.startswith('localport=')} == {'localport=18080', 'localport=18090'}


@pytest.mark.parametrize('cfg', [{'port': 0}, {'port': True}, {'simple_port': '8090'}, {'port': 8080, 'simple_port': 8080}])
def test_invalid_ports_never_change_firewall(tmp_path, monkeypatch, cfg):
    (tmp_path / 'settings.json').write_text(json.dumps(cfg))
    monkeypatch.setattr(firewall.subprocess, 'run', lambda *args, **kwargs: pytest.fail('no mutation on invalid config'))
    with pytest.raises(ValueError):
        firewall.apply(tmp_path)
