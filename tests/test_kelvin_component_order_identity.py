"""Component ordinals describe canonical physical islands, never GEOS order."""
import pcbnew
import pytest
import cec_kelvin_copper_cut as cut
from test_kelvin_copper_cut import native_board_fixture,audit,track,zone


def fixture(tmp_path,back=False):
    values=native_board_fixture(tmp_path/'source.kicad_pcb');board=values[0]
    # A true post-cut bypass gives nonempty upper/lower witness chains.
    for a,b in [((90.15,72),(92,72)),((92,72),(92,77)),((92,77),(90.08,77))]:
        track(board,a,b)
    # Disconnected physical same-net islands make component permutations
    # observable without inventing any new terminal or same-net connection.
    for n in range(4):track(board,(70+n*2,66),(70+n*2,67),width=.2)
    if back:
        for fp in board.GetFootprints():
            fp.SetLayer(pcbnew.B_Cu)
            for p in fp.Pads():
                layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);p.SetLayerSet(layers)
        for t in board.GetTracks():t.SetLayer(pcbnew.B_Cu)
    return values


@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('native_reverse',[False,True])
def test_full_raw_geometry_evidence_stable_under_independent_component_permutation(
        tmp_path,monkeypatch,back,native_reverse):
    values=fixture(tmp_path,back);board=values[0]
    # Deterministic operational clock lets us compare the ENTIRE raw packet,
    # not a comparator that discards component/geometry/electrical fields.
    monkeypatch.setattr(cut.time,'monotonic',lambda:100.)
    before=audit(values);original=cut._parts
    def reverse(shape):return list(reversed(original(shape)))
    monkeypatch.setattr(cut,'_parts',reverse)
    if native_reverse:
        items=list(board.GetTracks());monkeypatch.setattr(board,'GetTracks',lambda:list(reversed(items)))
    after=audit(values)
    assert before['complete'] and before['physical_bypass_proved']
    assert before['upper']['witnesses'] and before['lower']['witnesses']
    assert before==after


@pytest.mark.parametrize('change',['pad','hole','sliver','disconnected_island'])
@pytest.mark.parametrize('back',[False,True])
def test_actual_native_material_changes_are_not_normalized_away(tmp_path,monkeypatch,change,back):
    values=fixture(tmp_path,back);board,source,sense,authority=values
    monkeypatch.setattr(cut.time,'monotonic',lambda:100.)
    before=audit(values)
    face=pcbnew.B_Cu if back else pcbnew.F_Cu
    if change=='pad':source.SetSize(source.GetSize()+pcbnew.VECTOR2I(1000,0))
    elif change=='hole':
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('arbitrary_drill');board.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('hole');p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE);p.SetSize(pcbnew.VECTOR2I_MM(.3,.3))
        p.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3));p.SetLayerSet(pcbnew.PAD.PTHMask())
        p.SetPosition(pcbnew.VECTOR2I_MM(92,75));fp.Add(p)
    elif change=='sliver':track(board,(92,74.5),(92.002,74.5),layer=face,width=.201)
    else:track(board,(62,61),(62.5,61),layer=face,width=.2)
    after=audit(values)
    assert before!=after
    assert any(before.get(k)!=after.get(k)for k in('baseline_geometry','upper','lower','reason','source'))


@pytest.mark.parametrize('back',[False,True])
def test_unknown_native_fill_never_becomes_positive_after_reordering(tmp_path,monkeypatch,back):
    values=fixture(tmp_path,back)
    item=zone(values[0],[(88,71,94,79)],layer=pcbnew.B_Cu if back else pcbnew.F_Cu)
    item.SetIsFilled(False)
    before=audit(values);original=cut._parts
    monkeypatch.setattr(cut,'_parts',lambda shape:list(reversed(original(shape))))
    after=audit(values)
    assert before['ok'] is None and after['ok'] is None
    assert not before['complete'] and not after['complete']
    assert before['reason']==after['reason']=='native_zone_fill_unavailable'


@pytest.mark.parametrize('back',[False,True])
def test_relocating_a_disconnected_nonwitness_island_does_not_rename_actual_witnesses(tmp_path,monkeypatch,back):
    values=fixture(tmp_path,back);board=values[0]
    monkeypatch.setattr(cut.time,'monotonic',lambda:100.)
    before=audit(values)
    isolated=next(t for t in board.GetTracks()if tuple(t.GetStart())==(70000000,66000000))
    isolated.SetStart(pcbnew.VECTOR2I_MM(100,60));isolated.SetEnd(pcbnew.VECTOR2I_MM(100,61))
    after=audit(values)
    assert before==after
    for model in('baseline_geometry','upper','lower'):
        assert before[model]['witnesses']
        assert all(node['component'].startswith('native-copper-')
            for witness in before[model]['witnesses']for node in witness['path'])
    # A real material change in a witnessed island remains visible in the
    # producer itself. No consumer field-ignore list participates.
    track(board,(92,74.5),(92.002,74.5),layer=pcbnew.B_Cu if back else pcbnew.F_Cu,width=.201)
    actual=audit(values)
    assert actual!=after
    assert any(actual[m]['witnesses']!=after[m]['witnesses']for m in('baseline_geometry','upper','lower'))
