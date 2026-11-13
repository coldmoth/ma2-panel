"""Exercise the real CPython callback and Server bookkeeping without network I/O."""
import asyncio
import sys
from asyncio.proactor_events import _ProactorBasePipeTransport

import pytest

from ma2panel import bridge


class ResetSocket:
    def __init__(self, winerror=10054):
        self.closed = False
        self.winerror = winerror

    def fileno(self):
        return -1 if self.closed else 42

    def shutdown(self, how):
        error = ConnectionResetError('peer reset during shutdown')
        error.winerror = self.winerror
        raise error

    def close(self):
        self.closed = True


def install(loop, monkeypatch, platform='win32', version=(3, 12, 10)):
    with monkeypatch.context() as patch:
        patch.setattr(sys, 'platform', platform)
        patch.setattr(sys, 'version_info', version)
        bridge.install_windows_transport_recovery(loop)


@pytest.mark.parametrize('close_first', [False, True])
@pytest.mark.parametrize('winerror', [10054, 10053])
def test_reset_during_native_transport_shutdown_releases_server(monkeypatch, close_first, winerror):
    async def run():
        loop = asyncio.get_running_loop()
        delegated = []
        loop.set_exception_handler(lambda loop, context: delegated.append(context))
        install(loop, monkeypatch)
        server = asyncio.base_events.Server(loop, [], None, None, 100, None)
        server._attach()
        lost = []
        class Protocol(asyncio.Protocol):
            def connection_lost(self, exc):
                lost.append(exc)
        protocol = Protocol()
        transport = _ProactorBasePipeTransport.__new__(_ProactorBasePipeTransport)
        transport._loop, transport._sock = loop, ResetSocket(winerror)
        transport._server, transport._protocol = server, protocol
        transport._called_connection_lost, transport._closing = False, True
        sock = transport._sock
        if close_first:
            server.close()
        waiter = asyncio.create_task(server.wait_closed())
        loop.call_soon(transport._call_connection_lost, None)
        await asyncio.sleep(0)
        if not close_first:
            server.close()
        await asyncio.sleep(0)
        try:
            if winerror != 10054:
                assert not waiter.done()
                assert not sock.closed
                assert server._active_count == 1
                assert len(delegated) == 1
                assert delegated[0]['exception'].winerror == winerror
                return
            assert waiter.done(), 'reset leaked an attached transport: Server.wait_closed is blocked'
            assert sock.closed
            assert server._active_count == 0
            assert lost == [None]  # Never replay protocol or application cleanup.
            assert transport._called_connection_lost
            assert not delegated
            transport._call_connection_lost(None)
            assert lost == [None]
        finally:
            if transport._sock is not None:
                sock.close()
                transport._sock = None
                server._detach()
                transport._server = None
                transport._called_connection_lost = True
            waiter.cancel()
            await asyncio.gather(waiter, return_exceptions=True)
    asyncio.run(run())


@pytest.mark.parametrize('platform,version', [('linux', (3, 12, 10)), ('win32', (3, 13, 0))])
def test_other_platforms_keep_existing_handler(monkeypatch, platform, version):
    async def run():
        loop = asyncio.get_running_loop()
        handler = lambda loop, context: None
        loop.set_exception_handler(handler)
        install(loop, monkeypatch, platform, version)
        assert loop.get_exception_handler() is handler
    asyncio.run(run())


@pytest.mark.parametrize('winerror', [10054, 10053])
def test_unrelated_callback_errors_are_delegated(monkeypatch, winerror):
    async def run():
        loop = asyncio.get_running_loop()
        delegated = []
        loop.set_exception_handler(lambda loop, context: delegated.append(context))
        install(loop, monkeypatch)
        error = ConnectionResetError('unrelated application callback')
        error.winerror = winerror
        def fail():
            raise error
        loop.call_soon(fail)
        await asyncio.sleep(0)
        assert len(delegated) == 1
        assert delegated[0]['exception'] is error
    asyncio.run(run())
