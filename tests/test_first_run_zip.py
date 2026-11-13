import shutil
import sys
import socket
from pathlib import Path

import pytest
from ma2panel import release
from scripts.first_run_zip import check_program


@pytest.mark.parametrize('scenario', ['pristine','missing-config','broken-config','missing-settings','broken-settings'])
def test_delivered_defaults_without_replacing_configuration(tmp_path, scenario):
    if scenario in ('pristine','missing-settings'):
        try:
            for port in (8080,8090):
                with socket.socket() as sock: sock.bind(('127.0.0.1',port))
        except OSError:
            pytest.skip('Default ports occupied; untouched Windows ZIP CI gate must run independently')
    source=Path(__file__).resolve().parents[1]
    program=tmp_path/'program'
    release.write_tree(release.build(source),program)
    # This is the builder's exact delivery step, not a smoke-specific seed.
    for name in ('config','settings'):
        shutil.copy2(source/'ma2panel/resources'/f'{name}.example.json',program/f'{name}.json')
        assert (program/f'{name}.json').read_bytes()==(source/'ma2panel/resources'/f'{name}.example.json').read_bytes()
    check_program(program,sys.executable,tmp_path/'evidence',scenario)
    if scenario=='broken-config': assert (program/'config.json').read_bytes()==b'{broken'
    if scenario=='broken-settings': assert (program/'settings.json').read_bytes()==b'{broken'
