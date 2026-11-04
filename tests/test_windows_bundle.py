"""Packaging checks independent of network and Windows runtime execution."""
import hashlib
import importlib.util
import os
from pathlib import Path
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/build_windows.py'


def builder():
    spec = importlib.util.spec_from_file_location('build_windows', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_is_reproducible_with_changed_timestamps(tmp_path):
    tree = tmp_path / 'tree'
    (tree / 'ma2-panel/program/python').mkdir(parents=True)
    (tree / 'ma2-panel/start.bat').write_bytes(b'launcher')
    binary = tree / 'ma2-panel/program/python/python.exe'
    binary.write_bytes(b'runtime')
    first, second = tmp_path / 'first.zip', tmp_path / 'second.zip'
    builder().write_bundle(tree, first)
    os.utime(binary, (1800000000, 1800000000))
    builder().write_bundle(tree, second)
    assert hashlib.sha256(first.read_bytes()).digest() == hashlib.sha256(second.read_bytes()).digest()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ['ma2-panel/program/python/python.exe', 'ma2-panel/start.bat']
        assert archive.testzip() is None
