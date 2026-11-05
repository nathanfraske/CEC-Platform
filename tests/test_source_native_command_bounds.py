"""Suite intake/parity may compose stages, never run a 120/300-s native CLI."""
import ast
from pathlib import Path
import subprocess

import pytest
import cec_beta_electrical_audit as audit
import cec_constraints as constraints


@pytest.mark.parametrize('module,expected',[(audit,1),(constraints,3)])
def test_source_native_subprocesses_have_literal_ten_second_bound(module,expected):
    tree=ast.parse(Path(module.__file__).read_text());calls=[]
    # Checker workers compose several independent native stages; this test
    # concerns the actual CLI invocations, not their outer process lease.
    worker_calls={n.lineno for f in tree.body if isinstance(f,ast.FunctionDef)and f.name=='_run_checker_process'
        for n in ast.walk(f)if isinstance(n,ast.Call)}
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call)or not isinstance(node.func,ast.Attribute):continue
        if not isinstance(node.func.value,ast.Name)or node.func.value.id!='subprocess' or node.func.attr!='run':continue
        if node.lineno in worker_calls:continue
        timeout=next((k.value for k in node.keywords if k.arg=='timeout'),None)
        if isinstance(timeout,ast.BinOp):
            # Parity's one original ten-second lease now also includes the
            # immutable hierarchy snapshot/parser; CLI gets only its remainder.
            assert module is constraints
            assert ast.unparse(timeout)=='deadline - time.monotonic()'
            owner=next(f for f in tree.body if isinstance(f,ast.FunctionDef)
                       and any(n is node for n in ast.walk(f)))
            assert owner.name=='_schematic_component_signatures'
            assert any(isinstance(n,ast.Assign)and ast.unparse(n)=='deadline = time.monotonic() + 10.0'
                       for n in ast.walk(owner))
        else:
            assert isinstance(timeout,ast.Constant)and type(timeout.value)in(int,float)
            assert 0<timeout.value<=10
        calls.append(node)
    assert len(calls)==expected


@pytest.mark.parametrize('kind',['audit_export','parity_export','drc','erc'])
def test_native_timeout_remains_unknown_not_success_or_empty_report(monkeypatch,tmp_path,kind):
    monkeypatch.setattr(audit.cec_toolchain,'require_kicad_cli',lambda *_:'native-cli')
    monkeypatch.setattr(constraints.cec_toolchain,'kicad_cli',lambda:'native-cli')
    def blocked(command,**kwargs):
        assert 0<kwargs['timeout']<=10
        raise subprocess.TimeoutExpired(command,kwargs['timeout'])
    monkeypatch.setattr(subprocess,'run',blocked)
    source=tmp_path/'source.kicad_sch';source.write_text('(kicad_sch)')
    action={'audit_export':lambda:audit.export_netlist('unopened.kicad_sch'),
        'parity_export':lambda:constraints._schematic_component_signatures(str(source),{},{}),
        'drc':lambda:constraints._drc_json('unopened.kicad_pcb',{}),
        'erc':lambda:constraints._erc_errors('unopened.kicad_sch')}[kind]
    with pytest.raises(subprocess.TimeoutExpired):action()
