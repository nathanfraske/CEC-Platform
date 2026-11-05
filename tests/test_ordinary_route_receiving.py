"""Exact signal replacement scope and independent boundary/pad restoration."""
import math
import time
from pathlib import Path
from unittest import mock

import pcbnew
import pytest

import cec_additive_route_receiving as additive
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_ordinary_route_receiving as receiving
import cec_received_route_evidence as evidence
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def _ground_fill_regression_fixture(tmp_path,split):
    import cec_native_fill_geometry as fill
    source,child,uid,net=fixture(tmp_path)
    zone_uid='00000000-0000-4000-8000-000000000001'
    solid=[[[[3000000,20000000],[17000000,20000000],
        [17000000,24000000],[3000000,24000000]]]]
    pieces=[[[[3000000,20000000],[9000000,20000000],[9000000,24000000],[3000000,24000000]]],
        [[[11000000,20000000],[17000000,20000000],[17000000,24000000],[11000000,24000000]]]]
    for path in(source,child):
        b=pcbnew.LoadBoard(str(path));b.Add(pcbnew.NETINFO_ITEM(b,'GND'))
        z=pcbnew.ZONE(b);z.SetLayer(pcbnew.F_Cu);z.SetNet(b.FindNet('GND'))
        z.m_Uuid.Clone(pcbnew.KIID(zone_uid));z.Outline().Append(fill.reconstruct(solid,time.monotonic()+2))
        z.SetFilledPolysList(pcbnew.F_Cu,fill.reconstruct(pieces if split and path==child else solid,time.monotonic()+2))
        z.SetIsFilled(True);b.Add(z)
        for n,x in enumerate([5,15]):
            t=track(b,'GND',(x,22),(x+.5,22));t.m_Uuid.Clone(pcbnew.KIID(
                '11111111-1111-4111-8111-'+str(n+1).zfill(12)))
        field._save_field_snapshot(b,path)
    return source,child,uid


def test_actual_receiver_refuses_zone_island_split_before_delta_replay(tmp_path):
    source,child,uid=_ground_fill_regression_fixture(tmp_path,True)
    before=[p.read_bytes()for p in(source,child)]
    r=receiving.receive(source,child,retired_track_uuids=[uid],board_hint='synthetic')
    assert not r['ok'] and any('prior_native_terminal_partition_lost'in e for e in r['errors']),r
    assert r['paired_native_partition_preservation']['demoted_component_count']==1
    assert before==[p.read_bytes()for p in(source,child)]


def test_standalone_partition_distinguishes_islands_and_refuses_changed_fill_keys(tmp_path):
    source,child,uid=_ground_fill_regression_fixture(tmp_path,True)
    first=receiving._partition(pcbnew.LoadBoard(str(source)),time.monotonic()+5)
    last=receiving._partition(pcbnew.LoadBoard(str(child)),time.monotonic()+5)
    ground_keys={('copper','11111111-1111-4111-8111-'+str(n).zfill(12))for n in (1,2)}
    assert any(ground_keys<=part for part in first)
    assert not any(ground_keys<=part for part in last)
    # Exact-fill keys cannot silently be rebound to either descendant.
    # A changed fill requires the paired native overlap-token receiver.
    with pytest.raises(ValueError,match='surviving_source_conductor_missing'):
        receiving._partition(pcbnew.LoadBoard(str(child)),time.monotonic()+5,
            retained_keys=set().union(*first))


def test_actual_receiver_reproves_new_barrel_ground_antipad_hash(tmp_path):
    from test_field_refill_proposals import ground_fixture
    from test_additive_route_receiving import barrel
    import cec_native_fill_geometry as fill
    source,b=ground_fixture(tmp_path)
    old=next(t for t in b.GetTracks()if t.GetNetname()=='/CONTROL')
    uid=force._uid(old);field._save_field_snapshot(b,source)
    candidate=force._copy_family(source,tmp_path/'ordinary-antipad')
    c=pcbnew.LoadBoard(str(candidate));discard_items(c,[t for t in c.GetTracks()if force._uid(t)==uid])
    for a,z in [((25,16),(25,17)),((25,17),(25.1,17)),((25.1,17),(25.1,16)),
                ((22,14),(24,16)),((24,16),(25,16))]:track(c,'/CONTROL',a,z)
    barrel(c,(22,14));field._save_field_snapshot(c,candidate)
    final=Path(additive.finalize_private(source,candidate,tmp_path/'ordinary-antipad-final')['board'])
    a=pcbnew.LoadBoard(str(source));c=pcbnew.LoadBoard(str(final))
    def hashes(board):return [fill.identity(z.GetFilledPolysList(face),time.monotonic()+2)[0]
        for z in board.Zones()for face in z.GetLayerSet().CuStack()if z.GetNetname()=='GND']
    assert hashes(a)!=hashes(c)
    r=receiving.receive(source,final,retired_track_uuids=[uid],board_hint='synthetic')
    assert r['ok'] and r['complete'],r
    assert r['paired_native_partition_preservation']['preserved']
    assert r['exact_subtract_add_ground_rule_replay']['ok']


def fixture(tmp_path, rotation=0, prefix='/renamed/', *, locked=False, width=.2):
    net=prefix+'CONTROL'
    def rotate(p):
        a=math.radians(rotation);x,y=p[0]-15,p[1]-15
        return round(15+x*math.cos(a)-y*math.sin(a),6),round(15+x*math.sin(a)+y*math.cos(a),6)
    b=_board([(*rotate((5,10)),net),(*rotate((15,10)),net),(*rotate((20,10)),net)],edge=(0,0,30,30))
    old=track(b,net,rotate((5,10)),rotate((15,10)),width=width);old.SetLocked(locked)
    for fp in b.GetFootprints():list(fp.Pads())[0].SetPadName('1')
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source)
    candidate=force._copy_family(source,tmp_path/'candidate')
    c=pcbnew.LoadBoard(str(candidate));retired=next(t for t in c.GetTracks() if force._uid(t)==force._uid(old))
    discard_items(c,[retired])
    for a,z in (((5,10),(5,11)),((5,11),(15,11)),((15,11),(15,10)),((15,10),(20,10))):
        track(c,net,rotate(a),rotate(z),width=width)
    field._save_field_snapshot(c,candidate)
    final=Path(additive.finalize_private(source,candidate,tmp_path/'final')['board'])
    return source,final,force._uid(old),net


@pytest.mark.parametrize('rotation,prefix',[(0,'/a/'),(90,'/renamed/x/'),(180,'/z/'),(270,'/another/')])
def test_renamed_rotated_replacement_is_received_without_touching_inputs(tmp_path,rotation,prefix):
    source,child,uid,net=fixture(tmp_path,rotation,prefix)
    before=[p.read_bytes() for p in (source,child)]
    proof=receiving.receive(source,child,retired_track_uuids=[uid],board_hint='synthetic')
    assert proof['ok'] and proof['complete'],proof
    assert proof['boundary_restoration'][0]['net']==net
    assert proof['all_prior_native_terminal_partitions_preserved'] is True
    assert proof['release_authority'] is False and proof['power_authority'] is False
    assert [p.read_bytes() for p in (source,child)]==before
    assert not additive.receive(source,child)['ok']


@pytest.mark.parametrize('mode',['wrong_scope','duplicate_scope','missing_scope','locked','group','narrow','endpoint','partition','pose','power_addition','budget'])
def test_incomplete_or_unrelated_change_is_never_a_replacement_receipt(tmp_path,mode):
    source,child,uid,net=fixture(tmp_path,locked=mode=='locked')
    ids=[uid]
    if mode=='wrong_scope':ids=['not-the-retired-native-uuid']
    elif mode=='duplicate_scope':ids=[uid,uid]
    elif mode=='missing_scope':ids=[]
    elif mode=='group':
        b=pcbnew.LoadBoard(str(source));g=pcbnew.PCB_GROUP(b);g.SetName('OWNED')
        b.Add(g);g.AddItem(next(t for t in b.GetTracks() if force._uid(t)==uid));field._save_field_snapshot(b,source)
    elif mode in ('narrow','endpoint','partition','pose','power_addition'):
        b=pcbnew.LoadBoard(str(child))
        if mode=='narrow':
            for t in b.GetTracks():t.SetWidth(pcbnew.FromMM(.1))
        elif mode=='endpoint':
            first=next(t for t in b.GetTracks() if tuple(t.GetStart())==(5000000,10000000))
            first.SetStart(pcbnew.VECTOR2I_MM(5,10.5))
        elif mode=='partition':
            removed=[t for t in b.GetTracks() if tuple(t.GetStart())==(5000000,11000000)]
            discard_items(b,removed)
        elif mode=='pose':
            next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(0,.1))
        else:track(b,'+5V',(22,22),(24,22))
        field._save_field_snapshot(b,child)
    result=receiving.receive(source,child,retired_track_uuids=ids,board_hint='synthetic',timeout_s=0 if mode=='budget' else 10)
    assert result['ok'] is False and result['complete'] is False,result
    assert result['errors']


def test_exact_locked_permission_does_not_change_electrical_type(tmp_path):
    source,child,uid,_net=fixture(tmp_path,locked=True)
    result=receiving.receive(source,child,retired_track_uuids=[uid],
        allow_locked_track_uuids=[uid],board_hint='synthetic')
    assert result['ok'] and result['locked_scope_used']==[uid],result


@pytest.mark.parametrize('net',['+5V','GND','/nested/ATX_NEG12V','/USB_D_P','/USB_D_N','/SENSEC1_HI','/CLOCK'])
def test_specialized_owned_copper_cannot_be_retired_as_ordinary(tmp_path,net):
    source,child,uid,original=fixture(tmp_path)
    for path in (source,child):
        b=pcbnew.LoadBoard(str(path));b.Add(pcbnew.NETINFO_ITEM(b,net));code=b.GetNetcodeFromNetname(net)
        for t in b.GetTracks():t.SetNetCode(code)
        for fp in b.GetFootprints():
            for p in fp.Pads():p.SetNetCode(code)
        field._save_field_snapshot(b,path)
    result=receiving.receive(source,child,retired_track_uuids=[uid],board_hint='synthetic')
    assert not result['ok'] and 'ordinary' in result['errors'][0],result


def test_removed_internal_junction_is_not_hidden_by_equal_pad_partitions(tmp_path):
    source,child,uid,net=fixture(tmp_path)
    # The source segment ends in a copper-only middle junction, not a pad.
    b=pcbnew.LoadBoard(str(source));extra=track(b,net,(10,10),(10,8));field._save_field_snapshot(b,source)
    c=pcbnew.LoadBoard(str(child));same=extra.Duplicate();same.m_Uuid.Clone(extra.m_Uuid);c.Add(same)
    field._save_field_snapshot(c,child)
    # Detour preserves pads 1/2/3 but abandons the source branch at x=10.
    result=receiving.receive(source,child,retired_track_uuids=[uid],board_hint='synthetic')
    assert not result['ok'] and 'prior_native_terminal_partition_lost' in result['errors'][0],result


def test_internal_corners_can_disappear_but_external_boundaries_cannot(tmp_path):
    source,child,uid,net=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));old=next(iter(b.GetTracks()));discard_items(b,[old])
    edges=[track(b,net,a,z) for a,z in (((5,10),(5,9)),((5,9),(15,9)),((15,9),(15,10)))]
    field._save_field_snapshot(b,source)
    result=receiving.receive(source,child,retired_track_uuids=[force._uid(t) for t in edges],board_hint='synthetic')
    assert result['ok'] and result['boundary_restoration'][0]['external_boundary_count']==2,result


@pytest.mark.parametrize('klass',['Power','GND','Sense','Kelvin','CAN','USB','Differential','Clock','RF','HighSpeed'])
def test_neutrally_named_specialized_class_is_not_ordinary(tmp_path,klass):
    source,child,uid,_net=fixture(tmp_path)
    with mock.patch.object(fr,'_project_netclass_resolver',return_value=lambda n:dict(name=klass,track_width=.2)):
        result=receiving.receive(source,child,retired_track_uuids=[uid],board_hint='synthetic')
    assert not result['ok'] and 'ordinary' in result['errors'][0],result


@pytest.mark.parametrize('pin_type',['power_in','power_out'])
def test_native_supply_pin_on_a_neutral_name_is_not_an_ordinary_leaf(tmp_path,pin_type):
    source,child,uid,_net=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));list(next(iter(b.GetFootprints())).Pads())[0].SetPinType(pin_type)
    field._save_field_snapshot(b,source)
    result=receiving.receive(source,child,retired_track_uuids=[uid],board_hint='synthetic')
    assert not result['ok'] and 'ordinary' in result['errors'][0],result


@pytest.mark.parametrize('mutation',['outline','surviving_track','project','rule'])
def test_no_exact_scoped_permission_for_unrelated_native_or_sidecar_changes(tmp_path,mutation):
    source,child,uid,net=fixture(tmp_path)
    if mutation in ('project','rule'):
        child.with_suffix('.kicad_pro' if mutation=='project' else '.kicad_dru').write_text('unqualified')
    else:
        b=pcbnew.LoadBoard(str(child))
        if mutation=='outline':next(iter(b.GetDrawings())).Move(pcbnew.VECTOR2I_MM(.01,0))
        else:
            # Introduce the same unrelated source edge in both files, then
            # alter its saved received width outside the retirement scope.
            parent=pcbnew.LoadBoard(str(source));item=track(parent,net,(22,22),(24,22))
            field._save_field_snapshot(parent,source)
            copied=item.Duplicate();copied.m_Uuid.Clone(item.m_Uuid);copied.SetWidth(pcbnew.FromMM(.3));b.Add(copied)
        field._save_field_snapshot(b,child)
    result=receiving.receive(source,child,retired_track_uuids=[uid],board_hint='synthetic')
    assert not result['ok'] and result['errors'],result


def bound_reports(source,child):
    def report(path):
        # This fixture has ordinary control pads, not measurement inputs.
        # Inventory dispatch still requires BOTH complete raw inventories.
        # Use the real read-only producer rather than omitting clipped cuts
        # and relying on a comparator mock to bypass the mandatory input.
        import cec_pair_semantics as semantics
        assert not semantics.analog_input_pairs(pcbnew.LoadBoard(str(path)))
        observed=evidence.sense.replay(path,board_hint='synthetic',timeout_s=10.)
        assert observed['identity_stable']
        assert observed['clipped_isolation']['expected']==0
        assert observed['clipped_isolation']['unresolved_inputs']==0
        return observed
    return report(source),report(child)


def test_typed_evidence_manifest_is_derived_from_received_native_retirements(tmp_path):
    source,child,uid,net=fixture(tmp_path)
    before,after=bound_reports(source,child)
    with mock.patch.object(evidence.sense,'compare_contour_preservation',
             return_value=dict(comparison_complete=True,same_evidence=True)) as typed:
        result=evidence.compare(source,child,before,after,retired_ordinary_track_uuids=[uid])
    assert result['ok'] and result['complete'] and result['source_delta']['ok'],result
    transforms=typed.call_args.kwargs['native_copper_transforms']
    assert len(transforms)==1 and transforms[0]['net']==net
    assert transforms[0]['retired_track_uuids']==[uid]
    assert len(transforms[0]['added_track_uuids'])==4
    assert result['full_kelvin_qualification'] is False and result['release_authority'] is False


@pytest.mark.parametrize('mutation',['stale_family','missing_retirement','wrong_retirement','typed_refusal'])
def test_typed_replacement_route_evidence_fails_closed(tmp_path,mutation):
    source,child,uid,net=fixture(tmp_path);before,after=bound_reports(source,child)
    ids=[uid]
    if mutation=='stale_family':before['source_family_before']={}
    elif mutation=='missing_retirement':ids=[]
    elif mutation=='wrong_retirement':ids=['other-native-item']
    with mock.patch.object(evidence.sense,'compare_contour_preservation',
        return_value=dict(comparison_complete=True,same_evidence=False)):
        result=evidence.compare(source,child,before,after,retired_ordinary_track_uuids=ids)
    assert result['ok'] is False and result['release_authority'] is False,result


@pytest.mark.parametrize('parallel',[False,True])
def test_replacement_field_uses_real_parent_and_every_native_interaction(tmp_path,parallel):
    source,child,uid,net=fixture(tmp_path,prefix='/PWM_')
    if parallel:
        for path in (source,child):
            b=pcbnew.LoadBoard(str(path));new=track(b,'/ADC_INPUT',(5,11.8),(15,11.8))
            # The SAME source victim, not unrelated UUIDs on each board.
            if path==source:victim=force._uid(new)
            else:new.m_Uuid.Clone(pcbnew.KIID(victim))
            field._save_field_snapshot(b,path)
    before=[p.read_bytes() for p in (source,child)]
    result=field.assess_native_ordinary_replacement(source,child,
        retired_track_uuids=[uid],board_hint='synthetic')
    assert result['complete'] and result['ok'] is (not parallel),result
    assert result['prior_blocking_count']==0
    assert bool(result['new_blockers']) is parallel
    assert result['board_mutated'] is False and result['inherited_debt_qualified'] is False
    assert [p.read_bytes() for p in (source,child)]==before


def test_replacement_field_unknown_scope_or_timeout_never_passes(tmp_path):
    source,child,uid,net=fixture(tmp_path)
    invalid=field.assess_native_ordinary_replacement(source,child,
        retired_track_uuids=['wrong-native-edge'],board_hint='synthetic')
    assert invalid['ok'] is None and not invalid['complete']
    assert invalid['reason']=='native_ordinary_replacement_receiving_refused'
    expired=field.assess_native_ordinary_replacement(source,child,
        retired_track_uuids=[uid],board_hint='synthetic',timeout_s=0)
    assert expired['ok'] is None and not expired['complete']
