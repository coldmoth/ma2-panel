"""DATA-007: transport acknowledgement is not address verification."""
import asyncio
import re
from pathlib import Path
import pytest
from test_status_evidence import context  # noqa: F401
from test_patch_context import setup


@pytest.mark.parametrize('mode, sides, expected', [
    ('match', 'both', 'verified'), ('old', 'patch', 'sent'),
    ('error', 'patch', 'unknown'), ('ambiguous', 'patch', 'unknown'),
    ('missing', 'physical', 'unknown'), ('old', 'physical', 'sent'),
    ('partial', 'both', 'partial'), ('error_both', 'both', 'partial'), ('timeout', 'both', 'unknown')])
def test_patch_result_requires_matching_readback(context, mode, sides, expected):
    c = context
    action = setup(c)
    action.update(patch=sides != 'physical', physical=sides != 'patch')
    action['token'] = c.patch_offer(action)['token']
    c.safety['allow_fixture_read'] = True
    c.ma2['export_wait'] = 0
    calls = []
    async def send(line, **kw):
        calls.append(line)
        c.link.last = {'cmd': line, 'status': 'sent'}
        if mode == 'timeout' and line.startswith('RdmSetParameter'):
            c.link.last['status'] = 'unknown'
            return False, 'timeout'
        if mode == 'partial' and line.startswith('Assign'):
            c.link.last['status'] = 'error'
            return False, 'Error refused'
        if line.startswith('Export Fixture '):
            if mode in ('error', 'error_both'): return False, 'Error export'
            name = re.search(r'"([^"]+)"', line)[1]
            address = 200 if mode == 'match' else 120
            extra = '<Fixture id="13" name="Twin" type="3 Current"><Patch><Address>120</Address></Patch></Fixture>' if mode == 'ambiguous' else ''
            # Duplicate names and an unbound old fixture force unresolved import.
            if mode == 'ambiguous':
                c.cfg['fixtures'][0].update(id=99, type='3 Current', name='Twin')
                c.cfg['fixtures'].append({'id': 98, 'type': '3 Current', 'name': 'Twin', 'address': '1.120'})
            Path(c.export_dir, name + '.xml').write_text(f'<MA><Fixture id="12" name="Twin" type="3 Current"><Patch><Address>{address}</Address></Patch></Fixture>{extra}</MA>')
        if line.startswith('Export FixtureType'): return False, 'Error no profile'
        if line.startswith('RdmList'):
            address = 200 if mode in ('match', 'partial', 'error_both') else 120
            return True, 'Executing : ' + line if mode == 'missing' else f'43500F019FCB Address {address} Footprint 17'
        return True, 'OK'
    c.link.send = send
    async def go():
        result = await c.patch_action('patch_apply', action)
        assert result.get('status') == expected, result
        assert result['ok'] is (expected == 'verified')
        assert result.get('verified') is (expected == 'verified')
        if mode == 'error_both':
            assert result['check'].get('physical') == 200
        if mode == 'timeout':
            assert sum(ln.startswith('RdmSetParameter') for ln in calls) == 1
            assert not any(ln.startswith('Assign') for ln in calls)
        if action['physical'] and mode in ('missing', 'timeout'):
            f = next(f for f in c.cfg['fixtures'] if f['id'] == 12)
            assert f['rdm'].get('address') != 200
    asyncio.run(go())
