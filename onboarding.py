"""Passive, localhost-only first-run information. Never sends MA2 commands."""
import asyncio
import io
from ipaddress import IPv4Address

import segno
from fastapi import Request
from fastapi.responses import JSONResponse, Response


def tablet_urls(bind, port, addresses):
    if bind in ('127.0.0.1', 'localhost', '::1'):
        return []
    usable = set()
    for value in addresses:
        try:
            address = IPv4Address(value)
        except ValueError:
            continue
        if (address.is_loopback or address.is_link_local or address.is_multicast
                or address.is_unspecified or address.is_reserved):
            continue
        if bind not in ('0.0.0.0', '::', str(address)):
            continue
        usable.add(str(address))
    return [f'http://{address}:{port}/' for address in sorted(usable)]


def register(app, settings, link, is_loopback, addresses, *, mock=False):
    bind, port = settings.get('bind', '127.0.0.1'), settings.get('port', 8080)

    def local(request):
        return is_loopback(request) and request.url.hostname in ('localhost', '127.0.0.1', '::1')

    async def urls():
        return tablet_urls(bind, port, await asyncio.to_thread(addresses))

    @app.get('/api/setup')
    async def status(request: Request):
        if not local(request):
            return JSONResponse({'ok': False, 'err': 'Мастер доступен только на основном ПК через localhost.'}, status_code=403)
        return {'ok': True, 'instance': app.state.instance, 'bind': bind, 'port': port,
                'lan_enabled': bind not in ('127.0.0.1', 'localhost', '::1'),
                'urls': await urls(), 'mock': mock,
                'ma2': {'host': link.host, 'port': link.port, 'user': link.user,
                        'state': link.state, 'ready': link.ready, 'halted': link.halted,
                        'profile': link.vars.get('USERPROFILE') if link.ready else None,
                        'version': link.vars.get('VERSION') if link.ready else None}}

    @app.get('/api/setup/qr')
    async def qr(request: Request, address: str = ''):
        if not local(request):
            return JSONResponse({'ok': False}, status_code=403)
        target = f'http://{address}:{port}/'
        if target not in await urls():
            return JSONResponse({'ok': False, 'err': 'Адрес больше не доступен. Обновите список.'}, status_code=400)
        data = io.BytesIO()
        segno.make_qr(target).save(data, kind='svg', scale=5, border=4, light='white')
        return Response(data.getvalue(), media_type='image/svg+xml', headers={'Cache-Control': 'no-store'})
