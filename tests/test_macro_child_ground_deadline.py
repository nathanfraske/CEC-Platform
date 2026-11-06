"""A ten-second compiler lease does not widen a9.7-second child lease."""
import math
import pytest
import cec_cell_macro_requests as compiler
from test_macro_compilation_leases import Clock


@pytest.mark.parametrize('remaining',[.01,1.,9.,9.7,9.9,10.])
def test_child_inherits_earlier_deadline_and_never_borrows(monkeypatch,remaining):
    clock=Clock();monkeypatch.setattr(compiler.time,'monotonic',clock)
    deadline=clock.now+remaining
    child=compiler._selected_cap_boundary_deadline(deadline)
    assert child==min(deadline,clock.now+9.7)
    assert child<=deadline and 0<child-clock.now<=9.7+1e-12
    clock.spend(remaining/2)
    assert compiler._selected_cap_boundary_deadline(child)<=child


@pytest.mark.parametrize('bad',[True,False,None,'10',math.inf,math.nan,-1.,0.,10.01])
def test_child_refuses_invalid_expired_or_extended_parent(monkeypatch,bad):
    clock=Clock();clock.now=0.;monkeypatch.setattr(compiler.time,'monotonic',clock)
    with pytest.raises(ValueError,match='bounded_inherited_ground_boundary_deadline'):
        compiler._selected_cap_boundary_deadline(bad)
