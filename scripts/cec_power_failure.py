"""Typed exact-power failures projected into existing placement proposals."""
from __future__ import annotations

import math


def construction_probe_eligible(craft, craft_gate, *, physical_gates,
                                requires_authority, routed=False):
    """Schedule a private exact-power diagnosis, never defer a release gate.

    A legacy rail constructor can fail although an alternate exact planner
    has a useful path or better obstacle evidence. Only an otherwise legal
    open placement with a complete, explicit rail-refusal report may probe
    that alternative. Missing reports, unrelated craft failures and routed
    incumbents remain out of scope. The caller retains the failed gate.
    """
    if (requires_authority is not True or routed is not False
            or not physical_gates
            or any(value is not True for value in physical_gates)):
        return False
    if not isinstance(craft, dict) or not isinstance(craft_gate, dict):
        return False
    rail = craft.get('force_rail') or {}
    total, laid = rail.get('total'), rail.get('laid')
    return bool(craft.get('ok') is False and not craft.get('errors')
        and craft_gate.get('ok') is False
        and craft_gate.get('blockers') == ['force_rail placement evidence failed']
        and rail.get('schema') == 1 and rail.get('applicable') is True
        and rail.get('ok') is False and not rail.get('error')
        and type(total) is int and type(laid) is int and 0 <= laid < total
        and isinstance(rail.get('refused'), dict) and rail['refused'])


def retain_exact_trial(board, state, root, *, limit=2, minimum_free_gib=16):
    """Bounded immutable diagnostics, never a source/route authority promotion.

    The exact filled board is otherwise destroyed by the admission worker's
    temporary-directory cleanup. Keep enough to inspect the actual pinch or
    disconnected pad without having to reconstruct it from an error string.
    """
    import hashlib
    import json
    from pathlib import Path
    import shutil
    import tempfile
    board, state, root = Path(board), Path(state), Path(root)
    refused = {"schema": 1, "retained": False, "release_authority": False}
    if not board.is_file():
        return {**refused, "reason": "exact_board_unavailable"}
    root.mkdir(parents=True, exist_ok=True)
    if len(list(root.glob("trial-*"))) >= max(0, int(limit)):
        return {**refused, "reason": "diagnostic_artifact_budget_exhausted"}
    if shutil.disk_usage(root).free < float(minimum_free_gib) * 1024 ** 3:
        return {**refused, "reason": "diagnostic_storage_floor"}
    target = Path(tempfile.mkdtemp(prefix="trial-", dir=root))
    paths = [board.with_suffix(suffix) for suffix in (".kicad_pcb", ".kicad_pro", ".kicad_dru")]
    if state.is_file():
        paths.append(state)
    records = []
    for source in paths:
        if not source.is_file():
            continue
        output = target / source.name
        shutil.copy2(source, output)
        digest = hashlib.sha256(output.read_bytes()).hexdigest()
        if digest != hashlib.sha256(source.read_bytes()).hexdigest():
            raise RuntimeError("diagnostic copy changed during capture")
        records.append({"source": str(source), "path": str(output), "sha256": digest})
    report = {"schema": 1, "retained": True, "release_authority": False,
              "kind": "rejected-exact-power-diagnostic", "directory": str(target),
              "board": str(target / board.name), "files": records}
    (target / "diagnostic.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def bridge_failure(authority):
    """Accept only explicit structured evidence from a refused authority."""
    if not isinstance(authority, dict) or authority.get("ok") is not False:
        return None
    for source in (authority, authority.get("planner") or {}):
        row = source.get("failure_evidence")
        if (isinstance(row, dict) and row.get("schema") == 1
                and row.get("kind") == "power_bridge_feasibility"
                and row.get("net")
                and (row.get("bridge_feasibility") or {}).get("refusals")):
            return row
    return None


def terminal_evidence(failure, pads, *, tolerance_mm=1e-5):
    """Verify producer terminal identity/position against the current board.

    ``pads`` maps (ref, pin) to live {net, x_mm, y_mm} records or lists of
    records for multi-land terminals sharing a pin number. A stale
    certificate cannot cause a move simply because a reference still exists.
    """
    rows, rejected, seen = [], [], set()
    if not failure:
        return {"pin_access_blocked": [], "rejected": []}
    bottleneck = failure.get('bottleneck') or {}
    terminals = list(bottleneck.get('field_terminals') or ()) + list(bottleneck.get('terminals') or ())
    for terminal in terminals:
        key = (str(terminal.get("ref") or ""), str(terminal.get("pad") or ""))
        if key in seen:
            continue
        seen.add(key)
        candidates = pads.get(key) or []
        if isinstance(candidates, dict):
            candidates = [candidates]
        current = next((item for item in candidates
                        if item.get("net") == failure["net"]
                        and item.get("x_mm") == terminal.get("x_mm")
                        and item.get("y_mm") == terminal.get("y_mm")), None)
        if current is None:
            # Select the nearest same-net land before the tolerance proof.
            # Invalid producer coordinates are handled by the fail-closed
            # proof below, never guessed from another pad of the package.
            try:
                def rank(item):
                    return (item.get("net") != failure["net"],
                            math.dist((float(item["x_mm"]), float(item["y_mm"])),
                                      (float(terminal["x_mm"]), float(terminal["y_mm"]))))
                current = min(candidates, key=rank) if candidates else None
            except (KeyError, TypeError, ValueError):
                current = None
        reason = None
        if not current:
            reason = "terminal_missing"
        elif current.get("net") != failure["net"] or terminal.get("net") != failure["net"]:
            reason = "net_changed"
        else:
            try:
                delta = math.dist((float(terminal["x_mm"]), float(terminal["y_mm"])),
                                  (float(current["x_mm"]), float(current["y_mm"])))
                if not math.isfinite(delta) or delta > tolerance_mm:
                    reason = "terminal_position_changed"
            except (KeyError, TypeError, ValueError):
                reason = "terminal_position_unproven"
        if reason:
            rejected.append({"ref": key[0], "pad": key[1], "reason": reason})
        else:
            rows.append({"ref": key[0], "pad": key[1], "net": failure["net"],
                         "x": current["x_mm"], "y": current["y_mm"],
                         "critical": True, "source": "power_bridge_feasibility"})
    return {"pin_access_blocked": rows, "rejected": rejected}
