"""A fresh release must require an operator to choose the actual console."""
import json
from pathlib import Path

from ma2panel.safety import effective_safety, validate_settings


def test_public_templates_require_explicit_console_and_allow_no_lighting():
    root = Path(__file__).resolve().parents[1]
    settings = json.loads((root / 'ma2panel/resources/settings.example.json').read_text())
    config = json.loads((root / 'ma2panel/resources/config.example.json').read_text())
    validate_settings(settings)
    assert settings['ma2']['host'] == 'ma2-unconfigured.invalid'
    assert settings['bind'] == '127.0.0.1'
    assert not settings.get('mock') and not config.get('mock')
    safety = effective_safety(settings)
    assert safety['mode'] == 'test'
    assert safety['allowed_fixtures'] == safety['allowed_scenes'] == []
    assert not safety['allow_master'] and not safety['allow_page_change']
    assert config['fixtures'] == config['scenes'] == config['groups'] == []
