"""Pin SWIG's runtime type registry for the life of a pcbnew process.

THE DEFECT THIS CLOSES (root-caused 2026-07-25 from the hub's all-9999 wall).
Every hub-standard-rev2 wave variant since the ingress merge failed with::

    route failed: 'SwigPyObject' object has no attribute 'GetLayerID'

and the failure was read for two days as *placement seat pressure* (the +12
ingress parts refusing at the courtyard gate). It is not. Placement completes;
the ROUTE stage dies, and it dies for a reason that has nothing to do with the
board: mid-run, ``pcbnew.LoadBoard()`` stops returning a ``BOARD`` and starts
returning a bare ``SwigPyObject``. Measured, in order:

  * fresh ``LoadBoard`` of the same hub board in a clean process -> ``BOARD``
    (so it is process STATE, not board content);
  * the flip is sticky and global -- after it, ``BOX2I`` returns from
    ``GetBoardEdgesBoundingBox()`` are bare proxies too;
  * re-attaching a proxy by hand (``BOARD.__new__`` + ``.this``) reads correct
    footprint/net/layer data, so the C++ heap is INTACT;
  * no import fires at the flip, and the box has no memory limit (167 GB free
    at a 220 MB RSS) -- both hypotheses ablated, not assumed.

That combination is one specific SWIG mechanism. SWIG keeps its type table in a
capsule at ``sys.modules['swig_runtime_data4'].type_pointer_capsule``; the
capsule's destructor is ``SWIG_Python_DestroyModule``, which walks every
registered type and frees its ``clientdata`` -- the pointer that tells SWIG
which Python proxy class to build for a returned C++ pointer. With clientdata
gone, ``SWIG_Python_NewPointerObj`` has no class to instantiate and hands back
the raw ``SwigPyObject``. Permanently, for every type, in that process.

PROVEN BY ABLATION: holding one reference to that capsule for the run makes the
identical hub grade route to completion (``error=None``, structural DRC 8) where
it had produced 9999 on every seed. Pinning is the whole fix.

WHO DROPS THE CAPSULE IS STILL UNIDENTIFIED, and the observation is
self-defeating: a watcher that holds the capsule to compare its identity IS a
pin, so the run it was meant to observe completes normally (measured -- a
capsule-watching probe returned ``fired=False``, ``error=None``, DRC 11, a third
accidental confirmation of the fix). Identifying the dropper needs an
observer that does not hold a strong reference. That is worth doing only if a
related symptom reappears; the pin makes the failure unreachable regardless of
who the dropper is, which is why it is the fix rather than the workaround.

WHY A PIN RATHER THAN CHASING THE DROPPER: the capsule is a process-global the
interpreter owns; anything that replaces the ``type_pointer_capsule`` attribute
(a second SWIG-runtime extension initialising) or drops the synthetic module
takes pcbnew's bindings down with it, from outside our code. Holding a reference
is the standard, side-effect-free immunisation: the registry simply cannot be
torn down while a live reference exists, so the failure mode is unreachable no
matter who tries. It costs one pointer and cannot change behaviour on a healthy
process (the same objects, the same registry -- only the teardown path is
removed).

WHERE IT IS WIRED: there is no single import choke point (58 scripts import
pcbnew; only 7 share any common helper -- measured, not assumed), so the pin is
called explicitly beneath the ``import pcbnew`` of the four modules that import
pcbnew AT MODULE LEVEL and own the long multi-stage sessions: ``cec_fr`` (the
route engine, where the teardown was measured), ``cec_precision_route``, and the
pour engines ``cec_slab_pour`` / ``cec_pour_plan``. Everything above them --
``cec_router``, ``cec_synth_pipeline``, ``cec_placement_session``,
``cec_fresh_wave``, ``cec_staged_fr`` -- imports pcbnew lazily inside functions
and inherits the pin through those four, which are always imported before any
route or pour runs.

Placement matters: pinning is only effective once a SWIG runtime exists, so the
call must sit AFTER an ``import pcbnew``, not at the top of a module that imports
pcbnew lazily. ``pin()`` re-scans whenever nothing is pinned yet, so an early
no-op call never blocks a later real one. A new module that opens a long pcbnew
session should add the same two lines under its own pcbnew import.

Idempotent and fail-safe by construction: on a build with no SWIG runtime module
yet (or a future SWIG whose layout differs) it pins nothing and reports False --
it never raises into a caller's import.
"""

import sys

# Module-level so the references live exactly as long as the interpreter.
_PINNED: list = []

# SWIG's synthetic registry module is versioned by SWIG_RUNTIME_VERSION ("4"
# today). Match by prefix so a runtime bump keeps working.
_RUNTIME_PREFIX = "swig_runtime_data"
_CAPSULE_ATTR = "type_pointer_capsule"


def pin() -> bool:
    """Hold a reference to every live SWIG runtime type-table capsule.

    Returns True if at least one capsule is pinned (now or from a previous
    call). Safe to call any number of times, from any module, at any point --
    but it must run BEFORE the capsule would be dropped, so callers import this
    right after ``import pcbnew``.
    """
    try:
        mods = [m for name, m in list(sys.modules.items())
                if name.startswith(_RUNTIME_PREFIX) and m is not None]
        for m in mods:
            cap = getattr(m, _CAPSULE_ATTR, None)
            # A later-loaded SWIG extension may replace the runtime module's
            # capsule after an earlier caller pinned the old one. Re-scan on
            # every call and retain every distinct current object; returning
            # early merely made the guard report success while the active type
            # table remained destructible.
            if cap is not None and not any(cap is obj for obj in _PINNED):
                _PINNED.append(cap)
            # Hold the module too: the capsule is reachable only through it, and
            # a dropped sys.modules entry would take the capsule with it.
            if not any(m is obj for obj in _PINNED):
                _PINNED.append(m)
    except Exception:                                      # noqa: BLE001
        return False
    return bool(_PINNED)


def pinned() -> int:
    """How many objects are pinned (0 = registry not found / not pinned yet)."""
    return len(_PINNED)


# Pin on import: any module that has already imported pcbnew gets the guarantee
# by adding `import cec_swig_guard` beneath its pcbnew import.
pin()
