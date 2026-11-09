"""Bounded numeric readback evidence; no names, paths, Lua source or addresses."""
import math
import re


def _number(value, low=0, high=1000000, integer=False):
    if type(value) not in ((int,) if integer else (int, float)):
        return None
    return value if low <= value <= high and math.isfinite(value) else None


def _errors(text):
    return [int(n) for n in re.findall(r'\bError #([0-9]{1,4})\b', text)[:16]]


def build_readback(diag, cfg, clean):
    export = diag.get('export')
    export = export if isinstance(export, dict) else {}
    login = diag.get('login_vars')
    rights = clean(login.get('USERRIGHTS')).strip().strip('"').lower() if isinstance(login, dict) else ''
    out = {'enabled': export.get('allow_fixture_read') if type(export.get('allow_fixture_read')) is bool else None,
           'poll_seconds': _number(export.get('dmx_seconds'), high=86400),
           'rights': 'admin' if rights == 'admin' else 'other' if rights in ('none', 'view', 'setup', 'program', 'playback') else 'unknown',
           'fixtures': [], 'types': [], 'dmx': None, 'truncated': False}
    fixtures = cfg.get('fixtures')
    fixtures = fixtures if isinstance(fixtures, list) else []
    maps = cfg.get('dmx_map')
    maps = maps if isinstance(maps, dict) else {}
    reads = export.get('type_reads')
    reads = reads if isinstance(reads, dict) else {}
    kinds = []
    out['truncated'] = len(fixtures) > 64
    for fixture in fixtures[:64]:
        f = fixture if isinstance(fixture, dict) else {}
        kind = f.get('type') if isinstance(f.get('type'), str) else ''
        if kind not in kinds and len(kinds) < 32:
            kinds.append(kind)
            spec = maps.get(kind)
            spec = spec if isinstance(spec, dict) else {}
            no = re.match(r'(\d+) ', kind)
            trace = reads.get(no[1]) if no else None
            trace = trace if isinstance(trace, dict) else {}
            out['types'].append({'channels': {k: spec[k] for k in ('dim', 'r', 'g', 'b')
                                             if _number(spec.get(k), 1, 64, integer=True) is not None},
                                 'mapped': bool(spec), 'stale': spec.get('stale') is True,
                                 'unsupported': spec.get('unsupported') is True,
                                 'export': 'failed' if trace.get('error') else 'read' if 'spec' in trace else 'pending' if trace else 'not_attempted',
                                 'errors': _errors(clean(trace.get('reply'))),
                                 'size': _number(trace.get('size'), integer=True)})
        if kind not in kinds:
            out['truncated'] = True
        address = re.fullmatch(r'(\d{1,3})\.(\d{1,3})', str(f.get('address') or ''))
        out['fixtures'].append({'type': kinds.index(kind) + 1 if kind in kinds else None,
                                'patched': bool(address and 1 <= int(address[1]) <= 256 and 1 <= int(address[2]) <= 512),
                                'missing': f.get('missing') is True,
                                'footprint': _number(f.get('footprint'), 1, 512, integer=True)})
    read = export.get('dmx_read')
    if not isinstance(read, dict):
        return out
    reason = clean(read.get('reason'))
    codes = {'': 'complete', 'ответ DMX старше 6 с': 'stale',
             'неполный или недостоверный ответ DMX: маркер, диапазон или байты': 'partial',
             'MA2 отказал в чтении DMX; следующая попытка не раньше чем через 30 с': 'refused',
             'MA2 отказал в чтении DMX трижды; переподключитесь или получите приборы заново': 'paused'}
    span = read.get('span')
    valid_span = isinstance(span, (tuple, list)) and len(span) == 2 and all(type(n) is int for n in span)
    dmx = {k: _number(read.get(k), integer=True) for k in ('values', 'chunks')}
    dmx.update({k: _number(read.get(k), high=86400) for k in ('pause_seconds', 'read_seconds', 'cycle_seconds', 'max_age_seconds')})
    dmx.update(count=_number(span[1], 1, 32, integer=True) if valid_span else None,
               reason=codes.get(reason, 'unknown'), canary_status=None, canary_value=None, rows=[])
    stamp = clean(read.get('t'))
    dmx['time'] = stamp if re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d', stamp) else None
    reply = clean(read.get('reply'))
    dmx['errors'] = _errors(reply)
    for key, name, low, high in (('ST', 'canary_status', -2, 1), ('V', 'canary_value', -1, 255)):
        match = re.search(r'\$PANEL' + key + r'\s*=\s*"?(-?\d{1,3})(?=["\s|]|$)', reply)
        if match:
            dmx[name] = _number(int(match[1]), low, high, integer=True)
    pattern = r'\$PANELDMX(\d{1,6})\s*=\s*"?([TS][0-9a-f]{0,16}) (\d{1,6}) (-?\d{1,3}(?:,-?\d{1,3}){0,31})(?=["\s|]|$)'
    for match in list(re.finditer(pattern, reply))[:16]:
        values = [int(n) for n in match[4].split(',')]
        dmx['rows'].append({'marked': bool(re.fullmatch(r'T[0-9a-f]{16}', match[2])),
                            'span_matches': bool(valid_span and int(match[1]) == span[0] == int(match[3]) and len(values) == span[1]),
                            'bytes': [_number(n, -1, 255, integer=True) for n in values]})
    out['dmx'] = dmx
    return out


# The receiver accepts only this vocabulary, including on manually forged requests.
_COUNT = ('int', 0, 1000000)
_TIME = ('number', 0, 86400)
_DMX = {'values': _COUNT, 'chunks': _COUNT, 'count': ('int', 1, 32),
        'time': 'time',
        **{k: _TIME for k in ('pause_seconds', 'read_seconds', 'cycle_seconds', 'max_age_seconds')},
        'reason': ('enum', 'complete', 'stale', 'partial', 'refused', 'paused', 'unknown'),
        'canary_status': ('int', -2, 1), 'canary_value': ('int', -1, 255),
        'errors': ('list', 16, ('error',)),
        'rows': ('list', 16, {'marked': 'bool', 'span_matches': 'bool', 'bytes': ('list', 32, ('int', -1, 255))})}
_SCHEMA = {'enabled': 'maybe_bool', 'poll_seconds': _TIME, 'rights': ('enum', 'admin', 'other', 'unknown'), 'truncated': 'bool',
           'fixtures': ('list', 64, {'type': ('int', 1, 32), 'patched': 'bool', 'missing': 'bool', 'footprint': ('int', 1, 512)}),
           'types': ('list', 32, {'channels': 'channels', 'mapped': 'bool', 'stale': 'bool', 'unsupported': 'bool',
                                 'export': ('enum', 'failed', 'read', 'pending', 'not_attempted'),
                                 'errors': ('list', 16, ('error',)), 'size': _COUNT}),
           'dmx': ('nullable', _DMX)}


def _valid(value, schema):
    if isinstance(schema, dict):
        return isinstance(value, dict) and value.keys() == schema.keys() and all(_valid(value[k], rule) for k, rule in schema.items())
    if schema == 'bool':
        return type(value) is bool
    if schema == 'maybe_bool':
        return value is None or type(value) is bool
    if schema == 'channels':
        return isinstance(value, dict) and not value.keys() - {'dim', 'r', 'g', 'b'} and all(_number(n, 1, 64, integer=True) is not None for n in value.values())
    if schema == 'time':
        return value is None or isinstance(value, str) and re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d', value) is not None
    if schema[0] == 'nullable':
        return value is None or _valid(value, schema[1])
    if schema[0] == 'list':
        return isinstance(value, list) and len(value) <= schema[1] and all(_valid(item, schema[2]) for item in value)
    if schema[0] == 'enum':
        return isinstance(value, str) and value in schema[1:]
    if schema[0] == 'error':
        return _number(value, 0, 9999, integer=True) is not None
    return value is None or _number(value, schema[1], schema[2], integer=schema[0] == 'int') is not None


def valid_readback(value):
    return _valid(value, _SCHEMA)
