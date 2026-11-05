"""Native cut tests with no product layout, net-name or refdes repair rules."""
import time
from unittest.mock import patch

import pcbnew
import pytest

import cec_kelvin_copper_cut as cut
from test_force_sense_evidence import fixture


def native_board_fixture(path, **kwargs):
    fixture(path, overlap_at_cut=True, **kwargs)
    board = pcbnew.LoadBoard(str(path))
    pads = {(fp.GetReference(), p.GetNumber()): p
            for fp in board.GetFootprints() for p in fp.Pads()}
    source = pads["MEASUREMENT_ANCHOR", "a"]
    sense = pads["SERIES_POS", "x"] if kwargs.get("filtered", True) else pads["ANALOG_SENSOR", "8"]
    authority = pads["POWER_IN", "in"]
    return board, source, sense, authority


def audit(values, **kwargs):
    board, source, sense, authority = values
    return cut.audit(board, source, sense, [authority], **kwargs)


def track(board, a, b, *, layer=pcbnew.F_Cu, width=.2):
    item = pcbnew.PCB_TRACK(board)
    item.SetNet(board.FindNet("RENAMED_FEED"))
    item.SetLayer(layer)
    item.SetStart(pcbnew.VECTOR2I_MM(*a))
    item.SetEnd(pcbnew.VECTOR2I_MM(*b))
    item.SetWidth(pcbnew.FromMM(width))
    board.Add(item)
    return item


def zone(board, rectangles, *, layer=pcbnew.F_Cu, hole=False):
    item = pcbnew.ZONE(board)
    item.SetNet(board.FindNet("RENAMED_FEED"))
    item.SetLayer(layer)
    filled = pcbnew.SHAPE_POLY_SET()
    for x1, y1, x2, y2 in rectangles:
        i = filled.NewOutline()
        for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)):
            filled.Outline(i).Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    if hole:
        filled.NewHole(0)
        for x, y in ((89, 76.2), (91, 76.2), (91, 76.8), (89, 76.8)):
            filled.Hole(0, 0).Append(pcbnew.FromMM(x), pcbnew.FromMM(y))
    item.Outline().Append(filled)
    item.SetFilledPolysList(layer, filled)
    item.SetIsFilled(True)
    board.Add(item)
    return item


@pytest.mark.parametrize("filtered,angle", [(False, 0), (True, 0), (True, 37), (True, 90), (True, 180)])
def test_caps_overlapping_only_inside_pad_are_isolated(tmp_path, filtered, angle):
    values = native_board_fixture(tmp_path/"source.kicad_pcb", filtered=filtered, angle=angle)
    board = values[0]
    before = [(cut.identity(t), t.GetStart().x, t.GetEnd().y) for t in board.GetTracks()]
    result = audit(values)
    assert result["complete"] and result["ok"] is True, result
    assert result["upper"]["reached_authority"] == []
    assert result["lower"]["reached_authority"] == []
    assert result["tracks_clipped"] and not result["full_kelvin_qualification"]
    assert before == [(cut.identity(t), t.GetStart().x, t.GetEnd().y) for t in board.GetTracks()]


def test_sidewall_bypass_not_endpoint_coincidence_is_detected(tmp_path):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    board = values[0]
    added = [track(board, a, b) for a, b in [((90.15, 72), (92, 72)),
             ((92, 72), (92, 77)), ((92, 77), (90.08, 77))]]
    result = audit(values)
    assert result["complete"] and result["ok"] is False, result
    assert result["physical_bypass_proved"]
    identifiers = {item["uuid"] for w in result["lower"]["witnesses"]
                   for node in w["path"] for item in node["contributors"]}
    assert {item.m_Uuid.AsString() for item in added}.issubset(identifiers)


@pytest.mark.parametrize("bypass", [False, True])
def test_actual_zone_copper_is_cut_and_islands_not_rejoined_by_uuid(tmp_path, bypass):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    zone(values[0], [(88 if bypass else 89.9, 72, 92 if bypass else 90.1, 78)])
    result = audit(values)
    assert result["complete"] and result["ok"] is (not bypass), result


def test_disconnected_filled_islands_stay_disconnected(tmp_path):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    zone(values[0], [(90, 72, 92, 73), (90, 77, 92, 78)])
    assert audit(values)["ok"] is True


@pytest.mark.parametrize("with_vias", [False, True])
def test_only_real_barrels_bridge_same_xy_layers(tmp_path, with_vias):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    board = values[0]
    track(board, (90, 73), (90, 77), layer=pcbnew.B_Cu)
    if with_vias:
        for xy in ((90, 73), (90, 77)):
            via = pcbnew.PCB_VIA(board)
            via.SetPosition(pcbnew.VECTOR2I_MM(*xy))
            via.SetNet(board.FindNet("RENAMED_FEED"))
            via.SetWidth(pcbnew.FromMM(.6))
            via.SetDrill(pcbnew.FromMM(.3))
            via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
            board.Add(via)
    result = audit(values)
    assert result["complete"] and result["ok"] is (not with_vias), result


def test_real_arc_bypass_is_included(tmp_path):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    board = values[0]
    arc = pcbnew.PCB_ARC(board)
    arc.SetNet(board.FindNet("RENAMED_FEED"))
    arc.SetLayer(pcbnew.F_Cu)
    arc.SetWidth(pcbnew.FromMM(.2))
    arc.SetStart(pcbnew.VECTOR2I_MM(90, 73))
    arc.SetMid(pcbnew.VECTOR2I_MM(93, 75))
    arc.SetEnd(pcbnew.VECTOR2I_MM(90, 77))
    board.Add(arc)
    result = audit(values)
    assert result["ok"] is False and result["physical_bypass_proved"], result


def test_unknown_fill_never_becomes_isolation_pass(tmp_path):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    item = zone(values[0], [(88, 72, 92, 78)])
    item.SetIsFilled(False)
    result = audit(values)
    assert result["ok"] is None and result["reason"] == "native_zone_fill_unavailable"


def test_missing_terminal_native_connection_is_not_vacuous_isolation(tmp_path):
    values = native_board_fixture(tmp_path/"source.kicad_pcb", fault="missing_copper")
    result = audit(values)
    assert result["ok"] is None and result["reason"] == "baseline_native_terminal_connectivity_incomplete"


@pytest.mark.parametrize("bound", ["MAX_ITEMS", "MAX_NET_ITEMS", "MAX_VERTICES", "MAX_COMPONENTS", "MAX_CONTACTS"])
def test_bounds_stop_without_positive_evidence(tmp_path, bound):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    with patch.object(cut, bound, 0):
        result = audit(values)
    assert result["ok"] is None and not result["complete"], result


def test_deadline_and_native_errors_cannot_pass(tmp_path):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    assert audit(values, deadline=time.monotonic()-1)["ok"] is None
    with patch.object(cut, "_shape", side_effect=RuntimeError("native failure")):
        result = audit(values)
    assert result["ok"] is None and not result["complete"]


def test_terminal_cut_overlap_fails_closed(tmp_path):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    values[2].SetPosition(values[1].GetPosition())
    result = audit(values)
    assert result["ok"] is None and result["reason"] == "sense_or_authority_terminal_intersects_cut"


def test_non_smd_cut_not_guessed(tmp_path):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    values[1].SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    result = audit(values)
    assert result["ok"] is None and result["reason"] == "unsupported_non_smd_shunt_cut"


@pytest.mark.parametrize("kind", ["valid", "empty", "aliased"])
def test_authority_iterator_is_snapshotted_once(tmp_path, kind):
    board, source, sense, authority = native_board_fixture(tmp_path/"source.kicad_pcb")
    values = [authority] if kind == "valid" else [] if kind == "empty" else [source]
    result = cut.audit(board, source, sense, (pad for pad in values))
    assert result["ok"] is (True if kind == "valid" else None), result


def test_infinite_authority_iterator_is_bounded(tmp_path):
    import itertools
    board, source, sense, authority = native_board_fixture(tmp_path/"source.kicad_pcb")
    result = cut.audit(board, source, sense, itertools.repeat(authority))
    assert result["ok"] is None and result["reason"] == "authority_terminal_budget_exhausted"


def test_pth_missing_internal_lands_cannot_silently_omit_barrel_contact(tmp_path):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    board, _, _, authority = values
    board.SetCopperLayerCount(6)
    authority.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
    authority.SetDrillSize(pcbnew.VECTOR2I_MM(.3, .3))
    layers = pcbnew.LSET()
    layers.AddLayer(pcbnew.F_Cu)
    layers.AddLayer(pcbnew.B_Cu)
    authority.SetLayerSet(layers)
    result = audit(values)
    assert result["ok"] is None and result["reason"] == "unsupported_partial_barrel_padstack"


def test_foreign_drill_identity_alias_cannot_drop_a_physical_void(tmp_path):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    board = values[0]
    vias = []
    for xy in ((92, 73), (92, 77)):
        via = pcbnew.Cast_to_PCB_VIA(pcbnew.Cast_to_BOARD_ITEM(vias[0].Clone())) if vias else pcbnew.PCB_VIA(board)
        via.SetNet(board.FindNet("RENAMED_LOAD"))
        via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        via.SetPosition(pcbnew.VECTOR2I_MM(*xy))
        via.SetWidth(pcbnew.FromMM(.6))
        via.SetDrill(pcbnew.FromMM(.3))
        board.Add(via)
        vias.append(via)
    assert vias[0].m_Uuid.AsString() == vias[1].m_Uuid.AsString()
    result = audit(values)
    assert result["ok"] is None and result["reason"] == "ambiguous_physical_drill_identity"


def test_last_native_work_cannot_expire_then_claim_success(tmp_path):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    original = cut._model
    def overrun(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[-2] is False and kwargs.get("cut_enabled", True):
            args[-1].deadline = time.monotonic()-1
        return result
    with patch.object(cut, "_model", side_effect=overrun):
        result = audit(values)
    assert result["ok"] is None and result["reason"] == "copper_cut_deadline_exhausted"


def test_unknown_curve_or_invalid_bound_cannot_become_empty_copper(tmp_path):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    with patch.object(cut, "_poly", side_effect=cut.Unknown("unlinearized_native_polygon_arc")):
        result = audit(values)
    assert result["ok"] is None and not result["complete"]


def test_multiface_smd_terminal_does_not_union_disconnected_islands(tmp_path):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    layer_set = pcbnew.LSET()
    layer_set.AddLayer(pcbnew.F_Cu)
    layer_set.AddLayer(pcbnew.B_Cu)
    values[2].SetLayerSet(layer_set)
    result = audit(values)
    assert result["ok"] is None
    assert result["reason"] == "terminal_copper_islands_not_physically_connected"


@pytest.mark.parametrize("kind", ["offset_pth", "undersized_via"])
def test_barrel_wall_outside_nominal_land_cannot_be_omitted(tmp_path, kind):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    board = values[0]
    if kind == "offset_pth":
        fp = pcbnew.FOOTPRINT(board)
        fp.SetReference("EXTRA_PLATED_TERMINAL")
        board.Add(fp)
        item = pcbnew.PAD(fp)
        item.SetNumber("unused_number")
        item.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        item.SetLayerSet(pcbnew.PAD.PTHMask())
        item.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        item.SetSize(pcbnew.VECTOR2I_MM(.6, .6))
        item.SetDrillSize(pcbnew.VECTOR2I_MM(.3, .3))
        item.SetOffset(pcbnew.VECTOR2I_MM(2, 0))
        fp.Add(item)
    else:
        item = pcbnew.PCB_VIA(board)
        item.SetWidth(pcbnew.FromMM(.2))
        item.SetDrill(pcbnew.FromMM(.3))
        item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        board.Add(item)
    item.SetPosition(pcbnew.VECTOR2I_MM(90.2, 77))
    item.SetNet(board.FindNet("RENAMED_FEED"))
    result = audit(values)
    assert result["ok"] is None and result["reason"] == "plated_bore_not_enclosed_by_native_land"


def linear_boundary(tmp_path, *, shape=pcbnew.PAD_SHAPE_RECT, excess_nm=0,
                    angle=0, translation=(0, 0)):
    """Force fill stops exactly at an interior straight edge of the cut pad."""
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    board, source, _, _ = values
    source.SetShape(shape)
    source.SetRoundRectRadiusRatio(.125)
    item = zone(board, [(88, 64, 92, 76)])
    fill = pcbnew.SHAPE_POLY_SET()
    fill.NewOutline()
    for x,y in ((88_000_000,64_000_000),(92_000_000,64_000_000),
                (92_000_000,76_000_000+excess_nm),(88_000_000,76_000_000+excess_nm)):
        fill.Outline(0).Append(x,y)
    item.SetFilledPolysList(pcbnew.F_Cu,fill)
    origin, delta = pcbnew.VECTOR2I(0,0), pcbnew.VECTOR2I(*translation)
    rotation = pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T)
    for index,fp in enumerate(board.GetFootprints()):
        fp.SetReference(f"RENAMED_NATIVE_{index}")
        fp.Rotate(origin,rotation)
        fp.SetPosition(fp.GetPosition()+delta)
    for conductor in [*board.GetTracks(),*board.Zones()]:
        conductor.Rotate(origin,rotation)
        conductor.Move(delta)
    return values, item


@pytest.mark.parametrize("shape",[pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT])
@pytest.mark.parametrize("angle,translation",[(0,(0,0)),(90,(12_345_679,-3_579_113)),
    (180,(-11_357_921,23_579_113)),(270,(101_123_457,11_345_679))])
def test_exact_linear_boundary_isolation_is_renamed_translated_and_cardinal(tmp_path,shape,angle,translation):
    values,_ = linear_boundary(tmp_path,shape=shape,angle=angle,translation=translation)
    result = audit(values)
    assert result["complete"] and result["ok"] is True, result
    assert result["exact_linear_identity_verified"]
    assert result["numerical_guard_nm"] == 2 and result["approximation_error_nm"] == 1000
    certificates = result["exact_linear_refinements"]
    assert {c["kind"] for c in certificates if c["applied"]} == {
        "source_interior_core","filled_zone_integer_axis_bounds"}
    assert all(len(c["geometry_sha256"]) == 64 for c in certificates)


def test_linear_refinement_resolves_only_preexisting_guard_correlation(tmp_path):
    values,_ = linear_boundary(tmp_path)
    def old_fill(item,layer,upper,work):
        return cut._envelope(cut._poly(item.GetFilledPolysList(layer),work),upper)
    with patch.object(cut,"_source_cut",side_effect=cut._shape), \
         patch.object(cut,"_filled_shape",side_effect=old_fill):
        original = audit(values)
    assert original["ok"] is None and original["upper"]["reached_authority"]
    assert original["lower"]["reached_authority"] == []
    assert audit(values)["ok"] is True


@pytest.mark.parametrize("excess_nm,expected",[(1,None),(1000,False)])
def test_exact_bounds_preserve_real_one_nm_and_one_um_bridges(tmp_path,excess_nm,expected):
    values,item = linear_boundary(tmp_path,excess_nm=excess_nm)
    result = audit(values)
    assert result["ok"] is expected, result
    assert result["upper"]["reached_authority"]
    certificate = next(c for c in result["exact_linear_refinements"]
                       if c["identity"]["uuid"] == item.m_Uuid.AsString())
    assert certificate["bounds_nm"][3] == 76_000_000+excess_nm
    if excess_nm == 1000:
        assert result["physical_bypass_proved"]


@pytest.mark.parametrize("edge",[False,True])
def test_exterior_point_and_edge_contacts_remain_possible_copper(tmp_path,edge):
    values = native_board_fixture(tmp_path/"source.kicad_pcb")
    item = zone(values[0],[(90,72,93,73),(92,72,93,77),
                          (90,76.5 if edge else 77,92,78)])
    result = audit(values)
    assert result["ok"] is not True and result["upper"]["reached_authority"], result
    assert any(i["uuid"] == item.m_Uuid.AsString()
               for w in result["upper"]["witnesses"] for p in w["path"] for i in p["contributors"])


@pytest.mark.parametrize("shape",[pcbnew.PAD_SHAPE_RECT,pcbnew.PAD_SHAPE_ROUNDRECT])
@pytest.mark.parametrize("angle",[0,90,180,270])
@pytest.mark.parametrize("layer",[pcbnew.F_Cu,pcbnew.B_Cu])
def test_odd_size_core_is_rounded_inward_and_curves_keep_original_guard(tmp_path,shape,angle,layer):
    _,source,_,_ = native_board_fixture(tmp_path/"source.kicad_pcb")
    layers = pcbnew.LSET()
    layers.AddLayer(layer)
    source.SetLayerSet(layers)
    source.SetShape(shape)
    source.SetSize(pcbnew.VECTOR2I(3_000_001,1_000_003))
    source.SetRoundRectRadiusRatio(.2)
    source.SetOrientationDegrees(angle)
    source.SetPosition(pcbnew.VECTOR2I(-17_345_679,32_579_113))
    work = cut._Work(time.monotonic()+10)
    lower = cut._source_cut(source,layer,False,work)
    upper = cut._source_cut(source,layer,True,work)
    certificate = next(iter(work.linear_certificates.values()))
    assert certificate["applied"], certificate
    x,y = source.GetPosition()
    sx,sy = source.GetSize(layer)
    if angle % 180 == 90:
        sx,sy = sy,sx
    for x1,y1,x2,y2 in certificate["core_rectangles_nm"]:
        assert 2*x1 >= 2*x-sx and 2*x2 <= 2*x+sx
        assert 2*y1 >= 2*y-sy and 2*y2 <= 2*y+sy
    assert upper.equals(cut._shape(source,layer,True,work))
    assert upper.covers(lower)
    from shapely.geometry import box
    from shapely.ops import unary_union
    core = unary_union([box(*r) for r in certificate["core_rectangles_nm"]])
    assert lower.difference(core).equals(cut._shape(source,layer,False,work).difference(core))
    # Independently replay the integer core through native integer Booleans.
    # Every certified rectangle, not merely its four sampled corners, must
    # subtract completely against the native ERROR_INSIDE polygon.
    native = pcbnew.SHAPE_POLY_SET()
    source.TransformShapeToPolygon(native,layer,0,cut.ERROR_NM,pcbnew.ERROR_INSIDE,False)
    for x1,y1,x2,y2 in certificate["core_rectangles_nm"]:
        rectangle = pcbnew.SHAPE_POLY_SET()
        rectangle.NewOutline()
        for px,py in ((x1,y1),(x2,y1),(x2,y2),(x1,y2)):
            rectangle.Outline(0).Append(px,py)
        rectangle.BooleanSubtract(native)
        assert rectangle.OutlineCount() == 0
    cut._validate_linear_epochs(work)


@pytest.mark.parametrize("one_nm",[False,True])
def test_rational_output_proof_rejects_even_sub_nm_exterior_vertex(tmp_path,one_nm):
    import math
    from shapely.geometry import box
    _,source,_,_ = native_board_fixture(tmp_path/"source.kicad_pcb")
    native = pcbnew.SHAPE_POLY_SET()
    source.TransformShapeToPolygon(native,pcbnew.F_Cu,0,cut.ERROR_NM,pcbnew.ERROR_INSIDE,False)
    outside = 91_000_001 if one_nm else math.nextafter(91_000_000,math.inf)
    work = cut._Work(time.monotonic()+10)
    assert not cut._convex_core_contained(native,[],work,
        returned_geometry=box(89_000_000,74_000_000,outside,76_000_000))


@pytest.mark.parametrize("kind",["oval","circle","custom","noncardinal","offset","chamfer","delta"])
def test_unsupported_source_shapes_never_gain_an_exact_core(tmp_path,kind):
    _,source,_,_ = native_board_fixture(tmp_path/"source.kicad_pcb")
    if kind in ("oval","circle","custom"):
        source.SetShape({"oval":pcbnew.PAD_SHAPE_OVAL,"circle":pcbnew.PAD_SHAPE_CIRCLE,
                         "custom":pcbnew.PAD_SHAPE_CUSTOM}[kind])
    elif kind == "noncardinal":
        source.SetOrientationDegrees(37)
    elif kind == "offset":
        source.SetOffset(pcbnew.VECTOR2I(1,0))
    elif kind == "chamfer":
        source.SetChamferPositions(1)
    else:
        source.SetDelta(pcbnew.VECTOR2I(1,0))
    work = cut._Work(time.monotonic()+10)
    result = cut._source_cut(source,pcbnew.F_Cu,False,work)
    assert result.equals(cut._shape(source,pcbnew.F_Cu,False,work))
    assert not next(iter(work.linear_certificates.values()))["applied"]


def test_unsupported_oval_guard_correlation_stays_unknown(tmp_path):
    values,_ = linear_boundary(tmp_path,shape=pcbnew.PAD_SHAPE_OVAL)
    # A horizontal oval has a straight inner edge. A square OVAL is a circle,
    # whose curved edge would instead expose real sense/force contact here.
    values[1].SetSize(pcbnew.VECTOR2I_MM(4,2))
    result = audit(values)
    assert result["ok"] is None and not result["physical_bypass_proved"], result
    assert not next(c for c in result["exact_linear_refinements"]
                    if c["kind"] == "source_interior_core")["applied"]


def test_disagreeing_native_inside_core_certificate_falls_back(tmp_path):
    values,_ = linear_boundary(tmp_path)
    with patch.object(cut,"_convex_core_contained",return_value=False):
        result = audit(values)
    assert result["ok"] is None, result
    assert not next(c for c in result["exact_linear_refinements"]
                    if c["kind"] == "source_interior_core")["applied"]


@pytest.mark.parametrize("change",["position","ref","number","net","size","orientation","offset","uuid"])
def test_source_epoch_rejects_identity_and_geometry_mutations(tmp_path,change):
    board,source,_,_ = native_board_fixture(tmp_path/"source.kicad_pcb")
    work = cut._Work(time.monotonic()+10)
    cut._source_cut(source,pcbnew.F_Cu,False,work)
    if change == "position":
        source.Move(pcbnew.VECTOR2I(1,0))
    elif change == "ref":
        source.GetParentFootprint().SetReference("CHANGED_REFERENCE")
    elif change == "number":
        source.SetNumber("CHANGED_NUMBER")
    elif change == "net":
        source.SetNet(board.FindNet("RENAMED_LOAD"))
    elif change == "size":
        source.SetSize(pcbnew.VECTOR2I(2_000_001,2_000_000))
    elif change == "orientation":
        source.SetOrientationDegrees(90)
    elif change == "offset":
        source.SetOffset(pcbnew.VECTOR2I(1,0))
    else:
        source.m_Uuid.Increment()
    with pytest.raises(cut.Unknown,match="exact_linear_geometry_identity_changed"):
        cut._validate_linear_epochs(work)


@pytest.mark.parametrize("change",["fill","move","net","uuid","replace"])
def test_zone_epoch_rejects_changed_or_replaced_native_fill(tmp_path,change):
    values,item = linear_boundary(tmp_path)
    board = values[0]
    work = cut._Work(time.monotonic()+10)
    cut._filled_shape(item,pcbnew.F_Cu,True,work)
    if change == "fill":
        replacement = pcbnew.SHAPE_POLY_SET(item.GetFilledPolysList(pcbnew.F_Cu))
        replacement.Move(pcbnew.VECTOR2I(1,0))
        item.SetFilledPolysList(pcbnew.F_Cu,replacement)
    elif change == "move":
        item.Move(pcbnew.VECTOR2I(1,0))
    elif change == "net":
        item.SetNet(board.FindNet("RENAMED_LOAD"))
    elif change == "uuid":
        item.m_Uuid.Increment()
    else:
        replacement = pcbnew.Cast_to_ZONE(pcbnew.Cast_to_BOARD_ITEM(item.Clone()))
        board.Remove(item)
        board.Add(replacement)
    with pytest.raises(cut.Unknown,match="exact_linear_(geometry_identity_changed|native_object_not_on_board)"):
        cut._validate_linear_epochs(work)


@pytest.mark.parametrize("kind",["source","zone"])
def test_identity_change_within_native_snapshot_fails_closed(tmp_path,kind):
    values,item = linear_boundary(tmp_path)
    board,source,_,_ = values
    original = cut._poly
    def mutate(native,work):
        result = original(native,work)
        if kind == "source":
            source.GetParentFootprint().SetReference("CHANGED_DURING_NATIVE_READ")
        else:
            item.SetNet(board.FindNet("RENAMED_LOAD"))
        return result
    work = cut._Work(time.monotonic()+10)
    with patch.object(cut,"_poly",side_effect=mutate):
        with pytest.raises(cut.Unknown,match="exact_linear_geometry_identity_changed"):
            if kind == "source":
                cut._source_cut(source,pcbnew.F_Cu,False,work)
            else:
                cut._filled_shape(item,pcbnew.F_Cu,True,work)


def test_late_source_movement_never_returns_positive_certificate(tmp_path):
    values,_ = linear_boundary(tmp_path)
    original = cut._model
    def move_after_last_model(*args,**kwargs):
        result = original(*args,**kwargs)
        if args[-2] is False and kwargs.get("cut_enabled",True):
            values[1].Move(pcbnew.VECTOR2I(1,0))
        return result
    with patch.object(cut,"_model",side_effect=move_after_last_model):
        result = audit(values)
    assert result["ok"] is None and not result["exact_linear_identity_verified"]
    assert result["reason"] == "exact_linear_geometry_identity_changed"


@pytest.mark.parametrize("angle",[0,90,180,270])
def test_native_refilled_irregular_zone_preserves_material_without_monotonic_covers(tmp_path,angle):
    # The native filler produces the real linearized concave/rounded fill
    # implicated by branch replay, rather than our simple rectangle helper.
    # In GEOS 3.13.1, intersecting its guarded envelope with the exact bbox
    # can return covers=False against that envelope despite empty difference.
    from test_kelvin_branch_repair import fixture as branch_fixture
    path = tmp_path/"refilled.kicad_pcb"
    row = branch_fixture(path,angle=angle,renamed=True)
    saved = path.read_bytes()
    board = pcbnew.LoadBoard(str(path))
    item = next(z for z in board.Zones() if z.m_Uuid.AsString() == row["zone"])
    work = cut._Work(time.monotonic()+10)
    native = pcbnew.SHAPE_POLY_SET(item.GetFilledPolysList(pcbnew.F_Cu))
    original_format = native.Format()
    material = cut._poly(native,work)
    assert native.TotalVertices() > 4
    refined = cut._filled_shape(item,pcbnew.F_Cu,True,work)
    lower = cut._filled_shape(item,pcbnew.F_Cu,False,work)
    assert refined.is_valid and refined.covers(material) and refined.covers(lower)
    assert lower.equals(cut._envelope(material,False))
    certificate = next(iter(work.linear_certificates.values()))
    assert certificate["applied"] and certificate["bounds_nm"] == list(material.bounds)
    cut._validate_linear_epochs(work)
    assert item.GetFilledPolysList(pcbnew.F_Cu).Format() == original_format
    assert path.read_bytes() == saved
