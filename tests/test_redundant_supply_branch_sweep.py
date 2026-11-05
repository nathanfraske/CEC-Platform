"""Search proposes geometry; unchanged native/current receiving owns a cut."""
from pathlib import Path
from unittest import mock

import pcbnew
import pytest
import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_redundant_supply_branch_sweep as sweep
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, quarter=0, mirror=False, face=pcbnew.F_Cu, fault=None):
    net = '/UNFAMILIAR/POSITIVE-TEST-CATALOG'
    def pose(p):
        x, y = p
        if mirror:
            x = -x
        for _ in range(quarter):
            x, y = -y, x
        return (20+x, 20+y)
    b = _board([(*pose(p), net) for p in [(-8, 0), (8, 0)]], edge=(0, 0, 40, 40))
    for f in b.GetFootprints():
        for p in f.Pads():
            layers = pcbnew.LSET(); layers.AddLayer(face); p.SetLayerSet(layers)
    main = track(b, net, pose((-8, 0)), pose((8, 0)), layer=face, width=.2)
    path = [track(b, net, pose(a), pose(z), layer=face, width=.2) for a,z in
        [((-2, 0), (-2, 4)), ((-2, 4), (2, 4)), ((2, 4), (2, 0))]]
    for t in path:
        t.SetLocked(True)
    if fault == 'group':
        g = pcbnew.PCB_GROUP(b); b.Add(g); g.AddItem(path[1])
    elif fault == 'mask':
        path[1].SetHasSolderMask(True)
    elif fault == 'underwidth':
        for t in path:
            t.SetWidth(150000)
    elif fault == 'one_nm_gap':
        path[1].SetStart(path[1].GetStart()+pcbnew.VECTOR2I(1, 0))
    source = tmp_path/'source'/'board.kicad_pcb'; source.parent.mkdir()
    field._save_field_snapshot(b, source)
    catalog = dict(contracts={net:dict(net=net, role='all_terminal_conservative_aggregate',
        current_authority=dict(amps=.1, source='explicit_synthetic_test_catalog'),
        required_by_layer_mm={'F.Cu':.2,'B.Cu':.2}, routing_layers=['F.Cu','B.Cu'])})
    return source, {force._uid(t) for t in path}, force._uid(main), catalog


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', [False, True])
@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_discovery_owns_no_current_and_follows_the_whole_small_path(tmp_path, quarter, mirror, face):
    source, ids, main, catalog = fixture(tmp_path, quarter, mirror, face)
    before = source.read_bytes()
    with mock.patch.object(sweep.owner.rated.topology, 'distributed_supply_contracts', return_value=catalog):
        r = sweep.source_requests(pcbnew.LoadBoard(str(source)), source, board_hint='synthetic',
            allow_locked_source=True)
    assert len(r['requests']) == 1, r
    assert set(r['requests'][0]['source_track_uuids']) == ids
    assert main not in r['requests'][0]['source_track_uuids']
    assert not r['source_mutated'] and not r['deletion_or_current_authority_granted']
    assert source.read_bytes() == before


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', [False, True])
@pytest.mark.parametrize('face', [pcbnew.F_Cu, pcbnew.B_Cu])
def test_subpath_search_does_not_force_an_essential_maximal_continuation_into_every_cut(tmp_path,quarter,mirror,face):
    source,ids,main,catalog=fixture(tmp_path,quarter,mirror,face)
    original=source.read_bytes()
    with mock.patch.object(sweep.owner.rated.topology,'distributed_supply_contracts',return_value=catalog):
        r=sweep.source_requests(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',
            allow_locked_source=True,include_source_subpaths=True)
    scopes=[set(v['source_track_uuids']) for v in r['requests']]
    assert ids in scopes and any(len(v)==2 and v<ids for v in scopes)
    assert all(main not in v and len(v)<=8 for v in scopes)
    assert r['source_subpaths_included'] and not r['deletion_or_current_authority_granted']
    assert not r['source_subpath_window_bound_reached'] and source.read_bytes()==original


def test_subpath_seed_itself_must_fit_the_explicit_track_bound(tmp_path):
    source,ids,main,catalog=fixture(tmp_path)
    with mock.patch.object(sweep.owner.rated.topology,'distributed_supply_contracts',return_value=catalog):
        r=sweep.source_requests(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',
            allow_locked_source=True,include_source_subpaths=True,max_path_tracks=1)
    assert not r['requests']


def test_subpath_and_maximal_menus_share_one_global_source_window_bound(tmp_path):
    net='/UNFAMILIAR/POSITIVE-TEST-CATALOG';b=_board([],edge=(0,0,500,60));issues=[]
    for i in range(129):
        x=10+i*3
        pair=[track(b,net,(x,10),(x+1,10),width=.2),track(b,net,(x+1,10),(x+1,11),width=.2)]
        issues.append(dict(track_uuids=[force._uid(t) for t in pair]))
    source=tmp_path/'bounded-menu'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    catalog=dict(contracts={net:dict(net=net,role='all_terminal_conservative_aggregate',
        current_authority=dict(amps=.1,source='explicit_synthetic_test_catalog'),
        required_by_layer_mm={'F.Cu':.2,'B.Cu':.2},routing_layers=['F.Cu','B.Cu'])})
    with mock.patch.object(sweep.owner.rated.topology,'distributed_supply_contracts',return_value=catalog),\
            mock.patch.object(sweep.quality,'analyze_board',return_value=dict(issues=issues)):
        r=sweep.source_requests(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',
            include_source_subpaths=True,max_requests=32)
    assert len(r['requests'])+r['requests_outside_work_bound']==128
    assert r['source_subpath_window_bound_reached'] and not r['deletion_or_current_authority_granted']


@pytest.mark.parametrize('value',[None,1,'true'])
def test_subpath_mode_is_an_explicit_boolean_not_a_scope_waiver(tmp_path,value):
    source,ids,main,catalog=fixture(tmp_path)
    with pytest.raises(ValueError):
        sweep.source_requests(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',include_source_subpaths=value)


def covered_fixture(tmp_path,quarter=0,mirror=False,face=pcbnew.F_Cu,fault=None):
    net='/UNFAMILIAR/POSITIVE-TEST-CATALOG'
    def pose(p):
        x,y=p
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return (20+x,20+y)
    b=_board([],edge=(0,0,40,40))
    large=track(b,net,pose((-2,0)),pose((2,0)),layer=face,width=.2)
    small=track(b,net,pose((-2,0)),pose((0,0)),layer=face,width=.15 if fault=='underwidth' else .2)
    trigger=track(b,net,pose((-2,0)),pose((-2,-1)),layer=face,width=.2)
    if fault=='offset_cover':large.Move(pcbnew.VECTOR2I(1,1))
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('functional_owner');b.Add(g);g.AddItem(small)
    elif fault=='mask':small.SetHasSolderMask(True)
    elif fault=='lock':small.SetLocked(True)
    source=tmp_path/'covered-source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    child=force._copy_family(source,tmp_path/'covered-candidate');b=pcbnew.LoadBoard(str(source))
    ids={name:force._uid(t) for name,t in [('large',large),('small',small),('trigger',trigger)]}
    discard_items(b,[t for t in b.GetTracks() if force._uid(t)==ids['trigger']])
    if fault=='candidate_change':next(t for t in b.GetTracks() if force._uid(t)==ids['small']).Move(pcbnew.VECTOR2I(1,0))
    field._save_field_snapshot(b,child)
    catalog=dict(contracts={net:dict(net=net,role='all_terminal_conservative_aggregate',
        current_authority=dict(amps=.1,source='explicit_synthetic_test_catalog'),
        required_by_layer_mm={'F.Cu':.2,'B.Cu':.2},routing_layers=['F.Cu','B.Cu'])})
    return source,child,ids,catalog


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_newly_exposed_covered_backtrack_only_proposes_its_exact_redundant_source_capsule(tmp_path,quarter,mirror,face):
    source,child,ids,catalog=covered_fixture(tmp_path,quarter,mirror,face);original=source.read_bytes()
    with mock.patch.object(sweep.owner.rated.topology,'distributed_supply_contracts',return_value=catalog):
        scope=sweep.extend_causal_covered_scope(pcbnew.LoadBoard(str(source)),source,[ids['trigger']],child,
            board_hint='synthetic',allow_locked_source=True)
    assert set(scope)=={ids['trigger'],ids['small']} and ids['large'] not in scope
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['offset_cover','group','mask','lock','underwidth','candidate_change','no_catalog'])
def test_causal_covered_cleanup_never_weakens_exact_ownership_current_or_geometry(tmp_path,fault):
    source,child,ids,catalog=covered_fixture(tmp_path,fault=fault)
    if fault=='no_catalog':catalog['contracts']={}
    with mock.patch.object(sweep.owner.rated.topology,'distributed_supply_contracts',return_value=catalog):
        with pytest.raises(ValueError):
            sweep.extend_causal_covered_scope(pcbnew.LoadBoard(str(source)),source,[ids['trigger']],child,
                board_hint='synthetic',allow_locked_source=False)


@pytest.mark.parametrize('fault', ['group', 'mask', 'underwidth', 'no_catalog', 'no_amps', 'lock_policy'])
def test_discovery_never_invents_missing_process_current_or_lock_authority(tmp_path, fault):
    source, ids, _, catalog = fixture(tmp_path, fault=fault)
    b = pcbnew.LoadBoard(str(source)); before = source.read_bytes()
    if fault == 'no_catalog':
        catalog['contracts'] = {}
    elif fault == 'no_amps':
        next(iter(catalog['contracts'].values()))['current_authority'] = {}
    with mock.patch.object(sweep.owner.rated.topology, 'distributed_supply_contracts', return_value=catalog):
        r = sweep.source_requests(b, source, board_hint='synthetic', allow_locked_source=fault != 'lock_policy')
    assert all(set(q['source_track_uuids']) != ids for q in r['requests']), r
    assert source.read_bytes() == before


@pytest.mark.parametrize('value', [True, 0, 33, None])
def test_request_work_bound_is_literal_and_finite(tmp_path, value):
    source, _, _, catalog = fixture(tmp_path)
    with pytest.raises(ValueError, match='finite_explicit_supply_branch_search_required'):
        sweep.source_requests(pcbnew.LoadBoard(str(source)), source, board_hint='synthetic', max_requests=value)


def test_whole_path_is_not_truncated_to_fit_a_small_work_bound(tmp_path):
    source, ids, _, catalog = fixture(tmp_path)
    with mock.patch.object(sweep.owner.rated.topology, 'distributed_supply_contracts', return_value=catalog):
        r = sweep.source_requests(pcbnew.LoadBoard(str(source)), source, board_hint='synthetic',
            allow_locked_source=True, max_path_tracks=2)
    assert not r['requests'] and r['skipped'], r


def test_saved_full_load_cut_and_material_gain_are_independently_rederived(tmp_path):
    source, ids, _, catalog = fixture(tmp_path)
    child = force._copy_family(source, tmp_path/'candidate')
    b = pcbnew.LoadBoard(str(child)); discard_items(b, [t for t in b.GetTracks() if force._uid(t) in ids])
    additive._ground_refill(b); field._save_field_snapshot(b, child)
    with mock.patch.object(sweep.owner.rated.topology, 'distributed_supply_contracts', return_value=catalog):
        received = sweep.owner.receive(source, child, board_hint='synthetic', retired_track_uuids=sorted(ids),
            allow_locked_track_uuids=sorted(ids))
    assert received['ok'] and received['complete'], received
    assert received['unchanged_native_and_planar_full_load_graphs']
    actual = sweep.removed_material(pcbnew.LoadBoard(str(source)), pcbnew.LoadBoard(str(child)), sorted(ids))
    assert actual['positive_material_removed'] and actual['lower_bound_area_mm2'] > 2
    assert not actual['release_authority']


def test_unchanged_copper_cannot_be_claimed_as_physical_polish(tmp_path):
    source, ids, _, _ = fixture(tmp_path)
    actual = sweep.removed_material(pcbnew.LoadBoard(str(source)), pcbnew.LoadBoard(str(source)), sorted(ids))
    assert not actual['positive_material_removed'], actual


@pytest.mark.parametrize('void', ['drill', 'outside_substrate'])
def test_raw_lands_in_physical_voids_are_not_removed_copper(tmp_path, void):
    source, _, _, _ = fixture(tmp_path)
    b = pcbnew.LoadBoard(str(source))
    center = (31, 31) if void == 'drill' else (45, 45)
    cut = track(b, '/UNFAMILIAR/POSITIVE-TEST-CATALOG',
        (center[0]-.1, center[1]), (center[0]+.1, center[1]), width=.2)
    uid = force._uid(cut)
    if void == 'drill':
        fp = pcbnew.FOOTPRINT(b); b.Add(fp)
        p = pcbnew.PAD(fp); p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        p.SetDrillSize(pcbnew.VECTOR2I_MM(1, 1)); p.SetSize(pcbnew.VECTOR2I_MM(1, 1))
        p.SetLayerSet(pcbnew.LSET.AllCuMask()); fp.Add(p); p.SetPosition(pcbnew.VECTOR2I_MM(*center))
    field._save_field_snapshot(b, source)
    child = force._copy_family(source, tmp_path/'void-candidate')
    b = pcbnew.LoadBoard(str(child)); discard_items(b, [t for t in b.GetTracks() if force._uid(t) == uid])
    field._save_field_snapshot(b, child)
    r = sweep.removed_material(pcbnew.LoadBoard(str(source)), pcbnew.LoadBoard(str(child)), [uid])
    assert not r['positive_material_removed'], r
    assert r['actual_substrate_intersection_and_global_bores_subtracted']


def test_retained_narrow_copper_cannot_receive_removal_of_the_only_rated_path(tmp_path):
    source, ids, main, catalog = fixture(tmp_path)
    b = pcbnew.LoadBoard(str(source)); next(t for t in b.GetTracks() if force._uid(t) == main).SetWidth(100000)
    field._save_field_snapshot(b, source)
    child = force._copy_family(source, tmp_path/'candidate'); b = pcbnew.LoadBoard(str(child))
    discard_items(b, [t for t in b.GetTracks() if force._uid(t) in ids]); field._save_field_snapshot(b, child)
    with mock.patch.object(sweep.owner.rated.topology, 'distributed_supply_contracts', return_value=catalog):
        r = sweep.owner.receive(source, child, board_hint='synthetic', retired_track_uuids=sorted(ids),
            allow_locked_track_uuids=sorted(ids))
    assert not r['ok'] and r['errors'], r


@pytest.mark.parametrize('quarter', range(4))
def test_native_identified_tails_expand_only_a_finite_original_source_cut(tmp_path, quarter):
    source, ids, _, catalog = fixture(tmp_path, quarter=quarter)
    b = pcbnew.LoadBoard(str(source)); ordered = sorted(ids); before = source.read_bytes()
    faults = [dict(type='track_dangling', items=[dict(uuid=u)]) for u in ordered[1:]]
    with mock.patch.object(sweep.owner.rated.topology, 'distributed_supply_contracts', return_value=catalog):
        whole = sweep.extend_causal_tail_scope(b, source, [ordered[0]], faults,
            board_hint='synthetic', allow_locked_source=True)
    assert set(whole) == ids and source.read_bytes() == before


@pytest.mark.parametrize('fault', ['clearance', 'new_uuid', 'old_uuid', 'missing_items', 'lock_policy'])
def test_fault_feedback_is_not_permission_to_delete_arbitrary_copper(tmp_path, fault):
    source, ids, main, catalog = fixture(tmp_path)
    ordered = sorted(ids); issue = dict(type='track_dangling', items=[dict(uuid=ordered[1])])
    if fault == 'clearance':
        issue['type'] = 'clearance'
    elif fault == 'new_uuid':
        issue['items'] = [dict(uuid='not-an-original-source-track')]
    elif fault == 'old_uuid':
        issue['items'] = [dict(uuid=ordered[0])]
    elif fault == 'missing_items':
        issue['items'] = []
    with pytest.raises(ValueError):
        sweep.extend_causal_tail_scope(pcbnew.LoadBoard(str(source)), source, [ordered[0]], [issue],
            board_hint='synthetic', allow_locked_source=fault != 'lock_policy')


@pytest.mark.parametrize('lease', [True, 0, 30.01, float('inf'), float('nan')])
def test_larger_receiver_work_lease_is_explicit_bounded_and_not_a_waiver(tmp_path, lease):
    source, _, _, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match='finite_existing_supply_cut_receiving_lease_required'):
        sweep.run(source, tmp_path/'out', board_hint='synthetic', grade=tmp_path/'unused.json',
            expected_source_sha256=force._hash(source), reporting_build=tmp_path/'unused',
            cut_receive_timeout_s=lease)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_saved_shape_losers_skip_heavy_receiving_but_gain_no_acceptance(tmp_path,quarter,mirror,face):
    source,ids,main,catalog=fixture(tmp_path,quarter,mirror,face)
    b=pcbnew.LoadBoard(str(source));stem=next(t for t in b.GetTracks() if force._uid(t)==main)
    a,z=stem.GetStart(),stem.GetEnd();extra=stem.Duplicate();extra.m_Uuid.Clone(pcbnew.KIID())
    extra.SetStart(pcbnew.VECTOR2I((a.x+z.x)//2,(a.y+z.y)//2))
    extra.SetEnd(extra.GetStart()+pcbnew.VECTOR2I((z.x-a.x)//16,(z.y-a.y)//16));b.Add(extra)
    field._save_field_snapshot(b,source);original=source.read_bytes();cut=[force._uid(extra)]
    _check_refusal_order(tmp_path,source,cut,catalog,should_fund=False)
    assert source.read_bytes()==original


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_shape_improvement_never_bypasses_an_independent_current_refusal(tmp_path,quarter,mirror,face):
    source,ids,main,catalog=fixture(tmp_path,quarter,mirror,face)
    _check_refusal_order(tmp_path,source,sorted(ids),catalog,should_fund=True)


def _check_refusal_order(tmp_path,source,cut,catalog,*,should_fund):
    # A deliberately minimal mocked baseline only tests REJECTION ordering.
    # Neither branch is permitted to accept a candidate or skip native DRC
    # for any eventual winner.
    report=tmp_path/'rejection-only-baseline.json';force._write(report,dict(violations=[],unconnected_items=[]))
    producer=dict(ok=True,complete=True,native_inventory=dict(potentially_truncated=False),
        report=str(report),report_sha256=force._hash(report))
    grade=tmp_path/'rejection-only-grade.json';force._write(grade,dict(code_identity=force._code_identity(),
        boards=dict(candidate=dict(sha256=force._hash(source),native_producer=producer))))
    b=pcbnew.LoadBoard(str(source));live={force._uid(t):t for t in b.GetTracks()}
    menu=dict(requests=[dict(source_track_uuids=cut,allow_locked_track_uuids=[u for u in cut if live[u].IsLocked()])],
        source_bend_count=sweep.quality.analyze_board(b,min_open_angle_deg=134.999)['issue_count'])
    with mock.patch.object(sweep.owner.rated.topology,'distributed_supply_contracts',return_value=catalog),\
            mock.patch.object(sweep,'source_requests',return_value=menu),\
            mock.patch.object(sweep.owner,'receive',return_value=dict(ok=False,complete=False,errors=['independent_synthetic_refusal'])) as receiver,\
            mock.patch.object(sweep.native,'run',side_effect=AssertionError('a refused candidate cannot fund native acceptance')):
        got=sweep.run(source,tmp_path/'refused',board_hint='synthetic',grade=grade,
            expected_source_sha256=force._hash(source),reporting_build=tmp_path/'not-used',allow_locked_source=True)
    assert got['complete'] and not got['ok'] and not got['changed']
    assert receiver.call_count==int(should_fund)
    preflight=got['attempts'][0]['causal_tail_trials'][0]['saved_geometry_preflight']
    assert preflight['independent_current_receiving_run']==should_fund
    assert not preflight['acceptance_or_current_authority_granted']
    assert not got['attempts'][0]['accepted'] and not got['release_authority']
    return got
