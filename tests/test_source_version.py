"""The source VERSION follows project metadata; bundles retain release identity."""
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/generate_version.py'


def test_generate_and_refresh_source_version(tmp_path):
    metadata = tmp_path / 'pyproject.toml'
    for value in ('3.1.0rc1', '3.1.0'):
        metadata.write_text(f'[project]\nversion = "{value}"\n')
        result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(tmp_path)], capture_output=True)
        assert result.returncode == 0, result.stderr.decode()
        assert (tmp_path / 'VERSION').read_text() == value + '\n'


def test_bad_metadata_preserves_previous_version(tmp_path):
    (tmp_path / 'VERSION').write_text('previous\n')
    (tmp_path / 'pyproject.toml').write_text('[project]\n')
    result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(tmp_path)], capture_output=True)
    assert result.returncode != 0
    assert (tmp_path / 'VERSION').read_text() == 'previous\n'
