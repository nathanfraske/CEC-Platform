"""Source-bound jobs, independent checks, visual review and selection."""

from __future__ import annotations
import json, os, re, shutil, subprocess, sys, time
from pathlib import Path
from .capabilities import CAPABILITIES, MACROS
from .legacy import ROOT, bootstrap

bootstrap()
import cec_suite_inspection as inspection
from . import geometry as design

from .identity import (
    MODULE,
    GATES,
    INSTRUCTIONS,
    require,
    digest,
    code_identity,
    family,
    evidence_summary,
    check_passed,
)


class Workbench:
    def __init__(
        self, workspace, *, index=None, checkpoint=None, checkpoint_sha256=None
    ):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        require(not (checkpoint is not None and index is not None),
                "one_explicit_workspace_intake_required")
        require(checkpoint is not None or checkpoint_sha256 is None,
                "checkpoint_sha256_requires_explicit_checkpoint")
        explicit = checkpoint is not None or index is not None
        # Reopening a campaign must never follow a newer Git/dashboard pin.
        # Serialize first binding; the receipt path AND bytes are immutable
        # for this workspace. Legacy jobs require an explicit, matching base.
        import fcntl

        intake_path = self.workspace / "source-checkpoint.json"
        with (self.workspace / ".source-checkpoint.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            bound = json.loads(intake_path.read_text()) if intake_path.is_file() else None
            if intake_path.is_file():
                require(type(bound) is dict and set(bound) ==
                        {"schema", "source_receipt", "source_receipt_sha256"}
                        and type(bound["schema"]) is int and bound["schema"] == 1
                        and type(bound["source_receipt"]) is str
                        and Path(bound["source_receipt"]).is_absolute()
                        and type(bound["source_receipt_sha256"]) is str
                        and re.fullmatch(r"[a-f0-9]{64}", bound["source_receipt_sha256"]),
                        "invalid_workspace_source_checkpoint_binding")
            legacy_jobs = list(self.workspace.glob("*/job.json")) if bound is None else []
            require(not legacy_jobs or explicit,
                    "legacy_workspace_requires_explicit_source_checkpoint")
            if bound is not None and not explicit:
                checkpoint = bound["source_receipt"]
                checkpoint_sha256 = bound["source_receipt_sha256"]
            elif checkpoint is None and index is None:
                current = json.loads((ROOT / "checkpoints/current.json").read_text())
                checkpoint = ROOT / current["receipt"]
                checkpoint_sha256 = current["sha256"]
            if checkpoint is not None:
                require(checkpoint_sha256 is not None, "exact_checkpoint_receipt_identity_required")
                source = Path(checkpoint).resolve(strict=True)
                receipt = inspection.verify_receipt(source, checkpoint_sha256)
                self.base = source.parent
                self.manifest = dict(
                    source_receipt=str(source), source_receipt_sha256=checkpoint_sha256,
                    boards=[dict(board=row["board"],
                                 name=inspection.NAMES.get(row["board"], row["board"]),
                                 sha256=row["sha256"], counts=row["counts"])
                            for row in receipt["boards"]],
                )
            else:
                self.base, self.manifest = inspection._published(index)
            self.receipt = inspection.verify_receipt(
                self.manifest["source_receipt"], self.manifest["source_receipt_sha256"]
            )
            binding = dict(schema=1,
                           source_receipt=str(Path(self.manifest["source_receipt"]).resolve(strict=True)),
                           source_receipt_sha256=self.manifest["source_receipt_sha256"])
            require(bound is None or binding == bound,
                    "workspace_source_checkpoint_changed_use_new_workspace")
            for legacy in legacy_jobs:
                require(json.loads(legacy.read_text()).get("source_receipt_sha256") ==
                        binding["source_receipt_sha256"],
                        "legacy_job_source_checkpoint_mismatch")
            self.manifest["source_receipt"] = binding["source_receipt"]
            if bound is None:
                inspection.write_json(intake_path, binding)
                with intake_path.open("rb") as durable:
                    os.fsync(durable.fileno())
                descriptor = os.open(str(self.workspace), os.O_DIRECTORY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        self.rows = {r["board"]: r for r in self.receipt["boards"]}
        from .campaign import Journal

        self.journal = Journal(self.workspace)
        self.journal.verify()

    def _row(self, board):
        require(board in self.rows, "board_not_in_exact_checkpoint")
        parent = self.journal.parent(board)
        if parent is not None:
            require(
                parent["board"] == board
                and inspection.sha(parent["path"]) == parent["sha256"],
                "selected_review_parent_changed",
            )
            return parent
        return self.rows[board]

    def _job(self, token):
        require(
            type(token) is str and re.fullmatch(r"[a-f0-9]{24}", token),
            "exact_job_token_required",
        )
        path = self.workspace / token / "job.json"
        require(path.is_file(), "unknown_job")
        job = json.loads(path.read_text())
        base_sha = getattr(self, "manifest", {}).get("source_receipt_sha256")
        require(base_sha is not None and job.get("source_receipt_sha256") == base_sha,
                "job_source_checkpoint_differs_from_workspace_intake")
        from .authority import inputs, environment_identity

        if "authority_inputs" in job:
            require(
                inputs(job["source"], job["board"]) == job["authority_inputs"],
                "semantic_source_or_selected_assembly_input_changed",
            )
            require(
                environment_identity() == job["environment_identity"],
                "physical_policy_environment_changed",
            )
        require(job["code_identity"] == code_identity(), "stale_job_code_epoch")
        require(
            inspection.sha(job["source"]) == job["source_sha256"]
            and family(job["source"]) == job["source_family"],
            "stale_job_source_family",
        )
        require(
            inspection.sha(job["footprint_table"]) == job["footprint_table_sha256"],
            "stale_job_library_table",
        )
        if job.get("library_identity"):
            from cec_native_library_context import authority

            require(
                digest(authority(job["source"], job["footprint_table"]))
                == digest(job["library_identity"]),
                "referenced_source_library_changed",
            )
        if job.get("native_tool_identity"):
            require(
                all(
                    inspection.sha(name) == identity
                    for name, identity in job["native_tool_identity"]
                    .get("artifacts", {})
                    .items()
                ),
                "native_reporting_tool_changed",
            )
        candidate = Path(job.get("candidate", ""))
        if candidate.is_file():
            require(
                all(
                    (candidate.parent / name).is_file()
                    and inspection.sha(candidate.parent / name) == identity
                    for name, identity in job["source_family"].items()
                    if name != Path(job["source"]).name
                ),
                "candidate_rules_or_companions_changed",
            )
        return path, job

    def _make_job(self, board, request):
        require(board in self.rows, "board_not_in_exact_checkpoint")
        row = self._row(board)
        source = Path(row["path"])
        require(inspection.sha(source) == row["sha256"], "checkpoint_board_changed")
        from .checkpoint import verify_producer

        producer = verify_producer(row)
        from cec_native_drc_runner import _describe_build

        build = os.environ.get("CEC_NATIVE_REPORTING_BUILD") or (
            producer.get("reporting_build") or {}
        ).get("root")
        if build and not Path(build).is_dir():
            build = None
        tool_identity = _describe_build(build) if build else None
        from cec_native_library_context import authority

        libraries = authority(source, row["footprint_table"]["path"])
        from .authority import inputs, environment_identity

        binding = dict(
            board=board,
            source=str(source),
            source_sha256=row["sha256"],
            source_family=family(source),
            source_receipt_sha256=self.manifest["source_receipt_sha256"],
            request=request,
            code_identity=code_identity(),
            reporting_build=build,
            native_tool_identity=tool_identity,
            library_identity=libraries,
            authority_inputs=inputs(source, board),
            environment_identity=environment_identity(),
            footprint_table=row["footprint_table"]["path"],
            footprint_table_sha256=row["footprint_table"]["sha256"],
        )
        require(
            inspection.sha(binding["footprint_table"])
            == row["footprint_table"]["sha256"],
            "checkpoint_footprint_table_changed",
        )
        token = digest(binding)[:24]
        directory = self.workspace / token
        if not directory.exists():
            directory.mkdir()
            child = directory / "UNADMITTED"
            child.mkdir()
            for p in source.parent.glob(source.stem + ".*"):
                if p.is_file():
                    shutil.copy2(p, child / p.name)
            binding["candidate"] = str(child / source.name)
            binding["token"] = token
            inspection.write_json(directory / "job.json", binding)
        return token

    def _run(self, token, step, *, _slots_locked=False):
        from .execution import run

        return run(self, token, step, slots_locked=_slots_locked)

    def status(self, job):
        path, data = self._job(job)
        result = path.parent / "validate.json"
        if result.is_file():
            record = json.loads(result.read_text())
            require(
                record.get("candidate_sha256") == inspection.sha(data["candidate"]),
                "completed_validation_candidate_changed",
            )
            return record
        states = {}
        for step in (
            "construct",
            *GATES,
            "current_pair",
            "kelvin_pair",
            "assembly_pair",
        ):
            target = path.parent / (step + ".json")
            running = path.parent / (step + ".running.json")
            if target.is_file():
                states[step] = evidence_summary(json.loads(target.read_text()))
            elif running.is_file():
                states[step] = dict(complete=False, status="running")
        return dict(
            ok=True,
            complete=False,
            job=job,
            checks=states,
            selected=False,
            release_authority=False,
        )

    def validate(self, job):
        """Start one finite receiving checklist, not an optimization loop."""
        import fcntl

        path, data = self._job(job)
        with (self.workspace / ".validator-slots.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            target = path.parent / "validate.json"
            if target.is_file():
                return self.status(job)
            running = path.parent / "validate.running.json"
            if running.is_file():
                require(
                    time.time() - json.loads(running.read_text())["started"] < 250,
                    "finite_validation_coordinator_expired_replan_required",
                )
                return dict(ok=True, complete=False, status="running", job=job)
            active = [
                p
                for p in self.workspace.glob("*/validate.running.json")
                if not p.with_name("validate.json").exists()
                and time.time() - json.loads(p.read_text())["started"] < 250
            ]
            if len(active) >= 2:
                return dict(
                    ok=True,
                    complete=False,
                    status="waiting_for_validator_slot",
                    job=job,
                )
            self.journal.transition(job, "checking")
            with (path.parent / "validate.worker.log").open("wb") as log:
                process = subprocess.Popen(
                    [sys.executable, str(MODULE), "--validate-worker", str(path)],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
            inspection.write_json(running, dict(pid=process.pid, started=time.time()))
            return dict(
                ok=True,
                complete=False,
                status="running",
                job=job,
                completion_event="validate.json and durable campaign event; no periodic redesign",
            )

    def campaign(self, limit=24):
        self.journal.verify()
        return self.journal.state(limit)

    def plan_cell(
        self,
        board,
        poses,
        allow_locked_footprint_uuids=None,
        allow_locked_track_uuids=None,
        max_shift_nm=6000000,
        offset=0,
        limit=8,
    ):
        require(
            type(offset) is int
            and offset >= 0
            and type(limit) is int
            and 1 <= limit <= 32,
            "bounded_source_connection_page_required",
        )
        operation = dict(
            kind="place_cell",
            poses=poses,
            routes=[],
            vias=[],
            max_shift_nm=max_shift_nm,
            allow_locked_footprint_uuids=allow_locked_footprint_uuids or [],
            allow_locked_track_uuids=allow_locked_track_uuids or [],
        )
        token = self._make_job(board, dict(kind="cell_preview", operation=operation))
        record = self._run(token, "cell_preview")
        detail = record.get("result", {})
        connections = detail.get("source_owned_connections", {})
        keys = sorted(connections)
        return dict(
            ok=record.get("complete") is True,
            job=token,
            observation=evidence_summary(record),
            moved_refs=detail.get("moved_refs", []),
            retired_track_uuids=detail.get("retired_track_uuids", []),
            source_owned_connections={
                key: connections[key] for key in keys[offset : offset + limit]
            },
            obligation_count=len(keys),
            offset=offset,
            next_offset=offset + limit if offset + limit < len(keys) else None,
            full_source_owned_connections=str(
                self.workspace / token / "cell_preview.json"
            ),
            source_modified=False,
            route_search_run=False,
            release_authority=False,
        )

    def grid(self, center_nm, rows, columns, pitch_nm):
        from .power import symmetric_grid

        return dict(
            ok=True,
            points_nm=symmetric_grid(
                center_nm=center_nm, rows=rows, columns=columns, pitch_nm=pitch_nm
            ),
            construction_only=True,
            foreign_copper_process_and_current_receiving_still_required=True,
        )

    def row(self, board, references, axis, origin_nm, pitch_nm, rotation_deg=None):
        token = self._make_job(board, dict(kind="inspect"))
        record = self._run(token, "world")
        require(
            record.get("complete") is True, "complete_source_world_required_for_row"
        )
        rows = design.alignment(
            record["result"]["world"]["footprints"],
            references=references,
            axis=axis,
            origin_nm=origin_nm,
            pitch_nm=pitch_nm,
            rotation_deg=rotation_deg,
        )
        return dict(
            ok=True,
            source_sha256=self._row(board)["sha256"],
            poses=[
                dict(
                    reference=row["ref"],
                    at_nm=row["at_nm"],
                    rotation_deg=round(row["rotation_deg"]),
                )
                for row in rows
            ],
            connected_source_plan_and_explicit_routes_still_required=True,
            source_modified=False,
        )

    def fork(self, job, expected_candidate_sha256):
        """Adopt an exact selected review child as this board's next work parent."""
        path, data = self._job(job)
        selected = json.loads((path.parent / "selected.json").read_text())
        verdict = self.verdict(job)
        require(
            selected.get("selected") is True
            and verdict.get("ok") is True
            and expected_candidate_sha256
            == selected["candidate_sha256"]
            == verdict["candidate_sha256"],
            "unchanged_selected_child_required_for_fork",
        )
        row = dict(self._row(data["board"]))
        producer = json.loads((path.parent / "native_candidate.json").read_text())[
            "result"
        ]
        producer_path = path.parent / "parent-producer.json"
        inspection.write_json(producer_path, producer)
        row.update(
            path=data["candidate"],
            sha256=expected_candidate_sha256,
            result=producer["report"],
            result_sha256=producer["report_sha256"],
            counts=verdict["native_counts"],
            producer=str(producer_path),
        )
        row.pop("producer_source_path", None)
        row.pop("measured_source_path", None)
        self.journal.set_parent(data["board"], job, expected_candidate_sha256, row)
        return dict(
            ok=True,
            board=data["board"],
            sha256=expected_candidate_sha256,
            original_catalog_unchanged=True,
            release_authority=False,
        )

    def boards(self):
        return dict(
            ok=True,
            source_receipt_sha256=self.manifest["source_receipt_sha256"],
            boards=[
                dict(
                    board=b["board"],
                    name=b["name"],
                    sha256=self._row(b["board"])["sha256"],
                    original_checkpoint_sha256=b["sha256"],
                    checkpoint_native_counts=self._row(b["board"])["counts"],
                )
                for b in self.manifest["boards"]
            ],
            native_counts_are_checkpoint_not_new_measurements=True,
            instructions=INSTRUCTIONS,
        )

    def inspect(self, board, region_nm=None, limit=8, references=None, nets=None):
        require(
            type(limit) is int and 1 <= limit <= 32, "bounded_inspection_limit_required"
        )
        token = self._make_job(board, dict(kind="inspect"))
        record = self._run(token, "world")
        if not record["complete"]:
            return dict(ok=False, job=token, **record)
        world = record["result"]["world"]
        audit = record["result"]["audit"]
        totals = dict(
            footprints=len(world["footprints"]),
            tracks=len(world["tracks"]),
            zones=len(world["zones"]),
        )
        for names in (references, nets):
            require(
                names is None
                or type(names) is list
                and 1 <= len(names) <= 32
                and all(type(n) is str and n for n in names),
                "bounded_explicit_reference_or_net_filter_required",
            )
        if references is not None:
            require(
                set(references) <= {f["ref"] for f in world["footprints"]},
                "unknown_inspection_reference",
            )
            selected = {f["ref"] for f in world["footprints"] if f["ref"] in references}
            own = {
                p["net"]
                for f in world["footprints"]
                if f["ref"] in selected
                for p in f["pads"]
                if p["net"]
            }
            world = dict(
                world,
                footprints=[f for f in world["footprints"] if f["ref"] in selected],
                tracks=[t for t in world["tracks"] if t["net"] in own],
            )
        if nets is not None:
            world = dict(
                world,
                footprints=[
                    f
                    for f in world["footprints"]
                    if any(p["net"] in nets for p in f["pads"])
                ],
                tracks=[t for t in world["tracks"] if t["net"] in nets],
                zones=[z for z in world["zones"] if z["net"] in nets],
            )
        if region_nm is not None:
            require(
                type(region_nm) is list and len(region_nm) == 4,
                "native_region_bounds_required",
            )
            lo, hi = design.point(region_nm[:2]), design.point(region_nm[2:])
            require(all(a < b for a, b in zip(lo, hi)), "positive_region_required")
            inside = lambda p: all(a <= x <= b for a, x, b in zip(lo, p, hi))
            crosses = lambda t: all(
                max(t["a"][k], t["b"][k]) >= lo[k]
                and min(t["a"][k], t["b"][k]) <= hi[k]
                for k in (0, 1)
            )
            world = dict(
                world,
                tracks=[t for t in world["tracks"] if crosses(t)],
                footprints=[f for f in world["footprints"] if inside(f["at"])],
            )
        small_audit = {
            **audit,
            "route_opportunities": audit["route_opportunities"][:limit],
            "noncanonical_track_count": len(audit["noncanonical_tracks"]),
            "noncanonical_tracks": audit["noncanonical_tracks"][:limit],
            "repeated_component_group_count": len(audit["repeated_component_groups"]),
            "repeated_component_groups": audit["repeated_component_groups"][:limit],
            "zone_intent_finding_count": len(audit["zone_intent_findings"]),
            "zone_intent_findings": audit["zone_intent_findings"][:limit],
        }
        return dict(
            ok=True,
            job=token,
            source_sha256=world["sha256"],
            units=world["units"],
            ordinary_role_status=world["ordinary_role_status"],
            saved_global_limits_nm=world["saved_global_limits_nm"],
            layer_stack=world["layer_stack"],
            source_properties=world["properties"],
            source_netclass_geometry_mm={
                name: value
                for name, value in world["source_netclass_geometry_mm"].items()
                if name
                in (
                    set(nets)
                    if nets is not None
                    else (
                        {p["net"] for f in world["footprints"] for p in f["pads"]}
                        if references is not None
                        else set(list(world["source_netclass_geometry_mm"])[:limit])
                    )
                )
            },
            local_rules_can_override_global_limits=True,
            audit=small_audit,
            native_totals=totals,
            footprints=world["footprints"][:limit],
            footprints_truncated=len(world["footprints"]) > limit,
            zones=world["zones"][:limit],
            zones_truncated=len(world["zones"]) > limit,
            tracks=(
                world["tracks"][: min(128, limit * 8)]
                if any(v is not None for v in (region_nm, references, nets))
                else []
            ),
            explicit_filter_tracks_truncated=len(world["tracks"]) > min(128, limit * 8),
            full_native_world=str(self.workspace / token / "world.json"),
            release_authority=False,
        )

    def issues(self, board, offset=0, limit=16):
        """Read source-bound faults, not inferred success from a picture."""
        from .issues import compile_map

        require(
            type(offset) is int
            and offset >= 0
            and type(limit) is int
            and 1 <= limit <= 32,
            "bounded_issue_page_required",
        )
        token = self._make_job(board, dict(kind="inspect"))
        records = {
            step: self._run(token, step)
            for step in ("world", "native_source", "craft_source", "fields_source")
        }
        if not all(row.get("complete") is True for row in records.values()):
            return dict(
                ok=False,
                complete=False,
                job=token,
                evidence={step: evidence_summary(row) for step, row in records.items()},
                release_authority=False,
            )
        native = records["native_source"]["result"]
        require(
            native.get("ok") is True and native.get("complete") is True,
            "complete_native_issue_observer_required",
        )
        require(
            inspection.sha(native["report"]) == native["report_sha256"],
            "native_issue_report_changed",
        )
        result = compile_map(
            records["world"]["result"]["world"],
            json.loads(Path(native["report"]).read_text()),
            records["craft_source"]["result"],
            records["fields_source"]["result"],
        )
        target = self.workspace / token / "issues.json"
        inspection.write_json(target, result)
        return dict(
            ok=True,
            complete=True,
            job=token,
            source_sha256=result["source_sha256"],
            total=len(result["issues"]),
            offset=offset,
            issues=result["issues"][offset : offset + limit],
            key=result["key"],
            full_issue_map=str(target),
            full_issue_map_sha256=inspection.sha(target),
            release_authority=False,
        )

    def stage(self, board, expected_source_sha256, intent, operations):
        require(
            board in self.rows and expected_source_sha256 == self._row(board)["sha256"],
            "exact_expected_checkpoint_sha_required",
        )
        require(
            type(intent) is str and 16 <= len(intent) <= 2000,
            "explicit_design_rationale_required",
        )
        require(
            type(operations) is list
            and 1 <= len(operations) <= 8
            and all(type(op) is dict for op in operations),
            "bounded_atomic_operation_batch_required",
        )
        require(
            all(op.get("kind") in CAPABILITIES for op in operations),
            "only_independently_received_construction_kinds_are_exposed",
        )
        token = self._make_job(board, dict(intent=intent, operations=operations))
        path, job = self._job(token)
        decision = self.journal.begin(
            token,
            board,
            expected_source_sha256,
            job["code_identity"],
            dict(
                intent=intent,
                operations=operations,
                source_family=job["source_family"],
                footprint_table_sha256=job["footprint_table_sha256"],
            ),
        )
        require(decision["job"] == token, "campaign_decision_binding_changed")
        record = self._run(token, "construct")
        if record.get("complete") is False and record.get("status") not in (
            "running",
            "waiting_for_receiver_slot",
        ):
            self.journal.transition(
                token, "failed", str(record.get("error", "construction refused"))[:2000]
            )
        return dict(
            ok=record.get("complete") is True
            or record.get("status") in ("running", "waiting_for_receiver_slot"),
            complete=record.get("complete") is True,
            job=token,
            construction=evidence_summary(record),
            full_construction_path=str(path.parent / "construct.json"),
            next_action="validate",
            selected=False,
            release_authority=False,
        )

    def check(self, job, gate):
        if gate == "ordinary_delta":
            gate = "transaction_delta"
        require(
            gate in (*GATES, "current_pair", "kelvin_pair", "assembly_pair"),
            "known_independent_check_required",
        )
        path, data = self._job(job)
        require((path.parent / "construct.json").is_file(), "construction_required")
        construction = json.loads((path.parent / "construct.json").read_text())
        require(construction.get("complete") is True, "positive_construction_required")
        if (
            not construction["result"]["ordinary_only"]
            and construction["result"].get("transaction_kind") not in MACROS
        ):
            return dict(
                ok=False,
                complete=True,
                job=job,
                gate=gate,
                reason="Power/placement construction is private and unfinished. Specialized source-current, fill, decoupling and mating receivers are mandatory.",
                selected=False,
                release_authority=False,
            )
        record = self._run(job, gate)
        return dict(
            ok=check_passed(record),
            analysis_complete=record.get("complete") is True,
            job=job,
            gate=gate,
            evidence=evidence_summary(record),
            full_evidence_path=str(path.parent / (gate + ".json")),
            full_evidence_sha256=(
                inspection.sha(path.parent / (gate + ".json"))
                if (path.parent / (gate + ".json")).is_file()
                else None
            ),
            selected=False,
            release_authority=False,
        )

    def verdict(self, job):
        path, data = self._job(job)
        failed = []
        missing = []
        records = {}
        from .execution import required_gates

        built = path.parent / "construct.json"
        if not built.is_file():
            return dict(
                ok=False,
                job=job,
                missing=["construct"],
                failed=[],
                selected=False,
                release_authority=False,
            )
        construction = json.loads(built.read_text())
        if construction.get("complete") is not True:
            return dict(
                ok=False,
                job=job,
                missing=[],
                failed=["construct: incomplete"],
                selected=False,
                release_authority=False,
            )
        gates = required_gates(construction["result"])
        for step in ("construct", *gates):
            p = path.parent / (step + ".json")
            if not p.exists():
                missing.append(step)
                continue
            r = json.loads(p.read_text())
            records[step] = r.get("result", {})
            if r.get("complete") is not True:
                failed.append(step + ": incomplete")
            if r.get("candidate_sha256") != inspection.sha(data["candidate"]):
                failed.append(step + ": candidate identity changed")
        if missing or failed:
            return dict(
                ok=False,
                job=job,
                missing=missing,
                failed=failed,
                selected=False,
                release_authority=False,
            )
        c = records["construct"]
        if (
            c.get("ordinary_only") is not True
            and c.get("transaction_kind") not in MACROS
        ):
            return dict(
                ok=False,
                job=job,
                selected=False,
                release_authority=False,
                missing=[
                    "specialized_power_pose_source_receiving",
                    "decoupling_and_mating_receiving",
                    "filled_material_current_and_reference_receiving",
                ],
                failed=failed,
                reason="These construction tools are not yet connected to complete specialized receiving. Native DRC cannot substitute.",
            )
        for step in ("native_source", "native_candidate", "transaction_delta"):
            r = records[step]
            if r.get("ok") is not True or r.get("complete") is not True:
                failed.append(step + ": failed or unknown")
        for step in set(gates) - set(GATES):
            if (
                records[step].get("ok") is not True
                or records[step].get("complete") is not True
            ):
                failed.append(step + ": failed or unknown")
        for step in ("native_source", "native_candidate"):
            counts = records[step].get("counts", {})
            if (
                counts.get("opens") != 0
                or counts.get("errors") != 0
                or counts.get("exclusions") != 0
            ):
                failed.append(step + ": native closure absent")
        if not failed:
            import cec_stage_admission as admission

            a, b = [
                json.loads(Path(records[s]["report"]).read_text())
                for s in ("native_source", "native_candidate")
            ]
            delta = admission.native_geometry_nonregression(a, b)
            if delta["ok"] is not True or a.get("ignored_checks") != b.get(
                "ignored_checks"
            ):
                failed.append("native configuration or physical-fault regression")
            before, after = [records[s] for s in ("craft_source", "craft_candidate")]
            if any(
                r.get("complete") is not True
                or r.get("power_contours", {}).get("complete") is not True
                for r in (before, after)
            ):
                failed.append("craft/contour observer incomplete")
            elif (
                after["issue_count"] > before["issue_count"]
                or after["non_octilinear_count"] > before["non_octilinear_count"]
                or after["power_contours"]["finding_count"]
                > before["power_contours"]["finding_count"]
            ):
                failed.append("craft regression")
            first, last = [records[s] for s in ("fields_source", "fields_candidate")]

            # Compare exact physical interaction records, not only their count.
            def keys(r):
                return set(r["blocker_keys"])

            if any(r.get("complete") is not True for r in (first, last)):
                failed.append("field observer incomplete")
            elif keys(last) - keys(first):
                failed.append("new field-coupling interaction")
        result = dict(
            ok=not failed,
            job=job,
            failed=failed,
            missing=missing,
            selected=False,
            candidate=data["candidate"],
            candidate_sha256=inspection.sha(data["candidate"]),
            source_sha256=data["source_sha256"],
            native_counts=records["native_candidate"].get("counts"),
            saved_centerline_mm=sum(
                c.get("saved_centerline_mm", 0) for c in c.get("changes", [])
            ),
            review_nonregression_only=True,
            manufacturing_or_current_qualified=False,
            release_authority=False,
        )
        inspection.write_json(path.parent / "verdict.json", result)
        return result

    def select(self, job, expected_candidate_sha256, visual_review):
        """Select a reviewed private child, NEVER overwrite the source catalog."""
        path, data = self._job(job)
        verdict = self.verdict(job)
        require(
            verdict["ok"] is True, "all_independent_checks_must_pass_before_selection"
        )
        require(
            expected_candidate_sha256 == verdict["candidate_sha256"],
            "exact_reviewed_candidate_identity_required",
        )
        require(
            type(visual_review) is str and 24 <= len(visual_review) <= 2000,
            "explicit_model_visual_review_required",
        )
        proof_path = path.parent / "render-proof.json"
        require(
            proof_path.is_file(), "native_before_after_plots_required_before_selection"
        )
        proof = json.loads(proof_path.read_text())
        from . import visual

        manifest = visual.changed_copper(data["source"], data["candidate"])
        require(
            proof.get("schema") == 2
            and proof["candidate_sha256"] == verdict["candidate_sha256"]
            and proof["source_sha256"] == data["source_sha256"]
            and proof["code_identity"] == code_identity()
            and proof["changed_copper_sha256"] == manifest["sha256"]
            and all(
                inspection.sha(path.parent / name) == identity
                for name, identity in proof["plot_hashes"].items()
            ),
            "native_visual_evidence_changed",
        )
        covered = visual.verify_views(proof, manifest, path.parent)
        require(inspection.sha(data["candidate"]) == verdict["candidate_sha256"],
                "candidate_changed_during_visual_receiving")
        self._job(job)
        record = dict(
            **verdict,
            selected_at=time.time(),
            model_visual_review=visual_review,
            plot_hashes=proof["plot_hashes"],
            visual_coverage=covered,
            changed_copper_sha256=manifest["sha256"],
            source_catalog_overwritten=False,
        )
        self.journal.transition(job, "selected")
        record["selected"] = True
        inspection.write_json(path.parent / "selected.json", record)
        return record

    def render(self, job, layer, region_nm=None, guide=None):
        path, data = self._job(job)
        candidate_sha = inspection.sha(data["candidate"])
        epoch = code_identity()
        require(
            layer in ("F.Cu", "In1.Cu", "In2.Cu", "In3.Cu", "In4.Cu", "B.Cu"),
            "actual_copper_layer_required",
        )
        require(
            guide in (None, "F.Fab", "B.Fab", "F.Silkscreen", "B.Silkscreen"),
            "native_guide_layer_required",
        )
        from . import visual

        manifest = visual.changed_copper(data["source"], data["candidate"])
        if region_nm is None:
            region_nm = visual.default_region(manifest)
        require(type(region_nm) is list and len(region_nm) == 4, "bounded_region_required")
        a, b = design.point(region_nm[:2]), design.point(region_nm[2:])
        require(all(x < y for x, y in zip(a, b)), "positive_region_required")
        bounds = [a[0] / 1e6, a[1] / 1e6, (b[0] - a[0]) / 1e6, (b[1] - a[1]) / 1e6]
        view_key = digest(dict(layer=layer, region_nm=region_nm, guide=guide))[:16]
        result = {}
        previews = {}
        for label, p in (("before", data["source"]), ("after", data["candidate"])):
            target = path.parent / (label + "-" + layer.replace(".", "-") + "-" + view_key + ".svg")
            layers = [layer, *([guide] if guide else []), "Edge.Cuts"]
            inspection.bounded(inspection.plot_command(p, target, layers), timeout=9.7)
            inspection.reframe_svg(target, bounds)
            result[label] = dict(path=str(target), sha256=inspection.sha(target))
            if shutil.which("rsvg-convert"):
                png = target.with_suffix(".png")
                inspection.bounded(
                    [
                        "rsvg-convert",
                        "--width",
                        "1024",
                        "--height",
                        "768",
                        "--keep-aspect-ratio",
                        "--background-color",
                        "white",
                        "--output",
                        str(png),
                        str(target),
                    ],
                    timeout=9.7,
                )
                require(
                    png.stat().st_size <= 2 * 1024 * 1024,
                    "bounded_native_raster_preview_required",
                )
                previews[label] = dict(path=str(png), sha256=inspection.sha(png))
        proof_path = path.parent / "render-proof.json"
        prior = json.loads(proof_path.read_text()) if proof_path.is_file() else {}
        require(inspection.sha(data["candidate"]) == candidate_sha
                and inspection.sha(data["source"]) == data["source_sha256"]
                and code_identity() == epoch,
                "native_source_candidate_or_code_changed_during_render")
        self._job(job)
        same = (prior.get("schema") == 2
                and prior.get("source_sha256") == data["source_sha256"]
                and prior.get("candidate_sha256") == candidate_sha
                and prior.get("code_identity") == epoch
                and prior.get("changed_copper_sha256") == manifest["sha256"])
        views = [v for v in prior.get("views", []) if v["key"] != view_key] if same else []
        views.append(dict(key=view_key, layer=layer, region_nm=region_nm, guide=guide,
                          plot_hashes={Path(v["path"]).name: v["sha256"]
                                       for v in result.values()}))
        require(len(views) <= 64, "bounded_native_visual_views_required")
        proof = dict(
                schema=2,
                source_sha256=data["source_sha256"],
                candidate_sha256=candidate_sha,
                code_identity=epoch,
                changed_copper_sha256=manifest["sha256"],
                views=views,
                plot_hashes={name: identity for v in views
                             for name, identity in v["plot_hashes"].items()},
            )
        inspection.write_json(proof_path, proof)
        return dict(
            ok=True,
            job=job,
            actual_saved_copper=True,
            refilled=False,
            plots=result,
            previews=previews,
            visual_coverage=visual.coverage(manifest, views),
            release_authority=False,
        )
