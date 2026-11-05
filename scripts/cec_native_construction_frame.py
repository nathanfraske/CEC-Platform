"""Exact private unfinished IR, NEVER saved-board or ownership receiving.

Loading an intentionally unfinished frame can infer a floating via's net
from stale generated copper. Preserve authored intent only on an isolated
construction copy, with exact full native serialization and live inventory
equality. This does not repair a saved child: final saved snapshots remain
strict and must pass after actual refill/routing. No tolerant comparison,
new net, caller proof, cut authority or clearance waiver is accepted here.
"""
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import tempfile
import time

import pcbnew
import cec_copper_echo as syntax
import cec_field_coupling as field
import cec_return_plane_preview as authors


def _tick(deadline):
    if time.monotonic()>=deadline:raise ValueError('construction_frame_deadline')


def _table(board):
    # KiCad's RAM netcode integers are allocator indices, not persisted
    # identities: native reload can reorder them while every literal native
    # declaration is identical. Require the entire exact named net table.
    return sorted(str(name)for name in board.GetNetsByName())


def _authored(board):
    return {uid:row[:2]for uid,row in authors._authorship(board).items()}


def _text(board,deadline):
    _tick(deadline)
    if (len(list(board.GetTracks()))>8192 or len(list(board.GetFootprints()))>4096
            or sum(len(list(f.Pads()))for f in board.GetFootprints())>16384
            or len(list(board.Zones()))>256):
        raise ValueError('construction_frame_inventory_bound')
    output=pcbnew.STRING_FORMATTER()
    pcbnew.PCB_IO_KICAD_SEXPR().FormatBoardToFormatter(output,board)
    raw=output.GetString()
    if len(raw.encode())>32*1024*1024:raise ValueError('construction_frame_serialization_bound')
    _tick(deadline)
    return raw


def _identity(board,deadline):
    return (_text(board,deadline),field._field_snapshot_inventory(board),
        _authored(board),_table(board),str(board.GetFileName()))


def binding(board,deadline):
    """Full live IR identity only; does NOT claim saved/reload equivalence."""
    raw,inventory,authored,table,name=_identity(board,deadline)
    material=[raw,sorted(inventory.items()),sorted(authored.items()),table,name]
    result=hashlib.sha256(json.dumps(material,sort_keys=True,allow_nan=False).encode()).hexdigest()
    _tick(deadline)
    return result


def nodes(board,deadline):
    """Read native live IR without pretending its stale fills are savable."""
    raw=_text(board,deadline);root=syntax._parse(syntax._TOKEN.findall(raw));by_id={}
    for node in root[1:]:
        if not isinstance(node,list):continue
        uid=next((r[1].strip('"')for r in node[1:]if isinstance(r,list)
            and len(r)==2 and r[0]=='uuid'),None)
        if uid:
            if uid in by_id:raise ValueError('construction_frame_ambiguous_native_identity')
            by_id[uid]=node
    _tick(deadline)
    return root,by_id


@contextmanager
def zone_snapshot(board,deadline):
    """Ephemeral exact zone input ONLY for existing frozen-zone comparison.

    Frozen search independently matches every actual zone and returns no
    saved-board validity. Its guards always inspect the original live frame,
    not loader-inferred conductors in this temporary non-candidate file.
    """
    before=_identity(board,deadline)
    with tempfile.TemporaryDirectory(prefix='cec-construction-zones-')as work:
        path=Path(work)/'NOT-A-CANDIDATE.kicad_pcb'
        try:
            pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(path),board)
        finally:
            board.SetFileName(before[-1])
            if _identity(board,deadline)!=before:
                raise ValueError('construction_frame_changed_caller')
        if syntax._freeze(syntax._parse(syntax._TOKEN.findall(path.read_text())))!=syntax._freeze(
                syntax._parse(syntax._TOKEN.findall(before[0]))):
            raise ValueError('construction_frame_writer_changed_native_definition')
        # The enclosing frozen-zone context owns zone immutability while
        # searching. Ordinary route construction inside that context may add
        # tracks; this snapshot writer does not grant a whole-board edit lock.
        yield path


def clone(board,deadline):
    """Private exact copy; only known native net inference may be undone.

    Restore solely matching UUID/classes to names already in the exact net
    table. Then compare ALL native serialized properties, copper, metadata,
    locks, groups, masks and live authorship. No missing net may be created.
    """
    before=_identity(board,deadline)
    try:
      with zone_snapshot(board,deadline)as path:
        copied=pcbnew.LoadBoard(str(path));_tick(deadline)
        if copied is None or _table(copied)!=before[3]:
            raise ValueError('construction_frame_net_table_changed')
        items=authors._net_items(copied);authored=before[2]
        if items.keys()!=authored.keys()or any(items[u].GetClass()!=r[0]for u,r in authored.items()):
            raise ValueError('construction_frame_primitive_identity_changed')
        for uid,(_,name)in authored.items():
            _tick(deadline);item=items[uid]
            if str(item.GetNetname())==name:continue
            target=copied.FindNet(name)
            if target is None:raise ValueError('construction_frame_existing_authored_net_required')
            item.SetNet(target)
        project=board.GetProject()
        if project is not None:copied.SetProject(project,True)
        copied.SetDesignSettings(board.GetDesignSettings())
        for name,net in board.GetNetsByName().items():
            target=copied.FindNet(str(name))
            if target is None:raise ValueError('construction_frame_existing_net_context_required')
            target.SetNetClass(net.GetNetClassSlow())
        copied.SetFileName(before[-1])
        if _identity(copied,deadline)!=before:
            raise ValueError('construction_frame_clone_changed_native_definition')
    finally:
        if _identity(board,deadline)!=before:
            raise ValueError('construction_frame_changed_caller')
    return copied
