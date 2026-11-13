"""All scenario profiles; same application runner for source and delivered ZIP."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.browser_smoke import run


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--bundle', type=Path)
    args = p.parse_args()
    results = []
    for profile in ('clean', 'field-v2', 'synthetic', 'field-start'):
        folder = args.output.resolve() / profile
        script = 'field_regression_browser.cjs' if profile == 'field-start' else 'regression_browser.cjs'
        run(folder, 'node', ROOT / 'scripts' / script, profile=profile, bundle=args.bundle)
        checks = json.loads((folder / 'scenarios.json').read_text(encoding='utf-8'))
        if {c['engine'] for c in checks} != {'chromium', 'webkit'} or any(c['status'] != 'success' for c in checks):
            raise RuntimeError('Incomplete browser evidence')
        results.extend(checks)
    (args.output / 'summary.json').write_text(json.dumps({'checks': results, 'site_evidence': 'V2 equals V3 per owner; FixtureType/membership incomplete', 'physical': 'not tested'}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'{len(results)} scenario checks passed; FixtureType/membership completeness and physical light remain unconfirmed')


if __name__ == '__main__': main()
