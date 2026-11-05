import copy
import sys
import hashlib
from pathlib import Path
import pcbnew
import pytest
import cec_control_shunt_placement as op
import cec_force_current as force
import cec_field_coupling as field
import cec_cell_row_rebuild as row
from test_source_ground_leaf import source_fixture


def fixture(tmp_path,monkeypatch,turn=0,back=False):
    b,owner,ground,root,tree,uids=source_fixture(tmp_path,monkeypatch,'control')
    exporter=op.leaf._export
    def bound_export(*a,**kw):
        tree,metadata=exporter(*a,**kw);metadata.update(exporter=sys.executable,exporter_sha256=force._hash(Path(sys.executable)),**op.semantic.metadata(tree))
        return tree,metadata
    monkeypatch.setattr(op.leaf,'_export',bound_export)
    cap=ground.GetParentFootprint()
    for fp in b.GetFootprints():
        fp.SetOrientationDegrees(turn)
        if back:fp.Flip(pcbnew.VECTOR2I(0,0),False)
    field._save_field_snapshot(b,Path(b.GetFileName()))
    poses={cap.GetReference():[cap.GetPosition().x/1e6+.5,cap.GetPosition().y/1e6,(turn+180)%360]}
    return b,owner,ground,root,poses


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_canonical_renamed_control_shunt_not_power_or_bypass(tmp_path,monkeypatch,turn,back):
    b,owner,g,root,poses=fixture(tmp_path,monkeypatch,turn,back);before=row._source_binding(b)
    q=op.plan(b,poses,board_hint=str(root));assert len(q)==1
    r=next(iter(q.values()));assert r['control_owner']==owner.GetReference()
    assert r['role']=='source_control_shunt_passive'and r['ground_pad_uuid']==force._uid(g)
    assert not r['bypass_owner']and not r['current_authority']and not r['reset_timing_qualified']
    assert before==row._source_binding(b)


@pytest.mark.parametrize('fault',['missingproof','wrongproof','unknownowner','dnp','locked','group','owner_move','wrongnet','ambiguity','nan'])
def test_source_and_pose_refusals(tmp_path,monkeypatch,fault):
    b,owner,g,root,poses=fixture(tmp_path,monkeypatch);cap=g.GetParentFootprint()
    if fault in('missingproof','wrongproof'):
        old=op.leaf.plan
        def bad(*a,**kw):
            q=old(*a,**kw)
            if fault=='missingproof':q['proofs']={}
            else:next(iter(q['proofs'].values()))['owner']='forged'
            return q
        monkeypatch.setattr(op.leaf,'plan',bad)
    elif fault=='unknownowner':owner.SetField('MPN','unknown')
    elif fault=='dnp':cap.SetDNP(True)
    elif fault=='locked':cap.SetLocked(True)
    elif fault=='group':
        group=pcbnew.PCB_GROUP(b);b.Add(group);group.AddItem(cap)
    elif fault=='owner_move':poses[owner.GetReference()]=[1,0,0]
    elif fault=='wrongnet':cap.FindPadByNumber('1').SetNetCode(0)
    elif fault=='ambiguity':
        old=op.leaf._candidates
        def twice(*a):
            q=old(*a);v=next(v for v in q.values()if v[1]=='source_control_shunt_ground');q['forged_duplicate']=v;return q
        monkeypatch.setattr(op.leaf,'_candidates',twice)
    else:next(iter(poses.values()))[0]=float('nan')
    if fault in('unknownowner','dnp','wrongnet'):
        # Not applicable is not admission: the original escape.prepare
        # manufacturer gate still refuses such a passive.
        assert op.plan(b,poses,board_hint=str(root))=={}
    else:
        with pytest.raises(ValueError):op.plan(b,poses,board_hint=str(root))


def test_no_applicable_owner_does_not_export_source(tmp_path,monkeypatch):
    b,owner,g,root,poses=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(op.leaf,'plan',lambda *a,**k:pytest.fail('unrelated source export'))
    assert op.plan(b,{owner.GetReference():[0,0,0]},board_hint=str(root))=={}


@pytest.mark.parametrize('fault',['forged','face','net','ownerpose'])
def test_projected_request_rederives_source_and_refuses_changes(tmp_path,monkeypatch,fault):
    b,owner,g,root,poses=fixture(tmp_path,monkeypatch);q=op.plan(b,poses,board_hint=str(root))
    proposal=dict(poses=poses,selected_control_shunts=q,board_hint=str(root))
    child=pcbnew.LoadBoard(b.GetFileName())
    if fault=='forged':next(iter(q.values()))['control_pin']='forged'
    elif fault=='face':child.FindFootprintByReference(g.GetParentFootprint().GetReference()).Flip(pcbnew.VECTOR2I(0,0),False)
    elif fault=='net':child.FindFootprintByReference(g.GetParentFootprint().GetReference()).FindPadByNumber('1').SetNetCode(0)
    else:child.FindFootprintByReference(owner.GetReference()).Move(pcbnew.VECTOR2I_MM(.1,0))
    with pytest.raises(ValueError):op.requests(b,child,proposal)


def test_integration_separate_scope_and_mandatory_ground_hook():
    text=(Path(op.__file__).parent/'cec_cell_escape_replan.py').read_text()
    assert "if reqs:raise ValueError('control_shunt_cannot_alias_power_bypass')"in text
    assert "result['selected_control_shunts']=control_shunts"in text
    assert 'requests.update(control_shunt.requests(source,board,proposal))'in text
    assert "for ref in moved|set(proposal['selected_bypasses']):"in text


def test_fresh_changed_raw_export_hash_stable_requests_with_full_semantic_proof(tmp_path,monkeypatch):
    b,owner,g,root,poses=fixture(tmp_path,monkeypatch);export=op.leaf._export;count=[0]
    def dated(*a,**kw):
        tree,metadata=export(*a,**kw);count[0]+=1
        metadata['netlist_sha256']=format(count[0],'064x');return tree,metadata
    monkeypatch.setattr(op.leaf,'_export',dated)
    with op.capture_exports()as observations:
        q=op.plan(b,poses,board_hint=str(root))
    proposal=dict(poses=poses,selected_control_shunts=q,board_hint=str(root))
    child=pcbnew.LoadBoard(b.GetFileName())
    first=op.requests(b,child,proposal);second=op.requests(b,child,proposal)
    assert first==second and len(first)==1 and count[0]>=3
    exporter=next(iter(first.values()))['source_control_shunt']['source_proof']['exporter']
    assert 'netlist_sha256'not in exporter and 'netlist_semantic_sha256'in exporter
    assert observations[0]['raw_source_proof']['exporter']['netlist_sha256']==format(1,'064x')


def test_entire_prepared_proposal_stable_across_export_clock_and_raw_bytes(tmp_path,monkeypatch):
    import cec_cell_escape_replan as escape
    b,owner,g,root,poses=fixture(tmp_path,monkeypatch);export=op.leaf._export;counter=[0]
    def dated(*a,**kw):
        tree,metadata=export(*a,**kw);counter[0]+=1;tree=copy.deepcopy(tree)
        tree.append(['design',['source',str(root)],['date','2026-10-22T21:00:'+format(counter[0],'02d')+'-0500'],['tool','test-canonical-export']])
        metadata.update(netlist_sha256=hashlib.sha256(repr(tree).encode()).hexdigest(),**op.semantic.metadata(tree))
        return tree,metadata
    monkeypatch.setattr(op.leaf,'_export',dated)
    # Source fixture uses a generated schematic under tmp; no real-board job.
    # Its manufacturer supply pin is intentionally outside this EN-only
    # fixture; do not manufacture a bypass assignment to make it applicable.
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda *a,**k:{'assigned':{}})
    with op.capture_exports()as observations:
        first=escape.prepare(b,poses,board_hint=str(root))
        second=escape.prepare(b,poses,board_hint=str(root))
    assert first==second and counter[0]>=2
    assert observations[0]['raw_source_proof']['exporter']['netlist_sha256']!=observations[-1]['raw_source_proof']['exporter']['netlist_sha256']
    cap=g.GetParentFootprint();cap.FindPadByNumber('1').SetNetCode(0)
    with pytest.raises(ValueError):escape.prepare(b,poses,board_hint=str(root))


def test_canonical_pin_source_semantics_changed_is_not_clock_metadata(tmp_path,monkeypatch):
    b,owner,g,root,poses=fixture(tmp_path,monkeypatch);q=op.plan(b,poses,board_hint=str(root))
    export=op.leaf._export
    def changed(*a,**kw):
        tree,metadata=export(*a,**kw);metadata['netlist_semantic_sha256']='f'*64;return tree,metadata
    monkeypatch.setattr(op.leaf,'_export',changed)
    proposal=dict(poses=poses,selected_control_shunts=q,board_hint=str(root))
    with pytest.raises(ValueError,match='fresh_source'):op.requests(b,pcbnew.LoadBoard(b.GetFileName()),proposal)
