import asyncio
import pytest
from test_status_evidence import context  # noqa: F401


@pytest.mark.parametrize('busy', ['fade', 'operation', 'loading', 'http', 'rdm', 'lock', 'transition'])
def test_shutdown_gate_refuses_admitted_work(context, busy):
    c = context
    async def go():
        if busy == 'fade': c.throttle.fades['accepted'] = object()
        if busy == 'operation': c.active_operations['accepted'] = {}
        if busy == 'loading': c.state['loading'] = 'A'
        if busy == 'http': c.app.state.active_http = 1
        if busy == 'rdm': c.rdm._active = True
        if busy == 'lock': await c.action_lock.acquire()
        if busy == 'transition':
            task = asyncio.create_task(asyncio.sleep(10))
            c.bg.add(task)
        assert not await c.update_gate()
        assert not c.app.state.updating
        if busy == 'lock': c.action_lock.release()
        if busy == 'transition':
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    asyncio.run(go())
