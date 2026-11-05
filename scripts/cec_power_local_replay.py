"""Exact item-scoped transfer of package-local copper into frozen power.

A planner's dependency is its emitted copper, not a promise to rediscover an
equivalent route later. Geometry, net names, locks and local fabrication groups
travel together. Replay never waives native DRC, current, or connectivity gates.
"""
import hashlib
import json


def _digest(rows):
    return hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def _geometry(board,item):
    row=dict(kind=item.GetClass(),net=str(item.GetNetname()),locked=bool(item.IsLocked()))
    if row['kind']=='PCB_TRACK':
        row.update(start=[item.GetStart().x,item.GetStart().y],
                   end=[item.GetEnd().x,item.GetEnd().y],width=item.GetWidth(),
                   layer=board.GetLayerName(item.GetLayer()))
    elif row['kind']=='PCB_VIA':
        row.update(at=[item.GetPosition().x,item.GetPosition().y],
            width=item.GetWidth(item.TopLayer()),drill=item.GetDrillValue(),
            layers=[board.GetLayerName(item.TopLayer()),board.GetLayerName(item.BottomLayer())],
            via_type=int(item.GetViaType()))
    else:
        raise ValueError('unsupported local power copper primitive')
    return row


def _terminals(board,nets):
    return sorted((fp.GetReference(),p.GetNumber(),p.GetNetname(),
                   p.GetPosition().x,p.GetPosition().y,p.GetSize().x,p.GetSize().y,
                   p.GetOrientationDegrees(),tuple(p.GetLayerSet().CuStack()))
                  for fp in board.GetFootprints() for p in fp.Pads()
                  if p.GetNetname() in nets)


def _attached_refs(board, items):
    """Bind actual copper contacts, not every consumer of a shared rail."""
    refs=set()
    shapes=[(str(i.GetNetname()),{layer:i.GetEffectiveShape(layer)
            for layer in i.GetLayerSet().CuStack()}) for i in items]
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            for net,layers in shapes:
                if str(pad.GetNetname())==net and any(
                        layer in layers and pad.GetEffectiveShape(layer).Collide(layers[layer],0)
                        for layer in pad.GetLayerSet().CuStack()):
                    refs.add(str(fp.GetReference()))
    return sorted(refs)


def _scoped_terminals(board,refs):
    selected=set(refs)
    rows=[]
    for fp in board.GetFootprints():
        if fp.GetReference() not in selected:continue
        pads=[]
        for p in fp.Pads():
            pads.append((p.GetNumber(),p.GetNetname(),p.GetPosition().x,p.GetPosition().y,
                p.GetSize().x,p.GetSize().y,p.GetOrientationDegrees(),
                tuple(p.GetLayerSet().CuStack()),int(p.GetShape()),int(p.GetAttribute()),
                p.GetDrillSize().x,p.GetDrillSize().y,int(p.GetDrillShape()),
                p.GetOffset().x,p.GetOffset().y,p.GetDelta().x,p.GetDelta().y,
                p.GetRoundRectRadiusRatio(),p.GetChamferRectRatio(),int(p.GetChamferPositions())))
        rows.append((fp.GetReference(),fp.GetFPID().GetUniStringLibId(),
                     bool(fp.IsFlipped()),sorted(pads)))
    if {r[0] for r in rows}!=selected or len(rows)!=len(selected):
        raise ValueError('local power terminal identity missing or ambiguous')
    return sorted(rows)


def capture(board,uuids):
    requested=set(uuids)
    found={i.m_Uuid.AsString():i for i in board.GetTracks() if i.m_Uuid.AsString() in requested}
    if set(found)!=requested:
        raise ValueError('local power copper missing before freeze')
    rows=[]
    for uid,item in sorted(found.items()):
        row=_geometry(board,item)
        if not row['locked'] or not row['net']:
            raise ValueError('unowned local power copper')
        row.update(uuid=uid,groups=sorted(g.GetName() for g in board.Groups() if g.ContainsItem(item)))
        rows.append(row)
    refs=_attached_refs(board,list(found.values()))
    return dict(schema=2,items=rows,sha256=_digest(rows),terminal_refs=refs,
                terminal_sha256=_digest(_scoped_terminals(board,refs)))


def _validate(board,contract):
    rows=contract.get('items')
    if (contract.get('schema') not in (1,2) or not isinstance(rows,list)
            or any(not isinstance(row,dict) for row in rows)
            or _digest(rows)!=contract.get('sha256')):
        raise ValueError('local power copper contract identity mismatch')
    ids=[r.get('uuid') for r in rows]
    if any(not isinstance(uid,str) or not uid for uid in ids) or len(set(ids))!=len(ids):
        raise ValueError('duplicate or missing local copper identity')
    if any(not r.get('locked') or r.get('kind') not in ('PCB_TRACK','PCB_VIA')
           or not isinstance(r.get('net'),str) or not r['net'] for r in rows):
        raise ValueError('invalid local copper ownership or kind')
    if contract['schema']==1:
        terminals=_terminals(board,{r['net'] for r in rows})
    else:
        refs=contract.get('terminal_refs')
        if (not isinstance(refs,list) or any(not isinstance(r,str) or not r for r in refs)
                or refs!=sorted(set(refs))):
            raise ValueError('invalid local power terminal scope')
        terminals=_scoped_terminals(board,refs)
    if contract.get('terminal_sha256')!=_digest(terminals):
        raise ValueError('local power terminal geometry changed')
    physical=[_digest({k:v for k,v in row.items() if k not in ('uuid','groups')}) for row in rows]
    if len(set(physical))!=len(physical):raise ValueError('duplicate local copper geometry')
    if any(not isinstance(r.get('groups'),list) or any(not isinstance(g,str) or not g for g in r['groups']) for r in rows):
        raise ValueError('invalid local copper groups')
    return rows


def verify_present(board,contract):
    """Read-only prefix proof: no recreation, UUID substitution, or group repair."""
    rows=_validate(board,contract)
    items=list(board.GetTracks())
    by_id={i.m_Uuid.AsString():i for i in items}
    if len(by_id)!=len(items):raise ValueError('duplicate board copper identity')
    for row in rows:
        item=by_id.get(row['uuid'])
        if item is None:raise ValueError('local power copper missing on resume')
        actual=_geometry(board,item)
        actual.update(uuid=row['uuid'],groups=sorted(g.GetName() for g in board.Groups() if g.ContainsItem(item)))
        if actual!=row:raise ValueError('local power copper identity or groups changed')
    # Scope itself is part of the proof, including new contacts with a formerly
    # unrelated same-net consumer. Legacy contracts retain their broader check.
    if contract['schema']==2 and _attached_refs(board,[by_id[r['uuid']] for r in rows])!=contract['terminal_refs']:
        raise ValueError('local power contact scope changed')
    return dict(ok=True,items=len(rows),schema=contract['schema'],admitted=False)


def for_placement(board,contract):
    """Upgrade legacy all-net binding only against its unchanged original."""
    verify_present(board,contract)
    return capture(board,[row['uuid'] for row in contract['items']])


def replay(board,contract):
    """Idempotent exact replay on a working candidate; admission stays external.

    Validate the entire payload and native identity set before mutation. An
    existing equivalent primitive is reused; an identity with different copper
    refuses. Net codes are rebound by name, never copied between boards.
    """
    import pcbnew
    rows=_validate(board,contract)
    existing=list(board.GetTracks())
    by_id={item.m_Uuid.AsString():item for item in existing}
    if len(by_id)!=len(existing):raise ValueError('duplicate board copper identity')
    geometries={item.m_Uuid.AsString():_geometry(board,item) for item in existing
                if item.GetClass() in ('PCB_TRACK','PCB_VIA')}
    enabled=set(board.GetEnabledLayers().CuStack())
    prepared=[];reused=[];resolved=[]
    for row in rows:
        geometry={k:v for k,v in row.items() if k not in ('uuid','groups')}
        if not row.get('locked') or row.get('kind') not in ('PCB_TRACK','PCB_VIA'):
            raise ValueError('invalid local copper ownership or kind')
        nc=board.GetNetcodeFromNetname(row['net'])
        if nc<=0:raise ValueError('missing local copper net')
        if row['uuid'] in by_id:
            if geometries.get(row['uuid'])!=geometry:
                raise ValueError('local copper identity changed')
            item=by_id[row['uuid']];reused.append(item)
        else:
            # Lock state is ownership, not physical geometry. An unlocked
            # equivalent is a conflict, never permission to duplicate copper.
            physical={k:v for k,v in geometry.items() if k!='locked'}
            equivalent=[item for item in existing
                        if {k:v for k,v in geometries.get(item.m_Uuid.AsString(),{}).items()
                            if k!='locked'}==physical]
            if len(equivalent)>1:raise ValueError('ambiguous equivalent local copper')
            if equivalent:
                if not equivalent[0].IsLocked():
                    raise ValueError('equivalent local copper lost ownership')
                item=equivalent[0];reused.append(item)
            elif row['kind']=='PCB_TRACK':
                layer=board.GetLayerID(row['layer'])
                if layer not in enabled or int(row['width'])<=0:raise ValueError('invalid local track geometry')
                item=pcbnew.PCB_TRACK(board)
                item.SetStart(pcbnew.VECTOR2I(*row['start']));item.SetEnd(pcbnew.VECTOR2I(*row['end']))
                item.SetLayer(layer);item.SetWidth(int(row['width']));prepared.append(item)
            else:
                layers=[board.GetLayerID(name) for name in row['layers']]
                if (len(layers)!=2 or any(layer not in enabled for layer in layers)
                        or not 0<int(row['drill'])<int(row['width'])
                        or row['via_type']!=int(pcbnew.VIATYPE_THROUGH)):
                    raise ValueError('invalid local via geometry')
                item=pcbnew.PCB_VIA(board)
                item.SetPosition(pcbnew.VECTOR2I(*row['at']));item.SetWidth(int(row['width']))
                item.SetDrill(int(row['drill']));item.SetLayerPair(*layers)
                item.SetViaType(pcbnew.VIATYPE_THROUGH);prepared.append(item)
            if item in prepared:
                item.m_Uuid.Clone(pcbnew.KIID(row['uuid']))
                item.SetNetCode(nc);item.SetLocked(True)
        resolved.append((item,row.get('groups') or ()))
    if contract['schema']==2 and _attached_refs(board,[item for item,_ in resolved])!=contract['terminal_refs']:
        raise ValueError('local power contact scope changed')
    if prepared:
        for zone in board.Zones():zone.UnFill()
        for item in prepared:board.Add(item)
    groups={g.GetName():g for g in board.Groups()}
    for item,names in resolved:
        for name in names:
            if name not in groups:
                group=pcbnew.PCB_GROUP(board);group.SetName(name);board.Add(group);groups[name]=group
            if not groups[name].ContainsItem(item):groups[name].AddItem(item)
    board.BuildConnectivity()
    return dict(schema=1,ok=True,added=len(prepared),reused=len(reused),
                requested=len(rows),source_sha256=contract['sha256'],admitted=False)
