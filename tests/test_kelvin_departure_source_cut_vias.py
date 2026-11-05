"""Only a proved empty Source-face land may leave the departure graph."""
import time
import pcbnew
import pytest
import cec_kelvin_departure as departure
import cec_kelvin_copper_cut as cut
from cec_cell_row_rebuild import _source_binding
from test_kelvin_departure import native,with_input


def via(board,x,y,diameter=.6,drill=.3):
    item=pcbnew.PCB_VIA(board);item.SetNet(board.FindNet('ARBITRARY'))
    item.SetPosition(pcbnew.VECTOR2I_MM(x,y));item.SetWidth(pcbnew.FromMM(diameter))
    item.SetDrill(pcbnew.FromMM(drill));item.SetViaType(pcbnew.VIATYPE_THROUGH)
    item.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(item);return item


def fixture(tmp_path,*,rotation=0,back=False):
    board,pads=native(tmp_path,0,False,[((10.88,10),(13,10))])
    board.SetCopperLayerCount(6);target=with_input(board,13,10);barrel=via(board,10,10)
    for item in [*board.GetFootprints(),*board.GetTracks()]:
        if back:item.Flip(pcbnew.VECTOR2I(0,0),False)
        item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T))
    return board,pads,target,barrel


def audit(board,pads,target,vias):
    tracks=[t for t in board.GetTracks()if t.GetClass()=='PCB_TRACK']
    return departure.audit_pad_departures(pads['A'],pads['B'].GetPosition(),tracks,
        target_pads=[target],connectivity_pads=[target],connectivity_vias=vias)


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_wholly_removed_source_face_is_not_a_barrel_bypass(tmp_path,rotation,back):
    board,pads,target,barrel=fixture(tmp_path,rotation=rotation,back=back)
    before=_source_binding(board);r=audit(board,pads,target,[barrel])
    assert r['ok'] and r['departure_count']==1,r
    proof=r['source_face_barrel_cuts'];assert len(proof)==1
    assert proof[0]['layer']==(pcbnew.B_Cu if back else pcbnew.F_Cu)
    assert proof[0]['upper_land_removed_by_certified_lower_source_cut']
    assert proof[0]['true_polygon_and_bore_enclosure_verified']
    assert not proof[0]['isolation_current_or_fabrication_qualified']
    assert before==_source_binding(board)


@pytest.mark.parametrize('outside_nm',[0,1,2,10,100000])
def test_tangent_or_partially_outside_upper_land_stays_refused(tmp_path,outside_nm):
    board,pads,target,barrel=fixture(tmp_path)
    barrel.SetPosition(pcbnew.VECTOR2I(10700000+outside_nm,10000000))
    r=audit(board,pads,target,[barrel])
    assert not r['ok'] and any(i['reason']=='connectivity_barrel_overlaps_source_cut'for i in r['issues'])
    assert not r.get('source_face_barrel_cuts')


@pytest.mark.parametrize('inside_nm',[3,10,1000])
def test_certified_linear_core_keeps_the_native_nm_boundary(tmp_path,inside_nm):
    board,pads,target,barrel=fixture(tmp_path)
    barrel.SetPosition(pcbnew.VECTOR2I(10700000-inside_nm,10000000))
    assert audit(board,pads,target,[barrel])['ok']


def test_bbox_containment_cannot_substitute_for_roundrect_material(tmp_path):
    board,pads,target,barrel=fixture(tmp_path)
    pads['A'].SetShape(pcbnew.PAD_SHAPE_ROUNDRECT);pads['A'].SetRoundRectRadiusRatio(.25)
    barrel.SetPosition(pcbnew.VECTOR2I_MM(10.65,11.65))
    assert pads['A'].GetBoundingBox().Contains(barrel.GetBoundingBox())
    r=audit(board,pads,target,[barrel]);assert not r['ok']
    assert not r.get('source_face_barrel_cuts')


@pytest.mark.parametrize('drill',[0,.6,.7])
def test_unknown_or_non_enclosed_bore_is_not_an_empty_vertex_proof(tmp_path,drill):
    board,pads,target,barrel=fixture(tmp_path);barrel.SetDrill(pcbnew.FromMM(drill))
    r=audit(board,pads,target,[barrel]);assert not r['ok']
    assert r['issues'] and not r.get('source_face_barrel_cuts')


def test_unknown_true_polygon_cut_fails_closed(tmp_path,monkeypatch):
    board,pads,target,barrel=fixture(tmp_path)
    def unknown(*args,**kwargs):raise cut.Unknown('synthetic_source_cut_unknown')
    monkeypatch.setattr(cut,'_source_cut',unknown)
    r=audit(board,pads,target,[barrel]);assert not r['ok']
    assert any('synthetic_source_cut_unknown'in i.get('source_face_cut_refusal','')for i in r['issues'])


def test_invalid_live_source_epoch_cannot_be_accepted(tmp_path,monkeypatch):
    board,pads,target,barrel=fixture(tmp_path)
    def changed(*args):raise cut.Unknown('synthetic_changed_source_epoch')
    monkeypatch.setattr(cut,'_validate_linear_epochs',changed)
    assert not audit(board,pads,target,[barrel])['ok']


def test_empty_face_proof_cannot_borrow_time_after_its_deadline(tmp_path):
    board,pads,target,barrel=fixture(tmp_path)
    with pytest.raises(cut.Unknown,match='deadline'):
        departure._removed_source_via_face(pads['A'],barrel,pcbnew.F_Cu,time.monotonic()-1.)


def test_unconnected_sibling_is_not_qualified_by_another_input_departure(tmp_path):
    board,pads,target,barrel=fixture(tmp_path);sibling=with_input(board,13,15,'SIBLING')
    before=_source_binding(board);r=audit(board,pads,sibling,[barrel])
    assert not r['ok'] and not r['departures'] and r['non_sense_departures']
    assert r['unreachable_input_pad_uuids']==[sibling.m_Uuid.AsString()]
    assert r['reason']=='input_not_reached_from_source'
    assert before==_source_binding(board)


def add_track(board,a,b,layer):
    edge=pcbnew.PCB_TRACK(board);edge.SetNet(board.FindNet('ARBITRARY'));edge.SetWidth(200000)
    edge.SetLayer(layer);edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*b));board.Add(edge)


def test_other_faces_of_source_barrel_retain_real_plated_connectivity(tmp_path):
    board,pads,unused,barrel=fixture(tmp_path);remote=via(board,13,10)
    target=with_input(board,8,10,'BACK');layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);target.SetLayerSet(layers)
    add_track(board,(13,10),(10,10),pcbnew.In1_Cu)
    add_track(board,(10,10),(8,10),pcbnew.B_Cu)
    before=_source_binding(board)
    r=audit(board,pads,target,[barrel,remote]);assert r['ok'],r
    assert r['source_face_barrel_cuts'][0]['layer']==pcbnew.F_Cu
    assert not audit(board,pads,target,[remote])['ok']
    assert before==_source_binding(board)


def test_empty_source_face_cannot_supply_a_false_layer_jump(tmp_path):
    board,pads,unused,barrel=fixture(tmp_path)
    target=with_input(board,8,10,'BACK');layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);target.SetLayerSet(layers)
    add_track(board,(10,10),(8,10),pcbnew.B_Cu)
    r=audit(board,pads,target,[barrel]);assert not r['ok']
    assert r['unreachable_input_pad_uuids']==[target.m_Uuid.AsString()]
