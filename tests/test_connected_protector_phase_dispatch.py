"""Dispatch semantics only; mocked physical receivers confer no admission."""
from pathlib import Path
import pytest
import root_receive_connected_protector_transaction_20261027 as combined

base=combined.base

def row(kind,**extra):
    return dict(kind=kind,candidate='/unused/saved.kicad_pcb',candidate_sha256='a'*64,**extra)

def connected(n=9,net='/synthetic/control'):
    return row(combined.connected_phase.KIND,net=net,
        retired_track_uuids=[str(i)for i in range(n)],allow_locked_track_uuids=[])

def legacy(n=8,net='/synthetic/other'):
    return dict(connected(n,net),kind='ordinary_source_reflow')

def protector():return row(combined.protector_phase.KIND,proposal='/unused/exact-proposal.json')

def functions():
    return base.validate_phases,base.receive_phase,base.annotation_dependencies

def test_four_phase_schema_and_both_exact_kinds_preserve_base_bytes():
    before=Path(base.__file__).read_bytes();original=functions();kinds=base.KINDS
    with combined.installed():
        base.validate_phases([connected(),legacy(),protector(),row('print_context',proposal='print.json')])
        assert base.KINDS is kinds
        deps=base.annotation_dependencies()
        assert str(Path(combined.__file__).resolve())in deps
        assert str(Path(combined.connected_phase.__file__).resolve())in deps
        assert str(Path(combined.protector_phase.__file__).resolve())in deps
    assert functions()==original and base.KINDS is kinds
    assert Path(base.__file__).read_bytes()==before

@pytest.mark.parametrize('phases',[
    [legacy(9)],[connected(17)],
    [connected(),legacy(net='/synthetic/control')],
    [legacy(net='/synthetic/control'),connected()],
    [protector(),protector()],
    [row('print_context',proposal='p'),connected()],
])
def test_caps_collision_second_protector_and_print_order_refuse(phases):
    with combined.installed(),pytest.raises(ValueError):base.validate_phases(phases)

@pytest.mark.parametrize('kind',['connected','protector'])
@pytest.mark.parametrize('field',['timeout_s','width_nm','callback','received','allow_unknown'])
def test_prototype_authority_fields_never_enter_schema(kind,field):
    value=connected()if kind=='connected'else protector();value[field]=True
    with combined.installed(),pytest.raises(ValueError):base.validate_phases([value])

@pytest.mark.parametrize('kind',['connected','protector'])
@pytest.mark.parametrize('proof',[{},dict(ok=False,complete=True),dict(ok=True,complete=False),
    dict(ok=1,complete=True)])
def test_dispatch_cannot_accept_incomplete_physical_receiver(monkeypatch,tmp_path,kind,proof):
    # These mocks test dispatcher booleans ONLY, never physical scope.
    child=tmp_path/'child';child.write_bytes(b'synthetic dispatch identity')
    value=connected()if kind=='connected'else protector();value['candidate']=str(child)
    if kind=='connected':
        monkeypatch.setattr(combined.connected_phase,'receive_phase',lambda *a,**k:proof)
    else:monkeypatch.setattr(combined.protector_phase,'receive_phase',lambda *a,**k:proof)
    with combined.installed(),pytest.raises(ValueError):
        base.receive_phase('original','parent',value,'synthetic')

@pytest.mark.parametrize('kind',['connected','protector'])
def test_complete_dispatch_semantics_and_no_other_gate_replacement(monkeypatch,tmp_path,kind):
    child=tmp_path/'child';child.write_bytes(b'not a physical PCB')
    value=connected()if kind=='connected'else protector();value['candidate']=str(child)
    proof=dict(ok=True,complete=True,dispatch_only_mock=True)
    module=combined.connected_phase if kind=='connected'else combined.protector_phase
    monkeypatch.setattr(module,'receive_phase',lambda *a,**k:proof)
    original=dict(vars(base));permitted={'validate_phases','receive_phase','annotation_dependencies'}
    with combined.installed():
        result=base.receive_phase('original','parent',value,'synthetic')
        assert result==(child.resolve(),proof)
        for name,value in original.items():
            if callable(value)and name not in permitted:assert getattr(base,name)is value

def test_nested_exception_cleanup_restores_exact_captured_dispatchers():
    original=functions();kinds=base.KINDS
    with combined.installed():
        outer=functions()
        with pytest.raises(RuntimeError):
            with combined.installed():
                assert functions()!=outer
                base.validate_phases([connected(),protector()])
                raise RuntimeError('synthetic interruption')
        assert functions()==outer and base.KINDS is kinds
    assert functions()==original and base.KINDS is kinds

def test_captures_current_prior_composition_not_import_time_functions(monkeypatch):
    original=functions();calls=[]
    def validate(p):calls.append('validate');return original[0](p)
    def receive(*a,**k):calls.append('receive');return 'unchanged legacy result'
    def deps():calls.append('dependencies');return {'synthetic-prior-layer':'exact'}
    monkeypatch.setattr(base,'validate_phases',validate)
    monkeypatch.setattr(base,'receive_phase',receive)
    monkeypatch.setattr(base,'annotation_dependencies',deps)
    captured=functions()
    with combined.installed():
        base.validate_phases([legacy()])
        assert base.receive_phase('a','b',legacy(),'synthetic')=='unchanged legacy result'
        assert base.annotation_dependencies()['synthetic-prior-layer']=='exact'
    assert functions()==captured
    assert set(calls)=={'validate','receive','dependencies'}
