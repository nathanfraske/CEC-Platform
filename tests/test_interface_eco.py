import json

import pytest

import cec_interface_eco as eco


def fixture_board(tmp_path):
    pcbnew = pytest.importorskip('pcbnew')
    import cec_swig_guard
    cec_swig_guard.pin()
    b = pcbnew.BOARD()
    n = pcbnew.NETINFO_ITEM(b, 'supply')
    b.Add(n)
    for ref, x in [('alpha', 4), ('beta', 14), ('other', 8)]:
        fp = pcbnew.FOOTPRINT(b)
        fp.SetReference(ref)
        fp.SetPosition(pcbnew.VECTOR2I_MM(x, 5))
        pad = pcbnew.PAD(fp)
        pad.SetNumber('1')
        pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        pad.SetSize(pcbnew.VECTOR2I_MM(2, 2))
        pad.SetDrillSize(pcbnew.VECTOR2I_MM(1, 1))
        pad.SetLayerSet(pcbnew.LSET.AllCuMask())
        pad.SetPosition(fp.GetPosition())
        pad.SetNet(n)
        fp.Add(pad)
        b.Add(fp)
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(pcbnew.VECTOR2I_MM(4, 5))
    t.SetEnd(pcbnew.VECTOR2I_MM(14, 5))
    t.SetWidth(pcbnew.FromMM(.5))
    t.SetLayer(pcbnew.F_Cu)
    t.SetNet(n)
    b.Add(t)
    for a, z in [((0, 0), (20, 0)), ((20, 0), (20, 10)),
                 ((20, 10), (0, 10)), ((0, 10), (0, 0))]:
        edge = pcbnew.PCB_SHAPE(b)
        edge.SetShape(pcbnew.SHAPE_T_SEGMENT)
        edge.SetStart(pcbnew.VECTOR2I_MM(*a))
        edge.SetEnd(pcbnew.VECTOR2I_MM(*z))
        edge.SetLayer(pcbnew.Edge_Cuts)
        b.Add(edge)
    source = tmp_path / 'source.kicad_pcb'
    pcbnew.SaveBoard(str(source), b)
    return source


def test_eco_preserves_source_outline_unrelated_poses_and_copper(tmp_path):
    import pcbnew
    source = fixture_board(tmp_path)
    digest = eco.sha(source)
    output = tmp_path / 'candidate.kicad_pcb'
    source.with_suffix('.power-prefix.json').write_text('{"ok": true}')
    source.with_suffix('.kicad_dru').write_text('(version 1)\n')
    report = eco.apply(source, output, {'alpha': (5, 5, 0)}, expected_sha256=digest)
    assert eco.sha(source) == digest
    a, b = pcbnew.LoadBoard(str(source)), pcbnew.LoadBoard(str(output))
    assert eco.poses(a)['other'] == eco.poses(b)['other']
    assert eco.copper_signature(a) == eco.copper_signature(b)
    assert not output.with_suffix('.power-prefix.json').exists()
    assert report['route_authority_invalidated'] and not report['admission_ok']
    assert len(report['stale_copper']) == 1
    assert eco.sha(source.with_suffix('.kicad_dru')) == eco.sha(output.with_suffix('.kicad_dru'))
    assert report['affected_nets'] == ['supply']
    with pytest.raises(ValueError, match='requires replacement'):
        eco.require_rebuilt(output)
    assert json.loads(output.with_suffix('.interface-eco.json').read_text())['output_sha256'] == eco.sha(output)
    output.with_suffix('.kicad_dru').unlink()
    with pytest.raises(ValueError, match='design rules missing'):
        eco.read_status(output)


def test_eco_refuses_stale_input_and_overwrite(tmp_path):
    source = fixture_board(tmp_path)
    with pytest.raises(ValueError, match='digest'):
        eco.apply(source, tmp_path / 'candidate.kicad_pcb', {}, expected_sha256='old')
    with pytest.raises(ValueError, match='overwrite'):
        eco.apply(source, source, {}, expected_sha256=eco.sha(source))
    output = tmp_path / 'unchanged.kicad_pcb'
    eco.apply(source, output, {}, expected_sha256=eco.sha(source))
    assert eco.sha(source) == eco.sha(output)


def test_explicit_outline_extension_invalidates_copper_even_without_component_moves(tmp_path):
    import pcbnew
    source = fixture_board(tmp_path)
    digest = eco.sha(source)
    output = tmp_path/'extended.kicad_pcb'
    report = eco.apply(source, output, {}, expected_sha256=digest, outline_rect_mm=(0, 0, 23, 10))
    assert eco.sha(source) == digest
    assert report['outline_change']['after_mm'] == [0, 0, 23, 10]
    assert not report['outline_unchanged'] and report['route_authority_invalidated']
    assert report['copper_unchanged'] and report['affected_nets'] == ['supply']
    assert report['unrelated_footprints_unchanged']
    board = pcbnew.LoadBoard(str(output))
    assert max(e.GetStart().x for e in board.GetDrawings() if e.GetLayer()==pcbnew.Edge_Cuts) == 23000000
    with pytest.raises(ValueError, match='requires replacement'):
        eco.require_rebuilt(output)
    with pytest.raises(ValueError, match='only extend'):
        eco.apply(source, tmp_path/'shrink.kicad_pcb', {}, expected_sha256=digest,
                  outline_rect_mm=(0, 0, 19, 10))


def test_noop_copy_cannot_launder_unrebuilt_eco(tmp_path):
    source = fixture_board(tmp_path)
    first = tmp_path / 'first.kicad_pcb'
    eco.apply(source, first, {'alpha': (5, 5, 0)}, expected_sha256=eco.sha(source))
    second = tmp_path / 'second.kicad_pcb'
    report = eco.apply(first, second, {}, expected_sha256=eco.sha(first))
    assert report['moved'] == {}
    assert report['inherited_route_invalidation']
    assert report['affected_nets'] == ['supply']
    with pytest.raises(ValueError, match='requires replacement'):
        eco.require_rebuilt(second)


def test_rule_digest_ignores_only_serialization_metadata(tmp_path):
    path = tmp_path/'rules.kicad_pro'
    data = {'meta':{'filename':'old'}, 'net_settings':{'meta':{'version':4},
            'classes':[{'name':'example','track_width':.5}]}}
    path.write_text(json.dumps(data)); before=eco.rule_digest(path)
    data['meta']['filename']='new'; data['net_settings']['meta']['version']=5
    path.write_text(json.dumps(data)); assert eco.rule_digest(path)==before
    data['net_settings']['classes'][0]['track_width']=.4
    path.write_text(json.dumps(data)); assert eco.rule_digest(path)!=before


@pytest.mark.parametrize('interrupt', [False, True])
def test_coordinated_publication_preserves_backups_and_blocks_partial_reads(tmp_path, monkeypatch, interrupt):
    entries=[]
    for i in range(2):
        folder=tmp_path/str(i)
        folder.mkdir()
        source=fixture_board(folder)
        output=folder/'candidate.kicad_pcb'
        digest=eco.sha(source)
        eco.apply(source,output,{'alpha':(5,5,0)},expected_sha256=digest)
        entries.append(dict(target=str(source),candidate=str(output),
            expected_target_sha256=digest,expected_candidate_sha256=eco.sha(output)))
    original_replace=eco.os.replace
    count=0
    def replace(src,dst):
        nonlocal count
        count+=1
        if interrupt and count==3:
            raise OSError('injected group publication crash')
        original_replace(src,dst)
    monkeypatch.setattr(eco.os,'replace',replace)
    backup=tmp_path/'backups'
    if interrupt:
        with pytest.raises(OSError,match='group publication crash'):
            eco.publish_group(entries,backup)
        for row in entries:
            with pytest.raises(ValueError,match='incomplete'):
                eco.read_status(row['target'])
    else:
        report=eco.publish_group(entries,backup)
        assert report['status']=='complete' and not report['release_authority']
        for row in entries:
            assert eco.sha(row['target'])==row['expected_candidate_sha256']
            assert eco.read_status(row['target'])['route_authority_invalidated']
    for i,row in enumerate(entries):
        assert eco.sha(backup/str(i)/'source.kicad_pcb')==row['expected_target_sha256']


def test_orphan_sidecar_and_interrupted_publication_fail_closed(tmp_path, monkeypatch):
    source = fixture_board(tmp_path)
    output = tmp_path / 'candidate.kicad_pcb'
    output.with_suffix('.power-prefix.json').write_text('{}')
    with pytest.raises(ValueError, match='pre-existing sidecars'):
        eco.apply(source, output, {}, expected_sha256=eco.sha(source))
    output = tmp_path / 'interrupted.kicad_pcb'
    real_replace = eco.os.replace
    def interrupt_certificate(src, dst):
        if str(dst).endswith('.interface-eco.json'):
            raise OSError('injected crash')
        return real_replace(src, dst)
    monkeypatch.setattr(eco.os, 'replace', interrupt_certificate)
    with pytest.raises(OSError, match='injected crash'):
        eco.apply(source, output, {}, expected_sha256=eco.sha(source))
    with pytest.raises(ValueError, match='incomplete'):
        eco.read_status(output)
