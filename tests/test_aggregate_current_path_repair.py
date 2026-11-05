"""Whole-load repair is distinct from ordinary/distributed routing authority."""
from copy import deepcopy
import math

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_aggregate_path_repair as repair
import cec_constraints as constraints
import cec_field_coupling as field
import cec_force_current as force
import cec_full_current_planar_reflow as full
import cec_rated_branch_repair as rated
import cec_source_cut_chain as chain
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, monkeypatch, quarter=0, mirror=False, obstacle=False):
    net='/partition_%s_%s/ARBITRARY_PASS_THROUGH'%(quarter,mirror)
    def xy(p):
        x,y=p[0]-20,p[1]-20
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return 20+x,20+y
    points=[xy(p) for p in ((5,5),(15,5),(15,15),(25,15))]
    board=_board([(*p,net) for p in (points[0],points[-1])],edge=(0,0,40,40))
    board.SetCopperLayerCount(6)
    for fp in board.GetFootprints():
        pad=next(iter(fp.Pads()));pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetLayerSet(pcbnew.LSET.AllCuMask());pad.SetSize(pcbnew.VECTOR2I_MM(1.5,1.5))
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(.6,.6))
    ids=[]
    for a,z in zip(points,points[1:]):
        t=track(board,net,a,z,layer=pcbnew.In2_Cu,width=.2);t.SetLocked(True);ids.append(force._uid(t))
    if obstacle:
        board.Add(pcbnew.NETINFO_ITEM(board,'/unrelated/barrier'))
        track(board,'/unrelated/barrier',xy((14.4,9.5)),xy((14.4,10.5)),layer=pcbnew.In2_Cu,width=.4)
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    # Explicit synthetic authority only. Production rederives the complete
    # selected board-policy domain and stack widths; no load comes from a pad.
    domain=dict(net=net,amps=1.,complete=True,source_refs=('X1',),sink_refs=('X2',),authority_refs=('X1','X2'))
    contract=dict(net=net,amps=1.,current_authority=dict(amps=1.,geometry_margin=1.25,
        margin_included=False,source='board_design_basis'),routing_layers=['F.Cu','In2.Cu','B.Cu'],
        required_by_layer_mm={'F.Cu':.2,'In2.Cu':1.25,'B.Cu':.2})
    monkeypatch.setattr(full,'_model',lambda *a,**kw:('aggregate_source_sink',deepcopy(domain),deepcopy(contract)))
    def checker(board,path,ctx):
        graph=force._graph(board,net,domain,contract,{})[0]
        segments=[dict(uuid=force._uid(t),layer='In2.Cu',actual_mm=t.GetWidth()/1e6,required_mm=1.25)
            for t in board.GetTracks() if t.GetClass()=='PCB_TRACK' and t.GetNetname()==net
            and t.GetLayer()==pcbnew.In2_Cu and t.GetWidth()<1250000]
        if not segments or graph['rated_connectivity']['connected']:
            return True,'explicit synthetic domain has a complete rated native path',[]
        return False,'explicit complete synthetic native current debt',[
            dict(type='current_debt_inventory',schema=1,complete=True,trace_fault_count=0,domain_fault_count=1,violation_count=1),
            dict(type='current_domain_path',net=net,current_authority=deepcopy(contract['current_authority']),
                original_connectivity=dict(available=True,connected=graph['trace_connectivity']['connected']),
                rated_connectivity=dict(available=True,connected=False),
                undersized_segments=segments,removed_undersized_segments=len(segments))]
    monkeypatch.setitem(constraints.CHECKERS,'trace-width-high-current',checker)
    return source,net,ids,domain,contract,xy


def build(source,ids):
    board=pcbnew.LoadBoard(str(source))
    made=repair.construct(board,source,board_hint='synthetic',retired_track_uuids=ids,allow_locked_track_uuids=ids)
    raw=force._copy_family(source,source.parent/'raw');field._save_field_snapshot(board,raw)
    child=additive.finalize_private(source,raw,source.parent/'final')['board']
    return child,made


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_native_full_load_path_is_widened_and_beveled_with_no_new_barrels(tmp_path,monkeypatch,quarter,mirror):
    source,net,ids,domain,contract,xy=fixture(tmp_path,monkeypatch,quarter,mirror);original=source.read_bytes()
    child,made=build(source,ids)
    proof=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=ids,**repair.PARAMETERS)
    composed=chain.receive(source,child,board_hint='synthetic',phases=[dict(kind='rated_branch',candidate=child,
        retired_track_uuids=ids,**repair.PARAMETERS)],per_phase_leases=True)
    assert proof['ok'] and proof['complete'] and composed['ok'] and composed['complete'],(proof,composed)
    assert proof['source_aggregate_current_domain_unchanged'] and not proof['source_distributed_load_ownership_unchanged']
    assert proof['independent_complete_rated_paths'][net]['rated_connectivity']['connected']
    assert proof['strict_source_current_fault_repair']['before_fault_objects']==4
    assert proof['strict_source_current_fault_repair']['after_fault_objects']==0
    assert all(k[0]=='domain_trace' for k in made['source_proposal']['exact_source_current_fault_keys'])
    assert made['width_nm']==1250000 and made['new_vias']==made['new_holes']==0
    assert made['source_track_length_mm']==30 and made['replacement_track_length_mm']<30
    assert not proof['current_authority'] and not proof['release_authority'] and source.read_bytes()==original


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_wider_copper_replans_a_blocked_suffix_instead_of_violating_clearance(tmp_path,monkeypatch,quarter,mirror):
    source,net,ids,domain,contract,xy=fixture(tmp_path,monkeypatch,quarter,mirror,obstacle=True)
    original=source.read_bytes();child,made=build(source,ids)
    proof=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=ids,**repair.PARAMETERS)
    assert proof['ok'] and proof['complete'],proof
    assert made['width_nm']==1250000 and made['replacement_track_length_mm']<30
    assert len(made['added_native_uuids'])>=2 and made['new_vias']==0
    assert proof['independent_complete_rated_paths'][net]['rated_connectivity']['connected']
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['no_explicit_aggregate_scope','no_inner_scope','no_repair_scope','numeric_mode',
    'narrow','wrong_layer','extra_scalar','new_via','component_move','unowned_track','changed_load',
    'incomplete_inventory','source_not_current_fault','preexisting_open','source_group','source_outer','already_rated'])
def test_aggregate_path_tier_refuses_guesses_partial_proofs_and_other_material(tmp_path,monkeypatch,fault):
    source,net,ids,domain,contract,xy=fixture(tmp_path,monkeypatch)
    child,made=build(source,ids);options=dict(repair.PARAMETERS)
    if fault=='no_explicit_aggregate_scope':options['repair_aggregate_current_domain']=False
    elif fault=='no_inner_scope':options['allow_rated_source_inner_layers']=False
    elif fault=='no_repair_scope':options['repair_undersized_source']=False
    elif fault=='numeric_mode':options['repair_aggregate_current_domain']=1
    elif fault=='incomplete_inventory':
        monkeypatch.setitem(constraints.CHECKERS,'trace-width-high-current',lambda *a:(False,'incomplete',[]))
    elif fault=='source_not_current_fault':
        monkeypatch.setitem(constraints.CHECKERS,'trace-width-high-current',lambda *a:(True,'not a source current fault',[]))
    elif fault=='changed_load':
        def model(board,path,*a):
            d,c=deepcopy(domain),deepcopy(contract)
            if str(path)!=str(source):d['amps']=c['amps']=c['current_authority']['amps']=.5
            return 'aggregate_source_sink',d,c
        monkeypatch.setattr(full,'_model',model)
    elif fault in ('preexisting_open','source_group','source_outer','already_rated'):
        board=pcbnew.LoadBoard(str(source));edge=next(iter(board.GetTracks()))
        if fault=='preexisting_open':edge.Move(pcbnew.VECTOR2I_MM(0,2))
        elif fault=='source_group':
            group=pcbnew.PCB_GROUP(board);group.SetName('unrelated_owner');board.Add(group);group.AddItem(edge)
        elif fault=='source_outer':edge.SetLayer(pcbnew.F_Cu)
        else:edge.SetWidth(1300000)
        field._save_field_snapshot(board,source)
    else:
        board=pcbnew.LoadBoard(str(child));edge=next(iter(board.GetTracks()))
        if fault=='narrow':edge.SetWidth(1249999)
        elif fault=='wrong_layer':edge.SetLayer(pcbnew.In1_Cu)
        elif fault=='component_move':next(iter(board.GetFootprints())).Move(pcbnew.VECTOR2I_MM(0,2))
        elif fault=='unowned_track':
            track(board,net,xy((30,30)),xy((31,30)),layer=pcbnew.F_Cu,width=.2)
        elif fault=='extra_scalar':
            board.Add(pcbnew.NETINFO_ITEM(board,'/ordinary/new'));track(board,'/ordinary/new',(30,30),(31,30))
        else:
            v=pcbnew.PCB_VIA(board);v.SetNet(board.FindNet(net));v.SetPosition(pcbnew.VECTOR2I_MM(*xy((5,5))))
            v.SetWidth(600000);v.SetDrill(300000);v.SetViaType(pcbnew.VIATYPE_THROUGH)
            v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);board.Add(v)
        field._save_field_snapshot(board,child)
    proof=rated.receive(source,child,board_hint='synthetic',retired_track_uuids=ids,**options)
    assert not proof['ok'] and proof['errors'],proof


@pytest.mark.parametrize('fault',['not_aggregate','incomplete','no_sources','no_sinks','different_amps'])
def test_positive_whole_domain_not_inferred_from_a_small_trace_or_name(tmp_path,monkeypatch,fault):
    source,net,ids,domain,contract,xy=fixture(tmp_path,monkeypatch)
    # Exercise the actual shared model's complete-domain checks, rather than
    # letting a test-only facade grant positive authority to incomplete data.
    from cec_full_current_planar_reflow import topology
    monkeypatch.undo()
    if fault=='not_aggregate':
        monkeypatch.setattr(topology,'board_current_domains',lambda *a,**kw:{})
        monkeypatch.setattr(topology,'distributed_supply_contracts',lambda *a,**kw:{'contracts':{}})
    else:
        if fault=='incomplete':domain['complete']=False
        elif fault=='no_sources':domain['source_refs']=()
        elif fault=='no_sinks':domain['sink_refs']=()
        else:domain['amps']=.5
        monkeypatch.setattr(topology,'board_current_domains',lambda *a,**kw:{net:domain})
        monkeypatch.setattr(topology,'route_width_contracts',lambda *a,**kw:{net:contract})
    with pytest.raises(ValueError):
        rated._aggregate_repair_contracts(pcbnew.LoadBoard(str(source)),source,[net],'synthetic')


@pytest.mark.parametrize('value',[True,False,0,-1,float('nan'),float('inf'),10.01])
def test_constructor_deadline_is_finite_and_never_grants_edit_authority(tmp_path,monkeypatch,value):
    source,net,ids,domain,contract,xy=fixture(tmp_path,monkeypatch);board=pcbnew.LoadBoard(str(source))
    before=field._field_snapshot_inventory(board)
    with pytest.raises(ValueError):
        repair.construct(board,source,board_hint='synthetic',retired_track_uuids=ids,timeout_s=value)
    assert before==field._field_snapshot_inventory(board)


def test_phase_schema_cannot_silently_enable_aggregate_repair_or_accept_a_waiver(tmp_path,monkeypatch):
    source,net,ids,domain,contract,xy=fixture(tmp_path,monkeypatch);child,made=build(source,ids)
    row=dict(kind='rated_branch',candidate=child,retired_track_uuids=ids,**repair.PARAMETERS)
    for extra in ({'repair_aggregate_current_domain':1},{'repair_undersized_source':False},{'waive_current':True}):
        with pytest.raises(ValueError):chain._phases([dict(row,**extra)],child)
