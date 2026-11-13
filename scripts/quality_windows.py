"""Run new quality/migration tests under the existing Windows process watchdog."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ci_windows_tests import run

if __name__ == '__main__':
    names = ('quality_diagnostics', 'quality_delivery', 'quality_gates', 'quality_lifecycle', 'data_transfer',
             'field_fixture_dataset', 'stable_quality', 'audit_regressions', 'committed_mock', 'reconnect_stream', 'first_run_zip', 'migration_v5', 'data_startup', 'onboarding')
    command = [sys.executable, '-u', '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
               '--junitxml=test-results/windows-quality/pytest.xml',
               '--basetemp=test-results/windows-quality/tmp',
               *(str(ROOT / 'tests' / f'test_{n}.py') for n in names)]
    output = ROOT / 'test-results/windows-quality'
    result = run(command, output, timeout=300)
    if result:
        print((output / 'pytest.log').read_text(encoding='utf-8', errors='replace'))
    sys.exit(result)
