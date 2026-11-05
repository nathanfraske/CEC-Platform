"""Observed Source faults are repair scope, never relaxed load authority."""
from unittest.mock import patch

import pcbnew
import pytest

import cec_force_current as force
import cec_field_coupling as field
import cec_rated_barrel_reseat as reseat
import cec_source_cut_chain as chain
from test_field_proposals import track
from test_rated_barrel_reseat import fixture


OPTIONS=dict(max_source_width_mm=.5,max_replacement_width_mm=.5,
    repair_source_contact_web=True)


def case(tmp_path,quarter=0,prefix='/new-board/',floor=.4):
    data=fixture(tmp_path,quarter,prefix)
    source,child,cuts,old,new,net,contract=data
    for path,uid in ((source,old),(child,new)):
        board=pcbnew.LoadBoard(str(path))
        for t in board.GetTracks():
            if t.GetClass()=='PCB_TRACK':t.SetWidth(round(floor*1e6))
            elif force._uid(t)==uid and path==child:
                t.SetWidth(((300000+round(floor*1e6)+999)//1000)*1000)
        field._save_field_snapshot(board,path)
    contract['required_by_layer_mm']={n:floor for n in contract['required_by_layer_mm']}
    return data


def receive(data,**options):
    source,child,cuts,old,new,net,contract=data
    with patch.object(reseat.rated.topology,'distributed_supply_contracts',
            return_value=dict(contracts={net:contract},refusals={})):
        return reseat.receive(source,child,board_hint='synthetic',
            retired_track_uuids=cuts,retired_via_uuids=[old],
            **dict(OPTIONS,**options))


@pytest.mark.parametrize('quarter,prefix',[(0,'/A/'),(1,'/renamed/'),(2,'/nested/B/'),(3,'/another/')])
@pytest.mark.parametrize('floor',[.4,.400001])
def test_explicit_observed_fault_reseat_grows_exact_source_derived_land(tmp_path,quarter,prefix,floor):
    data=case(tmp_path,quarter,prefix,floor);before=[p.read_bytes() for p in data[:2]]
    strict=receive(data,repair_source_contact_web=False)
    assert not strict['ok'] and 'source_barrel_full_load_actual_contact_web_unqualified' in strict['errors'][0]
    proof=receive(data)
    assert proof['ok'] and proof['complete'],proof
    proposal=proof['source_proposal'];row=proposal['source_barrels'][0]
    assert proposal['exact_source_contact_web_fault_uuids']==[data[3]]
    assert row['replacement_diameter_nm']==((300000+round(floor*1e6)+999)//1000)*1000
    assert row['source_contact_web_fault_observed'] and not row['actual_native_source_contact_web']['ok']
    assert not proposal['actual_source_full_load_preserved']
    assert proposal['unchanged_full_source_current_contract_preserved']
    assert proof['actual_barrel_reseat_matches'][0]['actual_native_candidate_contact_web']['ok']
    assert proof['all_surviving_source_native_partitions_preserved']
    assert proof['exact_source_barrel_projection']['exact_opaque_source_subtraction']
    assert not proof['barrel_ampacity_qualified'] and not proof['current_authority']
    assert not proof['inherited_debt_qualified'] and not proof['release_authority']
    assert [p.read_bytes() for p in data[:2]]==before


@pytest.mark.parametrize('fault',['no_observed_fault','unknown_current','unowned_contact',
    'source_pad_contact','source_locked','source_nonuniform','new_nonuniform','new_drill',
    'new_under_land','new_over_land','new_position','lost_contact','new_inner_contact',
    'too_small_work_bound','lost_cut_port','extra_barrel','changed_sidecar'])
def test_fault_repair_does_not_exempt_geometry_current_contacts_or_saved_ownership(tmp_path,fault):
    data=case(tmp_path);source,child,cuts,old,new,net,contract=data
    if fault.startswith('source_') or fault in ('no_observed_fault','unowned_contact'):
        board=pcbnew.LoadBoard(str(source));v=next(t for t in board.GetTracks() if force._uid(t)==old)
        if fault=='no_observed_fault':v.SetWidth(800000)
        elif fault=='source_locked':v.SetLocked(True)
        elif fault=='source_nonuniform':
            v.Padstack().SetMode(pcbnew.PADSTACK.MODE_FRONT_INNER_BACK)
            v.SetWidth(pcbnew.B_Cu,650000)
        elif fault=='unowned_contact':track(board,net,(10,10),(10,12),width=.4)
        elif fault=='source_pad_contact':
            pad=next(iter(next(iter(board.GetFootprints())).Pads()))
            pad.SetPosition(v.GetPosition())
        field._save_field_snapshot(board,source)
    elif fault=='unknown_current':contract['current_authority']['amps']=0
    elif fault=='too_small_work_bound':
        result=receive(data,max_source_barrel_diameter_mm=.65)
        assert not result['ok'] and 'derived_contact_repair_land_exceeds' in result['errors'][0]
        return
    elif fault=='changed_sidecar':child.with_suffix('.kicad_pro').write_text('{}')
    else:
        board=pcbnew.LoadBoard(str(child));v=next(t for t in board.GetTracks() if force._uid(t)==new)
        if fault=='new_nonuniform':
            v.Padstack().SetMode(pcbnew.PADSTACK.MODE_FRONT_INNER_BACK)
            v.SetWidth(pcbnew.B_Cu,710000)
        elif fault=='new_drill':v.SetDrill(299999)
        elif fault=='new_under_land':v.SetWidth(699999)
        elif fault=='new_over_land':v.SetWidth(701000)
        elif fault=='new_position':v.SetPosition(pcbnew.VECTOR2I_MM(20,20))
        elif fault=='lost_contact':
            next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK'
                and t.GetLayer()==pcbnew.B_Cu).SetLayer(pcbnew.F_Cu)
        elif fault=='new_inner_contact':
            board.SetCopperLayerCount(6)
            for path in (source,):
                parent=pcbnew.LoadBoard(str(path));parent.SetCopperLayerCount(6)
                field._save_field_snapshot(parent,path)
            contract['required_by_layer_mm'].update({f'In{i}.Cu':1. for i in range(1,5)})
            contract['routing_layers'].append('In2.Cu')
            track(board,net,(10.2,10),(10.2,12),width=1.,layer=pcbnew.In2_Cu)
        elif fault=='lost_cut_port':
            t=next(t for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetLayer()==pcbnew.B_Cu)
            t.SetEnd(pcbnew.VECTOR2I_MM(13,10))
        elif fault=='extra_barrel':
            extra=v.Duplicate();extra.m_Uuid.Clone(pcbnew.KIID());extra.SetPosition(pcbnew.VECTOR2I_MM(20,20));board.Add(extra)
        field._save_field_snapshot(board,child)
    before=[p.read_bytes() for p in data[:2]]
    result=receive(data)
    assert not result['ok'] and not result['complete'] and result['errors'],result
    assert [p.read_bytes() for p in data[:2]]==before


@pytest.mark.parametrize('unknown',[dict(ok=False,complete=False),dict(ok=True,complete=True),
    dict(ok=False,complete=True),dict(ok=0,complete=True)])
def test_incomplete_or_unexplained_false_contact_proof_is_never_repair_authority(tmp_path,unknown):
    data=case(tmp_path)
    with patch.object(reseat.context,'receive',return_value=unknown):
        result=receive(data)
    assert not result['ok'] and result['errors']


def test_unused_thin_inner_floor_is_not_an_actual_contact_but_new_inner_contact_is_checked(tmp_path):
    data=case(tmp_path)
    for path in data[:2]:
        board=pcbnew.LoadBoard(str(path));board.SetCopperLayerCount(6)
        field._save_field_snapshot(board,path)
    data[-1]['required_by_layer_mm'].update({f'In{i}.Cu':1. for i in range(1,5)})
    proof=receive(data)
    assert proof['ok'] and proof['complete'],proof
    assert proof['source_proposal']['source_barrels'][0]['replacement_diameter_nm']==700000
    web=proof['actual_barrel_reseat_matches'][0]['actual_native_candidate_contact_web']
    assert web['actual_contact_layers']==['B.Cu','F.Cu']
    assert len(web['unused_copper_layers_not_assumed_to_carry_current'])==4


@pytest.mark.parametrize('flag',[1,0,None,'true',[],{}])
def test_repair_mode_requires_explicit_boolean(tmp_path,flag):
    result=receive(case(tmp_path),repair_source_contact_web=flag)
    assert not result['ok'] and 'explicit_boolean_rated_barrel_repair_mode_required' in result['errors'][0]


@pytest.mark.parametrize('quarter',[0,1,2,3])
def test_saved_typed_chain_retypes_the_explicit_repair_and_exact_whole_source_delta(tmp_path,quarter):
    data=case(tmp_path,quarter,prefix=f'/board-{quarter}/')
    source,child,cuts,old,new,net,contract=data
    phase=dict(kind='rated_barrel_reseat',candidate=str(child),retired_track_uuids=cuts,
        retired_via_uuids=[old],**OPTIONS)
    before=[p.read_bytes() for p in (source,child)]
    with patch.object(reseat.rated.topology,'distributed_supply_contracts',
            return_value=dict(contracts={net:contract},refusals={})):
        proof=chain.receive(source,child,board_hint='synthetic',phases=[phase],per_phase_leases=True)
    assert proof['ok'] and proof['complete'],proof
    assert proof['phase_receiving'][0]['proof']['repair_source_contact_web']
    assert [p.read_bytes() for p in (source,child)]==before


@pytest.mark.parametrize('change',[dict(repair_source_contact_web=1),dict(waive_current=True),
    dict(max_reseat_mm=33),dict(retired_via_uuids=[]),dict(retired_track_uuids=[]),
    dict(retired_via_uuids=['same'],retired_track_uuids=['same'])])
def test_public_chain_repair_schema_rejects_ambiguous_scope(tmp_path,change):
    child=tmp_path/'candidate.kicad_pcb'
    phase=dict(kind='rated_barrel_reseat',candidate=str(child),retired_track_uuids=['track'],
        retired_via_uuids=['via'],**OPTIONS)
    phase.update(change)
    with pytest.raises(ValueError):chain._phases([phase],child)
