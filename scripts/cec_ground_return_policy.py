"""Keep capacitor portals distinct from source-declared owner returns.

The capacitor's later .8 mm portal rule is not a blanket override of the
ordinary synthesis contract for a manufacturer ground/power-return pin.
Neither rule grants process, current, routing or release authority.
"""
import inspect
import math


def owner_policy(board_hint):
    import cec_synth_pipeline as synth
    import cec_decoupler_cell as cell
    try:
        cfg=synth.Config.load(board_hint)
    except FileNotFoundError:
        # Unnamed/synthetic policy contexts retain the old conservative
        # bound; no inferred project or filename discovery can enlarge it.
        return dict(max_mm=.8,source='unresolved_source_no_extension',
            project_resolved=False,capacitor_portal_max_mm=.8)
    default=inspect.signature(cell.synthesize_ground_returns).parameters['ground_reach_mm'].default
    value=cfg.params.get('decoupler_ground_reach_mm',default)
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=1.5:
        raise ValueError('bounded_source_owner_ground_return_policy_required')
    return dict(max_mm=float(value),source='canonical_synthesis_ground_return_contract',
        board_key=cfg.board_key,project=cfg.dir,
        parameter='decoupler_ground_reach_mm',explicit_parameter='decoupler_ground_reach_mm' in cfg.params,
        default_from='cec_decoupler_cell.synthesize_ground_returns.ground_reach_mm',
        project_resolved=True,capacitor_portal_max_mm=.8,
        current_authority=False,release_authority=False)


def reach(pad,entries,*,portal_max_mm=.8):
    """Only a freshly source-assigned typed low-power owner may extend reach.

    Callers independently recompile ``entries`` from source ownership; a
    worker-authored entry is never a saved receiving proof.
    """
    import cec_force_current as force
    import cec_device_power_roles as roles
    if type(portal_max_mm) not in (int,float) or not math.isfinite(portal_max_mm) or not 0<portal_max_mm<=.8:
        raise ValueError('bounded_unchanged_capacitor_portal_policy_required')
    entry=entries.get(force._uid(pad))
    if entry is None:return float(portal_max_mm)
    fp=pad.GetParentFootprint();model=roles.footprint_contract(fp)
    if (not model or model['pins'].get(pad.GetNumber()) not in ('ground','power_return')
            or pad.GetNetname()!='GND' or entry.get('selected_owner')!=fp.GetReference()
            or entry.get('owner_ground_pad_uuid')!=force._uid(pad)
            or any(role in ('power_output','switch','feedback')for role in model['pins'].values())):
        return float(portal_max_mm)
    policy=entry.get('source_owner_return_policy') or {}
    value=policy.get('max_mm')
    if type(value) not in (int,float) or not math.isfinite(value) or not 0<value<=1.5:
        raise ValueError('source_bound_owner_ground_return_policy_missing')
    return float(value)
