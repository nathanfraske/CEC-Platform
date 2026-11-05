"""A via obstruction cannot authorize a protected/partial native cut."""
import pcbnew
import pytest
import cec_macro_ordinary_barrel_scope as scope
import cec_force_current as force
import cec_field_coupling as field
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,turn=0,mirror=False):
    b=_board([(18,18,'OTHER')],edge=(0,0,25,25));b.SetCopperLayerCount(6)
    n=pcbnew.NETINFO_ITEM(b,'/renamed_ordinary');b.Add(n)
    def at(x,y):
        if mirror:x=24-x
        for _ in range(turn):x,y=24-y,x
        return x,y
    track(b,n.GetNetname(),at(6,8),at(10,8))
    track(b,n.GetNetname(),at(10,8),at(14,8),layer=pcbnew.B_Cu)
    v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I_MM(*at(10,8)))
    v.SetWidth(600000);v.SetDrill(300000);v.SetNet(n)
    v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetViaType(pcbnew.VIATYPE_THROUGH);v.SetLocked(True);b.Add(v)
    path=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,path);uid=force._uid(v)
    source,candidate=[pcbnew.LoadBoard(str(path)) for _ in range(2)]
    fp=next(iter(candidate.GetFootprints()));fp.SetPosition(pcbnew.VECTOR2I_MM(*at(10,8)))
    return source,candidate,path,uid,list(fp.Pads())


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_actual_obstruction_owns_every_source_face_departure_not_the_old_via_port(tmp_path,turn,mirror):
    a,b,path,uid,obstacles=fixture(tmp_path,turn,mirror)
    old=field._field_snapshot_inventory(a);new=field._field_snapshot_inventory(b)
    proof=scope.plan(a,b,[uid],source_path=path,board_hint='synthetic',obstructing_items=obstacles,
        clearance_nm=200000,allow_locked_via_uuids=[uid])
    assert proof['exact_retired_via_uuids']==[uid]
    assert len(proof['mandatory_reconstruction_track_uuids'])==2
    assert len(proof['independently_reproved_source_exclusive_barrels'])==1
    assert proof['original_source_saved_replay_and_partitions_required']
    assert not proof['current_or_barrel_capacity_credited'] and not proof['release_authority']
    assert field._field_snapshot_inventory(a)==old and field._field_snapshot_inventory(b)==new


@pytest.mark.parametrize('fault',['no_witness','group','grouped_leg','pad_contact','foreign_contact','one_face',
    'moved_via','width','drill','unpermitted_lock','protected','duplicate','unknown','bad_clearance','stale_source'])
def test_no_partial_or_protected_cut_is_conferred(tmp_path,fault):
    a,b,path,uid,obstacles=fixture(tmp_path)
    original=next(t for t in a.GetTracks() if force._uid(t)==uid)
    actual=next(t for t in b.GetTracks() if force._uid(t)==uid)
    requested=[uid];unlock=[uid];clearance=200000
    if fault=='no_witness':obstacles[0].Move(pcbnew.VECTOR2I_MM(5,0))
    elif fault=='group':
        g=pcbnew.PCB_GROUP(a);g.SetName('REAL_OWNER');g.AddItem(original);a.Add(g)
    elif fault=='grouped_leg':
        t=next(t for t in a.GetTracks() if t.GetClass()=='PCB_TRACK')
        g=pcbnew.PCB_GROUP(a);g.SetName('REAL_LEG_OWNER');g.AddItem(t);a.Add(g)
    elif fault=='pad_contact':
        fp=next(iter(a.GetFootprints()));pad=next(iter(fp.Pads()))
        fp.SetPosition(original.GetPosition());pad.SetNetCode(original.GetNetCode())
    elif fault=='foreign_contact':track(a,'OTHER',(9,8),(11,8))
    elif fault=='one_face':
        for t in a.GetTracks():
            if t.GetClass()=='PCB_TRACK':t.SetLayer(pcbnew.F_Cu)
    elif fault=='moved_via':actual.Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='width':actual.SetWidth(700000)
    elif fault=='drill':actual.SetDrill(400000)
    elif fault=='unpermitted_lock':unlock=[]
    elif fault=='protected':
        for board in (a,b):
            n=pcbnew.NETINFO_ITEM(board,'/SENSE_HI');board.Add(n)
            for t in board.GetTracks():t.SetNet(n)
    elif fault=='duplicate':requested=[uid,uid]
    elif fault=='unknown':requested=['missing'];unlock=[]
    elif fault=='bad_clearance':clearance=True
    elif fault=='stale_source':path=tmp_path/'different.kicad_pcb'
    old=field._field_snapshot_inventory(a);new=field._field_snapshot_inventory(b)
    with pytest.raises(ValueError):
        scope.plan(a,b,requested,source_path=path,board_hint='synthetic',obstructing_items=obstacles,
            clearance_nm=clearance,allow_locked_via_uuids=unlock)
    assert field._field_snapshot_inventory(a)==old and field._field_snapshot_inventory(b)==new
