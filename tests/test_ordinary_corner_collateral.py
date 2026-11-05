"""Native-warning-guided atomic scopes, not unbounded dangling cleanup."""
import os
from pathlib import Path
import pcbnew
import pytest
import cec_ordinary_corner_collateral as collateral
import cec_scalar_corner_stage as stage
import cec_force_current as force
import cec_field_coupling as field
from cec_native_items import discard_items
from test_scalar_acute_stage import fixture as base
from test_field_proposals import track


def fixture(tmp_path,angle=0,mirror=False,layer=pcbnew.F_Cu,*,locked=False,extended_tail=False):
    b,net,old,at=base(angle,mirror,layer)
    discard_items(b,old)
    # Keep pads well away from the microscopic loop. A real land touching
    # the whole loop legitimately absorbs a short end in KiCad's DRC; that
    # would not test the newly exposed native dangling diagnostic at all.
    points=(((22.024,20.06),(24.024,20.06)) if extended_tail
            else ((22.024,18.024),(22.024,20.06)))
    for fp,point in zip(b.GetFootprints(),points):
        p=next(iter(fp.Pads()));p.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6) for v in at(*point))))
        p.SetSize(pcbnew.VECTOR2I(10000,10000))
    def exact(a,z):
        t=track(b,net,at(*a),at(*z),layer=layer,width=.2)
        t.SetStart(pcbnew.VECTOR2I(*(round(v*1e6) for v in at(*a))))
        t.SetEnd(pcbnew.VECTOR2I(*(round(v*1e6) for v in at(*z))))
        return t
    old=[exact(a,z) for a,z in (
        ((20,20),(19.964,20)),((19.964,20),(20.024,20.06)))]
    tail=exact((20.024,20.024),(20,20))
    exact((20.024,20.024),(20.024,20.06))
    if extended_tail:
        exact((20.024,20.06),(22.024,20.06))
        exact((22.024,20.06),(24.024,20.06))
    else:
        exact((20.024,20.024),(22.024,18.024))
        exact((20.024,20.06),(22.024,20.06))
    for t in b.GetTracks():t.SetLocked(locked)
    ids=[force._uid(t) for t in old];uid=force._uid(tail)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir()
    field._save_field_snapshot(b,source)
    # KiCad's missing-project defaults ignore dangling tracks. Exercise the
    # native diagnostic explicitly, as the real production family does; do
    # not fake an admission report or call an ignored warning a clean test.
    force._write(source.with_suffix('.kicad_pro'),dict(meta=dict(filename='board.kicad_pro',version=3),
        board=dict(design_settings=dict(rule_severities=dict(track_dangling='warning')))))
    candidate=force._copy_family(source,tmp_path/'candidate');child=pcbnew.LoadBoard(str(candidate))
    discard_items(child,[t for t in child.GetTracks() if force._uid(t) in ids])
    field._save_field_snapshot(child,candidate)
    warning=dict(type='track_dangling',items=[dict(uuid=uid)])
    return source,candidate,ids,uid,net,warning


@pytest.mark.parametrize('angle',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_renamed_rotated_mirrored_source_adjacency_supplies_only_bounded_read_only_proposal(tmp_path,angle,mirror,layer):
    source,child,cut,uid,net,warning=fixture(tmp_path,angle,mirror,layer,locked=True)
    before=[p.read_bytes() for p in (source,child)]
    result=collateral.plan(source,child,[warning],cut,{net},allow_locked_source=True)
    assert result['ok'] and result['complete'] and result['retired_track_uuids']==[uid]
    assert result['proofs'][0]['causal_cut_track_uuids'] and result['proofs'][0]['literal_native_warning']==warning
    assert not result['mutation_authorized'] and not result['release_authority']
    assert before==[p.read_bytes() for p in (source,child)]


@pytest.mark.parametrize('mode',['locked','group','mask','long','wide','changed','not_ordinary',
    'not_adjacent','wrong_fault','wrong_uuid','new_item','unrelated_items','malformed'])
def test_native_warning_alone_cannot_authorize_unrelated_copper_retirement(tmp_path,mode):
    source,child,cut,uid,net,warning=fixture(tmp_path,locked=mode=='locked');nets={net}
    if mode in ('group','mask','long','wide','not_adjacent'):
        for path in (source,child):
            b=pcbnew.LoadBoard(str(path));t=next(t for t in b.GetTracks() if force._uid(t)==uid)
            if mode=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(t)
            elif mode=='mask':t.SetHasSolderMask(True)
            elif mode=='long':t.SetStart(t.GetStart()+pcbnew.VECTOR2I_MM(33,0))
            elif mode=='wide':t.SetWidth(500000)
            else:t.Move(pcbnew.VECTOR2I_MM(1,1))
            field._save_field_snapshot(b,path)
    elif mode=='changed':
        b=pcbnew.LoadBoard(str(child));t=next(t for t in b.GetTracks() if force._uid(t)==uid)
        t.Move(pcbnew.VECTOR2I(1,1));field._save_field_snapshot(b,child)
    elif mode=='not_ordinary':nets=set()
    elif mode=='wrong_fault':warning['type']='clearance'
    elif mode=='wrong_uuid':warning['items'][0]['uuid']='not-a-source-item'
    elif mode=='new_item':
        b=pcbnew.LoadBoard(str(child));t=track(b,net,(25,25),(25,25.1))
        warning['items'][0]['uuid']=force._uid(t);field._save_field_snapshot(b,child)
    elif mode=='unrelated_items':warning['items'].append(dict(uuid=cut[0]))
    else:warning=None
    before=[p.read_bytes() for p in (source,child)]
    result=collateral.plan(source,child,[warning],cut,nets)
    assert not result['ok'] and not result['retired_track_uuids']
    assert before==[p.read_bytes() for p in (source,child)]


@pytest.mark.parametrize('kwargs',[dict(timeout_s=0),dict(timeout_s=True),dict(timeout_s=float('nan')),
    dict(allow_locked_source=1)])
def test_invalid_collateral_context_has_no_mutation_authority(tmp_path,kwargs):
    source,child,cut,uid,net,warning=fixture(tmp_path)
    with pytest.raises(ValueError):collateral.plan(source,child,[warning],cut,{net},**kwargs)


@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
@pytest.mark.parametrize('extended_tail',[False,True])
def test_saved_atomic_cut_replays_new_native_warning_then_clears_it_without_waiver(tmp_path,layer,extended_tail):
    native=os.environ.get('CEC_NATIVE_DRC_TEST_BUILD')
    if not native:pytest.skip('uncapped native DRC build not configured')
    source,child,cut,uid,net,warning=fixture(tmp_path,layer=layer,locked=True,extended_tail=extended_tail)
    before=source.read_bytes()
    r=stage.run(source,tmp_path/'stage',board_hint='synthetic',reporting_build=Path(native),
        expected_source_sha256=force._hash(source),geometry_policy='acute_shortcut',allow_locked_source=True)
    assert r['ok'] and r['complete'] and r['changed'],r
    row=next(v for v in r['attempts'] if v['accepted'])
    assert row['new_native_fault_ids_before_collateral'] and not row['new_native_fault_ids']
    assert row['native_collateral_scope']['retired_track_uuids']==[uid]
    scopes=row['native_collateral_scopes']
    rounds=3 if extended_tail else 1
    assert len(scopes)==rounds
    assert set(r['construction']['retired_track_uuids'])==set(cut)|{u for p in scopes for u in p['retired_track_uuids']}
    assert r['independent_receiving']['actual_saved_redundant_cut_only']
    assert r['independent_receiving']['whole_original_ordinary_delta']['all_prior_native_terminal_partitions_preserved']
    assert r['craft_after']['issue_count']==0 and r['native_report_invocations']==2+rounds
    assert source.read_bytes()==before and not r['fab_ready'] and not r['release_authority']
