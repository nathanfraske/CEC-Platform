"""Preserve an explicit resumed board's executable project-rule authority.

Some native clone/save paths write a Default-only project after rule carriage.
Capture before that work and restore only the exact authorized source policy
at the publication boundary. This is not a donor-ranking or rule-edit API.
"""
from pathlib import Path
import hashlib
import json

EXTENSIONS=('.kicad_pro','.kicad_dru')


def capture(board, *, fallback_board=None):
    source=Path(board).resolve()
    files={extension:(source.with_suffix(extension).read_bytes()
                      if source.with_suffix(extension).is_file() else None)
           for extension in EXTENSIONS}
    # A newly saved, copper-free native board may have only KiCad's Default
    # project shell. Fresh placement explicitly permits resolving that shell
    # from its configured source. Routed/frozen callers never pass this option.
    # Named classes, bindings, custom rules or malformed projects are explicit
    # authority and must not be replaced by a richer guessed donor.
    owners={extension:source.with_suffix(extension) for extension in EXTENSIONS}
    if fallback_board and files['.kicad_dru'] is None:
        try:
            project=json.loads(files['.kicad_pro']) if files['.kicad_pro'] else {}
            settings=project.get('net_settings') or {}
            unbound=(not settings.get('netclass_patterns')
                and not settings.get('netclass_assignments')
                and all(row.get('name')=='Default'
                        for row in settings.get('classes') or ()))
        except (ValueError,TypeError,AttributeError):
            unbound=False
        fallback=Path(fallback_board).resolve()
        if unbound and fallback!=source and fallback.with_suffix('.kicad_pro').is_file():
            result=capture(fallback)
            return dict(result,resolution='explicit-config-for-fresh-native-shell',
                        geometry_source=source)
        # Native SaveBoard can retain the full project's netclasses yet omit
        # its sibling custom-rule file. A fresh placement may carry precisely
        # that missing file from its explicit config, never from ranked donors.
        # Existing source custom rules still win byte-for-byte.
        custom=fallback.with_suffix('.kicad_dru')
        if custom.is_file():
            files['.kicad_dru']=custom.read_bytes()
            owners['.kicad_dru']=custom
    return dict(source=source,files=files,owners=owners)


def restore(snapshot,board):
    """Refuse a changed source; publish the captured files byte-for-byte."""
    files=snapshot['files'];source=snapshot['source'];target=Path(board)
    if all(value is None for value in files.values()):
        return dict(applicable=False,ok=True)
    for extension,value in files.items():
        path=snapshot.get('owners',{}).get(extension,source.with_suffix(extension))
        actual=path.read_bytes() if path.is_file() else None
        if actual!=value:
            raise ValueError('source project rule authority changed during materialization: %s'%path)
        if value is None and target.with_suffix(extension).is_file():
            raise ValueError('unowned project rule file introduced: %s'%extension)
    hashes={}
    for extension,value in files.items():
        if value is None:continue
        path=target.with_suffix(extension)
        owner=snapshot.get('owners',{}).get(extension,source.with_suffix(extension))
        if path.resolve()!=owner:
            path.write_bytes(value)
        if path.read_bytes()!=value:
            raise ValueError('materialized project rule authority changed at publication')
        hashes[extension]=hashlib.sha256(value).hexdigest()
    return dict(applicable=True,ok=True,sha256=hashes)
