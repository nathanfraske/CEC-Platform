"""Observability must not change the bridge portfolio or imply release."""
import pcbnew
import pytest
import cec_fr as fr


@pytest.mark.parametrize('failure', ['barrel', 'stub', 'middle', 'none'])
def test_reports_actual_failure_stage_without_changing_plan(monkeypatch, failure):
    board = pcbnew.CreateEmptyBoard()
    board.SetCopperLayerCount(6)
    start, end = (5_000_000, 5_000_000), (15_000_000, 5_000_000)
    calls = []

    def barrel(_board, at, *args, **kwargs):
        calls.append(('barrel', at.x, at.y))
        clear = failure != 'barrel' and (at.x, at.y) not in (start, end)
        if not clear and kwargs.get('refusal_counts') is not None:
            counts = kwargs['refusal_counts']
            counts.setdefault('fixture refusal', {'count': 0, 'layers': {}})['count'] += 1
        return clear

    def stub(_board, a, b, width, layer, *args, **kwargs):
        calls.append(('stub', a.x, a.y, b.x, b.y, kwargs['allow_maze']))
        return None if failure == 'stub' else [(a, b, width)]

    def middle(_board, a, b, *args, **kwargs):
        calls.append(('middle', a.x, a.y, b.x, b.y))
        return [(a, b)] if failure == 'none' else None

    monkeypatch.setattr(fr, '_via_spot_clear', barrel)
    monkeypatch.setattr(fr, '_guarded_profiled_lastmile_legs', stub)
    monkeypatch.setattr(fr, '_guarded_lastmile_legs', middle)
    monkeypatch.setattr(fr, '_multilayer_maze_lastmile_ops', lambda *a, **kw: None)

    def run(diagnostics=None):
        return fr._lastmile_bridge(board, start, {pcbnew.F_Cu}, end, {pcbnew.F_Cu},
            200_000, 1, [pcbnew.In2_Cu, pcbnew.B_Cu], 200_000,
            seat_limit=1, seat_offsets_mm=(.5, 1.), seat_angles_deg=(0, 90),
            allow_maze=True, allow_lattice=False, leg_ok=lambda *a: True,
            diagnostics=diagnostics)

    plain = run()
    original_calls = list(calls)
    calls.clear()
    details = {}
    observed = run(details)
    assert calls == original_calls
    assert bool(plain) == bool(observed) == (failure == 'none')
    if plain:
        def native_ops(ops):
            return [[tuple(value) if isinstance(value, pcbnew.VECTOR2I) else value
                     for value in op] for op in ops]
        assert native_ops(plain) == native_ops(observed)
    assert not details['release_authority'] and not details['no_path_proof']
    assert len(details['endpoints']) == 2  # cached, not duplicated per layer
    # Each native layer has a canonical-breadth and an interleaved-depth
    # record. This is not a duplicate endpoint inventory or an extra layer.
    assert len(details['layers']) <= 4
    assert len({(row['layer'],row['search_tier']) for row in details['layers']})==len(details['layers'])
    assert not list(board.GetTracks())
    for endpoint in details['endpoints']:
        stats = endpoint['counters']
        if failure == 'barrel':
            assert stats['via_guard_refusals'] == 4
            assert stats.get('legal_via_trials', 0) == 0 and endpoint['seats'] == 0
            assert endpoint['via_refusal_causes']['canonical']['fixture refusal']['count'] == 4
        elif failure == 'stub':
            assert stats['canonical_stub_refusals'] == stats['maze_stub_refusals'] == 4
            assert stats['legal_via_trials'] == 8 and endpoint['seats'] == 0
        else:
            assert stats['canonical_stub_seats'] == endpoint['seats'] == 1
    if failure == 'middle':
        assert details['counters']['single_layer_middle_refusals'] == 4
        assert details['counters']['multilayer_middle_refusals'] == 1
    if failure == 'none':
        assert details['counters']['completed_paths'] == 1


def test_deadline_does_not_become_no_path_proof():
    board = pcbnew.CreateEmptyBoard()
    details = {}
    assert fr._lastmile_bridge(board, (0,0), {pcbnew.F_Cu}, (1,1), {pcbnew.F_Cu},
        200_000, 1, [pcbnew.B_Cu], 200_000, deadline_monotonic=0,
        diagnostics=details) is None
    assert details['endpoints'] == details['layers'] == []
    assert not details['no_path_proof'] and not details['release_authority']


def test_bridge_refines_only_deferred_local_stubs_with_same_finite_deadline(monkeypatch):
    import time
    board=pcbnew.BOARD();board.SetCopperLayerCount(6)
    start,end=(5000000,5000000),(15000000,5000000)
    deadline=time.monotonic()+2.;seen=[]
    monkeypatch.setattr(fr,'_via_spot_clear',lambda _b,at,*a,**kw:tuple(at) not in (start,end))
    def stub(_board,a,b,width,layer,*args,**kw):
        seen.append(kw)
        return [(a,b,width)] if kw['refine_maze'] else None
    monkeypatch.setattr(fr,'_guarded_profiled_lastmile_legs',stub)
    monkeypatch.setattr(fr,'_guarded_lastmile_legs',lambda _b,a,b,*args,**kw:[(a,b)])
    monkeypatch.setattr(fr,'_multilayer_maze_lastmile_ops',lambda *a,**kw:None)
    result=fr._lastmile_bridge(board,start,{pcbnew.F_Cu},end,{pcbnew.F_Cu},200000,1,
        [pcbnew.B_Cu],200000,seat_limit=1,seat_offsets_mm=(.5,),seat_angles_deg=(0,),
        allow_maze=True,allow_lattice=False,leg_ok=lambda *a:True,
        deadline_monotonic=deadline,refine_stubs=True)
    assert result and any(kw['refine_maze'] for kw in seen)
    assert all(not kw['refine_maze'] or kw['allow_maze'] for kw in seen)
    assert all(kw['deadline_monotonic']==deadline for kw in seen)


@pytest.mark.parametrize('mode,deadline', [(True,None),(1,1.),(True,float('inf'))])
def test_bridge_stub_refinement_requires_explicit_bounded_mode(mode,deadline):
    board=pcbnew.BOARD()
    with pytest.raises(ValueError,match='bounded_explicit_bridge_stub_refinement_required'):
        fr._lastmile_bridge(board,(0,0),{pcbnew.F_Cu},(1,1),{pcbnew.F_Cu},200000,1,
            [pcbnew.B_Cu],200000,refine_stubs=mode,deadline_monotonic=deadline)


@pytest.mark.parametrize('layer', [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu])
def test_native_histogram_preserves_refusal_without_detailed_snapshot(monkeypatch, layer):
    from test_local_bridge_dogbones import fixture
    board, pad, nc, _ = fixture()
    track = pcbnew.PCB_TRACK(board)
    track.SetNet(board.FindNet('/OTHER'))
    track.SetStart(pcbnew.VECTOR2I_MM(31, 39))
    track.SetEnd(pcbnew.VECTOR2I_MM(31, 41))
    track.SetWidth(pcbnew.FromMM(.2)); track.SetLayer(layer); board.Add(track)
    def check(at, **kwargs):
        return fr._via_spot_clear(board, pcbnew.VECTOR2I_MM(*at),
            pcbnew.FromMM(.6), pcbnew.FromMM(.2), {nc},
            drill_nm=pcbnew.FromMM(.3), net_code=nc, foreign_cache={}, **kwargs)
    report = {}
    assert not check((31, 40), report=report)
    assert report['reason'] == 'foreign copper excludes via land'
    assert report['layer'] == board.GetLayerName(layer)
    def no_detailed_scan(*_args, **_kwargs):
        pytest.fail('Aggregate diagnostics must not build identified blocker snapshots')
    monkeypatch.setattr(fr, '_identified_foreign_shape_indexes', no_detailed_scan)
    monkeypatch.setattr(fr, '_snapshot_foreign_blockers', no_detailed_scan)
    counts = {}
    for _ in range(3):
        assert not check((31, 40), refusal_counts=counts)
    assert counts == {report['reason']: {'count': 3, 'layers': {report['layer']: 3}}}
    assert check((33, 40), refusal_counts=counts)
    assert counts[report['reason']]['count'] == 3
    assert len(list(board.GetTracks())) == 1
    assert pad.GetPosition() == pcbnew.VECTOR2I_MM(30, 40)


def test_native_pad_and_pour_reasons_stay_distinct(monkeypatch):
    from test_local_bridge_dogbones import fixture
    board, pad, nc, _ = fixture(profile=False)
    counts = {}
    def check(at):
        return fr._via_spot_clear(board, pcbnew.VECTOR2I_MM(*at),
            pcbnew.FromMM(.6), pcbnew.FromMM(.2), {nc},
            drill_nm=pcbnew.FromMM(.3), net_code=nc, refusal_counts=counts)
    assert not check((30, 40))  # no profile-qualified in-pad barrel
    monkeypatch.setattr(fr, '_guarded_power_reservations', lambda: [{
        'net': '/OTHER', 'layer': 'In2.Cu', 'x0': 31, 'x1': 32, 'y0': 39, 'y1': 41}])
    assert not check((31.5, 40))
    assert counts == {
        'pad or hole excludes via land': {'count': 1, 'layers': {}},
        'foreign pour-first reservation excludes via land': {
            'count': 1, 'layers': {'In2.Cu': 1}},
    }
    assert not list(board.GetTracks())


def test_native_same_net_hole_is_counted_without_copper_exemption():
    from test_local_bridge_dogbones import fixture
    board, pad, nc, _ = fixture()
    via = pcbnew.PCB_VIA(board); via.SetNetCode(nc)
    via.SetPosition(pcbnew.VECTOR2I_MM(31, 40)); via.SetWidth(pcbnew.FromMM(.6))
    via.SetDrill(pcbnew.FromMM(.3)); via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetViaType(pcbnew.VIATYPE_THROUGH); board.Add(via)
    counts = {}
    assert not fr._via_spot_clear(board, via.GetPosition(), pcbnew.FromMM(.6),
        pcbnew.FromMM(.2), {nc}, drill_nm=pcbnew.FromMM(.3), net_code=nc,
        refusal_counts=counts)
    assert counts == {'existing via occupies drill origin': {'count': 1, 'layers': {}}}
    assert len(list(board.GetTracks())) == 1
