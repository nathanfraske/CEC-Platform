"""Exact existing aggregate GroundView metric, without role alias or waiver."""
import sys,json,math
from pathlib import Path
ROOT=Path('/home/codex/src/CEC-Platform');sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'src')]
from cec_pipeline.native import _native
import cec_force_current as force
import cec_decoupler_cell as cells
import cec_fab_profile as fab
p,_=_native();folder=Path(__file__).parent;r=json.loads((folder/'geometry-fixed-ground-pivot.json').read_text());source=Path(r['source']);assert force._hash(source)==r['source_sha256'];rows=[]
for mode in ['source','fixed_Ground_pivot']:
 b=p.LoadBoard(str(source));fps={f.GetReference():f for f in b.GetFootprints()}
 if mode!='source':
  for ref,pose in r['proposed_poses'].items():fps[ref].SetOrientationDegrees(pose[2]);fps[ref].SetPosition(p.VECTOR2I(pose[0],pose[1]))
 pad=next(q for q in fps['C55'].Pads()if q.GetNumber()=='2');face=int(fps['C55'].GetLayer());width=max(200000,int(b.GetDesignSettings().m_TrackMinWidth),int(cells._netclass(b,'GND')['width']))
 class GroundView:
  def GetTracks(self):return[t for t in b.GetTracks()if t.GetNetname()=='GND'and(t.GetClass()=='PCB_VIA'or t.GetClass()in('PCB_TRACK','PCB_ARC')and int(t.GetLayer())==face and t.GetWidth()>=width)]
  def __getattr__(self,name):return getattr(b,name)
 view=GroundView();immediate=cells._existing_return(view,pad,.8,allow_native_track_body=True);wide=cells._existing_return(view,pad,2.,allow_native_track_body=True)
 def result(value):
  if value is None:return None
  distance,via=value;blocked,records=fab.via_at_pad_conflicts(b,via.GetPosition(),via.GetWidth(via.TopLayer()),via.GetDrillValue(),via.GetNetCode())
  return dict(observed_path_mm=distance,via_uuid=force._uid(via),via_at_nm=list(via.GetPosition()),pad_to_axis_centerline_mm=math.dist(tuple(pad.GetPosition()),tuple(via.GetPosition()))/1e6,process_pad_blocked=blocked is not None,process_records=records)
 retained=next(t for t in b.GetTracks()if force._uid(t)=='8fcb6331-0f3f-403a-ba73-e7a6da00710b');prepared=cells._explicit_track_graph(view,pad.GetNetCode(),(pad,),1);explicit=cells._query_explicit_track_path_mm(prepared,pad,retained,1);straight=cells._straight_filled_return_mm(view,pad,retained,include_native_tracks=True)
 rows.append(dict(mode=mode,ground_width_nm=width,face=b.GetLayerName(face),pad_center_nm=list(pad.GetPosition()),exact_aggregate_point8_result=result(immediate),passes_existing_aggregate_immediate_gate=immediate is not None and immediate[0]<=.8,diagnostic_only_point2_result=result(wide),retained_axis_explicit_graph_cost_mm=explicit,retained_axis_straight_native_copper_cost_mm=straight,retained_axis_centerline_mm=math.dist(tuple(pad.GetPosition()),tuple(retained.GetPosition()))/1e6,metric_not_replaced_by_edge_distance=True))
out=dict(source=r['source'],source_sha256=r['source_sha256'],rows=rows,scope='Exact GroundView and cells._existing_return invocation from additional aggregate observe; 2mm query diagnostic only, no changed final gate or role alias',board_saved=False,release_authority=False)
assert force._hash(source)==r['source_sha256'];(folder/'C55-return-observation.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2))
