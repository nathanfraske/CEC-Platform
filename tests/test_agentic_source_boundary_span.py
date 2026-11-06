"""Explicit bounded native work reach; no ownership or electrical waiver."""
import pcbnew
import pytest
from cec_pipeline import cells, protocol
from cec_pipeline.workbench import Workbench
from test_agentic_annotation_cell_transport import operation
from test_source_reference_group_transport import external_fixture

FIELD = 'max_source_boundary_span_nm'


@pytest.mark.parametrize('value',[None,True,False,0,-1,32_000_001,8_000_000.,'12000000',[],{}])
def test_span_is_strict_bounded_int_before_native_source_work(value):
    op = dict(native_macro=True,**{FIELD:value})
    for call in (lambda:cells.compile_macro(None,op,'opaque'),
                 lambda:cells.construct(None,op,board_hint='opaque',request={}),
                 lambda:cells.receive_macro('unused','unused',op,{},'opaque'),
                 lambda:cells.preview('unused',op,'opaque')):
        with pytest.raises(ValueError,match='bounded_explicit_source_boundary_span'):
            call()


@pytest.mark.parametrize('native',[None,False,0,1,'true'])
def test_presence_is_rejected_outside_explicit_native_mode(native):
    op = {FIELD:8_000_000}
    if native is not None:op['native_macro']=native
    with pytest.raises(ValueError,match='source_boundary_span_requires_native_macro'):
        cells.source_boundary_span_option(op)
    with pytest.raises(ValueError,match='source_boundary_span_requires_native_macro'):
        cells.plan(None,op,'opaque')


@pytest.mark.parametrize('value',[None,1,12_000_000,32_000_000])
def test_native_compiler_forwards_default_or_exact_explicit_span(tmp_path,monkeypatch,value):
    import cec_cell_macro_requests as compiler
    source,_,group=external_fixture(tmp_path); board=pcbnew.LoadBoard(str(source))
    op=operation(group);op.update(native_macro=True,allow_locked_transport_uuids=[])
    if value is not None:op[FIELD]=value
    seen=[]
    class Reached(Exception):pass
    def spy(*a,**kwargs):seen.append(kwargs);raise Reached
    monkeypatch.setattr(compiler,'compile',spy)
    with pytest.raises(Reached):cells.compile_macro(board,op,'opaque')
    assert seen[0]['max_obstacle_track_mm']==(8_000_000 if value is None else value)/1e6
    assert seen[0]['allow_owned_locked_escapes'] is True
    assert seen[0]['timeout_s']==10.


@pytest.mark.parametrize('value',[None,12_000_000,32_000_000])
def test_saved_receiver_recompiles_then_forwards_identical_span(monkeypatch,value):
    import cec_complete_macro_cell as receiver
    op=dict(native_macro=True)
    if value is not None:op[FIELD]=value
    packet={'source_plan':{}};seen=[]
    monkeypatch.setattr(pcbnew,'LoadBoard',lambda path:object())
    def compile_spy(board,operation,hint):
        seen.append(cells.source_boundary_span_option(operation));return None,packet,[]
    monkeypatch.setattr(cells,'compile_macro',compile_spy)
    monkeypatch.setattr(receiver,'receive',lambda *a,**kwargs:seen.append(kwargs) or {'ok':True})
    record=dict(native_macro_packet_version=1,native_macro_packet=packet,transported_source_copper_uuids=[])
    assert cells.receive_macro('source','candidate',op,record,'opaque')['ok']
    expected=8_000_000 if value is None else value
    assert seen[0]==expected and seen[1]['max_obstacle_track_mm']==expected/1e6
    assert seen[1]['allow_owned_locked_escapes'] is True


def test_closed_schemas_expose_optional_span_only_in_native_variants():
    variants=[v for v in protocol._OPERATIONS if v['properties']['kind']['const']=='place_cell']
    assert len(variants)==4
    for variant in variants:
        if 'native_macro' in variant['properties']:
            assert variant['properties'][FIELD]==dict(type='integer',minimum=1,maximum=32_000_000,default=8_000_000)
            assert FIELD not in variant['required'] and variant['additionalProperties'] is False
        else:assert FIELD not in variant['properties']
    # Full native workbench preview remains intentionally unexposed until
    # its per-job watchdog has a separate explicit phase-runner integration.
    assert FIELD not in protocol.TOOL_PARAMETERS['plan_cell']


@pytest.mark.parametrize('kind,native,value,accepted',[
    ('place_cell',True,12_000_000,True),('place_cell',False,12_000_000,False),
    ('place_cell',True,True,False),('add_connections',True,12_000_000,False)])
def test_workbench_validates_span_before_queuing_any_job(monkeypatch,kind,native,value,accepted):
    workbench=object.__new__(Workbench);workbench.rows={'opaque':{}}
    monkeypatch.setattr(workbench,'_row',lambda board:{'sha256':'a'*64})
    class Queued(Exception):pass
    seen=[]
    def make_job(board,request):seen.append(request);raise Queued
    monkeypatch.setattr(workbench,'_make_job',make_job)
    op=dict(kind=kind,native_macro=native,**{FIELD:value})
    with pytest.raises(Queued if accepted else ValueError):
        workbench.stage('opaque','a'*64,'Explicit source-bound work reach only',[op])
    assert bool(seen) is accepted
