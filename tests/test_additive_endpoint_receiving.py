"""Only incoming complete pad-local tapers can extend endpoint ownership."""
import json
from pathlib import Path
import pcbnew
import pytest
import cec_additive_route_receiving as receiving
import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
from test_additive_route_receiving import terminal
from test_field_refill_proposals import ground_fixture
from test_field_proposals import track


def fixture(tmp_path,*,legacy_cover=False):
    source,board=ground_fixture(tmp_path)
    terminal(board,'OTHER_DEVICE_91',(26,14))
    terminal(board,'RENUMBERED_DEVICE_63',(22,14))
    narrow=track(board,'/CONTROL',(26,14),(26.4,14),width=.28)
    track(board,'/CONTROL',(26.4,14),(28,14),width=1.)
    owned=fr.group_endpoint_neckdowns(board,[narrow],pcbnew.FromMM(1.))
    assert owned['tracks']==1
    if legacy_cover:
        cover=pcbnew.ZONE(board);cover.SetLayer(pcbnew.F_Cu);cover.SetNetCode(board.GetNetcodeFromNetname('/CONTROL'))
        cover.Outline().NewOutline()
        for x,y in ((20,2),(21,2),(21,3),(20,3)):cover.Outline().Append(pcbnew.VECTOR2I_MM(x,y))
        board.Add(cover);next(g for g in board.Groups() if g.GetName()==fr.ENDPOINT_NECKDOWN_GROUP).AddItem(cover)
    settings=json.loads(source.with_suffix('.kicad_pro').read_text())
    settings['net_settings']={'classes':[{'name':'Default','track_width':1.,'clearance':.127}]}
    source.with_suffix('.kicad_pro').write_text(json.dumps(settings))
    fr.ensure_endpoint_neckdown_rule(str(source),owned)
    field._save_field_snapshot(board,source)
    child=force._copy_family(source,tmp_path/'child')
    trial=pcbnew.LoadBoard(str(child))
    short=track(trial,'/CONTROL',(22,14),(22.4,14),width=.28)
    throat=track(trial,'/CONTROL',(22.4,14),(24,14),width=1.)
    group=next(g for g in trial.Groups() if g.GetName()==fr.ENDPOINT_NECKDOWN_GROUP)
    group.AddItem(short)
    receiving._ground_refill(trial);field._save_field_snapshot(trial,child)
    return source,child,force._uid(short),force._uid(throat)


def test_exact_qualified_extension_requires_explicit_local_role(tmp_path):
    source,child,_,_=fixture(tmp_path)
    before=source.read_bytes(),force._sidecars(source)
    assert not receiving.receive(source,child)['ok']
    proof=receiving.receive(source,child,allow_endpoint_neckdown_additions=True)
    assert proof['ok'] and proof['complete'],proof
    assert proof['release_authority'] is False
    assert any(r['kind']=='exact_qualified_endpoint_group_extension'
        for r in proof['allowed_original_changes'])
    assert before==(source.read_bytes(),force._sidecars(source))


@pytest.mark.parametrize('bad',['long','missing_throat','branched','grouped_full_width',
    'claims_original','changes_original','broad_rule'])
def test_group_name_cannot_qualify_a_bad_or_expansive_escape(tmp_path,bad):
    source,child,uid,throat_uid=fixture(tmp_path)
    board=pcbnew.LoadBoard(str(child))
    by_id={force._uid(t):t for t in board.GetTracks()}
    short,throat=by_id[uid],by_id[throat_uid]
    group=next(g for g in board.Groups() if g.GetName()==fr.ENDPOINT_NECKDOWN_GROUP)
    if bad=='long':
        short.SetEnd(pcbnew.VECTOR2I_MM(24.5,14));throat.SetStart(short.GetEnd())
    elif bad=='missing_throat':
        throat.SetStart(pcbnew.VECTOR2I_MM(23,14))
    elif bad=='branched':
        short.SetEnd(pcbnew.VECTOR2I_MM(22.2,14))
        for end in ((22.4,14),(22.2,14.2)):
            group.AddItem(track(board,'/CONTROL',(22.2,14),end,width=.28))
    elif bad=='grouped_full_width':
        group.AddItem(throat)
    elif bad=='claims_original':
        group.AddItem(next(t for t in board.GetTracks() if force._uid(t) not in (uid,throat_uid)
            and t.GetParentGroup() is None))
    elif bad=='changes_original':
        next(t for t in board.GetTracks() if force._uid(t) not in (uid,throat_uid)).SetLocked(True)
    else:
        child.with_suffix('.kicad_dru').write_text(child.with_suffix('.kicad_dru').read_text()+
            '\n(rule "not allowed" (constraint clearance (min 0mm)))\n')
    receiving._ground_refill(board);field._save_field_snapshot(board,child)
    proof=receiving.receive(source,child,allow_endpoint_neckdown_additions=True)
    assert not proof['ok'] and proof['errors'],proof


@pytest.mark.parametrize('width',[.2,.34,.742453])
def test_exact_endpoint_rule_is_derived_from_complete_native_group_not_last_report(tmp_path,width):
    source,child,uid,_=fixture(tmp_path);original=(source.read_bytes(),force._sidecars(source))
    board=pcbnew.LoadBoard(str(child));item=next(t for t in board.GetTracks() if force._uid(t)==uid)
    item.SetWidth(pcbnew.FromMM(width));receiving._ground_refill(board);field._save_field_snapshot(board,child)
    rule=receiving.bind_local_endpoint_rule(board,child)
    assert rule['min_width_mm']==round(min(.28,width),3)
    proof=receiving.receive(source,child,allow_endpoint_neckdown_additions=True)
    assert proof['ok'] and proof['complete'],proof
    assert (source.read_bytes(),force._sidecars(source))==original


def test_last_new_width_rule_and_arbitrary_relaxation_are_both_refused(tmp_path):
    source,child,uid,_=fixture(tmp_path);board=pcbnew.LoadBoard(str(child))
    item=next(t for t in board.GetTracks() if force._uid(t)==uid);item.SetWidth(742453)
    receiving._ground_refill(board);field._save_field_snapshot(board,child)
    for width in (.742453,.05):
        fr.ensure_endpoint_neckdown_rule(str(child),dict(group=fr.ENDPOINT_NECKDOWN_GROUP,
            tracks=1,min_width_mm=width))
        proof=receiving.receive(source,child,allow_endpoint_neckdown_additions=True)
        assert not proof['ok'] and 'candidate_rule_differs_from_exact_native_replay' in proof['errors'][0]


def test_native_additive_finalizer_and_receiver_share_the_same_complete_group_rule(tmp_path):
    import cec_additive_pair_repair as emitter
    source,child,uid,_=fixture(tmp_path);board=pcbnew.LoadBoard(str(child))
    old={force._uid(t) for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    next(t for t in board.GetTracks() if force._uid(t)==uid).SetWidth(742453)
    report=emitter.save_native_additions(child,board,{},old)
    assert report['native_complete_endpoint_group_rule']['min_width_mm']==.28
    assert receiving.receive(source,child,allow_endpoint_neckdown_additions=True)['ok']


def test_frozen_cover_member_cannot_grant_or_obstruct_track_only_rule_binding(tmp_path):
    source,child,uid,_=fixture(tmp_path,legacy_cover=True);board=pcbnew.LoadBoard(str(child))
    next(t for t in board.GetTracks() if force._uid(t)==uid).SetWidth(742453)
    receiving._ground_refill(board);field._save_field_snapshot(board,child)
    rule=receiving.bind_local_endpoint_rule(board,child)
    assert rule['min_width_mm']==.28
    proof=receiving.receive(source,child,allow_endpoint_neckdown_additions=True)
    assert proof['ok'] and proof['complete'],proof


@pytest.mark.parametrize('invalid_throat', [False, True])
def test_additive_stage_invokes_independent_endpoint_receiver_not_group_waiver(tmp_path, invalid_throat):
    import cec_additive_pair_repair as additive
    source, child, uid, throat_uid = fixture(tmp_path)
    if invalid_throat:
        board = pcbnew.LoadBoard(str(child))
        throat = next(t for t in board.GetTracks() if force._uid(t) == throat_uid)
        throat.SetStart(pcbnew.VECTOR2I_MM(23, 14))
        receiving._ground_refill(board)
        field._save_field_snapshot(board, child)
    proof = additive._invariant_worker(str(source), str(child))
    assert proof['ok'] is (not invalid_throat), proof
    assert proof['terms']['native_source_delta_replay'] is (not invalid_throat)
    assert proof['release_authority'] is False
