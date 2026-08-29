#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 Nathan M. Fraske
"""
cec_staged_fr -- A1 STAGED-FR (actuation-space deep dive, owner GO 2026-07-08):
run Freerouting as a TIERED ladder instead of one monolithic call. Tier 1 routes the
important nets ALONE on the uncontended board (every other net's pins stripped from the
DSN via the same whole-token mechanism the production kelvin/force policies use); the
result is LOCKED; each later tier routes with all prior tiers' copper protect-ed
(fix->protect in the DSN -- FR drops unprotected fix wires, measured). Awareness by
SEQUENCE: the cheapest possible form of "each route aware of the others".

Composed ENTIRELY from cec_fr primitives (export_dsn / run_freerouting / import_ses /
cec_fr02.force_protect_in_dsn) -- no edits to cec_fr, deliberately, while the S2 agent
owns that region. Intermediate tiers import with fill/annular/pours/taps OFF; the final
tier runs the full additive finishing order.

Relationship to S2 (precision-first deterministic passes): complementary -- S2 lays
kelvin/pairs as deterministic copper BEFORE any FR; staged-FR tiers whatever FR work
REMAINS. Either composes with the other through the same lock+protect contract.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

MMNM = 1_000_000


def _carve(text, start):
    """Balanced-paren block starting at text[start] == '('."""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1], i + 1
    return text[start:], len(text)


def _stage_score(board_path):
    """Measure one tier artifact with the release scorer.

    Kept as a named boundary so tests and future process isolation can replace
    the scorer without weakening the admission semantics.
    """
    import cec_score
    return cec_score.score(board_path)


def _tier_admission(before, after):
    """Apply the repository-wide debt-monotonic promotion contract."""
    import cec_stage_admission
    return cec_stage_admission.evaluate(before, after)


def sanitize_tier_import(candidate_path, parent_path, generated_uuids):
    """Apply the repository import transaction before tier ownership.

    Kept as a late import to avoid coupling module initialization: the synth
    orchestrator invokes staged routing, while this function is called only
    after both modules are fully loaded.  A tier with no generated primitives
    is already a no-op delta and needs no scoring subprocesses.
    """
    generated = {str(uuid) for uuid in generated_uuids if uuid}
    if not generated:
        return ({"schema": 1, "accepted": True,
                 "reason": "no_generated_copper", "removed_count": 0}, None)
    import cec_synth_pipeline
    return cec_synth_pipeline._sanitize_imported_route_transactionally(
        candidate_path, parent_path, generated)


def _dsn_restrict_to_nets(dsn_path, keep_nets):
    """Strip non-tier pin lists from the DSN ``network`` section only.

    A Specctra deck also contains ``(net NAME)`` references on every fixed
    wire and via in the later ``wiring`` section.  The former whole-file scan
    mistook those references for declarations, rewrote them as ``(net NAME
    (pins))``, inflated the kept-net count, and corrupted the obstacle wiring
    handed to Freerouting.  Carve the balanced ``network`` block first and
    transform only its net declarations.  The stripped pads remain physical
    obstacles; all fixed-wire/via net ownership remains byte-for-byte intact.

    Returns the actual kept/stripped declaration counts and fails closed if a
    valid network block is absent.
    """
    import re
    with open(dsn_path, "r", encoding="utf-8",
              errors="replace") as source:
        text = source.read()
    network_match = re.search(r'\(network(?=\s|\))', text)
    if network_match is None:
        raise RuntimeError("DSN has no network section")
    network, network_end = _carve(text, network_match.start())
    if not network.rstrip().endswith(")"):
        raise RuntimeError("DSN network section is unbalanced")

    out = []
    i = 0
    kept = stripped = 0
    while True:
        j = network.find("(net ", i)
        if j < 0:
            out.append(network[i:])
            break
        out.append(network[i:j])
        block, nxt = _carve(network, j)
        m = re.match(r'\(net\s+("([^"]*)"|\S+)', block)
        name = (m.group(2) if m and m.group(2) is not None
                else (m.group(1) if m else "")).strip()
        if not name or m is None:
            raise RuntimeError("malformed net declaration in DSN network section")
        if name in keep_nets:
            kept += 1
            out.append(block)
        else:
            stripped += 1
            # keep the net DECLARED but with an empty pin list (FR then has nothing
            # to route for it; class bindings elsewhere in the file stay valid)
            hdr = re.match(r'(\(net\s+(?:"[^"]*"|\S+))', block).group(1)
            out.append(hdr + " (pins))")
        i = nxt
    rewritten = (text[:network_match.start()] + "".join(out)
                 + text[network_end:])
    with open(dsn_path, "w", encoding="utf-8") as sink:
        sink.write(rewritten)
    return kept, stripped


def _lock_nets_copper(board, nets):
    """SetLocked on every track/via of *nets*; returns count. Locked copper exports as
    (type fix); force_protect upgrades it so the next FR pass treats it as immovable."""
    n = 0
    for t in board.GetTracks():
        if t.GetNetname() in nets and not t.IsLocked():
            t.SetLocked(True)
            n += 1
    return n


def fully_connected_nets(board, nets):
    """Partition requested nets by exact pad ownership connectivity.

    A tier is allowed to leave partial copper for the residual router, but that
    net must not be promoted into the immutable protect set.  The former code
    protected the tier declaration wholesale, including nets Freerouting had
    not completed, and thereby converted recoverable ratlines into permanent
    obstacles.  This proof is topology based and works for two-terminal and
    multidrop nets without relying on names or a board-specific allowlist.
    """
    requested = {str(net) for net in (nets or ()) if net}
    board.BuildConnectivity()
    connectivity = board.GetConnectivity()
    pads_by_net = {}
    for footprint in board.GetFootprints():
        for pad in footprint.Pads():
            name = pad.GetNetname()
            if name in requested:
                pads_by_net.setdefault(name, []).append(pad)

    complete, incomplete = set(), set()
    for name in requested:
        pads = pads_by_net.get(name, ())
        if len(pads) < 2:
            # No route obligation exists for a one-pad pseudo-net, but it must
            # not become protected critical copper either.
            incomplete.add(name)
            continue
        expected = set()
        for pad in pads:
            parent = pad.GetParentFootprint()
            expected.add((parent.GetReference(), str(pad.GetNumber())))
        reached = set()
        first = pads[0]
        parent = first.GetParentFootprint()
        reached.add((parent.GetReference(), str(first.GetNumber())))
        try:
            for item in connectivity.GetConnectedItems(first):
                if item.GetClass() != "PAD" or item.GetNetname() != name:
                    continue
                owner = item.GetParentFootprint()
                reached.add((owner.GetReference(), str(item.GetNumber())))
        except Exception:                              # noqa: BLE001
            pass
        (complete if expected.issubset(reached) else incomplete).add(name)
    return complete, incomplete


def parent_copper_nets_outside_tier(board, tier_nets):
    """Return parent track/via nets a speculative tier does not own.

    A tier-restricted DSN removes ordinary-net pins from the router's workset.
    Some SES imports consequently omit or replace pre-existing copper on those
    nets even though the tier never owned them.  Staged routing is a delta
    transaction: every parent copper net outside the active tier must be
    restored byte-for-byte before admission.
    """
    owned = {str(net) for net in (tier_nets or ()) if net}
    return {
        str(item.GetNetname())
        for item in board.GetTracks()
        if item.GetNetname() and str(item.GetNetname()) not in owned
    }


def restore_protected_copper_prefix(source_path, candidate_path, nets):
    """Replace backend echoes of immutable nets with their exact source copper.

    Freerouting must see protected wires in the DSN so it can route around
    them, but some SES imports echo those fixed wires as additional ordinary
    tracks.  Comparing that raw import against the frozen-prefix contract then
    rejects an otherwise valid tier even though the tier never owned those
    nets.  Admission is a delta operation: discard every candidate track/via
    on the protected nets and restore the exact source items before geometry
    comparison.  New tier-net copper remains untouched and still faces the
    structural DRC and connectivity gates below.
    """
    import pcbnew

    selected = {str(net) for net in (nets or ()) if str(net)}
    if not selected:
        return {"nets": [], "removed": 0, "restored": 0}
    # KiCad's SWIG wrapper owns a process-global current board: loading the
    # candidate invalidates an already loaded source BOARD handle on real
    # project files (small synthetic BOARDs do not reliably expose this).
    # Detach the authoritative items while the source is still current, then
    # release it before loading the candidate.  Keep the net name separately
    # and rebind each duplicate to the candidate's own NETINFO_ITEM below.
    source = pcbnew.LoadBoard(source_path)
    restoration = []
    for item in source.GetTracks():
        if item.GetNetname() not in selected:
            continue
        duplicate = item.Duplicate()
        # ``Duplicate`` deliberately allocates a fresh KIID.  Geometry-only
        # comparison hid that identity churn, but downstream transactions use
        # exact UUIDs to prove that priority vias and locked prefixes survived.
        # Restore the source KIID as part of the delta transaction: every
        # selected candidate item is removed below, so the identity is unique
        # in the destination and safe to retain.
        duplicate.m_Uuid.Clone(item.m_Uuid)
        restoration.append((item.GetNetname(), duplicate))
    del source
    candidate = pcbnew.LoadBoard(candidate_path)
    removed = 0
    for item in list(candidate.GetTracks()):
        if item.GetNetname() in selected:
            candidate.Remove(item)
            removed += 1
    restored = 0
    for net_name, item in restoration:
        item.SetNet(candidate.FindNet(net_name))
        candidate.Add(item)
        restored += 1
    pcbnew.SaveBoard(candidate_path, candidate)
    return {"nets": sorted(selected), "removed": removed,
            "restored": restored}


def _import_stage_worker(cur, ses, nxt, final, pours, skip_locked_taps):
    """Import one SES in a disposable pcbnew process.

    ``cec_fr.import_ses`` performs several Remove/load/fill operations.  KiCad's
    SWIG bindings can leave the interpreter's global board state invalid after
    that sequence; a later ``LoadBoard`` then returns a bare ``SwigPyObject``.
    Tiered routing must therefore treat every import as a process boundary, the
    same discipline used by Hub materialization.
    """
    import cec_fr
    if final:
        cec_fr.import_ses(cur, ses, nxt, power_pours=pours,
                          skip_locked_taps=skip_locked_taps)
    else:
        cec_fr.import_ses(cur, ses, nxt, fill_zones=False, fix_annular=False,
                          power_pours=(), kelvin_taps=False)


def _lock_stage_worker(board_path, nets):
    """Lock routed tier copper in a second fresh pcbnew process."""
    import pcbnew
    board = pcbnew.LoadBoard(board_path)
    if not hasattr(board, "GetTracks"):
        raise RuntimeError("pcbnew.LoadBoard returned invalid board state")
    n = _lock_nets_copper(board, set(nets))
    pcbnew.SaveBoard(board_path, board)
    return n


def _route_quality_stage_worker(board_path, tier_nets, pre_track_ids):
    """Remove newly generated acute/backtracking copper before ownership.

    A connected net is not automatically a promotable net.  Run the generic
    route-geometry authority over only this tier's newly generated UUIDs, mark
    every tier net as critical for this admission, and remove only the new
    copper of any offending net.  Earlier protected copper is outside the UUID
    scope and can never be touched.  The later residual router retains
    ownership of the now-incomplete net.
    """
    import pcbnew
    import cec_route_quality

    board = pcbnew.LoadBoard(board_path)
    before = set(pre_track_ids or ())
    generated = {
        item.m_Uuid.AsString() for item in board.GetTracks()
        if item.m_Uuid.AsString() not in before}
    report = cec_route_quality.analyze_board(
        board, critical_nets=set(tier_nets or ()),
        track_uuid_scope=generated)
    bad_nets = {
        row.get("net") for row in (report.get("issues") or ())
        if row.get("severity") == "blocking" and row.get("net")}
    removed = 0
    if bad_nets:
        for item in list(board.GetTracks()):
            if (item.m_Uuid.AsString() in generated
                    and item.GetNetname() in bad_nets):
                board.Remove(item)
                removed += 1
        pcbnew.SaveBoard(board_path, board)
    report["removed_generated_items"] = removed
    report["refused_nets"] = sorted(bad_nets)
    return report


def foreign_pour_admission(board_path):
    """Fail-closed absolute-pour admission for every routed tier artifact."""
    import cec_pour_clearance

    summary = cec_pour_clearance.inspect_file(board_path)
    applicable = bool(summary.get("applicable"))
    clean = (summary.get("status") != "error"
             and int(summary.get("n_tracks", 0)) == 0
             and int(summary.get("n_vias", 0)) == 0)
    return {"ok": bool(clean), "applicable": applicable,
            "status": summary.get("status"),
            "tracks": int(summary.get("n_tracks", 0)),
            "vias": int(summary.get("n_vias", 0)),
            "by_pour": summary.get("by_pour") or {},
            "items": list(summary.get("tracks") or ())
                     + list(summary.get("vias") or ())}


def compile_tier_keepouts(board_path, tier_nets, locked_nets, hints=(),
                          include_locked_copper=None):
    """Compile every obstacle the staged router must see.

    A staged DSN strips foreign pin lists, so it cannot rely on the full-route
    wrapper to add physical guards later.  In particular, Freerouting does not
    know KiCad's copper-to-board-edge rule and does not preserve a no-net
    fiducial pad's local clearance.  Compile locked copper, caller
    reservations, the width-aware board-edge guard, via-in-SMD-pad guard,
    decorative-copper guard, and assembly fiducials here, then deduplicate
    exact geometry before baking the tier-only export.
    """
    import cec_fr
    import cec_route_preflight

    tier = set(tier_nets or ())
    if include_locked_copper is None:
        include_locked_copper = (
            os.environ.get("CEC_LOCKED_COPPER_KEEPOUTS", "1") != "0")
    rows = []
    if include_locked_copper:
        rows.extend(cec_fr.locked_copper_keepouts(
            board_path, only_nets=set(locked_nets or ()) - tier))
    rows.extend(list(hints or ()))
    # Every routing backend consumes the same routed-object ownership map.
    # The old tier adapter received only caller ``hints`` (the legacy broad
    # pour corridors), while precision/global routing consumed the exact
    # route-preflight compiler.  A successful early access tier could
    # therefore put locked signal copper through a future frozen power-via
    # barrel; the later power compiler correctly refused to drill through it.
    # Convert the exact per-layer rectangles to disposable DSN keepouts here.
    # Same-net ownership remains legal for a tier that explicitly owns that
    # routed object; all foreign tiers see a hard tracks+vias obstacle.
    reservations = cec_route_preflight.compile_route_reservations(board_path)
    if reservations.get("enabled"):
        for index, reserved in enumerate(reservations.get("corridors") or ()):
            owner = str(reserved.get("net") or "")
            if owner and owner in tier:
                continue
            layers = reserved.get("layers")
            if not layers:
                layer = reserved.get("layer")
                layers = (layer,) if layer else ()
            if not layers:
                raise RuntimeError(
                    "route reservation %d has no routing layer" % index)
            row = {
                "name": "route_reservation_%s_%d" % (
                    str(reserved.get("kind") or "region"), index),
                "layers": tuple(str(layer) for layer in layers),
                "allow_tracks": False,
                "allow_vias": False,
            }
            if reserved.get("polygon"):
                row["polygon"] = tuple(
                    (float(point[0]), float(point[1]))
                    for point in reserved["polygon"])
                if reserved.get("holes"):
                    row["holes"] = tuple(
                        tuple((float(point[0]), float(point[1]))
                              for point in hole)
                        for hole in reserved["holes"])
            else:
                row.update({key: float(reserved[key])
                            for key in ("x0", "y0", "x1", "y1")})
            rows.append(row)
    rows.extend(cec_fr.edge_keepout(board_path))
    rows.extend(cec_fr.smd_via_keepouts(board_path))
    rows.extend(cec_fr.decorative_copper_keepouts(board_path))
    rows.extend(cec_fr.fiducial_keepouts(board_path))
    unique, seen = [], set()
    for row in rows:
        key = json.dumps(row, sort_keys=True, separators=(",", ":"),
                         default=str)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    return unique


def _spawn_apply(func, args):
    """Run a pcbnew mutation in an isolated spawn worker."""
    import multiprocessing as mp
    with mp.get_context("spawn").Pool(1) as pool:
        return pool.apply(func, args)


def default_tiers(board_path):
    """Tier-1 = the coupled/critical signal set FR handles worst when contended: diff
    pairs (_P/_N convention) + the CAN pair class. (Kelvin force/sense pins are already
    excluded from FR entirely by the production DSN policies; pours are post-route.)"""
    import cec_score
    rules = cec_score.Rules.from_board(board_path)
    tier1 = set()
    for a, b in getattr(rules, "diff_pairs", ()) or ():
        tier1 |= {a, b}
    import pcbnew
    b = pcbnew.LoadBoard(board_path)
    for n in {t.GetNetname() for t in b.GetTracks()} | \
             {p.GetNetname() for fp in b.GetFootprints() for p in fp.Pads()}:
        if n and ("CAN_H" in n or "CAN_L" in n):
            tier1.add(n)
    return [sorted(tier1)] if tier1 else []


def adaptive_retry_chunks(incomplete_nets):
    """Deterministically bisect an incomplete tier for one less-contended retry.

    Successful nets are already promoted to immutable ownership by the caller.
    Retrying only the residual set preserves that work while giving failed
    nets a smaller simultaneous search problem.  The split is deliberately
    bounded and board-agnostic; a singleton receives one solo retry.
    """
    names = sorted({str(net) for net in (incomplete_nets or ()) if net})
    if len(names) <= 1:
        return [names] if names else []
    pivot = (len(names) + 1) // 2
    return [names[:pivot], names[pivot:]]


def _route_tiered_in_work(placed_board, out_board, *, work, tiers=None, passes=8,
                          opt=10, threads=1, seed=None, timeout=900, verbose=True,
                          pre_locked_nets=(), hints=(), skip_locked_taps=False,
                          include_residual=True, adaptive_retry_depth=1):
    """The tiered ladder. tiers = list of net-name lists; a final residual pass over
    everything else is implicit. Returns a report dict (per-tier stats + total wall).

    pre_locked_nets: nets whose LOCKED copper already exists on the input board (the S2
    precision pass) -- protected in EVERY tier's DSN. skip_locked_taps: forwarded to the
    final import (precision already laid the kelvin taps -- never double-lay)."""
    import pcbnew
    import cec_fr
    import cec_fr02
    if tiers is None:
        tiers = default_tiers(placed_board)
    cur = os.path.join(work, "t0.kicad_pcb")
    shutil.copy2(placed_board, cur)
    # Route authority is part of the board artifact. Dropping the exact
    # pourfirst state in tier scratch storage makes keepout/admission fall back
    # to broad derived slabs: valid locked copper then appears to cross pours
    # that do not exist in the source artifact. Use the shared copy boundary so
    # project rules, pour plan, frozen polygons, and provenance stay together.
    cec_fr.copy_project_sidecars(placed_board, cur)
    locked_nets = set(pre_locked_nets)
    report = {"tiers": [], "work": work, "threads": int(threads)}
    current_score = None
    t_all = time.monotonic()
    stages = [
        {"tier": set(t), "retry_depth": 0, "retry_parent": None}
        for t in tiers
    ]
    if include_residual:
        stages.append({"tier": None, "retry_depth": 0,
                       "retry_parent": None})
    # include_residual=False = TIER-ONLY mode (the wave-14 composition: refused precision
    # pairs get their solo uncontended FR pass here; the ORACLE's own route_once then
    # fills the true residual under the full recipe hints/pours).
    jar = cec_fr.ensure_jar(None)
    for i, stage in enumerate(stages):
        tier = stage["tier"]
        retry_depth = int(stage.get("retry_depth", 0))
        final = tier is None
        t0 = time.monotonic()
        before_board = pcbnew.LoadBoard(cur)
        before_track_ids = {
            track.m_Uuid.AsString() for track in before_board.GetTracks()}
        parent_delta_restore_nets = (
            parent_copper_nets_outside_tier(before_board, tier)
            if not final else set())
        tier_signal_layers = None
        dsn = os.path.join(work, f"t{i}.dsn")
        ses = os.path.join(work, f"t{i}.ses")
        export_src = cur
        if not final:
            # BLINDNESS CURE (2026-07-14, convicted by the M4 ablation + the pre-tier
            # DRC jump 13 -> 219 structural): _dsn_restrict_to_nets strips foreign
            # nets' PIN lists, and FR 1.7.0 drops protect wires of pin-less nets from
            # its obstacle model (the same measured mechanism route_once cured) -- so
            # the tier route plowed through locked cell/lane copper and _lock_nets_
            # copper then LOCKED the damage in. Bake every OTHER net's locked copper
            # as net-blind rule-area keepouts on the export copy (the SES still
            # imports onto the clean `cur`, so no keepout zone ever reaches output).
            try:
                _all_locked = {tr.GetNetname() for tr in pcbnew.LoadBoard(cur).GetTracks()
                               if tr.IsLocked()}
                # RESERVED POUR CORRIDORS travel with the tier (2026-07-25). A pair
                # the precision router REFUSES lands here, and this route LOCKS its
                # result -- so without the corridors the tier lays locked copper
                # straight through the pours, which is exactly what "FR is routing
                # through all of the pours" turned out to be: the eps USB pair,
                # refused upstream, arrived as 31 locked segments crossing
                # /SENSEC1_LO and /SENSEC2_LO. The main route already gets these.
                _ko = compile_tier_keepouts(
                    cur, tier, _all_locked, hints=hints)
                if _ko:
                    export_src = os.path.join(work, f"t{i}-hinted.kicad_pcb")
                    cec_fr.bake_hints(cur, export_src, keepouts=_ko)
                    if verbose:
                        mode = ("full locked-copper geometry" if
                                os.environ.get(
                                    "CEC_LOCKED_COPPER_KEEPOUTS", "1") != "0"
                                else "DSN protect plus reservations")
                        print(f"[staged-fr] tier {i}: {len(_ko)} obstacle "
                              f"keepout(s) baked ({mode})", flush=True)
            except Exception as e:                              # noqa: BLE001
                raise RuntimeError(
                    "staged tier obstacle compilation failed closed: %s: %s"
                    % (type(e).__name__, e)) from e
        cec_fr.export_dsn(export_src, dsn)
        if not final:
            # A precision-refused USB/CAN pair still needs an adjacent solid
            # reference when handed to FR.  The ordinary layer policy only
            # excludes GND planes and therefore allowed the EPS USB pair onto
            # In3 (a PWR role), producing connected copper that the independent
            # pair-physics gate correctly rejected.  Restrict pair-only tiers
            # to profile-declared signal layers adjacent to dedicated GND.
            pairish = all(
                (name.endswith(("_P", "_N"))
                 or "CAN_H" in name or "CAN_L" in name)
                for name in tier)
            if pairish:
                import cec_fab_profile
                tier_board = pcbnew.LoadBoard(cur)
                tier_signal_layers = list(
                    cec_fab_profile.referenced_signal_layers(
                        tier_board, hint=cur))
                enabled = set(cec_fab_profile.enabled_copper_layers(tier_board))
                forbidden = sorted(enabled - set(tier_signal_layers))
                # DSN uses the human layer aliases (GND/SIG2/PWR/GND2), not
                # the canonical KiCad identifiers above.  Passing ``In3.Cu``
                # therefore used to report the intended policy while silently
                # leaving the exported ``PWR`` layer routable.
                aliases = [tier_board.GetLayerName(tier_board.GetLayerID(name))
                           for name in forbidden]
                cec_fr._dsn_force_power_layers(dsn, aliases)
                with open(dsn, encoding="utf-8", errors="replace") as source:
                    deck = source.read()
                missing = []
                for alias in aliases:
                    token = r'(?:"' + re.escape(alias) + r'"|'
                    token += re.escape(alias) + r')'
                    if not re.search(r'\(layer\s+' + token
                                     + r'\s*\(\s*type\s+power\s*\)', deck):
                        missing.append(alias)
                if missing:
                    raise RuntimeError(
                        "pair layer policy was not applied to DSN layer(s): %s"
                        % ", ".join(missing))
            kept, stripped = _dsn_restrict_to_nets(dsn, tier | locked_nets)
        else:
            kept = stripped = None
        if locked_nets:
            cec_fr02.force_protect_in_dsn(dsn, sorted(locked_nets))
        fr_wd = tempfile.mkdtemp(prefix="cec_staged_fr_", dir=work)
        try:
            cec_fr.run_freerouting(
                dsn, ses, passes=passes, opt_time=opt,
                threads=int(threads), seed=seed, jar=jar,
                workdir=fr_wd, timeout=timeout)
        except Exception as exc:                           # noqa: BLE001
            # A tier is speculative; previously admitted prefixes are the
            # authority.  One adaptive child/backend crash must not erase
            # successful parent or sibling ownership by escaping the whole
            # transaction.  Keep ``cur`` byte-identical, publish the precise
            # refusal, and let later bounded stages/residual routing continue.
            row = {
                "tier": (sorted(tier) if tier else "RESIDUAL"),
                "refused": True,
                "reason": "routing_backend_error",
                "error": "%s: %s" % (type(exc).__name__, exc),
                "retry_depth": retry_depth,
                "retry_parent": stage.get("retry_parent"),
                "wall_s": round(time.monotonic() - t0, 1),
            }
            report["tiers"].append(row)
            if verbose:
                print(
                    "[staged-fr] tier %d REFUSED: routing backend error; "
                    "prior prefix retained (%s: %s)" % (
                        i, type(exc).__name__, exc), flush=True)
            continue
        nxt = os.path.join(work, f"t{i + 1}.kicad_pcb")
        pours = cec_fr.derive_power_pours(cur) if final else []
        _spawn_apply(_import_stage_worker,
                     (cur, ses, nxt, final, pours, skip_locked_taps))
        # The route backend is never an acceptance authority.  Inspect each
        # imported tier *before* any of its copper is promoted to immutable
        # ownership.  This closes the regression where a precision-refused
        # pair or residual route crossed a corridor, was locked, and only then
        # appeared as a final-dashboard warning.
        pour_admission = foreign_pour_admission(nxt)
        pour_evacuation = None
        if not pour_admission.get("ok") and not final:
            # Do not throw away every legal net in a multi-net tier because a
            # few newly generated primitives entered an immutable pour. Remove
            # only the exact convicted UUIDs in an isolated transaction,
            # protecting every previously owned net. Connectivity below then
            # promotes the clean completed subset and adaptive retries receive
            # only the disturbed/incomplete nets. No foreign item is waived or
            # allowed to survive into ownership.
            import cec_pour_clearance
            evacuated = os.path.join(
                work, f"t{i + 1}-pour-evacuated.kicad_pcb")
            pour_evacuation = cec_pour_clearance.evacuate_file(
                nxt, evacuated, protected_nets=sorted(locked_nets))
            if pour_evacuation.get("ok"):
                nxt = evacuated
                pour_admission = foreign_pour_admission(nxt)
                if verbose:
                    print(
                        "[staged-fr] tier %d evacuated %d foreign pour "
                        "item(s); clean subset continues to ownership" % (
                            i, int(pour_evacuation.get(
                                "removed_count", 0))), flush=True)
        if not pour_admission.get("ok"):
            report["tiers"].append({
                "tier": (sorted(tier) if tier else "RESIDUAL"),
                "refused": True,
                "reason": "foreign_on_high_current_pour",
                "foreign_pour_admission": pour_admission,
                "foreign_pour_evacuation": pour_evacuation,
                "wall_s": round(time.monotonic() - t0, 1),
            })
            if verbose:
                print(
                    "[staged-fr] tier %d REFUSED: foreign-on-pour "
                    "%dt/%dv -- result dropped before ownership" % (
                        i, pour_admission["tracks"],
                        pour_admission["vias"]), flush=True)
            continue
        if not final:
            # A restricted tier owns only its declared nets.  Restore every
            # other parent track/via net before connectivity or DRC admission;
            # otherwise an SES backend that omits pin-less ordinary wiring can
            # create a newly open net and make every useful tier look unsafe.
            # This is broader than the immutable-prefix contract below: it
            # protects ordinary already-routed copper too, without locking it
            # into future ownership.
            parent_delta_restore = None
            if parent_delta_restore_nets:
                parent_delta_restore = _spawn_apply(
                    restore_protected_copper_prefix,
                    (cur, nxt, tuple(sorted(parent_delta_restore_nets))))
            # Ownership is cumulative. FR imports protected wires as ordinary
            # unlocked copper; locking only the *new* tier silently released
            # every earlier pair/cell to the next pass. Verify geometry before
            # restoring lock state so a later tier can never inherit a changed
            # version of earlier precision copper.
            protected_contract = (cec_fr.copper_geometry_signature(
                cur, sorted(locked_nets)) if locked_nets else None)
            if protected_contract:
                # This helper necessarily loads both the source and candidate.
                # Keep that transaction outside the long-lived orchestrator:
                # KiCad's process-global SWIG board state remains invalid after
                # a second LoadBoard even when the helper has returned.
                prefix_restore = _spawn_apply(
                    restore_protected_copper_prefix,
                    (cur, nxt, protected_contract.get("nets") or ()))
                actual_contract = cec_fr.copper_geometry_signature(
                    nxt, protected_contract.get("nets") or ())
                if (actual_contract.get("sha256")
                        != protected_contract.get("sha256")):
                    report["tiers"].append({
                        "tier": sorted(tier), "refused": True,
                        "reason": "prior_tier_geometry_changed",
                        "expected": protected_contract,
                        "actual": actual_contract,
                        "prefix_restore": prefix_restore,
                        "wall_s": round(time.monotonic() - t0, 1),
                    })
                    if verbose:
                        print(f"[staged-fr] tier {i} REFUSED: prior-tier "
                              "copper contract changed", flush=True)
                    continue
            route_quality = _spawn_apply(
                _route_quality_stage_worker,
                (nxt, tuple(sorted(tier)), tuple(sorted(before_track_ids))))
            # Score under the real project/custom-rule authority.  The
            # sanitizer below may need exact KiCad DRC identities before the
            # ordinary admission block copies sidecars.
            for ext in (".kicad_pro", ".kicad_dru"):
                source = cur[:-len(".kicad_pcb")] + ext
                if os.path.isfile(source):
                    shutil.copy2(source, nxt[:-len(".kicad_pcb")] + ext)
            tier_after_quality = pcbnew.LoadBoard(nxt)
            tier_generated_ids = {
                item.m_Uuid.AsString()
                for item in tier_after_quality.GetTracks()
                if item.m_Uuid.AsString() not in before_track_ids}
            tier_import_sanitation, _tier_sanitized_score = (
                sanitize_tier_import(nxt, cur, tier_generated_ids))
            if not tier_import_sanitation.get("accepted"):
                report["tiers"].append({
                    "tier": sorted(tier), "refused": True,
                    "reason": "tier_import_sanitation_failed",
                    "import_sanitation": tier_import_sanitation,
                    "parent_delta_restore": parent_delta_restore,
                    "wall_s": round(time.monotonic() - t0, 1),
                })
                if verbose:
                    print(
                        f"[staged-fr] tier {i} REFUSED: imported copper "
                        "could not be made monotonic", flush=True)
                continue
            tier_complete, tier_incomplete = fully_connected_nets(
                pcbnew.LoadBoard(nxt), tier)
            refused_quality_nets = set(
                route_quality.get("refused_nets") or ())
            tier_complete -= refused_quality_nets
            tier_incomplete |= refused_quality_nets
            incomplete_prefix_restore = None
            if tier_incomplete:
                # A tier owns only a proved pad-complete net.  Freerouting may
                # otherwise carry an unfinished stub, rip up useful incoming
                # copper, or echo a disconnected island into the next retry.
                # Those fragments create extra connectivity components (the
                # production failure was 52 -> 54 opens) and consume future
                # escape channels despite never earning ownership. Restore
                # every incomplete net to its exact pre-tier geometry before
                # retries or downstream stages see it.
                incomplete_contract = cec_fr.copper_geometry_signature(
                    cur, sorted(tier_incomplete))
                incomplete_prefix_restore = _spawn_apply(
                    restore_protected_copper_prefix,
                    (cur, nxt, tuple(sorted(tier_incomplete))))
                actual_incomplete = cec_fr.copper_geometry_signature(
                    nxt, sorted(tier_incomplete))
                if (actual_incomplete.get("sha256")
                        != incomplete_contract.get("sha256")):
                    report["tiers"].append({
                        "tier": sorted(tier), "refused": True,
                        "reason": "incomplete_tier_restore_failed",
                        "expected": incomplete_contract,
                        "actual": actual_incomplete,
                        "incomplete_prefix_restore":
                            incomplete_prefix_restore,
                        "wall_s": round(time.monotonic() - t0, 1),
                    })
                    if verbose:
                        print(
                            f"[staged-fr] tier {i} REFUSED: incomplete-net "
                            "copper could not be restored", flush=True)
                    continue
        # The imported board must be scored under the same project/custom-rule
        # authority as its parent.  Copy sidecars before DRC, not only after a
        # candidate has already been admitted.
        for ext in (".kicad_pro", ".kicad_dru"):
            source = cur[:-len(".kicad_pcb")] + ext
            if os.path.isfile(source):
                shutil.copy2(source, nxt[:-len(".kicad_pcb")] + ext)

        # REFUSE-LOUD GATE (ladder doctrine): evaluate the complete structural
        # identity ledger only after non-authoritative incomplete copper has
        # been removed.  The historical ``DRC delta <= +6`` tolerance is the
        # source of the repair cascade: it explicitly promoted new clearances
        # and left later stages to chase them.  A tier may close old debt but
        # may never invent a new DRC identity or newly open net.  Cache the
        # admitted parent's score so this is no slower than the former two-DRC
        # count comparison and is cheaper across multiple child retries.
        if current_score is None:
            current_score = _stage_score(cur)
        candidate_score = _stage_score(nxt)
        stage_admission = _tier_admission(current_score, candidate_score)
        if not stage_admission["accepted"]:
            refused_row = {
                "tier": (sorted(tier) if tier else "RESIDUAL"),
                "refused": True,
                "reason": stage_admission["decision"],
                "admission": stage_admission,
                "wall_s": round(time.monotonic() - t0, 1),
            }
            if not final:
                refused_row["incomplete_prefix_restore"] = (
                    incomplete_prefix_restore)
                refused_row["parent_delta_restore"] = parent_delta_restore
            report["tiers"].append(refused_row)
            if verbose:
                print(
                    "[staged-fr] tier %d REFUSED: %s -- candidate dropped"
                    % (i, stage_admission["decision"]), flush=True)
            continue                       # cur unchanged; tier nets stay unrouted
        if not final:
            locked_nets |= tier_complete
            nlocked = _spawn_apply(
                _lock_stage_worker,
                (nxt, tuple(sorted(locked_nets))))
        row = {"tier": (sorted(tier) if tier else "RESIDUAL"),
               "kept_nets": kept, "stripped_nets": stripped,
               "admission": stage_admission,
               "wall_s": round(time.monotonic() - t0, 1),
               "retry_depth": retry_depth,
               "retry_parent": stage.get("retry_parent")}
        after_board = pcbnew.LoadBoard(nxt)
        generated_owner_nets = (set(tier) if tier is not None else
                                {track.GetNetname()
                                 for track in after_board.GetTracks()
                                 if track.GetNetname()} - set(locked_nets))
        generated = [
            {
                "uuid": track.m_Uuid.AsString(),
                "net": track.GetNetname(),
                "kind": track.GetClass(),
            }
            for track in after_board.GetTracks()
            if (track.m_Uuid.AsString() not in before_track_ids
                and track.GetNetname() in generated_owner_nets)]
        # This exact UUID ownership is what lets a later final DRC item be
        # attributed to a detailed-routing tier instead of merely associated
        # by net name.  Keep the full list in the tier report; fresh waves may
        # compact the surrounding record but must not discard this evidence.
        row["generated_items"] = generated
        row["generated_item_count"] = len(generated)
        if not final:
            row["locked_segments"] = nlocked
            row["completed_nets"] = sorted(tier_complete)
            row["incomplete_nets"] = sorted(tier_incomplete)
            row["route_quality"] = route_quality
            row["import_sanitation"] = tier_import_sanitation
            row["foreign_pour_admission"] = pour_admission
            if incomplete_prefix_restore is not None:
                row["incomplete_prefix_restore"] = (
                    incomplete_prefix_restore)
            if pour_evacuation is not None:
                row["foreign_pour_evacuation"] = pour_evacuation
            if protected_contract:
                row["prefix_restore"] = prefix_restore
            if parent_delta_restore is not None:
                row["parent_delta_restore"] = parent_delta_restore
            if tier_signal_layers is not None:
                row["signal_layers"] = tier_signal_layers
            if (tier_incomplete
                    and retry_depth < max(0, int(adaptive_retry_depth))):
                chunks = adaptive_retry_chunks(tier_incomplete)
                retry_rows = [
                    {"tier": set(chunk),
                     "retry_depth": retry_depth + 1,
                     "retry_parent": i}
                    for chunk in chunks if chunk
                ]
                # Insert before later declared tiers and the residual pass.
                # Python's list iterator observes these bounded insertions.
                stages[i + 1:i + 1] = retry_rows
                row["adaptive_retry_children"] = [
                    sorted(child["tier"]) for child in retry_rows]
        report["tiers"].append(row)
        if verbose:
            print(f"[staged-fr] pass {i}: {row}", flush=True)
        cur = nxt
        current_score = candidate_score
    shutil.copy2(cur, out_board)
    cec_fr.copy_project_sidecars(cur, out_board)
    report["total_wall_s"] = round(time.monotonic() - t_all, 1)
    return report


def route_tiered(placed_board, out_board, *, tiers=None, passes=8, opt=10,
                 threads=1, seed=None,
                 timeout=900, verbose=True, pre_locked_nets=(), hints=(), skip_locked_taps=False,
                 include_residual=True, adaptive_retry_depth=1):
    """Run the tiered ladder in disposable scratch storage.

    The output board and its project/rule files are copied out before cleanup. Set
    ``CEC_STAGED_FR_KEEP_INTERMEDIATES=1`` only when the tier DSN/SES files are needed
    for diagnosis; closure waves otherwise must not retain one work tree per probe.
    """
    work = tempfile.mkdtemp(prefix="cec_staged_", dir=os.environ.get("TMPDIR") or None)
    keep = os.environ.get("CEC_STAGED_FR_KEEP_INTERMEDIATES", "0") == "1"
    try:
        report = _route_tiered_in_work(
            placed_board, out_board, work=work, tiers=tiers, passes=passes,
            opt=opt, threads=threads, seed=seed, timeout=timeout,
            verbose=verbose,
            pre_locked_nets=pre_locked_nets, hints=hints,
            skip_locked_taps=skip_locked_taps,
            include_residual=include_residual,
            adaptive_retry_depth=adaptive_retry_depth,
        )
        if not keep:
            report["work"] = None
        return report
    finally:
        if not keep:
            shutil.rmtree(work, ignore_errors=True)


def measure(placed_board, *, seed=0, passes=8, opt=10):
    """A1's honest datapoint: single-shot vs tiered at the SAME per-pass effort and a
    pinned seed, scored identically. (FR has no real seed flag -- the pin is for logs;
    the A5 seed patch is what makes this comparison truly noise-free.)"""
    import cec_score
    import cec_fr
    work = tempfile.mkdtemp(prefix="cec_staged_ab_")
    single = os.path.join(work, "single.kicad_pcb")
    cand = cec_fr.route_once(placed_board, single, passes=passes, opt_time=opt,
                             seed=seed, power_pours=cec_fr.derive_power_pours(placed_board))
    m1 = cec_score.score(single) if cand.ok else None
    tiered_out = os.path.join(work, "tiered.kicad_pcb")
    rep = route_tiered(placed_board, tiered_out, passes=passes, opt=opt, seed=seed)
    m2 = cec_score.score(tiered_out)
    def _row(m):
        return None if m is None else {"unconn": m.unconnected, "drc": m.drc,
                                       "kelvin": m.kelvin_ok, "diffpair": m.diffpair_ok,
                                       "vias": m.vias, "len": round(m.length, 1)}
    return {"single": _row(m1), "tiered": _row(m2), "tier_report": rep, "work": work}


def main():
    import argparse
    ap = argparse.ArgumentParser(description="staged (tiered) Freerouting ladder")
    ap.add_argument("board", help="a PLACED .kicad_pcb")
    ap.add_argument("--out", default=None)
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--passes", type=int, default=8)
    ap.add_argument("--opt", type=int, default=10)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--tier-only", action="store_true",
                    help="route/lock the critical tiers without a residual pass")
    ap.add_argument(
        "--tier", action="append", default=[], metavar="NET,NET",
        help=("explicit comma-separated tier; repeat to route critical groups "
              "sequentially before the residual pass"))
    ap.add_argument(
        "--pre-locked-net", action="append", default=[], metavar="NET",
        help="net whose existing locked copper is an input ownership contract")
    a = ap.parse_args()
    if a.measure:
        print(json.dumps(measure(a.board, seed=a.seed, passes=a.passes, opt=a.opt),
                         indent=1, default=str))
    else:
        out = a.out or a.board[:-len(".kicad_pcb")] + "-tiered.kicad_pcb"
        tiers = ([tuple(name.strip() for name in row.split(",")
                        if name.strip()) for row in a.tier]
                 if a.tier else None)
        print(json.dumps(route_tiered(a.board, out, passes=a.passes, opt=a.opt,
                                      seed=a.seed, timeout=a.timeout,
                                      tiers=tiers,
                                      pre_locked_nets=a.pre_locked_net,
                                      include_residual=not a.tier_only),
                         indent=1, default=str))


if __name__ == "__main__":
    main()
