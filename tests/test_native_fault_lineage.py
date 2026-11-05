"""Representative churn is evidence, not a DRC or routing waiver."""
import pcbnew
import pytest
import cec_native_fault_lineage as lineage


def native_pair(offset=.15, rotate=0):
    b = pcbnew.CreateEmptyBoard()
    for code, name in enumerate(('first', 'second'), 1):
        b.Add(pcbnew.NETINFO_ITEM(b, name, code))
    fp = pcbnew.FOOTPRINT(b); b.Add(fp)
    pad = pcbnew.PAD(fp)
    pad.SetNumber('1'); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I_MM(.6, .3))
    pad.SetPosition(pcbnew.VECTOR2I_MM(1, 1))
    pad.SetOrientationDegrees(rotate)
    layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu)
    pad.SetLayerSet(layers)
    pad.SetNetCode(b.GetNetcodeFromNetname('first')); fp.Add(pad)
    # Keep a real terminal on both nets; KiCad omits padless named nets from
    # the saved net table, which is not the representative-churn test case.
    peer = pcbnew.PAD(fp); peer.SetNumber('2')
    peer.SetAttribute(pcbnew.PAD_ATTRIB_SMD); peer.SetShape(pcbnew.PAD_SHAPE_RECT)
    peer.SetSize(pcbnew.VECTOR2I_MM(.6, .3)); peer.SetPosition(pcbnew.VECTOR2I_MM(4, 4))
    peer.SetLayerSet(layers); peer.SetNetCode(b.GetNetcodeFromNetname('second')); fp.Add(peer)
    t = pcbnew.PCB_TRACK(b)
    t.SetStart(pcbnew.VECTOR2I_MM(.5, 1+offset))
    t.SetEnd(pcbnew.VECTOR2I_MM(1.5, 1+offset))
    t.SetWidth(pcbnew.FromMM(.2)); t.SetLayer(pcbnew.F_Cu)
    t.SetNetCode(b.GetNetcodeFromNetname('second')); b.Add(t)
    return b, pad, t


def violation(pad, track, kind='shorting_items'):
    return dict(type=kind, items=[dict(uuid=pad.m_Uuid.AsString()),
                                  dict(uuid=track.m_Uuid.AsString())])


def native_clone(parent, tmp_path):
    # Native LoadBoard propagates the net on this tiny, unlocked short.
    # This read-only board-object diagnostic tests both authored native boards
    # directly; KIID.Clone is the native identity copy, not a writable property.
    offset = parent[2].GetStart().y/1e6 - 1.
    child = native_pair(offset, parent[1].GetOrientationDegrees())
    for source, target in zip(parent[1:], child[1:]):
        target.m_Uuid.Clone(source.m_Uuid)
        assert source.m_Uuid.AsString() == target.m_Uuid.AsString()
    return child


@pytest.mark.parametrize('kind,offset', [('shorting_items', .15), ('clearance', .3)])
def test_unchanged_fault_keeps_blocking_and_no_admission_authority(tmp_path, kind, offset):
    parent = native_pair(offset); child = native_clone(parent, tmp_path)
    proof = lineage.explain(parent[0], child[0], [violation(*child[1:], kind)],
        clearance_nm=200000, rule_authority_unchanged=True)
    assert proof['complete'] and not proof['errors']
    assert proof['rows'][0]['classification'] == 'unchanged_source_pair_with_native_collision', proof
    assert proof['rows'][0]['remains_blocking']
    assert proof['faults_suppressed'] == 0 and proof['admission_unchanged']
    assert not proof['inherited_debt_qualified'] and not proof['release_authority']


@pytest.mark.parametrize('change', ['position', 'rotation', 'net', 'width', 'new'])
def test_new_or_changed_conductors_cannot_be_called_inherited(tmp_path, change):
    parent = native_pair(); child = native_clone(parent, tmp_path)
    b, pad, t = child
    if change == 'position': pad.SetPosition(pcbnew.VECTOR2I_MM(1.1, 1))
    if change == 'rotation': pad.SetOrientationDegrees(90)
    if change == 'net': pad.SetNetCode(b.GetNetcodeFromNetname('second'))
    if change == 'width': t.SetWidth(pcbnew.FromMM(.3))
    if change == 'new':
        new_track = pcbnew.PCB_TRACK(b)
        new_track.SetStart(t.GetStart()); new_track.SetEnd(t.GetEnd())
        new_track.SetLayer(t.GetLayer()); new_track.SetWidth(t.GetWidth())
        new_track.SetNetCode(t.GetNetCode()); b.Add(new_track)
        t = new_track
    proof = lineage.explain(parent[0], b, [violation(pad, t)],
        clearance_nm=200000, rule_authority_unchanged=True)
    assert proof['rows'][0]['classification'] == 'unknown'
    assert proof['rows'][0]['remains_blocking']


def test_exact_but_noncolliding_pair_has_no_inherited_fault_witness(tmp_path):
    parent = native_pair(1.); child = native_clone(parent, tmp_path)
    proof = lineage.explain(parent[0], child[0], [violation(*child[1:])],
        clearance_nm=200000, rule_authority_unchanged=True)
    assert proof['rows'][0]['classification'] == 'unknown'
    assert not proof['rows'][0]['source_native_collision_layers']


def test_rule_authority_is_mandatory_even_for_identical_copper():
    b, pad, t = native_pair()
    proof = lineage.explain(b, b, [violation(pad, t)], clearance_nm=200000)
    assert not proof['complete'] and proof['errors']


def test_reporting_adapter_uses_actual_stage_identity_key_without_changing_it(tmp_path):
    import cec_stage_admission as stage
    parent = native_pair(); child = native_clone(parent, tmp_path)
    fault = violation(*child[1:]); identity = stage._canonical_identity(fault)
    before = dict(unconnected=3, drc=1, structural_drc_identities=[],
                  kelvin_ok=True, diffpair_ok=True)
    after = dict(before, unconnected=2, structural_drc_identities=[identity])
    admission = stage.evaluate(before, after)
    assert not admission['accepted']
    proof = lineage.explain_changed_identities(parent[0], child[0], [fault],
        admission['new_structural_drc_identities'],
        netclass_resolver=lambda n: dict(clearance=.2), rule_authority_unchanged=True)
    assert len(proof['rows']) == 1 and proof['unexplained_count'] == 0
    assert proof['rows'][0]['classification'] == 'unchanged_source_pair_with_native_collision'
    assert not admission['accepted'] and admission['new_structural_drc_identities'] == [identity]


@pytest.mark.parametrize('kwargs', [dict(timeout_s=0), dict(timeout_s=11),
                                  dict(clearance_nm=-1), dict(clearance_nm=True)])
def test_bounds_are_not_silently_relaxed(kwargs):
    b, pad, t = native_pair()
    args = dict(clearance_nm=200000, rule_authority_unchanged=True); args.update(kwargs)
    with pytest.raises(ValueError):
        lineage.explain(b, b, [violation(pad, t)], **args)
