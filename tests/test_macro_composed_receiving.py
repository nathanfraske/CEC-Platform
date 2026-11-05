"""Every declared macro Source constituent is freshly received and counted."""
import pcbnew
import pytest
import cec_cell_macro_requests as compiler
import cec_complete_macro_cell as macro
import cec_field_coupling as field
import cec_force_current as force
from test_complete_macro_cell import saved_pair, fixture


def assert_composition(result):
    assert result['ok'] and result['complete'],result['errors']
    stages=result['bounded_composition']['constituents']
    expected=['source_compilation:'+p for p in compiler.COMPILATION_PHASES]
    expected+=['ground_source_compilation:'+p for p in compiler.COMPILATION_PHASES]
    expected+=['independent_ground_source_expectation']
    assert all(stages.count(stage)==1 for stage in expected)
    assert set(stages)==set(result['stage_timings_s'])
    assert all(0<=value<10 for value in result['stage_timings_s'].values())
    assert all(not result[k] for k in ('routing_admitted','fab_ready','release_authority','current_qualified'))


def test_saved_native_complete_macro_composes_all_source_and_ground_phases(tmp_path,monkeypatch):
    source,child,oldpacket=saved_pair(tmp_path,monkeypatch)
    paths=[source,child];before=[p.read_bytes()for p in paths]
    result=macro.receive(source,child,board_hint='opaque',compilation_phase_timeouts_s=[10,10,10])
    assert_composition(result)
    assert before==[p.read_bytes()for p in paths]


def test_new_packet_screen_and_saved_child_fresh_receive(tmp_path,monkeypatch):
    source,parent,private,oldpacket=fixture(tmp_path,monkeypatch)
    before=source.read_bytes()
    draft,packet=compiler.compile(source,oldpacket['source_plan']['poses'],board_hint='opaque',
        compilation_phase_timeouts_s=[10,10,10])
    proof=macro.screen(source,draft,packet,board_hint='opaque')
    assert proof['complete'],proof['errors']
    assert compiler.packet_options(packet)['compilation_phase_timeouts_s']==[10,10,10]
    macro.escape.construct_private(draft,proof['packet'],proof['selection'])
    macro.additive._ground_refill(draft)
    child=force._copy_family(source,tmp_path/'new-composed-child')
    macro.save_private(draft,child,packet)
    assert_composition(macro.receive(source,child,board_hint='opaque',
        compilation_phase_timeouts_s=[10,10,10]))
    assert source.read_bytes()==before


@pytest.mark.parametrize('budgets',[[1],[1,2,3,4,5],[True,1,1],[1,float('nan'),1],
    [1,1,11],[0,1,1]])
def test_invalid_phase_inputs_refuse_before_any_native_load(budgets):
    with pytest.raises(ValueError):macro.receive('missing-source','missing-child',board_hint='opaque',
        compilation_phase_timeouts_s=budgets)


def test_requested_constituents_cannot_exceed_receiver_limit():
    with pytest.raises(ValueError,match='exceed_receiving_limit'):
        macro.receive('missing-source','missing-child',board_hint='opaque',timeout_s=2,
            compilation_phase_timeouts_s=[2,3,2])


@pytest.mark.parametrize('fault',['child','source'])
def test_composition_does_not_waive_actual_source_or_child_damage(tmp_path,monkeypatch,fault):
    source,child,packet=saved_pair(tmp_path,monkeypatch)
    path=child if fault=='child' else source
    board=pcbnew.LoadBoard(str(path));owner=next(iter(board.GetFootprints()))
    if fault=='child':
        pad=next(iter(owner.Pads()));pad.SetNetCode(0)
    else:owner.SetField('MPN','unrecognized-changed-source')
    field._save_field_snapshot(board,path)
    result=macro.receive(source,child,board_hint='opaque',compilation_phase_timeouts_s=[10,10,10])
    assert not result['ok'] and not result['complete'] and result['errors']
