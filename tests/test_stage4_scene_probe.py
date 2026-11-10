"""Profiles based on a real onPC 3.9.63.11 List Executor reply, not mock defaults."""
import asyncio
import re
import pytest
from ma2panel.commands import ActionError
from ma2panel.scene_runtime import confirm_manual_scene


# Sanitized from the isolated PANEL_STAGE4_LAB_20261110, 2026-11-10.
EXECUTOR = 'Exec 1.101  No.=1.101 Name=Sequ Sequence=Seq 1(2) Width=1 SoftLTP=on Chaser=off Priority=Normal OffTime=Default\n[LayoutSelection]>'


def confirm(reply):
    calls = []
    nonce = [None]
    async def send(line):
        calls.append(line)
        if line == 'List Executor 1.101': return reply
        if line.startswith('Lua '):
            nonce[0] = re.search(r"setvar\('PANELSCENE','([0-9a-f]{16}) '",line)[1]
        if line == 'ListVar': return f'Global : $PANELSCENE = {nonce[0]} manual\n[LayoutSelection]>'
        return 'OK\n[LayoutSelection]>'
    asyncio.run(confirm_manual_scene(send,'1.101'))
    return calls


def test_normal_soft_ltp_profile_from_real_onpc_is_accepted():
    calls = confirm(EXECUTOR)
    assert 'List Executor 1.101' in calls


@pytest.mark.parametrize('reply', [
    EXECUTOR.replace('Priority=Normal','Priority=HTP'),
    EXECUTOR.replace('SoftLTP=on','SoftLTP=off'),
    EXECUTOR.replace('Chaser=off','Chaser=on'),
    EXECUTOR.replace('Priority=Normal','Priority=Unknown'),
    EXECUTOR.replace('Priority=Normal',''),
    EXECUTOR.replace('SoftLTP=on','SoftLTP=on SoftLTP=off'),
    EXECUTOR.replace('1.101','1.102'),
    EXECUTOR+'\n'+EXECUTOR,
])
def test_valid_cue_topology_does_not_override_unsafe_or_ambiguous_executor(reply):
    with pytest.raises(ActionError): confirm(reply)


def test_copy_method_and_commit_guard_stay_explicit_and_scoped():
    from ma2panel.safety import effective_safety, make_guard
    guard = make_guard(effective_safety({'safety':{'mode':'store','store_execs':['1.103','1.104'],
                                                     'extra_allowed_regex':['.*']}}))
    assert guard('Copy Cue 1 Executor 1.103 At Cue 2 Executor 1.104 /CueOnly') is None
    assert guard('Copy Cue 1 Executor 1.104 At Cue 1 Executor 1.103 /CueOnly /Overwrite') is None
    for line in [
        'Copy Cue 1 Executor 1.103 At Cue 2 Executor 1.104',
        'Copy Cue 1 Executor 1.104 At Cue 1 Executor 1.103 /Overwrite',
        'Copy Cue 1 Executor 1.103 At Cue 2 Executor 9.104 /CueOnly',
        'Copy Cue 1 Executor 1.104 At Cue 2 Executor 1.103 /CueOnly /Overwrite',
        'Copy Cue 1 Executor 1.103 At Cue 2 Executor 1.104 /CueOnly /NoConfirm',
    ]:
        assert guard(line), line


@pytest.mark.parametrize('result',['manual','unknown'])
def test_delayed_lua_result_uses_only_fresh_nonce_without_replaying_lua(result):
    calls=[];nonce=[None];reads=[0]
    async def send(line):
        calls.append(line)
        if line=='List Executor 1.101':return EXECUTOR
        if line.startswith('Lua '):nonce[0]=re.search(r"PANELSCENE','([0-9a-f]{16})",line)[1]
        if line=='ListVar':
            reads[0]+=1
            return ('$PANELSCENE = 0000000000000000 manual' if reads[0]==1
                    else f'$PANELSCENE = {nonce[0]} {result}')
        return 'OK'
    if result=='manual':asyncio.run(confirm_manual_scene(send,'1.101'))
    else:
        with pytest.raises(ActionError):asyncio.run(confirm_manual_scene(send,'1.101'))
    assert reads[0]==2
    assert sum(line.startswith('Lua ') for line in calls)==1


def test_grand_read_waits_for_fresh_snapshot_without_writing_a_master(tmp_path):
    from ma2panel.scene_runtime import GrandMasterBlackout
    calls=[];nonce=[None];reads=[0]
    async def send(line):
        calls.append(line)
        if line.startswith('Lua '):nonce[0]=re.search(r"PANELGM','([0-9a-f]{16})",line)[1]
        if line=='ListVar':
            reads[0]+=1
            return ('$PANELGM = 0000000000000000 100%' if reads[0]==1
                    else f'$PANELGM = {nonce[0]} 37.5%')
        return 'OK'
    grand=GrandMasterBlackout(tmp_path/'blackout.json',lambda *args:None)
    assert asyncio.run(grand.read(send))==37.5
    assert reads[0]==2 and sum(line.startswith('Lua ') for line in calls)==1
    assert not any(line.startswith('SpecialMaster ') for line in calls)


def test_grand_waits_for_applied_level_without_repeating_master_write(tmp_path):
    from ma2panel.scene_runtime import GrandMasterBlackout
    from ma2panel.fixtures import save_config
    grand=GrandMasterBlackout(tmp_path/'blackout.json',save_config)
    levels=iter([37.5,37.5,0,0,0,37.5]);calls=[]
    async def read(send):return next(levels)
    async def send(line):calls.append(line);return 'OK'
    grand.read=read
    async def go():
        await grand.toggle(send,(1,1,1,'test'))
        assert grand.state['phase']=='active'
        await grand.toggle(send,(1,1,1,'test'))
        assert grand.state['phase']=='idle'
    asyncio.run(go())
    assert calls==['SpecialMaster 2.1 At 0','SpecialMaster 2.1 At 37.5']
    assert not grand.journal.exists()
