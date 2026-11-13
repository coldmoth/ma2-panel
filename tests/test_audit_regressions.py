import xml.etree.ElementTree as ET

import pytest
from ma2panel.fixtures import parse_fixture_type
from ma2panel.quality_diagnostics import _xml
from ma2panel.mock import MockMA2


@pytest.mark.parametrize('attribute', ['Shutter1', 'Shutter2', 'Strobe1', 'Zoom1', 'Focus1'])
def test_anonymized_fixturetype_retains_parser_semantics(attribute):
    text = f'''<FixtureType name="PRIVATE PERSON"><Module><ChannelType attribute="{attribute}" coarse="1">
    <ChannelFunction name="Open Private" from_dmx="0" to_dmx="25"/>
    <ChannelSet name="Strobe Private" from_dmx="26" to_dmx="255"/>
    </ChannelType><ChannelType attribute="ColorRGB1" coarse="2"/></Module></FixtureType>'''
    safe = _xml(text, {})
    assert b'PRIVATE' not in safe and b'Private' not in safe
    assert parse_fixture_type(safe) == parse_fixture_type(text)

@pytest.mark.parametrize('name', ['QA_NOT_A_MA2_RED', 'QA_NOT_A_MA2_GREEN', 'QA_NOT_A_MA2_BLUE'])
def test_console_rejects_invented_panel_attributes(name):
    desk = MockMA2('qa', None)
    desk.configure_simulation({'fixtures': [{'id': 1}], 'attrs': {'color': {'names': [name] * 3}}})
    desk.strict_console = True
    desk._reply('Fixture 1')
    assert 'Error' in desk._reply(f'Attribute "{name}" At 100')
    assert desk.simulation_output()[1]['rgb'] == [100, 100, 100]


def test_console_rejects_unknown_commands_ranges_and_unsupported_features():
    desk = MockMA2('qa', None)
    desk.configure_simulation({'fixtures': [{'id': 1}, {'id': 60}], 'attrs': {}})
    desk.strict_console = True
    desk._reply('Fixture 1')
    assert 'Error' in desk._reply('DoInventedThing')
    assert 'Error' in desk._reply('Attribute "Pan" At 999')
    desk._reply('Fixture 60')
    assert 'Error' in desk._reply('Attribute "Focus" At 20')


def test_dataset_keeps_technical_params_and_strobe_ranges():
    import json
    from ma2panel import quality_diagnostics as quality
    from test_quality_diagnostics import inputs
    cfg,settings,state,link=inputs()
    cfg['fixtures'][0]['params']=['Pan','Tilt','Shutter1','PRIVATE PERSON']
    spec=cfg['dmx_map'][cfg['fixtures'][0]['type']]
    spec['strobe']={'attr':'Shutter1','open':0,'from':10.2,'to':100}
    data=json.loads(quality.collect(cfg,settings,state,link)['dataset.json'])
    assert data['fixtures'][0]['params']==['Pan','Tilt','Shutter1']
    assert data['dmx_map']['type-1']['strobe']==spec['strobe']


def test_console_group_command_selects_independent_membership():
    desk=MockMA2('qa',None)
    desk.configure_simulation({'fixtures':[{'id':n} for n in (1,2,3,55,56)]})
    desk.strict_console=True
    desk._reply('Fixture 1 + 2 + 3')
    assert 'Error' not in desk._reply('Group 2')
    assert desk.sim_selection==[55,56]
    assert 'Error' in desk._reply('Group 999')
