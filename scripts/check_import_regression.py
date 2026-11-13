"""A broken UI ma2_import call must fail the real browser scenario."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.browser_smoke import run, ROOT


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    try:
        run(a.output.resolve(),'node',ROOT/'scripts/regression_browser.cjs',profile='synthetic',mutation='ma2-import')
    except subprocess.CalledProcessError:
        results=json.loads((a.output/'scenarios.json').read_text(encoding='utf-8'))
        failures=[c for c in results if c['status']!='success']
        assert len(failures)==1 and failures[0]['name']=='import-console-groups-through-ui', results
        print('PASS: disabling UI ma2_import is detected by the group membership/output scenario')
        return
    raise RuntimeError('Broken UI import incorrectly passed')


if __name__=='__main__':main()
