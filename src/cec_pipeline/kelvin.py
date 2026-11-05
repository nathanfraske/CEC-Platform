"""Finite parallel transport for the existing exact Kelvin shard receiver.

Every native call gets its own killable sub-ten-second process. This module
does not decide physical outcomes: the existing fresh full-denominator join
receives every leg and the independent legacy observation. Nothing partial
is accepted and no geometry/native object is shared between processes.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from .legacy import ROOT, bootstrap
from .identity import require

bootstrap()

WORKERS = 2
PAIR_SECONDS = 45.0
NATIVE_SECONDS = 9.1
PROCESS_SECONDS = 9.7


def _call(stage, source, board_hint, output, deadline, extra=()):
    remaining = deadline - time.monotonic()
    require(remaining > 0.7, "kelvin_pair_checklist_deadline")
    lease = min(PROCESS_SECONDS, remaining)
    command = [sys.executable, str(ROOT / "scripts/cec_force_sense_shards.py"),
               stage, "--source", str(source), "--board-hint", board_hint,
               "--out", str(output), "--timeout-s", str(min(NATIVE_SECONDS, lease - 0.6)),
               *map(str, extra)]
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=lease)
    except subprocess.TimeoutExpired as exc:
        raise ValueError(f"kelvin_constituent_timeout:{output.name}") from exc
    require(result.returncode == 0,
            f"kelvin_constituent_failed:{output.name}:" + result.stderr[-1500:])
    require(output.is_file() and output.stat().st_size <= 64 * 1024**2,
            f"kelvin_constituent_output_missing_or_oversized:{output.name}")
    report = json.loads(output.read_text())
    if stage == "assemble":
        require(report.get("complete") is True and report.get("identity_stable") is True
                and report.get("stop") is None
                and report.get("sharded_replay", {}).get("full_exact_coverage_join") is True,
                f"kelvin_full_coverage_join_incomplete:{output.name}")
    else:
        # The independent join repeats these source/family/epoch checks.
        import cec_force_sense_shards as shards
        selector = ("manifest",) if stage == "manifest" else ("legacy",) if stage == "legacy" else (
            "leg", str(extra[3]), str(extra[5]))
        shards._require(report, report, selector)
    require(time.monotonic() <= deadline, "kelvin_pair_checklist_deadline")
    return report


def replay_pair(source, candidate, *, board_hint, evidence_dir=None):
    """Two native workers total, one finite pair lease, no whole-board retry.

    Worker files are retained with the gate when a directory is supplied.
    Only the independent assembler can upgrade shards into a complete replay.
    Its returned failed/unknown physical cuts remain failed/unknown.
    """
    if evidence_dir is None:
        with tempfile.TemporaryDirectory(prefix="cec-kelvin-pair-") as temporary:
            return _replay_pair(source, candidate, board_hint, Path(temporary))
    directory = Path(evidence_dir)
    directory.mkdir(parents=True, exist_ok=False)
    return _replay_pair(source, candidate, board_hint, directory)


def _replay_pair(source, candidate, board_hint, directory):
    import cec_force_sense_shards as shards
    import cec_force_sense_evidence as evidence

    started = time.monotonic()
    deadline = started + PAIR_SECONDS
    paths = [Path(source).resolve(strict=True), Path(candidate).resolve(strict=True)]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        def batch(requests):
            pending = [pool.submit(_call, *request) for request in requests]
            try:
                return [future.result() for future in pending]
            finally:
                for future in pending:
                    future.cancel()

        manifests = [directory / f"{side}-manifest.json" for side in ("source", "candidate")]
        prepared = batch([("manifest", path, board_hint, output, deadline)
                          for path, output in zip(paths, manifests)])
        requests, leg_files, legacy_files = [], [], []
        for index, (path, manifest, report) in enumerate(zip(paths, manifests, prepared)):
            shards._require(report, report, ("manifest",))
            legs = report["shard_inventory"]["legs"]
            require(type(legs) is list and len(legs) <= 2 * evidence.MAX_INPUTS,
                    "bounded_full_kelvin_manifest_required")
            files = []
            for ordinal, leg in enumerate(legs):
                output = directory / f"{index}-leg-{ordinal:03d}.json"
                files.append(output)
                requests.append(("leg", path, board_hint, output, deadline,
                                 ("--manifest", manifest, "--input-ref", leg["input_ref"],
                                  "--leg", leg["leg"])))
            leg_files.append(files)
            legacy = directory / f"{index}-legacy.json"
            legacy_files.append(legacy)
            requests.append(("legacy", path, board_hint, legacy, deadline,
                             ("--manifest", manifest)))
        batch(requests)
        joins = []
        for index, path in enumerate(paths):
            extra = ["--manifest", manifests[index], "--legacy-report", legacy_files[index]]
            for leg in leg_files[index]:
                extra.extend(("--leg-report", leg))
            joins.append(("assemble", path, board_hint, directory / f"{index}-joined.json",
                          deadline, extra))
        result = batch(joins)
    require(time.monotonic() <= deadline, "kelvin_pair_checklist_deadline")
    return result
