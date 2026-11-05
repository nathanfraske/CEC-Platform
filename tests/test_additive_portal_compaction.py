import time
import pcbnew
import pytest
import cec_additive_portal_compaction as compact
import cec_force_current as force
import cec_field_coupling as field
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,*,angle=0,back=False):
    b=_board([(5,10,'/CONTROL'),(8,10,'/CONTROL')],edge=(0,0,30,30))
    old=track(b,'/CONTROL',(5,10),(12,10))
    originals={force._uid(t) for t in b.GetTracks()}
    covered=track(b,'/CONTROL',(6,10),(8,10))
    useful=track(b,'/CONTROL',(6,10),(6,15))
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(8,10))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetNet(b.FindNet('/CONTROL'));b.Add(via)
    if back:
        for i in [*b.GetFootprints(),*b.GetTracks()]:
            i.Flip(pcbnew.VECTOR2I_MM(15,15),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    if angle:
        for i in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings()]:
            i.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    path=tmp_path/'board.kicad_pcb';field._save_field_snapshot(b,path)
    return b,path,originals,old,covered,useful,via


@pytest.mark.parametrize('angle,back',[(a,side) for a in (0,90,180,270) for side in (False,True)])
def test_new_covered_stub_and_single_layer_barrel_are_compacted_natively(tmp_path,angle,back):
    b,path,originals,old,covered,useful,via=fixture(tmp_path,angle=angle,back=back)
    old_data=(tuple(old.GetStart()),tuple(old.GetEnd()),old.GetWidth(),old.IsLocked())
    ids=[force._uid(i) for i in (old,covered,useful,via)]
    result=compact.compact(b,originals,board_path=path,board_hint='synthetic')
    assert result['removed']==sorted([ids[1],ids[3]]),result
    assert result['all_surviving_native_partitions_preserved']
    assert {force._uid(i) for i in b.GetTracks()}=={ids[0],ids[2]}
    assert (tuple(old.GetStart()),tuple(old.GetEnd()),old.GetWidth(),old.IsLocked())==old_data
    assert not result['release_authority']


def test_a_real_layer_transition_is_retained(tmp_path):
    b,path,originals,old,covered,useful,via=fixture(tmp_path)
    peer=track(b,'/CONTROL',(8,10),(8,13));peer.SetLayer(pcbnew.B_Cu)
    identity=force._uid(via)
    result=compact.compact(b,originals,board_path=path,board_hint='synthetic')
    assert identity not in result['removed'],result
    assert any(force._uid(i)==identity for i in b.GetTracks())


def test_a_single_layer_barrel_that_bridges_a_gap_cannot_be_removed(tmp_path):
    b=_board([(5,10,'/CONTROL'),(8,10,'/CONTROL')],edge=(0,0,30,30))
    old=track(b,'/CONTROL',(5,10),(6.8,10));originals={force._uid(old)}
    track(b,'/CONTROL',(7.2,10),(8,10))
    via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(7,10))
    via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetNet(b.FindNet('/CONTROL'));b.Add(via)
    path=tmp_path/'board.kicad_pcb';field._save_field_snapshot(b,path)
    prior={force._uid(i) for i in b.GetTracks()}
    result=compact.compact(b,originals,board_path=path,board_hint='synthetic')
    assert not result['board_mutated'] and result['reason']=='unused_portal_claim_would_break_native_partition',result
    assert prior=={force._uid(i) for i in b.GetTracks()}


@pytest.mark.parametrize('fault',['source_via','source_stub','one_nm_offset','thicker','grouped'])
def test_source_items_approximate_coverage_and_groups_are_not_retired(tmp_path,fault):
    b,path,originals,old,covered,useful,via=fixture(tmp_path)
    if fault=='source_via':originals.add(force._uid(via))
    if fault=='source_stub':originals.add(force._uid(covered))
    if fault=='one_nm_offset':covered.Move(pcbnew.VECTOR2I(0,1))
    if fault=='thicker':covered.SetWidth(old.GetWidth()+1)
    if fault=='grouped':
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.SetName('owned_portal_group')
        group.AddItem(covered);group.AddItem(via)
    protected=force._uid(via if fault=='source_via' else covered)
    result=compact.compact(b,originals,board_path=path,board_hint='synthetic')
    assert protected not in result['removed'],result
    assert any(force._uid(i)==protected for i in b.GetTracks())


def test_power_owned_portals_are_not_compacted(tmp_path):
    b,path,originals,old,covered,useful,via=fixture(tmp_path)
    b.Add(pcbnew.NETINFO_ITEM(b,'+3V3'))
    for i in b.GetTracks():i.SetNet(b.FindNet('+3V3'))
    before={force._uid(i) for i in b.GetTracks()}
    result=compact.compact(b,originals,board_path=path,board_hint='synthetic')
    assert not result['board_mutated'] and before=={force._uid(i) for i in b.GetTracks()},result


@pytest.mark.parametrize('seconds,limit',[(0,128),(11,128),(True,128),(2,0),(2,257),(2,True)])
def test_invalid_bounds_refuse_before_mutation(tmp_path,seconds,limit):
    b,path,originals,*_=fixture(tmp_path)
    before={force._uid(i) for i in b.GetTracks()}
    with pytest.raises(ValueError):compact.compact(b,originals,board_path=path,
        board_hint='synthetic',timeout_s=seconds,max_new_items=limit)
    assert before=={force._uid(i) for i in b.GetTracks()}
