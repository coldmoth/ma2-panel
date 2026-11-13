"""Passive readiness and local, structured test captures. Never calls a console."""
import hashlib
import asyncio
from contextlib import asynccontextmanager, suppress
import io
import json
import math
import re
import secrets
import time
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

from fastapi import Request
from fastapi.responses import JSONResponse, Response


def digest(data):
    return hashlib.sha256(data).hexdigest()


def recovery_pending(root):
    from .data_transfer import _settled
    try:
        _settled(Path(root))
        return False
    except (OSError, ValueError):
        return True


def capability(cfg, settings, state, link, fixture_id, attribute, *, hidden=False):
    if not link.ready:
        return 'disconnected'
    if hidden:
        return 'hidden'
    safety = settings.get('safety', {})
    feature = settings.get('features', {}).get('move' if attribute in ('pan', 'tilt') else attribute)
    allowed = safety.get('allowed_fixtures', [])
    if feature is False or isinstance(feature, str) and feature or link.halted or safety.get('mode') != 'full' or allowed and fixture_id not in allowed:
        return 'blocked'
    fixture = next((f for f in cfg.get('fixtures', []) if f.get('id') == fixture_id), None)
    if not fixture or fixture.get('missing'):
        return 'pending'
    kind = fixture.get('type', '')
    spec = cfg.get('dmx_map', {}).get(kind)
    if spec and spec.get('unsupported'):
        return 'unsupported'
    if not spec or spec.get('stale') or 'has' not in spec:
        number = re.match(r'^(\d+)\b', kind)
        trace = state.get('type_reads', {}).get(number[1]) if number else None
        if trace and trace.get('error') or any(t.get('kind') == kind and t.get('error') for t in state.get('type_reads', {}).values()):
            return 'read_error'
        return 'pending'
    if attribute == 'color':
        supported = all(type(spec.get(k)) is int for k in ('r', 'g', 'b'))
    elif attribute == 'dim':
        supported = type(spec.get('dim')) is int
    elif attribute in ('pan', 'tilt'):
        supported = any(str(p).lower() == attribute for p in fixture.get('params', []))
        if not supported: return 'pending'  # guessed "moves" is not confirmed profile evidence
    else:
        supported = attribute in spec.get('has', [])
    return 'supported' if supported else 'unsupported'


def readiness(cfg, settings, state, link):
    checks = []
    def add(key, status, reason, action):
        checks.append({'id': key, 'status': status, 'reason': reason, 'action': action})
    add('connection', 'pass' if link.ready else 'fail',
        'Вход в MA2 подтверждён.' if link.ready else 'Нет подтверждённого входа в MA2.',
        'Проверьте сеть, Telnet и пользователя в мастере подключения.')
    expected, actual = cfg.get('show'), state.get('show', {}).get('name')
    match = bool(expected and actual and expected == actual)
    add('show', 'pass' if match else 'fail' if expected and actual else 'unknown',
        'Открыто привязанное шоу.' if match else 'Открыто другое шоу.' if expected and actual else 'Не определено ожидаемое или текущее шоу.',
        'Сверьте имя шоу на onPC и привязку плана; не запускайте сцены другого шоу.')
    fixtures = [f for f in cfg.get('fixtures', []) if not f.get('missing')]
    fresh = state.get('read_freshness', {})
    add('fixtures', 'pass' if fixtures and fresh.get('fixtures') else 'unknown',
        'Приборы загружены в этом подключении.' if fixtures and fresh.get('fixtures') else 'Свежая загрузка приборов не подтверждена.',
        'Разрешённым действием получите приборы и проверьте Patch.')
    patched = bool(fixtures) and all(re.fullmatch(r'[1-9]\d*\.(?:\d{3})', str(f.get('address', ''))) for f in fixtures)
    add('patch', 'pass' if patched else 'unknown', 'Адреса Patch известны.' if patched else 'У части приборов неизвестен Patch.', 'Получите свежий экспорт Fixture/Patch.')
    groups = cfg.get('groups', []) or cfg.get('ma2groups', [])
    add('groups', 'pass' if groups and fresh.get('ma2') else 'unknown', 'Группы прочитаны.' if groups and fresh.get('ma2') else 'Свежесть или состав групп не подтверждены.', 'Прочитайте группы; локальные группы проверьте отдельно.')
    kinds = {f.get('type') for f in fixtures}
    maps = cfg.get('dmx_map', {})
    attrs = bool(kinds) and all(k in maps and 'has' in maps[k] and not maps[k].get('stale') for k in kinds)
    add('attributes', 'pass' if attrs else 'unknown', 'Карты атрибутов прочитаны.' if attrs else 'Данные атрибутов неполны или устарели.', 'Проверьте чтение FixtureType; не угадывайте каналы по названию.')
    safety = settings.get('safety', {})
    add('permissions', 'pass' if safety.get('mode') == 'full' and not link.halted else 'blocked',
        'Действия ограничены действующими разрешениями.' if safety.get('mode') == 'full' and not link.halted else 'Управление ограничено режимом или остановлено.',
        'Проверьте нужные разрешения; полный доступ автоматически не включается.')
    meta = state.get('values_meta', {}).get('live', {})
    dmx = meta.get('source') == 'ma2' and meta.get('freshness') == 'fresh' and link.ready
    add('readback', 'pass' if dmx else 'blocked' if not settings.get('dmx_seconds', 0) else 'unknown',
        'Есть свежие данные DMX.' if dmx else 'DMX выключен, неизвестен или устарел.',
        'Проверьте разрешение чтения, профиль типа и диагностику DMX. Mock не подтверждает реальный свет.')
    conflict = state.get('recovery_pending', False)
    add('recovery', 'blocked' if conflict else 'pass', 'Незавершённое восстановление.' if conflict else 'Конфликт восстановления не обнаружен.', 'Сохраните данные и завершите штатное recovery перед переносом или обновлением.')
    return {'ready': all(c['status'] == 'pass' for c in checks), 'checks': checks,
            'capabilities': [{'id': f['id'], **{a: capability(cfg, settings, state, link, f['id'], a) for a in ('dim', 'color', 'pan', 'tilt')}} for f in fixtures]}


def _num(value, low, high):
    return value if type(value) in (int, float) and math.isfinite(value) and low <= value <= high else None


def technical_attribute(value):
    return isinstance(value, str) and bool(re.fullmatch(
        r'(?:DIM|DIMMER|PAN|TILT|COLORRGB[123]|COLORMIX[123]|(?:ZOOM|FOCUS|STROBE|SHUTTER)[0-9]{0,3})', value, re.I))


def _xml(text, aliases):
    tags = set('MA Info Fixture FixtureType No SubFixture Patch Address AbsolutePosition Location Rotation Scaling Channel Modules Module ChannelType ChannelSet ChannelFunction LogicalChannel Function Attribute Instances Instance'.split())
    numbers = set('fixture_id channel_id index coarse fine patch from to from_dmx to_dmx dmx_from dmx_to physical_from physical_to module_index x y z'.split())
    def node(old):
        tag = old.tag.split('}')[-1]
        if tag not in tags: return None
        new = ET.Element(tag)
        for key, value in old.attrib.items():
            if key in numbers and re.fullmatch(r'-?\d{1,9}(?:\.\d{1,8})?', value): new.set(key, value)
            elif key in ('name', 'attribute'):
                label = value.strip().lower()
                canonical = None
                if tag in ('ChannelSet', 'ChannelFunction'):
                    if label in ('open', 'shutter open'): canonical = 'Open'
                    elif 'open' in label: canonical = 'Open range'
                    elif label in ('closed', 'shutter closed'): canonical = 'Closed'
                    elif 'strob' in label: canonical = 'Strobe'
                new.set(key, canonical or (value if technical_attribute(value) else aliases.get(value, 'item')))
        if old.text and re.fullmatch(r'\s*-?\d{1,9}(?:\.\d{1,8})?\s*', old.text): new.text = old.text.strip()
        for child in old:
            safe = node(child)
            if safe is not None: new.append(safe)
        return new
    safe = node(ET.fromstring(text))
    if safe is None: raise ValueError('Unsupported XML root')
    return ET.tostring(safe, encoding='utf-8')


def collect(cfg, settings, state, link, *, root=None):
    """Allowlist numeric structure; no credentials, arbitrary strings, paths or logs."""
    kinds = {kind: f'type-{i + 1}' for i, kind in enumerate(sorted({str(f.get('type', '')) for f in cfg.get('fixtures', [])}))}
    dataset = {'version': 5, 'show': 'show-1', 'fixtures': [], 'groups': [], 'scenes': [], 'dmx_map': {}}
    for f in cfg.get('fixtures', []):
        if type(f.get('id')) is not int or not 1 <= f['id'] <= 999999:
            continue
        item = {'id': f['id'], 'label': f'fixture-{f["id"]}', 'type': kinds[str(f.get('type', ''))], 'params': [a for a in f.get('params', []) if technical_attribute(a)]}
        address = str(f.get('address', ''))
        if re.fullmatch(r'[1-9]\d{0,3}\.(?:00[1-9]|0[1-9]\d|[1-4]\d\d|50\d|51[0-2])', address):
            item['address'] = address
        for k in ('x', 'y'):
            if _num(f.get(k), 0, 1) is not None:
                item[k] = f[k]
        for k in ('moves', 'missing'):
            if type(f.get(k)) is bool:
                item[k] = f[k]
        for k in ('footprint', 'channels'):
            if type(f.get(k)) is int and 1 <= f[k] <= 512:
                item[k] = f[k]
        dataset['fixtures'].append(item)
    ids = {f['id'] for f in dataset['fixtures']}
    dataset['ma2groups'] = [{'n': g['n'], 'name': f'ma2-group-{g["n"]}', 'ids': [n for n in g.get('ids', []) if type(n) is int and n in ids]}
                            for g in cfg.get('ma2groups', []) if type(g.get('n')) is int and 1 <= g['n'] <= 9999]
    for i, g in enumerate(cfg.get('groups', [])):
        dataset['groups'].append({'id': f'group-{i + 1}', 'label': f'group-{i + 1}', 'fixtures': [n for n in g.get('fixtures', []) if type(n) is int and n in ids]})
    for i, s in enumerate(cfg.get('scenes', [])):
        if re.fullmatch(r'\d{1,4}\.\d{1,4}', str(s.get('exec', ''))):
            dataset['scenes'].append({'id': f'scene-{i + 1}', 'label': f'scene-{i + 1}', 'exec': s['exec']})
    for kind, spec in cfg.get('dmx_map', {}).items():
        if kind not in kinds or not isinstance(spec, dict):
            continue
        item = {k: v for k, v in spec.items() if k in ('dim', 'r', 'g', 'b') and type(v) is int and 1 <= v <= 512}
        if isinstance(spec.get('has'), list):
            item['has'] = [k for k in spec['has'] if k in ('pan', 'tilt', 'zoom', 'focus', 'strobe')]
        for k in ('unsupported', 'stale'):
            if type(spec.get(k)) is bool:
                item[k] = spec[k]
        strobe = spec.get('strobe')
        if isinstance(strobe, dict) and technical_attribute(strobe.get('attr')):
            safe = {k: strobe[k] for k in ('open', 'from', 'to') if _num(strobe.get(k), 0, 100) is not None}
            if len(safe) == 3: item['strobe'] = {'attr': strobe['attr'], **safe}
        dataset['dmx_map'][kinds[kind]] = item
    hall = cfg.get('hall', {})
    if _num(hall.get('w'), 1, 1000) and _num(hall.get('d'), 1, 1000):
        dataset['hall'] = {k: hall[k] for k in ('w', 'd')}
        if hall.get('stage') in ('top', 'bottom', 'left', 'right'):
            dataset['hall']['stage'] = hall['stage']
        if _num(hall.get('stageDepth'), 0, 1000) is not None:
            dataset['hall']['stageDepth'] = hall['stageDepth']
    version = link.vars.get('VERSION', '')
    mock = state.get('mock') if type(state.get('mock')) is bool else None
    manifest = {'schema': 1, 'origin': 'mock-panel-snapshot' if mock is True else 'passive-panel-snapshot' if mock is False else 'unverified-panel-snapshot', 'mock': mock, 'complete': False,
                'ma2_version': version if isinstance(version, str) and re.fullmatch(r'\d{1,4}(?:\.\d{1,4}){1,4}', version) else None,
                'show_matches': bool(cfg.get('show') and cfg.get('show') == state.get('show', {}).get('name')),
                'missing': ['Свежий оригинал Patch/XML и FixtureType с подтверждённым происхождением',
                            'Подтверждённый состав групп MA2', 'Измерение физических приборов'],
                'privacy': 'Names replaced; no logs, host addresses, paths, login or passwords. No console commands.'}
    files = {'dataset.json': dataset, 'readiness.json': readiness(cfg, settings, state, link)}
    encoded = {name: json.dumps(value, ensure_ascii=False, indent=2).encode() for name, value in files.items()}
    manifest['captures'] = []
    if root is not None:
        folder = Path(root) / 'diag'
        if folder.is_dir() and not folder.is_symlink():
            paths = [folder / 'last_export.xml', *sorted(folder.glob('fixture_type_*.xml'))[:32]]
            for path in paths:
                if not re.fullmatch(r'(?:last_export|fixture_type_\d{1,6})\.xml', path.name) or path.is_symlink() or not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
                    continue
                try:
                    data = path.read_bytes()
                    encoded['captures/' + path.name] = _xml(data, kinds)
                    manifest['captures'].append({'file': path.name, 'source_sha256': digest(data), 'historical': True, 'sanitized': True})
                except (OSError, ValueError, ET.ParseError):
                    manifest['captures'].append({'file': path.name, 'unavailable': True})
    manifest['files'] = {name: {'size': len(data), 'sha256': digest(data)} for name, data in encoded.items()}
    encoded['manifest.json'] = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
    return encoded


def pack(files):
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(zipfile.ZipInfo(name, (2020, 1, 1, 0, 0, 0)), data)
    return out.getvalue()


def register(app, snapshot, is_loopback, *, root=None):
    cached = {}
    original_lifespan = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(current):
        async with original_lifespan(current) as value:
            current.state.quality = readiness(*snapshot())
            async def observe():
                while True:
                    await asyncio.sleep(2)
                    current.state.quality = readiness(*snapshot())
            task = asyncio.create_task(observe())
            try:
                yield value
            finally:
                task.cancel()
                with suppress(asyncio.CancelledError): await task
    app.router.lifespan_context = lifespan
    def local(request):
        return is_loopback(request) and request.url.hostname in ('localhost', '127.0.0.1', '::1')
    @app.get('/api/quality/readiness')
    async def status(request: Request):
        if not local(request):
            return JSONResponse({'ok': False}, status_code=403)
        return readiness(*snapshot())
    @app.post('/api/testing/preview')
    async def preview(request: Request):
        if not local(request):
            return JSONResponse({'ok': False}, status_code=403)
        files = await asyncio.to_thread(collect, *snapshot(), root=root)
        data, token = pack(files), secrets.token_hex(24)
        cached.clear()
        cached[token] = (time.monotonic(), data)
        return {'token': token, 'sha256': digest(data), 'bytes': len(data),
                'files': json.loads(files['manifest.json'])['files'],
                'missing': json.loads(files['manifest.json'])['missing']}
    @app.get('/api/testing/download/{token}')
    async def download(token: str, request: Request):
        if not local(request):
            return JSONResponse({'ok': False}, status_code=403)
        item = cached.get(token)
        if not item or time.monotonic() - item[0] > 300:
            cached.clear()
            return JSONResponse({'ok': False, 'err': 'Сначала обновите предварительный просмотр.'}, status_code=404)
        return Response(item[1], media_type='application/zip', headers={'Content-Disposition': 'attachment; filename="ma2-testing.zip"', 'Cache-Control': 'no-store'})
