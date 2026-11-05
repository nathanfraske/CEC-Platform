from unittest import mock
import pcbnew as pcb
import pytest
import cec_ground_plane as ground
import cec_precision_route as route
import cec_return_plane_preview as preview
from test_pair_return_field_cache import board_fixture


def via(board, net, point, diameter=.6):
    item=pcb.PCB_VIA(board);item.SetViaType(pcb.VIATYPE_THROUGH)
    item.SetLayerPair(pcb.F_Cu,pcb.B_Cu);item.SetPosition(pcb.VECTOR2I_MM(*point))
    item.SetWidth(pcb.FromMM(diameter));item.SetDrill(pcb.FromMM(.3))
    item.SetNet(board.FindNet(net));board.Add(item)
    return item


def test_native_preview_contact_rejects_antipad_and_never_mutates_source(tmp_path):
    board=board_fixture()
    props=board.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    via(board,'GND',(3,3));via(board,'FOREIGN',(10,10),1.8)
    path=tmp_path/'arbitrary.kicad_pcb';pcb.SaveBoard(str(path),board)
    board.SetFileName(str(path));before=path.read_bytes()
    zones=ground._zone_declaration_signature(board);tracks=ground._track_signature(board)
    accepts,evidence=preview.compile_contact_filter(board)
    assert evidence['applicable'] and evidence['final_native_refill_required']
    assert set(evidence['layers'])=={'In1.Cu','In4.Cu'}
    assert accepts((8,8),.6) and not accepts((10,10),.6)
    assert board.GetFileName()==str(path) and path.read_bytes()==before
    assert ground._zone_declaration_signature(board)==zones
    assert ground._track_signature(board)==tracks


def test_legacy_profile_keeps_existing_behavior():
    board=board_fixture()
    accepts,evidence=preview.compile_contact_filter(board)
    assert accepts is None and not evidence['applicable']


def test_failed_preview_cannot_claim_reference_contact():
    board=board_fixture();props=board.GetProperties()
    props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    via(board,'GND',(3,3))
    with mock.patch.object(ground,'fill_board',return_value={'ok':False,'reasons':['synthetic refusal']}):
        with pytest.raises(ValueError,match='reference preview refused'):
            preview.compile_contact_filter(board)
    assert not list(board.Zones())


def test_nearby_unconnected_return_does_not_count_as_covered():
    board=board_fixture();old=via(board,'GND',(10,10.9))
    added,status=route._add_pair_transition_returns(board,(10,10),(1,0),
        signal_points=((10,10),),reference_contact=lambda p,d:p[1]<10)
    assert status=='added' and len(added)==1
    assert added[0].GetPosition().y < pcb.FromMM(10)
    assert old in list(board.GetTracks())


def test_no_reference_candidate_fails_without_emitting_copper():
    board=board_fixture()
    added,status=route._add_pair_transition_returns(board,(10,10),(1,0),
        reference_contact=lambda p,d:False)
    assert not added and status.startswith('no legal GND return via')
    assert not list(board.GetTracks())


def test_transition_generator_uses_one_preview_per_transaction_and_cleans_up():
    board=board_fixture()
    @preview.with_candidate_reference
    def transaction(board, expected='added'):
        added,status=route._add_pair_transition_returns(board,(10,10),(1,0))
        again,status_again=route._add_pair_transition_returns(board,(10,10),(1,0))
        assert status==expected and status_again=='covered' and not again
        assert all(item.GetPosition().y < pcb.FromMM(10) for item in added)
        return dict(ok=True)
    with mock.patch.object(preview,'compile_contact_filter',return_value=(
            lambda p,d:p[1]<10,dict(applicable=True,scope='candidate-filter-only'))) as compile:
        result=transaction(board)
        assert compile.call_count==1
        assert result['return_reference_preview']['applicable']
        transaction(board,expected='covered')
        assert compile.call_count==2  # never inherit a prior board snapshot
    assert preview.candidate_contact_filter(board) is None


def test_preview_exception_fails_closed_and_restores_nested_context():
    board=board_fixture()
    @preview.with_candidate_reference
    def inner(board):
        route._add_pair_transition_returns(board,(10,10),(1,0))
    @preview.with_candidate_reference
    def outer(board):
        saved=preview.candidate_contact_filter(board)
        with mock.patch.object(preview,'compile_contact_filter',side_effect=ValueError('native failure')):
            with pytest.raises(ValueError,match='native failure'):
                inner(board)
        assert preview.candidate_contact_filter(board) is saved
        return {}
    outer(board)
    assert preview.candidate_contact_filter(board) is None
    assert not list(board.GetTracks())


def test_unused_preview_is_lazy():
    @preview.with_candidate_reference
    def transaction(board):
        return dict(ok=True)
    with mock.patch.object(preview,'compile_contact_filter') as compile:
        assert transaction(board_fixture())==dict(ok=True)
        compile.assert_not_called()


@pytest.mark.parametrize('quarter',range(4))
def test_floating_signal_barrel_over_old_ground_fill_keeps_authored_net_and_antipad(tmp_path,quarter):
    import cec_fr
    board=board_fixture();props=board.GetProperties()
    props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    via(board,'GND',(3,3))
    # Author the old filled source first; the signal transition is new and
    # deliberately has no trace yet, as in a transactional portal search.
    assert ground.fill_board(board)['ok']
    path=tmp_path/'source.kicad_pcb';pcb.SaveBoard(str(path),board)
    board.SetFileName(str(path));source_bytes=path.read_bytes()
    def xy(point):
        x,y=point
        for _ in range(quarter):x,y=-y,x
        return (10+x,10+y)
    signal=via(board,'FOREIGN',xy((0,0)),.6)
    authored=preview._authorship(board);at=pcb.VECTOR2I_MM(*xy((.7,0)))
    def seat():
        return cec_fr._via_spot_clear(board,at,600000,200000,
            {board.GetNetcodeFromNetname('GND')},drill_nm=300000,
            net_code=board.GetNetcodeFromNetname('GND'))
    assert not seat()
    accepts,evidence=preview.compile_contact_filter(board)
    assert preview._authorship(board)==authored
    assert signal.GetNetname()=='FOREIGN' and not seat()
    assert not accepts(xy((0,0)),.2)  # do not hide the signal via's real antipad
    assert evidence['live_board_net_authorship_unchanged']
    assert evidence['preview_authorship_received_after_refill']
    assert evidence['authored_net_restorations']>=1
    assert board.GetFileName()==str(path) and path.read_bytes()==source_bytes


def test_private_authorship_replay_rejects_missing_or_wrong_primitive():
    board=board_fixture();item=via(board,'GND',(3,3));authored=preview._authorship(board)
    missing=dict(authored);missing['unknown-native-uuid']=('PCB_VIA','GND',1)
    with pytest.raises(ValueError,match='primitive identities'):
        preview._restore_preview_authorship(board,missing)
    wrong=dict(authored);wrong[item.m_Uuid.AsString()]=('PAD','GND',1)
    with pytest.raises(ValueError,match='primitive identities'):
        preview._restore_preview_authorship(board,wrong)


def test_native_preview_writer_exception_still_leaves_live_authorship_unchanged():
    board=board_fixture();props=board.GetProperties()
    props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(props)
    via(board,'FOREIGN',(10,10));authored=preview._authorship(board)
    with mock.patch.object(pcb.PCB_IO_KICAD_SEXPR,'SaveBoard',side_effect=ValueError('synthetic writer failure')):
        with pytest.raises(ValueError,match='synthetic writer failure'):
            preview.compile_contact_filter(board)
    assert preview._authorship(board)==authored
