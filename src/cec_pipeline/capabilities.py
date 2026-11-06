"""The closed actuator catalog and mandatory receiving contracts.

Registering a shape does not grant authority: its constructor and independent
receiver must exist and tests require schema/catalog equality.
"""

from types import MappingProxyType

_PHYSICAL = ("current_pair", "kelvin_pair", "assembly_pair")
CAPABILITIES = MappingProxyType(
    {
        "replace_chain": (),
        "repair_chain": ("route_contract",),
        "place_cell": _PHYSICAL,
        "power_contour": ("assembly_pair",),
        "power_route": _PHYSICAL,
        "bank_collector": _PHYSICAL,
        "ground_plane_extension": _PHYSICAL,
        "outline_trim": _PHYSICAL,
        "add_connections": _PHYSICAL,
    }
)
MACROS = frozenset(CAPABILITIES) - {"replace_chain", "repair_chain"}
