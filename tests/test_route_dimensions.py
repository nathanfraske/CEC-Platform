"""Contract mutation tests independent of product names and part identities."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cec_route_dimensions as dimensions


def settings():
    return {"classes": [
        {"name": "Default", "track_width": 0.2, "via_diameter": 0.5, "via_drill": 0.2},
        {"name": "Supply", "track_width": 0.65, "via_diameter": 0.7, "via_drill": 0.4}],
        "netclass_patterns": [{"netclass": "Supply", "pattern": "/FEED"}],
        "netclass_assignments": {"/control/FEED": ["Default"]}}


def test_nonload_width_is_only_a_proposal_and_never_mutates_parent_or_project(tmp_path):
    path = tmp_path / 'renamed.kicad_pcb'
    project = path.with_suffix('.kicad_pro')
    project.write_text(json.dumps({'net_settings': settings()}))
    before = project.read_bytes()
    board = SimpleNamespace(GetDesignSettings=lambda: SimpleNamespace(m_TrackMinWidth=250001))
    parent = dimensions.compile_spec(dimensions.NetclassTable(settings()).resolve('/FEED'),
        current={'required_by_layer_mm': {'F.Cu': 4.8}}, role='trunk')
    original = json.loads(json.dumps(parent))
    result = dimensions.nonload_measurement_width(board, path, '/FEED', parent_spec=parent)
    assert result['width_nm'] == 250001
    assert result['basis'] == 'explicit_project_Default_and_native_board_minimum'
    assert result['manufacturer_input_and_single_contact_and_partition_proof_required']
    for key in ('clearance_or_via_requirements_changed', 'numeric_load_assumed',
                'trunk_capacity_credited', 'admission_authority'):
        assert result[key] is False
    assert parent == original and project.read_bytes() == before
    assert parent['track_width'] == .65
    assert parent['track_width_by_layer_mm']['F.Cu'] == 4.8


@pytest.mark.parametrize('mode', ['absent', 'no_default', 'no_width', 'unrelated_project', 'ambiguous_neighbours'])
def test_nonload_width_without_explicit_project_default_keeps_strict_parent(tmp_path, mode):
    path = tmp_path / 'renamed.kicad_pcb'
    if mode in ('unrelated_project', 'ambiguous_neighbours'):
        for name in (('other',) if mode=='unrelated_project' else ('a','b')):
            (tmp_path/(name+'.kicad_pro')).write_text(json.dumps({'net_settings': settings()}))
    elif mode != 'absent':
        classes = [{'name': 'Rail', 'track_width': 2.5}]
        if mode == 'no_width': classes.append({'name': 'Default'})
        path.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings': {'classes': classes}}))
    board = SimpleNamespace(GetDesignSettings=lambda: SimpleNamespace(m_TrackMinWidth=200000))
    result = dimensions.nonload_measurement_width(board, path, 'arbitrary',
        parent_spec={'name': 'Rail', 'track_width': 2.5, 'clearance': .3})
    assert result['width_nm'] == 2500000
    assert result['basis'] == 'unchanged_parent_net_width'
    assert result['authored_ordinary_class'] is None


@pytest.mark.parametrize('fault', ['corrupt', 'zero', 'boolean', 'negative'])
def test_nonload_width_cannot_guess_around_bad_or_ambiguous_authority(tmp_path, fault):
    path = tmp_path / 'renamed.kicad_pcb'
    if fault == 'corrupt': path.with_suffix('.kicad_pro').write_text('broken')
    else:
        width = {'zero': 0, 'boolean': True, 'negative': -.1}[fault]
        path.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings': {
            'classes': [{'name': 'Default', 'track_width': width}]}}))
    board = SimpleNamespace(GetDesignSettings=lambda: SimpleNamespace(m_TrackMinWidth=200000))
    with pytest.raises(dimensions.DimensionContractError):
        dimensions.nonload_measurement_width(board, path, 'arbitrary',
            parent_spec={'name': 'Rail', 'track_width': 2.5})


def test_nonload_width_cannot_shrink_a_larger_authored_ordinary_requirement(tmp_path):
    path = tmp_path / 'renamed.kicad_pcb'
    path.with_suffix('.kicad_pro').write_text(json.dumps({'net_settings': {
        'classes': [{'name': 'Default', 'track_width': .4}]}}))
    board = SimpleNamespace(GetDesignSettings=lambda: SimpleNamespace(m_TrackMinWidth=200000))
    result = dimensions.nonload_measurement_width(board, path, 'arbitrary',
        parent_spec={'name': 'Rail', 'track_width': 2.5})
    assert result['width_nm'] == 400000


@pytest.mark.parametrize("net,expected", [("/FEED", "Supply"),
    ("/partition/FEED", "Supply"), ("/control/FEED", "Default"),
    ("/FEED_EXTRA", "Default")])
def test_hierarchy_and_explicit_precedence(net, expected):
    assert dimensions.NetclassTable(settings()).resolve_name(net) == expected


def test_class_board_and_annular_minima_are_all_respected():
    spec = dict(via_diameter=0.5, via_drill=0.4)
    limits = dict(via_diameter=0.6, via_drill=0.3, annular=0.15)
    assert dimensions.ordinary_via_geometry(spec, limits) == pytest.approx((0.7, 0.4))
    assert dimensions.ordinary_via_geometry(spec, limits, requested=(0.9, 0.5)) == (0.9, 0.5)


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan")])
def test_invalid_dimensions_cannot_pass_comparisons(value):
    with pytest.raises(dimensions.DimensionContractError):
        dimensions.ordinary_via_geometry({"via_drill": value})
    import cec_fab_profile as fab
    profile = next(iter(fab.PROFILES.values()))
    assert not fab.pofv_dimensions(profile, 0.35, value)[0]
    with pytest.raises(dimensions.DimensionContractError):
        dimensions.current_trace_widths({"amps": 1.0}, ("F.Cu",),
            "jlcpcb_6l_pofv_signal", rise_c=value)


def test_trunk_widths_cannot_leak_into_local_branch_requirements():
    spec = dimensions.NetclassTable(settings()).resolve("/FEED")
    current = {"required_by_layer_mm": {"F.Cu": 1.2, "In2.Cu": 4.8}}
    trunk = dimensions.compile_spec(spec, current=current, role="trunk")
    assert trunk["track_width_by_layer_mm"]["In2.Cu"] == 4.8
    branch = dimensions.compile_spec(trunk, current=current, role="branch")
    assert branch["track_width"] == 0.65
    assert "track_width_by_layer_mm" not in branch
    with pytest.raises(dimensions.DimensionContractError):
        dimensions.compile_spec(spec, role="trunk")
    with pytest.raises(dimensions.DimensionContractError):
        dimensions.compile_spec(spec, role="qualified_because_small")


def test_current_margin_is_applied_once_and_inner_copper_is_distinct():
    import cec_fab_profile as fab
    profile = "jlcpcb_6l_pofv_signal"
    already_margined = dict(amps=0.8, margin_included=True, geometry_margin=1.0)
    widths = dimensions.current_trace_widths(already_margined, ("F.Cu", "In2.Cu"), profile)
    assert widths["In2.Cu"] > widths["F.Cu"]
    assert widths["F.Cu"] == pytest.approx(fab.ipc2221_required_width_mm(
        0.8, "F.Cu", profile_name=profile, margin=1.0))
    with pytest.raises(dimensions.DimensionContractError, match="another geometry margin"):
        dimensions.current_trace_widths({**already_margined, "geometry_margin": 1.25},
                                        ("F.Cu",), profile)


def test_router_repair_and_signoff_use_the_same_hierarchical_class(tmp_path):
    import cec_fr
    import cec_constraints
    path = tmp_path / "artifact.kicad_pcb"
    path.with_suffix(".kicad_pro").write_text(json.dumps({"net_settings": settings()}))
    router = cec_fr._project_netclass_resolver(str(path))
    classes, signoff = cec_constraints._netclass_rules(str(path))
    for net in ("/FEED", "/partition/FEED", "/control/FEED"):
        assert router(net)["name"] == signoff(net)
        assert router(net)["via_drill"] == classes[signoff(net)]["via_drill"]


def test_corrupt_or_ambiguous_authority_is_not_a_small_default(tmp_path):
    import cec_fr
    import cec_constraints
    board = str(tmp_path / "artifact.kicad_pcb")
    project = tmp_path / "artifact.kicad_pro"
    project.write_text("broken")
    for resolver in (cec_fr._project_netclass_resolver, cec_constraints._netclass_rules):
        with pytest.raises(dimensions.DimensionContractError):
            resolver(board)
    project.unlink()
    (tmp_path / "a.kicad_pro").write_text("{}")
    (tmp_path / "b.kicad_pro").write_text("{}")
    with pytest.raises(dimensions.DimensionContractError, match="ambiguous"):
        dimensions.NetclassTable.from_board_path(board)


def test_margin_provenance_survives_priority_routing(monkeypatch, tmp_path):
    import cec_current_topology as topology
    import cec_fab_profile as fab
    import cec_synth_pipeline as synth
    authority = dict(amps=0.8, geometry_margin=1.0, margin_included=True, source="budget")
    monkeypatch.setattr(synth, "spec_net_current_contract", lambda *_: authority)
    monkeypatch.setattr(topology, "board_current_domains", lambda *_args, **_kwargs: {
        "FEED": dict(amps=0.8, complete=True, authority_refs=("SOURCE", "LOAD"))})
    monkeypatch.setattr(fab, "active_profile_name", lambda *_args, **_kwargs: "jlcpcb_6l_pofv_signal")
    monkeypatch.setattr(fab, "enabled_copper_layers", lambda *_: ("F.Cu", "In2.Cu"))
    monkeypatch.setattr(fab, "referenced_signal_layers", lambda *_args, **_kwargs: ("F.Cu", "In2.Cu"))
    # Layer authority now comes from the actual saved project; an opaque
    # object is not a board fixture. Keep both original margin assertions,
    # supplying an explicit non-Power class without mocking the resolver.
    pcbnew = pytest.importorskip("pcbnew")
    path = tmp_path / "margin.kicad_pcb"
    board = pcbnew.CreateEmptyBoard()
    pcbnew.SaveBoard(str(path), board)
    path.with_suffix(".kicad_pro").write_text(json.dumps({"net_settings": {
        "classes": [{"name": "Default", "track_width": 0.2,
                     "clearance": 0.2, "via_diameter": 0.6, "via_drill": 0.3}],
        "netclass_assignments": {"FEED": "Default"}, "netclass_patterns": []}}))
    contract = topology.route_width_contracts(pcbnew.LoadBoard(str(path)))["FEED"]
    assert contract["geometry_margin"] == 1.0
    assert contract["current_authority"]["margin_included"]


def test_import_mutation_is_repaired_to_the_same_solver_contract(tmp_path):
    pcbnew = pytest.importorskip("pcbnew")
    import cec_fr
    import cec_constraints
    path = tmp_path / "artifact.kicad_pcb"
    path.with_suffix(".kicad_pro").write_text(json.dumps({"net_settings": settings()}))
    board = pcbnew.CreateEmptyBoard()
    rules = board.GetDesignSettings()
    rules.m_TrackMinWidth = pcbnew.FromMM(0.15)
    rules.m_ViasMinSize = pcbnew.FromMM(0.5)
    rules.m_MinThroughDrill = pcbnew.FromMM(0.2)
    rules.m_ViasMinAnnularWidth = pcbnew.FromMM(0.15)
    net = pcbnew.NETINFO_ITEM(board, "/partition/FEED"); board.Add(net)
    via = pcbnew.PCB_VIA(board)
    via.SetPosition(pcbnew.VECTOR2I_MM(10, 10))
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    via.SetWidth(pcbnew.FromMM(0.4)); via.SetDrill(pcbnew.FromMM(0.2))
    via.SetNet(net); board.Add(via)
    pcbnew.SaveBoard(str(path), board)
    # Saving a newly constructed board can emit its default project settings.
    # Install the explicit test authority after that materialization boundary.
    path.with_suffix(".kicad_pro").write_text(json.dumps({"net_settings": settings()}))
    expected = dimensions.project_resolver(str(path), board=board)(net.GetNetname())
    assert expected["name"] == "Supply"
    assert not cec_constraints._chk_netclass_geom(board, str(path), {})[0]
    result = cec_fr.normalize_netclass_geometry(board, str(path))
    assert result["vias"] == 1
    assert via.GetWidth(via.TopLayer()) / 1e6 == expected["via_diameter"]
    assert via.GetDrillValue() / 1e6 == expected["via_drill"]
    assert cec_constraints._chk_netclass_geom(board, str(path), {})[0]
    assert cec_fr.normalize_netclass_geometry(board, str(path))["vias"] == 0


def test_replay_carries_executable_sidecars_and_never_adopts(tmp_path, monkeypatch):
    import cec_route_dimension_replay as trial
    import cec_fab_review_regression as regression
    source = tmp_path / "input.kicad_pcb"
    source.write_text("immutable board fixture")
    source.with_suffix(".kicad_pro").write_text(json.dumps({"net_settings": settings()}))
    source.with_suffix(".pourplan.json").write_text('{"schema":1,"ownership":"fixture"}')
    source.with_suffix(".pourfirst-state.json").write_text('{"schema":1,"regions":[]}')
    def normalize(command, **_kwargs):
        Path(command[command.index("--out") + 1]).write_text('{"tracks":0,"vias":0}')
        return SimpleNamespace(returncode=0, stderr="")
    monkeypatch.setattr(trial.subprocess, "run", normalize)
    monkeypatch.setattr(regression, "_run_worker", lambda *_args: {"blockers": []})
    result = trial.replay(source, tmp_path / "trial", "fixture")
    for phase in ("before", "proposal"):
        for extension in (".pourplan.json", ".pourfirst-state.json", ".kicad_pro"):
            clone = tmp_path / "trial" / phase / ("input" + extension)
            if extension == ".kicad_pro":
                # The common copy helper rebinds only project metadata.
                assert json.loads(clone.read_text())["net_settings"] == settings()
            else:
                assert clone.read_bytes() == source.with_suffix(extension).read_bytes()
    assert result["source_unchanged"]
    assert result["adopted"] is False
    assert source.read_text() == "immutable board fixture"
    with pytest.raises(FileExistsError):
        trial.replay(source, tmp_path / "trial", "fixture")


@pytest.mark.parametrize("obstacle", ["same_net_pad", "same_net_drill", "foreign_pad"])
def test_growth_refuses_new_assembly_hole_or_copper_fault(tmp_path, obstacle):
    pcbnew = pytest.importorskip("pcbnew")
    import cec_fr
    path = tmp_path / "artifact.kicad_pcb"
    path.with_suffix(".kicad_pro").write_text(json.dumps({"net_settings": settings()}))
    board = pcbnew.CreateEmptyBoard()
    board.GetDesignSettings().m_HoleToHoleMin = pcbnew.FromMM(0.25)
    own = pcbnew.NETINFO_ITEM(board, "/FEED"); board.Add(own)
    foreign = pcbnew.NETINFO_ITEM(board, "UNRELATED"); board.Add(foreign)
    if obstacle == "foreign_pad":
        item = pcbnew.PCB_TRACK(board)
        item.SetStart(pcbnew.VECTOR2I_MM(5, 10)); item.SetEnd(pcbnew.VECTOR2I_MM(10, 10))
        item.SetWidth(pcbnew.FromMM(0.2)); item.SetLayer(pcbnew.F_Cu)
        at, size = (7.5, 10.4), 0.4
    else:
        item = pcbnew.PCB_VIA(board)
        item.SetPosition(pcbnew.VECTOR2I_MM(10, 10))
        item.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        item.SetWidth(pcbnew.FromMM(0.4)); item.SetDrill(pcbnew.FromMM(0.2))
        at, size = (10.55, 10), 0.5
    item.SetNet(own); board.Add(item)
    if obstacle == "same_net_drill":
        nearby = pcbnew.PCB_VIA(board)
        nearby.SetPosition(pcbnew.VECTOR2I_MM(10.52, 10))
        nearby.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        nearby.SetWidth(pcbnew.FromMM(0.4)); nearby.SetDrill(pcbnew.FromMM(0.2))
        nearby.SetNet(own); nearby.SetLocked(True); board.Add(nearby)
    else:
        fp = pcbnew.FOOTPRINT(board); fp.SetReference("OBSTACLE")
        pad = pcbnew.PAD(fp); pad.SetNumber("1")
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetSize(pcbnew.VECTOR2I_MM(size, size)); pad.SetPosition(pcbnew.VECTOR2I_MM(*at))
        layer_set = pcbnew.LSET(); layer_set.AddLayer(pcbnew.F_Cu)
        pad.SetLayerSet(layer_set)
        pad.SetNet(foreign if obstacle == "foreign_pad" else own)
        fp.Add(pad); board.Add(fp)
    pcbnew.SaveBoard(str(path), board)
    path.with_suffix(".kicad_pro").write_text(json.dumps({"net_settings": settings()}))
    if obstacle == "same_net_drill":
        import cec_decoupler_cell
        hole_test = cec_decoupler_cell._hole_to_hole_clear(
            board, item.GetPosition(), 0.4,
            ignore_via_uuids={item.m_Uuid.AsString()})
        assert not hole_test[0], (hole_test, board.GetDesignSettings().m_HoleToHoleMin,
                                 [t.m_Uuid.AsString() for t in board.GetTracks()])
    result = cec_fr.normalize_netclass_geometry(board, str(path))
    assert result["tracks"] == result["vias"] == 0, result
    refusal = next(r for r in result["refused_growth"] if r["uuid"] == item.m_Uuid.AsString())
    assert refusal["action"] == "reroute_required_no_in_place_growth"
    if obstacle != "foreign_pad":
        assert item.GetWidth(item.TopLayer()) / 1e6 == 0.4
        assert item.GetDrillValue() / 1e6 == 0.2


@pytest.mark.parametrize("profiled", [False, True])
def test_on_pad_repair_requires_explicit_process_and_preserves_copper(tmp_path, profiled):
    pcbnew = pytest.importorskip("pcbnew")
    import cec_fr
    import cec_fab_profile as fab
    board = pcbnew.CreateEmptyBoard(); board.SetCopperLayerCount(6)
    if profiled:
        props = board.GetProperties()
        props["CEC_FAB_PROFILE"] = "jlcpcb_6l_pofv_signal"
        board.SetProperties(props)
    net = pcbnew.NETINFO_ITEM(board, "/FEED"); board.Add(net)
    fp = pcbnew.FOOTPRINT(board); fp.SetReference("ENDPOINT")
    pad = pcbnew.PAD(fp); pad.SetNumber("1"); pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    pad.SetShape(pcbnew.PAD_SHAPE_RECT); pad.SetSize(pcbnew.VECTOR2I_MM(1, 1))
    pad.SetPosition(pcbnew.VECTOR2I_MM(10, 10)); pad.SetNet(net)
    layers = pcbnew.LSET(); layers.AddLayer(pcbnew.F_Cu); pad.SetLayerSet(layers)
    fp.Add(pad); board.Add(fp)
    via = pcbnew.PCB_VIA(board); via.SetPosition(pad.GetPosition())
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetNet(net)
    via.SetWidth(pcbnew.FromMM(0.35)); via.SetDrill(pcbnew.FromMM(0.15)); board.Add(via)
    path = tmp_path / "artifact.kicad_pcb"; pcbnew.SaveBoard(str(path), board)
    path.with_suffix(".kicad_pro").write_text(json.dumps({"net_settings": settings()}))
    result = cec_fr.normalize_netclass_geometry(board, str(path))
    assert via.GetWidth(via.TopLayer()) / 1e6 == 0.35
    if profiled:
        assert result["repaired_qualified_pofv_vias"] == 1
        assert via.GetDrillValue() / 1e6 == 0.25
        assert fab.via_pad_decision(board, pad, via.GetPosition(),
            via.GetWidth(via.TopLayer()), via.GetDrillValue(), via.GetNetCode())[0]
        assert cec_fr.normalize_netclass_geometry(board, str(path))["vias"] == 0
    else:
        assert result["refused_growth"]
        assert via.GetDrillValue() / 1e6 == 0.15
