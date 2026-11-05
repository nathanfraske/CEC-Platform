"""Explicit planar reconstruction sizing from unchanged full-current authority.

A legacy/netclass preferred width is not an ampacity requirement. A caller may
request a smaller small-supply stroke only after positive current-domain and
native process-floor binding. The source load, margin, copper, thermal rise,
layer and ports do not change. Independent saved DRC, current-path, field and
whole-source connectivity receiving remain mandatory. Main buses and critical
measurement/pair/ground copper are outside this bounded work tier.
"""
import math
import cec_force_current as force
import cec_redundant_force_branch as authority
import cec_fr as fr
import cec_fab_profile as fab
import cec_route_dimensions as dimensions
import cec_pair_semantics as pairs


def plan(board,source,row,*,board_hint,width_nm):
    if (type(width_nm) is not int or not 0<width_nm<=1000000 or type(row) is not dict
            or type(row.get('uid')) is not str or type(row.get('layer')) is not int
            or type(row.get('width')) is not int or not width_nm<row['width']<=1000000):
        raise ValueError('explicit_bounded_smaller_native_supply_stroke_required')
    net=row.get('net');live={force._uid(t):t for t in board.GetTracks()};item=live.get(row['uid'])
    if (item is None or item.GetClass()!='PCB_TRACK' or item.GetNetname()!=net
            or item.GetLayer()!=row['layer'] or item.GetWidth()!=row['width']
            or item.GetParentGroup() is not None or any(g.ContainsItem(item) for g in board.Groups())
            or item.GetLayer() not in (0,2)):
        raise ValueError('exact_source_owned_ungrouped_outer_power_stroke_required')
    protected={n for p in fr._board_kelvin_pairs(board) for n in p}
    protected.update(n for _,p,q in pairs.coupled_pair_names(board) for n in (p,q))
    protected.update(r[k] for r in pairs.analog_input_pairs(board) for k in ('p','n'))
    protected.update(pairs.unresolved_current_monitor_nets(board))
    planes={board.GetLayerID(n) for n in fr.plane_layers(board)}
    protected.update(str(z.GetNetname()) for z in board.Zones() if z.GetLayer() in planes)
    if not net or net.rsplit('/',1)[-1].upper().startswith('GND') or net in protected:
        raise ValueError('ground_precision_pair_or_reference_copper_is_not_small_supply_scope')
    domain,contract=authority._model(board,net,board_hint)
    face=fab.COPPER_LAYER_IDS[row['layer']]
    required=contract.get('required_by_layer_mm',{}).get(face)
    limits=dimensions.board_limits(board);minimum=limits['track_width']
    if (type(required) not in (int,float) or not math.isfinite(required) or not 0<required<=1
            or not math.isfinite(minimum) or not 0<minimum<=1
            or face not in contract.get('routing_layers',())):
        raise ValueError('complete_finite_small_supply_current_and_native_process_floors_required')
    floor=max(math.ceil(required*1e6),math.ceil(minimum*1e6))
    if width_nm<floor:raise ValueError('literal_supply_width_below_unchanged_current_or_process_floor')
    spec=fr._project_netclass_resolver(str(source))(net) or {}
    return dict(schema=1,source_track_uuid=row['uid'],net=net,layer=row['layer'],
        source_width_nm=row['width'],replacement_width_nm=width_nm,
        current_floor_nm=math.ceil(required*1e6),native_board_minimum_nm=math.ceil(minimum*1e6),
        preferred_netclass_width_mm=spec.get('track_width'),unchanged_current_domain=domain,
        unchanged_whole_source_contract=contract,source_current_or_margin_or_copper_reduced=False,
        new_barrels=0,all_native_custom_rules_and_whole_source_receiving_still_required=True,
        current_qualified=False,routing_admitted=False,release_authority=False)
