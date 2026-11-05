"""Existing plated pair vias are access, never permission for new drills."""
import time
from contextlib import ExitStack
from unittest.mock import patch

import pcbnew
import pytest
import cec_precision_route as route
import cec_local_copper_cell as cell
from test_native_pair_terminal_layers import fixture


def via_fixture(rotation=0,offset=0.,names=('/RENAMED_P','/RENAMED_N')):
    board,pair,ends,pads=fixture(offset=offset,attributes={i:pcbnew.PAD_ATTRIB_SMD for i in range(4)})
    pair=dict(pair,p=names[0],n=names[1])
    for name in names:board.Add(pcbnew.NETINFO_ITEM(board,name))
    vias=[]
    for index,(at,pad) in enumerate(zip(ends,pads)):
        net=names[0 if index<2 else 1];pad.SetNetCode(board.GetNetcodeFromNetname(net))
        via=pcbnew.PCB_VIA(board);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetPosition(pcbnew.VECTOR2I_MM(*at))
        via.SetWidth(600000);via.SetDrill(300000);via.SetNetCode(pad.GetNetCode());board.Add(via);vias.append(via)
    if rotation:
        pivot=pcbnew.VECTOR2I_MM(14+offset,10);angle=pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T)
        for fp in board.GetFootprints():fp.Rotate(pivot,angle)
        for via in vias:via.Rotate(pivot,angle)
    ends=tuple(tuple(x/1e6 for x in via.GetPosition()) for via in vias)
    return board,pair,ends,pads,vias


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('middle',['In2.Cu','B.Cu'])
@pytest.mark.parametrize('offset,names',[(0.,('/RENAMED_P','/RENAMED_N')),(37.,('/OTHER_PLUS','/OTHER_MINUS'))])
def test_retained_vias_prove_both_actual_end_layer_access(rotation,middle,offset,names):
    b,pair,ends,pads,vias=via_fixture(rotation,offset,names);before=cell.copper_inventory(b)
    q=route._paired_native_terminal_layers(b,pair,ends,layer='F.Cu',middle_layer=middle)
    assert all(x['native_plated_access'] and x['source_layer']==middle for x in q.values())
    assert [x['uuid'] for side in ('start','end') for x in q[side]['barrels']]==[vias[i].m_Uuid.AsString() for i in (0,2,1,3)]
    assert all(x['kind']=='via' and x['existing_unmodified_plated_barrel']
        and not x['new_hole_or_process_qualification'] for side in q.values() for x in side['barrels'])
    assert all(not side['pads'] for side in q.values())
    assert cell.copper_inventory(b)==before


@pytest.mark.parametrize('case',['wrong_net','offset','zero_effective_drill','no_annulus','blind',
    'partial_drill','backdrill','duplicate_same_net','duplicate_foreign','duplicate_npth','one_missing'])
def test_invalid_or_ambiguous_member_cannot_grant_native_access(case):
    b,pair,ends,pads,vias=via_fixture();via=vias[2]
    if case=='wrong_net':via.SetNetCode(b.GetNetcodeFromNetname('FOREIGN'))
    elif case=='offset':via.Move(pcbnew.VECTOR2I(1,0))
    elif case=='no_annulus':via.SetDrill(600000)
    elif case=='blind':via.SetViaType(pcbnew.VIATYPE_BLIND)
    elif case=='partial_drill':via.SetPrimaryDrillEndLayer(pcbnew.In2_Cu)
    elif case=='backdrill':via.SetBackdrillMode(pcbnew.BACKDRILL_MODE_BACKDRILL_TOP)
    elif case=='one_missing':b.Remove(via)
    elif case=='duplicate_npth':
        pad=pads[2];pad.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    elif case.startswith('duplicate_'):
        duplicate=via.Duplicate();duplicate.m_Uuid.Clone(pcbnew.KIID())
        if case=='duplicate_foreign':duplicate.SetNetCode(b.GetNetcodeFromNetname('FOREIGN'))
        b.Add(duplicate)
    with ExitStack() as stack:
        if case=='zero_effective_drill':
            # Native raw drill zero means "use the class default", not a
            # zero effective hole. Test the actual invalid getter boundary.
            target=via.m_Uuid.AsString();original=pcbnew.PCB_VIA.GetDrillValue
            stack.enter_context(patch.object(pcbnew.PCB_VIA,'GetDrillValue',
                lambda obj:0 if obj.m_Uuid.AsString()==target else original(obj)))
        q=route._paired_native_terminal_layers(b,pair,ends,layer='F.Cu',middle_layer='B.Cu')
    assert not q['start']['native_plated_access']
    assert q['end']['native_plated_access']


def test_mixed_actual_pth_and_existing_via_pair_end_is_supported():
    b,pair,ends,pads,vias=via_fixture()
    b.Remove(vias[0]);pad=pads[0];pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    pad.SetLayerSet(pcbnew.PAD.PTHMask());pad.SetDrillSize(pcbnew.VECTOR2I_MM(.4,.4))
    q=route._paired_native_terminal_layers(b,pair,ends,layer='F.Cu',middle_layer='In2.Cu')
    assert q['start']['native_plated_access']
    assert q['start']['pads'][0]['uuid']==pad.m_Uuid.AsString()
    assert len(q['start']['pads'])==1
    assert q['start']['barrels'][1]['kind']=='via'


def test_via_pair_beam_routes_fanins_on_middle_without_testing_new_via_fields():
    b,pair,ends,pads,vias=via_fixture();old=cell.copper_inventory(b);fanins=[]
    def fanin(board,pair,points,**kw):
        fanins.append(kw['layer']);return dict(refused='bounded synthetic fanin refusal')
    with patch.object(route,'_route_paired_stub',side_effect=fanin), \
            patch.object(route,'_probe_matched_transition_field') as fields:
        q=route._route_coupled_via_portal_beam(b,pair,ends,middle_layer='B.Cu',
            max_fanins_per_side=1,max_portal_pairs=1,deadline=time.monotonic()+3.)
    assert q.get('refused') and fanins and set(fanins)=={'B.Cu'}
    fields.assert_not_called();assert cell.copper_inventory(b)==old


def test_real_pair_closes_on_existing_back_layer_access_without_redundant_holes():
    b,pair,ends,pads,vias=via_fixture();source_ids={x.m_Uuid.AsString() for x in vias}
    for a,z in (((0,0),(30,0)),((30,0),(30,20)),((30,20),(0,20)),((0,20),(0,0))):
        edge=pcbnew.PCB_SHAPE(b);edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a));edge.SetEnd(pcbnew.VECTOR2I_MM(*z));edge.SetLayer(pcbnew.Edge_Cuts);b.Add(edge)
    q=route._route_coupled_via_portal_beam(b,pair,ends,middle_layer='B.Cu',
        max_fanins_per_side=2,max_portal_pairs=8,minimum_coupled_fraction=.6,deadline=time.monotonic()+5.)
    assert not q.get('refused'),q
    assert {t.m_Uuid.AsString() for t in b.GetTracks() if t.GetClass()=='PCB_VIA'}==source_ids
    assert all(t.GetLayer()==pcbnew.B_Cu for t in b.GetTracks() if t.GetClass()=='PCB_TRACK')
    assert all(t['signal_vias_added']==0 for t in q['transitions'])
    import cec_fr
    b.BuildConnectivity()
    assert all(cec_fr.net_connectivity_component_count(b,b.GetNetcodeFromNetname(net))==1 for net in (pair['p'],pair['n']))


def test_raw_zero_drill_uses_actual_positive_native_class_default():
    b,pair,ends,pads,vias=via_fixture();vias[2].SetDrill(0)
    assert vias[2].GetDrill()==0 and vias[2].GetDrillValue()>0
    q=route._paired_native_terminal_layers(b,pair,ends,layer='F.Cu',middle_layer='B.Cu')
    assert q['start']['native_plated_access']


def test_compact_witnesses_do_not_mislabel_existing_vias_as_component_pads():
    import cec_probe_evidence
    b,pair,ends,pads,vias=via_fixture()
    access=route._paired_native_terminal_layers(b,pair,ends,layer='F.Cu',middle_layer='B.Cu')
    q=cec_probe_evidence.compact_pair_search_trace(dict(portal_evidence=dict(terminal_layer_access=access)))
    actual=q[0]['terminal_layer_access']['start']
    assert actual['pad_uuids']==[]
    assert actual['barrel_uuids']==[vias[i].m_Uuid.AsString() for i in (0,2)]
