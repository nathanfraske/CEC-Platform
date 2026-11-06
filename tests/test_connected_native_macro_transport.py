"""Constructor wiring/AST ownership only; synthetic compiler is not admission."""
import copy
from pathlib import Path
import shutil

import pcbnew
import pytest
import cec_additive_route_receiving as syntax
import cec_cell_escape_replan as escape
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as macro
import cec_field_coupling as field
import cec_force_current as force
from cec_pipeline import cells, construction, protocol


def fixture_context(tmp_path,monkeypatch,mode):
    board=pcbnew.BOARD()
    fp=pcbnew.FOOTPRINT(board);fp.SetReference('SYNTHETIC');board.Add(fp)
    board.Add(pcbnew.NETINFO_ITEM(board,'GND'))
    ids=[]
    for x in (10,20):
        via=pcbnew.PCB_VIA(board);via.SetPosition(pcbnew.VECTOR2I_MM(x,10))
        via.SetWidth(600000);via.SetDrill(300000);via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu)
        via.SetNet(board.FindNet('GND'));board.Add(via);ids.append(via.m_Uuid.AsString())
    source=tmp_path/'source.kicad_pcb';field._save_field_snapshot(board,source)
    candidate=tmp_path/'candidate.kicad_pcb';shutil.copyfile(source,candidate)
    op=dict(kind='place_cell',poses=[dict(reference='SYNTHETIC',at_nm=[1,1],rotation_deg=0)],
            routes=[],vias=[],allow_locked_footprint_uuids=[],allow_locked_track_uuids=[],native_macro=mode)
    if mode is True:op['allow_locked_transport_uuids']=[]
    proposal=dict(scope='synthetic-test-only',poses={'SYNTHETIC':[.000001,.000001,0]},retired_track_uuids=[])
    monkeypatch.setattr(cells,'plan',lambda *a:(copy.deepcopy(proposal),{'SYNTHETIC'}))
    monkeypatch.setattr(cells,'emit_connections',lambda *a,**k:[])
    monkeypatch.setattr(escape,'apply_private',lambda *a:None)
    monkeypatch.setattr(syntax,'_ground_refill',lambda *a:None)
    monkeypatch.setattr(macro,'_reference_requests',lambda *a:[])
    monkeypatch.setattr(force,'_sidecars',lambda *a:{})
    packet=dict(schema=1,scope='source_typed_complete_native_macro_requests',
                source_plan=proposal,retired_track_uuids=[],requests={},
                transport={'source_process_barrel_motion':[{'uuid':ids[0]}]})
    def compile(*a,**kw):
        child=pcbnew.LoadBoard(str(source))
        next(t for t in child.GetTracks()if t.m_Uuid.AsString()==ids[0]).SetPosition(pcbnew.VECTOR2I_MM(11,10))
        return child,copy.deepcopy(packet)
    monkeypatch.setattr(compiler,'compile',compile)
    # No real moving footprint is needed to exercise native barrel merge.
    actual_construct=cells.construct
    def construct(*a,**kw):
        r=actual_construct(*a,**kw);r['affected_footprint_uuids']=[];return r
    monkeypatch.setattr(cells,'construct',construct)
    return source,candidate,op,ids


@pytest.mark.parametrize('mode',[False,True])
def test_explicit_compiler_transport_survives_saved_merge_old_mode_stays_fixed(tmp_path,monkeypatch,mode):
    source,candidate,op,ids=fixture_context(tmp_path,monkeypatch,mode)
    raw=source.read_bytes();_,old=syntax._nodes(source)
    r=construction._construct_connected(source,candidate,{'operations':[op]},'synthetic')
    _,new=syntax._nodes(candidate)
    assert new[ids[1]]==old[ids[1]]
    child=pcbnew.LoadBoard(str(candidate))
    via=next(t for t in child.GetTracks()if t.m_Uuid.AsString()==ids[0])
    assert via.GetPosition().x==(11000000 if mode else 10000000)
    assert (ids[0] in r['affected_native_uuids'])==mode
    assert source.read_bytes()==raw
    if mode:
        assert r['changes'][0]['native_macro_packet_version']==1
        assert r['changes'][0]['transported_source_copper_uuids']==[ids[0]]
        assert '_native_board' not in r['changes'][0]


def test_merge_invariant_rejects_silently_discarded_native_delta(tmp_path,monkeypatch):
    source,candidate,op,ids=fixture_context(tmp_path,monkeypatch,True)
    before=candidate.read_bytes()
    original=cells.construct
    def omit(*a,**kw):
        r=original(*a,**kw);r['transported_source_copper_uuids']=[];return r
    monkeypatch.setattr(cells,'construct',omit)
    with pytest.raises(ValueError,match='AST_merge_discarded'):
        construction._construct_connected(source,candidate,{'operations':[op]},'synthetic')
    assert candidate.read_bytes()==before


def test_boolean_mode_not_coerced(tmp_path,monkeypatch):
    source,candidate,op,ids=fixture_context(tmp_path,monkeypatch,1)
    with pytest.raises(ValueError,match='boolean'):
        construction._construct_connected(source,candidate,{'operations':[op]},'synthetic')


def test_compiler_unowned_source_delta_is_rejected(tmp_path,monkeypatch):
    source,candidate,op,ids=fixture_context(tmp_path,monkeypatch,True)
    original=compiler.compile
    def corrupt(*a,**kw):
        board,packet=original(*a,**kw)
        next(t for t in board.GetTracks()if t.m_Uuid.AsString()==ids[1]).Move(pcbnew.VECTOR2I(1,0))
        return board,packet
    monkeypatch.setattr(compiler,'compile',corrupt)
    with pytest.raises(ValueError,match='unowned_source'):
        construction._construct_connected(source,candidate,{'operations':[op]},'synthetic')


def test_saved_packet_tamper_cannot_reach_independent_receiver(tmp_path,monkeypatch):
    source,candidate,op,ids=fixture_context(tmp_path,monkeypatch,True)
    r=construction._construct_connected(source,candidate,{'operations':[op]},'synthetic')
    called=[]
    monkeypatch.setattr(macro,'receive',lambda *a,**k:called.append(True)or {'synthetic_dispatch_only':True})
    assert cells.receive_macro(source,candidate,op,r['changes'][0],'synthetic')['synthetic_dispatch_only']
    assert called==[True]
    r['changes'][0]['native_macro_packet']['transport']['source_process_barrel_motion']=[]
    with pytest.raises(ValueError,match='fresh_exact'):
        cells.receive_macro(source,candidate,op,r['changes'][0],'synthetic')
    assert called==[True]


def test_old_protocol_contract_and_explicit_closed_opt_in_are_distinct():
    variants=[v for v in protocol._OPERATIONS if v['properties']['kind']['const']=='place_cell']
    assert len(variants)==2
    old,new=variants
    assert 'native_macro' not in old['properties']
    assert new['required']==[*old['required'],'native_macro','allow_locked_transport_uuids']
    assert new['properties']['native_macro']=={'type':'boolean','const':True}
    assert old['additionalProperties'] is new['additionalProperties'] is False


def test_locked_transport_needs_exact_consent_no_extra_source_owner(tmp_path,monkeypatch):
    source,candidate,op,ids=fixture_context(tmp_path,monkeypatch,True)
    board=pcbnew.LoadBoard(str(source))
    next(t for t in board.GetTracks()if t.m_Uuid.AsString()==ids[0]).SetLocked(True)
    field._save_field_snapshot(board,source)
    with pytest.raises(ValueError,match='transport_not_explicitly'):
        cells.compile_macro(pcbnew.LoadBoard(str(source)),op,'synthetic')
    op['allow_locked_transport_uuids']=[ids[0]]
    assert cells.compile_macro(pcbnew.LoadBoard(str(source)),op,'synthetic')[2]==[ids[0]]
    op['allow_locked_transport_uuids']=[ids[0],ids[1]]
    with pytest.raises(ValueError,match='exact_native_macro_transport_lock_scope'):
        cells.compile_macro(pcbnew.LoadBoard(str(source)),op,'synthetic')


def test_observation_and_consented_replay_use_identical_compiler_authority(tmp_path,monkeypatch):
    source,candidate,op,ids=fixture_context(tmp_path,monkeypatch,True)
    original=compiler.compile;flags=[]
    def observed(*a,**kw):
        flags.append(kw['allow_owned_locked_escapes'])
        return original(*a,**kw)
    monkeypatch.setattr(compiler,'compile',observed)
    _,first,_=cells.compile_macro(pcbnew.LoadBoard(str(source)),op,'synthetic',enforce_locks=False)
    op['allow_locked_transport_uuids']=[ids[0]]
    _,second,_=cells.compile_macro(pcbnew.LoadBoard(str(source)),op,'synthetic')
    assert first==second and flags==[True,True]


@pytest.mark.parametrize('mode', [False, True])
@pytest.mark.parametrize('has_group', [False, True])
def test_native_macro_emits_exact_saved_member_rule_as_independent_replay(
        tmp_path, monkeypatch, mode, has_group):
    import cec_fr as fr
    source, candidate, op, ids = fixture_context(tmp_path, monkeypatch, mode)
    if has_group:
        board = pcbnew.LoadBoard(str(source))
        group = pcbnew.PCB_GROUP(board); group.SetName(fr.ENDPOINT_NECKDOWN_GROUP); board.Add(group)
        for x, width in ((30, 200000), (40, 350000)):
            track = pcbnew.PCB_TRACK(board); track.SetNet(board.FindNet('GND'))
            track.SetStart(pcbnew.VECTOR2I_MM(x, 10)); track.SetEnd(pcbnew.VECTOR2I_MM(x + 1, 10))
            track.SetWidth(width); track.SetLayer(pcbnew.F_Cu); board.Add(track); group.AddItem(track)
        field._save_field_snapshot(board, source); shutil.copyfile(source, candidate)
    original_rule = '(version 1)\n# unrelated source rule preserved byte for byte\n'
    source.with_suffix('.kicad_dru').write_text(original_rule)
    candidate.with_suffix('.kicad_dru').write_text(original_rule)
    original_board = source.read_bytes()
    result = construction._construct_connected(source, candidate, {'operations': [op]}, 'synthetic')
    actual = candidate.with_suffix('.kicad_dru').read_bytes()
    replay = tmp_path / 'independent.kicad_pcb'
    shutil.copyfile(candidate, replay); replay.with_suffix('.kicad_dru').write_text(original_rule)
    syntax.bind_local_endpoint_rule(pcbnew.LoadBoard(str(replay)), replay)
    if mode:
        assert actual == replay.with_suffix('.kicad_dru').read_bytes()
        rule = result['changes'][0]['native_macro_endpoint_rule']
        assert rule['applicable'] == has_group
        if has_group:
            assert rule['min_width_mm'] == .2
            assert b"A.Type == 'Track' && A.memberOfGroup('" in actual
            assert b'(constraint track_width (min 0.200mm))' in actual
    else:
        assert actual == original_rule.encode()
        assert 'native_macro_endpoint_rule' not in result['changes'][0]
    assert source.read_bytes() == original_board
    assert source.with_suffix('.kicad_dru').read_text() == original_rule
