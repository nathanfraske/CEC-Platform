import pcbnew
import pytest
import cec_frozen_copper as frozen
from test_frozen_copper import source, run_sync


def test_item_scope_does_not_preserve_entire_net(source):
    board=pcbnew.LoadBoard(str(source))
    uid=next(t.m_Uuid.AsString() for t in board.GetTracks() if t.GetClass()=='PCB_VIA')
    report=run_sync(source,preserve=False,uuids=[uid])
    assert report['preserved_locked_nets']==[]
    assert report['preserved_locked_uuids']==[uid]
    assert report['tracks_after']==1
    assert report['zones_after']==1
    current=pcbnew.LoadBoard(str(source))
    assert [t.m_Uuid.AsString() for t in current.GetTracks()]==[uid]


@pytest.mark.parametrize('mode',['missing','unlocked'])
def test_invalid_item_scope_fails_before_source_mutation(source,mode):
    board=pcbnew.LoadBoard(str(source))
    uid=('absent' if mode=='missing' else next(t.m_Uuid.AsString()
         for t in board.GetTracks() if not t.IsLocked()))
    before=source.read_bytes()
    with pytest.raises(ValueError,match='absent or unlocked'):
        run_sync(source,uuids=[uid])
    assert source.read_bytes()==before
    with pytest.raises(ValueError,match='absent or unlocked'):
        frozen.FrozenCopperContext(source,[],item_uuids=[uid])


def test_item_scope_guards_shape_not_every_same_net_package(source):
    board=pcbnew.LoadBoard(str(source))
    uid=next(t.m_Uuid.AsString() for t in board.GetTracks() if t.GetClass()=='PCB_VIA')
    ctx=frozen.FrozenCopperContext(source,[],item_uuids=[uid])
    assert len(ctx.items)==1
    assert ctx.anchor_refs==set()
    assert ctx.check({'ANCHOR':(6,10,0)})['ok']
    assert not ctx.check({'MOVABLE':(15,10,0)})['ok']
    assert ctx.check({'MOVABLE':(10,10,0)})['ok']


def test_item_scope_rejects_a_disappeared_live_net(source):
    board=pcbnew.LoadBoard(str(source))
    uid=next(t.m_Uuid.AsString() for t in board.GetTracks() if t.GetClass()=='PCB_VIA')
    before=source.read_bytes()
    with pytest.raises(ValueError,match='frozen item net absent'):
        run_sync(source,preserve=False,uuids=[uid],assignments={
            ('ANCHOR','1'):'/SIGNAL',('MOVABLE','1'):'/SIGNAL'})
    assert source.read_bytes()==before
