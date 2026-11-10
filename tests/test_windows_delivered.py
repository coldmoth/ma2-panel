"""Windows may release a loaded extension after its child process has exited."""
import pytest
from scripts import windows_delivered as delivered


@pytest.mark.parametrize('body_error',[False,True])
def test_workspace_retries_transient_lock_and_preserves_assertion(monkeypatch,body_error):
    calls=[]
    class Directory:
        name='owned-test-directory'
        def __init__(self,**kw): pass
        def cleanup(self):
            calls.append('cleanup')
            if len(calls)==1:raise PermissionError('loaded extension')
    monkeypatch.setattr(delivered.tempfile,'TemporaryDirectory',Directory)
    monkeypatch.setattr(delivered.time,'sleep',lambda _:None)
    if body_error:
        with pytest.raises(AssertionError,match='body failed'):
            with delivered.delivered_workspace():raise AssertionError('body failed')
    else:
        with delivered.delivered_workspace() as path:assert path=='owned-test-directory'
    assert calls==['cleanup','cleanup']


def test_workspace_still_fails_on_persistent_lock(monkeypatch):
    class Directory:
        name='owned-test-directory'
        def __init__(self,**kw): pass
        def cleanup(self):raise PermissionError('persistent lock')
    monkeypatch.setattr(delivered.tempfile,'TemporaryDirectory',Directory)
    ticks=iter([0,6])
    monkeypatch.setattr(delivered.time,'monotonic',lambda:next(ticks))
    with pytest.raises(PermissionError,match='persistent lock'):
        with delivered.delivered_workspace():pass
