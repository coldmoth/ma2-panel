"""Exercise the delivered layout, rather than only source imports."""
import importlib
from pathlib import Path
import subprocess
import sys

from ma2panel import release

ROOT = Path(__file__).resolve().parents[1]


def test_payload_runs_without_source_tree(tmp_path):
    files = release.build(ROOT, version='3.2.0+structure-test')
    assert 'ma2panel/bridge.py' in files
    assert 'ma2panel/resources/mock/sample_export.xml' in files
    assert 'config.json' not in files and 'settings.json' not in files
    release.write_tree(files, tmp_path)
    # Both supported entry points work from outside the repository.
    for command in ([sys.executable, str(tmp_path / 'bridge.py'), '--help'],
                    [sys.executable, '-m', 'ma2panel', '--help']):
        result = subprocess.run(command, cwd=tmp_path, capture_output=True, timeout=15)
        assert result.returncode == 0, result.stderr.decode(errors='replace')
    code = 'from ma2panel import mock; assert mock.SAMPLE.is_file(); assert mock.REAL_EXPORT.is_file(); assert mock.TYPE_LIST.is_file()'
    result = subprocess.run([sys.executable, '-c', code], cwd=tmp_path, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode(errors='replace')


def test_all_backend_modules_import():
    for path in (ROOT / 'ma2panel').glob('*.py'):
        if path.stem not in ('__init__', '__main__'):
            importlib.import_module('ma2panel.' + path.stem)
