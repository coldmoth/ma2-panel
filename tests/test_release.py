import hashlib
import json
import os
import posixpath
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import zipfile

from ma2panel import release


DOCS = ('quality-audit-fixes-2026-11-13.md', 'quality-verification-2026-11-12.md', 'QUALITY-GATES.md', 'testing-infrastructure-audit.md', 'OPERATIONS.md', 'SETUP.md', 'USAGE.md', 'RELEASE-3.0.md', 'RELEASE-3.1.md', 'pre-hall-3.1.md', 'phase1-windows-smoke.md', 'browser-preflight.md', 'audit-step3-executors.md', 'audit-step5-programmer.md', 'audit-step6-blackout.md', 'audit-step7-scenes.md', 'update-usb.txt', 'spec.md', 'CODEMAP.md', 'code-index.md', 'hall-test-plan.md', 'outgoing-commands.md', 'ma2-syntax.md', 'archive/spec-history.md', 'superpowers/specs/2026-10-30-tablet-ui-design.md', 'RELEASE-3.2.md', 'RELEASE-3.3.md', 'ONPC-HALL-TEST-3.2.md', 'hardware-acceptance.md', 'ma2-command-evidence.md')


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'source'
        self.root.mkdir()
        for name in (*('docs/' + d for d in DOCS), 'README.md', 'docs/CHANGELOG.md', 'LICENSE', 'bridge.py', 'update.py', 'static/a.js', 'scripts/win/run.bat', 'uv.lock', 'settings.json', 'logs/log.txt', 'lib/private.py', 'static/__pycache__/bad.pyc'):
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(name.encode())
        (self.root / 'pyproject.toml').write_text('[project]\nversion="3.0"\n')
        self.archive = Path(self.tmp.name) / 'package.zip'

    def files(self):
        return release.build(self.root, version='3.0+abc')

    def test_payload_layout_and_exclusions(self):
        files = release.payload(self.root)
        expected = {'bridge.py', 'update.py', 'static/a.js', 'run.bat', 'README-RU.md', 'CHANGELOG.md', 'docs/LICENSE.txt'} | {'docs/' + d for d in DOCS}
        self.assertEqual(set(files), expected)
        self.assertEqual(files['README-RU.md'], b'README.md')

    def test_license_is_shipped_and_validated_in_zip(self):
        license_text = b'GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\n'
        (self.root / 'LICENSE').write_bytes(license_text)
        (self.root / 'README.md').write_text('[License](LICENSE)')
        (self.root / 'docs/RELEASE-3.1.md').write_text('[License](../LICENSE)')
        files = self.files()
        self.assertEqual(files.get('docs/LICENSE.txt'), license_text)
        self.assertNotIn('LICENSE', files)
        self.assertEqual(files['README-RU.md'], b'[License](docs/LICENSE.txt)')
        self.assertEqual(files['docs/RELEASE-3.1.md'], b'[License](LICENSE.txt)')
        self.assertEqual((self.root / 'README.md').read_text(), '[License](LICENSE)')
        self.assertEqual((self.root / 'docs/RELEASE-3.1.md').read_text(), '[License](../LICENSE)')
        release.write_zip(files, self.archive)
        manifest = release.check(self.archive)
        self.assertEqual(manifest['files']['docs/LICENSE.txt']['sha256'], hashlib.sha256(license_text).hexdigest())
        with zipfile.ZipFile(self.archive) as archive:
            self.assertEqual(archive.read('docs/LICENSE.txt'), license_text)
        files['docs/LICENSE.txt'] = b'changed license'
        release.write_zip(files, self.archive)
        with self.assertRaises(ValueError):
            release.check(self.archive)

    def test_missing_license_refuses_build(self):
        (self.root / 'LICENSE').unlink()
        with self.assertRaises(FileNotFoundError):
            self.files()

    def test_missing_doc(self):
        (self.root / 'docs' / DOCS[-1]).unlink()
        with self.assertRaises(FileNotFoundError):
            release.payload(self.root)

    def test_symlink(self):
        try:
            (self.root / 'static/link').symlink_to(self.root / 'bridge.py')
        except OSError:
            self.skipTest('symlinks unavailable')
        with self.assertRaises(ValueError):
            release.payload(self.root)

    def test_deterministic_build_zip_and_tree(self):
        full = self.files()
        update = self.files()
        self.assertEqual(full, update)
        release.write_zip(full, self.archive)
        first = self.archive.read_bytes()
        release.write_zip(update, self.archive)
        self.assertEqual(first, self.archive.read_bytes())
        manifest = release.check(self.archive)
        self.assertEqual(manifest['version'], '3.0+abc')
        self.assertEqual(manifest['runtime']['lock_sha256'], hashlib.sha256(b'uv.lock').hexdigest())
        with zipfile.ZipFile(self.archive) as z:
            self.assertEqual(z.namelist(), sorted(full))
            self.assertTrue(all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in z.infolist()))
        target = Path(self.tmp.name) / 'tree'
        release.write_tree(full, target)
        self.assertEqual({p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob('*') if p.is_file()}, full)

    def test_compact_windows_bundle_keeps_update_root_and_runtime(self):
        (self.root / 'scripts/win/start.bat').write_bytes(b'@echo off\r\nexit /b 0\r\n')
        files = self.files()
        bundle = Path(self.tmp.name) / 'space in path' / 'ma2-panel'
        program = bundle / 'program'
        release.write_tree(files, program)
        for name, contents in {'python/python.exe': b'embedded runtime',
                               'lib/one.py': b'dependency',
                               'settings.json': b'{"port":8080}',
                               'config.json': b'{"fixtures":[]}'}.items():
            path = program / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(contents)
        release.record_runtime(program)
        release.write_windows_launcher(bundle)
        self.assertEqual({p.name for p in bundle.iterdir()}, {'start.bat', 'program'})
        self.assertEqual((program / 'start.bat').read_bytes(), files['start.bat'])
        self.assertEqual((program / 'python/python.exe').read_bytes(), b'embedded runtime')
        self.assertEqual(self.files(), files)  # Outer launcher never enters the update payload.
        release.write_zip(files, self.archive)
        self.assertEqual(release.check(self.archive)['version'], '3.0+abc')
        archive = shutil.make_archive(str(bundle.parent / 'windows'), 'zip', bundle.parent, 'ma2-panel')
        with zipfile.ZipFile(archive) as packed:
            members = {i.filename for i in packed.infolist() if not i.is_dir()}
            self.assertEqual({name.split('/')[1] for name in members}, {'start.bat', 'program'})
            for name, contents in files.items():
                self.assertEqual(packed.read('ma2-panel/program/' + name), contents)
            self.assertNotIn('program/start.bat', release.check(self.archive)['files'])

    @unittest.skipUnless(os.name == 'nt', 'Windows batch execution needs cmd.exe')
    def test_outer_launcher_forwards_quoted_arguments_and_exit_code(self):
        bundle = Path(self.tmp.name) / 'space in path' / 'ma2-panel'
        program = bundle / 'program'
        program.mkdir(parents=True)
        (program / 'start.bat').write_bytes(
            b'@echo off\r\n> "%~dp0received.txt" echo %~1\r\nexit /b 7\r\n')
        release.write_windows_launcher(bundle)
        # /s strips the outer pair; retain quotes around both the batch path and its argument.
        command = f'cmd.exe /d /s /c ""{bundle / "start.bat"}" "value with spaces""'
        completed = subprocess.run(command, capture_output=True, timeout=10)
        self.assertEqual(completed.returncode, 7, completed.stderr)
        self.assertEqual((program / 'received.txt').read_text().strip(), 'value with spaces')

    def test_identity_no_clock(self):
        def response(args, **kwargs):
            return subprocess.CompletedProcess(args, 0, 'abc\n' if 'rev-parse' in args else ' M bridge.py\n', '')
        with patch('subprocess.run', side_effect=response):
            self.assertEqual(release.identity(self.root), '3.0+abc-dirty')
        with patch('subprocess.run', side_effect=OSError):
            self.assertEqual(release.identity(self.root), '3.0+nogit')

    def test_mutation(self):
        files = self.files()
        files['bridge.py'] += b'changed'
        release.write_zip(files, self.archive)
        with self.assertRaises(ValueError):
            release.check(self.archive)

    def test_extra_missing(self):
        for kind in ('extra', 'missing'):
            files = self.files()
            if kind == 'extra':
                files['other.py'] = b'x'
            else:
                del files['update.py']
            release.write_zip(files, self.archive)
            with self.assertRaises(ValueError):
                release.check(self.archive)

    def test_unsafe_and_colliding_names(self):
        for names in [('.. /x.py',), ('../x.py',), ('/x.py',), ('C:x.py',), ('static/a\\b',), ('static/CON.txt',), ('static/a.',), ('static/a ',), ('static/a\x01',), ('static/A', 'static/a'), ('static/A', 'static/a/b')]:
            with self.subTest(names=names):
                with zipfile.ZipFile(self.archive, 'w') as z:
                    for name in names:
                        z.writestr(name, b'x')
                with self.assertRaises(ValueError):
                    release.check(self.archive)

    def test_runtime_mismatch(self):
        release.write_zip(self.files(), self.archive)
        self.assertEqual(release.check(self.archive, release.runtime(self.root))['schema'], 1)
        with self.assertRaises(ValueError):
            release.check(self.archive, {'python': '3.11'})
        with self.assertRaises(RuntimeError):
            release.check(self.archive, {})

    def test_manifest_validation_and_zip_symlink(self):
        for field, value in [('schema', True), ('version', ''), ('files', []), ('runtime', {})]:
            files = self.files()
            m = json.loads(files['program-manifest.json'])
            m[field] = value
            files['program-manifest.json'] = json.dumps(m).encode()
            release.write_zip(files, self.archive)
            with self.assertRaises(ValueError):
                release.check(self.archive)
        with zipfile.ZipFile(self.archive, 'w') as z:
            i = zipfile.ZipInfo('bridge.py')
            i.create_system = 3
            i.external_attr = 0o120777 << 16
            z.writestr(i, b'target')
        with self.assertRaises(ValueError):
            release.check(self.archive)


if __name__ == '__main__':
    unittest.main()


def test_changed_embedded_runtime_refuses_update(tmp_path):
    (tmp_path / 'python').mkdir()
    (tmp_path / 'python/python.exe').write_bytes(b'python')
    (tmp_path / 'lib').mkdir()
    (tmp_path / 'lib/one.py').write_bytes(b'library')
    release.record_runtime(tmp_path)
    release.verify_runtime(tmp_path)
    (tmp_path / 'lib/one.py').write_bytes(b'changed')
    import pytest
    with pytest.raises(ValueError, match='Python/lib'):
        release.verify_runtime(tmp_path)


def test_hall_and_candidate_protocol_links_are_shipped():
    files = release.payload(Path(__file__).resolve().parents[1])
    required = {'docs/' + name for name in (
        'pre-hall-3.1.md', 'phase1-windows-smoke.md', 'browser-preflight.md', 'audit-step3-executors.md',
        'audit-step5-programmer.md', 'audit-step6-blackout.md', 'audit-step7-scenes.md')}
    assert required <= set(files)
    for name in ('docs/hall-test-plan.md', 'docs/RELEASE-3.1.md',
                 'docs/pre-hall-3.1.md', 'docs/browser-preflight.md'):
        for target in re.findall(r'\]\(([^)]+)\)', files[name].decode('utf-8')):
            if '://' in target or target.startswith('#'):
                continue
            destination = posixpath.normpath(posixpath.join(posixpath.dirname(name), target.split('#')[0]))
            assert destination in files, (name, target, destination)
    assert b'](https://github.com/coldmoth/ma2-panel/blob/main/.github/workflows/ci.yml)' in files['docs/browser-preflight.md']


def test_every_markdown_link_resolves_inside_delivered_zip(tmp_path):
    # Read only the delivered archive; the checkout must not satisfy missing targets.
    source = Path(__file__).resolve().parents[1]
    archive = tmp_path / 'delivered.zip'
    release.write_zip(release.build(source, version='test-links'), archive)
    release.check(archive)
    with zipfile.ZipFile(archive) as packed:
        files = {name: packed.read(name) for name in packed.namelist()}
    broken = []
    for name, data in files.items():
        if not name.endswith('.md'):
            continue
        text = data.decode('utf-8')
        for label, target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)', text):
            if re.match(r'[a-z][a-z0-9+.-]*:', target, re.I):
                continue
            path, _, anchor = target.partition('#')
            dest = posixpath.normpath(posixpath.join(posixpath.dirname(name), path)) if path else name
            if dest not in files:
                broken.append((name, target))
                continue
            if anchor and dest.endswith('.md'):
                headings = re.findall(r'^#{1,6}\s+(.+)', files[dest].decode('utf-8'), re.M)
                slugs = [re.sub(r'[^\w\- ]', '', heading.lower()).replace(' ', '-') for heading in headings]
                assert anchor in slugs, (name, target)
    assert broken == []


def test_packaged_readme_alias_and_missing_target(tmp_path, monkeypatch):
    import pytest
    monkeypatch.setattr(release, 'DOCS', ())
    (tmp_path / 'docs').mkdir()
    for name, data in {'README.md': '[history](docs/CHANGELOG.md)',
                       'docs/CHANGELOG.md': '[home](../README.md)', 'LICENSE': 'license'}.items():
        (tmp_path / name).write_text(data)
    files = release.payload(tmp_path)
    assert files['CHANGELOG.md'] == b'[home](README-RU.md)'
    (tmp_path / 'README.md').write_text('[typo](absent.md)')
    with pytest.raises(ValueError, match='missing documentation target'):
        release.payload(tmp_path)
