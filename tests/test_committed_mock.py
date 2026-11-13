from ma2panel.mock import MockMA2


def test_committed_mock_exposes_output_without_local_files():
    desk = MockMA2('qa', None)
    desk.configure_simulation({'fixtures': [{'id': 1}]})
    desk._reply('Fixture 1'); desk._reply('At 25')
    assert desk.simulation_output()[1]['dim'] == 25
