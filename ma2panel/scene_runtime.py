"""Bounded MA2 scene transactions. Callers own action_lock, guards and context checks."""
import asyncio
import re
import secrets

from .commands import ActionError, fade_suffix, find, select_line


def probe_command(ex, nonce):
    return (
        "Lua \"local o,r=gma.show.getobj,gma.show.property; "
        "local c=o.handle('Executor " + ex + " Cue 1'); "
        "local p=c and o.parent(c); local n=p and o.amount(p); "
        "local q=c and o.child(c,0); local m; "
        "if q then for i=0,r.amount(q)-1 do if r.name(q,i)=='CMD' then m=r.get(q,i) end end end; "
        "local k=n and (n==1 or n==2) and r.get(c,'trig')=='Go' and o.amount(c)==1 and m==''; "
        "local h,j=k and o.child(p,0),k and o.child(p,1); "
        "local a,b=h and tonumber(o.number(h)),j and tonumber(o.number(j)); "
        "k=k and (n==1 and h==c and a==1 or n==2 and (h==c and a==1 and j and b==0 or (not h or a==0) and j==c and b==1)); "
        "gma.cmd(('SetVar %sPANELSCENE = %q'):format(string.char(36),'" + nonce + " '..(k and 'manual' or 'unknown')))\""
    )


def is_probe_command(line):
    match = re.search(r"handle\('Executor (\d+\.\d+) Cue 1'\)", line)
    nonce = re.search(r"SetVar %sPANELSCENE = %q'\):format\(string\.char\(36\),'([0-9a-f]{16}) ", line)
    return bool(match and nonce and line == probe_command(match[1], nonce[1]))


def grand_probe_command(nonce):
    return (
        "Lua \"local h=gma.show.getobj.handle('SpecialMaster 2.1'); "
        "local v=h and gma.show.property.get(h,'value'); "
        "gma.cmd(('SetVar %sPANELGM = %q'):format(string.char(36),'"
        + nonce + " '..tostring(v)))\""
    )


def is_grand_probe_command(line):
    match = re.search(r"SetVar %sPANELGM = %q'\):format\(string\.char\(36\),'([0-9a-f]{16}) ", line)
    return bool(match and line == grand_probe_command(match[1]))


async def read_nonce(send, variable, nonce):
    # onPC acknowledges Lua before its SetVar may be visible. Re-read only;
    # never replay Lua, a master write or a scene command to obtain evidence.
    for attempt in range(3):
        reply = await send('ListVar')
        values = re.findall(rf'(?m)^\s*(?:Global\s*:\s*)?\${variable}\s*=\s*"?{nonce} ([^"\r\n]*)"?[ \t]*\r?$', reply)
        if len(values) == 1:
            return values[0].strip()
        if attempt < 2:
            await asyncio.sleep(.05)
    raise ActionError('не получен свежий ответ ' + variable + ': результат неизвестен; проверьте MA2')


def _parse_tabular_exec_options(lines, raw_row):
    """Parse Priority / SoftLTP / Chaser from a grandMA2 tabular List Executor header + row."""
    headers = [ln for ln in lines if '=' not in ln and all(re.search(rf'\b{k}\b', ln) for k in ('Priority', 'SoftLTP', 'Chaser'))]
    if len(headers) != 1:
        return []
    header = headers[0]
    cols = [(m.group(0), m.start(), m.end()) for m in re.finditer(r'\S+', header)]
    names = [c[0] for c in cols]
    if any(names.count(k) != 1 for k in ('Priority', 'SoftLTP', 'Chaser')):
        return []
    # Fixed-width column extraction based on header start offsets
    extracted = []
    for idx, (col_name, start, _end) in enumerate(cols):
        if col_name not in ('Priority', 'SoftLTP', 'Chaser'):
            continue
        if start >= len(raw_row):
            extracted = []
            break
        if start > 0 and not raw_row[start - 1].isspace() and not raw_row[start].isspace():
            extracted = []
            break
        end = cols[idx + 1][1] if idx + 1 < len(cols) else len(raw_row)
        cell = raw_row[start:end].strip()
        if not cell or ' ' in cell or '\t' in cell:
            extracted = []
            break
        extracted.append((col_name, cell))
    if len(extracted) == 3:
        return extracted
    # Fallback: 2+ space delimited columns when header and row (minus leading "Exec <ex>") align 1:1
    header_parts = re.split(r'\s{2,}', header.strip())
    body = re.sub(r'^\s*(?:Exec|Executor)\s+\d+\.\d+\s+', '', raw_row).strip()
    row_parts = re.split(r'\s{2,}', body)
    if len(header_parts) == len(row_parts) and all(header_parts.count(k) == 1 for k in ('Priority', 'SoftLTP', 'Chaser')):
        return [(k, row_parts[header_parts.index(k)].strip()) for k in ('Priority', 'SoftLTP', 'Chaser')]
    return []


async def confirm_manual_scene(send, ex):
    # Executor handles expose only No./Name on onPC 3.9.63.11. Its playback
    # options are in List Executor; a missing/ambiguous field is not a default.
    profile = await send(f'List Executor {ex}')
    cleaned_raw = [re.sub(r'^(?:\s*\[[^\]]*\]>\s*)+', '', line) for line in profile.splitlines()]
    raw_rows = [line for line in cleaned_raw if re.match(rf'^\s*(?:Exec|Executor)\s+{re.escape(ex)}\s', line)]
    rows = [line.strip() for line in raw_rows]
    fields = re.findall(r'(?:^|\s)(Priority|SoftLTP|Chaser)=([^\s]+)', rows[0]) if len(rows) == 1 else []
    if len(rows) == 1 and not fields and '=' not in rows[0]:
        fields = _parse_tabular_exec_options(cleaned_raw, raw_rows[0])
    options = dict(fields)
    if (len(fields) != 3 or len(options) != 3 or options.get('Priority') not in ('Normal', 'LTP')
            or options.get('SoftLTP', '').lower() not in ('on', 'yes') or options.get('Chaser', '').lower() != 'off'):
        raise ActionError('не подтверждены normal LTP/Soft LTP и выключенный Chaser: запуск отменён')
    nonce = secrets.token_hex(8)
    await send(probe_command(ex, nonce))
    if await read_nonce(send, 'PANELSCENE', nonce) != 'manual':
        raise ActionError('не подтверждена одиночная ручная Cue 1 с LTP/Soft LTP без Cmd: запуск отменён')


def transition_lines(action, cfg, allowed, owned=()):
    target = find(cfg['scenes'], action['id'])['exec']
    fade_suffix(action, cfg)  # finite, bounded validation, independent of a custom fade_fmt
    seconds = action.get('fade', 0)
    others = sorted({ex for ex in owned if ex != target and allowed(ex)})
    return ([f'Masterfade {seconds:g} Executor {ex}' for ex in others]
            + [f'Goto Cue 1 Executor {target} Fade {seconds:g}']
            + [f'Off Executor {ex}' for ex in others])


async def store_scene(send, target, label, ids, *, spare=None, send_overwrite=None):
    """Prepare away from the live target. Keep the spare, including the old Cue 1.

    No recovery command is sent after any failure: in particular an unknown Copy
    must not overwrite the possibly successful new cue with an automatic rollback.
    """
    dest = spare or target
    await send(select_line(ids))
    await send(f'Store Executor {dest} Cue 1 /Source=Output /Use=Allforselected')
    await send(f'Assign Cue 1 Executor {dest} /Trig=Go')
    await send(f'Label Executor {dest} "{label}"')
    await confirm_manual_scene(send, dest)
    if spare:
        await send(f'Copy Cue 1 Executor {target} At Cue 2 Executor {spare} /CueOnly')
        await (send_overwrite or send)(f'Copy Cue 1 Executor {spare} At Cue 1 Executor {target} /CueOnly /Overwrite')
    # A successful reply is not content verification; caller additionally lists the target.


class GrandMasterBlackout:
    """Snapshot/restore Grand, leaving the independent native B.O. mask untouched.

    The getobj/property reply must carry a fresh nonce and a numeric level. Property
    availability on a particular MA2 version is a runtime prerequisite, not assumed.
    """
    def __init__(self, journal, save):
        self.journal, self.save = journal, save
        self.state = {'phase': 'unknown', 'reason': 'осталась запись затемнения; проверьте Grand Master на MA2'} if journal.exists() else {'phase': 'idle'}
        self.context = None
        self.previous = None

    async def read(self, send):
        nonce = secrets.token_hex(8)
        await send(grand_probe_command(nonce))
        value = await read_nonce(send, 'PANELGM', nonce)
        match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*%', value)
        if not match or not 0 <= float(match[1]) <= 100:
            raise ActionError('Grand Master не прочитан в процентах: затемнение/восстановление отменено; проверьте MA2')
        return float(match[1])

    async def toggle(self, send, context):
        if self.state['phase'] == 'unknown':
            raise ActionError(self.state.get('reason', 'исход затемнения неизвестен; проверьте MA2'))
        restoring = self.state['phase'] == 'active'
        if restoring and self.context != context:
            self.state = {'phase': 'unknown', 'reason': 'изменилось шоу или соединение; восстановите Grand Master на MA2 вручную'}
            raise ActionError(self.state['reason'])
        level = await self.read(send)
        if restoring and level != 0:
            self.state = {'phase': 'unknown', 'reason': 'Grand Master изменён другим оператором; автоматическое восстановление отменено'}
            raise ActionError(self.state['reason'])
        if not restoring:
            self.previous, self.context = level, context
        target = self.previous if restoring else 0
        self.save(self.journal, {'previous': self.previous, 'phase': 'pending', 'show': context[-1]})
        self.state = {'phase': 'unknown', 'reason': 'результат затемнения неизвестен; проверьте Grand Master на MA2'}
        level_text = format(target, '.15f').rstrip('0').rstrip('.')
        await send(f'SpecialMaster 2.1 At {level_text}')
        for attempt in range(3):
            if await self.read(send) == target:
                break
            if attempt < 2:
                await asyncio.sleep(.05)
        else:
            raise ActionError('Grand Master после команды не подтверждён; повторно не отправлено')
        if restoring:
            self.journal.unlink()
            self.state = {'phase': 'idle'}
            self.context = self.previous = None
        else:
            self.state = {'phase': 'active', 'previous': self.previous}
