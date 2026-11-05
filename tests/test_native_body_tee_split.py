"""Body-tee preparation changes graph edges, never source material or vias."""
import math
import pcbnew
import pytest
import cec_native_body_tee_split as split
import cec_field_coupling as field
import cec_force_current as force
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,monkeypatch,*,turn=0,layer=0):
    b=_board([(10,10,'RENAMED'),(20,20,'RENAMED')])
    t=track(b,'RENAMED',(10,10),(20,20));t.SetLayer(layer)
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(15.025,14.975))
    v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(b.FindNet('RENAMED'));b.Add(v)
    for x in [*b.GetFootprints(),*b.GetTracks()]:
        x.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(turn,pcbnew.DEGREES_T))
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path)
    monkeypatch.setattr(split.ordinary,'eligible_nets',lambda *a,**k:{'RENAMED'})
    req=[dict(via_uuid=force._uid(v),track_uuid=force._uid(t),locked_source_requested=t.IsLocked())]
    return pcbnew.LoadBoard(str(path)),path,req


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('layer',[0,2,6])
def test_saved_exact_split_preserves_copper_and_native_partitions(tmp_path,monkeypatch,turn,layer):
    b,path,req=fixture(tmp_path,monkeypatch,turn=turn,layer=layer)
    proposal=split.plan(b,req,source_path=path,board_hint='SYNTHETIC')
    source_sha=force._hash(path);via=next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA')
    original=(tuple(via.GetPosition()),via.GetWidth(via.TopLayer()),via.GetDrillValue())
    result=split.materialize(b,proposal,source_path=path,board_hint='SYNTHETIC')
    assert len(result['incoming_track_uuids'])==1
    assert original==(tuple(via.GetPosition()),via.GetWidth(via.TopLayer()),via.GetDrillValue())
    target=force._copy_family(path,tmp_path/'candidate');field._save_field_snapshot(b,target)
    r=split.receive(path,target,req,board_hint='SYNTHETIC')
    assert r['ok'] and r['complete'] and r['actual_copper_geometry_unchanged']
    assert source_sha==force._hash(path) and not r['current_qualified'] and not r['release_authority']


@pytest.mark.parametrize('fault',['protected_net','group','endpoint','no_contact','noncanonical','stale_plan','wrong_lock','width','foreign_edit','setup'])
def test_source_ownership_and_saved_geometry_cannot_be_forged(tmp_path,monkeypatch,fault):
    b,path,req=fixture(tmp_path,monkeypatch)
    t=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')
    v=next(t for t in b.GetTracks() if t.GetClass()=='PCB_VIA')
    if fault=='protected_net':monkeypatch.setattr(split.ordinary,'eligible_nets',lambda *a,**k:set())
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('REAL_OWNER');b.Add(g);g.AddItem(t)
    elif fault=='endpoint':v.SetPosition(t.GetStart())
    elif fault=='no_contact':v.Move(pcbnew.VECTOR2I_MM(0,2))
    elif fault=='noncanonical':t.SetEnd(pcbnew.VECTOR2I_MM(20,21))
    elif fault=='wrong_lock':req[0]['locked_source_requested']=not t.IsLocked()
    if fault in ('stale_plan','width','foreign_edit','setup'):
        p=split.plan(b,req,source_path=path,board_hint='SYNTHETIC')
        if fault=='stale_plan':
            p['rows'][0]['split_nm'][0]+=1
            with pytest.raises(ValueError):split.materialize(b,p,source_path=path,board_hint='SYNTHETIC')
            return
        split.materialize(b,p,source_path=path,board_hint='SYNTHETIC')
        if fault=='width':next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK').SetWidth(200001)
        elif fault=='foreign_edit':next(iter(b.GetFootprints())).SetValue('UNAUTHORISED')
        else:
            props=b.GetProperties();props['CEC_FAB_PROFILE']='UNAUTHORISED_FACTORY';b.SetProperties(props)
        child=force._copy_family(path,tmp_path/'candidate');field._save_field_snapshot(b,child)
        assert not split.receive(path,child,req,board_hint='SYNTHETIC')['ok']
    else:
        with pytest.raises(ValueError):split.plan(b,req,source_path=path,board_hint='SYNTHETIC')


@pytest.mark.parametrize('bad',[True,0,-1,math.nan,10.1])
def test_body_split_work_is_explicitly_bounded(tmp_path,monkeypatch,bad):
    b,path,req=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):split.plan(b,req,source_path=path,board_hint='SYNTHETIC',timeout_s=bad)
