"""REL-015: every manual Identify attempt is visible, never undoable."""
import asyncio
import pytest
from ma2panel.commands import ActionError
from test_status_evidence import context  # noqa: F401


@pytest.mark.parametrize('on', [True, False])
@pytest.mark.parametrize('outcome', ['sent', 'error', 'unknown'])
def test_identify_attempt_history(context, on, outcome):
    c = context
    c.safety['allow_rdm'] = True
    calls = []
    async def send(line, **kw):
        calls.append(line)
        c.link.last = {'cmd': line, 'status': outcome}
        return outcome == 'sent', 'OK' if outcome == 'sent' else 'timeout' if outcome == 'unknown' else 'Error refused'
    c.link.send = send
    async def go():
        try:
            await c.patch_action('rdm_identify', {'uid': '43500F019FCB', 'on': on})
        except ActionError:
            assert outcome != 'sent'
        entries = c.history_msg()['history']
        assert len(entries) == 1
        assert all(part in entries[0]['what'] for part in ('43500F019FCB', 'On' if on else 'Off', outcome))
        assert not entries[0]['undo']
        assert len(calls) == 1
    asyncio.run(go())
