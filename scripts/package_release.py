"""One program payload for Windows, USB and LAN; no local site data is read."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

from generate_version import generate

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import release


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tree', type=Path)
    parser.add_argument('--archive', type=Path, default=ROOT / 'dist/update/ma2-panel-update.zip')
    args = parser.parse_args()
    generate(ROOT)
    files = release.build(ROOT)
    args.archive.parent.mkdir(parents=True, exist_ok=True)
    release.write_zip(files, args.archive)
    digest = hashlib.sha256(args.archive.read_bytes()).hexdigest()
    Path(str(args.archive) + '.sha256').write_text(f'{digest}  {args.archive.name}\n')
    if args.tree:
        release.write_tree(files, args.tree)
        release.record_runtime(args.tree)
        (args.tree / 'runtime.json').write_text(json.dumps(release.runtime(ROOT), sort_keys=True) + '\n')
    print(f"{json.loads(files['program-manifest.json'])['version']}: {len(files)} files")


if __name__ == '__main__':
    main()
