"""A frozen current field is physical authority, not a request for extra holes."""
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import pytest
import cec_fr


def fixture(offset=0, net='arbitrary-rail'):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    for name in (net, 'foreign'):
        board.Add(pcbnew.NETINFO_ITEM(board, name))
    polygon = [[offset+2, 2], [offset+24, 2], [offset+24, 24], [offset+2, 24]]
    pours = [dict(net=net, layer=layer, polygon=polygon) for layer in ('F.Cu', 'In3.Cu')]
    rows = [dict(net=net, x_mm=offset+x, y_mm=y) for x,y in ((8,8),(8,10),(10,8))]
    return board, pours, rows


def barrel(board, row, *, drill=.5, dia=.9, locked=True, net=None, blind=False):
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(row['x_mm']), pcbnew.FromMM(row['y_mm'])))
    via.SetDrill(pcbnew.FromMM(drill))
    via.SetWidth(pcbnew.FromMM(dia))
    via.SetNetCode(board.GetNetcodeFromNetname(net or row['net']))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.In1_Cu if blind else pcbnew.B_Cu)
    if blind:
        via.SetViaType(pcbnew.VIATYPE_BLIND)
    via.SetLocked(locked)
    board.Add(via)
    return via


def snapshot(board, path):
    # These negative fixtures deliberately contain shorts. SaveBoard rebuilds
    # connectivity and can merge their track/via net assignments before the
    # guard under test sees them. Use the native serializer, not that mutating
    # convenience loader/saver, for a point-in-time byte snapshot.
    before_nets = {item.m_Uuid.AsString(): item.GetNetname()
                   for item in board.GetTracks()}
    pcbnew.PCB_IO_MGR.Save(pcbnew.PCB_IO_MGR.KICAD_SEXP, str(path), board)
    assert {item.m_Uuid.AsString(): item.GetNetname()
            for item in board.GetTracks()} == before_nets
    return path.read_bytes()


@pytest.mark.parametrize('offset,net', [(0,'arbitrary-rail'), (71,'another supply')])
def test_repeated_native_replay_preserves_instances_and_geometry(tmp_path, offset, net):
    board,pours,rows = fixture(offset,net)
    first = cec_fr.add_overunder_vias(board, rows)
    assert len(first) == 3
    ids = {v.m_Uuid.AsString() for v in first}
    before = snapshot(board,tmp_path/'board.kicad_pcb')
    for _ in range(4):
        proposal, report = cec_fr.reseat_overunder_vias(board, rows, pours)
        assert report['ok'] and not report['changed'], report
        assert report['reused_existing'] == report['preserved'] == 3
        assert proposal == rows
        evidence = {}
        all_items = cec_fr.add_overunder_vias(board, proposal, include_reused=True, evidence=evidence)
        assert {v.m_Uuid.AsString() for v in all_items} == ids
        assert evidence['added'] == 0 and evidence['reused'] == evidence['materialized'] == 3
        assert cec_fr.add_overunder_vias(board, proposal) == []
        assert snapshot(board,tmp_path/'board.kicad_pcb') == before


@pytest.mark.parametrize('kwargs', [dict(drill=.4),dict(dia=1),dict(locked=False),dict(net='foreign'),dict(blind=True)])
def test_geometry_net_lock_and_span_mismatches_never_self_exempt(kwargs):
    board,pours,rows = fixture()
    barrel(board,rows[0],**kwargs)
    evidence = {}
    assert cec_fr.add_overunder_vias(board,[rows[0]],include_reused=True,evidence=evidence) == []
    assert evidence['reused'] == evidence['added'] == 0
    assert evidence['skipped_ledger'] == 1
    assert len(list(board.GetTracks())) == 1


@pytest.mark.parametrize('net', ['arbitrary-rail','foreign'])
@pytest.mark.parametrize('distance_mm', [.6, 1.0])
def test_reuse_does_not_exempt_a_distinct_adjacent_barrel(tmp_path,net,distance_mm):
    board,pours,rows = fixture()
    original = barrel(board,rows[0])
    adjacent = barrel(board,dict(rows[0],x_mm=8+distance_mm),net=net)
    assert original.GetNetname() == rows[0]['net'], 'fixture net changed before save'
    before = snapshot(board,tmp_path/'board.kicad_pcb')
    assert original.GetNetname() == rows[0]['net'], 'fixture net changed during save'
    assert adjacent.GetNetname() == net, 'adjacent fixture net changed during save'
    proposal,report = cec_fr.reseat_overunder_vias(board,[rows[0]],pours)
    assert not report['ok'] and report['reason'] == 'existing_frozen_via_conflict', {
        'report': report,
        'native_vias': [(v.m_Uuid.AsString(), v.GetNetname(), v.GetPosition().x,
                         v.GetPosition().y, v.GetWidth(pcbnew.F_Cu))
                        for v in board.GetTracks()],
    }
    assert report['conflicts'][0]['reason'] == 'via_ledger'
    assert report['conflicts'][0]['existing_uuid'] == original.m_Uuid.AsString()
    assert proposal == [rows[0]]
    assert cec_fr.add_overunder_vias(board,proposal,include_reused=True) == []
    assert snapshot(board,tmp_path/'board.kicad_pcb') == before


@pytest.mark.parametrize('layer', [pcbnew.F_Cu,pcbnew.In1_Cu,pcbnew.B_Cu])
def test_foreign_track_through_existing_authority_refuses_not_reseats(tmp_path,layer):
    board,pours,rows = fixture()
    barrel(board,rows[0])
    track = pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(6),pcbnew.FromMM(8)))
    track.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(10),pcbnew.FromMM(8)))
    track.SetWidth(pcbnew.FromMM(.2)); track.SetLayer(layer)
    track.SetNetCode(board.GetNetcodeFromNetname('foreign')); board.Add(track)
    proposal,report = cec_fr.reseat_overunder_vias(board,[rows[0]],pours)
    assert not report['ok'] and not report['changed']
    assert report['conflicts'][0]['reason'] == 'foreign_track'
    evidence = {}
    assert cec_fr.add_overunder_vias(board,proposal,include_reused=True,evidence=evidence) == []
    assert evidence['skipped_track'] == 1


def test_existing_barrel_outside_overlap_is_not_relocated():
    board,pours,rows = fixture()
    outside = dict(rows[0],x_mm=27)
    barrel(board,outside)
    proposal,report = cec_fr.reseat_overunder_vias(board,[outside],pours)
    assert not report['ok'] and not report['changed']
    assert report['conflicts'][0]['reason'] == 'outside_overlap'
    assert proposal == [outside]


@pytest.mark.parametrize('cut_layer', ['F.Cu', 'In3.Cu'])
def test_empty_hole_is_not_accepted_as_a_same_net_landing(cut_layer):
    board, pours, rows = fixture()
    barrel(board, rows[0])
    for pour in pours:
        if pour['layer'] == cut_layer:
            pour['holes'] = [[[6, 6], [10, 6], [10, 10], [6, 10]]]
    proposal, report = cec_fr.reseat_overunder_vias(board, [rows[0]], pours)
    assert not report['ok'] and not report['changed']
    assert report['conflicts'][0]['reason'] == 'outside_overlap'
    assert proposal == [rows[0]]


@pytest.mark.parametrize('already_present', [False, True])
def test_explicit_field_split_by_copper_geometry_preserves_each_legal_island(already_present):
    board,_,rows=fixture()
    pours=[dict(net=rows[0]['net'],layer=layer,polygon=polygon)
           for layer in ('F.Cu','In3.Cu') for polygon in
           ([[2,2],[14,2],[14,24],[2,24]], [[20,2],[24,2],[24,24],[20,24]])]
    rows=[dict(row,field_index=7,field_kind='layer_transition') for row in rows]
    rows[-1]=dict(rows[-1],x_mm=22,y_mm=8)
    if already_present:
        for row in rows: barrel(board,row)
    proposed,report=cec_fr.reseat_overunder_vias(board,rows,pours)
    assert report['ok'],report
    assert report['preserved']==3 and report['reseated']==0,report
    assert not report['changed'] and proposed==rows


def test_explicit_field_cannot_escape_foreign_copper_by_jumping_to_other_island():
    board,_,rows=fixture()
    pours=[dict(net=rows[0]['net'],layer=layer,polygon=polygon)
           for layer in ('F.Cu','In3.Cu') for polygon in
           ([[2,2],[14,2],[14,24],[2,24]], [[20,2],[24,2],[24,24],[20,24]])]
    rows=[dict(rows[0],field_index=7,field_kind='layer_transition'),
          dict(rows[0],x_mm=22,field_index=7,field_kind='layer_transition')]
    track=pcbnew.PCB_TRACK(board)
    track.SetStart(pcbnew.VECTOR2I_MM(22,0));track.SetEnd(pcbnew.VECTOR2I_MM(22,26))
    track.SetWidth(pcbnew.FromMM(5));track.SetLayer(pcbnew.In2_Cu)
    track.SetNetCode(board.GetNetcodeFromNetname('foreign'));board.Add(track)
    proposed,report=cec_fr.reseat_overunder_vias(board,rows,pours)
    assert not report['ok'] and not report['changed']
    assert report['reason']=='replacement_lattice_exhausted'
    assert proposed==rows


@pytest.mark.parametrize('already_present',[True,False])
def test_duplicate_requests_fail_instead_of_creating_a_second_field(already_present):
    board,pours,rows = fixture()
    if already_present:
        barrel(board,rows[0])
    duplicates = [rows[0],rows[0]]
    _,report = cec_fr.reseat_overunder_vias(board,duplicates,pours)
    assert not report['ok'] and report['reason'] == 'duplicate_requested_frozen_via'
    evidence = {}
    assert len(cec_fr.add_overunder_vias(board,duplicates,include_reused=True,evidence=evidence)) == 1
    assert evidence['skipped_duplicate'] == 1
    assert len(list(board.GetTracks())) == 1


def test_ambiguous_existing_instances_fail_closed():
    board,pours,rows = fixture()
    barrel(board,rows[0]); barrel(board,rows[0])
    _,report = cec_fr.reseat_overunder_vias(board,[rows[0]],pours)
    assert not report['ok'] and report['reason'] == 'ambiguous_existing_frozen_via'
    with pytest.raises(ValueError,match='ambiguous existing frozen via'):
        cec_fr.add_overunder_vias(board,[rows[0]],include_reused=True)


def test_mixed_new_and_existing_members_report_separate_counts():
    board,pours,rows = fixture()
    first = barrel(board,rows[0])
    evidence = {}
    result = cec_fr.add_overunder_vias(board,rows,include_reused=True,evidence=evidence)
    assert len(result) == 3
    assert evidence['added'] == 2 and evidence['reused'] == 1
    assert evidence['reused_uuids'] == [first.m_Uuid.AsString()]
    assert len(list(board.GetTracks())) == 3


def test_frozen_pipeline_boundary_counts_reused_not_only_added(tmp_path,monkeypatch):
    """The producer must not reject an exact replay just because nothing is new."""
    import cec_constraints
    import cec_slab_pour
    import cec_synth_pipeline as synth
    board,pours,rows = fixture()
    cec_fr.add_overunder_vias(board,rows)
    cec_fr.add_power_pours(board,pours)
    original_ids = {t.m_Uuid.AsString() for t in board.GetTracks()}
    source = tmp_path/'source.kicad_pcb'
    snapshot(board,source)
    state = dict(placement_scope='complete',frozen_nets=['arbitrary-rail'],
                 pours=pours,vias=rows,corridors=pours,placements={})
    monkeypatch.setenv('CEC_POURFIRST_STATE',str(tmp_path/'authority.json'))
    monkeypatch.setattr(cec_fr,'_pourfirst_state',lambda:state)
    monkeypatch.setattr(cec_constraints,'foreign_on_pour_summary',
                        lambda p:dict(status='ok',n_tracks=0,n_vias=0))
    monkeypatch.setattr(synth,'_synthesize_priority_power_local_pin_access',lambda *a:{})
    monkeypatch.setattr(cec_slab_pour,'cleanup_floating_zones',lambda *a:0)
    admissions = []
    def gate(path,nets,baseline):
        current = pcbnew.LoadBoard(str(path))
        admissions.append({t.m_Uuid.AsString() for t in current.GetTracks()})
        return dict(passed=True,open_after=[],exact_after={})
    monkeypatch.setattr(synth,'_admit_priority_power_candidate_isolated',gate)
    original = source.read_bytes()
    for index in range(2):
        target = tmp_path/f'candidate-{index}.kicad_pcb'
        result = synth._compile_post_priority_power_state(
            str(source),pours,str(target.with_suffix('.json')),str(target))
        assert result['frozen_via_materialization']['added'] == 0
        assert result['frozen_via_materialization']['reused'] == 3
        assert result['frozen_via_reseat']['reused_existing'] == 3
        assert admissions[-1] == original_ids
        if index == 0:
            assert source.read_bytes() == original
        source = target
