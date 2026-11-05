"""Matched native corner shortening preserves exact pair skew, not flags."""
import copy,math
import pcbnew
import pytest
import cec_pair_balanced_miters as balanced
import cec_pair_craft_reflow as craft
import cec_pair_neutral_miter as neutral
import cec_force_current as force
import cec_field_coupling as field
from test_pair_local_reference_refinement import physical_craft_fixture


def frames(quarter=0,mirror=False,reverse=False,counter_flat=40000):
 def at(x,y):
  if mirror:x=-x
  for _ in range(quarter):x,y=-y,x
  return [x+20000000,y+20000000]
 result=[]
 for shift,flat in ((0,40000),(700000,counter_flat)):
  p=[at(x,y+shift) for x,y in ((0,0),(1000000,1000000),(1000000+flat,1000000),(2000000+flat,0))]
  if reverse:p.reverse()
  result.append(craft.fixed_port_frame(p,250000))
 return result


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('reverse',[False,True])
@pytest.mark.parametrize('counter_flat',[40000,600000])
def test_matched_growth_has_equal_exact_radical_reduction_without_moving_ports(quarter,mirror,reverse,counter_flat):
 f=frames(quarter,mirror,reverse,counter_flat);points,proof=balanced.matched_points(f,210000)
 length=lambda p:sum(math.dist(a,b) for a,b in zip(p,p[1:]))
 reductions=[]
 for before,after in zip(f,points):
  assert after[0]==before['source_points_nm'][0] and after[-1]==before['source_points_nm'][-1]
  reductions.append(length(before['source_points_nm'])-length(after))
  assert craft.visible_miter(craft.fixed_port_frame(after,250000)['source_flat_nm'],250000)
 assert reductions[0]==pytest.approx(reductions[1],abs=1e-8)
 assert reductions[0]==pytest.approx(210000*(math.sqrt(2)-1),abs=1e-8)
 assert proof['exact_pair_skew_unchanged'] and proof['exact_equal_member_shortening']
 assert not proof['pair_qualified'] and not proof['release_authority']


@pytest.mark.parametrize('fault',['bool','odd','tiny','large','width','axis','forged_frame','no_bad_miter','short_flank','invisible_target'])
def test_no_rounding_fabrication_or_style_floor_waiver(fault):
 f=frames();growth=210000
 if fault=='bool':growth=True
 elif fault=='odd':growth+=1
 elif fault=='tiny':growth=2
 elif fault=='large':growth=500002
 elif fault=='width':f[1]=craft.fixed_port_frame(f[1]['source_points_nm'],200000)
 elif fault=='axis':
  p=[[q[1],q[0]] for q in f[1]['source_points_nm']];f[1]=craft.fixed_port_frame(p,250000)
 elif fault=='forged_frame':f[1]['source_flat_nm']+=2
 elif fault=='no_bad_miter':f=[craft.fixed_port_frame(p,250000) for p in balanced.matched_points(f,210000)[0]]
 elif fault=='short_flank':f[1]=craft.fixed_port_frame([[0,0],[40000,40000],[80000,40000],[120000,0]],250000)
 else:growth=20000
 with pytest.raises(ValueError):balanced.matched_points(f,growth)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu,pcbnew.In2_Cu])
def test_both_members_of_a_perfectly_matched_source_pass_existing_whole_bus_receiving(tmp_path,quarter,mirror,layer):
 b,source,pair=physical_craft_fixture(tmp_path,'port_miter',quarter,mirror,layer);original=source.read_bytes()
 requests=balanced.discover(b,source,pair);assert requests
 made=craft.construct_whole(b,source,pair,requests[0],board_hint='synthetic')
 neutral.additive._ground_refill(b);child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
 proof=neutral.receive_phase(source,child,made,board_hint='synthetic',pair_name=pair['name'])
 assert proof['ok'] and proof['complete'],proof
 assert proof['physical_craft_operation']==balanced.OPERATION and proof['shortened_centerline_mm_each']>0
 assert proof['continuous_coupling']['ok'] and proof['existing_full_bus_receiver']['ok']
 assert proof['exact_neutral_geometry']['length']['exact_pair_skew_unchanged']
 assert all(not x['before']['violations'] and not x['after']['violations'] for x in proof['full_pair_physical_samples'])
 assert source.read_bytes()==original and not proof['pair_qualified'] and not proof['release_authority']


@pytest.mark.parametrize('fault',['geometry','growth','certificate','net','width','lock','pad','mapping','extra_field'])
def test_saved_source_scope_and_each_members_process_are_rederived(tmp_path,fault):
 b,source,pair=physical_craft_fixture(tmp_path,'port_miter');request=balanced.discover(b,source,pair)[0]
 made=craft.construct_whole(b,source,pair,request,board_hint='synthetic');made=copy.deepcopy(made)
 tracks={force._uid(t):t for t in b.GetTracks()};t=tracks[made['local_new_track_uuids'][0]]
 if fault=='geometry':t.Move(pcbnew.VECTOR2I(1,0))
 elif fault=='growth':made['operation_parameters']['growth_nm']+=2
 elif fault=='certificate':made['exact_neutral_geometry']['length']['flat_growth_nm_each']+=2
 elif fault=='net':t.SetNet(b.FindNet(pair['n'] if t.GetNetname()==pair['p'] else pair['p']))
 elif fault=='width':t.SetWidth(249999)
 elif fault=='lock':t.SetLocked(not t.IsLocked())
 elif fault=='pad':next(p for f in b.GetFootprints() for p in f.Pads() if p.GetNetname()==pair['p']).GetParent().Move(pcbnew.VECTOR2I(1,0))
 elif fault=='mapping':made['unchanged_pair_native_copies'].pop(next(iter(made['unchanged_pair_native_copies'])))
 else:made['extra_field']='not-authority'
 if fault=='net':
  parent=pcbnew.LoadBoard(str(source));old={force._uid(t):t for t in parent.GetTracks()}
  with pytest.raises(ValueError):
   balanced.certificate(parent,pair,[old[u] for u in made['local_source_track_uuids']],
    [tracks[u] for u in made['local_new_track_uuids']],made['operation_parameters'])
  # Native connectivity can auto-reassign this forged attached track's net.
  # The existing authored-net guard must stop that before any saved trial.
  with pytest.raises(RuntimeError,match='selected_native_fill_changed_authored_net_identity'):
   neutral.additive._ground_refill(b)
  return
 neutral.additive._ground_refill(b);child=force._copy_family(source,tmp_path/'child');field._save_field_snapshot(b,child)
 proof=neutral.receive_phase(source,child,made,board_hint='synthetic',pair_name=pair['name'])
 assert not proof['ok'] and not proof['complete'] and proof['errors'],proof


def test_remote_same_face_corner_is_not_a_local_matched_corner_permission(tmp_path):
 b,source,pair=physical_craft_fixture(tmp_path,'port_miter')
 for t in b.GetTracks():
  if t.GetNetname()==pair['n']:t.Move(pcbnew.VECTOR2I(0,20000000))
 far=force._copy_family(source,tmp_path/'far');field._save_field_snapshot(b,far)
 assert not balanced.discover(b,far,pair)
