import asyncio
from contextlib import suppress

import pytest
from ma2panel.mock_console import is_read_only
from test_bridge import connect, wait_state, bridge_cfg, ask, ready, until

COMMANDS=['Goto Cue 1 Executor 1.101','Off Executor 1.101','ClearAll','Fixture 1 At 20',
          'Master 2.1 At 20','StoreLook Executor 1.105','Go Executor 1.101']


@pytest.mark.parametrize('command',COMMANDS)
@pytest.mark.parametrize('phase',['before-send','after-apply'])
def test_complete_reconnect_stream_has_no_mutation_replay(command,phase):
    async def run():
        mock,link,task=await connect()
        try:
            await wait_state(link,'logged_in',2)
            link.timeout=.15
            initial=len(mock.received)
            if phase=='before-send':
                await link._lock.acquire()
                pending=asyncio.create_task(link.send(command));await asyncio.sleep(0)
                mock.paused=True;mock.drop()
                for _ in range(100):
                    if not link.ready:break
                    await asyncio.sleep(.01)
                link._lock.release()
                ok,_=await pending
                assert not ok
                assert command not in mock.received[initial:]
            else:
                original=mock._reply
                def apply_then_disconnect(text):
                    reply=original(text)
                    if text==command:
                        mock.paused=True;mock.drop()
                    return reply
                mock._reply=apply_then_disconnect
                ok,_=await link.send(command)
                assert not ok and link.last['status']=='unknown'
                assert mock.received[initial:]==[command]
            cutoff=len(mock.received)
            mock.paused=False
            await wait_state(link,'logged_in',3)
            # A full read barrier observes the reconnected stream without light actions.
            assert (await link.send('ListVar'))[0]
            assert all(is_read_only(c) for c in mock.received[cutoff:]),mock.received[cutoff:]
            assert mock.received[initial:].count(command)==(phase=='after-apply')
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):await task
            mock.drop()
    asyncio.run(run())


def test_compound_scene_disconnect_keeps_unknown_and_stops_remaining_commands(bridge_cfg):
    with bridge_cfg() as (ws,mock,app):
        original=mock._reply
        applied=[]
        def disconnect(text):
            reply=original(text)
            if text.startswith(('Goto Cue ', 'Go Executor ')):
                applied.append(text);mock.drop()
            return reply
        mock._reply=disconnect
        result=ask(ws,{'a':'scene_go','id':'pianist','request_id':'compound-drop'})
        assert not result['ok'] and result['outcome']=='unknown'
        assert applied
        cutoff=len(mock.received)
        until(ws,lambda m:m.get('status',{}).get('ma2')=='logged_in')
        assert all(is_read_only(c) for c in mock.received[cutoff:]),mock.received[cutoff:]
        assert len(applied)==1
