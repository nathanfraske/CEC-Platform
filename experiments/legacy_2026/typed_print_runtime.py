"""Compatibility facade for the shared native runtime owner.

Private helpers and the live fence registry intentionally retain identity.
"""
import cec_native_runtime as _shared_runtime

globals().update({name: value for name, value in vars(_shared_runtime).items()
    if not (name.startswith("__") and name.endswith("__"))})
