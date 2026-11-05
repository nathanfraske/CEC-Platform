import pytest
import cec_search_budget as budget
import cec_decoupler_cell as cell


@pytest.mark.parametrize('limit', [0, -1, 1.5, True, 1000001])
def test_invalid_work_limit(limit):
    with pytest.raises(ValueError):
        with budget.scoped(limit):
            pass


def test_identical_work_under_different_clock_speeds(monkeypatch):
    reports = []
    for step in (0.001, 0.25):
        clock = iter(i * step for i in range(10))
        monkeypatch.setattr(budget.time, 'monotonic', lambda: next(clock))
        with budget.scoped(4) as run:
            assert [budget.exhausted(10.) for _ in range(6)] == [False] * 4 + [True] * 2
        reports.append(run.report())
    assert reports[0] == reports[1]
    assert reports[0]['stop_reason'] == 'work_limit'
    assert reports[0]['exhaustion_is_no_path_proof'] is False


def test_wall_guard_remains_an_explicit_cancellation(monkeypatch):
    monkeypatch.setattr(budget.time, 'monotonic', lambda: 20.)
    with budget.scoped(100) as run:
        assert budget.exhausted(10.)
    assert run.used == 0 and run.stop_reason == 'wall_deadline'
    assert budget.exhausted(10.) and not budget.exhausted(30.)


def test_nested_searches_cannot_reset_parent_budget():
    with budget.scoped(2) as outer:
        assert not budget.exhausted()
        with budget.scoped(10) as inner:
            assert not budget.exhausted()
            assert budget.exhausted()
        assert outer.used == 2 and inner.used == 1
        assert budget.exhausted()
    assert not budget.exhausted()


def test_exception_restores_search_scope():
    with pytest.raises(RuntimeError):
        with budget.scoped(1):
            assert not budget.exhausted()
            raise RuntimeError('native failure')
    assert not budget.exhausted()


def test_stop_poll_does_not_spend_work_and_scope_restores():
    assert budget.stop_status() is None
    with budget.scoped(2) as run:
        assert budget.stop_status() is None and run.used==0
        assert not budget.exhausted()
        assert budget.stop_status() is None and run.used==1
        assert not budget.exhausted()
        status=budget.stop_status()
        assert status['budgets'][0]['stop_reason']=='work_limit'
        assert not status['exhaustion_is_no_path_proof']
        assert budget.stop_status()==status and run.used==2
    assert budget.stop_status() is None


def test_inner_stop_does_not_poison_still_funded_outer_scope():
    with budget.scoped(5) as outer:
        with budget.scoped(1):
            assert not budget.exhausted()
            assert budget.stop_status() is not None
        assert outer.used==1 and budget.stop_status() is None


def test_native_lastmile_stops_work_exhaustion_without_false_no_path(tmp_path):
    import cec_fr
    import pcbnew
    from test_bridge_new_hole_pair import fixture
    path,*_=fixture(tmp_path,spacing=5)
    board=pcbnew.LoadBoard(str(path))
    with budget.scoped(1) as work:
        report=cec_fr.synthesize_lastmile(board,max_mm=80,cap=24,attempts_per_pair=16,
            prefer_bridge=True,wall_timeout_s=10,per_net_timeout_s=None)
    assert work.stop_reason=='work_limit'
    assert report['search_budget_exhausted'] and not report['timed_out']
    assert report['search_budget_detail']['exhaustion_is_no_path_proof'] is False
    assert report['refused']<=1 and report['closed']==0
    assert all(row['reason']=='bounded_pair_search_budget_exhausted' for row in report['refused_details'])


@pytest.mark.parametrize('diagnostics', [None, {}])
def test_local_constructor_labels_work_exhaustion_unproved(monkeypatch, diagnostics):
    def solve(*args, **kwargs):
        for _ in range(5):
            if budget.exhausted():
                return None, 'no guarded path'
        raise AssertionError('work limit bypassed')
    monkeypatch.setattr(cell, '_add_supply_link_impl', solve)
    result, error = cell._add_supply_link(None, None, None, lock=True,
        search_work_limit=3, diagnostics=diagnostics)
    assert result is None and 'budget exhausted' in error
    if diagnostics is not None:
        assert diagnostics['conclusion'] == 'search_budget_exhausted'
        assert diagnostics['search']['work_used'] == 3


def test_local_constructor_records_proved_result_work_without_weakening_it(monkeypatch):
    def solve(*args, **kwargs):
        assert not budget.exhausted()
        return {'status': 'native-guarded', 'items': []}, None
    monkeypatch.setattr(cell, '_add_supply_link_impl', solve)
    result, error = cell._add_supply_link(None, None, None, lock=True)
    assert error is None and result['status'] == 'native-guarded'
    assert result['search_work']['work_used'] == 1
    assert not result['search_work']['budget_exhausted']


@pytest.mark.parametrize('rail,expected', [(False,4096),(True,262144)])
def test_role_defaults_fund_completion_not_local_cell_probes(monkeypatch, rail, expected):
    def solve(*args, **kwargs):
        assert not budget.exhausted()
        return {'status':'same-native-guards','items':[]}, None
    monkeypatch.setattr(cell, '_add_supply_link_impl', solve)
    result,error = cell._add_supply_link(None,None,None,lock=True,rail_completion=rail)
    assert error is None and result['search_work']['work_limit'] == expected


def test_explicit_work_limit_and_outer_lease_override_larger_role_default(monkeypatch):
    def solve(*args, **kwargs):
        while not budget.exhausted():
            pass
        return None, 'no guarded local supply path within locality bound'
    monkeypatch.setattr(cell, '_add_supply_link_impl', solve)
    diagnostic={}
    result,error=cell._add_supply_link(None,None,None,lock=True,rail_completion=True,
        search_work_limit=7,diagnostics=diagnostic)
    assert result is None and diagnostic['search']['work_limit']==7
    assert diagnostic['search']['work_used']==7
    with budget.scoped(1) as outer:
        diagnostic={}
        result,error=cell._add_supply_link(None,None,None,lock=True,
            rail_completion=True,diagnostics=diagnostic)
        assert result is None and outer.used==1 and outer.stop_reason=='work_limit'
        assert len(diagnostic['search']['tiers'])==1


def test_funded_rail_role_can_visit_beyond_old_local_budget_without_new_rules(monkeypatch):
    calls=[]
    def solve(*args, **kwargs):
        calls.append(kwargs)
        for _ in range(88085):
            if budget.exhausted(kwargs['deadline_monotonic']):
                return None, 'no guarded local supply path within locality bound'
        return {'status':'guarded-native-channel','items':[]},None
    monkeypatch.setattr(cell, '_add_supply_link_impl', solve)
    result,error=cell._add_supply_link(None,None,None,lock=True,rail_completion=True)
    assert error is None and result['search_work']['work_used']==88085
    assert len(calls)==1 and calls[0]['rail_completion'] is True
    assert result['search_tiers'][0]['tier']=='native-channels'
    assert result['search_work']['exhaustion_is_no_path_proof'] is False


def test_supply_maze_gets_reserved_work_after_native_channels_plateau(monkeypatch):
    modes = []
    def solve(*args, **kwargs):
        modes.append(kwargs['allow_maze'])
        if not kwargs['allow_maze']:
            while not budget.exhausted():
                pass
            return None, 'local supply search budget exhausted without a path'
        assert not budget.exhausted()
        return {'status': 'native-guarded-fallback', 'items': []}, None
    monkeypatch.setattr(cell, '_add_supply_link_impl', solve)
    result, error = cell._add_supply_link(None, None, None, lock=True, search_work_limit=8)
    assert error is None and modes == [False, True]
    assert result['search_work']['work_used'] == 5
    assert not result['search_work']['budget_exhausted']
    assert [tier['work_used'] for tier in result['search_tiers']] == [4,1]
    assert result['search_tiers'][0]['tier_work']['stop_reason'] == 'work_limit'
    assert budget.stop_status() is None


def test_supply_tiers_cannot_reset_the_shared_total_budget(monkeypatch):
    modes = []
    def solve(*args, **kwargs):
        modes.append(kwargs['allow_maze'])
        while not budget.exhausted():
            pass
        return None, 'no guarded local supply path within locality bound'
    monkeypatch.setattr(cell, '_add_supply_link_impl', solve)
    diagnostic = {}
    result,error = cell._add_supply_link(None,None,None,lock=True,
        search_work_limit=7,diagnostics=diagnostic)
    assert result is None and 'budget exhausted' in error
    assert modes == [False,True]
    assert diagnostic['search']['work_used'] == 7
    assert [tier['work_used'] for tier in diagnostic['search']['tiers']] == [3,4]
    assert diagnostic['search']['exhaustion_is_no_path_proof'] is False
    assert budget.stop_status() is None


def test_supply_fallback_honors_an_already_funded_callers_stop(monkeypatch):
    def solve(*args, **kwargs):
        assert not budget.exhausted()
        return None, 'no guarded local supply path within locality bound'
    monkeypatch.setattr(cell, '_add_supply_link_impl', solve)
    diagnostic = {}
    with budget.scoped(1) as outer:
        result,error = cell._add_supply_link(None,None,None,lock=True,
            search_work_limit=8,diagnostics=diagnostic)
        assert result is None and 'budget exhausted' in error
        assert outer.used == 1 and outer.stop_reason == 'work_limit'
        assert len(diagnostic['search']['tiers']) == 1
    assert budget.stop_status() is None


def test_supply_fallback_does_not_continue_after_fatal_geometry_refusal(monkeypatch):
    calls = []
    def solve(*args, **kwargs):
        calls.append(kwargs['allow_maze'])
        return None, 'owner/cap rail mismatch'
    monkeypatch.setattr(cell, '_add_supply_link_impl', solve)
    result,error = cell._add_supply_link(None,None,None,lock=True,search_work_limit=8)
    assert result is None and error == 'owner/cap rail mismatch'
    assert calls == [False] and budget.stop_status() is None


def test_supply_shared_wall_guard_is_not_reset_for_fallback(monkeypatch):
    calls = []
    def solve(*args, **kwargs):
        calls.append(kwargs['allow_maze'])
        monkeypatch.setattr(budget.time,'monotonic',lambda: kwargs['deadline_monotonic']+1)
        assert budget.exhausted(kwargs['deadline_monotonic'])
        return None, 'no guarded local supply path within locality bound'
    monkeypatch.setattr(cell, '_add_supply_link_impl', solve)
    diagnostic = {}
    result,error = cell._add_supply_link(None,None,None,lock=True,
        search_work_limit=8,diagnostics=diagnostic)
    assert result is None and 'budget exhausted' in error and calls == [False]
    assert diagnostic['search']['stop_reason'] == 'wall_deadline'
    assert diagnostic['search']['work_used'] == 0
    assert budget.stop_status() is None
