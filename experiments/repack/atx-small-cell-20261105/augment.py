"""Explicit ordinary pad-owned control vias, private native geometry only."""
import sys,json,uuid
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'src'),str(ROOT/'scripts')]
import pcbnew,cec_swig_guard
cec_swig_guard.pin()
from cec_pipeline.native import _native
pcbnew,quiet=_native()
from cec_pipeline import geometry
import cec_force_current as f,cec_additive_route_receiving as syntax
import cec_zone_fill as fill,cec_field_coupling as field
WORK=ROOT/'experiments/repack/atx-small-cell-20261105'
version=sys.argv[1] if len(sys.argv)>1 else 'v3'
parent=WORK/('cell-'+version+'/carrier/board.kicad_pcb');folder=WORK/('native-'+version)
target=f._copy_family(parent,folder/'carrier')
f._copy_family(WORK/('cell-'+version+'/cover/board.kicad_pcb'),folder/'cover')
overlay=json.loads((ROOT/('docs/evidence/20261105-bottom-compaction/5v-small-cell-'+version+'-overlay.json')).read_text())
parenthash=f._hash(parent);b=pcbnew.LoadBoard(str(parent));byid={f._uid(t):t for t in b.GetTracks()};added=set();records=[]
def key(label):return str(uuid.uuid5(uuid.NAMESPACE_URL,parenthash+':small-cell:'+label))
for i,row in enumerate(overlay['control_vias']):
 ref,number=row['pad_owner'].split('.');pad=next(p for p in b.FindFootprintByReference(ref).Pads()if p.GetNumber()==number)
 proto=byid[row['process_prototype_uuid']];v=proto.Duplicate();uid=key('via'+str(i));v.m_Uuid.Clone(pcbnew.KIID(uid));v.SetParentGroup(None);v.SetPosition(pcbnew.VECTOR2I(*row['at_nm']));v.SetNet(pad.GetNet());b.Add(v);added.add(uid)
 records.append(dict(operation='explicit_pad_owned_ordinary_control_via',uuid=uid,net=pad.GetNetname(),net_authority_pad_uuid=f._uid(pad),net_authority_reference=row['pad_owner'],process_prototype_uuid=f._uid(proto),at_nm=row['at_nm'],diameter_nm=v.GetWidth(pcbnew.F_Cu),drill_nm=v.GetDrillValue(),qualification='Source process only; no inferred current allocation or assembly admission.'))
pad=next(p for p in b.FindFootprintByReference('U5').Pads()if p.GetNumber()=='5')
for i,points in enumerate(overlay['control_paths']):
 geometry.path(points,minimum_phase_nm=20000)
 for j,(a,z)in enumerate(zip(points,points[1:])):
  t=pcbnew.PCB_TRACK(b);uid=key('path'+str(i)+':'+str(j));t.m_Uuid.Clone(pcbnew.KIID(uid));t.SetNet(pad.GetNet());t.SetLayer(b.GetLayerID('SIG2'));t.SetWidth(200000);t.SetLocked(True);t.SetStart(pcbnew.VECTOR2I(*a));t.SetEnd(pcbnew.VECTOR2I(*z));b.Add(t);added.add(uid)
 records.append(dict(operation='explicit_pad_owned_ordinary_control_path',net=pad.GetNetname(),net_authority_pad_uuid=f._uid(pad),layer='SIG2',width_nm=200000,points_nm=points))
zones=pcbnew.ZONES()
for z in b.Zones():
 if not z.GetIsRuleArea():zones.append(z)
fill.compile_selected(b,zones,timeout_s=10.,initialize_selected=True)
raw=folder/'native.kicad_pcb';field._save_field_snapshot(b,raw)
root,old=syntax._nodes(parent);_,fresh=syntax._nodes(raw);names={id(n):k for k,n in old.items()}
changed={f._uid(z)for z in b.Zones()if not z.GetIsRuleArea()}
root[1:]=[fresh[names[id(n)]]if names.get(id(n))in changed else n for n in root[1:]]
root.extend(fresh[k]for k in sorted(added));target.write_text(syntax._render(root)+'\n')
saved=pcbnew.LoadBoard(str(target));assert field._field_snapshot_inventory(saved)==field._field_snapshot_inventory(b)
(folder/'additions.json').write_text(json.dumps(dict(parent_sha256=parenthash,candidate_sha256=f._hash(target),operations=records,added_uuids=sorted(added),typed_members_changed=[],routing_admitted=False,current_qualified=False,release_authority=False),indent=2)+'\n')
assert f._hash(parent)==parenthash
print(str(target),f._hash(target))
