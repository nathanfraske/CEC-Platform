#!/usr/bin/env python3
"""Full Hub pipeline run: place -> materialize -> route -> check, budget-guided.

The L1 route-leg wiring (docs/placer-upgrade-2026-06-14 FOLLOWUPS): composes the MV2-MV5 placer
(oracle-derived frame from the committed Hub) with cec_router's Freerouting route + cec_score gates +
DRC + the electrothermal physics. Run IN the kicad10 container (pcbnew + kicad-cli + java + xvfb):

  docker run --rm -v $PWD:/work -w /work cec/routing:kicad10 \
    python3 scripts/hub_pipeline_run.py --hours 1 --out build/hub-full

Writes build/hub-full/{run.log, report.json, hub-cand*.kicad_pcb, route-cand*/...}. The committed Hub
is the read-only reference oracle (Stage-1 inputs + MV3 similarity); this never edits it.
"""
import argparse
import copy
import contextlib
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import cec_synth_pipeline as S          # noqa: E402
import cec_router                       # noqa: E402
import cec_score                        # noqa: E402
import cec_seats                        # noqa: E402  (the cloud/local residency resolver)
import cec_constraints                  # noqa: E402

REF = "beta/hub-standard-rev2/candidate/hub-standard-rev2-candidate.kicad_pcb"
REF_SCH = "beta/hub-standard-rev2/hub-standard-rev2.kicad_sch"
HUB_INITIAL_FR_PASSES = max(4, int(os.environ.get("CEC_HUB_FR_PASSES", "12")))

# The synth-relevant PCB-geometry conformance subset (post-route HARD gate). Cable-only checkers
# (high-current-corridor-keepout) self-N/A on the cable-less Hub -- that is correct, not a miss.
CONFORMANCE_SUBSET = (
    "hub-stackup-6layer", "through-vias-only", "mezzanine-segment-contract",
    "netclass-geometry-conformance", "high-current-corridor-keepout",
    "high-current-pour-integrity", "high-current-pour-present",
    "kelvin-sense-fcu-no-via", "kelvin-sense-adjacent-shunt", "kelvin-sense-from-inner-pad",
    "logo-bcu-keepout", "mount-holes-present-clear", "connector-mouth-faces-edge",
    "via-on-pad", "no-incursion-in-laid-pour",
)
CONFORMANCE_REQUIRED_PASS = {
    "hub-stackup-6layer", "through-vias-only", "mezzanine-segment-contract",
}

# Names owned by the copper synthesis pipeline.  These are safe to use as a
# temporary pickup envelope and then replace; hand-authored zones (including
# the GND planes) are deliberately excluded.  ``slab:`` is the legacy name,
# while current boards may contain any of the later planner realizations.
PIPELINE_RAIL_ZONE_PREFIXES = (
    "slab:", "overunder:", "pourfirst:", "pourplan:", "patch:", "manifold:",
)


def _build_seats(sel, spec, log):
    """Build (manager, worker) for cec_router.route() per the resolved seat backend, mirroring
    cec_cascade.route_tier: local -> the broker swarm (gated on available()); cloud -> the SAME
    swarm makers with cloud model names (cec_judge_local._chat_json auto-routes to the claude shim);
    off/unavailable -> (None, None) => deterministic defaults. Fail-safe: any error -> deterministic."""
    backend = sel["backend"]
    if backend == "off":
        log("SEATS: off -> deterministic route (no LLM control plane)")
        return None, None
    try:
        import cec_judge_local as jl
    except Exception as e:
        log("SEATS: cec_judge_local import failed (%s) -> deterministic" % e)
        return None, None
    if backend == "local":
        if not jl.available():
            log("SEATS: local chosen but broker :8080 down -> deterministic")
            return None, None
        log("SEATS: LOCAL swarm (manager=%s worker=%s, panel=3)"
            % (sel["manager_model"], sel["worker_model"]))
        return (jl.make_manager_swarm(spec, panel=3, model=sel["manager_model"]),
                jl.make_worker_swarm(spec, fanout=3, model=sel["worker_model"]))
    # cloud: claude -p has no sampling temperature, so a voted panel collapses -> single judge.
    if not getattr(jl, "CLOUD_MODELS", None):
        log("SEATS: cloud chosen but CLOUD_MODELS empty -> deterministic")
        return None, None
    log("SEATS: CLOUD seats (manager=%s effort=%s, worker=%s effort=%s, panel=1)"
        % (sel["manager_model"], sel["effort"], sel["worker_model"], sel["effort"]))
    return (jl.make_manager_swarm(spec, panel=1, model=sel["manager_model"], effort=sel["effort"]),
            jl.make_worker_swarm(spec, fanout=1, model=sel["worker_model"], effort=sel["effort"]))


@contextlib.contextmanager
def _freerouting_wave_environment(params):
    """Activate the live wave's route-diversity and plateau contracts locally.

    Seeds are inert in the pinned Freerouting fork unless the seed axis is
    explicitly enabled.  The external plateau monitor also needs both its
    streak and the board-calibrated recovery floor.  Scope all three variables
    to one route call so importing this runner cannot contaminate other jobs.
    """
    keys = ("CEC_FR_SEED_AXIS", "CEC_FR_PLATEAU_KILL", "CEC_FR_PLATEAU_FLOOR")
    previous = {key: os.environ.get(key) for key in keys}
    os.environ["CEC_FR_SEED_AXIS"] = "1"
    os.environ.setdefault("CEC_FR_PLATEAU_KILL", "4")
    os.environ.setdefault(
        "CEC_FR_PLATEAU_FLOOR", str(int(params.get("wave_plateau_floor", 100))))
    try:
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _conformance(final, cfg, log):
    """Run the synth-relevant PCB-geometry conformance subset post-route. Returns (n_fail, rows)
    where rows = [{id, status, detail}, ...] for the subset. FAIL here is a real geometry violation
    (the placer's corridor/pour/kelvin invariants given post-route teeth). Checker errors fail."""
    try:
        import cec_constraints
        ctx = {"radio": bool(cfg.params.get("antenna_edge"))}
        rows = cec_constraints.run(final, ctx)
    except Exception as e:
        detail = "%s: %s" % (type(e).__name__, e)
        log("  conformance: ERROR (%s)" % detail)
        return 1, [{"id": "conformance-run", "status": "ERROR", "detail": detail[:140]}]
    sub = [{"id": c.id, "status": st, "detail": str(d)[:140]}
           for c, st, d, _ in rows if c.id in CONFORMANCE_SUBSET]
    present = {r["id"] for r in sub}
    for missing in sorted(set(CONFORMANCE_SUBSET) - present):
        sub.append({"id": missing, "status": "ERROR", "detail": "checker result missing"})
    n_fail = sum(1 for r in sub if r["status"] in ("FAIL", "ERROR")
                 or (r["id"] in CONFORMANCE_REQUIRED_PASS and r["status"] != "PASS"))
    if sub:
        log("  conformance: %d FAIL / %d checked (%s)"
            % (n_fail, len(sub), ", ".join("%s=%s" % (r["id"], r["status"]) for r in sub
                                           if r["status"] in ("FAIL", "ERROR")) or "all PASS/N-A"))
    return n_fail, sub


def _copy_reference_worker(ref_pcb, out):
    """Copy the oracle and make every persistent board-item UUID unambiguous."""
    import shutil
    import cec_fr

    shutil.copy(ref_pcb, out)
    return cec_fr.ensure_unique_board_file_uuids(out)


def _reposition_worker(P, pinned_refs, out):
    """Phase 2 (spawn subprocess): reposition components and rip committed routing.

    ``_copy_reference_worker`` has already staged and UUID-normalized *out*.
    ORDER: move footprints BEFORE any Remove() (a Remove invalidates later SWIG
    iterators). After Remove() this process's pcbnew state is corrupt, so the
    zone FILL is a SEPARATE process (_fill_worker).
    """
    import pcbnew
    bd = pcbnew.LoadBoard(out)
    # cand.P is in a 0-origin synth frame, but the committed board's OUTLINE sits at (x0,y0) (the Hub
    # at (70,90)). Offset by the board-edge origin so the repositioned parts land INSIDE the outline --
    # otherwise every component is off-board and FR routes nothing.
    bb = bd.GetBoardEdgesBoundingBox()
    ox, oy = bb.GetLeft(), bb.GetTop()
    moved = 0
    for fp in bd.GetFootprints():
        r = fp.GetReference()
        if r in P:
            x, y, rot = P[r]
            fp.SetPosition(pcbnew.VECTOR2I(int(x * 1e6) + ox, int(y * 1e6) + oy))
            fp.SetOrientationDegrees(rot)
            if r in pinned_refs:
                # Preserve mechanical/user-pinned seats through the router's
                # advisory repair loop. Moving one after pour synthesis also
                # invalidates the actual laid-copper contract.
                fp.SetLocked(True)
            moved += 1
    for t in list(bd.GetTracks()):
        bd.Remove(t)
    bd.Save(out)
    return moved


def _fill_worker(out, rail_nets=()):
    """Fill fresh zones and land guarded local pickups before Freerouting.

    The GND plane MUST connect -- FR excludes its plane layer from signal
    routing, so an unfilled plane leaves every GND ratline unroutable.  The
    over-under rail zones have the same ordering requirement: only after the
    real fill exists can we prove that an adjacent pickup barrel lands in
    copper instead of in an empty lane between polygons.  Give those proven
    pad-to-fill connections to the router as existing topology rather than
    asking it to rediscover dozens of sub-millimetre power escapes.

    This remains a separate process from the track-removal phase, whose pcbnew
    SWIG state is invalid after Remove().
    """
    import pcbnew
    import cec_fr

    bd = pcbnew.LoadBoard(out)
    pcbnew.ZONE_FILLER(bd).Fill(bd.Zones())
    before_pickup = {item.m_Uuid.AsString() for item in bd.GetTracks()}
    pickup = cec_fr.synthesize_power_pickups(
        bd, (), plane_nets=("GND",), filled_zone_nets=tuple(rail_nets),
        lock=True)
    pickup_item_ids = {item.m_Uuid.AsString() for item in bd.GetTracks()} - before_pickup
    resolver = cec_fr._project_netclass_resolver(out)
    local_footprint = cec_fr.synthesize_same_footprint_links(
        bd, lock=True, netclass_resolver=resolver)
    bypass = cec_fr.synthesize_local_power_bypass_links(
        bd, lock=True, netclass_resolver=resolver)
    local_signal = cec_fr.synthesize_local_signal_links(
        bd, lock=True, netclass_resolver=resolver)
    normalization = {"tracks": 0, "vias": 0}
    if (pickup["vias"] or local_footprint["linked"] or bypass["linked"]
            or local_signal["linked"]):
        normalization = cec_fr.normalize_netclass_geometry(bd, out)
        for zone in bd.Zones():
            zone.UnFill()
        pcbnew.ZONE_FILLER(bd).Fill(bd.Zones())
    bd.BuildConnectivity()
    local_rail = cec_fr.synthesize_lastmile(
        bd, max_mm=8.0, cap=80, netclass_resolver=resolver,
        include_nets=tuple(rail_nets) + ("GND",), lock=True)
    rail_normalization = {"tracks": 0, "vias": 0}
    if local_rail["closed"]:
        rail_normalization = cec_fr.normalize_netclass_geometry(bd, out)
        for zone in bd.Zones():
            zone.UnFill()
        pcbnew.ZONE_FILLER(bd).Fill(bd.Zones())
    pickup_prune = cec_fr.prune_redundant_dangling_pickups(
        bd, pickup_item_ids, discover_nets=tuple(rail_nets))
    # Do not touch SWIG-owned zone objects after Remove(): pruning is the
    # final in-process mutation, and deleting same-net copper needs no
    # antipad refill. A later worker may refill if another stage needs it.
    bd.Save(out)
    return {"areas": bd.GetAreaCount(), "power_pickups": pickup,
            "same_footprint_links": local_footprint,
            "local_power_bypass": bypass,
            "local_signal_links": local_signal,
            "normalization": normalization,
            "local_rail_finish": local_rail,
            "rail_normalization": rail_normalization,
            "pickup_prune": pickup_prune}


def _prepare_repour_worker(out, nets):
    """Bootstrap pickups from generated outlines, then remove inherited rail zones.

    The old zones are never accepted as final copper. They are used only as a
    coverage envelope so the guarded pickup pass can connect SMD rail pads to
    In3 before the fresh slab solve requires real inner-layer anchors.
    """
    import pcbnew
    import cec_fr

    board = pcbnew.LoadBoard(out)
    old = [zone for zone in board.Zones()
           if _is_pipeline_rail_zone_name(zone.GetZoneName())]
    if not old:
        raise RuntimeError(
            "six-layer Hub reference contains no pipeline-generated rail zones")
    covered = {zone.GetNetname() for zone in old if zone.GetNetname()}
    missing = sorted(set(nets) - covered)
    pickup = cec_fr.synthesize_power_pickups(
        board, ({"net": net, "layers": ("In3.Cu",)} for net in nets),
        plane_nets=tuple(nets))
    for zone in old:
        board.Remove(zone)
    pcbnew.SaveBoard(out, board)
    return {"zones_removed": len(old), "pickup": pickup,
            "asks_without_bootstrap_zone": missing}


def _prepour_local_worker(out, rail_nets=()):
    """Lay short, placement-dependent copper before shaped-rail allocation.

    Local bypass/control links and duplicate-pad pair ties are physical board
    objects, not work for a global autorouter.  They must exist before the
    pour solver builds its foreign-copper masks; adding them after the slabs
    were filled made the pipeline obstruct its own shortest legal escapes.

    The remaining hand-authored zones (notably GND) are freshly filled first,
    so last-mile connectivity is evaluated against real plane copper.  Rail
    gaps may be bridged here even though their shaped zones do not exist yet:
    the following over-under solve must land those locked barrels in real
    copper, and the fail-closed materialization DRC rejects the candidate if
    it cannot.  This worker never synthesizes rail pickups from absent fill.
    """
    import pcbnew
    import cec_fr

    board = pcbnew.LoadBoard(out)
    for zone in board.Zones():
        zone.UnFill()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    resolver = cec_fr._project_netclass_resolver(out)
    same_footprint = cec_fr.synthesize_same_footprint_links(
        board, lock=True, netclass_resolver=resolver)
    bypass = cec_fr.synthesize_local_power_bypass_links(
        board, lock=True, netclass_resolver=resolver)
    local_signal = cec_fr.synthesize_local_signal_links(
        board, lock=True, netclass_resolver=resolver)
    normalization = {"tracks": 0, "vias": 0}
    if (same_footprint["linked"] or bypass["linked"]
            or local_signal["linked"]):
        normalization = cec_fr.normalize_netclass_geometry(board, out)
        for zone in board.Zones():
            zone.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    board.BuildConnectivity()
    local_rail = cec_fr.synthesize_lastmile(
        board, max_mm=8.0, cap=80, netclass_resolver=resolver,
        include_nets=tuple(rail_nets) + ("GND",), lock=True)
    rail_normalization = {"tracks": 0, "vias": 0}
    if local_rail["closed"]:
        rail_normalization = cec_fr.normalize_netclass_geometry(board, out)
        for zone in board.Zones():
            zone.UnFill()
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())

    board.Save(out)
    return {"same_footprint_links": same_footprint,
            "local_power_bypass": bypass,
            "local_signal_links": local_signal,
            "normalization": normalization,
            "local_rail_finish": local_rail,
            "rail_normalization": rail_normalization}


def _is_pipeline_rail_zone_name(name):
    """Return whether *name* identifies copper owned by the synthesis pipeline."""
    return str(name or "").startswith(PIPELINE_RAIL_ZONE_PREFIXES)


def _resolve_board_net_names(board_path, requested):
    """Resolve schematic-local ask names to exact saved-board net names.

    KiCad qualifies sheet-local nets in the PCB.  An exact name always wins;
    otherwise exactly one hierarchy-suffix match is required.  Missing or
    ambiguous asks fail closed so a pour can never silently target no net (or
    the wrong identically named leaf on another sheet).
    """
    import pcbnew

    board = pcbnew.LoadBoard(board_path)
    available = {str(name) for name in board.GetNetsByName().keys() if str(name)}
    resolved = []
    for requested_name in requested:
        requested_name = str(requested_name)
        if requested_name in available:
            matches = [requested_name]
        else:
            suffix = requested_name if requested_name.startswith("/") else "/" + requested_name
            matches = sorted(name for name in available if name.endswith(suffix))
        if len(matches) != 1:
            state = "missing" if not matches else "ambiguous: %s" % ", ".join(matches)
            raise RuntimeError("Hub pour net %r is %s in %s"
                               % (requested_name, state, board_path))
        resolved.append(matches[0])
    return tuple(dict.fromkeys(resolved))


def _hub_pour_nets():
    """Return the current Hub ask contract using exact saved-board net names."""
    import cec_fresh_wave

    asks = cec_fresh_wave._board_params("hub-standard-rev2")  # noqa: SLF001
    requested = tuple(dict.fromkeys(
        ask.get("net") for ask in (asks.get("pour_asks") or ())
        if ask.get("net")))
    if not requested:
        raise RuntimeError("Hub placement contract contains no power-pour asks")
    return _resolve_board_net_names(os.path.join(S.ROOT, REF), requested)


def _repour_worker(out, nets):
    """Lay the Hub's current routed-object power corridors in a fresh process.

    The live Hub contract has ``overunder=True`` because ten mutually exclusive
    same-layer slabs cannot join all rail terminals on this compact board.  Do
    not regress to the superseded fair-share slab solver here: the over-under
    search may bridge to another signal layer with qualified via fields when a
    real obstruction requires it.
    """
    import pcbnew
    import cec_fr
    import cec_slab_pour

    board = pcbnew.LoadBoard(out)
    asks = [{"net": net, "layers": ("In3.Cu",)} for net in nets]
    pours, vias, report = cec_slab_pour.synthesize_overunder_pours(
        board, asks, manifolds=True)
    failed = sorted(net for net, row in report.items()
                    if row.get("path_found") is not True)
    if failed or not pours:
        raise RuntimeError("Hub over-under allocation failed for %s"
                           % (", ".join(failed) or "all rails"))
    cec_fr.add_power_pours(board, pours, fill=False)
    added_vias = cec_fr.add_overunder_vias(board, vias)
    pcbnew.SaveBoard(out, board)
    return {"rails": len(nets), "polygons": len(pours),
            "vias": len(added_vias or ()), "planner": "overunder",
            "paths": {net: {key: row.get(key) for key in
                              ("path_found", "segments", "bridges", "layers_used")}
                      for net, row in report.items()}}


def _stage_reference_sidecars(ref, dst):
    """Stage and rebind the project files required by pcbnew netclass lookup."""
    import shutil
    import cec_fr

    src_base = ref[:-len(".kicad_pcb")]
    dst_base = dst[:-len(".kicad_pcb")]
    copied = []
    for ext in (".kicad_pro", ".kicad_dru"):
        candidates = [src_base + ext,
                      os.path.join(os.path.dirname(os.path.dirname(ref)),
                                   "hub-standard-rev2" + ext)]
        source = next((path for path in candidates if os.path.isfile(path)), None)
        if source:
            target = dst_base + ext
            shutil.copy2(source, target)
            copied.append(target)
    cec_fr.rebind_project_metadata(dst)
    return copied


def materialize_onto_reference(cand, ref_pcb, out, *, pinned_refs=()):
    """Materialize a synth placement onto the REFERENCE board's stackup (the owner's 'base stackup =
    committed Hub'). build_board's from-scratch output is NOT DSN-exportable (KiCad's Specctra
    exporter silently refuses it), so instead COPY the committed board -- which exports + routes fine,
    with its real net classes / layer stackup / mounts / logo -- then reposition each synth component,
    rip the committed routing, and FILL the zones fresh at the new positions (so the GND plane
    connects). Refs the synth does not model (M*/LOGO/FID/TP) keep their committed (correct) positions.
    Runs in SIX isolated spawn subprocesses (copy+UUID normalization,
    reposition+rip, strip pours, local copper, repour, then fill). Remove
    operations invalidate later SWIG state in that process, so each mutating
    phase is isolated."""
    import multiprocessing as mp
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    ref, dst = os.path.abspath(ref_pcb), os.path.abspath(out)

    # Stage the project and custom-rule sidecars BEFORE the first pcbnew worker
    # loads the copied board.  Netclass lookup is project-backed: staging these
    # only after pickup synthesis made every pre-route pickup use KiCad's
    # 0.6/0.3-mm defaults, after which the final normalizer enlarged/moved it.
    # The candidate-local files are authoritative; the parent project is only
    # a compatibility fallback for older reference snapshots.
    _stage_reference_sidecars(ref, dst)

    ctx = mp.get_context("spawn")
    with ctx.Pool(1) as pool:
        uuid_report = pool.apply(_copy_reference_worker, (ref, dst))
    with ctx.Pool(1) as pool:
        moved = pool.apply(
            _reposition_worker, (dict(cand.P), tuple(pinned_refs), dst))
    slab_nets = _hub_pour_nets()
    with ctx.Pool(1) as pool:
        pool.apply(_prepare_repour_worker, (dst, slab_nets))
    with ctx.Pool(1) as pool:
        prepour_report = pool.apply(_prepour_local_worker, (dst, slab_nets))
    with ctx.Pool(1) as pool:
        pour_report = pool.apply(_repour_worker, (dst, slab_nets))
    with ctx.Pool(1) as pool:                          # FRESH process -> clean pcbnew state for fill
        finish_report = pool.apply(_fill_worker, (dst, slab_nets))
    pour_report["uuid_normalization"] = uuid_report
    pour_report["prepour_local"] = prepour_report
    pour_report["pre_route_finish"] = finish_report
    return out, moved, pour_report


def _acceptance_terms(route_verdict, conformance_fail, physics_flags,
                      policy_ok, intake_ok):
    """One explicit fail-closed contract for the Hub runner's accepted artifact."""
    terms = {
        "route": route_verdict.get("gates_pass") is True,
        "conformance": int(conformance_fail) == 0,
        "physics": len(physics_flags) == 0,
        "policy": policy_ok is True,
        "reference_intake": intake_ok is True,
    }
    return terms, all(terms.values())


_PRE_ROUTE_FATAL_DRC = frozenset({
    "clearance", "shorting_items", "tracks_crossing", "hole_clearance",
    "isolated_copper", "via_dangling", "track_dangling",
})


def _pre_route_materialization_gate(board_path):
    """Refuse electrically invalid synthesized copper before routing.

    Ordinary signal ratlines are expected, but synthesized copper must already
    be physically coherent: the shaped rails are filled and every generated
    bridge/pickup barrel must contact copper on both sides. Copper collisions,
    isolated fill, and dangling tracks or vias cannot be handed to the router
    as a valid starting point. Return a compact, auditable result from one DRC
    run.
    """
    types, loci = cec_score.drc_types(board_path)
    fatal = {kind: count for kind, count in types.items()
             if kind in _PRE_ROUTE_FATAL_DRC and count}
    details = [row for row in loci if row.get("type") in fatal]
    incursion = cec_constraints.laid_pour_incursion_summary(board_path)
    incursion_count = sum(int(incursion.get(key) or 0)
                          for key in ("n_parts", "n_tracks", "n_vias"))
    if incursion_count:
        types = dict(types)
        types["laid_pour_incursion"] = incursion_count
        fatal["laid_pour_incursion"] = incursion_count
        details.extend({"type": "laid_pour_incursion",
                        "where": "%s %s on %s inside %s"
                        % (row.get("kind", "copper"), row.get("ref", ""),
                           row.get("net", ""), row.get("pour", "pour"))}
                       for row in incursion.get("items", ())[:20])
    return {"ok": not fatal, "fatal": fatal, "types": types,
            "loci": details[:20]}


def _reference_intake():
    """Run intake on the candidate while explicitly binding its parent schematic."""
    import cec_constraints

    board = os.path.join(S.ROOT, REF)
    schematic = os.path.join(S.ROOT, REF_SCH)
    if not os.path.isfile(board):
        raise FileNotFoundError("reference PCB missing: %s" % board)
    if not os.path.isfile(schematic):
        raise FileNotFoundError("reference schematic missing: %s" % schematic)
    return cec_constraints.intake_gate(board, ctx={"sch": schematic})


def _reference_freshness():
    """Require the materialization oracle to match the current Hub netlist exactly."""
    import cec_fresh_wave

    board = os.path.join(S.ROOT, REF)
    want = cec_fresh_wave._netlist_refs("hub-standard-rev2")  # noqa: SLF001
    match = cec_fresh_wave._schematic_match(board, want)      # noqa: SLF001
    return {
        "match": match,
        "exact": match is not None and abs(match - 1.0) <= 1e-9,
        "schematic_parts": len(want) if want else None,
        "board": REF,
    }


def _route_iteration_timeout(remaining_s, max_iters, reserve_s=30):
    """Bound each parallel seed batch so all planned iterations fit the run window."""
    usable = float(remaining_s) - float(reserve_s)
    if usable <= 0 or int(max_iters) <= 0:
        raise RuntimeError("insufficient route budget after reserve")
    return max(5, int(usable // int(max_iters)))


def _hub_route_parallelism(cpu_count=None, available_memory_bytes=None):
    """Choose parallel Freerouting seeds without oversubscribing RAM.

    The pinned router is effectively single-core per JVM but uses about
    0.7-0.8 GiB on the live Hub. Use half the logical CPUs (leaving headroom
    for KiCad, scoring, Xvfb, and the OS), reserve 4 GiB, and budget a full
    GiB per JVM. ``CEC_HUB_ROUTE_WORKERS`` can lower or request a higher count,
    but the same resource ceilings and the 16-worker safety cap still apply.
    """
    cpus = max(1, int(cpu_count if cpu_count is not None else (os.cpu_count() or 1)))
    if available_memory_bytes is None:
        try:
            with open("/proc/meminfo", encoding="utf-8") as fh:
                mem_kib = next(int(line.split()[1]) for line in fh
                               if line.startswith("MemAvailable:"))
            available_memory_bytes = mem_kib * 1024
        except (OSError, StopIteration, ValueError):
            available_memory_bytes = 5 * 1024**3
    reserve = 4 * 1024**3
    per_worker = 1024**3
    by_cpu = max(1, cpus // 2)
    by_memory = max(1, int((int(available_memory_bytes) - reserve) // per_worker))
    ceiling = max(1, min(16, by_cpu, by_memory))
    requested = os.environ.get("CEC_HUB_ROUTE_WORKERS")
    if requested is None:
        return ceiling
    return max(1, min(ceiling, int(requested)))


def _hub_route_passes(seed_timeout_s, route_workers,
                      requested=HUB_INITIAL_FR_PASSES):
    """Choose depth that can finish before the per-seed timeout at this breadth.

    On the live Hub, sixteen simultaneous JVMs complete seven passes within a
    short-wave slot; asking all of them for twelve timed out all sixteen seeds
    even with a 582-second per-seed allowance, then the router's own backoff
    proved seven passes importable.  Avoid spending the first third of every
    wave rediscovering that measured limit.  Retain twelve for longer windows
    and narrower batches.
    """
    passes = max(4, int(requested))
    if float(seed_timeout_s) < 660 and int(route_workers) >= 12:
        return min(passes, 7)
    if float(seed_timeout_s) < 330 and int(route_workers) >= 8:
        return min(passes, 9)
    return passes


def _closure_placement_key(row):
    """Rank legal, corridor-clean Hub placements by minimum board area.

    A marginal proxy improvement cannot justify a larger PCB when a smaller
    candidate is equally legal and leaves the same number of pour-corridor
    crossings.  The larger sweep sizes remain available as fallbacks when they
    actually improve legality or corridor cleanliness.
    """
    cand, width, height = row[:3]
    return (cand.residual,
            getattr(cand, "corridor_cross_aware", cand.corridor_cross),
            cand.corridor_cross,
            float(width) * float(height),
            cand.proxy.get("proxy_score", 1e9))


def _placement_probe_pool(placed, route_candidates, *, fallbacks=2):
    """Keep ranked fallbacks for placements rejected during materialization.

    ``route_candidates`` limits placements that actually consume router time.
    A diameter-aware power bridge can still prove the top legal placement
    unrealizable, so probe two more ranked placements before declaring that no
    Hub candidate exists.
    """
    target = max(1, int(route_candidates))
    return list(placed[:min(len(placed), target + max(0, int(fallbacks)))])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=1.0)
    ap.add_argument("--board", default="hub-standard-rev2")
    ap.add_argument("--out", default="build/hub-full")
    ap.add_argument("--route-candidates", type=int, default=2, help="how many top placements to route")
    ap.add_argument("--seats", default="auto", choices=["auto", "cloud", "local", "off"],
                    help="control-plane seat residency: auto (overnight-long->local, else cloud) | "
                         "cloud | local | off (deterministic). Owner default: cloud unless --hours>=2.")
    a = ap.parse_args()

    # The route()-internal intake gate runs on the MATERIALIZED candidate (no sibling .kicad_sch
    # there), so keep it from pre-refusing candidate generation -- but we DO run the schematic-side
    # intake against the committed REFERENCE schematic below (cheap base-stackup insurance).
    os.environ.setdefault("CEC_SKIP_INTAKE", "1")
    t0 = time.time()
    deadline = t0 + a.hours * 3600
    os.makedirs(a.out, exist_ok=True)
    logf = os.path.join(a.out, "run.log")

    def log(msg):
        line = "[%s | +%4ds] %s" % (time.strftime("%H:%M:%S"), int(time.time() - t0), msg)
        print(line, flush=True)
        with open(logf, "a") as h:
            h.write(line + "\n")

    # ---- seat residency (cloud/local toggle; owner policy via cec_seats) ----
    sel = cec_seats.select_seat_backend(hours=a.hours, judge=(None if a.seats == "auto" else a.seats))
    log("SEATS resolved: backend=%s (%s); manager=%s worker=%s effort=%s"
        % (sel["backend"], sel["reason"], sel["manager_model"], sel["worker_model"], sel["effort"]))
    if sel["backend"] == "cloud" and sel["manager_model"]:
        # keep the advisory corpus reviewer on the same venue as the seats
        os.environ.setdefault("CEC_VLLM_REVIEWER_MODEL", sel["manager_model"])

    report = {"board": a.board, "hours": a.hours, "seats": sel, "stages": [],
              "placements": [], "materializations": [], "routes": [],
              "policy_ok": None, "ref_intake": None}
    log("=== FULL HUB PIPELINE (place -> route -> check), budget %.2f h ===" % a.hours)

    # The runner copies the candidate's footprint inventory before moving the
    # synthesized placement. A stale candidate would silently omit newly added
    # parts (for example the current buck L1/divider) and preserve old pin nets.
    # Refuse before spending placement/routing compute; the next exact candidate
    # must be generated from the authoritative current schematic first.
    try:
        report["reference_freshness"] = _reference_freshness()
    except Exception as e:
        report["reference_freshness"] = {
            "exact": False, "error": "%s: %s" % (type(e).__name__, e)}
    if not report["reference_freshness"].get("exact"):
        log("REFERENCE: STALE/UNKNOWN against current schematic -> refuse before placement (%s)"
            % report["reference_freshness"])
        report["elapsed_s"] = round(time.time() - t0, 1)
        with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as out_file:
            json.dump(report, out_file, indent=2, default=str)
        return 2
    log("REFERENCE: exact current-schematic signature match")

    # ---- run-start guards: policy loadability (DF-05/07 anti-ratchet) + REF schematic intake ----
    try:
        import cec_policy
        cec_policy.assert_loadable(cec_policy.load_policy())
        report["policy_ok"] = True
        log("POLICY: cec-policy.json loadable (under the same guard as the night)")
    except Exception as e:
        report["policy_ok"] = False
        report["policy_error"] = "%s: %s" % (type(e).__name__, e)
        log("POLICY: assert_loadable FAILED -> %s" % report["policy_error"])
    if os.path.isfile(os.path.join(S.ROOT, REF_SCH)):
        try:
            g = _reference_intake()
            report["ref_intake"] = {"ok": bool(getattr(g, "ok", g) if not isinstance(g, dict) else g.get("ok")),
                                    "detail": str(g)[:300]}
            log("INTAKE(ref schematic): %s" % report["ref_intake"]["ok"])
        except Exception as e:
            report["ref_intake"] = {"ok": False,
                                    "error": "%s: %s" % (type(e).__name__, e)}
            log("INTAKE(ref schematic): ERROR (%s)" % e)
    else:
        report["ref_intake"] = {"ok": False, "error": "reference schematic missing"}
        log("INTAKE(ref schematic): ERROR (reference schematic missing)")

    # ---- Stage 1: oracle Stage-1 + placement sweep (a couple sizes, keep the best) ----
    import cec_fresh_wave

    cfg = S.Config.load(a.board)
    cfg.params["oracle_reference_path"] = REF
    os.environ["CEC_THERMAL_BOARD_HINT"] = os.path.abspath(REF)
    S.elicit_requirements(cfg, {"antenna_keepout": True})
    S.apply_oracle_stage1(cfg)
    W, H = cfg.params["size_target_wh"]
    # The reference oracle supplies diagnostics and the candidate's physical
    # stackup, but the live BETA declaration owns placement and route policy.
    # Merge it after Stage 1 so stale oracle-derived connector edges can never
    # override the current dead-bug/mezzanine contract.
    live = cec_fresh_wave._placement_params(a.board, W, H)  # noqa: SLF001
    cfg.pins = dict(live.pop("anchor_pins", {}) or {})
    cfg.params.update(live)
    ref_pl = S.read_placement(REF)
    ref_proxy = S.placement_proxy(ref_pl)
    ref_hpwl = S.hpwl(ref_pl.pads_by_net)
    log("PLACE: oracle frame %.1fx%.1f, %d connector edges, antenna=%s; reference HPWL %.0f"
        % (W, H, len(cfg.params["edge_override"]), cfg.params.get("antenna_edge"), ref_hpwl))

    placed = []
    for (sw, sh) in [(W, H), (W + 3, H + 3), (W + 6, H + 6)]:
        if time.time() > deadline - 120:
            log("budget nearly spent -> stop before placement %.0fx%.0f" % (sw, sh))
            break
        try:
            size_cfg = copy.deepcopy(cfg)
            size_live = cec_fresh_wave._placement_params(  # noqa: SLF001
                a.board, sw, sh)
            size_cfg.pins = dict(size_live.pop("anchor_pins", {}) or {})
            size_cfg.params.update(size_live)
            cs = S.place_candidates(
                size_cfg, sw, sh, strategies=S.STRATEGIES,
                seeds=(0, 1, 2, 3))
        except Exception as e:
            log("  place %.0fx%.0f FAILED: %s" % (sw, sh, e))
            continue
        b = cs[0]
        placed.append((b, sw, sh, size_cfg))
        rec = {"W": sw, "H": sh, "strat": b.strat, "seed": b.seed, "residual": b.residual,
               "corridor_cross": b.corridor_cross, "proxy_score": b.proxy.get("proxy_score"),
               "similarity": b.similarity, "hpwl": b.proxy["hpwl"],
               "hpwl_ratio": round(b.proxy["hpwl"] / ref_hpwl, 3), "hub_terms": b.proxy.get("hub_terms")}
        report["placements"].append(rec)
        log("  size %.0fx%.0f: best %s/s%d residual=%d cc=%d sim=%.3f hpwl=%.0f (%.2fx) hub=%s"
            % (sw, sh, b.strat, b.seed, b.residual, b.corridor_cross, b.similarity, b.proxy["hpwl"],
               rec["hpwl_ratio"], b.proxy.get("hub_terms")))
    placed.sort(key=_closure_placement_key)
    topK = _placement_probe_pool(placed, a.route_candidates)
    log("ROUTE: probe %d top placement(s), route up to %d -> %s"
        % (len(topK), a.route_candidates,
           [(t[0].strat, t[0].seed, t[0].residual) for t in topK]))

    # ---- Stage 2: route each top placement (budget-bounded), score gates+DRC, electrothermal ----
    best = None
    route_attempts = 0
    for rank, (cand, sw, sh, cand_cfg) in enumerate(topK):
        if route_attempts >= a.route_candidates:
            break
        if time.time() > deadline - 120:
            log("budget nearly spent -> stop before routing cand%d" % rank)
            break
        try:
            mat = os.path.abspath(os.path.join(a.out, "hub-cand%d.kicad_pcb" % rank))
            _, nmoved, pour_report = materialize_onto_reference(
                cand, REF, mat, pinned_refs=cand_cfg.pins)
            prepour_finish = pour_report["prepour_local"]
            postpour_finish = pour_report["pre_route_finish"]
            log("  materialized cand%d onto six-layer reference (%d components repositioned; "
                "%d rails -> %d %s polygons, %d bridge vias; %d guarded pre-route pickups; "
                "%d guarded same-footprint links; "
                "%d guarded local power links; "
                "%d guarded local signal links; "
                "%d guarded rail/ground gaps closed; "
                "%d duplicate UUID occurrence(s) repaired)"
                % (rank, nmoved, pour_report["rails"], pour_report["polygons"],
                   pour_report["planner"], pour_report["vias"],
                   postpour_finish["power_pickups"]["vias"],
                   prepour_finish["same_footprint_links"]["linked"]
                   + postpour_finish["same_footprint_links"]["linked"],
                   prepour_finish["local_power_bypass"]["linked"]
                   + postpour_finish["local_power_bypass"]["linked"],
                   prepour_finish["local_signal_links"]["linked"]
                   + postpour_finish["local_signal_links"]["linked"],
                   prepour_finish["local_rail_finish"]["closed"]
                   + postpour_finish["local_rail_finish"]["closed"],
                   pour_report["uuid_normalization"]["rewritten"]))
            pre_route = _pre_route_materialization_gate(mat)
            report["materializations"].append({
                "rank": rank, "board": os.path.relpath(mat, S.ROOT),
                "pour_report": pour_report, "pre_route_gate": pre_route,
            })
            if not pre_route["ok"]:
                log("  cand%d: PRE-ROUTE MATERIALIZATION REFUSED -- %s; %s"
                    % (rank, pre_route["fatal"], pre_route["loci"][:4]))
                continue
            log("  cand%d: pre-route copper-contact gate PASS (%s)"
                % (rank, pre_route["types"]))
            remaining = deadline - time.time()
            slots = max(1, a.route_candidates - route_attempts)
            opt = int(max(15, min(50, remaining / slots / 8)))   # per-seed opt seconds within budget
            max_iters = 3
            fr_timeout = _route_iteration_timeout(remaining, max_iters)
            route_workers = _hub_route_parallelism()
            route_passes = _hub_route_passes(fr_timeout, route_workers)
            route_seeds = tuple(range(route_workers))
            log("ROUTE cand%d (%s/s%d residual=%d size %.0fx%.0f) "
                "opt_time=%ds passes=%d seed_timeout=%ds parallel_seeds=%d"
                 % (rank, cand.strat, cand.seed, cand.residual, sw, sh, opt,
                    route_passes, fr_timeout, route_workers))
            spec, name = cec_router.board_spec(
                mat, os.path.abspath(os.path.join(a.out, "route-cand%d" % rank)),
                seeds=route_seeds, passes=route_passes, opt_time=opt,
                max_iters=max_iters, kmax=2, max_workers=route_workers,
                fr_timeout=fr_timeout)
            # CONTROL PLANE: judge+fix tiers per the resolved residency (cloud Claude / local broker /
            # off). Two-plane rule: cec_router/cec_fr/cec_score GENERATE+SCORE; the seats only
            # JUDGE+FIX through these slots. Fail-safe -> deterministic defaults (None,None).
            manager, worker = _build_seats(sel, spec, log)
            route_attempts += 1
            with S._oracle_env(cand_cfg.params), \
                    _freerouting_wave_environment(cand_cfg.params):
                final, dlog = cec_router.route(
                    mat, spec, manager=manager, worker=worker, verbose=True)
            if not (final and os.path.isfile(final)):
                log("  cand%d: route produced no board (final=%r) -- skipping score" % (rank, final))
                continue
            # VERIFY THE SHIPPED ARTIFACT: score the SAVED board (cec_cascade.py:132-151 precedent).
            # The Hub does no post-route copper mutation today, so `final` as-saved IS what ships;
            # if a pour/via mutation is ever added here, re-score AFTER it, never before.
            rules = cec_score.Rules.from_board(final)
            route_verdict = cec_router.independent_drc(final, rules, weights=spec.weights)
            m = cec_score.score(final, rules)
            n_conf_fail, conf_rows = _conformance(  # synth-relevant geometry gate
                final, cand_cfg, log)
            cand_cfg.params["thermal_field"] = True
            try:
                th, physics_flags = S.physics(final, cand_cfg)
                et = {"max_T": round(getattr(th, "max_T", float("nan")), 1),
                      "max_dT": round(getattr(th, "max_dT", float("nan")), 1),
                      "calibration": getattr(th, "calibration", "unknown"),
                      "flags": [{"name": f.name, "where": str(f.where), "detail": f.detail}
                                for f in physics_flags]}
            except Exception as e:
                physics_flags = [S.Flag("Hub physics failed", final, 1.0, S.Kind.MEASURE,
                                        {"error": "%s: %s" % (type(e).__name__, e)})]
                et = {"error": "%s: %s" % (type(e).__name__, e),
                      "flags": [{"name": physics_flags[0].name,
                                 "detail": physics_flags[0].detail}]}
            acceptance, accepted = _acceptance_terms(
                route_verdict, n_conf_fail, physics_flags,
                report.get("policy_ok"), (report.get("ref_intake") or {}).get("ok"))
            rrec = {"rank": rank, "strat": cand.strat, "seed": cand.seed, "size": [sw, sh],
                    "board": os.path.relpath(final, S.ROOT),
                    "gates_pass": route_verdict["gates_pass"],
                    "kelvin_ok": route_verdict["kelvin_ok"],
                    "diffpair_ok": route_verdict["diffpair_ok"],
                    "drc": m.drc, "unconnected": m.unconnected, "tracks": m.tracks, "vias": m.vias,
                    "length": round(m.length, 1), "electrothermal": et,
                    "conformance_fail": n_conf_fail, "conformance": conf_rows,
                    "route_verdict": route_verdict, "pour_report": pour_report,
                    "acceptance_terms": acceptance, "accepted": accepted}
            report["routes"].append(rrec)
            log("  cand%d ROUTED: gates_pass=%s kelvin=%s diffpair=%s drc=%d unconnected=%d "
                "conformance_fail=%d tracks=%d vias=%d length=%.0f %s"
                % (rank, m.gates_pass, m.kelvin_ok, m.diffpair_ok, m.drc, m.unconnected, n_conf_fail,
                   m.tracks, m.vias, m.length, et))
            # selection: gates first, THEN conformance (the synth-geometry HARD signal), then drc/...
            key = (not accepted, not route_verdict["gates_pass"], n_conf_fail > 0,
                   len(physics_flags), n_conf_fail, m.drc, m.unconnected, m.length)
            if best is None or key < best[0]:
                best = (key, rrec, final, dlog)
        except Exception as e:
            log("  cand%d ROUTE FAILED: %s\n%s" % (rank, e, traceback.format_exc()))
            continue

    report["best_attempt"] = best[1] if best else None
    accepted_best = best if best is not None and best[1].get("accepted") else None
    report["best_route"] = accepted_best[1] if accepted_best else None

    # ---- corpus-fit review (ADVISORY sidecar; never a rank key, never feeds back -- holdout rule).
    # Even with zero same-family peers (the corpus is eps-only -> _cf_insufficient) the BRIEFED path
    # (ratified routing/layer/plane rules incl. the Hub In2 exception) gives the reviewer teeth. ----
    if best is not None:
        try:
            import cec_judge_local as jl
            cf = jl.corpus_fit_review(best[3], verbose=False)
            report["corpus_fit"] = cf
            with open(os.path.join(a.out, "hub-corpus-fit.json"), "w", encoding="utf-8") as out_file:
                json.dump(cf, out_file, indent=2, default=str)
            log("CORPUS-FIT (advisory): %s"
                % (cf.get("verdict") or cf.get("status") or cf.get("fit") or "recorded"))
        except Exception as e:
            report["corpus_fit"] = {"error": "%s: %s" % (type(e).__name__, e)}
            log("CORPUS-FIT: skipped (%s)" % e)

    # ---- ledger the run (auditable like the night; stamp the policy sha) ----
    try:
        import cec_ledger
        bm = report["best_route"]
        psha = None
        try:
            import cec_policy
            psha = cec_policy.policy_sha256()
        except Exception:
            pass
        cec_ledger.append(board=a.board, mode="hub-pipeline",
                          verdict={"accepted": bm, "best_attempt": report["best_attempt"],
                                   "seats": sel, "policy_ok": report["policy_ok"],
                                   "policy_sha": psha},
                          board_file=(bm["board"] if bm else None))
        log("LEDGER: hub-pipeline run recorded (policy_sha=%s)" % (str(psha)[:12] if psha else "n/a"))
    except Exception as e:
        log("LEDGER: skipped (%s)" % e)

    report["elapsed_s"] = round(time.time() - t0, 1)
    with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as out_file:
        json.dump(report, out_file, indent=2, default=str)
    if accepted_best:
        log("=== DONE in %.0fs. accepted route: %s ===" %
            (report["elapsed_s"], accepted_best[1]["board"]))
        return 0
    attempt = (best[1]["board"] + " gates_pass=%s drc=%d unconn=%d" %
               (best[1]["gates_pass"], best[1]["drc"], best[1]["unconnected"])) if best else "none"
    log("=== DONE in %.0fs. NO ACCEPTED ROUTE; best attempt: %s ===" %
        (report["elapsed_s"], attempt))
    return 2


if __name__ == "__main__":
    sys.exit(main())
