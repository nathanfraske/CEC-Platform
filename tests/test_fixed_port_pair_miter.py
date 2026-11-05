"""Fixed-port visible miters shorten geometry, not pair qualification gates."""
import copy,math
import pcbnew
import pytest
import cec_pair_craft_reflow as craft
import cec_pair_neutral_miter as neutral
import cec_force_current as force
import cec_field_coupling as field
from test_pair_local_reference_refinement import physical_craft_fixture


def points(quarter=0,mirror=False,reverse=False):
 def at(x,y):
  if mirror:x=-x
  for _ in range(quarter):x,y=-y,x
  return [x+20000000,y+20000000]
 p=[at(*q) for q in ((0,0),(1000000,1000000),(1040000,1000000),(2040000,0))]
 return p[::-1] if reverse else p


def fixture(tmp_path,quarter=0,mirror=False,layer=pcbnew.F_Cu):
 board,source,pair=physical_craft_fixture(tmp_path,'port_miter',quarter,mirror,layer)
 # A one-member shortening must improve, not worsen, existing skew. Give the
 # synthetic N member a real200um cardinal terminal tail within the source
 # CAN contract. Do not waive the perfect-length-pair refusal tested below.
 port=next(p for f in board.GetFootprints() for p in f.Pads()
  if p.GetNetname()==pair['n'] and p.GetAttribute()==pcbnew.PAD_ATTRIB_PTH)
 at=tuple(port.GetPosition())
 t=next(t for t in board.GetTracks() if t.GetNetname()==pair['n'] and at in (tuple(t.GetStart()),tuple(t.GetEnd())))
 other=tuple(t.GetEnd()) if tuple(t.GetStart())==at else tuple(t.GetStart())
 delta=pcbnew.VECTOR2I(*[200000*(1 if a>b else -1) if a!=b else 0 for a,b in zip(at,other)])
 new=pcbnew.VECTOR2I(*at)+delta
 if tuple(t.GetStart())==at:t.SetStart(new)
 else:t.SetEnd(new)
 port.GetParent().Move(delta);neutral.additive._ground_refill(board)
 saved=force._copy_family(source,tmp_path/'fixed-source');field._save_field_snapshot(board,saved)
 return board,saved,pair


def accepted(tmp_path,board,source,pair):
 requests=[r for r in craft.discover(board,source,pair) if r['operation']=='fixed_port_miter']
 assert requests;refusals=[]
 for i,r in enumerate(requests):
  b=pcbnew.LoadBoard(str(source))
  try:made=craft.construct_whole(b,source,pair,r,board_hint='synthetic')
  except ValueError as exc:refusals.append(str(exc));continue
  child=force._copy_family(source,tmp_path/('candidate-'+str(i)));neutral.additive._ground_refill(b);field._save_field_snapshot(b,child)
  proof=neutral.receive_phase(source,child,made,board_hint='synthetic',pair_name=pair['name'])
  if proof['ok'] and proof['complete']:return b,made,proof
  refusals.append(proof)
 pytest.fail(str(refusals))


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('target',[196778,250000])
def test_integer_fixed_ports_and_exact_positive_radical_shortening(quarter,mirror,reverse,target):
 p=points(quarter,mirror,reverse);frame=craft.fixed_port_frame(p,250000)
 q,proof=craft.fixed_port_points(frame,target)
 assert p[0]==q[0] and p[-1]==q[-1] and len(p)==len(q)==4
 assert craft.visible_miter(craft.fixed_port_frame(q,250000)['source_flat_nm'],250000)
 assert proof['fixed_ports_exact'] and proof['actual_centerline_strictly_shorter']
 assert proof['diagonal_axis_removed_each_nm']*2==proof['flat_growth_nm']
 length=lambda rows:sum(math.dist(a,b) for a,b in zip(rows,rows[1:]))
 assert length(p)-length(q)==pytest.approx((target-40000)*(math.sqrt(2)-1),abs=1e-8)
 assert not craft.visible_miter(40000,250000)


@pytest.mark.parametrize('target',[True,0,-1,250000.,float('nan'),196777,150000,1040000])
def test_no_rounding_invisible_flat_or_work_bound_waiver(target):
 frame=craft.fixed_port_frame(points(),250000)
 with pytest.raises(ValueError):craft.fixed_port_points(frame,target)


@pytest.mark.parametrize('fault',['source','width','axis','sign','flat','flanks','too_short','cardinal','non45'])
def test_frame_is_rederived_from_literal_native_stations(fault):
 frame=craft.fixed_port_frame(points(),250000)
 if fault=='source':frame['source_points_nm'][1][0]+=1
 elif fault=='width':frame['width_nm']=True
 elif fault=='axis':frame['axis']=1-frame['axis']
 elif fault=='sign':frame['sign']*=-1
 elif fault=='flat':frame['source_flat_nm']+=1
 elif fault=='flanks':frame['diagonal_axis_nm'][0]+=1
 elif fault=='too_short':frame=craft.fixed_port_frame([[0,0],[50000,50000],[90000,50000],[140000,0]],250000)
 elif fault=='cardinal':frame['source_points_nm'][1][1]=0
 else:frame['source_points_nm'][2][1]+=1
 with pytest.raises(ValueError):craft.fixed_port_points(frame,250000)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_saved_fixed_port_operation_uses_unchanged_positive_full_bus_receiver(tmp_path,quarter,mirror,layer):
 board,source,pair=fixture(tmp_path,quarter,mirror,layer);original=source.read_bytes()
 _,made,proof=accepted(tmp_path,board,source,pair)
 assert proof['physical_craft_operation']=='fixed_port_miter' and proof['shortened_centerline_mm']>0
 assert proof['continuous_coupling']['ok'] and proof['existing_full_bus_receiver']['ok']
 assert all(not p['before']['violations'] and not p['after']['violations'] for p in proof['full_pair_physical_samples'])
 assert not proof['exact_neutral_geometry']['exact_centerline_length_unchanged']
 assert not proof['pair_qualified'] and not proof['release_authority'] and source.read_bytes()==original


@pytest.mark.parametrize('fault',['geometry','target','width','lock','port','mapping','certificate'])
def test_saved_worker_cannot_rehash_a_different_splice_or_changed_native_scope(tmp_path,fault):
 board,source,pair=fixture(tmp_path);board,made,_=accepted(tmp_path,board,source,pair);made=copy.deepcopy(made)
 tracks={force._uid(t):t for t in board.GetTracks()}
 if fault=='geometry':tracks[made['local_new_track_uuids'][0]].Move(pcbnew.VECTOR2I(1,0))
 elif fault=='target':made['operation_parameters']['target_flat_nm']+=2
 elif fault=='width':tracks[made['local_new_track_uuids'][0]].SetWidth(249999)
 elif fault=='lock':tracks[made['local_new_track_uuids'][0]].SetLocked(True)
 elif fault=='port':next(p for f in board.GetFootprints() for p in f.Pads() if p.GetNetname()==pair['p']).GetParent().Move(pcbnew.VECTOR2I(1,0))
 elif fault=='mapping':made['unchanged_pair_native_copies'].pop(next(iter(made['unchanged_pair_native_copies'])))
 else:made['exact_neutral_geometry']['length']['flat_growth_nm']+=2
 child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(board,child)
 proof=neutral.receive_phase(source,child,made,board_hint='synthetic',pair_name=pair['name'])
 assert not proof['ok'] and not proof['complete'] and proof['errors'],proof


def test_new_operation_does_not_spend_skew_on_a_perfectly_length_matched_source(tmp_path):
 board,source,pair=physical_craft_fixture(tmp_path,'port_miter');rejected=[]
 for i,r in enumerate(q for q in craft.discover(board,source,pair) if q['operation']=='fixed_port_miter'):
  b=pcbnew.LoadBoard(str(source))
  try:made=craft.construct_whole(b,source,pair,r,board_hint='synthetic')
  except ValueError:continue
  child=force._copy_family(source,tmp_path/('rejected-'+str(i)));neutral.additive._ground_refill(b);field._save_field_snapshot(b,child)
  proof=neutral.receive_phase(source,child,made,board_hint='synthetic',pair_name=pair['name'])
  assert not proof['ok'] and any('skew_mm' in e for e in proof['errors']),proof
  rejected.append(proof)
 assert rejected


@pytest.mark.parametrize('operations',['fixed_port_miter',[],['unknown'],['fixed_port_miter']*2,[True],{}])
def test_explicit_operation_portfolio_is_typed_bounded_and_not_a_receiving_exception(tmp_path,operations):
 with pytest.raises(ValueError):
  craft.run(tmp_path/'missing',tmp_path/'out',board_hint='synthetic',expected_source_sha256='0'*64,
   reporting_build=tmp_path/'native',operations=operations)
 assert not (tmp_path/'out').exists()
