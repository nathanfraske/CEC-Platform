import json
from pathlib import Path
import pytest
from PIL import Image
import cec_pass_review as review


@pytest.mark.parametrize('status', ['blocked_or_failed', 'failed', 'coordinator_error', 'resource_refused'])
def test_failure_without_admission_result_is_still_labelled_blocked(status):
    assert review.status_label({'status':status}) == 'BLOCKED'


def test_nested_native_budget_failure_is_not_generic_review_only():
    result={'status':'blocked_or_failed','stages':{'placement':{
        'execution_status':'failed','admission_ok':None,
        'failure_evidence':{'status':'operation_budget_exhausted'}}}}
    assert review.status_label(result) == 'BUDGET EXHAUSTED'
    result['engine_unchanged']=False
    assert review.status_label(result) == 'INVALID PROVENANCE'


def test_successful_process_without_release_stays_review_only():
    assert review.status_label({'status':'completed'}) == 'REVIEW ONLY'


def staged(tmp_path, board='synthetic'):
    target = tmp_path / 'cohort' / board
    path = target / '02-placement' / 'board.kicad_pcb'
    path.parent.mkdir(parents=True)
    path.write_text('current pass CAD')
    entry = {'status': 'complete', 'result': {'board': str(path), 'ok': False},
             'artifacts': [{'path': str(path), 'sha256': review.sha(path)}]}
    state = {'board': board, 'stages': {'placement': entry}}
    (target / 'pipeline-state.json').write_text(json.dumps(state))
    return target, path, state


def fake_render(board, output, **kwargs):
    assert kwargs['no_bodies'] is True
    assert kwargs['timeout'] <= 60
    Image.new('RGB', (700, 300), 'green').save(output)
    return output


def fake_inventory(board):
    import cec_dashboard
    return cec_dashboard.COPPER_PLOTS


def fake_plot(board, output, **kwargs):
    assert kwargs['timeout'] == 10
    Path(output).write_text('<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0 L1 1"/></svg>')
    return str(output)


PLOT_ARGS = dict(plot_inventory=fake_inventory, plotter=fake_plot)


def test_parent_counts_cannot_be_published_as_current_native_measurements(tmp_path):
    target, path, _ = staged(tmp_path)
    before = path.read_bytes()
    def measure(snapshot):
        return dict(source_board_sha256=review.sha(snapshot), unconnected=0,
            power_contours=dict(complete=True, finding_count=36))
    out = review.publish(target, 'synthetic',
        {'status':'blocked_or_failed','unconnected':7,'drc':0,
         'power_contour_review_findings':38}, archive_root=tmp_path/'a',
        renderer=fake_render, geometry_measurer=measure, **PLOT_ARGS)
    assert out['label']=='BLOCKED / COUNT MISMATCH'
    assert out['measured_counts']=={'unconnected':0,'drc':0,'power_contour_review_findings':36}
    assert out['count_mismatches']=={
        'unconnected':{'campaign_reported':7,'native_snapshot':0},
        'power_contour_review_findings':{'campaign_reported':38,'native_snapshot':36}}
    assert out['campaign_result']['power_contour_review_findings']==38
    assert out['counts_source']['drc']=='campaign-report-not-independent-preview-measurement'
    assert out['counts_source']['power_contour_review_findings']=='hash-bound-native-saved-board'
    assert path.read_bytes()==before and not out['release_authority']


@pytest.mark.parametrize('failure',['stale_hash','incomplete'])
def test_unavailable_native_geometry_does_not_claim_a_clean_contour_count(tmp_path, failure):
    target, path, _ = staged(tmp_path)
    def measure(snapshot):
        return dict(source_board_sha256='0'*64 if failure=='stale_hash' else review.sha(snapshot),
            unconnected=0, power_contours=dict(complete=False,finding_count=0))
    out = review.publish(target,'synthetic',{'status':'blocked_or_failed'},
        archive_root=tmp_path/'a',renderer=fake_render,geometry_measurer=measure,**PLOT_ARGS)
    assert 'power_contour_review_findings' not in out['measured_counts']
    assert out.get('native_geometry_error') or out.get('native_geometry_unknown')
    assert not out['release_authority']


def test_publish_blocked_output_is_hashed_immutable_unqualified_and_serializable(tmp_path):
    target, path, state = staged(tmp_path)
    path.with_suffix('.new-authority.json').write_text('{}')
    result = {'status': 'blocked_or_failed', 'stages': {'placement': {'admission_ok': False}}}
    out = review.publish(target, 'synthetic', result, archive_root=tmp_path/'archive',
                         renderer=fake_render, mirror=tmp_path/'desktop', **PLOT_ARGS)
    result['review'] = out
    json.dumps(result)  # publisher must not create a circular result reference
    assert out['label'] == 'BLOCKED'
    assert out['output_sha256'] == review.sha(path)
    assert out['journal_hash_verified'] is True
    assert out['release_authority'] is False
    summary = json.loads(Path(out['summary']).read_text())
    assert summary['gates']['ok'] is False and summary['thermal']['ok'] is False
    assert summary['lineage']['archive_role'] == 'diagnostic'
    assert len(summary['panels']) == 8
    assert out['native_copper_plots_complete'] is True
    assert len(out['native_copper_plots']) == 6
    for metadata in out['native_copper_plots'].values():
        assert metadata['source_board_sha256'] == review.sha(path)
        assert metadata['sha256'] == review.sha(Path(out['summary']).parent / metadata['file'])
        assert metadata['source'] == 'native-saved-board-copper-only'
    assert out['plots_do_not_grant_admission'] is True
    assert (Path(out['summary']).parent/'board.new-authority.json').exists()
    assert (tmp_path/'desktop/synthetic/render.png').exists()
    assert (tmp_path/'desktop/synthetic/plot-in4.svg').exists()
    with pytest.raises(FileExistsError):
        review.publish(target, 'synthetic', result, archive_root=tmp_path/'archive', renderer=fake_render)


@pytest.mark.parametrize('failure', ['changed', 'missing', 'external', 'unjournaled-route'])
def test_invalid_output_never_falls_back_to_older_placement(tmp_path, failure):
    target, path, state = staged(tmp_path)
    entry = state['stages']['placement']
    if failure == 'changed': path.write_text('changed after journal commit')
    elif failure == 'missing': path.unlink()
    elif failure == 'external': entry['result']['board'] = str(tmp_path/'old-board.kicad_pcb')
    else: state['stages']['precision_detailed_route'] = {'status': 'timed_out'}
    with pytest.raises(ValueError): review.select_output(target, state)


def test_missing_output_gets_explicit_card_not_canonical_board(tmp_path):
    target = tmp_path/'pass'/'synthetic'
    target.mkdir(parents=True)
    out = review.publish(target, 'synthetic', {'status':'blocked_or_failed'}, archive_root=tmp_path/'a')
    assert out['output_sha256'] is None and out['stage'] == 'no-output'
    assert Path(out['panels']['render']).exists()
    assert not (Path(out['summary']).parent/'board.kicad_pcb').exists()


def test_interrupted_placement_is_not_presented_as_completed_or_routed(tmp_path):
    target, path, state = staged(tmp_path)
    state['stages']['placement'] = {'status': 'timed_out'}
    selected, stage, verified = review.select_output(target, state)
    assert selected == path and stage == 'partial-placement' and not verified


@pytest.mark.parametrize('failure',['none','changed','missing','external'])
def test_native_preflight_child_beats_old_placement_without_fallback(tmp_path,failure):
    target,parent,state=staged(tmp_path)
    child=target/'03-preflight'/'native'/'board.kicad_pcb'
    child.parent.mkdir(parents=True);child.write_text('new hash-bound native prefix')
    state['stages']['route_preflight']=dict(status='complete',result=dict(board=str(child)),
        artifacts=[dict(path=str(child),sha256=review.sha(child))])
    if failure=='changed':child.write_text('changed after proof')
    if failure=='missing':child.unlink()
    if failure=='external':state['stages']['route_preflight']['result']['board']=str(tmp_path/'other.kicad_pcb')
    if failure=='none':
        selected,stage,verified=review.select_output(target,state)
        assert selected==child and stage=='route_preflight' and verified
    else:
        with pytest.raises(ValueError):review.select_output(target,state)


def test_board_identity_mismatch_refuses_publication(tmp_path):
    target, path, state = staged(tmp_path)
    with pytest.raises(ValueError, match='identity'):
        review.publish(target, 'wrong-board', {}, archive_root=tmp_path/'a')


def test_gallery_keeps_queued_boards_and_completed_outputs(tmp_path):
    target, path, state = staged(tmp_path)
    completed = {'status':'blocked_or_failed'}
    completed['review'] = review.publish(target, 'synthetic', completed,
                                archive_root=tmp_path/'a', renderer=fake_render, **PLOT_ARGS)
    report = {'boards': {'synthetic': completed, 'other-family': {'status':'queued'}}}
    gallery = review.gallery(report, tmp_path/'all.png', mirror=tmp_path/'desktop')
    assert Path(gallery).exists()
    assert Path(gallery).name != 'all.png'
    assert (tmp_path/'desktop'/Path(gallery).name).exists()
    assert (tmp_path/'desktop/all.png').exists()
    assert set(json.loads((tmp_path/'desktop/suite.json').read_text())['boards']) == set(report['boards'])
    original = Path(gallery).read_bytes()
    report['boards']['other-family']['status'] = 'budget_exhausted'
    changed = review.gallery(report, tmp_path/'all.png')
    assert changed != gallery
    assert Path(gallery).read_bytes() == original
    assert review.gallery(report, tmp_path/'all.png') == changed


def test_render_failure_is_visible_without_changing_board(tmp_path):
    target, path, state = staged(tmp_path)
    out = review.publish(target, 'synthetic', {}, archive_root=tmp_path/'a',
                         renderer=lambda *a, **kw: None)
    assert len(out['render_errors']) == 2
    assert out['output_sha256'] == review.sha(path)
    assert Path(out['panels']['render']).exists()


@pytest.mark.parametrize('copper_count', [2, 4, 6])
def test_native_plot_inventory_uses_actual_enabled_stack(tmp_path, copper_count):
    pcbnew = pytest.importorskip('pcbnew')
    import cec_swig_guard
    cec_swig_guard.pin()
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(copper_count)
    board.SetLayerName(pcbnew.F_Cu, 'CUSTOM_FRONT')
    path = tmp_path / 'layer-inventory.kicad_pcb'
    pcbnew.SaveBoard(str(path), board)
    actual = review.native_plot_inventory(path)
    assert len(actual) == copper_count
    assert actual[0][0] == 'plotf' and actual[-1][0] == 'plotb'
    assert [layers.split(',')[0] for _, _, layers in actual] == (
        ['F.Cu'] + ['In%d.Cu' % i for i in range(1, copper_count - 1)] + ['B.Cu'])


@pytest.mark.parametrize('failure', ['exception', 'missing', 'invalid-svg'])
def test_failed_native_layer_never_reuses_an_earlier_plot(tmp_path, failure):
    target, source, _ = staged(tmp_path)
    def partial_plot(board, output, **kwargs):
        if kwargs['panel'] != 'plot2':
            return fake_plot(board, output, **kwargs)
        if failure == 'exception':
            Path(output).write_text('<svg/>')
            raise RuntimeError('export interrupted')
        if failure == 'missing':
            return str(output)
        Path(output).write_text('<not-svg/>')
        return str(output)
    out = review.publish(target, 'synthetic', {}, archive_root=tmp_path/'a',
                         renderer=fake_render, plot_inventory=fake_inventory, plotter=partial_plot)
    assert out['native_copper_plots_complete'] is False
    assert set(out['plot_errors']) == {'plot2'}
    assert 'plot2' not in out['panels'] and 'plot2' not in out['native_copper_plots']
    assert len(out['native_copper_plots']) == 5
    assert out['output_sha256'] == review.sha(source)
    assert out['release_authority'] is False


def test_inventory_failure_is_explicit_not_a_guessed_six_layer_board(tmp_path):
    target, source, _ = staged(tmp_path)
    def unavailable(_board):
        raise RuntimeError('native layer inventory unavailable')
    out = review.publish(target, 'synthetic', {}, archive_root=tmp_path/'a',
                         renderer=fake_render, plot_inventory=unavailable, plotter=fake_plot)
    assert out['native_copper_plots_complete'] is False
    assert set(out['plot_errors']) == {'inventory'}
    assert out['native_copper_plots'] == {}
    assert set(out['panels']) == {'render', 'render-bottom'}
    assert out['output_sha256'] == review.sha(source)


def test_native_plotter_mutation_cannot_publish_a_catalog(tmp_path):
    target, source, _ = staged(tmp_path)
    def changing(board, output, **kwargs):
        Path(board).write_text('changed during layer export')
        return fake_plot(board, output, **kwargs)
    with pytest.raises(ValueError, match='changed board'):
        review.publish(target, 'synthetic', {}, archive_root=tmp_path/'a',
                       renderer=fake_render, plot_inventory=fake_inventory, plotter=changing)
    assert not list((tmp_path/'a').glob('*/summary.json'))
    assert source.read_text() == 'current pass CAD'


def test_dashboard_reload_preserves_review_status_not_fabrication_verdict():
    import cec_dashboard
    summary = {'id':'isolated-pass', 'verdict':'FAILED',
               'review': {'kind':'pipeline-pass-preview', 'label':'BLOCKED'},
               'panels': {'render':'render.png'}}
    cec_dashboard._decorate_archive_summary(summary)
    assert summary['verdict'] == 'BLOCKED'
    assert summary['failing'] == ['not-release-qualified']
    assert summary['panel_urls']['render'] == '/img?id=isolated-pass&panel=render'
