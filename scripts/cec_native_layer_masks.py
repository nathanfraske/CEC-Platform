"""Detach SWIG-exposed const LSET caches before Python callers can mutate them.

KiCad's cached ``static const LSET&`` factories are mutable, borrowed proxies
in pcbnew. Adding F.Mask to AllCuMask() therefore changes the C++ singleton,
and the native parser subsequently rejects valid masked tracks as multi-copper
tracks. Copy at the Python binding boundary, not by repairing board files or
resetting an already poisoned native cache. An unhealthy worker must restart.

The profile uses named native layer constants, not board names or layer-number
arithmetic. Unsupported bindings and prior cache mutation fail closed. This
guard is separate from cec_swig_guard.pin(), whose never-raises API is retained.
"""
from __future__ import annotations

from functools import wraps


class NativeLayerMaskError(RuntimeError):
    """Native mask identity is unavailable, replaced, or already corrupted."""


_STATE = '_cec_detached_const_mask_factories'


def _profile(pcb):
    try:
        def layers(*names):
            return frozenset(int(getattr(pcb, name)) for name in names)
        copper = layers('F_Cu', 'B_Cu', *(f'In{i}_Cu' for i in
            range(1, int(pcb.MAX_CU_LAYERS)-1)))
        if (len(copper) != int(pcb.MAX_CU_LAYERS)
                or not all(pcb.IsCopperLayer(layer) for layer in copper)):
            raise ValueError('inconsistent_native_copper_enumeration')
        front = layers('F_SilkS', 'F_Mask', 'F_Adhes', 'F_Paste', 'F_CrtYd', 'F_Fab')
        back = layers('B_SilkS', 'B_Mask', 'B_Adhes', 'B_Paste', 'B_CrtYd', 'B_Fab')
        front_board = layers('F_SilkS', 'F_Mask', 'F_Adhes', 'F_Paste')
        back_board = layers('B_SilkS', 'B_Mask', 'B_Adhes', 'B_Paste')
        return dict(
            AllCuMask=copper,
            InternalCuMask=copper-layers('F_Cu', 'B_Cu'),
            ExternalCuMask=layers('F_Cu', 'B_Cu'),
            FrontAssembly=layers('F_SilkS', 'F_Mask', 'F_Fab', 'F_CrtYd'),
            BackAssembly=layers('B_SilkS', 'B_Mask', 'B_Fab', 'B_CrtYd'),
            AllLayersMask=frozenset(range(int(pcb.PCB_LAYER_ID_COUNT))),
            FrontTechMask=front, BackTechMask=back,
            FrontBoardTechMask=front_board, BackBoardTechMask=back_board,
            AllTechMask=front | back, AllBoardTechMask=front_board | back_board,
            FrontMask=front | layers('F_Cu'), BackMask=back | layers('B_Cu'),
            SideSpecificMask=front | back | copper,
            UserMask=layers('Dwgs_User', 'Cmts_User', 'Eco1_User', 'Eco2_User',
                'Edge_Cuts', 'Margin'),
            PhysicalLayersMask=front_board | back_board | copper)
    except (AttributeError, TypeError, ValueError) as exc:
        raise NativeLayerMaskError('unsupported_native_layer_mask_binding') from exc


def _check(name, factory, expected):
    try:
        actual = frozenset(map(int, factory().Seq()))
    except Exception as exc:
        raise NativeLayerMaskError('native_layer_mask_unavailable:'+name) from exc
    if actual != expected:
        raise NativeLayerMaskError('native_layer_mask_cache_corrupted:'+name+
            ':restart_worker;added='+str(sorted(actual-expected))+
            ';missing='+str(sorted(expected-actual)))


def _detached(cls, name, raw, expected):
    @wraps(raw)
    def factory(*args, **kwargs):
        # Also detect mutation through a previously captured raw factory. Never
        # return a cleaned-up copy while the native parser remains corrupted.
        _check(name, raw, expected)
        result = cls(raw(*args, **kwargs))
        if not result.thisown:
            raise NativeLayerMaskError('native_layer_mask_copy_not_owned:'+name)
        return result
    return factory


def install(pcb=None):
    """Install idempotent detached factories, checking native caches first.

    AllCuMask's native count overload is forwarded, not reimplemented. Existing
    value-returning factories remain untouched. No copper, pad, zone or board
    state is changed, and no installed KiCad files are edited.
    """
    if pcb is None:
        import pcbnew as pcb
    cls = pcb.LSET
    expected = _profile(pcb)
    state = getattr(cls, _STATE, None)
    if state is not None:
        if state['expected'] != expected:
            raise NativeLayerMaskError('native_layer_mask_profile_changed')
        for name, raw in state['originals'].items():
            if getattr(cls, name, None) is not state['wrappers'][name]:
                raise NativeLayerMaskError('native_layer_mask_factory_replaced:'+name)
            _check(name, raw, expected[name])
        return dict(installed=True, detached_factories=len(expected),
            native_caches_pristine=True)
    try:
        originals = {name: getattr(cls, name) for name in expected}
    except AttributeError as exc:
        raise NativeLayerMaskError('unsupported_native_layer_mask_factory') from exc
    # Validate everything before replacing anything. A failed install must not
    # mask a partial, poisoned native state or silently reset it.
    for name, raw in originals.items():
        _check(name, raw, expected[name])
    wrappers = {name: _detached(cls, name, raw, expected[name])
        for name, raw in originals.items()}
    for name, factory in wrappers.items():
        setattr(cls, name, staticmethod(factory))
    setattr(cls, _STATE, dict(expected=expected, originals=originals, wrappers=wrappers))
    return dict(installed=True, detached_factories=len(expected),
        native_caches_pristine=True)
