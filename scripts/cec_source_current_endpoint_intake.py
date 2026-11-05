"""Early source/native endpoint identity gate, not current-path qualification."""
from copy import deepcopy
import os


def check(board, board_hint):
    """Bind explicit terminal declarations to unchanged ratified source current.

    No declarations is neutral and inspects neither native objects nor current
    providers. A nonempty policy must bind actual selected MPN/FPID and every
    actual on-net pin through the existing binder, including legacy conflict
    checks. No routing, connectivity, thermal, sharing or fab approval follows.
    """
    import cec_board_policy as policy
    import cec_current_topology as topology
    import cec_declared_current_endpoints as endpoints

    base = dict(ok=False, scope='declared_current_endpoint_source_identity',
        current_path_qualified=False, thermal_qualified=False,
        physical_release=False, new_current_or_margin_inferred=False)
    try:
        declarations = policy.params(board_hint).get('current_endpoint_contracts', [])
        if declarations == []:
            return dict(base, ok=True, neutral=True, declaration_count=0,
                        bound_nets=[], witnesses={})
        override = os.environ.get('CEC_THERMAL_BOARD_HINT')
        if override and policy.policy_path(override) != policy.policy_path(board_hint):
            raise ValueError('declared_current_endpoint_policy_identity_conflict')
        # board_current_domains uses the existing binder against the original
        # source provider and refuses conflicts with older domain authority.
        domains = topology.board_current_domains(board, board_hint=board_hint)
        bound = endpoints.bind(board, declarations,
            lambda net: topology.current_contract_for_net(
                net, board_hint, domains), existing=domains)
        return dict(base, ok=True, neutral=False,
            declaration_count=len(declarations), bound_nets=sorted(bound),
            witnesses={net: deepcopy(row['declared_endpoint_witness'])
                       for net, row in sorted(bound.items())})
    except Exception as exc:  # Malformed/unknown authority never becomes neutral.
        return dict(base, neutral=False, error_type=type(exc).__name__,
                    reason=str(exc), bound_nets=[], witnesses={})
