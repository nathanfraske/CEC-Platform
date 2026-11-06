"""Actual adjacent stage-control cuts are one complete Source cohort."""
import copy
from pathlib import Path
import time

import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_field_coupling as field
import cec_linear_stage_ground_boundary as op
import cec_macro_cut_components as cuts
from test_linear_stage_ground_transport import fixture as transport_fixture


def fixture(tmp_path,monkeypatch):
    parent,q,ids,root=transport_fixture(tmp_path,monkeypatch,True)
    for target in q['poses'].values():target[0]+=1.5
    owner=parent.FindFootprintByReference(ids['owner']);first=op.native._items(parent)[ids['edge']]
    pad=owner.FindPadByNumber('4');pad.SetNet(owner.FindPadByNumber('3').GetNet())
    tree,_=op.canonical._export(root,time.monotonic()+8.)
    ground=next(n for n in op.canonical.synth._kids(op.canonical.synth._first(tree,'nets'),'net')
        if op.canonical.synth._val(n,'name','')=='GND')
    for net in op.canonical.synth._kids(op.canonical.synth._first(tree,'nets'),'net'):
        for node in list(op.canonical.synth._kids(net,'node')):
            if(op.canonical.synth._val(node,'ref','')==ids['owner']
                    and op.canonical.synth._val(node,'pin','')=='4'):
                net.remove(node);ground.append(node)
    a,b=first.GetStart(),first.GetEnd()
    # Cross the first edge in its body, not at the peer's fixed endpoint.
    # Moving only the peer's package endpoint then loses that old body
    # contact, exactly the situation which must not invent a retained port.
    junction=pcbnew.VECTOR2I(a.x+300000,b.y)
    peer=pcbnew.PCB_TRACK(parent);peer.SetNet(pad.GetNet());peer.SetLayer(first.GetLayer())
    peer.SetStart(pad.GetPosition());peer.SetEnd(junction);peer.SetWidth(first.GetWidth());peer.SetLocked(True)
    parent.Add(peer);ids['peer']=op.force._uid(peer);ids['peer_root']=op.force._uid(pad)
    field._save_field_snapshot(parent,Path(parent.GetFileName()))
    q['source_native_binding']=op.row._source_binding(parent)
    q['source_linear_power_stages']=op.entries.stage.collect(parent,q['poses'],board_hint=str(root),enabled=True)
    cohort=sorted([ids['edge'],ids['peer']])
    return parent,q,ids,root,cohort


def union(parent,q,cohort):
    return op.ownership(parent,q,cohort,deadline=time.monotonic()+9.,
        allow_locked_track_uuids=cohort,native_transport_options={})


def test_native_union_marks_peer_cocut_and_preserves_every_surviving_port(tmp_path,monkeypatch):
    parent,q,ids,root,cohort=fixture(tmp_path,monkeypatch)
    before=Path(parent.GetFileName()).read_bytes();binding=op.row._source_binding(parent)
    result=union(parent,q,cohort)
    assert {r['change']['uuid']for r in result['extras']}==set(cohort)
    for row in result['extras']:
        authority=row['authority'];proof=authority['source_linear_stage_ground_boundary']
        assert proof['explicit_selected_source_edge_uuids']==cohort
        peer=next(p for p in proof['source_contacts']if p['item']['uuid']in set(cohort)-{row['change']['uuid']})
        assert peer['independently_co_cut_source_edge']is True
        assert peer['every_original_contact_mandatory']is True
        assert 'source_contact_port'not in peer
        assert peer not in authority['exact_retained_ports']
        assert op.authority_label(authority)and authority['kind']==op.KIND
        assert all(r['role']=='control'and r['functional_ground_return']is False
            for r in authority['source_pad_roots'])
    private,transport=compiler._frame(parent,Path(parent.GetFileName()),q,timeout_s=9.)
    assert all(op.transport_matches(r['authority'],transport)for r in result['extras'])
    requests,records=cuts.requests(parent,private,result['extras'],set(cohort),transport,
        project_contacts=compiler._project_contacts,deadline=time.monotonic()+9.)
    assert len(records)==1
    record=records[0];assert record['source_extra_edge_uuids']==cohort
    actual={p['source_item_uuid']for p in record['surviving_contacts']}
    assert {ids['root'],ids['peer_root'],ids['via']}<=actual
    assert not actual&set(cohort)
    expected={p['item']['uuid']for row in result['extras']
        for p in row['authority']['exact_retained_ports']}
    assert actual==expected
    ports=[p for contact in record['surviving_contacts']for p in contact['projected_literal_ports']]
    requested=[r[end]for r in requests.values()for end in('a','b')]
    assert all(port in requested for port in ports)
    assert all(r['every_surviving_source_component_port_mandatory']for r in requests.values())
    assert binding==op.row._source_binding(parent)and Path(parent.GetFileName()).read_bytes()==before


@pytest.mark.parametrize('fault',['omitted_peer','wrong_cohort','wrong_transport','wrong_proposal'])
def test_incomplete_or_mismatched_cohort_cannot_supply_cut_components(tmp_path,monkeypatch,fault):
    parent,q,ids,root,cohort=fixture(tmp_path,monkeypatch)
    extras=union(parent,q,cohort)['extras']
    private,transport=compiler._frame(parent,Path(parent.GetFileName()),q,timeout_s=9.)
    extras=copy.deepcopy(extras)
    if fault=='omitted_peer':extras=extras[:1]
    elif fault=='wrong_transport':transport['new_barrels_created']=1
    else:
        authority=extras[-1]['authority'];proof=authority['source_linear_stage_ground_boundary']
        if fault=='wrong_cohort':
            proof['explicit_selected_source_edge_uuids']=[extras[-1]['change']['uuid']]
        else:proof['source_proposal_sha256']='0'*64
        authority['Source_binding_sha256']=op._digest(proof)
    with pytest.raises(ValueError,match='cohort|transport'):
        cuts.requests(parent,private,extras,set(cohort),transport,
            project_contacts=compiler._project_contacts,deadline=time.monotonic()+9.)


def test_singleton_does_not_claim_peer_cut_and_default_remains_unchanged(tmp_path,monkeypatch):
    parent,q,ids,root,cohort=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError,match='locked'):
        op.ownership(parent,q,cohort,deadline=time.monotonic()+9.)
    default=op.ownership(parent,q,cohort,deadline=time.monotonic()+9.,allow_locked_track_uuids=cohort)
    assert all(r['authority']['existing_barrels_must_survive_unchanged']is True for r in default['extras'])
    with pytest.raises(ValueError,match='retained_native_copper'):
        op.ownership(parent,q,[ids['edge']],deadline=time.monotonic()+9.,
            allow_locked_track_uuids=[ids['edge']],native_transport_options={})
