"""Generate the source VERSION; release.build supplies the bundle's full identity."""
import argparse
from pathlib import Path
import tomllib


def generate(root):
    root = Path(root)
    metadata = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf-8'))
    version = metadata.get('tool', {}).get('ma2panel', {}).get('release-version', metadata['project']['version'])
    if not isinstance(version, str) or not version or version.strip() != version or any(c.isspace() for c in version):
        raise ValueError('Invalid project version')
    (root / 'ma2panel').mkdir(exist_ok=True)
    (root / 'ma2panel/VERSION').write_text(version + '\n', encoding='utf-8')
    return version


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    print(generate(parser.parse_args().root))
