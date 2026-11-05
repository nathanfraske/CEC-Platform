"""Bounded worker dispatch to independent physical validators."""

from __future__ import annotations
import json, time
from pathlib import Path
from .legacy import ROOT, bootstrap

bootstrap()
import cec_suite_inspection as inspection
from . import geometry as design

from .identity import require, code_identity, family
from .native import _native, native_world
from .construction import _construct


def worker(job_path, step, output):
    job = json.loads(Path(job_path).read_text())
    source = Path(job["source"])
    candidate = Path(job["candidate"])
    require(
        inspection.sha(source) == job["source_sha256"]
        and family(source) == job["source_family"],
        "source_family_changed",
    )
    require(job["code_identity"] == code_identity(), "workbench_code_epoch_changed")
    result = None
    if step == "world":
        world = native_world(source, job["board"])
        result = dict(world=world, audit=design.audit(world))
    elif step == "cell_preview":
        from .cells import preview

        result = preview(source, job["request"]["operation"], job["board"])
    elif step == "construct":
        result = _construct(source, candidate, job["request"], job["board"])
    elif step.startswith("native_"):
        import cec_native_drc_runner as native

        path = source if step == "native_source" else candidate
        report = Path(output).with_name(step + ".native.json")
        result = native.run(
            path,
            report,
            reporting_build=job["reporting_build"],
            footprint_table=job["footprint_table"],
            timeout_s=8.5,
        )
        if result["ok"] and result["complete"]:
            raw = json.loads(report.read_text())
            result["counts"] = dict(
                opens=len(raw["unconnected_items"]),
                errors=sum(v["severity"] == "error" for v in raw["violations"]),
                warnings=sum(v["severity"] == "warning" for v in raw["violations"]),
                exclusions=len(raw.get("excluded_violations", [])),
            )
    elif step in ("transaction_delta", "ordinary_delta"):
        construction = json.loads(
            (Path(job_path).parent / "construct.json").read_text()
        )["result"]
        kind = construction.get("transaction_kind", "ordinary_route")
        if construction["ordinary_only"]:
            import cec_ordinary_route_receiving as ordinary

            result = ordinary.receive(
                source,
                candidate,
                board_hint=job["board"],
                retired_track_uuids=construction["retired_track_uuids"],
                allow_locked_track_uuids=construction["allow_locked_track_uuids"],
                timeout_s=10.0,
            )
        elif kind == "place_cell":
            import cec_complete_cell_receiving as cell_receiving

            op = job["request"]["operations"][0]
            result = cell_receiving.receive(
                source,
                candidate,
                board_hint=job["board"],
                timeout_s=10.0,
                max_shift_mm=op.get("max_shift_nm", 6000000) / 1e6,
                allow_owned_locked_escapes=bool(op["allow_locked_track_uuids"]),
                reference_group_uuids=op.get("reference_group_uuids", ()),
            )
        elif kind == "add_connections":
            from .connections import receive

            result = receive(source, candidate, board_hint=job["board"])
        elif kind in ("power_contour", "power_route", "bank_collector"):
            from . import power

            result = power.receive(
                source,
                candidate,
                job["request"]["operations"][0],
                construction["changes"][0],
                board_hint=job["board"],
            )
        else:
            raise ValueError("unsupported_transaction_not_independently_received")
    elif step == "current_pair":
        import cec_current_debt as current

        result = current.receive(source, candidate, board_hint=job["board"])
    elif step == "assembly_pair":
        from .safety import assembly_pair

        result = assembly_pair(source, candidate)
    elif step == "pair_integrity":
        from .pairs import receive

        result = receive(source, candidate, timeout_s=8.0)
    elif step == "route_contract":
        from .routes import receive

        operations = job["request"]["operations"]
        require(len(operations) == 1 and operations[0]["kind"] == "repair_chain"
                and job["request"].get("target_field_issue_ids"),
                "one_field_targeted_repair_required")
        result = receive(source, candidate, operations[0], board_hint=job["board"])
    elif step == "kelvin_pair":
        from .safety import kelvin_pair

        result = kelvin_pair(source, candidate, board_hint=job["board"],
                             evidence_dir=Path(output).with_name("kelvin-replay"))
    elif step.startswith("fields_"):
        pcbnew, quiet = _native()
        import cec_field_coupling as field

        path = source if step == "fields_source" else candidate
        board = pcbnew.LoadBoard(str(path))
        result = field.field_coupling_summary(
            str(path),
            board=board,
            board_hint=job["board"],
            _work=field._ProposalWork(
                time.monotonic() + 8.0, 16384, 1000000, 1000000, 16384
            ),
        )
        result["complete"] = True
        result["blocker_keys"] = sorted(field.blocker_keys(result))
        from .fields import _native_geometry, inventory

        wanted = {
            uid
            for row in result["interactions"]
            for member in row.get("member_track_uuids", [[uid] for uid in row["track_uuids"]])
            for uid in member
        }
        result["track_geometry"] = _native_geometry(board, wanted)
        result["semantic_inventory"] = inventory(result)
    elif step.startswith("craft_"):
        pcbnew, quiet = _native()
        import cec_route_quality as quality

        path = source if step == "craft_source" else candidate
        board = pcbnew.LoadBoard(str(path))
        result = quality.analyze_board(board)
        from .craft import inventory

        result["semantic_inventory"] = inventory(result, board)
    else:
        raise ValueError("unknown_worker_step")
    require(
        inspection.sha(source) == job["source_sha256"]
        and family(source) == job["source_family"],
        "source_changed_during_tool",
    )
    require(job["code_identity"] == code_identity(), "code_changed_during_tool")
    inspection.write_json(
        output,
        dict(complete=True, result=result, candidate_sha256=inspection.sha(candidate)),
    )
