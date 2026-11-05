#!/usr/bin/env python3
"""Small, immutable CAD previews of completed campaign attempts, not signoff.

Only this attempt's declared output may be pictured. Failed attempts remain
visible; missing output gets a status card, never an older-board fallback.
Publishing does not run FEM, grant admission, or replace release authority.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(value, indent=2, default=str) + '\n')
    temp.replace(path)


def select_output(target, state):
    """Resolve the most advanced *published* output; never search by mtime."""
    target = Path(target).resolve()
    stages = state.get('stages', {})
    for stage in ('precision_detailed_route', 'route_preflight', 'placement'):
        entry = stages.get(stage)
        if not entry:
            continue
        raw = (entry.get('result') or {}).get('board')
        if raw:
            path = Path(raw).resolve()
            if not path.is_relative_to(target):
                raise ValueError('stage output escapes its campaign directory')
            if not path.is_file():
                raise ValueError('declared stage output is missing; refusing fallback')
            matches = [r for r in entry.get('artifacts', [])
                       if Path(r['path']).resolve() == path]
            if len(matches) != 1 or sha(path) != matches[0]['sha256']:
                raise ValueError('stage output hash is missing or changed; refusing fallback')
            return path, stage, True
        if stage == 'route_preflight':
            # Older prediction-only receipts have no board output. A native
            # recovery now does: when present it must beat the earlier
            # placement and match its journal hash, never silently fall back.
            continue
        if stage == 'precision_detailed_route':
            # A killed route must not be represented by its earlier placement.
            raise ValueError('routing attempt has no journaled output yet')
        checkpoints = target / '02-placement' / 'checkpoints'
        if entry.get('status') != 'complete' and (checkpoints / 'current.json').exists():
            import cec_placement_checkpoint
            try:
                record = cec_placement_checkpoint.read_current(
                    checkpoints, expected_family=state.get('board'))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise ValueError('invalid placement checkpoint; refusing fallback: ' + str(exc)) from exc
            return Path(record['board']), 'placement-checkpoint:' + record['phase'], False
        # Interrupted placement can still have its explicit working artifact.
        # It is useful for diagnosis but is not a completed/admitted stage.
        path = target / '02-placement' / 'board.kicad_pcb'
        if entry.get('status') != 'complete' and path.is_file():
            if not path.resolve().is_relative_to(target):
                raise ValueError('working artifact escapes its campaign directory')
            return path, 'partial-placement', False
    return None, 'no-output', False


def status_label(result):
    if result.get('engine_unchanged') is False or result.get('source_inputs_unchanged') is False:
        return 'INVALID PROVENANCE'
    stages = list((result.get('stages') or {}).values())
    if (result.get('status') == 'budget_exhausted'
            or any((row.get('failure_evidence') or {}).get('status') in
                   ('operation_budget_exhausted', 'budget_exhausted')
                   for row in stages)):
        return 'BUDGET EXHAUSTED'
    if any(r.get('admission_ok') is False for r in result.get('stages', {}).values()):
        return ('UNCHANGED / ' if result.get('status') == 'unchanged-context' else '') + 'BLOCKED'
    if (result.get('status') in ('blocked_or_failed', 'failed', 'coordinator_error', 'resource_refused')
            or any(row.get('execution_status') in ('failed', 'interrupted', 'timed_out')
                   for row in stages)):
        return 'BLOCKED'
    # Even a successful process is not, by itself, a release certificate.
    return 'REVIEW ONLY'


def _font(size):
    from PIL import ImageFont
    try:
        return ImageFont.truetype('DejaVuSans.ttf', size)
    except OSError:
        return ImageFont.load_default()


def label_image(path, lines, *, empty=False):
    """Legible wrapped metadata outside the CAD drawing, never over copper."""
    from PIL import Image, ImageDraw
    import textwrap
    image = Image.new('RGB', (1400, 650), '#17212b') if empty else Image.open(path).convert('RGB')
    font = _font(24)
    wrapped = [line for text in lines for line in textwrap.wrap(str(text), max(24, image.width // 15))]
    header = max(90, 34 * len(wrapped) + 24)
    canvas = Image.new('RGB', (image.width, image.height + header), '#17212b')
    canvas.paste(image, (0, header))
    draw = ImageDraw.Draw(canvas)
    for i, line in enumerate(wrapped):
        draw.text((16, 12 + 34 * i), line, font=font, fill='#ffffff')
    canvas.save(path)
    image.close()
    canvas.close()


def native_plot_inventory(board_path):
    """Resolve every enabled copper layer; a guessed stack is not a preview."""
    import pcbnew
    import cec_swig_guard
    cec_swig_guard.pin()
    import cec_dashboard
    import cec_fab_profile

    board = pcbnew.LoadBoard(str(board_path))
    if board is None:
        raise ValueError('native copper inventory cannot read the saved board')
    ids = tuple(int(layer) for layer in board.GetEnabledLayers().CuStack())
    # Use canonical layer identity, not the board's optional display aliases.
    # Unknown stacks fail visibly instead of silently dropping extra layers.
    names = tuple(cec_fab_profile.COPPER_LAYER_IDS[layer] for layer in ids)
    by_layer = {layers.split(',')[0]: (panel, filename, layers)
                for panel, filename, layers in cec_dashboard.COPPER_PLOTS}
    if not names or len(set(names)) != len(names):
        raise ValueError('empty or duplicate native copper-layer inventory')
    return tuple(by_layer[name] for name in names)


def export_native_plot(board_path, output, *, layers, panel, timeout=10):
    """Export only actual saved-board copper, without a filler/FEM overlay."""
    import cec_dashboard
    import cec_toolchain

    executable = cec_toolchain.kicad_cli()
    if not executable:
        raise RuntimeError('KiCad native copper exporter is unavailable')
    command = cec_dashboard._copper_plot_command(
        str(board_path), str(output), layers, panel)
    command[0] = executable
    completed = subprocess.run(command, capture_output=True, text=True,
                               timeout=timeout)
    if completed.returncode or not Path(output).is_file():
        raise RuntimeError('native copper export failed: ' + completed.stderr[-500:])
    return str(output)


def measure_native_geometry(board_path):
    """Cheap current-snapshot topology/style counts, not a fabrication signoff.

    Never carry a parent's power-contour count into a child's preview. Native
    opens and bounded geometry are recomputed from the same bytes being shown;
    scored DRC is still separately reported by the campaign's receiving stage.
    """
    import pcbnew
    import cec_swig_guard
    import cec_route_quality
    cec_swig_guard.pin()
    digest = sha(board_path)
    native = pcbnew.LoadBoard(str(board_path))
    if native is None:
        raise ValueError('saved-board native geometry unavailable')
    native.BuildConnectivity()
    native.GetConnectivity().RecalculateRatsnest()
    geometry = cec_route_quality.analyze_board(native)
    contours = geometry['power_contours']
    result = dict(source_board_sha256=digest,
        unconnected=int(native.GetConnectivity().GetUnconnectedCount(False)),
        craft_ok=geometry['craft_ok'], craft_issue_count=geometry['issue_count'],
        power_contours=contours, release_authority=False)
    if sha(board_path) != digest:
        raise ValueError('native geometry source changed while measuring')
    return result


def publish(target, board, result, *, archive_root=None, renderer=None, mirror=None,
            plot_inventory=None, plotter=None, geometry_measurer=None):
    """Publish no-body views and every native copper layer from one snapshot."""
    target = Path(target).resolve()
    state_path = target / 'pipeline-state.json'
    state = json.loads(state_path.read_text()) if state_path.is_file() else {}
    if state.get('board', board) != board:
        raise ValueError('journal board identity differs from campaign')
    selection_error = None
    try:
        source, stage, verified = select_output(target, state)
    except ValueError as exc:
        source, stage, verified = None, 'no-trustworthy-output', False
        selection_error = str(exc)
    digest = sha(source) if source else None
    epoch = time.time()
    # Full directory identity prevents same-minute names from overwriting.
    key = hashlib.sha256(str(target).encode()).hexdigest()[:10]
    slug = re.sub(r'[^a-zA-Z0-9_-]+', '-', target.parent.name + '-' + board)[:130]
    aid = 'pass-' + slug + '-' + key
    archive_root = Path(archive_root or ROOT / 'build' / 'board-archive')
    archive_root.mkdir(parents=True, exist_ok=True)
    dest = archive_root / aid
    if dest.exists():
        raise FileExistsError('pass preview already exists; use a new attempt ID')
    dest.mkdir()
    label = 'UNTRUSTWORTHY OUTPUT' if selection_error else status_label(result)
    review = {'schema': 1, 'kind': 'pipeline-pass-preview', 'board_family': board,
              'attempt': str(target), 'pass_id': target.parent.name, 'stage': stage,
              'label': label, 'journal_hash_verified': verified,
              'checkpoint_hash_verified': stage.startswith('placement-checkpoint:'),
              'output_sha256': digest, 'selection_error': selection_error,
              'release_authority': False,
              'campaign_result': json.loads(json.dumps(result, default=str))}
    counts = {key: result[key] for key in ('unconnected', 'drc')
              if type(result.get(key)) is int and result[key] >= 0}
    review['campaign_reported_counts'] = dict(counts)
    review['counts_source'] = {key: 'campaign-report-not-independent-preview-measurement'
                              for key in counts}
    review['measured_counts'] = counts
    count_label = ' | '.join('%d %s' % (value, 'opens' if key == 'unconnected' else 'scored DRC')
                             for key, value in counts.items())
    input_path = target / 'campaign-input.json'
    if input_path.is_file():
        declaration = json.loads(input_path.read_text())
        review['input_board'] = declaration.get('input')
        review['input_sha256'] = declaration.get('input_sha256')
        review['output_identical_to_input'] = bool(digest and digest == declaration.get('input_sha256'))
    panels = {}
    if source:
        snapshot = dest / 'board.kicad_pcb'
        shutil.copy2(source, snapshot)
        # Preserve all board-stem metadata without an ever-stale suffix list.
        for sidecar in source.parent.glob(source.stem + '.*'):
            if sidecar == source or not sidecar.is_file():
                continue
            shutil.copy2(sidecar, dest / ('board' + sidecar.name[len(source.stem):]))
        if sha(snapshot) != digest or sha(source) != digest:
            raise ValueError('board changed while snapshotting')
        try:
            measure = geometry_measurer or measure_native_geometry
            geometry = measure(snapshot)
            if geometry.get('source_board_sha256') != digest:
                raise ValueError('native geometry receipt does not bind this snapshot')
            review['native_geometry'] = geometry
            measurements = {'unconnected': geometry.get('unconnected')}
            contours = geometry.get('power_contours') or {}
            if contours.get('complete') is True:
                measurements['power_contour_review_findings'] = contours.get('finding_count')
            else:
                review['native_geometry_unknown'] = 'power-contour inspection incomplete'
            for key, value in measurements.items():
                if type(value) is not int or value < 0:
                    raise ValueError('invalid native geometry count: ' + key)
                supplied = result.get(key)
                if supplied is not None and supplied != value:
                    review.setdefault('count_mismatches', {})[key] = {
                        'campaign_reported': supplied, 'native_snapshot': value}
                counts[key] = value
                review['counts_source'][key] = 'hash-bound-native-saved-board'
            if review.get('count_mismatches'):
                # Preserve the quoted campaign evidence, but make its stale
                # count visible and never label it an independently measured
                # result from the board on screen.
                label = 'BLOCKED / COUNT MISMATCH'
                review['label'] = label
        except Exception as exc:
            review['native_geometry_error'] = str(exc)
        review['measured_counts'] = dict(counts)
        names = {'unconnected': 'opens', 'drc': 'reported scored DRC',
                 'power_contour_review_findings': 'power-contour reviews'}
        count_label = ' | '.join('%d %s' % (value, names[key])
                                 for key, value in counts.items())
        if renderer is None:
            from cec_render import render
            renderer = render
        for side, panel in (('top', 'render'), ('bottom', 'render-bottom')):
            image = dest / (panel + '.png')
            try:
                rendered = renderer(str(snapshot), str(image), side=side,
                                    no_bodies=True, timeout=45)
                if not rendered or not image.is_file():
                    raise ValueError('native renderer returned no image')
                label_image(image, [f'{board} | {side} | {stage} | {label}',
                                   f'{target.parent.name} | SHA256 {digest[:16]} | NOT FAB SIGNOFF',
                                   count_label] if count_label else
                                  [f'{board} | {side} | {stage} | {label}',
                                   f'{target.parent.name} | SHA256 {digest[:16]} | NOT FAB SIGNOFF'])
                panels[panel] = image.name
            except Exception as exc:
                review.setdefault('render_errors', {})[side] = str(exc)
        # The normal pass publisher used to expose only F/B renders even though
        # the analyzer supported all six layers. Bind each engineering layer to
        # this immutable PCB, not to a previous archive or plotting substitute.
        inventory = plot_inventory or native_plot_inventory
        plotter = plotter or export_native_plot
        review['native_copper_plots'] = {}
        review['plots_do_not_grant_admission'] = True
        try:
            specs = tuple(inventory(snapshot))
            if not specs:
                raise ValueError('empty native copper plot inventory')
        except Exception as exc:
            specs = ()
            review.setdefault('plot_errors', {})['inventory'] = str(exc)
        for panel, filename, layers in specs:
            image = dest / filename
            try:
                rendered = plotter(snapshot, image, layers=layers, panel=panel, timeout=10)
                if not rendered or not image.is_file():
                    raise ValueError('native copper exporter returned no layer image')
                import xml.etree.ElementTree as xml
                if xml.parse(image).getroot().tag.rsplit('}', 1)[-1] != 'svg':
                    raise ValueError('native copper exporter returned a non-SVG artifact')
                panels[panel] = image.name
                review['native_copper_plots'][panel] = {
                    'file': filename, 'sha256': sha(image), 'layers': layers,
                    'source_board_sha256': digest,
                    'source': 'native-saved-board-copper-only',
                }
            except Exception as exc:
                review.setdefault('plot_errors', {})[panel] = str(exc)
        review['native_copper_plots_complete'] = bool(
            specs and not review.get('plot_errors')
            and len(review['native_copper_plots']) == len(specs))
        if sha(snapshot) != digest or sha(source) != digest:
            raise ValueError('renderer changed board content')
    if 'render' not in panels:
        image = dest / 'render.png'
        label_image(image, [f'{board} | {label} | {stage}', target.parent.name,
                           selection_error or ('Render unavailable' if source else 'No new board output produced'),
                           'No older board substituted. NOT FAB SIGNOFF.'], empty=True)
        panels['render'] = image.name
    review['panels'] = {k: str(dest / v) for k, v in panels.items()}
    summary = {'schema': 1, 'id': aid, 'name': f'{board} | {stage} | {label} | {target.parent.name}',
               'epoch': epoch, 'timestamp': time.strftime('%Y%m%dT%H%M%SZ', time.gmtime(epoch)),
               'ts_human': time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(epoch)),
               'source': str(source) if source else None, 'board': 'board.kicad_pcb' if source else None,
               'panels': panels, 'review': review, 'gates': {'ok': False, 'error': 'Preview only; signoff not evaluated'},
               'thermal': {'ok': False, 'error': 'Not solved by preview publisher'},
               'lineage': {'schema': 1, 'board_family': board, 'archive_role': 'diagnostic',
                           'status': 'pass-preview', 'reason': 'Unpromoted campaign output; see review metadata'},
               'verdict': label, 'failing': ['not-release-qualified'], **counts}
    atomic_json(dest / 'summary.json', summary)  # catalog appears only after complete images
    review.update(id=aid, viewer_url='http://localhost:8090/?id=' + quote(aid),
                  summary=str(dest / 'summary.json'))
    if mirror:
        export = Path(mirror) / board
        export.mkdir(parents=True, exist_ok=True)
        for panel, path in review['panels'].items():
            shutil.copy2(path, export / Path(path).name)
        atomic_json(export / 'review.json', review)
    atomic_json(target / 'pass-review.json', review)
    return review


def gallery(report, output, *, mirror=None):
    """One current-pass tile per selected board, including queued/failed jobs."""
    from PIL import Image, ImageDraw, ImageOps
    output = Path(output)
    rows = list(report['boards'].items())
    width, height, columns = 800, 700, 3
    canvas = Image.new('RGB', (width * columns, height * ((len(rows) + columns - 1) // columns)), '#101820')
    draw = ImageDraw.Draw(canvas)
    for i, (name, row) in enumerate(rows):
        x, y = (i % columns) * width, (i // columns) * height
        preview = row.get('review') or {}
        path = (preview.get('panels') or {}).get('render')
        draw.text((x + 12, y + 10), name, font=_font(27), fill='white')
        draw.text((x + 12, y + 50), preview.get('label') or row['status'], font=_font(22), fill='#ffcc66')
        if path and Path(path).is_file():
            with Image.open(path) as raw:
                tile = ImageOps.contain(raw.convert('RGB'), (width - 16, height - 105))
                canvas.paste(tile, (x + (width - tile.width) // 2, y + 90))
        else:
            draw.text((x + 12, y + 120), 'No current-pass preview yet', font=_font(24), fill='white')
    temporary = output.with_suffix('.tmp.png')
    canvas.save(temporary)
    # A stable filename is convenient locally, but reusing it in chat/browser
    # embeds can show a cached earlier gallery. Return a content-addressed
    # snapshot; retain the convenient alias separately.
    immutable = output.with_name(output.stem + '-' + sha(temporary)[:16] + output.suffix)
    if not immutable.exists():
        shutil.copy2(temporary, immutable)
    temporary.replace(output)
    canvas.close()
    if mirror:
        export = Path(mirror)
        export.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output, export / output.name)
        shutil.copy2(immutable, export / immutable.name)
        atomic_json(export / 'suite.json', report)
    return str(immutable)
