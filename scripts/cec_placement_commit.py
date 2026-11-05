"""Bounded admission of placement proposals against required constructed copper.

The neutral transaction knows only poses and an authoritative proof callback.
The native adapter reuses production materialization, not an approximate power
corridor or a board-specific corrective move. Returned evidence is not fab approval.
"""
from __future__ import annotations

import dataclasses
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def admit_changes(before, proposed, prove, *, max_probes=32):
    """Keep a fully proved batch, or a bounded, sequentially proved subset.

    Each ref is one atomic pose update. This entry point is for independent
    footprint orientation proposals, not rigid multi-footprint operations.
    Neither dictionary is mutated; exceptions and exhaustion never authorize
    the unproved part of a batch. Accepted subsets are proved cumulatively.
    """
    if (set(before)!=set(proposed) or not isinstance(max_probes,int)
            or isinstance(max_probes,bool) or max_probes<1):
        raise ValueError("placement transaction requires identical identities and a positive budget")
    for poses in (before,proposed):
        if any(len(p)<3 or not all(math.isfinite(float(v)) for v in p[:3]) for p in poses.values()):
            raise ValueError("placement poses must be finite")
    before={r:tuple(p) for r,p in before.items()}
    proposed={r:tuple(p) for r,p in proposed.items()}
    changed=sorted(r for r in before if before[r]!=proposed[r])
    report={"schema":1,"scope":"required_copper_and_physical_placement_not_release",
        "requested":changed,"accepted":[],"rejected":[],"unproved":[],
        "probes":[],"budget":max_probes}
    accepted=dict(before)
    if not changed:
        report.update(ok=True,reason="no_changes")
        return accepted,report
    def probe(poses,label):
        if len(report["probes"])>=max_probes:
            report["unproved"].append(label)
            return False
        try:
            evidence=prove(dict(poses))
        except Exception as exc:
            evidence={"ok":False,"error":type(exc).__name__+": "+str(exc)}
        report["probes"].append({"label":label,"evidence":evidence})
        return isinstance(evidence,dict) and evidence.get("ok") is True
    if not probe(before,"baseline"):
        report.update(ok=False,reason="baseline_unqualified",rejected=changed)
        return accepted,report
    if probe(proposed,"complete_batch"):
        report.update(ok=True,reason="complete_batch",accepted=changed)
        return dict(proposed),report
    for ref in changed:
        trial=dict(accepted); trial[ref]=proposed[ref]
        if probe(trial,ref):
            accepted=trial; report["accepted"].append(ref)
        else:
            report["rejected"].append(ref)
    report.update(ok=not report["rejected"],reason="proved_subset",
                  budget_exhausted=bool(report["unproved"]))
    return accepted,report


def _run_worker(command,timeout_s):
    """Contain KiCad children as well as the worker on a WSL/POSIX timeout."""
    with subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          text=True,start_new_session=os.name=="posix") as proc:
        try:
            stdout,stderr=proc.communicate(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            if os.name=="posix":
                try:
                    os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                proc.kill()
            proc.communicate()
            raise
        return subprocess.CompletedProcess(command,proc.returncode,stdout,stderr)


def _checked_response(data,before,proposed):
    """A corrupt/incomplete worker reply cannot authorize an arbitrary move."""
    positions={r:tuple(p) for r,p in data["positions"].items()}
    report=data["report"]
    if set(positions)!=set(before):
        raise ValueError("worker changed placement identities")
    changed={r for r in before if tuple(before[r])!=tuple(proposed[r])}
    accepted={r for r in before if positions[r]!=tuple(before[r])}
    if any(positions[r] not in (tuple(before[r]),tuple(proposed[r])) for r in before):
        raise ValueError("worker returned an unproposed pose")
    if (report.get("schema")!=1 or set(report.get("requested",()))!=changed
            or set(report.get("accepted",()))!=accepted
            or set(report.get("rejected",()))!=changed-accepted):
        raise ValueError("worker admission accounting mismatch")
    return positions,report


def native_admit(cfg, before, proposed, *, width, height, back_refs=(),
                 blueprint_stamps=(), max_probes=32, timeout_s=180):
    """One warm Python/KiCad worker, bounded work and temporary-only outputs."""
    if max_probes<1 or not math.isfinite(timeout_s) or timeout_s<=0:
        raise ValueError("native placement admission budgets must be positive")
    changed=sorted(r for r in before if tuple(before[r])!=tuple(proposed[r]))
    fallback={"schema":1,"ok":False,"accepted":[],"requested":changed,
              "rejected":changed,"scope":"required_copper_and_physical_placement_not_release"}
    payload={"cfg":dataclasses.asdict(cfg),"before":before,"proposed":proposed,
             "width":width,"height":height,"back_refs":list(back_refs),
             "blueprint_stamps":list(blueprint_stamps),"max_probes":max_probes}
    # The hierarchy, not a possibly stale committed .net, owns a fresh proof.
    payload["cfg"]["net"]=None
    with tempfile.TemporaryDirectory(prefix="cec-placement-commit-") as tmp:
        request=Path(tmp)/"request.json"; response=Path(tmp)/"response.json"
        request.write_text(json.dumps(payload),encoding="utf-8")
        try:
            proc=_run_worker([sys.executable,__file__,str(request),str(response)],timeout_s)
        except subprocess.TimeoutExpired:
            return dict(before),dict(fallback,reason="native_timeout")
        except OSError as exc:
            return dict(before),dict(fallback,reason="native_worker_failure",diagnostic=str(exc))
        if proc.returncode or not response.exists():
            return dict(before),dict(fallback,reason="native_worker_failure",
                diagnostic=(proc.stderr or proc.stdout)[-1600:])
        try:
            return _checked_response(json.loads(response.read_text()),before,proposed)
        except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
            return dict(before),dict(fallback,reason="native_response_invalid",diagnostic=str(exc))


def _worker(payload, output):
    import cec_synth_pipeline as synth
    cfg=synth.Config(**payload["cfg"])
    directory=output.parent
    generated_net=synth._ensure_netlist_path(cfg)
    cfg.net=generated_net
    started=time.monotonic()
    def prove(positions):
        # Reusing the worker keeps imports/library caches warm. Each trial is
        # nevertheless a fresh source materialization: failed constructors may
        # not leave copper behind for the next proposal to inherit.
        cand=synth.Candidate("placement-commit",0,positions,payload["width"],payload["height"],0,{},
            back_refs=tuple(payload["back_refs"]),blueprint_stamps=payload["blueprint_stamps"])
        with tempfile.TemporaryDirectory(prefix="probe-",dir=directory) as trial:
            path=str(Path(trial)/"trial.kicad_pcb")
            with synth._oracle_env(cfg.params):
                synth.materialize(cand,cfg,path)
                if not Path(path).is_file():
                    return {"ok":False,"error":"materialized board missing"}
                terms={"blueprints":synth._blueprint_cell_craft_evidence(path,cfg),
                       "rails":synth._force_rail_craft_evidence(path,cfg),
                       "pads":synth._oracle_pads_in_bounds(path),
                       "courtyards":synth._oracle_courtyard_overlaps(path)}
        return {"ok":all(t.get("ok") is True for t in terms.values()),"terms":terms}
    try:
        positions,report=admit_changes(payload["before"],payload["proposed"],prove,
                                       max_probes=int(payload["max_probes"]))
        report["elapsed_s"]=round(time.monotonic()-started,3)
        # Temp paths disappear by design; retain actual evidence, not dead links.
        for probe in report["probes"]:
            for term in probe["evidence"].get("terms",{}).values(): term.pop("report",None)
        output.write_text(json.dumps({"positions":positions,"report":report},indent=2)+"\n")
    finally:
        # Only the PID-owned export created by this worker is disposable.
        if not payload["cfg"].get("net"):
            Path(generated_net).unlink(missing_ok=True)


if __name__=="__main__":
    _worker(json.loads(Path(sys.argv[1]).read_text()),Path(sys.argv[2]))
    # Do not tear down SWIG object graphs after successful worker output.
    os._exit(0)
