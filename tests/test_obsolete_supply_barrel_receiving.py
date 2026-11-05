"""Actual saved hole deletion composes with full-current Source repair.

Only the explicit synthetic current catalog and canonical terminal catalog
are mocked. Geometry, via/group ownership, literal subtraction, native
partitions, drill-subtracted paths, debt and whole-chain replay are real.
"""
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_constraints as constraints
import cec_field_coupling as field
import cec_force_current as force
import cec_rated_branch_repair as rated
import cec_source_cut_chain as chain
import cec_source_obsolete_supply_barrels as barrels
import cec_surface_supply_path_graph as surface
from cec_native_items import discard_items
from test_field_proposals import track
from test_source_obsolete_supply_barrels import fixture, source_context
from test_undersized_inner_supply_repair import checker


OPTIONS=dict(allow_rated_layer_bridges=True,allow_rated_source_inner_layers=True,
    repair_undersized_source=True,retire_obsolete_terminal_vias=True)


@contextmanager
def catalogs(contracts,*,new_fault=False):
    catalog=dict(contracts=contracts)
    with mock.patch.object(rated.topology,'distributed_supply_contracts',return_value=catalog), \
         mock.patch.object(barrels.canonical,'prepare',side_effect=source_context), \
         mock.patch.dict(constraints.CHECKERS,{'trace-width-high-current':checker(catalog,new_fault=new_fault)}):
        yield


def case(tmp_path,angle=0,mirror=False,face=pcbnew.F_Cu,grouped=True):
    source,parent,cut,vias,contracts=fixture(tmp_path,angle=angle,mirror=mirror,face=face,grouped=grouped)
    props=parent.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';parent.SetProperties(props)
    field._save_field_snapshot(parent,source)
    trial=force._copy_family(source,tmp_path/'native-trial');board=pcbnew.LoadBoard(str(trial))
    old=next(t for t in board.GetTracks()if force._uid(t)==cut)
    a,z=tuple(old.GetStart()),tuple(old.GetEnd());net=str(old.GetNetname())
    discard_items(board,[t for t in board.GetTracks()if force._uid(t)in{cut,*vias[:2]}])
    track(board,net,tuple(v/1e6 for v in a),tuple(v/1e6 for v in z),layer=face,width=.2)
    field._save_field_snapshot(board,trial)
    child=Path(additive.finalize_private(source,trial,tmp_path/'final')['board'])
    return source,child,cut,vias,contracts,net


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_saved_actual_bore_deletion_and_factory_members_compose(tmp_path,angle,mirror,face):
    source,child,cut,vias,contracts,_=case(tmp_path,angle,mirror,face);saved=[p.read_bytes()for p in(source,child)]
    with catalogs(contracts):
        received=rated.receive(source,child,board_hint='synthetic-explicit-source',retired_track_uuids=[cut],**OPTIONS)
        combined=chain.receive(source,child,board_hint='synthetic-explicit-source',phases=[dict(
            kind='rated_branch',candidate=str(child),retired_track_uuids=[cut],**OPTIONS)])
    assert received['ok']and received['complete']and combined['ok']and combined['complete'],(received,combined)
    assert received['retired_track_uuids']==[cut]and received['retired_via_uuids']==sorted(vias[:2])
    assert len(received['source_local_factory_group_uuids'])==1
    assert received['drill_subtracted_full_width_surface_paths']['all_source_pads_surface_connected']
    assert received['strict_source_current_fault_repair']['after_fault_objects']==0
    assert received['literal_source_subtraction']['independent_full_native_inventory_and_membership_equal']
    assert combined['literal_native_cut_projection']['only_exact_derived_memberships_removed']
    assert combined['retired_via_uuids']==sorted(vias[:2])
    for p in(received,combined):assert not p['release_authority']
    actual=pcbnew.LoadBoard(str(child));group=next(iter(actual.Groups()))
    assert sorted(force._uid(i)for i in group.GetItems())==vias[2:]
    assert [p.read_bytes()for p in(source,child)]==saved


def test_ungrouped_unlocked_terminal_barrels_keep_legacy_literal_projection(tmp_path):
    source,child,cut,vias,contracts,_=case(tmp_path,grouped=False)
    with catalogs(contracts):
        proof=rated.receive(source,child,board_hint='synthetic-explicit-source',retired_track_uuids=[cut],**OPTIONS)
    assert proof['ok']and proof['retired_via_uuids']==sorted(vias[:2]),proof
    assert not proof['source_local_factory_group_uuids']
    assert proof['literal_source_subtraction']['exact_opaque_source_subtraction']


@pytest.mark.parametrize('bad',['default','keep_drill','remove_other_via','changed_other_member',
    'thin','inner','open','scalar','new_via','moved_pad','new_current_fault','physical_graph_refusal'])
def test_complete_original_scope_and_physical_path_are_mandatory(tmp_path,bad):
    source,child,cut,vias,contracts,net=case(tmp_path);board=pcbnew.LoadBoard(str(child));options=dict(OPTIONS)
    if bad=='default':options['retire_obsolete_terminal_vias']=False
    elif bad=='keep_drill':
        parent=pcbnew.LoadBoard(str(source));v=next(t for t in parent.GetTracks()if force._uid(t)==vias[0])
        incoming=v.Duplicate();board.Add(incoming);next(iter(board.Groups())).AddItem(incoming)
    elif bad=='remove_other_via':discard_items(board,[t for t in board.GetTracks()if force._uid(t)==vias[2]])
    elif bad=='changed_other_member':next(t for t in board.GetTracks()if force._uid(t)==vias[2]).SetLocked(False)
    elif bad=='thin':next(t for t in board.GetTracks()if t.GetClass()=='PCB_TRACK').SetWidth(199999)
    elif bad=='inner':next(t for t in board.GetTracks()if t.GetClass()=='PCB_TRACK').SetLayer(pcbnew.In2_Cu)
    elif bad=='open':
        t=next(t for t in board.GetTracks()if t.GetClass()=='PCB_TRACK')
        t.SetEnd(t.GetStart()+pcbnew.VECTOR2I_MM(.1,.1))
    elif bad=='scalar':track(board,'/SCALAR',(3,3),(4,3))
    elif bad=='new_via':
        v=pcbnew.PCB_VIA(board);v.SetNetCode(board.GetNetcodeFromNetname(net));v.SetPosition(pcbnew.VECTOR2I_MM(3,3))
        v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(v)
    elif bad=='moved_pad':next(iter(board.GetFootprints())).Move(pcbnew.VECTOR2I(1000,0))
    field._save_field_snapshot(board,child)
    with catalogs(contracts,new_fault=bad=='new_current_fault'):
        if bad=='physical_graph_refusal':
            with mock.patch.object(surface,'prove',return_value=dict(complete=False,all_source_pads_surface_connected=False)):
                proof=rated.receive(source,child,board_hint='synthetic-explicit-source',retired_track_uuids=[cut],**options)
        else:proof=rated.receive(source,child,board_hint='synthetic-explicit-source',retired_track_uuids=[cut],**options)
    assert not proof['ok']and proof['errors'],proof


@pytest.mark.parametrize('bad',[
    dict(retire_obsolete_terminal_vias=1),dict(retire_obsolete_terminal_vias=True),
    dict(OPTIONS,repair_undersized_source=False),dict(OPTIONS,allow_rated_source_inner_layers=False),
    dict(OPTIONS,allow_rated_layer_bridges=False),dict(OPTIONS,repair_aggregate_current_domain=True),
    dict(OPTIONS,use_source_declared_consumer_island=True),dict(OPTIONS,allow_locked_via_uuids=[]),
    dict(OPTIONS,retired_via_uuids=[]),dict(OPTIONS,current_amps=.01)])
def test_mode_has_no_arbitrary_lock_via_or_current_authority(bad):
    with pytest.raises(ValueError):rated.reconstruction_options(bad)


def test_partial_physical_evidence_or_wrong_source_members_cannot_seed_chain_cache(tmp_path):
    source,child,cut,_,contracts,_=case(tmp_path)
    row=dict(kind='rated_branch',candidate=str(child),retired_track_uuids=[cut],**OPTIONS)
    with catalogs(contracts):
        with mock.patch.object(surface,'prove',return_value=dict(complete=False,all_source_pads_surface_connected=False)):
            bad=chain.receive(source,child,board_hint='synthetic-explicit-source',phases=[row])
        good=chain.receive(source,child,board_hint='synthetic-explicit-source',phases=[row])
    assert not bad['ok']and good['ok'],(bad,good)


def test_untyped_centered_endpoint_is_retained_and_its_inner_boundary_not_waived(tmp_path):
    source,child,cut,vias,contracts,_=case(tmp_path)
    parent=pcbnew.LoadBoard(str(source));old=next(t for t in parent.GetTracks()if force._uid(t)==vias[0])
    pad=next(p for f in parent.GetFootprints()for p in f.Pads()if p.GetPosition()==old.GetPosition())
    def partial(*args,**kwargs):
        context=source_context(*args,**kwargs);context['pads'].pop(force._uid(pad));return context
    # A missing positive role can never license physical deletion. Retaining
    # the Source via also keeps its REAL old inner boundary obligation, even
    # if a full-width F route makes a simpler whole-net graph look connected.
    board=pcbnew.LoadBoard(str(child));retained=old.Duplicate()
    retained.m_Uuid.Clone(pcbnew.KIID(vias[0]));board.Add(retained)
    next(iter(board.Groups())).AddItem(retained);field._save_field_snapshot(board,child)
    with catalogs(contracts),mock.patch.object(barrels.canonical,'prepare',side_effect=partial):
        q=barrels.plan(parent,source,contracts,[cut],board_hint='synthetic-explicit-source')
        proof=rated.receive(source,child,board_hint='synthetic-explicit-source',retired_track_uuids=[cut],**OPTIONS)
    assert vias[0]not in q['retired_via_uuids']and vias[1]in q['retired_via_uuids']
    assert vias[0]in{r['uuid']for r in q['retained_endpoint_vias']}
    assert not proof['ok']and any('boundary' in e or 'retired_endpoint' in e for e in proof['errors']),proof
