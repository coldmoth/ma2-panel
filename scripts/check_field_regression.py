"""Dropping parsed RGB evidence must fail the empty-install browser scenario."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.browser_smoke import run, ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        run(args.output.resolve(), 'node', ROOT / 'scripts/field_regression_browser.cjs',
            profile='field-start', mutation='color-capability')
    except subprocess.CalledProcessError:
        checks = json.loads((args.output / 'scenarios.json').read_text())
        failed = [c for c in checks if c['status'] != 'success']
        assert len(failed) == 1 and failed[0]['name'] == 'empty-install-import-patch-and-types', checks
        assert 'undefined !== 2' in failed[0]['error'], failed
        print('PASS: loss of parsed RGB evidence fails the empty-install control scenario')
        return
    raise RuntimeError('Loss of color evidence incorrectly passed')


if __name__ == '__main__':
    main()
