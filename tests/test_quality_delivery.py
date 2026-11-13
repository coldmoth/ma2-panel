from pathlib import Path

from ma2panel import release


def test_delivered_mock_has_the_same_public_fixture_assets():
    files = release.payload(Path(__file__).resolve().parents[1])
    for name in ('sample_export.xml', 'real_export_3.9.60.xml', 'list_fixturetype_3.9.60.txt'):
        assert files['ma2panel/resources/mock/' + name] == Path('ma2panel/resources/mock', name).read_bytes()
    for name in ('QUALITY-GATES.md', 'OPERATIONS.md'):
        assert 'docs/' + name in files


def test_package_script_runs_with_minimal_environment(tmp_path):
    import subprocess
    import sys
    from scripts.first_run_zip import clean_environment
    source = Path(__file__).resolve().parents[1]
    archive = tmp_path / 'candidate.zip'
    result = subprocess.run([sys.executable,str(source/'scripts/package_release.py'),'--archive',str(archive)],
                            cwd=source,env=clean_environment(),capture_output=True,text=True,timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert release.check(archive)['version'].startswith('3.3.1+')
