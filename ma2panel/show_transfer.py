"""Browser show-file operations. A confirmation ID can start its MA2 command only once."""
import asyncio
import ipaddress
import json
import re
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.requests import ClientDisconnect

from .commands import ActionError, is_error_reply
from . import show_files as files

FILE_WAIT = 120
STABLE_SECONDS = 1
OFFER_TTL = 300
MAX_OPERATIONS = 32
MAX_TEMP_BYTES = 2 * 1024 * 1024 * 1024


async def disk(fn, *args):
    # Cancellation must not race a worker still publishing/copying a file.
    task = asyncio.create_task(asyncio.to_thread(fn, *args))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


def register(app, c):
    operations = {}
    workspace = tempfile.TemporaryDirectory(prefix='ma2-show-')
    root = Path(workspace.name)
    app.state.show_files_workspace = workspace
    app.state.show_files_operations = operations
    busy = None
    uploading = False

    def space(amount):
        used = sum(p.stat().st_size for p in root.iterdir() if p.is_file())
        if used + amount > MAX_TEMP_BYTES or shutil.disk_usage(root).free < amount + 16 * 1024 * 1024:
            raise ValueError('недостаточно места для временного файла; завершите операции или освободите диск')

    def public(op):
        return {k: v for k, v in op.items() if not k.startswith('_')}

    def fail(message, status=400):
        return JSONResponse({'ok': False, 'err': c.mask(str(message))}, status_code=status)

    def trusted(request, mutate=False):
        try:
            host = urlsplit('http://' + request.headers.get('host', ''))
            origin = urlsplit(request.headers.get('origin', ''))
            hostname = host.hostname or ''
            # No DNS hostnames except localhost: closes DNS rebinding on an unauthenticated LAN panel.
            valid_host = hostname == 'localhost' or bool(ipaddress.ip_address(hostname))
            good_origin = not request.headers.get('origin') or (
                origin.scheme in ('http', 'https') and origin.netloc == host.netloc
                and not (origin.path or origin.query or origin.fragment or origin.username))
            return valid_host and good_origin and (not mutate or request.headers.get('x-show-files') == '1')
        except ValueError:
            return False

    def folder():
        host = c.ma2.get('host', '127.0.0.1')
        if not c.mock and host not in ('localhost', '127.0.0.1', '::1'):
            raise ValueError('обмен файлами доступен только с локальной MA2 onPC')
        value = c.ma2.get('shows_dir')
        path = Path(value) if isinstance(value, str) and value else None
        if path is None or not path.is_absolute() or not path.is_dir() or path.is_symlink():
            raise ValueError('на основном ПК задайте ma2.shows_dir: каталог shows текущей установки MA2')
        if c.mock and not path.resolve().is_relative_to(Path(c.config_path).parent.resolve()):
            raise ValueError('в mock каталог шоу должен находиться внутри каталога изолированного config')
        return path.resolve()

    def available(kind):
        if busy or c.state['loading']:
            raise ActionError('выполняется операция шоу; дождитесь результата')
        if not c.link.ready or c.link.halted:
            raise ActionError('нет готового подключения MA2 или передача остановлена')
        if kind in ('load', 'save') and c.safety.get('allow_show_' + kind) is not True:
            raise ActionError('операция запрещена: allow_show_' + kind)
        return folder()

    def new(kind, name, **values):
        if len(operations) >= MAX_OPERATIONS:
            raise ValueError('достигнут лимит временных операций; перезапустите мост после завершения работы')
        oid = uuid.uuid4().hex
        op = {'ok': True, 'id': oid, 'kind': kind, 'name': name, 'state': 'confirm', 'reason': '',
              '_created': time.monotonic(), '_gen': c.link._gen, '_epoch': c.state['plan_epoch'],
              '_stop': c.link._stop_epoch,
              '_show': c.state['show']['name'], **values}
        operations[oid] = op
        return op

    async def identity():
        ok, reply = await c.link.send('ListVar')
        if not ok:
            raise ActionError('имя текущего шоу не подтверждено')
        name = c.show_from(reply).get('name')
        if not name:
            raise ActionError('имя текущего шоу не распознано')
        c.update_show(c.show_from(reply))
        return name

    def source_for(base, name):
        if not isinstance(name, str) or not name or name in ('.', '..') or any(x in name for x in '/\\:\x00'):
            raise ValueError('небезопасное имя шоу MA2')
        path = base / (name + '.show.gz')
        files.regular(path)
        return path

    def connection(op):
        if (c.link._gen != op['_gen'] or c.link._stop_epoch != op['_stop']
                or not c.link.ready or c.link.halted):
            raise ActionError('подключение или передача изменились; старое согласие недействительно')

    def fresh(op):
        connection(op)
        if (time.monotonic() - op['_created'] > OFFER_TTL
                or c.state['plan_epoch'] != op['_epoch'] or c.state['show']['name'] != op['_show']):
            raise ActionError('подтверждение устарело: заново выберите файл/операцию')

    async def stage(op, value, reason=''):
        op['state'], op['reason'] = value, c.mask(reason)
        c.state['show_file'] = public(op)
        await c.broadcast(c.status_msg())

    async def checked_send(command, op):
        fresh(op)
        if command == 'SelectDrive 1':
            c.export_extra.add(command)
        try:
            if why := c.guard(command):
                raise ActionError(why)
            ok, reply = await c.link.send(command, gen=op['_gen'])
            if not ok:
                raise ActionError(reply or 'команда не подтверждена')
        finally:
            if command == 'SelectDrive 1':
                c.export_extra.discard(command)

    async def run(op):
        nonlocal busy
        wrote = False
        try:
            if op['kind'] == 'load':
                async def before():
                    fresh(op)
                    if await identity() != op['_show']:
                        raise ActionError('текущее шоу изменилось; загрузка отменена')
                    await stage(op, 'checking', 'Проверяю файл и список MA2')
                    if (await disk(files.snapshot, op['_file'], root / (op['id'] + '-check')))['sha256'] != op['_sha256']:
                        raise ValueError('переданный файл изменился')
                    target = await disk(files.publish, op['_file'], op['_folder'], op['name'])
                    op['_published'], op['_published_fingerprint'] = target, files.regular(target)
                    await checked_send('SelectDrive 1', op)
                    await stage(op, 'loading', 'Ожидаю подтверждения загрузки MA2')
                # load_show owns action_lock and checks fresh ListShows after before().
                def sent(value):
                    nonlocal wrote
                    wrote = value
                def verify():
                    connection(op)
                    if files.regular(op['_published']) != op['_published_fingerprint']:
                        raise ValueError('файл шоу изменился перед LoadShow; загрузка отменена')
                result = await c.load_show({'name': op['name'], 'confirm_name': op['name'], 'ack_unsaved': True}, before=before, sent=sent, verify=verify, expected_gen=op['_gen'])
                if not result.get('ok'):
                    raise ActionError('загрузка не подтверждена')
                await stage(op, 'done', 'MA2 подтвердил имя загруженного шоу')
            else:
                async with c.action_lock:
                    fresh(op)
                    if not c.link.ready or c.link.halted or c.state['loading']:
                        raise ActionError('MA2 недоступна или идёт загрузка')
                    if await identity() != op['name']:
                        raise ActionError('текущее шоу изменилось; операция отменена')
                    source = source_for(op['_folder'], op['name'])
                    if files.regular(source) != op['_fingerprint']:
                        raise ActionError('сохранённый файл изменился; подтвердите новую версию')
                    if op['kind'] == 'save':
                        if not c.safety.get('allow_show_save'):
                            raise ActionError('сохранение запрещено')
                        await stage(op, 'backup', 'Сохраняю резервную копию прежнего файла')
                        backup = Path(c.config_path).parent / 'backups'
                        backup.mkdir(exist_ok=True)
                        await disk(files.snapshot, source, backup / ('show-' + op['id'] + '.show.gz'))
                        await checked_send('SelectDrive 1', op)
                        await stage(op, 'saving', 'Ожидаю обновления файла MA2')
                        wrote = True
                        await checked_send('SaveShow', op)
                        deadline, last, stable = time.monotonic() + FILE_WAIT, None, time.monotonic()
                        while time.monotonic() < deadline:
                            if not c.link.ready or c.link.halted or c.link._gen != op['_gen']:
                                raise ActionError('связь прервана во время записи')
                            try:
                                current = files.regular(source)
                            except (ValueError, OSError):
                                current = None
                            if current != last:
                                last, stable = current, time.monotonic()
                            if current and current != op['_fingerprint'] and time.monotonic() - stable >= STABLE_SECONDS:
                                break
                            await asyncio.sleep(.1)
                        else:
                            raise ActionError('обновление файла после SaveShow не подтверждено')
                        if await identity() != op['name']:
                            raise ActionError('после записи MA2 сообщает другое шоу')
                    await stage(op, 'checking', 'Проверяю и копирую файл для скачивания')
                    target = root / (op['id'] + '-download.show.gz')
                    info = await disk(files.snapshot, source, target)
                    op.update(size=info['size'], sha256=info['sha256'], mtime=info['mtime'], _download=target)
                    await stage(op, 'ready', 'Файл готов. Сохранение на устройство выполняет браузер')
        except asyncio.CancelledError:
            op.update(state='unknown', reason='мост остановлен; операция не повторяется')
            raise
        except (ActionError, ValueError, OSError) as exc:
            unknown = wrote or (op['kind'] == 'load' and c.state['show_load'].get('state') == 'unknown')
            await stage(op, 'unknown' if unknown else 'failed', str(exc))
        finally:
            busy = None
            c.state['show_file_active'] = None
            if op.get('_request'):
                c.record(op['_request'], json.dumps({'a': 'show_file_' + op['kind'], 'id': op['id']}),
                         {**public(op), 'ok': op['state'] in ('ready', 'done')})
            await c.broadcast(c.status_msg())

    @app.post('/api/show-files/upload')
    async def upload(request: Request):
        nonlocal uploading
        if not trusted(request, True):
            return fail('запрос запрещён: Host/Origin/X-Show-Files', 403)
        if uploading:
            return fail('уже передаётся файл шоу', 409)
        uploading = True
        temp = root / (uuid.uuid4().hex + '.upload')
        verified = root / (temp.stem + '-verified')
        keep = False
        try:
            base = available('load')
            space(files.MAX_FILE * 2)
            if len(operations) >= MAX_OPERATIONS:
                raise ValueError('слишком много временных операций')
            name = request.query_params.get('name', '')
            if (not name.lower().endswith('.show.gz') or len(name) > 240
                    or any(ch in name for ch in '/\\:\x00') or any(ord(ch) < 32 for ch in name)):
                raise ValueError('выберите файл .show.gz без пути')
            size = 0
            async with asyncio.timeout(FILE_WAIT):
                with temp.open('xb') as dest:
                    async for block in request.stream():
                        size += len(block)
                        if size > files.MAX_FILE:
                            raise ValueError('файл превышает 512 МиБ')
                        dest.write(block)
            info = await disk(files.snapshot, temp, verified)
            temp.unlink()
            alias = re.sub(r'[^A-Za-z0-9_-]', '_', name[:-8])[:40].strip('_') or 'show'
            async with c.action_lock:
                available('load')
                await identity()
                op = new('load', alias + '_panel_' + uuid.uuid4().hex[:12], original=name, size=size,
                         _folder=base, _file=verified, _sha256=info['sha256'])
            keep = True
            return public(op)
        except (ActionError, ValueError, OSError, ClientDisconnect, TimeoutError) as exc:
            return fail(exc)
        finally:
            temp.unlink(missing_ok=True)
            if not keep:
                verified.unlink(missing_ok=True)
            uploading = False

    @app.post('/api/show-files/prepare')
    async def prepare(request: Request):
        if not trusted(request, True):
            return fail('запрос запрещён: Host/Origin/X-Show-Files', 403)
        try:
            body = await request.json()
            if uploading:
                raise ActionError('дождитесь окончания передачи файла')
            kind = body.get('kind') if isinstance(body, dict) else None
            if kind not in ('save', 'download'):
                raise ValueError('неизвестная операция')
            base = available(kind)
            async with c.action_lock:
                name = await identity()
                source = source_for(base, name)
                info = files.regular(source)
                op = new(kind, name, size=info[2], mtime=info[3] / 1e9, _fingerprint=info, _folder=base)
            return public(op)
        except (ActionError, ValueError, OSError) as exc:
            return fail(exc)

    @app.get('/api/show-files/{oid}')
    async def status(oid: str, request: Request):
        if not trusted(request):
            return fail('запрос запрещён', 403)
        op = operations.get(oid)
        return public(op) if op else fail('операция неизвестна этому запуску моста; команда не повторена', 404)

    @app.post('/api/show-files/{oid}/confirm')
    async def confirm(oid: str, request: Request):
        nonlocal busy
        if not trusted(request, True):
            return fail('запрос запрещён', 403)
        op = operations.get(oid)
        if op is None:
            return fail('операция неизвестна; команда не повторена', 404)
        try:
            body = await request.json()
            if (not isinstance(body, dict) or body.get('confirm_name') != op['name']
                    or (op['kind'] == 'load' and body.get('ack_unsaved') is not True)
                    or (op['kind'] == 'save' and body.get('ack_overwrite') is not True)):
                raise ValueError('подтвердите точное имя и замену текущих данных')
            if op['state'] != 'confirm':
                return public(op)  # same ID never sends another command
            if uploading:
                raise ActionError('дождитесь окончания передачи файла')
            available(op['kind'])
            if c.action_lock.locked():
                raise ActionError('другая операция MA2 ещё выполняется; дождитесь результата')
            fresh(op)
            space(files.MAX_FILE)
            busy = oid
            c.state['show_file_active'] = oid
            c.throttle.clear()
            op['state'] = 'queued'
            op['_request'] = request
            task = asyncio.create_task(run(op))
            c.bg.add(task)
            task.add_done_callback(c.bg.discard)
            return public(op)
        except (ActionError, ValueError, OSError) as exc:
            return fail(exc)

    @app.get('/api/show-files/{oid}/download')
    async def download(oid: str, request: Request):
        if not trusted(request):
            return fail('запрос запрещён', 403)
        op = operations.get(oid)
        if not op or op['state'] != 'ready':
            return fail('готового снимка файла нет; проверьте состояние операции', 409)
        return FileResponse(op['_download'], media_type='application/octet-stream', filename=op['name'] + '.show.gz',
                            headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
