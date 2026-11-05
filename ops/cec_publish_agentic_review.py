#!/usr/bin/env python3
"""Build a NEW nine-board review receipt from independently selected children.

No source board, existing receipt, fabrication output or published index is
overwritten. The operator separately reviews and changes the dashboard index.
This is review-only lineage, not manufacturing or current qualification.
"""
import argparse
import copy
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cec_agentic_workbench as workbench
import cec_suite_inspection as inspection


def publish(workspace, jobs, output):
    require = workbench.require
    output = Path(output).resolve()
    require(not output.exists(), "fresh_review_receipt_directory_required")
    require(
        type(jobs) is list and 1 <= len(jobs) <= 9 and len(set(jobs)) == len(jobs),
        "finite_unique_selected_jobs_required",
    )
    w = workbench.Workbench(workspace)
    selected = {}
    for token in jobs:
        path, data = w._job(token)
        record = json.loads((path.parent / "selected.json").read_text())
        verdict = w.verdict(token)
        require(
            record.get("selected") is True
            and verdict["ok"] is True
            and record["candidate_sha256"] == verdict["candidate_sha256"],
            "positive_unchanged_selected_child_required",
        )
        require(data["board"] not in selected, "one_selected_child_per_board_required")
        proof = json.loads((path.parent / "render-proof.json").read_text())
        require(
            proof["source_sha256"] == data["source_sha256"]
            and proof["candidate_sha256"] == verdict["candidate_sha256"]
            and proof["code_identity"] == workbench.code_identity()
            and all(
                inspection.sha(path.parent / name) == identity
                for name, identity in proof["plot_hashes"].items()
            ),
            "review_plot_identity_changed",
        )
        selected[data["board"]] = (path, data, verdict, proof, record)
    output.mkdir(parents=True)
    rows = []
    lineage = []
    for original in w.receipt["boards"]:
        row = copy.deepcopy(original)
        if row["board"] in selected:
            path, data, verdict, proof, record = selected[row["board"]]
            directory = output / row["board"].replace("/", "-")
            directory.mkdir()
            producer = json.loads((path.parent / "native_candidate.json").read_text())[
                "result"
            ]
            raw = directory / "native.json"
            shutil.copy2(producer["report"], raw)
            require(
                inspection.sha(raw) == producer["report_sha256"],
                "selected_native_report_changed",
            )
            inspection.write_json(directory / "producer.json", producer)
            row.update(
                path=verdict["candidate"],
                sha256=verdict["candidate_sha256"],
                result=str(raw),
                result_sha256=inspection.sha(raw),
                counts=verdict["native_counts"],
                complete=True,
                producer=str(directory / "producer.json"),
            )
            row.pop("producer_source_path", None)
            row.pop("measured_source_path", None)
            row["input_family"] = {
                name: dict(
                    kind="file",
                    size=(Path(row["path"]).parent / name).stat().st_size,
                    sha256=identity,
                )
                for name, identity in workbench.family(row["path"]).items()
            }
            row["agentic_selected_job"] = str(path.parent / "selected.json")
            row["agentic_selected_job_sha256"] = inspection.sha(
                row["agentic_selected_job"]
            )
            lineage.append(
                dict(
                    board=row["board"],
                    job=data["token"],
                    parent_sha256=data["source_sha256"],
                    candidate_sha256=row["sha256"],
                    native_counts=row["counts"],
                    saved_centerline_mm=verdict["saved_centerline_mm"],
                    intent=data["request"]["intent"],
                    work_order=data["request"],
                    model_visual_review=record["model_visual_review"],
                    reviewed_native_plots={
                        side: dict(path=str(path.parent / name), sha256=identity)
                        for side in ("before", "after")
                        for name, identity in proof["plot_hashes"].items()
                        if name.startswith(side + "-")
                    },
                )
            )
        rows.append(row)
    result = dict(
        schema=1,
        complete=True,
        scope="agent_directed_review_nonregression_only",
        boards=rows,
        parent_receipt=w.manifest["source_receipt"],
        parent_receipt_sha256=w.manifest["source_receipt_sha256"],
        selected_children=lineage,
        field_receipts=copy.deepcopy(w.receipt.get("field_receipts", [])),
        source_controls_unchanged=True,
        release_authority=False,
        manufacturing_or_current_qualified=False,
        totals={
            key: sum(r["counts"][key] for r in rows)
            for key in ("opens", "errors", "warnings", "exclusions")
        },
    )
    inspection.verify_receipt(
        w.manifest["source_receipt"], w.manifest["source_receipt_sha256"]
    )
    receipt = output / "result.json"
    inspection.write_json(receipt, result)
    inspection.verify_receipt(receipt, inspection.sha(receipt))
    return dict(
        ok=True,
        receipt=str(receipt),
        sha256=inspection.sha(receipt),
        totals=result["totals"],
        selected_children=lineage,
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--workspace", required=True)
    p.add_argument("--job", action="append", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    print(json.dumps(publish(a.workspace, a.job, a.output)))
