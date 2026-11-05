"""Source-consumer geometry uses unchanged allocation/current receivers.

Explicit synthetic budgets are fixture inputs only; they are not hardware
power-budget changes. Native group proofs, contacts, snapshots and DRC run.
"""
import copy,json,os,runpy,time
from pathlib import Path
import pcbnew
import pytest
import cec_consumer_group_reconstruction as reconstruction
import cec_field_coupling as field
import cec_force_current as force
import cec_native_drc_runner as native
from test_pass_through_supply_branch import fixture
from test_field_proposals import track
from test_lastmile import _board

TOOL=Path(__file__).resolve().parents[1]/'ops/cec_consumer_corner_miter.py'
BUILD=Path(os.environ.get('CEC_NATIVE_DRC_TEST_BUILD','/home/codex/.cache/cec/native-drc-10.0.5'))


def case(tmp_path,monkeypatch,quarter=0,mirror=False,**options):
    b,root,anchor,owner,cap,tracks,trunk,group,row,domain,downstream=fixture(monkeypatch,tmp_path)
    source=Path(b.GetFileName());old=tracks[1];width=old.GetWidth()
    scope=reconstruction.plan(b,source,board_hint='synthetic',retired_track_uuids=[force._uid(old)])
    reconstruction.subtract(b,scope)
    points=[(8,8),(12,8),(12,15),(20,15),(25,10),(25,8)];new=[]
    for a,z in zip(points,points[1:]):
        t=pcbnew.PCB_TRACK(b);t.SetNet(root.GetNet());t.SetLayer(pcbnew.F_Cu);t.SetWidth(width);t.SetLocked(True)
        t.SetStart(pcbnew.VECTOR2I_MM(*a));t.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(t);new.append(t)
    reconstruction.assign(b,scope,[force._uid(t) for t in new],[])
    # The source fixture's unrelated output is closed too. Zero source opens
    # may not be faked by filtering the native baseline to the selected net.
    t=pcbnew.PCB_TRACK(b);t.SetNet(owner.FindPadByNumber('1').GetNet());t.SetLayer(pcbnew.F_Cu)
    t.SetWidth(200000);t.SetStart(owner.FindPadByNumber('1').GetPosition());t.SetEnd(owner.FindPadByNumber('8').GetPosition());b.Add(t)
    for a,z in [((-50,-50),(50,-50)),((50,-50),(50,50)),((50,50),(-50,50)),((-50,50),(-50,-50))]:
        e=pcbnew.PCB_SHAPE(b);e.SetShape(pcbnew.SHAPE_T_SEGMENT);e.SetLayer(pcbnew.Edge_Cuts)
        e.SetStart(pcbnew.VECTOR2I_MM(*a));e.SetEnd(pcbnew.VECTOR2I_MM(*z));b.Add(e)
    for item in [*b.GetFootprints(),*b.GetTracks()]:
        if quarter:item.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(quarter*90,pcbnew.DEGREES_T))
        if mirror:item.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    fault=options.get('fault')
    if fault=='unknown_group':group.SetName('UNRELATED_OWNER')
    elif fault=='wrong_package':owner.SetField('MPN','UNKNOWN_DEVICE')
    elif fault=='underwidth':
        for t in new:t.SetWidth(100000)
    elif fault=='masked':
        for t in [tracks[0],*new]:t.SetHasSolderMask(True)
    elif fault=='second_tap':
        t=pcbnew.PCB_TRACK(b);t.SetNet(root.GetNet());t.SetLayer(pcbnew.F_Cu);t.SetWidth(width)
        t.SetStart(cap.FindPadByNumber('1').GetPosition());t.SetEnd(trunk.GetEnd());b.Add(t);group.AddItem(t)
    elif fault=='lowered_allocation':row['amps']=3.
    elif fault=='inner_outer_width':
        for t in new:t.SetLayer(pcbnew.In2_Cu)
    field._save_field_snapshot(b,source)
    return source,b,row,domain,downstream


def run_tool(tmp_path,source,*,authorize=True,max_corners=8,digest=None):
    shadow=force._copy_family(source,tmp_path/'native-source');report=tmp_path/'source.drc.json'
    producer=native.run(shadow,report,reporting_build=BUILD,timeout_s=10.)
    assert producer['ok'] and producer['complete'] and not producer['native_inventory']['potentially_truncated']
    raw=json.loads(report.read_text());assert not raw['unconnected_items']
    grade=tmp_path/'baseline.json';force._write(grade,dict(code_identity=force._code_identity(),
        boards=dict(candidate=dict(sha256=force._hash(source),native_producer=producer))))
    function=runpy.run_path(str(TOOL))['run']
    return function(source,tmp_path/'work',board_hint='synthetic',expected_source_sha256=digest or force._hash(source),
        grade=grade,reporting_build=BUILD,allow_locked_source=authorize,max_corners=max_corners)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('max_corners',[1,8])
def test_native_consumer_group_corners_keep_exact_budget_tap_process_and_all_copper_contacts(tmp_path,monkeypatch,quarter,mirror,max_corners):
    source,b,row,domain,downstream=case(tmp_path,monkeypatch,quarter=quarter,mirror=mirror)
    original=source.read_bytes();budgets=copy.deepcopy((row,domain,downstream))
    r=run_tool(tmp_path,source,max_corners=max_corners)
    assert r['ok'] and r['complete'] and r['changed'],r
    proof=r['independent_source_consumer_receiving']
    assert proof['ok'] and proof['complete'] and not proof['errors']
    assert proof['all_original_surviving_partitions_preserved'] and proof['exact_native_ground_refill_replayed']
    assert proof['source_scope']['source_budget']['current_authority']['amps']==3.0004
    assert proof['source_scope']['source_budget']['aggregate_current_authority']['amps']==20.
    assert not proof['source_current_reduced'] and not proof['branch_sharing_assumed']
    assert r['actual_length_removed_mm']>0 and r['corners']<=max_corners
    assert not r['attempts'][-1]['new_native_faults'] and r['attempts'][-1]['opens']==0
    assert r['source_family_and_code_unchanged'] and not r['fab_ready'] and not r['release_authority']
    assert source.read_bytes()==original and (row,domain,downstream)==budgets
    assert r['input_sha256'][str(TOOL)]==force._hash(TOOL)


@pytest.mark.parametrize('fault',['unknown_group','wrong_package','underwidth','masked','second_tap','lowered_allocation','inner_outer_width'])
def test_unqualified_group_current_or_process_cannot_be_treated_as_an_ordinary_corner(tmp_path,monkeypatch,fault):
    source,*_=case(tmp_path,monkeypatch,fault=fault)
    b=pcbnew.LoadBoard(str(source));original=source.read_bytes()
    api=runpy.run_path(str(TOOL));r=api['inventory'](b,source,board_hint='synthetic',allow_locked_source=True)
    assert not r['batches'] and r['refusals'],r
    assert source.read_bytes()==original


def test_locked_source_needs_explicit_authorization(tmp_path,monkeypatch):
    source,b,*_=case(tmp_path,monkeypatch)
    api=runpy.run_path(str(TOOL));r=api['inventory'](b,source,board_hint='synthetic')
    assert not r['batches'] and r['refusals']


@pytest.mark.parametrize('options',[dict(max_corners=0),dict(max_corners=9),dict(max_corners=True),
    dict(minimum_flat_nm=19999),dict(minimum_flat_nm=True),dict(allow_locked_source='yes')])
def test_no_unbounded_work_or_invisible_micro_miter_policy(tmp_path,monkeypatch,options):
    source,b,*_=case(tmp_path,monkeypatch)
    api=runpy.run_path(str(TOOL))
    with pytest.raises(ValueError):api['inventory'](b,source,board_hint='synthetic',**options)


def test_wrong_literal_source_hash_is_refused_before_output(tmp_path,monkeypatch):
    source,b,*_=case(tmp_path,monkeypatch)
    api=runpy.run_path(str(TOOL));original=source.read_bytes()
    with pytest.raises(ValueError,match='source_hash'):
        api['run'](source,tmp_path/'out',board_hint='synthetic',expected_source_sha256='0'*64,
            grade=tmp_path/'not-read.json',reporting_build=BUILD,allow_locked_source=True)
    assert not (tmp_path/'out').exists() and source.read_bytes()==original


def test_exact_native_contact_containment_does_not_need_radius_binary_search(monkeypatch):
    b=_board([],edge=(-2,-2,12,12));b.Add(pcbnew.NETINFO_ITEM(b,'CONTACT'))
    body=track(b,'CONTACT',(1,0),(3,0),width=.2)
    old=[track(b,'CONTACT',(3,0),(8,0),width=.2),track(b,'CONTACT',(8,0),(8,5),width=.2)]
    new=[track(b,'CONTACT',(3,0),(6,0),width=.2),track(b,'CONTACT',(6,0),(8,2),width=.2),
        track(b,'CONTACT',(8,2),(8,5),width=.2)]
    api=runpy.run_path(str(TOOL))
    def forbidden(*a,**k):raise AssertionError('Exact containment must not recompute an inscribed radius')
    monkeypatch.setattr(api['contacts'],'native_contact_radius',forbidden)
    proof=api['retained_contact_proof'](body,old,new,pcbnew.F_Cu,200000,time.monotonic()+10.)
    assert proof['method']=='exact_full_native_contact_containment'
    assert proof['every_old_native_contact_point_retained'] and proof['maximum_inscribed_radius_cannot_decrease']
    assert proof['positive_native_contact_radius_lower_bound_nm']==proof['polygon_error_nm']==1
    assert not proof['current_or_barrel_capacity_qualified']


@pytest.mark.parametrize('empty',[False,True])
def test_missing_or_empty_source_contact_keeps_the_existing_positive_radius_guard(monkeypatch,empty):
    b=_board([],edge=(-2,-2,12,12));b.Add(pcbnew.NETINFO_ITEM(b,'CONTACT'))
    body=track(b,'CONTACT',(1,0),(3,0),width=.2)
    old=[track(b,'CONTACT',(3,0),(8,0),width=.2)] if not empty else []
    new=[track(b,'CONTACT',(3.5,0),(8,0),width=.2)]
    api=runpy.run_path(str(TOOL));calls=[]
    def radius(*args):
        calls.append(args)
        return 100000 if len(calls)==1 and not empty else 0
    monkeypatch.setattr(api['contacts'],'native_contact_radius',radius)
    with pytest.raises(ValueError,match='contact_web_would_shrink'):
        api['retained_contact_proof'](body,old,new,pcbnew.F_Cu,200000,time.monotonic()+10.)
    assert len(calls)==2
