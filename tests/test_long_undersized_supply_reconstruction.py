"""Long source reach requires positive fault evidence, never a current waiver."""
import math
from unittest import mock

import pcbnew
import pytest

import cec_constraints as constraints
import cec_field_coupling as field
import cec_force_current as force
import cec_rated_branch_layer_chain as worker
import cec_rated_branch_repair as rated
import cec_source_cut_chain as chain
import cec_source_literal_additions as literal
import cec_source_literal_retirement as subtraction
import cec_source_retaining_ses_import as raw
from test_field_proposals import track
from test_lastmile import _board
from test_undersized_inner_supply_repair import checker


def fixture(tmp_path, reach=48., rotation=0, mirror=False, face=pcbnew.F_Cu):
    net='/renamed/%s_%s_%s_%s/explicit-load'%(reach,rotation,mirror,face)
    def point(x,y):
        x,y=x-50,y-50
        if mirror:x=-x
        a=math.radians(rotation)
        return [round((50+x*math.cos(a)-y*math.sin(a))*1e6),
                round((50+x*math.sin(a)+y*math.cos(a))*1e6)]
    ends=[point(15,40),point(15+reach,40)]
    b=_board([(p[0]/1e6,p[1]/1e6,net) for p in ends],edge=(0,0,100,100))
    b.SetCopperLayerCount(6)
    for fp in b.GetFootprints():
        pad=next(iter(fp.Pads()));pad.SetNumber('1')
        layers=pcbnew.LSET();layers.AddLayer(face);pad.SetLayerSet(layers)
    old=track(b,net,(0,0),(1,0),layer=pcbnew.In2_Cu,width=.5)
    old.SetStart(pcbnew.VECTOR2I(*ends[0]));old.SetEnd(pcbnew.VECTOR2I(*ends[1]))
    uid=force._uid(old)
    for at in ends:
        via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I(*at))
        via.SetWidth(1200000);via.SetDrill(300000);via.SetNetCode(b.GetNetcodeFromNetname(net))
        via.SetViaType(pcbnew.VIATYPE_THROUGH);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    catalog=dict(contracts={net:dict(net=net,clearance_mm=.2,
        current_authority=dict(amps=3.,geometry_margin=1.25,margin_included=False,
            source='explicit_synthetic_load_catalog'),
        required_by_layer_mm={'F.Cu':.4773698,'B.Cu':.4773698,'In2.Cu':5.719034},
        routing_layers=['F.Cu','In2.Cu','B.Cu'])})
    stages=[dict(layer=pcbnew.LayerName(face),points_nm=ends)]
    return source,uid,net,catalog,stages


OPTIONS=dict(max_source_track_mm=64.,max_source_width_mm=1.,max_replacement_width_mm=1.,
    allow_rated_source_inner_layers=True,repair_undersized_source=True)


@pytest.mark.parametrize('reach',[40.,60.])
@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_constructed_long_fault_repair_reuses_plated_endpoints_and_replays_saved_source(
        tmp_path,reach,rotation,face):
    source,uid,net,catalog,stages=fixture(tmp_path,reach,rotation,rotation in (90,270),face)
    saved=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog), \
            mock.patch.dict(constraints.CHECKERS,{'trace-width-high-current':checker(catalog)}):
        with pytest.raises(ValueError):
            worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],stages=stages,
                **dict(OPTIONS,repair_undersized_source=False))
        board,proposal=worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],
            stages=stages,**OPTIONS)
        candidate=force._copy_family(source,tmp_path/'private-full-load')
        field._save_field_snapshot(board,candidate)
        options=dict(OPTIONS,allow_rated_layer_bridges=True)
        received=rated.receive(source,candidate,board_hint='synthetic',retired_track_uuids=[uid],**options)
        composed=chain.receive(source,candidate,board_hint='synthetic',phases=[dict(kind='rated_branch',
            candidate=str(candidate),retired_track_uuids=[uid],**options)])
    assert received['ok'] and received['complete'] and composed['ok'] and composed['complete'],(received,composed)
    assert received['source_proposal']['extended_undersized_source_reach']
    assert received['strict_source_current_fault_repair']['before_fault_objects']==1
    assert received['strict_source_current_fault_repair']['after_fault_objects']==0
    assert proposal['undersized_source_repair_scope_explicit'] is True
    assert proposal['derived_new_barrel_sites_nm']==[] and not proposal['new_via_uuids']
    assert all(row['width_nm']==500000 for row in proposal['full_width_native_legs'])
    assert not proposal['branch_sharing_inferred'] and not proposal['routing_admitted']
    assert not received['current_authority'] and not received['release_authority']
    assert source.read_bytes()==saved


@pytest.mark.parametrize('fault',['unproved_current','missing_contract','source_group','rated_long_edge',
    'plane_source','missing_inner_scope','implicit_repair_flag','reach_over_bound'])
def test_extended_constructor_reach_keeps_existing_source_and_current_gates(tmp_path,fault):
    source,uid,net,catalog,stages=fixture(tmp_path);options=dict(OPTIONS)
    if fault in ('source_group','rated_long_edge','plane_source'):
        b=pcbnew.LoadBoard(str(source));old=next(t for t in b.GetTracks() if force._uid(t)==uid)
        if fault=='source_group':
            group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(old)
        elif fault=='rated_long_edge':old.SetLayer(pcbnew.F_Cu)
        else:old.SetLayer(pcbnew.In1_Cu)
        field._save_field_snapshot(b,source)
    if fault=='missing_contract':catalog=dict(contracts={})
    elif fault=='missing_inner_scope':options['allow_rated_source_inner_layers']=False
    elif fault=='implicit_repair_flag':options['repair_undersized_source']=1
    elif fault=='reach_over_bound':options['max_source_track_mm']=64.000001
    saved=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog), \
            mock.patch.dict(constraints.CHECKERS,{'trace-width-high-current':checker(catalog,
                missing=fault=='unproved_current')}):
        with pytest.raises(ValueError):
            worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],stages=stages,**options)
    assert source.read_bytes()==saved


def test_extended_cut_total_is_bounded_even_with_many_proved_faults(tmp_path):
    source,uid,net,catalog,_=fixture(tmp_path,60.)
    b=pcbnew.LoadBoard(str(source));uids=[uid]
    for y in (42,44):
        edge=track(b,net,(15,y),(75,y),layer=pcbnew.In2_Cu,width=.5);uids.append(force._uid(edge))
    field._save_field_snapshot(b,source)
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog):
        with pytest.raises(ValueError,match='bounded_extended_undersized_source_cut_required'):
            rated.plan(b,source,board_hint='synthetic',retired_track_uuids=uids,
                max_source_track_mm=64.,max_source_width_mm=1.,allow_rated_source_inner_layers=True,
                repair_undersized_source=True)


@pytest.mark.parametrize('value',[True,None,'64',0,-1,64.000001,float('inf'),float('nan')])
def test_extended_span_is_explicit_finite_numeric(value):
    with pytest.raises(ValueError):rated.source_span_mm(value,allow_undersized_reconstruction=True)


@pytest.mark.parametrize('flag',[1,None,'yes'])
def test_extended_mode_is_not_truthiness(flag):
    with pytest.raises(ValueError):rated.source_span_mm(48.,allow_undersized_reconstruction=flag)


def test_legacy_work_bounds_are_unchanged():
    with pytest.raises(ValueError):rated.source_span_mm(32.000001)
    assert rated.source_span_mm(64.,allow_undersized_reconstruction=True)==64.
    assert rated.plan.__kwdefaults__['max_source_track_mm']==8.
    assert worker.construct.__kwdefaults__['repair_undersized_source'] is False


@pytest.mark.parametrize('candidate_normalized',[False,True])
def test_proved_fault_cut_preserves_opaque_source_properties_not_serializer_order(tmp_path,candidate_normalized):
    from test_source_literal_retirement import hidden_field_last
    source,uid,net,catalog,stages=fixture(tmp_path)
    hidden_field_last(source);saved=source.read_bytes()
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog), \
            mock.patch.dict(constraints.CHECKERS,{'trace-width-high-current':checker(catalog)}):
        board,_=worker.construct(source,board_hint='synthetic',retired_track_uuids=[uid],
            stages=stages,**OPTIONS)
        candidate=force._copy_family(source,tmp_path/'private')
        projection=tmp_path/'native.kicad_pcb';field._save_field_snapshot(board,projection)
        raw.write_raw(candidate,literal.assemble(subtraction.subtract(raw.raw_text(source),[uid]),
            raw.raw_text(projection)))
        if candidate_normalized:field._save_field_snapshot(pcbnew.LoadBoard(str(candidate)),candidate)
        received=rated.receive(source,candidate,board_hint='synthetic',retired_track_uuids=[uid],
            allow_rated_layer_bridges=True,**OPTIONS)
    assert received['ok'] is not candidate_normalized,received
    if not candidate_normalized:
        assert received['literal_source_subtraction']['exact_opaque_source_subtraction']
        assert received['literal_source_subtraction']['independent_full_native_inventory_equal']
    assert source.read_bytes()==saved
