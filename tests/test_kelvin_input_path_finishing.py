"""Native isolated-input geometry, never a synthetic hardware current rating."""
import copy,json
from pathlib import Path
import pcbnew
import pytest
import cec_kelvin_input_path_finishing as repair
import cec_force_current as force
import cec_force_sense_evidence as sense
import cec_field_coupling as field
import cec_zone_fill
from cec_native_items import discard_items
from test_kelvin_branch_repair import fixture

def case(tmp_path,monkeypatch,quarter=0,back=False):
    source=tmp_path/'source.kicad_pcb';row=fixture(source,renamed=True)
    b=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in b.GetTracks()}
    monitor=next(fp for fp in b.GetFootprints() if fp.GetReference()==row['input_ref'])
    monitor.SetValue('INA240A3DR');monitor.SetFPID(pcbnew.LIB_ID('Package_SO','SOIC-8_3.9x4.9mm_P1.27mm'))
    discard_items(b,[live[u] for u in row['removed']|{row['spine']}])
    net=next(p.GetNet() for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname()==row['net'])
    coords=[(20.,30.),(20.,28.2),(15.,28.2),(15.,27.)];old=[]
    for a,z in zip(coords,coords[1:]):
        t=pcbnew.PCB_TRACK(b);t.SetNet(net);t.SetLayer(pcbnew.F_Cu);t.SetWidth(250000);t.SetLocked(True)
        t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(t);old.append(t)
    target=next(p for fp in b.GetFootprints() for p in fp.Pads() if fp.GetReference()==row['input_ref'] and p.GetNumber()=='8')
    wanted=[(20.,30.),(20.,28.6),(19.6,28.2),(15.4,28.2),(15.,27.8),(15.,27.)]
    ghosts=[]
    for xy in wanted:
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(*xy));t.SetEnd(t.GetStart());ghosts.append(t)
    for item in [*b.GetFootprints(),*b.GetTracks(),*b.Zones(),*b.GetDrawings(),*ghosts]:
        if quarter:item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if back:item.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    cec_zone_fill.fill_with_report(b)
    field._save_field_snapshot(b,source);field._save_field_snapshot(pcbnew.LoadBoard(str(source)),source)
    monkeypatch.setattr(repair.topology,'board_current_domains',lambda *a,**k:copy.deepcopy(row['domains']))
    evidence=tmp_path/'typed-source.json';before=sense.replay(source,board_hint='opaque',timeout_s=20.)
    assert before['complete'],{k:before.get(k) for k in ('errors','stop','complete','loaded_board_identity_verified')}
    force._write(evidence,before)
    points=[list(t.GetStart()) for t in ghosts]
    if points[0]!=list(repair.chains._chain(old)[0]):points.reverse()
    return source,dict(board_hint='opaque',sense_evidence=evidence,input_pad_uuid=force._uid(target),
        retired_track_uuids=[force._uid(t) for t in old],points_nm=points,allow_locked_source=True),row

@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_rotated_opaque_parts_keep_force_copper_and_isolated_input_geometry(tmp_path,monkeypatch,quarter,back):
    source,args,row=case(tmp_path,monkeypatch,quarter,back);original=source.read_bytes()
    proposal=repair.plan(source,**args)
    assert proposal['width_nm']==250000 and proposal['native_input_island']['exact_integer_native_component_subtraction']
    assert not proposal['native_input_island']['numeric_healing_or_area_epsilon_used']
    assert proposal['source_length_nm']-proposal['candidate_length_nm']>400000
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(repair.construct(source,proposal),child)
    after=sense.replay(child,board_hint='opaque',timeout_s=20.)
    before=json.loads(Path(args['sense_evidence']).read_text())
    assert sense.admit_changed_net(before,after,row['net'])['ok']
    assert source.read_bytes()==original and force._sidecars(source)==force._sidecars(child)
    old=repair.additive._nodes(source)[1];new=repair.additive._nodes(child)[1]
    assert old.keys()-new.keys()==set(args['retired_track_uuids'])
    assert all(repair.syntax._freeze(n)==repair.syntax._freeze(new[u]) for u,n in old.items() if n[0]=='footprint')

@pytest.mark.parametrize('fault',['stale_source','unproved_isolation','bypass','inner_departure','lineage','epoch',
    'unknown_input','implicit_lock','raw_diagonal','moved_port','boolean_permission'])
def test_weak_or_forged_input_authority_never_grants_a_force_cut(tmp_path,monkeypatch,fault):
    source,args,row=case(tmp_path,monkeypatch)
    evidence=Path(args['sense_evidence']);report=json.loads(evidence.read_text())
    if fault=='stale_source':report['source_family_before'][str(source.resolve())]='0'*64
    elif fault=='unproved_isolation':report['clipped_isolation']['details'][0]['ok']=None
    elif fault=='bypass':report['clipped_isolation']['details'][0]['native']['physical_bypass_proved']=True
    elif fault=='inner_departure':report['inner_departure']['details'][0]['ok']=False
    elif fault=='lineage':report['lineage']['details'][0]['selected']['p']['anchor_net']='invented'
    elif fault=='epoch':report['code_before']={}
    elif fault=='unknown_input':args['input_pad_uuid']=str(pcbnew.KIID())
    elif fault=='implicit_lock':args['allow_locked_source']=False
    elif fault=='raw_diagonal':args['points_nm'][2][1]+=1
    elif fault=='moved_port':args['points_nm'][0][0]+=1
    elif fault=='boolean_permission':args['allow_locked_source']='yes'
    force._write(evidence,report)
    with pytest.raises((ValueError,KeyError)):repair.plan(source,**args)

@pytest.mark.parametrize('fault',['width','face','net','extra_copper','via','pose','source_land','rule','forged_plan'])
def test_saved_source_reconstruction_rejects_unowned_changes_before_full_receiving(tmp_path,monkeypatch,fault):
    source,args,row=case(tmp_path,monkeypatch);proposal=repair.plan(source,**args)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(repair.construct(source,proposal),child)
    b=pcbnew.LoadBoard(str(child));added=set(repair.additive._nodes(child)[1])-set(repair.additive._nodes(source)[1])
    t=next(t for t in b.GetTracks() if force._uid(t) in added)
    if fault=='width':t.SetWidth(t.GetWidth()-1)
    elif fault=='face':t.SetLayer(pcbnew.B_Cu)
    elif fault=='net':t.SetNet(next(p.GetNet() for fp in b.GetFootprints() for p in fp.Pads() if p.GetNetname()!=row['net']))
    elif fault=='extra_copper':q=t.Duplicate();q.m_Uuid.Clone(pcbnew.KIID());b.Add(q)
    elif fault=='via':
        q=pcbnew.PCB_VIA(b);q.SetNet(t.GetNet());q.SetWidth(600000);q.SetDrill(300000)
        q.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);q.SetViaType(pcbnew.VIATYPE_THROUGH);q.SetPosition(t.GetStart());b.Add(q)
    elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(1000,0))
    elif fault=='source_land':
        p=next(p for fp in b.GetFootprints() for p in fp.Pads() if force._uid(p)==proposal['source_pad_uuid']);p.SetSize(p.GetSize()+pcbnew.VECTOR2I(1,0))
    elif fault=='rule':child.with_suffix('.kicad_dru').write_text('(version 1)\n')
    elif fault=='forged_plan':proposal['source_length_nm']+=1
    try:field._save_field_snapshot(b,child)
    except ValueError as e:
        assert fault=='net' and str(e)=='native_field_snapshot_changed_saved_identity';return
    got=repair.receive(source,child,proposal,board_hint='opaque')
    assert not got['ok'] and got['errors']


def saved_case(tmp_path,monkeypatch):
    source,args,row=case(tmp_path,monkeypatch);plan=repair.plan(source,**args)
    child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(repair.construct(source,plan),child)
    before=json.loads(Path(args['sense_evidence']).read_text());after=sense.replay(child,board_hint='opaque',timeout_s=20.)
    boards=[pcbnew.LoadBoard(str(p)) for p in (source,child)]
    added=set(repair.additive._nodes(child)[1])-set(repair.additive._nodes(source)[1])
    return source,child,plan,before,after,boards,added


def test_complete_saved_native_input_replay_and_explicit_observation_ledger(tmp_path,monkeypatch):
    source,child,plan,before,after,boards,added=saved_case(tmp_path,monkeypatch)
    # The synthetic fixture has no hardware current design. Only this unit
    # test substitutes its unchanged-authority comparator; real-board runs
    # must use the actual independent current receiver unchanged.
    monkeypatch.setattr(repair.debt,'receive',lambda *a,**k:dict(ok=True,complete=True,
        synthetic_fixture_only=True,no_hardware_current_rating=True))
    got=repair.receive(source,child,plan,board_hint='opaque')
    assert got['ok'] and got['complete'],got['errors']
    assert got['whole_parent_clipped_preservation']['same_evidence']
    assert got['whole_parent_clipped_preservation']['comparison_complete']
    assert got['owned_departure_observation_ledger'] and got['fresh_source_and_candidate_clipped_net_admission']['ok']
    assert got['all_surviving_native_partitions_preserved'] and not got['current_or_barrel_qualified']


@pytest.mark.parametrize('fault',['source_exit','projection','direction','input_reach','source_identity',
    'row_identity','extra_departure','missing_bfs_target','bfs_endpoint','bfs_unknown_item','native_end','unowned_uuid'])
def test_departure_ledger_cannot_hide_changed_physical_requirements(tmp_path,monkeypatch,fault):
    source,child,plan,before,after,boards,added=saved_case(tmp_path,monkeypatch)
    selected=next(r for r in after['inner_departure']['details'] if r['sense_terminal']['uuid']==plan['input_pad_uuid'])
    contact=selected['native']['departures'][0]
    paths=contact['input_contact_paths'];target=next(iter(paths))
    if fault=='source_exit':contact['contact_exit_mm'][0]+=.000001
    elif fault=='projection':contact['inner_projection_mm']+=.000001
    elif fault=='direction':contact['inward_direction'][0]=1.
    elif fault=='input_reach':contact['reachable_input_pad_uuids'].append(str(pcbnew.KIID()))
    elif fault=='source_identity':selected['source_pad']['uuid']=str(pcbnew.KIID())
    elif fault=='row_identity':selected['input_ref']='another owner'
    elif fault=='extra_departure':selected['native']['departures'].append(copy.deepcopy(contact))
    elif fault=='missing_bfs_target':paths.clear()
    elif fault=='bfs_endpoint':paths[target][-1]=contact['uuid']
    elif fault=='bfs_unknown_item':paths[target].insert(1,str(pcbnew.KIID()))
    elif fault=='native_end':contact['departure_end_mm'][0]+=.000001
    elif fault=='unowned_uuid':contact['uuid']=str(pcbnew.KIID())
    with pytest.raises(ValueError):repair.receive_owned_departure_observations(before,after,plan,boards,added)


@pytest.mark.parametrize('complete',[False,True])
def test_real_current_refusal_or_unknown_remains_a_hard_gate(tmp_path,monkeypatch,complete):
    source,child,plan,before,after,boards,added=saved_case(tmp_path,monkeypatch)
    monkeypatch.setattr(repair.debt,'receive',lambda *a,**k:dict(ok=False,complete=complete))
    got=repair.receive(source,child,plan,board_hint='opaque')
    assert not got['ok'] and got['errors']==['ValueError:kelvin_input_whole_current_debt_regressed_or_unknown']
