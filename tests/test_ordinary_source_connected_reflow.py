"""Native saved connected Source chains and exact isolated phase dispatch."""
import json,shutil,copy,time
from pathlib import Path
import pcbnew
import pytest
import cec_ordinary_source_connected_reflow as op
import cec_force_current as force
import cec_field_coupling as field
import cec_ordinary_route_receiving as ordinary
from cec_native_items import discard_items
from test_ordinary_route_receiving import fixture as old_fixture
import root_connected_ordinary_phase_20261027 as adapter

def fixture(tmp_path,n=9,rotation=0,back=False,locked=True):
    source,child,uid,net=old_fixture(tmp_path,rotation=rotation,prefix='/arbitrary/cohort/',locked=locked)
    b=pcbnew.LoadBoard(str(source));old=next(t for t in b.GetTracks()if force._uid(t)==uid)
    a,z=tuple(old.GetStart()),tuple(old.GetEnd());face=pcbnew.B_Cu if back else pcbnew.F_Cu
    discard_items(b,[old]);ids=[]
    for i in range(n):
        t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I(*(a[k]+round((z[k]-a[k])*i/n)for k in(0,1))))
        t.SetEnd(pcbnew.VECTOR2I(*(a[k]+round((z[k]-a[k])*(i+1)/n)for k in(0,1))))
        t.SetWidth(200000);t.SetLayer(face);t.SetNetCode(b.GetNetcodeFromNetname(net));t.SetLocked(locked);b.Add(t);ids.append(force._uid(t))
    c=pcbnew.LoadBoard(str(child))
    if back:
        for board in(b,c):
            for fp in board.GetFootprints():fp.Flip(fp.GetPosition(),False)
        for t in c.GetTracks():t.SetLayer(face)
    field._save_field_snapshot(b,source);field._save_field_snapshot(c,child)
    project=dict(net_settings=dict(classes=[dict(name='Default',track_width=.2,clearance=.2,
        via_diameter=.6,via_drill=.3)],netclass_assignments={}))
    for path in(source,child):path.with_suffix('.kicad_pro').write_text(json.dumps(project))
    return source,child,net,ids,ids[:]if locked else[]

def receive(data):
    source,child,net,cuts,locks=data
    return op.receive(source,child,board_hint='synthetic',net=net,retired_track_uuids=cuts,
        allow_locked_track_uuids=locks,timeout_s=10.)

@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_actual_saved_nine_track_chain_all_boundaries_partitions_and_nonmutation(tmp_path,rotation,back):
    data=fixture(tmp_path,rotation=rotation,back=back);before=[p.read_bytes()for p in data[:2]]
    r=receive(data)
    assert r['ok']and r['complete'],r
    assert r['source_plan']['maximum_source_tracks']==16
    assert r['source_plan']['maximum_incoming_tracks']==64
    assert r['independent_ordinary_receiving']['max_retired_tracks']==16
    assert r['all_original_native_boundaries_and_partitions_received']
    assert not r['power_authority']and not r['barrel_authority']and not r['release_authority']
    assert before==[p.read_bytes()for p in data[:2]]

def test_actual_saved_sixteen_source_strokes_pass(tmp_path):
    assert receive(fixture(tmp_path,n=16))['ok']

@pytest.mark.parametrize('fault',['17','empty','duplicate','missing','locks_missing','locks_extra','unlocked_extra',
    'disconnected','cycle','branch','group','width','face','crossing'])
def test_source_scope_is_fresh_exact_connected_and_nonbranching(tmp_path,fault):
    data=fixture(tmp_path,n=17 if fault=='17' else 9,locked=fault!='unlocked_extra')
    source,child,net,cuts,locks=data;b=pcbnew.LoadBoard(str(source));tracks={force._uid(t):t for t in b.GetTracks()}
    if fault=='empty':cuts=[];locks=[]
    elif fault=='duplicate':cuts=cuts+[cuts[0]]
    elif fault=='missing':cuts=cuts+['missing'];locks=locks+['missing']
    elif fault=='locks_missing':locks=locks[1:]
    elif fault=='locks_extra':locks=locks+['outside']
    elif fault=='unlocked_extra':locks=cuts[:1]
    elif fault=='disconnected':tracks[cuts[4]].Move(pcbnew.VECTOR2I(0,1000000))
    elif fault=='cycle':tracks[cuts[-1]].SetEnd(tracks[cuts[0]].GetStart())
    elif fault=='branch':
        t=pcbnew.PCB_TRACK(b);t.SetStart(tracks[cuts[3]].GetEnd());t.SetEnd(t.GetStart()+pcbnew.VECTOR2I(0,1000000))
        t.SetNetCode(b.GetNetcodeFromNetname(net));t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);t.SetLocked(True);b.Add(t)
        cuts=cuts+[force._uid(t)];locks=locks+[force._uid(t)]
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);g.SetName('actual-retained-map');b.Add(g);g.AddItem(tracks[cuts[0]])
    elif fault=='width':tracks[cuts[3]].SetWidth(190000)
    elif fault=='face':tracks[cuts[3]].SetLayer(pcbnew.B_Cu)
    elif fault=='crossing':
        # Exact integer crossing predicate is not a fuzzy endpoint alias.
        assert op._intersects((0,0),(2,2),(0,2),(2,0))
        tracks[cuts[3]].SetEnd(tracks[cuts[0]].GetStart())
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):
        op.plan(pcbnew.LoadBoard(str(source)),source,board_hint='synthetic',net=net,
            retired_track_uuids=cuts,allow_locked_track_uuids=locks)

@pytest.mark.parametrize('net',['GND','+5V','/USB_D_P','/USB_D_N','/SENSEC1_HI','/CLOCK'])
def test_locks_cannot_ordinary_classify_specialized_domains(tmp_path,net):
    source,child,_,cuts,locks=fixture(tmp_path)
    b=pcbnew.LoadBoard(str(source));b.Add(pcbnew.NETINFO_ITEM(b,net));code=b.GetNetcodeFromNetname(net)
    for t in b.GetTracks():t.SetNetCode(code)
    for fp in b.GetFootprints():
        for p in fp.Pads():p.SetNetCode(code)
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.plan(b,source,board_hint='synthetic',net=net,
        retired_track_uuids=cuts,allow_locked_track_uuids=locks)

@pytest.mark.parametrize('fault',['thin','wide','foreign_net','extra64','pose','partition','endpoint','new_group'])
def test_saved_damage_or_scope_expansion_is_not_received(tmp_path,fault):
    source,child,net,cuts,locks=fixture(tmp_path);b=pcbnew.LoadBoard(str(child));rows=list(b.GetTracks())
    original_pair=None
    if fault in('partition','endpoint'):
        parent=pcbnew.LoadBoard(str(source))
        tracks={force._uid(t):t for t in parent.GetTracks()}
        first=tuple(tracks[cuts[0]].GetStart())
        last=tuple(tracks[cuts[-1]].GetEnd())
        pads=[p for fp in parent.GetFootprints()for p in fp.Pads()]
        selected=[p for point in(first,last)for p in pads if tuple(p.GetPosition())==point]
        assert len(selected)==2
        original_pair={force._item_key(p)for p in selected}
        assert any(original_pair<=part for part in ordinary._partition(parent,time.monotonic()+10))
        assert any(original_pair<=part for part in ordinary._partition(b,time.monotonic()+10))
        # Native iteration order follows UUIDs, not creation order. Select
        # the actual original first boundary, never the newly added spur
        # towards the third pad that Source intentionally left isolated.
        incident=[t for t in rows if first in(tuple(t.GetStart()),tuple(t.GetEnd()))]
        assert len(incident)==1
        damaged=incident[0]
    if fault=='thin':rows[0].SetWidth(190000)
    elif fault=='wide':rows[0].SetWidth(210000)
    elif fault=='foreign_net':
        rows[0].SetNetCode(0)
    elif fault=='extra64':
        for i in range(65):
            t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(23,20+i*.05));t.SetEnd(pcbnew.VECTOR2I_MM(24,20+i*.05))
            t.SetWidth(200000);t.SetNetCode(b.GetNetcodeFromNetname(net));t.SetLayer(pcbnew.F_Cu);b.Add(t)
    elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I(100000,0))
    elif fault=='partition':discard_items(b,[damaged])
    elif fault=='endpoint':damaged.Move(pcbnew.VECTOR2I(1000000,0))
    else:
        g=pcbnew.PCB_GROUP(b);g.SetName('unowned');b.Add(g);g.AddItem(rows[0])
    if fault=='foreign_net':
        pcbnew.SaveBoard(str(child),b)
        b=pcbnew.LoadBoard(str(child))
    field._save_field_snapshot(b,child)
    if original_pair is not None:
        saved=pcbnew.LoadBoard(str(child))
        assert not any(original_pair<=part for part in ordinary._partition(saved,time.monotonic()+10))
    r=op.receive(source,child,board_hint='synthetic',net=net,retired_track_uuids=cuts,allow_locked_track_uuids=locks)
    assert not r['ok']and not r['complete'],r

def row(data):
    source,child,net,cuts,locks=data
    return dict(kind=adapter.KIND,candidate=str(child),candidate_sha256=force._hash(child),
        net=net,retired_track_uuids=cuts,allow_locked_track_uuids=locks)

def test_actual_saved_adapter_nine_track_positive(tmp_path):
    data=fixture(tmp_path);r=adapter.receive_phase(data[0],data[0],row(data),'synthetic')
    assert r['ok']and r['complete'],r

@pytest.mark.parametrize('fault',['kind','max','timeout','width','locks','sha','same','17'])
def test_isolated_schema_or_stale_identity_never_dispatches(tmp_path,fault,monkeypatch):
    data=fixture(tmp_path);r=row(data)
    if fault=='kind':r['kind']='ordinary_source_reflow'
    elif fault=='max':r['maximum_source_tracks']=128
    elif fault=='timeout':r['timeout_s']=30
    elif fault=='width':r['width_nm']=100000
    elif fault=='locks':r['allow_locked_track_uuids']+=['outside']
    elif fault=='sha':r['candidate_sha256']='0'*64
    elif fault=='same':r['candidate']=str(data[0]);r['candidate_sha256']=force._hash(data[0])
    else:r['retired_track_uuids']=[str(i)for i in range(17)];r['allow_locked_track_uuids']=[]
    def forbidden(*a,**k):pytest.fail('invalid scope reached production receive')
    monkeypatch.setattr(adapter.connected,'receive',forbidden)
    with pytest.raises(ValueError):adapter.receive_phase(data[0],data[0],r,'synthetic')

@pytest.mark.parametrize('seconds',[True,0,-1,11,float('nan'),float('inf')])
def test_one_original_ten_second_budget_only(tmp_path,seconds):
    source,child,net,cuts,locks=fixture(tmp_path)
    with pytest.raises(ValueError):op.receive(source,child,board_hint='synthetic',net=net,
        retired_track_uuids=cuts,allow_locked_track_uuids=locks,timeout_s=seconds)

def test_legacy_eight_track_schema_unchanged(tmp_path):
    import root_receive_local_transaction_20261022 as base
    r=row(fixture(tmp_path));r['kind']='ordinary_source_reflow'
    with pytest.raises(ValueError):base.validate_phases([r])

def test_installed_adapter_actual_saved_dispatch_and_exact_restore(tmp_path):
    import root_receive_local_transaction_20261022 as base
    data=fixture(tmp_path);r=row(data)
    previous=base.validate_phases,base.receive_phase,base.annotation_dependencies
    before=Path(base.__file__).read_bytes()
    restore=adapter.install(base)
    try:
        base.validate_phases([r])
        child,proof=base.receive_phase(data[0],data[0],r,'synthetic')
        assert child==data[1].resolve()and proof['ok']and proof['complete']
        assert str(Path(adapter.__file__).resolve())in base.annotation_dependencies()
        with pytest.raises(ValueError,match='repeated_local_operator'):
            base.validate_phases([r,r])
        legacy=dict(r,kind='ordinary_source_reflow')
        with pytest.raises(ValueError):base.validate_phases([legacy])
    finally:restore()
    assert previous==(base.validate_phases,base.receive_phase,base.annotation_dependencies)
    assert before==Path(base.__file__).read_bytes()
