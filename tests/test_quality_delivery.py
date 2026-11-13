from pathlib import Path

from ma2panel import release


def test_delivered_mock_has_the_same_public_fixture_assets():
    files = release.payload(Path(__file__).resolve().parents[1])
    for name in ('sample_export.xml', 'real_export_3.9.60.xml', 'list_fixturetype_3.9.60.txt'):
        assert files['ma2panel/resources/mock/' + name] == Path('ma2panel/resources/mock', name).read_bytes()
    for name in ('QUALITY-GATES.md', 'OPERATIONS.md'):
        assert 'docs/' + name in files
