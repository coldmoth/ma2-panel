import hashlib
import json
from pathlib import Path

import pytest
from ma2panel.fixtures import parse_export
from scripts.quality_dataset import load


def test_real_v2_is_pinned_and_not_advertised_as_v3():
    manifest, config = load('field-v2')
    assert manifest['show'] == 'big room v2'
    assert manifest['ma2_version'] == '3.9.60'
    assert manifest['complete'] is False
    fixtures = config['fixtures']
    assert [f['id'] for f in fixtures] == list(range(1, 17)) + list(range(23, 31))
    assert fixtures[0]['address'] == '1.200' and fixtures[-1]['address'] == '1.360'
    assert not config.get('dmx_map')  # missing real FixtureType must remain unknown
    assert not config.get('ma2groups')  # no invented membership
    assert config['show'] == manifest['show']
    assert manifest['missing']


def test_no_fabricated_v3_or_silent_profile_fallback():
    with pytest.raises(ValueError): load('field-v3')
    with pytest.raises(ValueError): load('../field-v2')
