"""Native original-island frontier geometry, never original barrel ratings."""
import time,copy,shutil
from pathlib import Path
import pcbnew
import pytest
import cec_distributed_supply_layer_join as join
import cec_force_current as force
import cec_field_coupling as field
from test_distributed_supply_layer_join import native,source_boundary,companions


def geometry(tmp_path,turn=0,face=pcbnew.F_Cu):
    board,net,pads,source=native(tmp_path,turn,face)
    def point(x,y):
        for _ in range(turn):x,y=40-y,x
        return pcbnew.VECTOR2I_MM(x,y)
    def track(a,b,layer,width=.5):
        item=pcbnew.PCB_TRACK(board);item.SetStart(point(*a));item.SetEnd(point(*b))
        item.SetWidth(pcbnew.FromMM(width));item.SetLayer(layer);item.SetNetCode(pads[0].GetNetCode())
        board.Add(item);return item
    launch=track((8,20),(8,22),face)
    via=pcbnew.PCB_VIA(board);via.SetPosition(point(8,22));via.SetWidth(600000)
    via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNetCode(pads[0].GetNetCode());board.Add(via)
    inner=track((8,22),(12,22),pcbnew.In2_Cu)
    thin=track((8,22),(8,26),pcbnew.In2_Cu,.2)
    plane=track((8,22),(12,22),pcbnew.In1_Cu)
    detached=track((30,30),(32,30),pcbnew.In2_Cu)
    pcbnew.SaveBoard(str(source),board)
    return board,net,pads,source,point,(launch,via,inner,thin,plane,detached)


@pytest.mark.parametrize('turn,face',[(r,f)for r in range(4)for f in(pcbnew.F_Cu,pcbnew.B_Cu)])
def test_only_explicit_original_native_frontier_offers_real_rated_track(tmp_path,turn,face):
    board,net,pads,source,point,items=geometry(tmp_path,turn,face)
    original=source.read_bytes();binding=force._hash(source)
    with source_boundary(net):
        proposal=join.plan_native_frontier(board,source,board_hint='arbitrary-source-family',net=net,
            pad_uuids=[force._uid(p)for p in pads[:2]])
        assert proposal['complete'],proposal
        strict=join._ports(board,proposal,time.monotonic()+10.)
        explicit=join._ports(board,proposal,time.monotonic()+10.,native_frontier=True)
    anchor=force._uid(items[2]);all_strict=[a for menu in strict for a in menu]
    offered=[a for menu in explicit for a in menu]
    assert anchor not in {a['uuid']for a in all_strict}
    received={tuple(a['point_nm'])for a in offered if a['uuid']==anchor}
    # The old via's actual drill void forbids the coincident endpoint.
    assert received=={tuple(point(10,22)),tuple(point(12,22))}
    assert not {force._uid(v)for v in(items[1],*items[3:])}&{a['uuid']for a in offered}
    assert all(a['kind']in('pad_center','rated_track')for a in offered)
    assert not proposal['current_qualified']and not proposal['plated_barrel_current_qualified']
    assert source.read_bytes()==original and force._hash(source)==binding


@pytest.mark.parametrize('fault',['disconnected','thin','plane','different_net'])
def test_actual_frontier_requires_original_contact_face_and_whole_width(tmp_path,fault):
    board,net,pads,source,point,items=geometry(tmp_path)
    target=items[2]
    if fault=='disconnected':target.SetStart(point(26,22));target.SetEnd(point(28,22))
    elif fault=='thin':target.SetWidth(499999)
    elif fault=='plane':target.SetLayer(pcbnew.In1_Cu)
    else:
        other=pcbnew.NETINFO_ITEM(board,'/unrelated');board.Add(other);target.SetNet(other)
        target.SetStart(point(26,22));target.SetEnd(point(28,22))
    pcbnew.SaveBoard(str(source),board);before=source.read_bytes()
    with source_boundary(net):
        proposal=join.plan_native_frontier(board,source,board_hint='arbitrary-source-family',net=net,
            pad_uuids=[force._uid(p)for p in pads[:2]])
        assert proposal['complete'],proposal
        menus=join._ports(board,proposal,time.monotonic()+10.,native_frontier=True)
    assert force._uid(target)not in {a['uuid']for menu in menus for a in menu}
    assert source.read_bytes()==before


@pytest.mark.parametrize('turn,face',[(0,pcbnew.F_Cu),(1,pcbnew.B_Cu),(2,pcbnew.F_Cu),(3,pcbnew.B_Cu)])
def test_saved_frontier_recompiles_source_and_legacy_does_not_self_enable(tmp_path,turn,face):
    board,net,pads,source,point,items=geometry(tmp_path,turn,face)
    # Remove decoy branches: this positive has exactly one old physical entry.
    for item in items[3:]:board.Remove(item)
    pcbnew.SaveBoard(str(source),board);original=source.read_bytes()
    child=pcbnew.LoadBoard(str(source));code=child.GetNetcodeFromNetname(net)
    for a,b,layer in[((12,22),(16,22),pcbnew.In2_Cu),((16,22),(16,20),face)]:
        t=pcbnew.PCB_TRACK(child);t.SetStart(point(*a));t.SetEnd(point(*b));t.SetLayer(layer)
        t.SetWidth(500000);t.SetNetCode(code);child.Add(t)
    via=pcbnew.PCB_VIA(child);via.SetPosition(point(16,22));via.SetWidth(900000);via.SetDrill(400000)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetNetCode(code);child.Add(via)
    candidate=tmp_path/'frontier-child.kicad_pcb';field._save_field_snapshot(child,candidate)
    companions(source,candidate);ids=[force._uid(p)for p in pads[:2]]
    with source_boundary(net):
        legacy=join.receive(source,candidate,board_hint='arbitrary-source-family',net=net,pad_uuids=ids)
        received=join.receive_native_frontier(source,candidate,board_hint='arbitrary-source-family',net=net,pad_uuids=ids)
    assert not legacy['ok']and legacy['errors']
    assert received['ok']and received['complete'],received
    assert received['exactly_two_source_islands_joined']and received['all_source_partitions_preserved']
    assert not received['current_qualified']and not received['plated_barrel_current_qualified']
    assert received['unresolved_barrel_ampacity_and_thermal_debt']
    assert source.read_bytes()==original


@pytest.mark.parametrize('fault',['thin_launch','not_through','not_full_depth','zero_drill','empty_annulus'])
def test_original_graph_never_borrows_unproved_barrel_or_thin_bridge(tmp_path,fault):
    board,net,pads,source,point,items=geometry(tmp_path)
    with source_boundary(net):
        proposal=join.plan_native_frontier(board,source,board_hint='arbitrary-source-family',net=net,
            pad_uuids=[force._uid(p)for p in pads[:2]])
        assert proposal['complete'],proposal
        if fault=='thin_launch':items[0].SetWidth(499999)
        elif fault=='not_through':items[1].SetViaType(pcbnew.VIATYPE_MICROVIA)
        elif fault=='not_full_depth':
            items[1].SetViaType(pcbnew.VIATYPE_BLIND)
            items[1].SetLayerPair(pcbnew.F_Cu,pcbnew.In2_Cu)
            assert items[1].BottomLayer()==pcbnew.In2_Cu
        elif fault=='zero_drill':items[1].SetDrill(0)
        else:items[1].SetWidth(300000)
        menus=join._ports(board,proposal,time.monotonic()+10.,native_frontier=True)
    assert force._uid(items[2])not in {a['uuid']for menu in menus for a in menu}


@pytest.mark.parametrize('forgery',['native_proposal','legacy_flag','legacy_scope'])
def test_private_legacy_constructor_cannot_self_enable_native_frontier(tmp_path,forgery):
    board,net,pads,source,point,items=geometry(tmp_path)
    candidate=tmp_path/'exact-copy.kicad_pcb';shutil.copy2(source,candidate);companions(source,candidate)
    before=candidate.read_bytes()
    with source_boundary(net):
        compiler=join.plan_native_frontier if forgery=='native_proposal'else join.plan
        proposal=compiler(board,source,board_hint='arbitrary-source-family',net=net,
            pad_uuids=[force._uid(p)for p in pads[:2]])
        assert proposal['complete'],proposal
        if forgery=='legacy_flag':proposal['source_access_mode']='original_native_islands_full_class_track_frontiers'
        if forgery=='legacy_scope':proposal['scope']='source_distributed_full_class_original_native_frontier_join'
        with pytest.raises(ValueError,match='fresh_exact_distributed_layer_scope_required'):
            join.construct_private(source,candidate,proposal,board_hint='arbitrary-source-family')
    assert candidate.read_bytes()==before


@pytest.mark.parametrize('mode',[1,0,None,'true',{},[]])
def test_native_frontier_switch_is_an_explicit_bool(tmp_path,mode):
    board,net,pads,source,point,items=geometry(tmp_path)
    with source_boundary(net):
        proposal=join.plan(board,source,board_hint='arbitrary-source-family',net=net,
            pad_uuids=[force._uid(p)for p in pads[:2]])
        with pytest.raises(ValueError,match='explicit_native_frontier_mode_required'):
            join._ports(board,proposal,time.monotonic()+10.,native_frontier=mode)


def adapter_row(tmp_path):
    import root_native_frontier_layer_join_phase_20261026 as adapter
    child=tmp_path/'saved.kicad_pcb';child.write_text('actual saved bytes')
    return dict(kind=adapter.KIND,candidate=str(child),candidate_sha256=force._hash(child),
        net='/literal/aggregate',pad_uuids=['literal-pad-a','literal-pad-b'])


def test_identity_only_adapter_dispatch_and_scoped_registration(tmp_path,monkeypatch):
    import root_native_frontier_layer_join_phase_20261026 as adapter
    base=adapter.base;row=adapter_row(tmp_path);parent=tmp_path/'source.kicad_pcb';parent.write_text('Source')
    previous=(base.validate_phases,base.receive_phase,base.annotation_dependencies,base.KINDS)
    calls=[]
    def receive(source,child,**kwargs):
        calls.append((source,child,kwargs));return dict(ok=True,complete=True)
    monkeypatch.setattr(join,'receive_native_frontier',receive)
    assert adapter.KIND not in base.KINDS
    with adapter.installed():
        base.validate_phases([row])
        child,result=base.receive_phase(parent,parent,row,'source-family')
        assert child==Path(row['candidate'])and result['ok']
        assert adapter.KIND not in base.KINDS
    assert previous==(base.validate_phases,base.receive_phase,base.annotation_dependencies,base.KINDS)
    assert calls==[(parent,Path(row['candidate']),dict(board_hint='source-family',net=row['net'],
        pad_uuids=row['pad_uuids'],timeout_s=10.))]
    with pytest.raises(ValueError):base.validate_phases([row])


@pytest.mark.parametrize('key',['amps','current','width','diameter','drill','points_nm','position_nm',
    'layers','timeout_s','lease_s','allow_locked','source_access_mode','native_frontier','proposal'])
def test_adapter_rejects_every_nonidentity_authority(tmp_path,key):
    import root_native_frontier_layer_join_phase_20261026 as adapter
    row=adapter_row(tmp_path);row[key]=1
    with pytest.raises(ValueError,match='exact_typed_local_phase_schema_required'):
        adapter.validate_phases([row])
    assert adapter.KIND not in adapter.base.KINDS


@pytest.mark.parametrize('fault',['duplicate','empty','bad_hash','empty_path','empty_net','nonstring_net',
    'empty_pads','duplicate_pads','one_pad','three_pads','nonstring_pad','empty_pad'])
def test_adapter_refuses_malformed_identity_packets(tmp_path,fault):
    import root_native_frontier_layer_join_phase_20261026 as adapter
    row=adapter_row(tmp_path);rows=[row]
    if fault=='duplicate':rows=[row,copy.deepcopy(row)]
    elif fault=='empty':rows=[]
    elif fault=='bad_hash':row['candidate_sha256']='INVALID'
    elif fault=='empty_path':row['candidate']=''
    elif fault=='empty_net':row['net']=''
    elif fault=='nonstring_net':row['net']=True
    elif fault=='empty_pads':row['pad_uuids']=[]
    elif fault=='duplicate_pads':row['pad_uuids']=['a','a']
    elif fault=='one_pad':row['pad_uuids']=['a']
    elif fault=='three_pads':row['pad_uuids']=['a','b','c']
    elif fault=='nonstring_pad':row['pad_uuids']=['a',True]
    else:row['pad_uuids']=['a','']
    with pytest.raises(ValueError):adapter.validate_phases(rows)
    assert adapter.KIND not in adapter.base.KINDS


def test_adapter_stale_saved_hash_never_dispatches_and_scope_unwinds(tmp_path,monkeypatch):
    import root_native_frontier_layer_join_phase_20261026 as adapter
    row=adapter_row(tmp_path);Path(row['candidate']).write_text('mutated saved bytes')
    parent=tmp_path/'source.kicad_pcb';parent.write_text('Source')
    previous=(adapter.base.validate_phases,adapter.base.receive_phase,adapter.base.annotation_dependencies)
    monkeypatch.setattr(join,'receive_native_frontier',lambda *a,**kw:pytest.fail('stale hash dispatched'))
    with pytest.raises(AssertionError):
        with adapter.installed():adapter.base.receive_phase(parent,parent,row,'source-family')
    assert previous==(adapter.base.validate_phases,adapter.base.receive_phase,adapter.base.annotation_dependencies)
    assert adapter.KIND not in adapter.base.KINDS


def test_adapter_dependencies_are_actual_dispatch_and_core_file_hashes():
    import root_native_frontier_layer_join_phase_20261026 as adapter
    dependencies=adapter.dependencies()
    for module in(adapter,adapter.base,join):
        path=Path(module.__file__).resolve()
        assert dependencies[str(path)]==force._hash(path)
    assert all(Path(path).is_file()and force._hash(Path(path))==digest for path,digest in dependencies.items())
