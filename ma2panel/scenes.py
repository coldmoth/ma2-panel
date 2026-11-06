"""Stable panel scene order, independent of the console's pages."""
import re

from .commands import ActionError


def canonical_exec(value):
    if not isinstance(value, str) or not re.fullmatch(r"\d+\.\d+", value):
        raise ActionError("executor: нужен номер в формате 1.101")
    page, slot = map(int, value.split('.'))
    if page < 1 or slot < 1:
        raise ActionError("executor: номера должны быть положительными")
    return f"{page}.{slot}"


def exec_key(value):
    return tuple(map(int, canonical_exec(value).split('.')))


def ordered_scenes(scenes, migrated):
    result = [{**s, 'exec': canonical_exec(s['exec'])} for s in scenes]
    return result if migrated else sorted(result, key=lambda s: exec_key(s['exec']))


def merge_scenes(existing, incoming):
    result = ordered_scenes(existing, True)
    index = {s['exec']: i for i, s in enumerate(result)}
    incoming = {canonical_exec(ex): label for ex, label in incoming}
    added = 0
    ids = {s['id'] for s in result}
    for ex, label in sorted(incoming.items(), key=lambda item: exec_key(item[0])):
        if ex in index:
            i = index[ex]
            result[i] = {**result[i], 'label': label}
        else:
            n = 1
            while f's{n}' in ids:
                n += 1
            sid = f's{n}'
            ids.add(sid)
            index[ex] = len(result)
            result.append({'id': sid, 'exec': ex, 'label': label})
            added += 1
    return result, added


def slot_candidates(mode, allowed, occupied):
    occupied = {canonical_exec(ex) for ex in occupied}
    pool = {f'1.{n}' for n in range(1, 251)} if mode == 'full' else (
        {canonical_exec(ex) for ex in allowed} if mode == 'store' else set())
    return sorted(pool - occupied, key=exec_key)
