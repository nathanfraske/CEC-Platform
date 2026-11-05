from pathlib import Path
import pytest
import cec_suite_annotation_transition as op


@pytest.mark.parametrize('selected',op.KINDS)
def test_each_declared_scope_is_freshly_dispatched_with_its_exact_parent(monkeypatch,selected):
    import cec_print_context_transition as original
    import cec_chained_annotation_transition as chained
    import cec_received_private_stage as stage
    import cec_component_metadata_transition as component
    declaration=dict(source=dict(path='/exact-origin'),steps=[dict(candidate=dict(path='/exact-selected'))])
    row={selected:declaration,'assembly_instance':{'matched':True}}
    seen=[]
    monkeypatch.setattr(stage,'matched_instance',lambda value,path:(value,str(path)))
    monkeypatch.setattr(chained,'validate',lambda *a:([Path('/exact-origin'),Path('/exact-selected'),Path('/child')],[]))
    def receive(*a,**kw):seen.append((a,kw));return dict(ok=True,complete=True)
    def wrong(*a,**kw):raise AssertionError('wrong annotation receiver')
    monkeypatch.setattr(original,'receive_row',receive if selected=='print_context_transition'else wrong)
    monkeypatch.setattr(chained,'receive_print_row',receive if selected=='replayed_print_context_transition'else wrong)
    monkeypatch.setattr(chained,'receive',receive if selected=='annotation_transition'else wrong)
    monkeypatch.setattr(component,'receive',receive if selected=='component_internal_transition'else wrong)
    result=op.receive_row('/child',row,board_hint='renamed',timeout_s=5.)
    assert result['ok']and result['suite_annotation_transition_kind']==selected
    args,kwargs=seen[0]
    assert args==((Path('/exact-selected'),'/child',declaration)if selected=='annotation_transition'else('/child',declaration))
    instance=({'matched':True}if selected=='component_internal_transition'else({'matched':True},
        '/exact-selected'if selected=='annotation_transition'else'/exact-origin'))
    assert kwargs==dict(board_hint='renamed',timeout_s=5.,assembly_instance=instance)
    # Every call is a new receiver invocation, never a retained success cache.
    op.receive_row('/child',row,board_hint='renamed',timeout_s=5.);assert len(seen)==2


def test_ambiguous_provenance_and_context_spoofing_cannot_choose_a_receiver():
    assert op.receive_row('/unused',{},board_hint='none')is None
    for first in op.KINDS:
        for second in op.KINDS:
            if first!=second:
                with pytest.raises(ValueError,match='ambiguous'):
                    op.receive_row('/unused',{first:{},second:{}},board_hint='none')


@pytest.mark.parametrize('selected',op.KINDS)
def test_timing_replay_remains_typed(monkeypatch,selected):
    import cec_print_context_transition as original
    import cec_chained_annotation_transition as chained
    import cec_component_metadata_transition as component
    seen=[]
    def compare(a,b):seen.append((a,b));return a==b
    target=(component,'same_replay')if selected=='component_internal_transition'else(
        (original,'same_replay')if selected=='print_context_transition'else(
        (chained,'same_print_replay')if selected=='replayed_print_context_transition'else(chained,'same_replay'))
    )
    monkeypatch.setattr(*target,compare)
    a=dict(ok=True,complete=True,suite_annotation_transition_kind=selected)
    assert op.same_replay(a,dict(a))and len(seen)==1
    assert seen[0]==(dict(ok=True,complete=True),dict(ok=True,complete=True))
    assert not op.same_replay(a,dict(a,suite_annotation_transition_kind='untyped-context'))
