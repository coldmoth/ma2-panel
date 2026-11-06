import importlib.util

def rules():
    assert importlib.util.find_spec("ma2panel.scenes") is not None, "scene ordering rules are missing"
    from ma2panel import scenes
    return scenes


def test_legacy_migration_only_once():
    canonical_exec = rules().canonical_exec
    ordered_scenes = rules().ordered_scenes
    merge_scenes = rules().merge_scenes
    old = [{'id':'b','exec':'2.1','label':'B'},{'id':'a','exec':'01.0101','label':'A'}]
    assert [s['id'] for s in ordered_scenes(old, False)] == ['a','b']
    assert [s['id'] for s in ordered_scenes(old, True)] == ['b','a']
    assert canonical_exec('01.0101') == '1.101'


def test_merge_keeps_identity_and_order_and_updates_names():
    canonical_exec = rules().canonical_exec
    ordered_scenes = rules().ordered_scenes
    merge_scenes = rules().merge_scenes
    old = [{'id':'b','exec':'2.1','label':'B'},{'id':'a','exec':'1.101','label':'A'}]
    result, added = merge_scenes(old, [('01.0101','Новое'),('3.2','Три'),('3.1','Два')])
    assert [(s['id'],s['label']) for s in result[:2]] == [('b','B'),('a','Новое')]
    assert [s['exec'] for s in result] == ['2.1','1.101','3.1','3.2']
    assert added == 2


def test_slot_candidates_respect_scope_and_existing_plan():
    slot_candidates = rules().slot_candidates
    full = slot_candidates('full', set(), {'1.1'})
    assert len(full) == 249 and full[0] == '1.2' and full[-1] == '1.250'
    assert slot_candidates('store', {'2.110','1.102','1.101'}, {'1.102'}) == ['1.101','2.110']
