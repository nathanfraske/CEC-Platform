"""Real saved CAD, real connectivity and real pair receiving; no success mocks."""
import json
from pathlib import Path
import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_paired_route_reconstruction as receiving
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, rotation=0, prefix='/renamed/', retire_barrels=False,
            source_track_width_mm=.25,allow_source_width_repair=False):
    pn,nn=prefix+'CAN_H',prefix+'CAN_L'
    b=_board([(5,10,pn),(15,10,pn),(5,10.45,nn),(15,10.45,nn)],edge=(0,0,22,22))
    b.SetCopperLayerCount(6)
    props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
    for fp in b.GetFootprints():
        pad=list(fp.Pads())[0];pad.SetNumber('1');pad.SetSize(pcbnew.VECTOR2I_MM(.25,.25))
    for s,z in [((5,10),(10,10)),((10,10),(15,10))]:
        track(b,pn,s,z,width=source_track_width_mm).SetLocked(True)
    track(b,'+5V',(5,16),(15,16),width=1.)
    if retire_barrels:
        import cec_fr as fr
        group=pcbnew.PCB_GROUP(b);group.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP);b.Add(group)
        # A shared factory group is not an ownership claim over the other bus.
        # The N barrel is an old isolated launch, not a .6-mm land squeezed
        # onto the .45-mm pair pitch (which would be an actual source short).
        for net,xy in ((pn,(10,10)),(nn,(10,12)),('+5V',(15,16))):
            via=pcbnew.PCB_VIA(b);via.SetViaType(pcbnew.VIATYPE_THROUGH)
            via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetWidth(600000);via.SetDrill(300000)
            via.SetPosition(pcbnew.VECTOR2I_MM(*xy));via.SetNet(b.FindNet(net));b.Add(via);group.AddItem(via)
    ground=pcbnew.NETINFO_ITEM(b,'GND');b.Add(ground)
    for layer in (pcbnew.In1_Cu,pcbnew.In4_Cu):
        zone=pcbnew.ZONE(b);zone.SetNet(ground);zone.SetLayer(layer)
        zone.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
        zone.SetLocalClearance(200000);zone.SetMinThickness(100000)
        zone.Outline().NewOutline()
        for x,y in [(1,1),(21,1),(21,21),(1,21)]:zone.Outline().Append(x*1000000,y*1000000)
        b.Add(zone)
    if rotation:
        origin=pcbnew.VECTOR2I_MM(11,11);angle=pcbnew.EDA_ANGLE(rotation,pcbnew.DEGREES_T)
        for item in [*b.GetFootprints(),*b.GetTracks(),*b.GetDrawings(),*b.Zones()]:item.Rotate(origin,angle)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    # Fixture generation, not import of a board-specific authority shim.
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[
        dict(name='CAN',diff_pair_width=.25,diff_pair_gap=.2,track_width=.25,
            clearance=.2,via_diameter=.6,via_drill=.3),
        dict(name='Default',track_width=.25,clearance=.2,via_diameter=.6,via_drill=.3)]))))
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    pair_plan=receiving.plan(b,source,board_hint='synthetic',pair_name='CAN',
        allow_source_width_repair=allow_source_width_repair)
    if retire_barrels:
        pair_plan=receiving.plan(b,source,board_hint='synthetic',pair_name='CAN',
            retired_via_uuids=pair_plan['retained_pair_via_uuids'],
            allow_source_width_repair=allow_source_width_repair)
    candidate=force._copy_family(source,tmp_path/'child')
    c=pcbnew.LoadBoard(str(candidate));outgoing=set(pair_plan['retired_track_uuids'])|set(pair_plan['retired_via_uuids'])
    old=[t for t in c.GetTracks() if force._uid(t) in outgoing]
    # Use actual pad coordinates, independent of enum iterator order/rotation.
    for net in (pn,nn):
        points=[p.GetPosition() for f in c.GetFootprints() for p in f.Pads() if p.GetNetname()==net]
        track(c,net,tuple(v/1e6 for v in points[0]),tuple(v/1e6 for v in points[1]),width=.25)
    discard_items(c,old)
    additive._ground_refill(c);field._save_field_snapshot(c,candidate)
    child=Path(additive.finalize_private(source,candidate,tmp_path/'final')['board'])
    return source,child,pair_plan


@pytest.mark.parametrize('rotation,prefix',[(0,'/a/'),(90,'/different/'),(180,'/nested/x/'),(270,'/fourth/')])
def test_exact_rotated_half_bus_reconstruction_gets_real_native_and_physical_receiving(tmp_path,rotation,prefix):
    source,child,plan=fixture(tmp_path,rotation,prefix)
    before=[p.read_bytes() for p in (source,child)]
    result=receiving.receive(source,child,board_hint='synthetic',pair_name='CAN',
        retired_track_uuids=plan['retired_track_uuids'])
    assert result['ok'] and result['complete'],result['errors']
    assert result['actual_saved_native_pair_completion']['connected'] is True
    assert not result['actual_saved_native_pair_physical_contract']['violations']
    assert result['independent_exact_subtract_add_ground_and_rule_replay']['ok'] is True
    assert result['release_authority'] is False and result['inherited_debt_qualified'] is False
    assert [p.read_bytes() for p in (source,child)]==before


@pytest.mark.parametrize('rotation,prefix',[(0,'/old-width/'),(90,'/second/'),(180,'/nested/third/'),(270,'/fourth/')])
def test_saved_whole_pair_rebuild_repairs_old_width_without_changing_new_contract(tmp_path,rotation,prefix):
    source,child,plan=fixture(tmp_path,rotation,prefix,source_track_width_mm=.3,
        allow_source_width_repair=True)
    before=[p.read_bytes() for p in (source,child)]
    strict=receiving.receive(source,child,board_hint='synthetic',pair_name='CAN',
        retired_track_uuids=plan['retired_track_uuids'])
    assert not strict['ok'] and 'width_disagrees' in ' '.join(strict['errors'])
    result=receiving.receive(source,child,board_hint='synthetic',pair_name='CAN',
        retired_track_uuids=plan['retired_track_uuids'],allow_source_width_repair=True)
    assert result['ok'] and result['complete'],result['errors']
    proof=result['independently_derived_source_scope']
    assert proof['nonconforming_source_track_uuids']==plan['retired_track_uuids']
    assert {r['width_nm'] for r in proof['source_track_width_inventory']}=={300000}
    assert proof['source_widths_authorize_new_geometry'] is False
    assert proof['pair']['width']==.25
    assert result['actual_saved_native_pair_completion']['connected']
    assert not result['actual_saved_native_pair_physical_contract']['violations']
    assert result['independent_exact_subtract_add_ground_and_rule_replay']['ok']
    assert not result['inherited_debt_qualified'] and not result['release_authority']
    assert [p.read_bytes() for p in (source,child)]==before


@pytest.mark.parametrize('fault',['partial_scope','wrong_new_width','old_width_in_new',
    'retained_old_node_changed','unrelated_power_changed','contract_changed','missing_member'])
def test_old_width_repair_mode_keeps_all_saved_reconstruction_gates(tmp_path,fault):
    source,child,plan=fixture(tmp_path,source_track_width_mm=.3,allow_source_width_repair=True)
    c=pcbnew.LoadBoard(str(child));ids=plan['retired_track_uuids'];pair=plan['pair']
    if fault=='partial_scope':ids=ids[:1]
    elif fault in ('wrong_new_width','old_width_in_new'):
        next(t for t in c.GetTracks() if t.GetNetname()==pair['p']).SetWidth(
            200000 if fault=='wrong_new_width' else 300000)
    elif fault=='retained_old_node_changed':
        next(iter(c.GetFootprints())).Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='unrelated_power_changed':
        next(t for t in c.GetTracks() if t.GetNetname()=='+5V').SetWidth(900000)
    elif fault=='contract_changed':
        pro=child.with_suffix('.kicad_pro');settings=json.loads(pro.read_text())
        settings['net_settings']['classes'][0]['diff_pair_width']=.3
        pro.write_text(json.dumps(settings))
    elif fault=='missing_member':
        discard_items(c,[t for t in c.GetTracks() if t.GetNetname()==pair['n']])
    if fault not in ('partial_scope','contract_changed'):field._save_field_snapshot(c,child)
    result=receiving.receive(source,child,board_hint='synthetic',pair_name='CAN',
        retired_track_uuids=ids,allow_source_width_repair=True)
    assert not result['ok'] and not result['complete'] and result['errors'],result


@pytest.mark.parametrize('fault',['n_missing','pair_scope','pose','power_trace','extra_signal','narrow','rule_width','uncoupled'])
def test_saved_incomplete_or_unrelated_reconstruction_never_gets_pair_authority(tmp_path,fault):
    source,child,plan=fixture(tmp_path)
    c=pcbnew.LoadBoard(str(child));ids=plan['retired_track_uuids']
    names=plan['pair']
    if fault=='pair_scope':ids=ids[:1]
    elif fault=='n_missing':discard_items(c,[t for t in c.GetTracks() if t.GetNetname()==names['n']])
    elif fault=='pose':next(iter(c.GetFootprints())).Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='power_trace':
        next(t for t in c.GetTracks() if t.GetNetname()=='+5V').SetWidth(900000)
    elif fault=='extra_signal':track(c,'/unowned',(5,18),(15,18),width=.25)
    elif fault=='narrow':next(t for t in c.GetTracks() if t.GetNetname()==names['n']).SetWidth(200000)
    elif fault=='uncoupled':
        t=next(t for t in c.GetTracks() if t.GetNetname()==names['n'])
        t.Move(pcbnew.VECTOR2I_MM(0,2))
        for fp in c.GetFootprints():
            if list(fp.Pads())[0].GetNetname()==names['n']:fp.Move(pcbnew.VECTOR2I_MM(0,2))
    elif fault=='rule_width':
        pro=child.with_suffix('.kicad_pro');settings=json.loads(pro.read_text())
        settings['net_settings']['classes'][0]['diff_pair_width']=.2;pro.write_text(json.dumps(settings))
    if fault not in ('pair_scope','rule_width'):field._save_field_snapshot(c,child)
    result=receiving.receive(source,child,board_hint='synthetic',pair_name='CAN',retired_track_uuids=ids)
    assert result['ok'] is False and result['complete'] is False and result['errors'],result


@pytest.mark.parametrize('rotation,prefix',[(0,'/replacement/'),(90,'/new/x/'),(180,'/another/'),(270,'/fourth/')])
def test_saved_whole_pair_barrel_rebuild_has_real_physical_and_exact_group_replay(tmp_path,rotation,prefix):
    source,child,plan=fixture(tmp_path,rotation,prefix,retire_barrels=True)
    before=[p.read_bytes() for p in (source,child)]
    result=receiving.receive(source,child,board_hint='synthetic',pair_name='CAN',
        retired_track_uuids=plan['retired_track_uuids'],retired_via_uuids=plan['retired_via_uuids'])
    assert result['ok'] and result['complete'],result['errors']
    assert result['actual_saved_native_pair_completion']['connected'] is True
    assert not result['actual_saved_native_pair_physical_contract']['violations']
    assert result['independent_exact_subtract_add_ground_and_rule_replay']['ok']
    assert result['source_local_factory_group_uuids']==plan['source_local_factory_group_uuids']
    partitions=result['paired_native_partition_preservation']
    assert partitions['preserved'] and partitions['exact_positive_native_island_overlap']
    assert not partitions['whole_zone_uuid_connectivity_credit']
    assert partitions['demoted_component_count']==0
    assert result['retired_via_uuids']==plan['retired_via_uuids']
    assert not result['release_authority'] and not result['inherited_debt_qualified']
    assert [p.read_bytes() for p in (source,child)]==before


@pytest.mark.parametrize('fault',['partial_barrels','missing_explicit_barrel_mode','foreign_barrel',
    'group_claim','orphan_pair_barrel','missing_n','terminal_moved','power_changed'])
def test_saved_whole_barrel_mode_never_waives_terminal_group_or_power_obligations(tmp_path,fault):
    source,child,plan=fixture(tmp_path,retire_barrels=True)
    c=pcbnew.LoadBoard(str(child));vias=plan['retired_via_uuids']
    if fault=='partial_barrels':vias=vias[:1]
    elif fault=='missing_explicit_barrel_mode':vias=None
    elif fault=='foreign_barrel':
        discard_items(c,[v for v in c.GetTracks() if v.GetClass()=='PCB_VIA' and v.GetNetname()=='+5V'])
    elif fault=='group_claim':
        group=next(iter(c.Groups()))
        group.AddItem(next(t for t in c.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()==plan['pair']['p']))
    elif fault=='orphan_pair_barrel':
        track(c,plan['pair']['p'],(18,18),(19,18),width=.25)
        via=pcbnew.PCB_VIA(c);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetPosition(pcbnew.VECTOR2I_MM(18,18))
        via.SetWidth(600000);via.SetDrill(300000);via.SetNet(c.FindNet(plan['pair']['p']));c.Add(via)
    elif fault=='missing_n':discard_items(c,[t for t in c.GetTracks() if t.GetNetname()==plan['pair']['n']])
    elif fault=='terminal_moved':next(iter(c.GetFootprints())).Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='power_changed':next(t for t in c.GetTracks() if t.GetNetname()=='+5V').SetWidth(900000)
    if fault not in ('partial_barrels','missing_explicit_barrel_mode'):field._save_field_snapshot(c,child)
    result=receiving.receive(source,child,board_hint='synthetic',pair_name='CAN',
        retired_track_uuids=plan['retired_track_uuids'],retired_via_uuids=vias)
    assert not result['ok'] and not result['complete'] and result['errors'],result
