"""Exact selected-package land-pattern alternatives, not arbitrary pad edits.

The source-selected MPN, existing native package and vendored manufacturer
drawing select an alternative. No board, reference or coordinate heuristic
participates. Pad identities/nets, component pose, other native material and
all old conductor partitions remain immutable. This narrow receiver is not
assembly, current, thermal, Kelvin, or release qualification.
"""
import math
from pathlib import Path
import re
import tempfile
import time

import pcbnew
import cec_additive_route_receiving as additive
import cec_copper_echo as sexpr
import cec_device_power_roles as roles
import cec_field_coupling as field
import cec_force_current as force
import cec_measurement_leaf as leaf
import cec_ordinary_route_receiving as ordinary
from cec_footprint_fields import footprint_properties


ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'lib/vendor/Package_TO_SOT_SMD.pretty'
CATALOG = {
    'INA181 DBV': dict(old='SOT-23-6', new='SOT-23-6_TI_DBV0006A',
        library='cec-Package_TO_SOT_SMD',
        source='https://www.ti.com/lit/ds/symlink/ina181.pdf',
        drawing='DBV0006A 4214840/G 08/2024', page=60),
    'Bourns CSS2H-2512R-L500F': dict(old='R_2512_6332Metric',
        new='R_Bourns_CSS2H-2512R_L500',library='cec-Resistor_SMD',
        directory='lib/vendor/Resistor_SMD.pretty',selected_mpn='CSS2H-2512R-L500F',
        manufacturer='Bourns',
        value_ohms=.0005,source='https://www.bourns.com/docs/product-datasheets/css2h-2512.pdf',
        drawing='CSS2H-2512 Recommended Pad Layout',page=2,
        datasheet='lib/datasheets/Bourns_CSS2H-2512.pdf',
        datasheet_sha256='7e32b223f4b0f086d9e08cd5a4fb42e9935cf119db3dd9cf3ea7969bdd643909'),
}


def _library(rule):
    return ROOT/rule['directory'] if 'directory' in rule else LIB


def library_identity():
    files={_library(r)/(r[k]+'.kicad_mod')for r in CATALOG.values()for k in ('old','new')}
    files.update(ROOT/r['datasheet']for r in CATALOG.values()if 'datasheet'in r)
    return {str(p):force._hash(p)for p in sorted(files)}


def _bounds(timeout_s):
    if (type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or not 0 < timeout_s <= 10):
        raise ValueError('bounded_manufacturer_land_pattern_work_required')
    return time.monotonic() + timeout_s


def _pad(p):
    return (p.GetNumber(), tuple(p.GetPosition()), tuple(p.GetSize()),
        p.GetOrientationDegrees(), p.GetShape(), p.GetRoundRectRadiusRatio(),
        p.GetAttribute(), tuple(p.GetLayerSet().Seq()), p.HasHole(),
        tuple(p.GetOffset()),tuple(p.GetDrillSize()),int(p.GetDrillShape()))


def _edge(e):
    return (int(e.GetLayer()), int(e.GetShape()), tuple(e.GetStart()),
        tuple(e.GetEnd()), int(e.GetWidth()))


def _placed(name, fp, *, library=None):
    template = pcbnew.FootprintLoad(str(LIB if library is None else library), name)
    if template is None:
        raise ValueError('vendored_manufacturer_pattern_missing')
    # Flip consults native board layer settings; a detached footprint can
    # segfault in KiCad 10. Attach its parent without adding it to population.
    template.SetParent(fp.GetBoard())
    if fp.IsFlipped():
        template.Flip(pcbnew.VECTOR2I(0, 0), False)
    template.SetOrientationDegrees(fp.GetOrientationDegrees())
    template.SetPosition(fp.GetPosition())
    return template


def _courts(fp):
    return [e for e in fp.GraphicalItems()
        if e.GetLayer() in (pcbnew.F_CrtYd, pcbnew.B_CrtYd)]


def _selected(fp):
    # No value-family/package inference: the actually selected MPN is needed.
    if not footprint_properties(fp).get('MPN') or fp.IsDNP():
        raise ValueError('selected_manufacturer_mpn_required')
    selected=str(footprint_properties(fp)['MPN']).strip().upper()
    exact=[(name,r)for name,r in CATALOG.items()if r.get('selected_mpn')==selected]
    if exact:
        if len(exact)!=1:raise ValueError('unique_selected_manufacturer_pattern_required')
        name,rule=exact[0]
        value=re.fullmatch(r'\s*([0-9]+(?:\.[0-9]+)?)\s*([mukKM]?)\s*(?:Ω|[Oo][Hh][Mm])?\s*',fp.GetValue())
        multipliers={'':1.,'m':1e-3,'u':1e-6,'k':1e3,'K':1e3,'M':1e6}
        if (not value or float(value[1])*multipliers[value[2]]!=rule['value_ohms']
                or force._hash(ROOT/rule['datasheet'])!=rule['datasheet_sha256']):
            raise ValueError('selected_manufacturer_value_or_primary_drawing_mismatch')
        model=dict(device_package=name)
    else:
        model = roles.footprint_contract(fp)
        rule = CATALOG.get(model['device_package']) if model else None
    if rule is None or fp.GetFPIDAsString() != rule['library'] + ':' + rule['old']:
        raise ValueError('source_selected_package_has_no_exact_land_pattern_alternative')
    library=_library(rule)
    old, new = _placed(rule['old'], fp,library=library), _placed(rule['new'], fp,library=library)
    pads = list(fp.Pads())
    count=len(list(old.Pads()))
    if (len(pads) != count or len({p.GetNumber() for p in pads}) != count
            or sorted(map(_pad, pads)) != sorted(map(_pad, old.Pads()))):
        raise ValueError('source_lands_are_not_the_exact_catalog_package')
    if (any(e.GetClass() != 'PCB_SHAPE' or e.GetShape() not in (pcbnew.SHAPE_T_SEGMENT,pcbnew.SHAPE_T_RECT)
            for e in _courts(fp))
            or sorted(map(_edge, _courts(fp))) != sorted(map(_edge, _courts(old)))):
        raise ValueError('source_courtyard_is_not_the_exact_catalog_package')
    # Positive geometry gate independent of a footprint filename or its SHA.
    local = pcbnew.FootprintLoad(str(library), rule['new'])
    if 'selected_mpn'in rule:
        expected={'1':(-2.6,0),'2':(2.6,0)}
        size=(1800000,3400000);shape=pcbnew.PAD_SHAPE_RECT;radius=None
    else:
        expected = {'1':(-1.3,-.95),'2':(-1.3,0),'3':(-1.3,.95),
                    '4':(1.3,.95),'5':(1.3,0),'6':(1.3,-.95)}
        size=(1100000,600000);shape=pcbnew.PAD_SHAPE_ROUNDRECT;radius=(49999,50001)
    if (len(list(local.Pads())) != len(expected) or any(
            p.GetNumber() not in expected
            or tuple(p.GetPosition()) != tuple(int(round(v*1e6)) for v in expected[p.GetNumber()])
            or tuple(p.GetSize()) != size or p.GetShape() != shape
            or radius is not None and not radius[0] <= p.GetRoundRectCornerRadius() <= radius[1]
            or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD or p.HasHole()
            or tuple(p.GetOffset())!=(0,0)
            or set(map(int,p.GetLayerSet().Seq()))!={int(pcbnew.F_Cu),int(pcbnew.F_Mask),int(pcbnew.F_Paste)}
            for p in local.Pads())):
        raise ValueError('manufacturer_drawing_dimensions_changed')
    return model, rule, old, new


def plan(board, footprint_uuids, *, timeout_s=10.):
    deadline = _bounds(timeout_s)
    ids = ordinary._ids(footprint_uuids, 'manufacturer_package_scope', 4)
    if not ids:
        raise ValueError('finite_nonempty_manufacturer_package_scope_required')
    live = {force._uid(fp):fp for fp in board.GetFootprints()}
    rows = []
    for uid in sorted(ids):
        if time.monotonic() >= deadline:
            raise ValueError('manufacturer_pattern_plan_deadline')
        if uid not in live:
            raise ValueError('actual_source_manufacturer_package_missing')
        fp = live[uid]
        model, rule, old, new = _selected(fp)
        rows.append(dict(footprint_uuid=uid, device_package=model['device_package'],
            source=rule['source'], drawing=rule['drawing'], page=rule['page'],
            old_pattern=rule['old'], new_pattern=rule['new'], library=rule['library'],
            old_library_sha256=force._hash(_library(rule)/(rule['old']+'.kicad_mod')),
            new_library_sha256=force._hash(_library(rule)/(rule['new']+'.kicad_mod')),
            **({k:rule[k]for k in ('selected_mpn','datasheet','datasheet_sha256')}if 'selected_mpn'in rule else {})))
    return dict(schema=1, scope='exact_selected_manufacturer_land_pattern',
        footprint_uuids=sorted(ids), patterns=rows,
        source_native_binding=leaf._binding(board), release_authority=False,
        current_authority=False, assembly_qualified=False)


def materialize(board, proposal):
    # A worker cannot author a geometry, mask/paste exception, or package rule.
    if plan(board, proposal.get('footprint_uuids', ())) != proposal:
        raise ValueError('manufacturer_pattern_proposal_differs_from_source_rederivation')
    live = {force._uid(fp):fp for fp in board.GetFootprints()}
    for row in proposal['patterns']:
        fp = live[row['footprint_uuid']]
        _, rule, old, new = _selected(fp)
        target = {p.GetNumber():p for p in new.Pads()}
        for pad in fp.Pads():
            p = target[pad.GetNumber()]
            pad.SetPosition(p.GetPosition())
            pad.SetSize(p.GetSize())
            pad.SetShape(p.GetShape())
            pad.SetRoundRectRadiusRatio(p.GetRoundRectRadiusRatio())
        # FootprintLoad regenerates template UUIDs. Associate the canonical
        # ordered library lines by old geometry, never by those transient IDs,
        # retaining every actual source line UUID.
        old_edges = {_edge(a):b for a,b in zip(_courts(old),_courts(new))}
        for e in _courts(fp):
            target_edge = old_edges[_edge(e)]
            e.SetStart(target_edge.GetStart());e.SetEnd(target_edge.GetEnd())
        fp.SetFPIDAsString(rule['library'] + ':' + rule['new'])
        fp.SetLibDescription(new.GetLibDescription())


def receive(source, candidate, *, board_hint, footprint_uuids, timeout_s=10.):
    started = time.monotonic()
    result = dict(schema=1, scope='exact_selected_manufacturer_land_pattern_receiving',
        ok=False, complete=False, errors=[], added_native_uuids=[],
        retired_track_uuids=[], retired_via_uuids=[], release_authority=False,
        current_authority=False, assembly_qualified=False, inherited_debt_qualified=False)
    try:
        deadline = _bounds(timeout_s)
        paths = [Path(p).resolve() for p in (source,candidate)]
        families = [force._family(p,board_hint) for p in paths]
        epoch = force._code_identity()
        libraries = library_identity()
        parent, child = [pcbnew.LoadBoard(str(p)) for p in paths]
        proposal = plan(parent, footprint_uuids, timeout_s=max(.001,deadline-time.monotonic()))
        old_root, old = additive._nodes(paths[0]); new_root, new = additive._nodes(paths[1])
        if old.keys() != new.keys():
            raise ValueError('land_pattern_phase_cannot_change_native_population')
        old_parts = ordinary._partition(parent, deadline)
        materialize(parent, proposal)
        with tempfile.TemporaryDirectory(prefix='cec-manufacturer-pattern-') as work:
            projected = force._copy_family(paths[0],Path(work)/'projected')
            field._save_field_snapshot(parent,projected)
            root, nodes = additive._nodes(projected)
            if (sexpr._freeze(root) != sexpr._freeze(new_root) or nodes.keys()!=new.keys()
                    or any(sexpr._freeze(nodes[u])!=sexpr._freeze(new[u]) for u in nodes)
                    or force._sidecars(projected)!=force._sidecars(paths[1])):
                raise ValueError('candidate_is_not_exact_manufacturer_package_replay')
        original = pcbnew.LoadBoard(str(paths[0]))
        originals = {force._uid(fp):fp for fp in original.GetFootprints()}
        targets = {force._uid(fp):fp for fp in child.GetFootprints()}
        bindings = {}
        for uid in proposal['footprint_uuids']:
            a = {force._uid(p):p for p in originals[uid].Pads()}
            b = {force._uid(p):p for p in targets[uid].Pads()}
            if a.keys()!=b.keys():
                raise ValueError('manufacturer_pattern_pad_identity_changed')
            for key in a:
                bindings[force._item_key(b[key])] = force._item_key(a[key])
        retained = set().union(*old_parts)
        new_parts = ordinary._partition(child,deadline,retained_keys=retained,
            _identity_rebindings=bindings)
        if {frozenset(p) for p in old_parts}!={frozenset(p) for p in new_parts}:
            raise ValueError('manufacturer_pattern_lost_prior_native_conductor_component_or_acquired_contact')
        if (families != [force._family(p,board_hint) for p in paths]
                or epoch != force._code_identity() or libraries != library_identity()
                or time.monotonic()>=deadline):
            raise ValueError('manufacturer_pattern_identity_or_deadline_changed')
        result.update(ok=True,complete=True,proposal=proposal,
            modified_native_uuids=proposal['footprint_uuids'],
            exact_manufacturer_land_pattern_replayed=True,
            all_prior_native_terminal_and_copper_partitions_preserved=True,
            source_candidate_and_code_unchanged=True)
    except Exception as exc:
        result['errors'].append(type(exc).__name__+':'+str(exc))
    result['elapsed_s'] = round(time.monotonic()-started,6)
    return result
