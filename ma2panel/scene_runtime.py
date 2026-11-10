"""Bounded MA2 scene transactions. Callers own action_lock, guards and context checks."""
import asyncio
import re
import secrets

from .commands import ActionError, fade_suffix, find, select_line


def probe_command(ex, nonce):
    return ("Lua \"local c=gma.show.getobj.handle('Executor " + ex + " Cue 1'); "
            "local p=c and gma.show.getobj.parent(c); local n=p and gma.show.getobj.amount(p); "
            "local q=c and gma.show.getobj.child(c,0); local cmd; "
            "if q then for i=0,gma.show.property.amount(q)-1 do "
            "if gma.show.property.name(q,i)=='CMD' then cmd=gma.show.property.get(q,i) end end end; "
            "local ok=n and n>=1 and n<=2 and gma.show.property.get(c,'trig')=='Go' "
            "and gma.show.getobj.amount(c)==1 and cmd==''; "
            "local seen=0; if ok then for i=0,n-1 do local h=gma.show.getobj.child(p,i); "
            "local k=h and tonumber(gma.show.getobj.number(h)); "
            "if not h then if i~=0 then ok=false end "
            "elseif h==c and k==1 then seen=seen+1 "
            "elseif k~=0 then ok=false end end end; ok=ok and seen==1; "
            "gma.show.setvar('PANELSCENE','" + nonce + " '..(ok and 'manual' or 'unknown'))\"")


def is_probe_command(line):
    match = re.search(r"handle\('Executor (\d+\.\d+) Cue 1'\)", line)
    nonce = re.search(r"setvar\('PANELSCENE','([0-9a-f]{16}) '", line)
    return match and nonce and line == probe_command(match[1], nonce[1])


async def read_nonce(send, variable, nonce):
    # onPC acknowledges Lua before its setvar may be visible. Re-read only;
    # never replay Lua, a master write or a scene command to obtain evidence.
    for attempt in range(3):
        reply = await send('ListVar')
        values = re.findall(rf'(?m)^\s*(?:Global\s*:\s*)?\${variable}\s*=\s*{nonce} ([^\r\n]*)\r?$', reply)
        if len(values) == 1:
            return values[0].strip()
        if attempt < 2:
            await asyncio.sleep(.05)
    raise ActionError('не получен свежий ответ ' + variable + ': результат неизвестен; проверьте MA2')


async def confirm_manual_scene(send, ex):
    # Executor handles expose only No./Name on onPC 3.9.63.11. Its playback
    # options are in List Executor; a missing/ambiguous field is not a default.
    profile = await send(f'List Executor {ex}')
    rows = [line.strip() for line in profile.splitlines()
            if re.match(rf'^\s*(?:Exec|Executor)\s+{re.escape(ex)}\s', line)]
    fields = re.findall(r'(?:^|\s)(Priority|SoftLTP|Chaser)=([^\s]+)', rows[0]) if len(rows) == 1 else []
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


async def store_scene(send, target, label, ids, *, spare=None, prepared=None):
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
        if prepared:
            prepared()
        await send(f'Copy Cue 1 Executor {spare} At Cue 1 Executor {target} /CueOnly /Overwrite')
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
        await send('Lua "local h=gma.show.getobj.handle(\'SpecialMaster 2.1\'); '
                   'local v=h and gma.show.property.get(h,\'value\'); '
                   f'gma.show.setvar(\'PANELGM\',\'{nonce} \'..tostring(v))"')
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
