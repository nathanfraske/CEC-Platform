"""A real unchanged landing may fund geometry, never a smaller rail budget."""
import copy
from pathlib import Path
import pcbnew
import pytest
import cec_landing_consumer_miter as repair
import cec_force_current as force
import cec_field_coupling as field
from test_pass_through_supply_branch import fixture
from test_lastmile import _board
from test_field_proposals import track


def case(tmp_path,monkeypatch,quarter=0,back=False):
    b,root,anchor,device,cap,tracks,trunk,group,row,domain,downstream=fixture(monkeypatch,tmp_path)
    source=tmp_path/'source.kicad_pcb';width=tracks[1].GetWidth()
    scope=repair.owner.plan(b,Path(b.GetFileName()),board_hint='synthetic',retired_track_uuids=[force._uid(tracks[1])])
    repair.owner.subtract(b,scope);new=[]
    for a,z,face in [((8,8),(12,8),pcbnew.F_Cu),((12,8),(12,15),pcbnew.B_Cu),
        ((12,15),(12.35,15),pcbnew.B_Cu),((12.35,15),(25,15),pcbnew.F_Cu),((25,15),(25,8),pcbnew.F_Cu)]:
        t=pcbnew.PCB_TRACK(b);t.SetNet(root.GetNet());t.SetLayer(face);t.SetWidth(width);t.SetLocked(True)
        t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(t);new.append(t)
    vias=[]
    for xy in ((12,8),(12.35,15)):
        via=pcbnew.PCB_VIA(b);via.SetNet(root.GetNet());via.SetPosition(pcbnew.VECTOR2I_MM(*xy))
        via.SetWidth(900000);via.SetDrill(500000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetViaType(pcbnew.VIATYPE_THROUGH);b.Add(via);vias.append(via)
    repair.owner.assign(b,scope,[force._uid(t) for t in new],[force._uid(v) for v in vias])
    for a,z in [((-50,-50),(50,-50)),((50,-50),(50,50)),((50,50),(-50,50)),((-50,50),(-50,-50))]:
        e=pcbnew.PCB_SHAPE(b);e.SetShape(pcbnew.SHAPE_T_SEGMENT);e.SetLayer(pcbnew.Edge_Cuts)
        e.SetStart(pcbnew.VECTOR2I_MM(*a));e.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(e)
    for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:
        if quarter:item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:item.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    field._save_field_snapshot(b,source);field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    return source,dict(board_hint='synthetic',retired_track_uuids=[force._uid(t) for t in new[1:3]],allow_locked_source=True),row,domain,downstream


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_actual_single_tap_consumer_miter_preserves_width_budget_and_native_via_contacts(tmp_path,monkeypatch,quarter,back):
    source,args,row,domain,downstream=case(tmp_path,monkeypatch,quarter,back);saved=source.read_bytes()
    before=copy.deepcopy((row,domain,downstream));proposal=repair.plan(source,**args)
    assert proposal['shape']['landing_witnesses'] and not proposal['current_or_width_reduced']
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(repair.construct(source,proposal),child)
    got=repair.receive(source,child,proposal,board_hint='synthetic')
    assert got['ok'] and got['complete'],got['errors']
    assert got['source_allocation_budget_and_single_tap_exact'] and got['every_saved_native_object_reconstructed']
    assert got['saved_trace_length_mm']>.1 and not got['new_vias'] and not got['pads_moved']
    scope=got['source_consumer_receiving']['source_scope']
    assert scope['source_budget']['current_authority']['amps']==3.0004
    assert scope['source_budget']['aggregate_current_authority']['amps']==20.
    assert not got['source_current_reduced'] and not got['release_authority']
    assert source.read_bytes()==saved and before==(row,domain,downstream)


@pytest.mark.parametrize('fault',['no_lock_permission','wrong_group','wrong_package','underwidth','masked',
    'budget','no_hidden_landing','too_short','split_process'])
def test_a_short_leg_or_group_name_alone_never_grants_the_extension(tmp_path,monkeypatch,fault):
    source,args,row,domain,downstream=case(tmp_path,monkeypatch);b=pcbnew.LoadBoard(str(source))
    live={force._uid(t):t for t in b.GetTracks()};old=[live[u] for u in args['retired_track_uuids']]
    if fault=='no_lock_permission':args['allow_locked_source']=False
    elif fault=='wrong_group':next(g for g in b.Groups() if g.ContainsItem(old[0])).SetName('unrelated')
    elif fault=='wrong_package':next(fp for fp in b.GetFootprints() if fp.GetReference()=='NO_PREFIX_OWNER').SetField('MPN','UNKNOWN')
    elif fault=='underwidth':
        for t in old:t.SetWidth(100000)
    elif fault=='masked':old[0].SetHasSolderMask(True)
    elif fault=='budget':row['amps']=3.
    elif fault=='no_hidden_landing':
        for v in b.GetTracks():
            if v.GetClass()=='PCB_VIA':v.SetWidth(550000);v.SetDrill(300000)
    elif fault=='too_short':
        t=next(t for t in old if t.GetStart().y==t.GetEnd().y)
        t.SetEnd(t.GetStart()+pcbnew.VECTOR2I(100000,0))
    elif fault=='split_process':old[0].SetLocked(False)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):repair.plan(source,**args)


@pytest.mark.parametrize('fault',['width','face','point','pad_pose','group','barrel','sidecar','plan'])
def test_saved_exact_receiving_rejects_collateral_or_forged_source_changes(tmp_path,monkeypatch,fault):
    source,args,*_=case(tmp_path,monkeypatch);proposal=repair.plan(source,**args)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(repair.construct(source,proposal),child)
    b=pcbnew.LoadBoard(str(child));t=next(t for t in b.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.B_Cu)
    if fault=='width':t.SetWidth(t.GetWidth()-1)
    elif fault=='face':t.SetLayer(pcbnew.F_Cu)
    elif fault=='point':t.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(1,0))
    elif fault=='pad_pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='group':next(iter(b.Groups())).SetName('changed')
    elif fault=='barrel':next(v for v in b.GetTracks() if v.GetClass()=='PCB_VIA').SetDrill(510000)
    elif fault=='sidecar':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='plan':proposal['shape']['points_nm'][1][0]+=1
    field._save_field_snapshot(b,child)
    got=repair.receive(source,child,proposal,board_hint='synthetic')
    assert not got['ok'] and got['errors']


@pytest.mark.parametrize('fault',['other_face','bbox_only'])
def test_a_landing_bbox_or_opposite_face_is_not_a_native_hiding_witness(fault):
    board=_board([(12.35,15.04,'UNFAMILIAR')],edge=(-10,-10,30,30))
    pad=next(iter(next(iter(board.GetFootprints())).Pads()))
    pad.SetSize(pcbnew.VECTOR2I_MM(.68,.68));pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    if fault=='bbox_only':layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);pad.SetLayerSet(layers)
    old=[track(board,'UNFAMILIAR',(12,8),(12,15),width=.5),track(board,'UNFAMILIAR',(12,15),(12.35,15),width=.5)]
    for t in old:t.SetLayer(pcbnew.B_Cu)
    # The last stub's rectangle fits this circle's bounding box, but an
    # actual curved wedge lies outside its shifted circular copper land.
    with pytest.raises(ValueError,match='not_entirely_inside_actual_retained_native_landing'):
        repair.geometry.hidden_landing_miter(board,old)
