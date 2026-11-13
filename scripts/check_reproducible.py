"""Reproduce the browser suite from a clean exact SHA, locked deps and a minimal env."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts.first_run_zip import clean_environment


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sha',required=True);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];output=a.output.resolve();output.mkdir(parents=True,exist_ok=True)
    sha=subprocess.check_output(['git','rev-parse',a.sha+'^{commit}'],cwd=root,text=True).strip()
    if sha != a.sha: raise ValueError('Use the full exact commit SHA')
    env=clean_environment();env['UV_NO_CONFIG']='1'
    with tempfile.TemporaryDirectory(prefix='ma2 clean commit ') as temp:
        checkout=Path(temp)/'source'
        npmrc=Path(temp)/'empty.npmrc';npmrc.write_text('');env['NPM_CONFIG_USERCONFIG']=str(npmrc)
        subprocess.run(['git','worktree','add','--detach',str(checkout),sha],cwd=root,check=True,capture_output=True)
        try:
            assert not subprocess.check_output(['git','status','--porcelain'],cwd=checkout)
            commands=[['uv','sync','--locked'],['npm','ci','--prefix','scripts/browser_smoke','--ignore-scripts'],
                      ['node','scripts/browser_smoke/node_modules/playwright/cli.js','install','chromium','webkit'],
                      ['uv','run','--no-sync','python','scripts/run_quality_browser.py','--output',str(output/'browser')],
                      ['uv','run','--no-sync','python','scripts/check_import_regression.py','--output',str(output/'negative-import')],
                      ['uv','run','--no-sync','python','scripts/check_field_regression.py','--output',str(output/'negative-color')],
                      ['uv','run','--no-sync','python','scripts/package_release.py','--archive',str(output/'candidate.zip')],
                      ['uv','run','--no-sync','python','scripts/release_lifecycle.py','--previous',str(output/'previous-3.3.0.zip'),'--candidate',str(output/'candidate.zip'),'--output',str(output/'lifecycle')]]
            with (output/'run.log').open('wb') as log:
                for cmd in commands:
                    result=subprocess.run(cmd,cwd=checkout,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
                    if result.returncode:raise RuntimeError('Clean checkout failed: '+str(cmd)+'; see '+str(output/'run.log'))
            assert not subprocess.check_output(['git','status','--porcelain'],cwd=checkout), 'Tests changed committed source'
            report={'source_sha':sha,'status':'success','environment':'minimal; no MA2/PYTHONPATH/developer config','untracked_source':False, 'lifecycle':json.loads((output/'lifecycle/result.json').read_text()),
                    'checks':json.loads((output/'browser/summary.json').read_text())['checks']}
            (output/'reproducibility.json').write_text(json.dumps(report,indent=2)+'\n')
        finally:
            # This checkout and all generated, ignored dependencies belong to this process.
            subprocess.run(['git','worktree','remove','--force',str(checkout)],cwd=root,check=True,capture_output=True)
    print('PASS: browser suite and negative import from clean commit '+sha)


if __name__=='__main__':main()
