"""Narrow workaround for reset-on-close in the shipped CPython 3.12 Proactor.

A failing sock.shutdown in _call_connection_lost skips socket.close and
Server._detach, so Server.wait_closed never finishes (CPython 3.12.10,
Lib/asyncio/proactor_events.py:165). Finish only that interrupted cleanup;
never replay the protocol callback or change the event-loop implementation.
"""
import asyncio
import logging
import sys


log = logging.getLogger('bridge')


def install_windows_transport_recovery(loop):
    if sys.platform != 'win32' or sys.version_info[:2] != (3, 12):
        return
    from asyncio.proactor_events import _ProactorBasePipeTransport

    previous = loop.get_exception_handler()

    def delegate(current, context):
        if previous is None:
            current.default_exception_handler(context)
        else:
            previous(current, context)

    def recover(current, context):
        error = context.get('exception')
        callback = getattr(context.get('handle'), '_callback', None)
        transport = getattr(callback, '__self__', None)
        method = _ProactorBasePipeTransport._call_connection_lost
        if (not isinstance(error, ConnectionResetError)
                or getattr(error, 'winerror', None) != 10054
                or getattr(callback, '__func__', None) is not method
                or transport._called_connection_lost
                or transport._sock is None
                or not isinstance(transport._server, asyncio.base_events.Server)):
            delegate(current, context)
            return
        if not any(frame.tb_frame.f_code is method.__code__ for frame in _traceback_frames(error)):
            delegate(current, context)
            return
        try:
            transport._sock.close()
        except OSError:
            delegate(current, context)
            return
        transport._sock = None
        transport._server._detach()
        transport._server = None
        transport._called_connection_lost = True
        log.warning('Windows: освобождён серверный транспорт после сброса соединения при shutdown (10054)')

    loop.set_exception_handler(recover)


def _traceback_frames(error):
    frame = error.__traceback__
    while frame is not None:
        yield frame
        frame = frame.tb_next
