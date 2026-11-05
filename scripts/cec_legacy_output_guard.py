"""Prevent legacy/bootstrap writers from replacing current manifest sources."""
from pathlib import Path
import os


def require_safe_destination(destination, *, root):
    """Return a resolved non-current destination or refuse before any write.

    Resolve existing parent symlinks too. Protect whole current source project
    families, not just one basename; a changed extension/leaf name is not a
    bypass. This grants no permission to overwrite user files elsewhere.
    """
    from cec_beta_manifest import PROJECTS
    root = Path(root).resolve()
    target = Path(destination).resolve()
    target_key = os.path.normcase(str(target))
    for project in PROJECTS:
        family = (root / 'beta' / project['directory']).resolve()
        family_key = os.path.normcase(str(family))
        try:
            protected = os.path.commonpath([target_key, family_key]) == family_key
        except ValueError:  # Different Windows drive is outside this family.
            protected = False
        if protected:
            raise ValueError('legacy_bootstrap_current_manifest_output_forbidden: '
                             + project['board'] + ': ' + str(target))
    return target
