"""Shared dimensional authority for route generation, repair and signoff.

This compiles requirements, not permission to resize protected copper. Ordinary
branch, aggregate trunk and independently qualified local escape are distinct
roles. In particular, a net current never makes every branch carry that current.
"""
from __future__ import annotations

import fnmatch
import json
import math
from pathlib import Path


class DimensionContractError(ValueError):
    pass


def _number(value, label, *, zero=True):
    number = float(value)
    if not math.isfinite(number) or number < 0 or (not zero and number == 0):
        raise DimensionContractError("invalid %s: %r" % (label, value))
    return number


def hierarchical_pattern_matches(net, pattern):
    net, pattern = str(net or ""), str(pattern or "")
    if not net or not pattern:
        return False
    leaf = net.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatchcase(candidate, pattern)
               for candidate in (net, leaf, "/" + leaf))


def project_path(board_path):
    """Exact sibling wins; a unique sibling is accepted, ambiguity is refused."""
    path = Path(board_path)
    exact = path.with_suffix(".kicad_pro")
    if exact.is_file():
        return exact
    alternatives = sorted(path.parent.glob("*.kicad_pro"))
    if len(alternatives) > 1:
        raise DimensionContractError("ambiguous project authority beside %s" % path)
    return alternatives[0] if alternatives else None


class NetclassTable:
    def __init__(self, settings=None, *, source="caller"):
        settings = settings or {}
        self.source = source
        self.classes = {str(row["name"]): dict(row)
                        for row in settings.get("classes", ()) if row.get("name")}
        self.assignments = settings.get("netclass_assignments") or {}
        self.patterns = [(str(row["netclass"]), str(row["pattern"]))
                         for row in settings.get("netclass_patterns", ())
                         if row.get("netclass") in self.classes and row.get("pattern")]
        for spec in self.classes.values():
            for key in ("track_width", "clearance", "via_diameter", "via_drill",
                        "diff_pair_width", "diff_pair_gap"):
                if key in spec and spec[key] is not None:
                    _number(spec[key], key)

    @classmethod
    def from_board_path(cls, board_path):
        path = project_path(board_path)
        if path is None:
            return cls(source="project_absent")
        try:
            settings = json.loads(path.read_text(encoding="utf-8")).get("net_settings") or {}
            return cls(settings, source=str(path))
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            raise DimensionContractError("unreadable dimension authority %s: %s" %
                                         (path, exc)) from exc

    def resolve_name(self, net):
        chosen = self.assignments.get(net)
        if isinstance(chosen, list):
            # Preserve the existing project's explicit ordered-class convention.
            chosen = chosen[0] if chosen else None
        if chosen:
            if chosen not in self.classes:
                raise DimensionContractError("unknown assigned netclass %r for %s" % (chosen, net))
            return chosen
        for name, pattern in self.patterns:
            if hierarchical_pattern_matches(net, pattern):
                return name
        return "Default"

    def resolve(self, net):
        name = self.resolve_name(net)
        return {**self.classes.get(name, {}), "name": name}


def board_limits(board):
    """The common ordinary-feature floor; no fabrication opt-in is inferred."""
    settings = board.GetDesignSettings()
    fields = {"track_width": ("m_TrackMinWidth", 0.0),
              "via_diameter": ("m_ViasMinSize", 0.50),
              "via_drill": ("m_MinThroughDrill", 0.20),
              "annular": ("m_ViasMinAnnularWidth", 0.10)}
    return {key: _number(float(getattr(settings, attr, default * 1e6)) / 1e6, attr)
            for key, (attr, default) in fields.items()}


def source_board_limits(board, source=None):
    """Monotone ordinary floors from native settings AND the exact project.

    LoadBoard does not reliably install sibling project settings. Never
    replace a stronger saved floor with a process-global native default, or
    treat a saved lower value as permission to lower the native floor.
    """
    settings = board.GetDesignSettings()
    result = board_limits(board)
    additions = {'clearance': 'm_MinClearance', 'hole_to_hole': 'm_HoleToHoleMin',
                 'hole_clearance': 'm_HoleClearance', 'copper_edge': 'm_CopperEdgeClearance'}
    result.update({key: _number(getattr(settings, attr, 0)/1e6, attr)
                   for key, attr in additions.items()})
    path = Path(source or board.GetFileName()).with_suffix('.kicad_pro')
    if not path.is_file():
        return result
    if path.stat().st_size > 4*1024*1024:
        raise DimensionContractError('bounded_exact_saved_project_floors_required')
    rules = json.loads(path.read_text()).get('board', {}).get('design_settings', {}).get('rules', {})
    if type(rules) is not dict:
        raise DimensionContractError('literal_saved_board_floor_inventory_required')
    names = {'track_width': 'min_track_width', 'via_diameter': 'min_via_diameter',
             'via_drill': 'min_through_hole_diameter', 'annular': 'min_via_annular_width',
             'clearance': 'min_clearance', 'hole_to_hole': 'min_hole_to_hole',
             'hole_clearance': 'min_hole_clearance', 'copper_edge': 'min_copper_edge_clearance'}
    for name, saved in names.items():
        if saved not in rules:
            continue
        value = rules[saved]
        if type(value) not in (int, float) or not math.isfinite(value) or not 0 <= value <= 100:
            raise DimensionContractError('finite_bounded_exact_saved_board_floor_required:'+saved)
        result[name] = max(result[name], math.ceil(value*1e6)/1e6)
    return result


def ordinary_via_geometry(spec, limits=None, *, requested=None):
    limits = limits or {}
    requested = requested or (0.0, 0.0)
    drill = max(_number(requested[1], "requested drill"),
                _number(spec.get("via_drill") or 0, "class drill"),
                _number(limits.get("via_drill") or 0, "board drill"))
    annular = _number(limits.get("annular") or 0, "annular ring")
    diameter = max(_number(requested[0], "requested diameter"),
                   _number(spec.get("via_diameter") or 0, "class diameter"),
                   _number(limits.get("via_diameter") or 0, "board diameter"))
    # Compile in native integer units before returning millimetres. Floating
    # addition (e.g. .35 + 2*.15) can otherwise become .6499999999999999,
    # which KiCad FromMM truncates to a land ONE nm below the required ring.
    # Round requirements outward, then construct the ring from those integers.
    drill_nm=math.ceil(drill*1e6)
    annular_nm=math.ceil(annular*1e6)
    diameter_nm=max(math.ceil(diameter*1e6),drill_nm+2*annular_nm)
    diameter,drill=diameter_nm/1e6,drill_nm/1e6
    # Some decimal fractions still multiply back below their integer. Keep
    # every native consumer (rounding or truncating) outside the requirement.
    if int(diameter*1e6)<diameter_nm:diameter=(diameter_nm+1)/1e6
    if int(drill*1e6)<drill_nm:drill=(drill_nm+1)/1e6
    return diameter, drill


def current_trace_widths(current, layers, profile, *, rise_c=30.0):
    """One margin-aware model used by both trunk planning and width signoff."""
    import cec_fab_profile as fab
    amps = _number(current["amps"], "sustained current", zero=False)
    rise_c = _number(rise_c, "temperature rise", zero=False)
    margin = _number(current.get("geometry_margin", 1.0 if
                                current.get("margin_included") else 1.25),
                     "geometry margin", zero=False)
    if current.get("margin_included") and abs(margin - 1.0) > 1e-9:
        raise DimensionContractError("current budget includes margin but requests another geometry margin")
    if not profile:
        raise DimensionContractError("rated trace requires a declared copper profile")
    return {layer: fab.ipc2221_required_width_mm(
                amps, layer, profile_name=profile, rise_c=rise_c, margin=margin)
            for layer in layers}


def contained_via_repair_candidate(profile_name, diameter, drill):
    """Offer process geometry without shrinking existing copper or granting a waiver.

    Callers must separately prove through-via type, full same-net pad
    containment, foreign-copper clearance and hole spacing at the proposed size.
    """
    import cec_fab_profile as fab
    profile = fab.get_profile(profile_name) if profile_name else None
    preferred = fab.preferred_pofv_geometry(profile)
    if preferred is None:
        return None
    drill = max(_number(drill, "existing drill", zero=False), preferred[1])
    diameter = max(_number(diameter, "existing diameter", zero=False),
                   preferred[0], drill + 2.0 * profile["pofv_annular_min_mm"])
    return ((diameter, drill) if fab.pofv_dimensions(profile, diameter, drill)[0]
            else None)


def compile_spec(spec, *, limits=None, current=None, role="branch", source="caller"):
    """Compile ordinary geometry, adding aggregate ampacity only for trunks."""
    if role not in {"branch", "trunk"}:
        raise DimensionContractError("unqualified route role %r" % role)
    limits = limits or {}
    out = dict(spec)
    width = max(_number(spec.get("track_width") or 0, "class width"),
                _number(limits.get("track_width") or 0, "board width"))
    diameter, drill = ordinary_via_geometry(spec, limits)
    out.update(track_width=width, via_diameter=diameter, via_drill=drill)
    if role == "trunk":
        if not current or not current.get("required_by_layer_mm"):
            raise DimensionContractError("aggregate trunk has no current-width authority")
        out["track_width_by_layer_mm"] = {
            layer: max(width, _number(value, "current width", zero=False))
            for layer, value in current["required_by_layer_mm"].items()}
    else:
        # A trunk's cached metadata cannot silently follow its local branches.
        out.pop("track_width_by_layer_mm", None)
    out["dimension_contract"] = {
        "schema": 1, "role": role, "source": source,
        "class": spec.get("name", "Default"), "board_limits_mm": dict(limits),
        "current": dict(current or {}) if role == "trunk" else None}
    return out


def nonload_measurement_width(board, board_path, net, *, parent_spec):
    """Geometry proposal for an independently proved non-load input leaf.

    This does NOT prove that a trace is a measurement branch. Consumers must
    separately establish the manufacturer/package/input topology, one actual
    source-land contact and unchanged full-load terminal partitions. A rail's
    preferred aggregate trace width is not an input-stub load specification.
    Use only the authored project's explicit Default branch width plus the
    unchanged native board floor; absent that authority keep the old strict
    parent-net width. Never infer a bias current or grant trunk/barrel credit.
    Clearance and via requirements are NOT overridden by this width proposal.
    """
    # A differently named neighbour can be a valid legacy netclass lookup,
    # but is NOT authority to narrow a source-bound measurement exemption.
    # Only the exact source-family project may supply this role override.
    exact_project = Path(board_path).with_suffix('.kicad_pro')
    table = (NetclassTable.from_board_path(board_path) if exact_project.is_file()
             else NetclassTable(source='exact_project_absent_strict_parent_fallback'))
    ordinary = table.classes.get('Default')
    explicit = bool(ordinary and ordinary.get('track_width') is not None)
    if explicit:
        if isinstance(ordinary['track_width'], bool):
            raise DimensionContractError('boolean_nonload_branch_width_is_not_authority')
        _number(ordinary['track_width'], 'authored nonload branch width', zero=False)
    basis = ordinary if explicit else parent_spec
    spec = compile_spec(basis or {}, limits=board_limits(board), role='branch',
                        source=table.source if explicit else 'unchanged_parent_net_fallback')
    width = math.ceil(spec['track_width'] * 1e6)
    if width <= 0:
        raise DimensionContractError('positive_authored_nonload_branch_width_required')
    return dict(width_nm=width, source=table.source,
        basis='explicit_project_Default_and_native_board_minimum' if explicit else 'unchanged_parent_net_width',
        net=str(net), parent_net_class=dict(parent_spec or {}),
        authored_ordinary_class=dict(ordinary) if explicit else None,
        native_board_limits_mm=board_limits(board),
        manufacturer_input_and_single_contact_and_partition_proof_required=True,
        clearance_or_via_requirements_changed=False, numeric_load_assumed=False,
        trunk_capacity_credited=False, admission_authority=False)


def project_resolver(board_path, *, board=None, table=None):
    table = table if table is not None else NetclassTable.from_board_path(board_path)
    limits = board_limits(board) if board is not None else {}
    fallback = {"name": "Default", "via_diameter": 0.6, "via_drill": 0.3}

    def resolve(net):
        spec = table.resolve(net) if table.classes else fallback
        return compile_spec(spec, limits=limits, source=table.source)

    return resolve


def with_trunk_contracts(base_resolver, contracts):
    """Wrap ordinary sizing only for nets with resolved aggregate authority."""
    def resolve(net):
        base = dict(base_resolver(net) or {})
        current = contracts.get(net)
        if not current:
            return base
        metadata = base.get("dimension_contract") or {}
        return compile_spec(base, limits=metadata.get("board_limits_mm"),
                            current=current, role="trunk",
                            source=metadata.get("source", "caller"))
    return resolve
