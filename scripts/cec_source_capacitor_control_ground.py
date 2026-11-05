"""Fresh Source ownership of a shared input-capacitor/control Ground island.

This is deliberately NOT low-power classification. Only ceramic shunts to
an actual manufacturer power-input rail may accompany canonical control
shunts. Every pad and retained stroke is accounted for. Full Source Ground
class, original current/plane/return/field/native gates remain mandatory;
no capacitor ripple, ampacity, barrel or fabrication rating is inferred.
"""
from pathlib import Path
from collections import Counter
import time
import pcbnew
import cec_decoupler_cell as cells
import cec_device_power_roles as roles
import cec_force_current as force
import cec_full_current_supply_prefix as supply
import cec_source_ground_leaf as leaf
import cec_source_netlist_semantics as semantics
import cec_source_no_connect as source_nc
from cec_source_divider_ground_span import _pins


def _tick(deadline):
    if time.monotonic() >= deadline:
        raise ValueError('coowned_capacitor_control_ground_source_deadline')


def derive(board, hint, source, snapshot, ground, live, root_component, deadline):
    """Consume this invocation's actual export; never a serialized proof."""
    _tick(deadline)
    if source.get('complete') is not True or source.get('errors') or not snapshot:
        raise ValueError('fresh_complete_coowned_ground_source_required')
    root = source_nc._root(board, hint).resolve()
    if (type(snapshot) is not tuple or len(snapshot) != 3
            or snapshot[0] != str(root)):
        raise ValueError('coowned_ground_actual_export_root_required')
    tree, exporter = snapshot[1:]
    metadata = semantics.metadata(tree)
    if any(exporter.get(key) != value for key, value in metadata.items()):
        raise ValueError('coowned_ground_complete_export_semantics_required')
    if (Path(exporter.get('exporter', '')).resolve().is_file() is not True
            or force._hash(exporter['exporter']) != exporter.get('exporter_sha256')):
        raise ValueError('coowned_ground_live_exporter_required')
    files, hashes, instances = leaf._hierarchy(root, deadline)
    comps, nets, node_net = leaf._tables(tree)
    controls = {uid: proof for uid, proof in source['proofs'].items()
                if proof.get('kind') == 'source_control_shunt_ground'}
    if any(proof.get('root_schematic') != str(root)
           or proof.get('schematic_files_sha256') != hashes
           or proof.get('exporter') != exporter for proof in controls.values()):
        raise ValueError('coowned_ground_fresh_control_binding_required')
    native = {}
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            native.setdefault((fp.GetReference(), str(pad.GetNumber())), []).append(pad)
    identities, pinmaps = {}, {}

    def identity(fp):
        uid = force._uid(fp)
        if uid not in identities:
            value = leaf._identity(board, fp.GetReference(), comps, instances, deadline)
            pins = _pins(value)
            for pad in fp.Pads():
                pin = str(pad.GetNumber())
                selected = [p for p in value[3]['pins'] if p['num'] == pin]
                if len(selected) != 1 or selected[0]['type'] != pins[pin][0]:
                    raise ValueError('coowned_ground_actual_source_pin_type_required')
                # KiCad exports an intentionally unused pin as a singleton
                # unconnected net too. Its NC marker is valid, but grants no
                # witness authority. Never excuse an NC on a shared net.
                is_nc = any(source_nc._nm(p['pos']) == source_nc._nm(selected[0]['pos'])
                    for p in value[2].no_connects)
                if is_nc:
                    peers = nets.get(pad.GetNetname(), set())
                    if peers - {(fp.GetReference(), pin)}:
                        raise ValueError('coowned_ground_NC_conflicts_with_shared_source_net')
                elif pad.GetNetCode() > 0:
                    leaf._pin(value, pin)
                if node_net.get((fp.GetReference(), pin), '') != pad.GetNetname():
                    raise ValueError('coowned_ground_complete_native_pin_net_map_required')
                if (pad.GetPinType() and pad.GetPinType() != pins[pin][0]
                        or pad.GetPinFunction() and pad.GetPinFunction() != pins[pin][1]):
                    raise ValueError('coowned_ground_native_pin_metadata_contradiction')
            identities[uid], pinmaps[uid] = value, pins
        return identities[uid], pinmaps[uid]

    cap_cache = {}

    def input_capacitor(pad):
        fp = pad.GetParentFootprint()
        uid = force._uid(fp)
        if uid in cap_cache:
            return cap_cache[uid]
        if not leaf._ceramic(fp):
            return None
        pads = list(fp.Pads())
        if len([p for p in pads if p.GetNetname() == 'GND']) != 1:
            return None
        other = next(p for p in pads if force._uid(p) != force._uid(pad))
        if (other.GetNetCode() <= 0 or other.GetNetname() == 'GND'
                or supply.supply_terminal_role(other)
                != 'value_qualified_grounded_ceramic_supply_terminal'):
            return None
        selected, pins = identity(fp)
        for terminal in pads:
            leaf._pin(selected, terminal.GetNumber())
        if set(pins) != {p.GetNumber() for p in pads} or any(v[0] != 'passive' for v in pins.values()):
            raise ValueError('coowned_ground_source_capacitor_passive_both_pins_required')
        net = str(other.GetNetname())
        expected = nets.get(net, set())
        actual = {key for key, values in native.items() if any(p.GetNetname() == net for p in values)}
        if (not expected or expected != actual
                or any(len(native[key]) != 1 or native[key][0].GetNetname() != net for key in actual)):
            raise ValueError('coowned_ground_complete_source_input_rail_membership_required')
        witnesses = []
        for ref, number in sorted(expected):
            _tick(deadline)
            peer = native[(ref, number)][0]
            owner = peer.GetParentFootprint()
            model = roles.footprint_contract(owner)
            if not model or model['pins'].get(number) != 'power_input':
                continue
            owner_identity, owner_pins = identity(owner)
            leaf._pin(owner_identity, number)
            if set(model['pins']) != set(owner_pins) or owner_pins[number][0] != 'power_in':
                raise ValueError('coowned_ground_complete_manufacturer_input_pin_map_required')
            grounds = [p for p in owner.Pads() if model['pins'].get(p.GetNumber()) in ('ground', 'power_return')]
            if not grounds or any(p.GetNetname() != 'GND' for p in grounds):
                raise ValueError('coowned_ground_manufacturer_input_return_net_required')
            for terminal in grounds:
                leaf._pin(owner_identity, terminal.GetNumber())
            witnesses.append(dict(owner_uuid=force._uid(owner), pad_uuid=force._uid(peer),
                source_symbol_uuid=owner_identity[3]['uuid'], pin=number,
                source_pin_type=owner_pins[number][0], manufacturer=model))
        if not witnesses:
            return None
        result = dict(kind='source_input_rail_ceramic_ground', pad_uuid=force._uid(pad),
            supply_pad_uuid=force._uid(other), source_symbol_uuid=selected[3]['uuid'],
            rail=net, complete_rail_nodes=[list(key) for key in sorted(expected)],
            manufacturer_input_witnesses=witnesses, current_authority=False,
            bypass_assignment_inferred=False, ripple_current_qualified=False, release_authority=False)
        cap_cache[uid] = result
        return result

    spec = cells._netclass(board, 'GND')
    floor = max(200000, int(board.GetDesignSettings().m_TrackMinWidth), int(spec['width']))
    cohorts = []
    for part in ground:
        _tick(deadline)
        if part == root_component or not 2 <= len(part) <= 32:
            continue
        objects = [live[key] for key in part]
        if any(item.GetClass() not in ('PAD', 'PCB_TRACK') for item in objects):
            continue
        if any(item.GetClass() == 'PCB_TRACK' and (item.GetWidth() < floor
               or item.GetLayer() not in (pcbnew.F_Cu, pcbnew.B_Cu)) for item in objects):
            continue
        pads = [item for item in objects if item.GetClass() == 'PAD']
        if not any(force._uid(pad) in controls for pad in pads):
            continue
        control_proofs, input_proofs = [], []
        valid = 2 <= len(pads) <= 12
        for pad in pads:
            uid = force._uid(pad)
            if (pad.GetNetname() != 'GND' or pad.HasHole()
                    or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD
                    or pad.GetParentFootprint().IsDNP()):
                valid = False
                break
            if uid in controls:
                control_proofs.append(controls[uid])
            else:
                proof = input_capacitor(pad)
                if proof is None:
                    valid = False
                    break
                input_proofs.append(proof)
        if valid and 1 <= len(control_proofs) <= 4 and 1 <= len(input_proofs) <= 8:
            cohorts.append(dict(component=part, proof=dict(
                kind='source_coowned_input_capacitor_and_control_ground_island',
                native_contact_keys=[list(key) for key in sorted(part)],
                control_ground_proofs=control_proofs, input_capacitor_ground_proofs=input_proofs,
                unchanged_source_ground_class_floor_nm=floor,
                source_schematic_files_sha256=hashes, exporter=exporter,
                class_only=True, low_power_classification=False,
                aggregate_ground_current_inferred=False, ampacity_qualified=False,
                immediate_return_qualified=False, release_authority=False)))
    _tick(deadline)
    if hashes != {str(path): force._hash(path) for path in files}:
        raise ValueError('coowned_ground_source_hierarchy_changed')
    return cohorts


def bindings_current(proofs):
    if type(proofs) is not list or not 1 <= len(proofs) <= 64:
        return False
    for proof in proofs:
        if proof.get('kind') != 'source_coowned_input_capacitor_and_control_ground_island':
            return False
        files, exporter = proof['source_schematic_files_sha256'], proof['exporter']
        if (any(force._hash(path) != digest for path, digest in files.items())
                or force._hash(exporter['exporter']) != exporter['exporter_sha256']):
            return False
    return True


def receive_chain(tracks, component, root_component, live, deadline):
    """Every new surface stroke belongs to one actual two-terminal chain."""
    if not 1 <= len(tracks) <= 128 or any(t.GetClass() != 'PCB_TRACK' for t in tracks):
        raise ValueError('coowned_ground_surface_chain_required')
    faces = {int(t.GetLayer()) for t in tracks}
    if len(faces) != 1:
        raise ValueError('coowned_ground_single_surface_chain_required')
    face = next(iter(faces));degree = Counter();adjacency = {}
    for track in tracks:
        _tick(deadline)
        a,b=tuple(track.GetStart()),tuple(track.GetEnd())
        if a == b:raise ValueError('coowned_ground_nonzero_chain_stroke_required')
        degree.update((a,b));adjacency.setdefault(a,set()).add(b);adjacency.setdefault(b,set()).add(a)
    ends = [point for point,count in degree.items() if count == 1]
    if len(ends) != 2 or any(count not in (1,2) for count in degree.values()):
        raise ValueError('coowned_ground_no_extra_spur_or_branch_allowed')
    reached=set();queue=[ends[0]]
    while queue:
        _tick(deadline);point=queue.pop()
        if point in reached:continue
        reached.add(point);queue.extend(adjacency[point]-reached)
    if reached != set(degree):raise ValueError('coowned_ground_one_complete_chain_required')
    def contact(point, keys):
        pos=pcbnew.VECTOR2I(*point)
        return any(live[key].IsOnLayer(face) and live[key].GetEffectiveShape(face).Collide(pos,0)
                   for key in keys)
    if not ((contact(ends[0],component) and contact(ends[1],root_component))
            or (contact(ends[1],component) and contact(ends[0],root_component))):
        raise ValueError('coowned_ground_both_real_Source_chain_contacts_required')
    return dict(complete=True,added_track_uuids=sorted(force._uid(t)for t in tracks),
        chain_endpoints_nm=[list(point)for point in sorted(ends)],
        one_chain=True,no_added_spurs_or_branches=True,actual_old_cohort_and_reference_contacts=True,
        current_qualified=False,release_authority=False)
