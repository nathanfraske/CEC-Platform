"""Unknown native contact evidence rejects an offer without killing the menu."""
import pytest
import cec_field_coupling as field
import cec_kelvin_copper_cut as cut
import cec_measurement_terminal_route as route
from test_measurement_terminal_route import fixture


@pytest.mark.parametrize('reason', ['copper_cut_deadline_exhausted','unsupported_contact_geometry'])
def test_exact_native_unknown_cannot_fund_a_path_or_escape_the_bounded_menu(monkeypatch, reason):
    board, demand, root, pickup = fixture()
    before = field._field_snapshot_inventory(board)
    original = route.contact_guard
    def guarded(*a, **kw):
        result = original(*a, **kw)
        def unknown(*args): raise cut.Unknown(reason)
        result['clear'] = unknown
        return result
    monkeypatch.setattr(route, 'contact_guard', guarded)
    monkeypatch.setattr(route.fr, '_guarded_profiled_lastmile_legs', lambda *a, **k: None)
    menu = route.menus(board, demand, width_nm=200000, timeout_s=1., max_choices=1)
    assert menu['ops'] == [] and menu['same_net_contact_unknown_refusals']
    assert set(menu['same_net_contact_unknown_refusals']) == {reason}
    assert len(menu['same_net_contact_unknown_refusals']) <= 8
    assert menu['source_unchanged'] is True and menu['no_path_proof'] is False
    assert menu['retirement_authority'] is menu['current_authority'] is menu['release_authority'] is False
    assert before == field._field_snapshot_inventory(board)


def test_arbitrary_programming_error_is_not_relabelled_as_native_unknown(monkeypatch):
    board, demand, root, pickup = fixture()
    original = route.contact_guard
    def guarded(*a, **kw):
        result = original(*a, **kw)
        def broken(*args): raise RuntimeError('programming-defect')
        result['clear'] = broken
        return result
    monkeypatch.setattr(route, 'contact_guard', guarded)
    with pytest.raises(RuntimeError, match='programming-defect'):
        route.menus(board, demand, width_nm=200000, timeout_s=1., max_choices=1)
