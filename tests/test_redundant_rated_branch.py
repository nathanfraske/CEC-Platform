import math
from unittest import mock
import pcbnew,pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_redundant_rated_branch as redundant
from cec_native_items import discard_items
from test_lastmile import _board
from test_field_proposals import track


def fixture(tmp_path,quarter=0,shift=(0,0),fault=None):
    net='RENAMED_SUPPLY'
    b=_board([(5,10,net),(25,10,net),(25,25,'OTHER')],edge=(0,0,40,40))
    main=track(b,net,(5,10),(25,10));tail=track(b,net,(15,10),(15,20))
    if fault=='locked':tail.SetLocked(True)
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('PROTECTED');b.Add(g);g.AddItem(tail)
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        item.Rotate(pcbnew.VECTOR2I_MM(15,15),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        item.Move(pcbnew.VECTOR2I_MM(*shift))
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,source)
    selected=force._uid(main if fault=='required' else tail)
    candidate=force._copy_family(source,tmp_path/'candidate');b=pcbnew.LoadBoard(str(candidate))
    discard_items(b,[t for t in b.GetTracks() if force._uid(t)==selected])
    if fault=='added':track(b,net,(26,20),(28,20))
    elif fault=='unowned_width':next(iter(b.GetTracks())).SetWidth(150000)
    field._save_field_snapshot(b,candidate)
    catalog=dict(contracts={net:dict(net=net,role='all_terminal_conservative_aggregate',
        current_authority=dict(amps=.1,source='explicit_synthetic_test_catalog'),
        required_by_layer_mm={'F.Cu':.2,'B.Cu':.2},routing_layers=['F.Cu','B.Cu'])})
    return source,candidate,selected,catalog


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('shift',[(0,0),(2,-1)])
def test_real_redundant_supply_tail_keeps_full_load_and_drilled_terminal_material(tmp_path,quarter,shift):
    source,candidate,uid,catalog=fixture(tmp_path,quarter,shift);before=source.read_bytes()
    with mock.patch.object(redundant.rated.topology,'distributed_supply_contracts',return_value=catalog):
        r=redundant.receive(source,candidate,board_hint='synthetic',retired_track_uuids=[uid],max_source_track_mm=16)
    assert r['ok'] and r['complete'],r
    assert r['added_native_uuids']==[] and not r['current_qualified'] and not r['release_authority']
    assert source.read_bytes()==before


@pytest.mark.parametrize('fault',['required','added','unowned_width','locked','group','no_catalog','no_amps','changed_catalog','deadline'])
def test_no_loss_new_material_unknown_current_or_lock_scope_is_accepted(tmp_path,fault):
    source,candidate,uid,catalog=fixture(tmp_path,fault=fault)
    call=dict(return_value=catalog)
    if fault=='no_catalog':call=dict(return_value=dict(contracts={}))
    elif fault=='no_amps':next(iter(catalog['contracts'].values()))['current_authority']={}
    elif fault=='changed_catalog':
        changed=dict(contracts={n:dict(c,current_authority=dict(amps=.2)) for n,c in catalog['contracts'].items()})
        call=dict(side_effect=[catalog,changed])
    with mock.patch.object(redundant.rated.topology,'distributed_supply_contracts',**call):
        r=redundant.receive(source,candidate,board_hint='synthetic',retired_track_uuids=[uid],
            max_source_track_mm=32,timeout_s=0 if fault=='deadline' else 10)
    assert not r['ok'] and r['errors'],r


@pytest.mark.parametrize('budget',[True,math.inf,math.nan,30.1])
def test_receiving_wall_budget_is_finite_not_scope_permission(tmp_path,budget):
    source,candidate,uid,catalog=fixture(tmp_path)
    with mock.patch.object(redundant.rated.topology,'distributed_supply_contracts',return_value=catalog):
        r=redundant.receive(source,candidate,board_hint='synthetic',retired_track_uuids=[uid],
            timeout_s=budget,max_source_track_mm=16)
    assert not r['ok'] and 'bounded_unused_rated_branch_context_required' in r['errors'][0]
