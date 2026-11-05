"""Routing optimization needs plated material, not a pad copper-layer mask."""
import time
import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_fr as fr
import cec_kelvin_copper_cut as native


def board_fixture(*, count=2, attribute=None, flip=False, angle=0, partial=False):
    b = pcbnew.CreateEmptyBoard(); b.SetCopperLayerCount(6)
    n = pcbnew.NETINFO_ITEM(b, 'RENAMED'); b.Add(n)
    fp = pcbnew.FOOTPRINT(b); fp.SetReference('OTHER_LABEL'); b.Add(fp)
    pads = []
    for i in range(count):
        p = pcbnew.PAD(fp); p.SetNumber(str(i+1)); p.SetNet(n)
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH if attribute is None else attribute)
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        p.SetSize(pcbnew.VECTOR2I_MM(1.5, 1.5))
        if p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
            p.SetDrillSize(pcbnew.VECTOR2I_MM(.8, .8))
        p.SetLayerSet(pcbnew.PAD.PTHMask())
        if partial:
            layers = pcbnew.LSET()
            layers.AddLayer(pcbnew.F_Cu)
            p.SetLayerSet(layers)
        p.SetPosition(pcbnew.VECTOR2I_MM(5+2*i, 5)); fp.Add(p); pads.append(p)
    if flip:
        fp.Flip(pcbnew.VECTOR2I_MM(6, 5), False)
    fp.SetOrientationDegrees(angle)
    return b, fp, pads, n


def filled_rectangle(b, n, a=(2, 2), c=(10, 8), *, layer=pcbnew.In1_Cu):
    z = pcbnew.ZONE(b); z.SetNet(n); z.SetLayer(layer)
    poly = pcbnew.SHAPE_POLY_SET(); i = poly.NewOutline()
    for x, y in ((a[0], a[1]), (c[0], a[1]), (c[0], c[1]), (a[0], c[1])):
        poly.Outline(i).Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    z.Outline().Append(poly); z.SetFilledPolysList(layer, poly)
    z.SetIsFilled(True); b.Add(z)
    return z


@pytest.mark.parametrize('flip', [False, True])
def test_actual_full_through_barrel_is_orientation_independent(flip):
    b, fp, pads, n = board_fixture(flip=flip)
    for pad in pads:
        assert native._simple_drill(pad, tuple(b.GetEnabledLayers().CuStack()))
        assert set(fr._pth_barrel_layers(b, pad)) == set(b.GetEnabledLayers().CuStack())


@pytest.mark.parametrize('attribute', [pcbnew.PAD_ATTRIB_NPTH, pcbnew.PAD_ATTRIB_SMD])
def test_multilayer_mask_is_never_a_plated_barrel(attribute):
    b, fp, pads, n = board_fixture(attribute=attribute)
    filled_rectangle(b, n)
    proof = {}
    assert fr.filled_tht_exclusion_pins(b, evidence=proof) == {}
    assert proof['complete']
    assert all(fr._pth_barrel_layers(b, p) == () for p in pads)


def test_partial_padstack_is_explicit_unknown_and_retains_all_terminals():
    b, fp, pads, n = board_fixture(partial=True)
    filled_rectangle(b, n)
    proof = {}
    assert fr.filled_tht_exclusion_pins(b, evidence=proof) == {}
    assert not proof['complete'] and proof['reason'] == 'unsupported_partial_barrel_padstack'


@pytest.mark.parametrize('modification', ['primary', 'backdrill'])
def test_modified_barrels_remain_unknown_even_after_flip(modification):
    b, fp, pads, n = board_fixture(flip=True)
    for pad in pads:
        if modification == 'primary':
            pad.SetPrimaryDrillEndLayer(pcbnew.In2_Cu)
        else:
            pad.SetBackdrillMode(pcbnew.BACKDRILL_MODE_BACKDRILL_TOP)
        assert fr._pth_barrel_layers(b, pad) == ()
    filled_rectangle(b, n)
    proof = {}
    assert fr.filled_tht_exclusion_pins(b, evidence=proof) == {}
    assert not proof['complete']


def test_one_real_pour_port_must_not_be_deleted_from_dsn():
    b, fp, pads, n = board_fixture(count=1)
    filled_rectangle(b, n)
    proof = {}
    assert fr.filled_tht_exclusion_pins(b, evidence=proof) == {}
    assert proof['proven_contact_pin_count'] == 1
    assert proof['retained_representatives'] == ['OTHER_LABEL-1']


def test_two_disconnected_fill_islands_keep_two_representatives():
    b, fp, pads, n = board_fixture()
    filled_rectangle(b, n, (4.4, 4.4), (5.6, 5.6))
    filled_rectangle(b, n, (6.4, 4.4), (7.6, 5.6))
    proof = {}
    assert fr.filled_tht_exclusion_pins(b, evidence=proof) == {}
    assert proof['complete'] and proof['filled_component_count'] == 2


def test_only_hole_void_contact_never_excludes_a_pin():
    b, fp, pads, n = board_fixture()
    for pad in pads:
        x, y = pad.GetPosition().x/1e6, pad.GetPosition().y/1e6
        filled_rectangle(b, n, (x-.1, y-.1), (x+.1, y+.1))
    proof = {}
    assert fr.filled_tht_exclusion_pins(b, evidence=proof) == {}
    assert proof['complete'] and proof['proven_contact_pin_count'] == 0


def test_shared_native_component_excludes_only_redundant_port_and_does_not_mutate():
    b, fp, pads, n = board_fixture()
    filled_rectangle(b, n)
    positions = [p.GetPosition() for p in pads]
    proof = {}
    assert fr.filled_tht_exclusion_pins(b, evidence=proof) == {'OTHER_LABEL-2': 'RENAMED'}
    assert proof['complete'] and proof['retained_representatives'] == ['OTHER_LABEL-1']
    assert positions == [p.GetPosition() for p in pads]


def fractured_fill_fixture():
    b, fp, pads, n = board_fixture()
    z = filled_rectangle(b, n)
    poly = pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(pcbnew.In1_Cu))
    hole = poly.NewHole(0)
    for x, y in ((8, 2.5), (9, 2.5), (9, 4), (8, 4)):
        poly.Hole(0, hole).Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    poly.Fracture()
    z.SetFilledPolysList(pcbnew.In1_Cu, poly)
    with pytest.raises(native.Unknown, match='invalid_native_polygon'):
        native._poly(poly, native._Work(time.monotonic()+1))
    return b, z


def test_real_fractured_fill_uses_proven_lower_material_without_rewriting_it():
    b, zone = fractured_fill_fixture()
    original = zone.GetFilledPolysList(pcbnew.In1_Cu).Format()
    proof = {}
    result = fr.filled_tht_exclusion_pins(b, evidence=proof)
    assert result == {'OTHER_LABEL-2': 'RENAMED'}, proof.get('reason', proof)
    assert proof['complete']
    assert len(proof['conservative_fill_subsets']) == 1
    certificate = proof['conservative_fill_subsets'][0]
    assert certificate['native_inward_guard_nm'] == 2
    assert certificate['exterior_difference_contours'] == 0
    assert certificate['geometric_contacts_only']
    assert zone.GetFilledPolysList(pcbnew.In1_Cu).Format() == original


def test_unfracture_alone_cannot_credit_invented_material(monkeypatch):
    b, zone = fractured_fill_fixture()
    original = pcbnew.SHAPE_POLY_SET.Unfracture
    def inject_exterior(poly):
        original(poly)
        index = poly.NewOutline()
        for x, y in ((100, 100), (101, 100), (101, 101), (100, 101)):
            poly.Outline(index).Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    monkeypatch.setattr(pcbnew.SHAPE_POLY_SET, 'Unfracture', inject_exterior)
    proof = {}
    assert fr.filled_tht_exclusion_pins(b, evidence=proof) == {}
    assert not proof['complete']
    assert proof['reason'] == 'THT_normalized_fill_lower_containment_unproved'


def test_fractured_fill_identity_drift_cannot_reuse_its_contact_proof(monkeypatch):
    b, zone = fractured_fill_fixture()
    original = fr._tht_filled_material
    def change_after_extraction(item, layer, work):
        result = original(item, layer, work)
        fill = pcbnew.SHAPE_POLY_SET(item.GetFilledPolysList(layer))
        fill.RemoveAllContours()
        item.SetFilledPolysList(layer, fill)
        return result
    monkeypatch.setattr(fr, '_tht_filled_material', change_after_extraction)
    proof = {}
    assert fr.filled_tht_exclusion_pins(b, evidence=proof) == {}
    assert not proof['complete'] and proof['reason'] == 'THT_native_fill_epoch_changed'


def test_uncovered_physical_alias_keeps_the_whole_logical_pin():
    b, fp, pads, n = board_fixture(count=3)
    pads[1].SetNumber('1'); pads[2].SetNumber('2')
    filled_rectangle(b, n, (4, 4), (6, 6))
    proof = {}
    assert fr.filled_tht_exclusion_pins(b, evidence=proof) == {}
    assert proof['complete'] and proof['proven_contact_pin_count'] == 0


@pytest.mark.parametrize('attribute', [pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH,
                                     pcbnew.PAD_ATTRIB_SMD])
def test_importer_waives_junction_only_for_a_real_through_barrel(attribute):
    b, fp, pads, n = board_fixture(count=1, attribute=attribute)
    p = pads[0].GetPosition()
    for layer, end in ((pcbnew.F_Cu, (3, 5)), (pcbnew.In2_Cu, (7, 5))):
        t = pcbnew.PCB_TRACK(b); t.SetNet(n); t.SetLayer(layer)
        t.SetWidth(200000); t.SetStart(p); t.SetEnd(pcbnew.VECTOR2I_MM(*end)); b.Add(t)
    result = fr.synthesize_missing_layer_junction_vias(b)
    assert result['candidates'] == (0 if attribute == pcbnew.PAD_ATTRIB_PTH else 1)


def test_tracks_only_inside_the_pth_void_are_not_a_barrel_contact():
    b, fp, pads, n = board_fixture(count=1)
    tracks = []
    for layer in (pcbnew.F_Cu, pcbnew.In2_Cu):
        t = pcbnew.PCB_TRACK(b); t.SetNet(n); t.SetLayer(layer)
        t.SetWidth(50000); t.SetStart(pads[0].GetPosition())
        t.SetEnd(pcbnew.VECTOR2I_MM(5.1, 5)); b.Add(t); tracks.append(t)
    assert not fr._barrel_contacts_tracks(b, pads[0], tracks)
    assert fr.synthesize_missing_layer_junction_vias(b)['candidates'] > 0


def test_blind_via_cannot_waive_a_full_cross_layer_junction():
    b, fp, pads, n = board_fixture(count=0)
    via = pcbnew.PCB_VIA(b); via.SetNet(n); via.SetPosition(pcbnew.VECTOR2I_MM(5, 5))
    via.SetWidth(600000); via.SetDrill(300000)
    via.SetViaType(pcbnew.VIATYPE_BLIND); via.SetLayerPair(pcbnew.F_Cu, pcbnew.In1_Cu)
    b.Add(via)
    tracks = []
    for layer, end in ((pcbnew.F_Cu, (3, 5)), (pcbnew.In2_Cu, (7, 5))):
        t = pcbnew.PCB_TRACK(b); t.SetNet(n); t.SetLayer(layer)
        t.SetWidth(200000); t.SetStart(via.GetPosition())
        t.SetEnd(pcbnew.VECTOR2I_MM(*end)); b.Add(t); tracks.append(t)
    assert fr._through_barrel_layers(b, via) == ()
    assert not fr._barrel_contacts_tracks(b, via, tracks)
    assert fr.synthesize_missing_layer_junction_vias(b)['candidates'] == 1


@pytest.mark.parametrize('seconds', [True, 0, -.1, float('nan')])
def test_invalid_lease_retains_every_dsn_pin(seconds):
    b, fp, pads, n = board_fixture(); filled_rectangle(b, n)
    proof = {}
    assert fr.filled_tht_exclusion_pins(b, evidence=proof, timeout_s=seconds) == {}
    assert not proof['complete']
