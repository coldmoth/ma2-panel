"""Pinned public field snapshots, deliberately separate from synthetic capabilities."""
import hashlib
import json
from pathlib import Path

from ma2panel.fixtures import parse_export

ROOT = Path(__file__).resolve().parents[1]


def load(profile):
    if profile != 'field-v2':
        raise ValueError('No confirmed dataset for this profile; v3 is incomplete.')
    manifest = json.loads((ROOT / 'tests/data/ma2-v2/manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Field dataset SHA256 mismatch')
    cfg = json.loads((ROOT / 'ma2panel/resources/config.example.json').read_text(encoding='utf-8'))
    cfg.update(show=manifest['show'], fixtures=parse_export((ROOT / 'ma2panel/resources/mock/real_export_3.9.60.xml').read_text(encoding='utf-8')))
    return manifest, cfg
