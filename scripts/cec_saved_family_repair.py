"""Durable one-shot private repair dispatch, not canonical adoption or release.

The caller supplies a stable ledger root shared by its staged copies/waves.
Same-stem paths are normalized for request identity; bytes, absence, external
authority, effective policy/environment, code and effort are not. Seed and
wall-clock deadline are scheduling metadata, never another deterministic try.

A request directory is its exclusive acquisition record. Interrupted owners
are quarantined, not retried. Explicit ``recover=True`` can recover only an
already completed supervised validation, never replay an uncertain operator.
``select_private`` checks the saved evidence again at the receiving boundary.
It returns a private proposal path; ordinary canonical preservation, aggregate
admission, checkpoints and independent release gates remain the caller's job.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import socket
import shutil
import stat
import sys
import time
import uuid

SCHEMA = 1
MAX_JSON_BYTES = 32 * 1024**2
OPERATIONS = {"force_current": "force_current_additive", "kelvin_branch": "kelvin_branch_repair"}
CONTROL_ENV = frozenset(("CEC_OPERATION_PROGRESS", "CEC_OPERATION_STACKS",
    "CEC_OPERATION_OWNER_PID", "CEC_OPERATION_DEADLINE_EPOCH", "CEC_JOB_DEADLINE_EPOCH",
    "CEC_OPERATION_ID", "CEC_OPERATION_DIR", "CEC_JOB_ID", "CEC_JOB_PID", "CEC_RUN_ID",
    "CEC_RUN_DIR", "CEC_WORK_DIR", "CEC_OUTPUT_DIR", "CEC_LOG_DIR", "CEC_SEED",
    "CEC_ROUTE_SEED", "CEC_FR_SEED"))
PREFIXES = (".pourfirst-state.json", ".authored-prefix.json", ".power-prefix.json",
            ".priority-replacements.json")


class Refusal(ValueError):
    pass


def _json(value):
    """Reject ambiguous/nonfinite policy rather than stringify Python objects."""
    def check(item):
        if isinstance(item, dict):
            if any(type(key) is not str for key in item):
                raise ValueError("policy keys must be strings")
            for child in item.values():
                check(child)
        elif isinstance(item, list):
            for child in item:
                check(child)
        elif item is not None and type(item) not in (str, bool, int, float):
            raise ValueError("policy must be explicit JSON data")
    check(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _native_evidence_json_data(value):
    """Native topology tuples are arrays, not a relaxation of request policy.

    Copy containers without stringifying unknown objects, coercing keys or
    admitting nonfinite numbers. Supplied policy still uses _json directly.
    """
    def arrays(item):
        if type(item) in (tuple, list):
            return [arrays(child) for child in item]
        if isinstance(item, dict):
            return {key: arrays(child) for key, child in item.items()}
        return item
    normalized = arrays(value)
    _json(normalized)
    return normalized


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _unalias(path, *, regular=False):
    path = Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise Refusal("symlink_input_or_evidence_path")
    if path.exists():
        info = path.stat()
        if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
            raise Refusal("hardlink_input_or_evidence_path")
        if regular and not stat.S_ISREG(info.st_mode):
            raise Refusal("regular_file_required")
    elif regular:
        raise Refusal("required_file_missing")
    return path


def _hash(path):
    path = _unalias(path)
    if not path.exists():
        return None
    _unalias(path, regular=True)
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _read(path):
    path = _unalias(path, regular=True)
    if path.stat().st_size > MAX_JSON_BYTES:
        raise Refusal("evidence_size_limit")
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise Refusal("duplicate_evidence_key")
            result[key] = value
        return result
    result = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=pairs)
    _json(result)
    return result


def _write_new(path, value):
    """Publish an immutable record using exclusive creation and durable bytes."""
    path = _unalias(path)
    encoded = _json(value) + "\n"  # Encoding failures must not leave empty records.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    with os.fdopen(os.open(path, flags, 0o600), "w", encoding="utf-8") as sink:
        sink.write(encoded)
        sink.flush()
        os.fsync(sink.fileno())
    _sync_directory(path.parent)


def _sync_directory(path):
    if os.name == "posix":
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _family(source, hint):
    import cec_force_current as force
    import cec_kelvin_branch_repair as branch
    # Includes unknown same-stem sidecars and their established absence set.
    paths = branch._family(source, hint)
    controls = {str(Path(value).absolute()) for key, value in os.environ.items()
                if key in CONTROL_ENV and os.path.isabs(value)}
    return {path: _hash(path) for path in paths if not Path(path).is_dir()
            and (path not in controls or _local(path, source).startswith("@board"))}


def _toolchain():
    files = {str(Path(sys.executable).resolve())}
    for name in ("pcbnew", "_pcbnew"):
        spec = importlib.util.find_spec(name)
        if spec and spec.origin:
            files.add(str(Path(spec.origin).resolve()))
    cli = shutil.which("kicad-cli")
    if cli:
        files.add(str(Path(cli).resolve()))
    return dict(python=sys.version, executable=str(Path(sys.executable).resolve()),
                files={path: _hash(path) for path in sorted(files)})


def _local(path, source):
    path, source = str(Path(path).absolute()), str(Path(source).absolute())
    if path == source:
        return "@board"
    stem = str(Path(source).with_suffix(""))
    if path.startswith(stem + ".") and Path(path).parent == Path(source).parent:
        return "@board" + path[len(stem):]
    return path


def _normalize(value, source):
    if isinstance(value, dict):
        return {_local(k, source) if os.path.isabs(k) else k: _normalize(v, source)
                for k, v in value.items()}
    if isinstance(value, list):
        return [_normalize(v, source) for v in value]
    if isinstance(value, str) and os.path.isabs(value):
        return _local(value, source)
    return value


def _policy_files(value):
    files = {}
    if isinstance(value, dict):
        for child in value.values():
            files.update(_policy_files(child))
    elif isinstance(value, list):
        for child in value:
            files.update(_policy_files(child))
    elif isinstance(value, str) and value and value.lstrip().startswith(("{", "[")):
        try:
            parsed = json.loads(value)
            _json(parsed)
        except ValueError:
            pass  # The exact uninterpreted environment value is still bound.
        else:
            files.update(_policy_files(parsed))
    elif isinstance(value, str) and value:
        path = Path(value)
        if path.is_absolute() or path.suffix in {".json", ".yaml", ".toml", ".kicad_pcb",
                                               ".kicad_sch", ".kicad_pro", ".kicad_dru", ".net", ".csv"}:
            path = _unalias(path)
            if not path.is_dir():
                files[str(path)] = _hash(path)
    return files


def _environment():
    return {key: value for key, value in os.environ.items()
            if key not in CONTROL_ENV and (key.startswith(("CEC_", "KICAD_")) or key in
                {"PYTHONPATH", "PYTHONHASHSEED", "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "PATH"})}


def _options(operator, supplied):
    if not isinstance(supplied, dict):
        raise ValueError("operator options must be a mapping")
    defaults = ({"max_pairs": 16, "max_bridges": 4, "allow_maze": False,
                 "include_bypass_terminals": False}
                if operator == "force_current" else {"max_paths": 64})
    if set(supplied) - set(defaults):
        raise ValueError("unknown operator options")
    result = dict(defaults, **supplied)
    for key, maximum in (("max_pairs", 64), ("max_bridges", 16), ("max_paths", 128)):
        if key in result and (type(result[key]) is not int or not 1 <= result[key] <= maximum):
            raise ValueError("operator work limit out of bounds")
    if "allow_maze" in result and type(result["allow_maze"]) is not bool:
        raise ValueError("allow_maze must be boolean")
    if ("include_bypass_terminals" in result
            and type(result["include_bypass_terminals"]) is not bool):
        raise ValueError("include_bypass_terminals must be boolean")
    return result


def _request(source, *, operator, net, board_hint, immutable_nets, policy, options,
             timeout_s, finalization_reserve_s):
    import cec_force_current as force
    source = _unalias(source, regular=True)
    if operator not in OPERATIONS or not isinstance(net, str) or not net:
        raise ValueError("explicit supported operator and net required")
    if not isinstance(board_hint, (str, Path)) or not str(board_hint).strip():
        raise ValueError("explicit board hint required")
    if (not isinstance(immutable_nets, (list, tuple, set, frozenset))
            or any(type(n) is not str or not n for n in immutable_nets)):
        raise ValueError("explicit immutable net inventory required")
    if not isinstance(policy, dict):
        raise ValueError("explicit effective policy required")
    _json(policy)
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 300 or type(finalization_reserve_s) not in (int, float)
            or not math.isfinite(finalization_reserve_s)
            or not 0 <= finalization_reserve_s < timeout_s):
        raise ValueError("invalid bounded lease or finalization reserve")
    hint = str(board_hint)
    # Match operator semantics; an enclosing hint overrides the force hint.
    if os.environ.get("CEC_THERMAL_BOARD_HINT", hint) != hint:
        raise Refusal("conflicting_effective_board_hint")
    environment = dict(_environment(), CEC_THERMAL_BOARD_HINT=hint)
    family = _family(source, hint)
    # Operational file paths can appear in the older operator's conservative
    # environment scan. Exclude those only from deterministic scheduling;
    # the raw operator receipt still binds its actual execution environment.
    controls = {str(Path(value).absolute()) for key, value in os.environ.items()
                if key in CONTROL_ENV and os.path.isabs(value)}
    protected = {str(source), *(str(source.with_suffix(ext)) for ext in force.SIDECARS)}
    protected.update(_policy_files(policy))
    protected.update(_policy_files(environment))
    family = {path: value for path, value in family.items() if path not in controls or path in protected}
    identity = _normalize(dict(schema=SCHEMA, operator=operator, net=net, board_hint=hint,
        immutable_nets=sorted(set(immutable_nets)), policy=policy,
        policy_files=_policy_files(policy), source_family=family, code=force._code_identity(),
        environment=environment, environment_files=_policy_files(environment), toolchain=_toolchain(),
        options=_options(operator, options), timeout_s=float(timeout_s),
        finalization_reserve_s=float(finalization_reserve_s)), source)
    return dict(schema=SCHEMA, request_id=_digest(identity), identity=identity,
        source=str(source), board_hint=hint, policy=json.loads(_json(policy)),
        options=identity["options"], operator=operator, net=net,
        immutable_nets=identity["immutable_nets"], timeout_s=float(timeout_s),
        finalization_reserve_s=float(finalization_reserve_s))


def _current(request, source=None, **overrides):
    args = {key: request[key] for key in ("operator", "net", "board_hint", "immutable_nets",
                                        "policy", "options", "timeout_s", "finalization_reserve_s")}
    args.update(overrides)
    return _request(source or request["source"], **args)


def _owner():
    pid = os.getpid()
    token = Path(f"/proc/{pid}/stat")
    boot = Path("/proc/sys/kernel/random/boot_id")
    return dict(pid=pid, host=socket.gethostname(),
        process_start=token.read_text().split(") ", 1)[1].split()[19] if token.is_file() else None,
        boot=boot.read_text().strip() if boot.is_file() else None, nonce=uuid.uuid4().hex)


def _owner_alive(owner):
    if owner.get("host") != socket.gethostname():
        return None  # Unknown remote owner is not permission to steal a lease.
    try:
        pid = int(owner["pid"])
        if pid <= 0:
            return None
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (KeyError, ValueError, TypeError, PermissionError):
        return None
    proc = Path(f"/proc/{pid}/stat")
    if proc.is_file() and owner.get("process_start"):
        fields = proc.read_text().split(") ", 1)[1].split()
        boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        return fields[0] != "Z" and fields[19] == owner["process_start"] and boot == owner.get("boot")
    return True


def _result(request, status, reason, **detail):
    return dict(schema=SCHEMA, request_id=request["request_id"], operator=request["operator"],
        net=request["net"], status=status, reason=reason, accepted=False, changed=False,
        retryable=False, physical_no_path_proof=False, release_authority=False,
        full_kelvin_qualification=False, canonical_adoption=False, private_selection=None, **detail)


def _remaining(request, reserve=0):
    import cec_operation_budget as budget
    available = budget.available_timeout(request["timeout_s"], os.environ, reserve_s=reserve)
    if available <= 0:
        raise Refusal("deferred_budget")
    return available


def _replay(request, source):
    import cec_force_sense_evidence as sense
    return sense.replay(source, board_hint=request["board_hint"],
                        timeout_s=min(60., _remaining(request, 1)))


def _sense_dependencies(before, request):
    import cec_sense_topology as topology
    if (before.get("complete") is not True or before.get("identity_stable") is not True
            or before.get("loaded_board_identity_verified") is not True):
        return dict(reason="incomplete_affected_sense", detail="unbound_or_incomplete_replay")
    rows = before.get("lineage", {}).get("details", [])
    lineage = before.get("lineage", {})
    if (lineage.get("inputs") != len(rows) or lineage.get("resolved") != len(rows)
            or any(row.get("ok") is not True for row in rows)
            or len({row["ref"] for row in rows}) != len(rows)):
        return dict(reason="incomplete_affected_sense", detail="unresolved_typed_inventory")
    demands = [dict(row, input_ref=leg["ref"]) for leg in rows
               for row in topology.placement_segments(leg)]
    affected = {(d["input_ref"], d["leg"]) for d in demands if d["net"] == request["net"]}
    key = lambda d: _json({k: d[k] for k in ("input_ref", "leg", "net", "start", "end")})
    expected = sorted(key(d) for d in demands if (d["input_ref"], d["leg"]) in affected)
    actual = [d for d in before.get("same_net_connectivity", {}).get("details", [])
              if (d.get("input_ref"), d.get("leg")) in affected]
    if sorted(key(d) for d in actual) != expected or any(d.get("ok") is not True for d in actual):
        return dict(reason="incomplete_affected_sense", affected_legs=sorted(map(list, affected)),
                    detail="complete_affected_sense_demands_required_before_private_force_or_branch_work")
    return None


def _preflight(request):
    import cec_force_current as force
    source, net = request["source"], request["net"]
    if request["operator"] == "kelvin_branch":
        if os.environ.get("CEC_POURFIRST_STATE"):
            return dict(reason="enclosing_branch_prefix_unsupported")
        present = [ext for ext in PREFIXES if Path(source).with_suffix(ext).exists()]
        if present:
            return dict(reason="saved_branch_prefix_unsupported", prefixes=present)
    if net in force._ownership(source, request["immutable_nets"]):
        return dict(reason="immutable_net_repair_forbidden")
    _remaining(request, request["finalization_reserve_s"] + 15.)
    before = _replay(request, source)
    if (before.get("source_family_before") != force._family(source, request["board_hint"])
            or before.get("code_before") != force._code_identity()):
        raise Refusal("source_replay_epoch_mismatch")
    return _sense_dependencies(before, request)


def _operator(request, directory):
    import cec_force_current as force
    import cec_kelvin_branch_repair as branch
    module = force if request["operator"] == "force_current" else branch
    return module.propose(request["source"], directory, request["net"],
        board_hint=request["board_hint"], immutable_nets=request["immutable_nets"],
        timeout_s=request["timeout_s"], **request["options"])


def _receipt(request, directory, returned):
    import cec_force_current as force
    import cec_kelvin_branch_repair as branch
    path = directory / "operator" / "receipt.json"
    receipt = _read(path)
    if receipt != returned or not isinstance(receipt, dict):
        raise Refusal("operator_receipt_disagrees_with_return")
    if type(receipt.get("accepted")) is not bool or type(receipt.get("changed")) is not bool:
        raise Refusal("invalid_operator_admission_type")
    if (("net" in receipt and receipt["net"] != request["net"])
            or ("operation" in receipt and receipt["operation"] != OPERATIONS[request["operator"]])):
        raise Refusal("operator_receipt_request_mismatch")
    if receipt.get("accepted") is not True:
        return receipt, path, None
    if (receipt.get("schema") != 1 or receipt.get("operation") != OPERATIONS[request["operator"]]
            or receipt.get("net") != request["net"] or receipt.get("release_authority") is not False
            or receipt.get("source_unchanged") is not True or receipt.get("code_unchanged") is not True):
        raise Refusal("unbound_operator_admission")
    module = force if request["operator"] == "force_current" else branch
    family = module._family(request["source"], request["board_hint"])
    if (receipt.get("source_family_before") != family or receipt.get("source_family_after") != family
            or receipt.get("code_before") != force._code_identity()
            or receipt.get("code_after") != receipt["code_before"]):
        raise Refusal("operator_source_or_code_epoch_mismatch")
    if request["operator"] == "kelvin_branch" and (
            receipt.get("environment_unchanged") is not True
            or receipt.get("environment_before") != receipt.get("environment_after")):
        raise Refusal("operator_environment_epoch_mismatch")
    if not receipt["changed"]:
        if (request["operator"] != "force_current" or receipt.get("candidate") is not None
                or receipt.get("reason") != "qualified_input_prefix"
                or receipt.get("connected") is not True or receipt.get("scoped_kelvin", {}).get("ok") is not True):
            raise Refusal("unverified_operator_noop")
        return receipt, path, Path(request["source"])
    candidate = _unalias(receipt.get("candidate") or "", regular=True)
    if not candidate.is_relative_to(directory / "operator" / "candidate"):
        raise Refusal("candidate_outside_private_operator_family")
    if (receipt.get("candidate_sha256") != _hash(candidate)
            or receipt.get("candidate_family_unchanged") is not True
            or receipt.get("candidate_family_verified") != module._family(candidate, request["board_hint"])):
        raise Refusal("candidate_receipt_epoch_mismatch")
    for key in ("preservation", "whole_board_admission", "scoped_kelvin"):
        field = "accepted" if key == "whole_board_admission" else "ok"
        if receipt.get(key, {}).get(field) is not True:
            raise Refusal("operator_missing_" + key)
    if (receipt.get("exact_refill", {}).get("stable") is not True
            or receipt.get("sense_candidate_identity_matches") is not True):
        raise Refusal("operator_missing_saved_native_epoch")
    if request["operator"] == "force_current":
        required = (receipt.get("current_width", {}).get("ok"),
            receipt.get("authority_proof", {}).get("connected"),
            receipt.get("rated_proof", {}).get("rated_connectivity", {}).get("connected"),
            receipt.get("surface_contacts", {}).get("ok"))
    else:
        required = (receipt.get("saved_path_screen", {}).get("ok"),)
    if any(value is not True for value in required):
        raise Refusal("operator_missing_physical_admission")
    old = {k: v for k, v in _normalize(_family(request["source"], request["board_hint"]), request["source"]).items()
           if k.startswith("@board.")}
    new = {k: v for k, v in _normalize(_family(candidate, request["board_hint"]), candidate).items()
           if k.startswith("@board.")}
    if old != new:
        raise Refusal("candidate_sidecar_family_changed")
    return receipt, path, candidate


def _native_validate(request, candidate, receipt):
    """Independent saved-object replay; the receipt's accepted flag is insufficient."""
    import cec_force_current as force
    import cec_kelvin_branch_repair as branch
    import cec_force_sense_evidence as sense
    import cec_score
    import cec_stage_admission as admission
    source, hint, net = request["source"], request["board_hint"], request["net"]
    _remaining(request, 1)
    preservation = (force.preservation(source, candidate, net=net)
        if request["operator"] == "force_current" else
        branch.preservation(source, candidate, receipt["replacement"], board_hint=hint))
    if preservation.get("ok") is not True:
        raise Refusal("independent_saved_preservation_refused")
    _remaining(request, 1)
    score = admission.evaluate(cec_score.score(source), cec_score.score(str(candidate)))
    if score.get("accepted") is not True:
        raise Refusal("independent_whole_board_refused")
    before, after = _replay(request, source), _replay(request, candidate)
    scoped = sense.admit_changed_net(before, after, net)
    if (scoped.get("ok") is not True or after.get("source_family_before") != force._family(candidate, hint)
            or after.get("loaded_board_identity_verified") is not True):
        raise Refusal("independent_affected_sense_refused")
    rating = None
    if request["operator"] == "force_current":
        _remaining(request, 1)
        diagnosis = force.diagnose(candidate, [net], board_hint=hint)
        rating = diagnosis.get("domains", {}).get(net, {})
        if (rating.get("qualified") is not True or diagnosis.get("source_unchanged") is not True
                or diagnosis.get("code_unchanged") is not True):
            raise Refusal("independent_rated_current_refused")
        if request["options"].get("include_bypass_terminals"):
            # A primary-only diagnosis cannot receive the broader requested
            # tree, including a purported qualified no-op. Re-derive actual
            # native capacitor terminals and the unchanged full-load widths;
            # never trust the producer's cached selection/connected flag.
            import pcbnew
            import cec_fr
            tree, _ = force._graph(pcbnew.LoadBoard(str(candidate)), net,
                rating["domain"], rating["width_contract"],
                cec_fr._project_netclass_resolver(str(candidate))(net) or {},
                include_bypass_terminals=True)
            if tree["rated_connectivity"]["connected"] is not True:
                raise Refusal("independent_rated_bypass_tree_refused")
            rating["bypass_tree_receiving"] = tree
    return dict(preservation=preservation, whole_board=score, scoped_kelvin=scoped, rated_current=rating)


def _worker(request, directory):
    import cec_operation_budget as budget
    directory = Path(directory)
    result = _result(request, "deferred", "not_dispatched")
    try:
        if _current(request)["request_id"] != request["request_id"]:
            raise Refusal("source_policy_environment_or_code_changed")
        dependency = _preflight(request)
        if dependency:
            result = _result(request, "deferred_dependency", dependency["reason"], dependency=dependency)
        else:
            budget.progress("saved_family_private_operator", operator=request["operator"], net=request["net"])
            with budget.finalization_reserve(request["finalization_reserve_s"]) as reservation:
                returned = _operator(request, directory / "operator")
            if reservation["budget_exhausted"]:
                raise budget.OperationFailure(reservation["operation_failure"])
            receipt, path, candidate = _receipt(request, directory, returned)
            result.update(receipt=str(path), receipt_sha256=_hash(path))
            if receipt["accepted"] is not True:
                failure = receipt.get("operation_failure") or {}
                exhausted = failure.get("status") in ("operation_budget_exhausted", "campaign_budget_exhausted")
                exhausted |= receipt.get("reason") in ("deferred_budget", "branch_operation_deadline_exhausted")
                result.update(status="deferred_budget" if exhausted else "deferred_operator",
                    reason="deferred_budget" if exhausted else receipt.get("reason", "operator_refused"),
                    operator_reason=receipt.get("reason"), operation_failure=failure or None)
            else:
                epoch = _family(candidate, request["board_hint"])
                budget.progress("saved_family_independent_admission", operator=request["operator"])
                native = _native_evidence_json_data(_native_validate(request, candidate, receipt))
                if epoch != _family(candidate, request["board_hint"]) or _hash(path) != result["receipt_sha256"]:
                    raise Refusal("candidate_or_receipt_changed_during_validation")
                result.update(status="private_selection_ready", reason="saved_family_independently_verified",
                    accepted=True, changed=receipt["changed"], native_admission=native,
                    private_selection=dict(board=str(candidate), family=epoch, family_sha256=_digest(epoch),
                        source_request_id=request["request_id"], operator=request["operator"],
                        transition="additive_force" if request["operator"] == "force_current" else "typed_branch_replacement"))
        if _current(request)["request_id"] != request["request_id"]:
            raise Refusal("source_policy_environment_or_code_changed")
    except budget.OperationFailure as exc:
        exhausted = exc.failure_evidence.get("status") in ("operation_budget_exhausted", "campaign_budget_exhausted")
        result = _result(request, "deferred_budget" if exhausted else "deferred_worker",
            "deferred_budget" if exhausted else "private_operator_worker_failed", operation_failure=exc.failure_evidence)
    except (Refusal, OSError, ValueError, KeyError, TypeError) as exc:
        result = _result(request, "deferred_budget" if str(exc) == "deferred_budget" else "deferred_evidence",
                         str(exc), error=type(exc).__name__)
    _write_new(directory / "validation.json", result)
    return result


def _verified_result(request, directory, result):
    if (result.get("request_id") != request["request_id"] or result.get("release_authority") is not False
            or result.get("canonical_adoption") is not False
            or result.get("full_kelvin_qualification") is not False
            or type(result.get("accepted")) is not bool or type(result.get("changed")) is not bool):
        raise Refusal("validation_request_identity_mismatch")
    if result.get("accepted") is True:
        native = result.get("native_admission") or {}
        if (result.get("status") != "private_selection_ready"
                or native.get("preservation", {}).get("ok") is not True
                or native.get("whole_board", {}).get("accepted") is not True
                or native.get("scoped_kelvin", {}).get("ok") is not True
                or (request["operator"] == "force_current"
                    and native.get("rated_current", {}).get("qualified") is not True)):
            raise Refusal("validation_missing_independent_admission")
        selection = result.get("private_selection") or {}
        transition = "additive_force" if request["operator"] == "force_current" else "typed_branch_replacement"
        if selection.get("operator") != request["operator"] or selection.get("transition") != transition:
            raise Refusal("selection_transition_mismatch")
        candidate = _unalias(selection["board"], regular=True)
        if result.get("changed") is True and not candidate.is_relative_to(directory / "operator" / "candidate"):
            raise Refusal("selection_outside_private_family")
        if (selection.get("source_request_id") != request["request_id"]
                or selection.get("family") != _family(candidate, request["board_hint"])
                or selection.get("family_sha256") != _digest(selection["family"])
                or _hash(directory / "operator" / "receipt.json") != result.get("receipt_sha256")):
            raise Refusal("selection_or_receipt_changed")
    elif result.get("changed") is not False or result.get("private_selection") is not None:
        raise Refusal("unadmitted_result_contains_selection")
    return dict(result, evidence_directory=str(directory))


def _completed_operation(directory):
    operation = _read(directory / "supervisor" / "operation.json")
    if (operation.get("status") != "complete" or operation.get("operation") != "saved-family-repair"
            or operation.get("directory") != str(directory / "supervisor")
            or not isinstance(operation.get("command"), list)
            or len(operation["command"]) != 4
            or Path(operation["command"][0]).resolve() != Path(sys.executable).resolve()
            or Path(operation["command"][1]).resolve() != Path(__file__).resolve()
            or operation["command"][-2:] != ["--request", str(directory / "request.json")]):
        raise Refusal("no_completed_supervised_validation")
    return operation


def select_private(result, source, *, board_hint, immutable_nets, policy):
    """Recheck returned selection at handoff; no copy, replacement or gate waiver."""
    if result.get("accepted") is not True:
        return None
    directory = _unalias(result["evidence_directory"])
    request = _read(directory / "request.json")
    current = _current(request, source, board_hint=board_hint, immutable_nets=immutable_nets, policy=policy)
    if current["request_id"] != request["request_id"] or result.get("request_id") != request["request_id"]:
        raise Refusal("selection_source_policy_environment_or_code_changed")
    if _hash(directory / "validation.json") != result.get("validation_sha256"):
        raise Refusal("validation_receipt_changed")
    saved = _read(directory / "validation.json")
    _completed_operation(directory)
    if any(result.get(key) != value for key, value in saved.items()):
        raise Refusal("returned_result_disagrees_with_validated_receipt")
    checked = _verified_result(current, directory, saved)
    if checked.get("private_selection") != result.get("private_selection") or checked.get("accepted") is not True:
        raise Refusal("returned_selection_disagrees_with_validated_receipt")
    return checked["private_selection"]["board"]


def _check_ledger_root(root, request):
    """A prior admitted private selection may seed another ledger request.

    No arbitrary authority-containing root is allowed. The only exception is
    the exact verified family selected by a completed sibling request; the new
    request directory must still be disjoint from every protected input.
    """
    import cec_force_current as force
    protected = force._protected_paths(request["source"], request["board_hint"])
    contained = {path for path in protected if Path(path).resolve().is_relative_to(root)}
    if contained:
        source = Path(request["source"])
        try:
            relative = source.relative_to(root)
        except ValueError as exc:
            raise Refusal("ledger_contains_protected_authority") from exc
        if (len(relative.parts) != 4 or relative.parts[1:3] != ("operator", "candidate")
                or len(relative.parts[0]) != 64
                or any(c not in "0123456789abcdef" for c in relative.parts[0])):
            raise Refusal("ledger_source_is_not_admitted_private_family")
        previous_dir = root / relative.parts[0]
        previous_request = _read(previous_dir / "request.json")
        previous = _read(previous_dir / "result.json")
        selected = select_private(previous, previous_request["source"],
            **{key: previous_request[key] for key in ("board_hint", "immutable_nets", "policy")})
        if (previous_request.get("request_id") != relative.parts[0]
                or selected != str(source)
                or any(not _local(path, source).startswith("@board") for path in contained)):
            raise Refusal("ledger_source_family_handoff_refused")
    force._check_proposal_directory(root / request["request_id"], protected)


def dispatch(source, ledger_root, *, operator, net, board_hint, immutable_nets, policy,
             options=None, timeout_s=120., finalization_reserve_s=20., seed=None, recover=False):
    """Acquire one deterministic request; launch at most one private operator.

    A dead owner does not authorize replay. Recovery only seals a complete
    supervised validation already present; incomplete work stays quarantined.
    The caller must keep this ledger outside disposable candidate directories.
    """
    import cec_operation_budget as budget
    request = _request(source, operator=operator, net=net, board_hint=board_hint,
        immutable_nets=immutable_nets, policy=policy, options=options or {},
        timeout_s=timeout_s, finalization_reserve_s=finalization_reserve_s)
    root = _unalias(ledger_root)
    _check_ledger_root(root, request)
    root.mkdir(parents=True, exist_ok=True)
    _sync_directory(root.parent)
    directory = root / request["request_id"]
    try:
        directory.mkdir()
        _sync_directory(root)
    except FileExistsError:
        try:
            _unalias(directory)
            previous = _read(directory / "request.json")
            if previous.get("request_id") != request["request_id"] or previous.get("identity") != request["identity"]:
                raise Refusal("ledger_request_mismatch")
            if (directory / "result.json").exists():
                result = _read(directory / "result.json")
                _verified_result(request, directory, result)
                if result.get("accepted") is True:
                    _completed_operation(directory)
                    if _hash(directory / "validation.json") != result.get("validation_sha256"):
                        raise Refusal("validation_receipt_changed")
                    validated = _read(directory / "validation.json")
                    if any(result.get(key) != validated.get(key) for key in validated):
                        raise Refusal("ledger_result_disagrees_with_validation")
                    result = dict(_verified_result(request, directory, validated),
                                  validation_sha256=result["validation_sha256"])
                elif result.get("request_id") != request["request_id"]:
                    raise Refusal("ledger_result_request_mismatch")
                return dict(result, cached=True, operator_replayed=False)
            alive = _owner_alive(_read(directory / "owner.json"))
            if alive is not False or not recover:
                return _result(request, "deferred_in_progress" if alive is not False else "deferred_recovery_required",
                    "request_owner_active_or_unknown" if alive is not False else "interrupted_attempt_requires_explicit_recovery",
                    evidence_directory=str(directory), owner_alive=alive)
            (directory / "recovery").mkdir()
            _write_new(directory / "recovery" / "owner.json", _owner())
            _completed_operation(directory)
            result = _verified_result(request, directory, _read(directory / "validation.json"))
            result.update(validation_sha256=_hash(directory / "validation.json"), recovered=True, operator_replayed=False)
            _write_new(directory / "result.json", result)
            return result
        except (OSError, ValueError, KeyError, TypeError) as exc:
            return _result(request, "deferred_recovery_required", str(exc), evidence_directory=str(directory))
    _write_new(directory / "request.json", request)
    _write_new(directory / "owner.json", _owner())
    try:
        environment = dict(os.environ)
        budget.available_timeout(timeout_s, environment, reserve_s=finalization_reserve_s)
        deadline = min([time.time() + timeout_s] + [float(environment[key]) for key in
            ("CEC_OPERATION_DEADLINE_EPOCH", "CEC_JOB_DEADLINE_EPOCH") if key in environment])
        environment["CEC_OPERATION_DEADLINE_EPOCH"] = str(deadline)
        environment["CEC_THERMAL_BOARD_HINT"] = str(board_hint)
        _write_new(directory / "dispatch.json", dict(seed=seed, deadline_epoch=deadline, requested_at=time.time()))
        command = [sys.executable, str(Path(__file__).resolve()), "--request", str(directory / "request.json")]
        operation = budget.run(command, directory / "supervisor", operation="saved-family-repair",
                               timeout=timeout_s, env=environment)
        if _current(request)["request_id"] != request["request_id"]:
            raise Refusal("source_policy_environment_or_code_changed")
        result = _verified_result(request, directory, _read(directory / "validation.json"))
        result.update(validation_sha256=_hash(directory / "validation.json"), operation=operation)
    except budget.OperationFailure as exc:
        exhausted = exc.failure_evidence.get("status") in ("operation_budget_exhausted", "campaign_budget_exhausted")
        result = _result(request, "deferred_budget" if exhausted else "deferred_worker",
            "deferred_budget" if exhausted else "supervised_worker_failed", operation_failure=exc.failure_evidence)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = _result(request, "deferred_evidence", str(exc), error=type(exc).__name__)
    result.update(evidence_directory=str(directory), operator_replayed=False)
    _write_new(directory / "result.json", result)
    return result


def main(argv=None):
    import cec_operation_budget as budget
    diagnostics = budget.arm_diagnostics()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    args = parser.parse_args(argv)
    request_path = _unalias(args.request, regular=True)
    request = _read(request_path)
    _worker(request, request_path.parent)
    return 0


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code)
