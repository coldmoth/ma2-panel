import asyncio
import json
import pytest
from test_status_evidence import context  # noqa: F401


@pytest.mark.parametrize('phase', ['starting', 'collecting', 'stopping', 'unknown'])
def test_blackout_is_refused_before_waiting_for_rdm_lock(context, phase):
    c = context
    async def go():
        ws = object()
        c.sessions[ws] = {'selection': [], 'base': None}
        c.rdm._active = True
        c.rdm._state['phase'] = phase
        c.rdm._state['off_state'] = 'unknown'
        sent = []
        async def send(line, **kw):
            sent.append(line)
            return True, 'ok'
        c.link.send = send
        await c.action_lock.acquire()
        try:
            reply = await asyncio.wait_for(c.handle(ws, json.dumps({'a': 'blackout'})), .1)
            assert not reply['ok'] and 'RDM' in reply['err']
            assert not sent
            assert c.rdm._active and c.rdm._state['off_state'] == 'unknown'
        finally:
            c.action_lock.release()
    asyncio.run(go())
