"""Portable byte-identical review snapshots with explicit measured origins.

Relocation is not a new DRC measurement. Original native reports/producers
and their receipt are retained verbatim. Relative paths are resolved only
after their origin, PCB, companion and report identities have been checked.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[2]
FORMAT = "cec-portable-review-checkpoint-v1"


def sha(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def require(value, reason):
    if not value:
        raise ValueError(reason)


def _write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def normalize(path, expected, *, repository=ROOT):
    path = Path(path).resolve(strict=True)
    require(sha(path) == expected, "checkpoint_receipt_identity_changed")
    result = json.loads(path.read_text())
    if result.get("format") != FORMAT:
        return result
    require(
        not Path(result["origin_receipt"]).is_absolute(),
        "relative_origin_receipt_required",
    )
    origin_path = (path.parent / result["origin_receipt"]).resolve(strict=True)
    require(origin_path.is_relative_to(path.parent), "origin_receipt_escapes_bundle")
    require(
        sha(origin_path) == result["origin_receipt_sha256"],
        "checkpoint_original_receipt_changed",
    )
    origin = json.loads(origin_path.read_text())
    originals = {row["board"]: row for row in origin["boards"]}
    result = copy.deepcopy(result)
    require(
        len(originals) == len(origin["boards"])
        and len(result["boards"]) == len(originals),
        "unique_portable_checkpoint_board_rows_required",
    )
    require(
        {row["board"] for row in result["boards"]} == set(originals),
        "portable_checkpoint_board_set_changed",
    )
    for row in result["boards"]:
        source = originals[row["board"]]
        require(
            row["sha256"] == source["sha256"],
            "portable_checkpoint_source_geometry_origin_differs",
        )
        for key in ("path", "result", "producer"):
            candidate = Path(row[key])
            require(not candidate.is_absolute(), "relative_portable_asset_required")
            resolved = (path.parent / candidate).resolve(strict=True)
            require(
                resolved.is_relative_to(path.parent),
                "portable_checkpoint_asset_escapes_bundle",
            )
            row[key] = str(resolved)
        row["producer_source_path"] = row.get(
            "measured_source_path", source.get("measured_source_path", source["path"])
        )
        table = row["footprint_table"]
        require(
            table.get("root") in ("repository", "checkpoint")
            and not Path(table["path"]).is_absolute(),
            "explicit_library_table_root_required",
        )
        base = Path(repository) if table["root"] == "repository" else path.parent
        resolved = (base / table["path"]).resolve(strict=True)
        require(
            resolved.is_relative_to(base.resolve()),
            "library_table_escapes_declared_root",
        )
        table["path"] = str(resolved)
        require(
            sha(resolved) == table["sha256"],
            "portable_checkpoint_library_table_changed",
        )
        require(
            sha(row["path"]) == row["sha256"]
            and sha(row["result"]) == row["result_sha256"],
            "portable_checkpoint_board_or_native_report_changed",
        )
        producer = json.loads(Path(row["producer"]).read_text())
        require(
            producer.get("ok") is True
            and producer.get("complete") is True
            and producer["report_sha256"] == row["result_sha256"]
            and producer["source_files"].get(row["producer_source_path"])
            == row["sha256"],
            "portable_original_native_producer_not_bound",
        )
        for name, identity in table.get("referenced_assets", {}).items():
            asset = (resolved.parent / name).resolve(strict=True)
            require(
                asset.is_relative_to(path.parent) and sha(asset) == identity,
                "portable_native_library_asset_changed",
            )
        for name, entry in row["input_family"].items():
            require(
                Path(name).name == name and entry.get("kind") == "file",
                "literal_checkpoint_companion_name_required",
            )
            require(
                sha(Path(row["path"]).parent / name) == entry["sha256"],
                "portable_companion_changed",
            )
        verify_producer(row)
    for entry in result.get("field_receipts", []):
        asset = (path.parent / entry["path"]).resolve(strict=True)
        require(
            asset.is_relative_to(path.parent) and sha(asset) == entry["sha256"],
            "portable_field_evidence_changed",
        )
        entry["path"] = str(asset)
    for review in result.get("selected_children", []):
        require(
            any(
                row["board"] == review["board"]
                and row["sha256"] == review["candidate_sha256"]
                for row in result["boards"]
            ),
            "portable_review_not_bound_to_board",
        )
        for plot in review.get("reviewed_native_plots", {}).values():
            asset = (path.parent / plot["path"]).resolve(strict=True)
            require(
                asset.is_relative_to(path.parent) and sha(asset) == plot["sha256"],
                "portable_review_plot_changed",
            )
            plot["path"] = str(asset)
    return result


def export_reviews(original, output):
    """Retain work orders and exact plots; do not refresh old receiving dates."""
    rows = {row["board"]: row for row in original["boards"]}
    reviews = []
    for entry in original.get("selected_children", []):
        copied = copy.deepcopy(entry)
        source = rows[entry["board"]]
        require(
            copied["candidate_sha256"] == source["sha256"],
            "review_child_identity_changed",
        )
        selected = source.get("agentic_selected_job")
        if selected:
            require(
                sha(selected) == source["agentic_selected_job_sha256"],
                "selected_review_record_changed",
            )
            record = json.loads(Path(selected).read_text())
            require(
                record.get("selected") is True
                and record["candidate_sha256"] == source["sha256"],
                "positive_exact_historical_selection_required",
            )
            job_path = Path(selected).with_name("job.json")
            job = json.loads(job_path.read_text())
            require(
                job["source_sha256"] == copied["parent_sha256"],
                "review_work_order_parent_changed",
            )
            copied["work_order"] = job["request"]
            copied["model_visual_review"] = record["model_visual_review"]
            copied["receiving_code_identity"] = job["code_identity"]
        plots = {}
        for side, plot in copied.get("reviewed_native_plots", {}).items():
            require(
                side in ("before", "after") and sha(plot["path"]) == plot["sha256"],
                "exact_native_review_plot_required",
            )
            name = entry["board"].replace("/", "--") + "-" + side + ".svg"
            target = output / "reviews" / name
            target.parent.mkdir(exist_ok=True)
            shutil.copy2(plot["path"], target)
            plots[side] = dict(path=str(target.relative_to(output)), sha256=sha(target))
        copied["reviewed_native_plots"] = plots
        copied["historical_receiving_not_relabelled_as_current"] = True
        reviews.append(copied)
    return reviews


def verify_producer(row):
    producer_path = Path(
        row.get("producer", Path(row["result"]).with_name("producer.json"))
    )
    producer = json.loads(producer_path.read_text())
    origin = Path(row.get("producer_source_path", row["path"]))
    source = Path(row["path"])
    require(
        producer.get("ok") is True
        and producer.get("complete") is True
        and producer.get("report_sha256") == row["result_sha256"]
        and producer.get("source_files", {}).get(str(origin)) == row["sha256"],
        "native_producer_not_bound_to_exact_source",
    )
    for suffix in (".kicad_pro", ".kicad_dru"):
        current = source.with_suffix(suffix)
        expected = producer.get("source_files", {}).get(str(origin.with_suffix(suffix)))
        require(
            (sha(current) if current.is_file() else None) == expected,
            "checkpoint_native_rule_or_project_context_changed",
        )
    return producer


def export(receipt, expected, output, *, repository=ROOT, field_receipts=()):
    """Copy actual native assets; no refill, source edit or fabricated producer."""
    from .legacy import bootstrap

    bootstrap()
    import cec_suite_inspection as inspection

    original = inspection.verify_receipt(receipt, expected)
    output = Path(output).resolve()
    require(not output.exists(), "fresh_portable_checkpoint_directory_required")
    output.mkdir(parents=True)
    shutil.copy2(receipt, output / "origin-receipt.json")
    rows = []
    for source in original["boards"]:
        row = copy.deepcopy(source)
        directory = output / "boards" / source["board"].replace("/", "--")
        directory.mkdir(parents=True)
        board = Path(source["path"])
        files = sorted(board.parent.glob(board.stem + ".*"))
        require(
            len(files) <= 64
            and sum(p.stat().st_size for p in files if p.is_file()) <= 64 * 1024 * 1024,
            "bounded_checkpoint_source_family_required",
        )
        family = {}
        for item in files:
            if item.is_file() and item.suffix not in (".kicad_prl", ".net"):
                shutil.copy2(item, directory / item.name)
                require(
                    sha(item) == sha(directory / item.name), "checkpoint_copy_changed"
                )
                family[item.name] = dict(
                    kind="file", size=item.stat().st_size, sha256=sha(item)
                )
        producer = Path(
            source.get("producer", Path(source["result"]).with_name("producer.json"))
        )
        shutil.copy2(source["result"], directory / "origin-native.json")
        shutil.copy2(producer, directory / "origin-producer.json")
        row.update(
            path=str((directory / board.name).relative_to(output)),
            result=str((directory / "native.json").relative_to(output)),
            producer=str((directory / "producer.json").relative_to(output)),
            input_family=family,
        )
        row["measured_source_path"] = str(directory / board.name)
        table = Path(row["footprint_table"]["path"]).resolve(strict=True)
        require(
            sha(table) == row["footprint_table"]["sha256"],
            "source_library_table_changed_before_export",
        )
        from .libraries import export as export_libraries

        library = export_libraries(
            directory / board.name,
            table,
            directory / "library",
            pool=output / "libraries",
        )
        row["footprint_table"] = dict(
            path=str(Path(library["path"]).relative_to(output)),
            root="checkpoint",
            sha256=library["sha256"],
            referenced_assets=library["referenced_assets"],
            original_table_sha256=library["original_table_sha256"],
        )
        # Fresh read-only DRC in the relocated library context, with all
        # native findings. No old result is relabelled as newly measured.
        import cec_native_drc_runner as native

        previous = json.loads(producer.read_text())
        build = os.environ.get("CEC_NATIVE_REPORTING_BUILD") or (
            previous.get("reporting_build") or {}
        ).get("root")
        print(
            json.dumps(dict(board=source["board"], phase="portable native receiving")),
            flush=True,
        )
        fresh = native.run(
            directory / board.name,
            directory / "native.json",
            reporting_build=build,
            footprint_table=library["path"],
            timeout_s=9.7,
        )
        _write(directory / "producer.json", fresh)
        require(
            fresh.get("ok") is True and fresh.get("complete") is True,
            "relocated_native_DRC_incomplete",
        )
        report = json.loads((directory / "native.json").read_text())
        counts = dict(
            opens=len(report["unconnected_items"]),
            errors=sum(item["severity"] == "error" for item in report["violations"]),
            warnings=sum(
                item["severity"] == "warning" for item in report["violations"]
            ),
            exclusions=len(report.get("excluded_violations", [])),
        )
        require(
            counts["opens"] == 0
            and counts["errors"] == 0
            and counts["exclusions"] == 0,
            "portable_control_requires_actual_native_closure",
        )
        row["result_sha256"] = sha(directory / "native.json")
        row["counts"] = counts
        # Selection is retained in the immutable origin receipt. Never leave
        # a machine-local job path as the new checkpoint's mutable dependency.
        row.pop("agentic_selected_job", None)
        row.pop("agentic_selected_job_sha256", None)
        rows.append(row)
    fields = []
    inherited = [
        (entry["path"], entry["sha256"]) for entry in original.get("field_receipts", [])
    ]
    for path, identity in dict.fromkeys([*inherited, *map(tuple, field_receipts)]):
        require(sha(path) == identity, "field_evidence_identity_changed")
        target = output / "fields" / (str(len(fields)) + ".json")
        target.parent.mkdir(exist_ok=True)
        shutil.copy2(path, target)
        fields.append(dict(path=str(target.relative_to(output)), sha256=identity))
    reviews = export_reviews(original, output)
    result = dict(
        schema=2,
        format=FORMAT,
        complete=True,
        origin_receipt="origin-receipt.json",
        origin_receipt_sha256=expected,
        boards=rows,
        field_receipts=fields,
        selected_children=reviews,
        scope="byte_identical_native_geometry_with_fresh_relocated_context_DRC",
        totals={
            key: sum(row["counts"][key] for row in rows)
            for key in ("opens", "errors", "warnings", "exclusions")
        },
        release_authority=False,
        manufacturing_or_current_qualified=False,
    )
    target = output / "receipt.json"
    _write(target, result)
    normalize(target, sha(target), repository=repository)
    return dict(
        ok=True,
        path=str(target),
        sha256=sha(target),
        boards=len(rows),
        totals=result["totals"],
        source_controls_unchanged=True,
        release_authority=False,
    )
