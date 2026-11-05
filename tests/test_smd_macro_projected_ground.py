"""Keep proved source Ground entries while transporting every other port."""
import copy,json
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_projected_ground_contact as contact
import cec_smd_macro_transport as macro
import cec_additive_route_receiving as additive
import cec_fr as fr
from test_projected_ground_contact import fixture,apply
from test_field_proposals import track
from test_smd_macro_transport import inventory


def example(tmp_path,quarter=0,back=False,turn=90,short=False):
    b,path,owner,cap,root,via,target=fixture(tmp_path,quarter,back,turn)
    if short:
        at=tuple(root.GetPosition());v=pcbnew.PCB_VIA(b);v.SetPosition(pcbnew.VECTOR2I(at[0]+700000,at[1]))
        v.SetNet(b.FindNet('GND'));v.SetWidth(600000);v.SetDrill(300000)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
        track(b,'GND',[n/1e6 for n in at],[(at[0]+700000)/1e6,at[1]/1e6],
            layer=pcbnew.B_Cu if back else pcbnew.F_Cu,width=.2)
        fr.group_local_pofv_signal_vias(b,[v]);additive._ground_refill(b);field._save_field_snapshot(b,path)
    proof=contact.plan(b,force._uid(root),target,board_hint='synthetic')
    child=pcbnew.LoadBoard(str(path));future=child.FindFootprintByReference(cap.GetReference());apply(child,future,target)
    return b,child,path,proof,root,cap


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('turn',[90,180,270])
def test_exact_source_ground_entry_survives_cardinal_transport_without_dragging_reference(tmp_path,quarter,back,turn):
    b,c,path,q,root,cap=example(tmp_path,quarter,back,turn)
    old=inventory(b);source_bytes=path.read_bytes()
    r=macro.apply(b,c,source_path=path,board_hint='synthetic',allow_cardinal_rotations=True,
        retained_ground_contacts=[json.loads(json.dumps(q))])
    kept=r['independently_retained_projected_ground_contacts'];assert len(kept)==1
    assert kept[0]['after_complete_transport']['saved_return_mm']<=q['source_return_mm']+.000001
    assert r['new_barrels_created']==0 and not r['saved_candidate_authorized'] and not r['routing_admitted']
    assert set(r['retained_projected_ground_native_uuids']).isdisjoint(t['uuid'] for t in r['changes'])
    new=inventory(c)
    assert all(new[u]==old[u] for u in r['retained_projected_ground_native_uuids'])
    assert r['changes'] and r['transient_rebuild_required_uuids']
    assert inventory(b)==old and path.read_bytes()==source_bytes


@pytest.mark.parametrize('back',[False,True])
def test_short_shared_ground_stem_and_factory_grouped_barrel_remain_exact(tmp_path,back):
    b,c,path,q,root,cap=example(tmp_path,back=back,short=True);old=inventory(b)
    assert q['source_return_mm']==.7
    r=macro.apply(b,c,source_path=path,board_hint='synthetic',allow_cardinal_rotations=True,retained_ground_contacts=[q])
    assert r['independently_retained_projected_ground_contacts'][0]['after_complete_transport']['saved_return_mm']==.7
    assert all(inventory(c)[u]==old[u] for u in r['retained_projected_ground_native_uuids'])


@pytest.mark.parametrize('fault',['source_hash','source_binding','entry','entry_width','return','land','role','target',
    'missing_source_path','wrong_hint','duplicate','unknown_terminal','candidate_anchor','candidate_plane','in_memory_source'])
def test_unowned_or_forged_retention_refuses_before_any_conductor_writes(tmp_path,fault):
    b,c,path,q,root,cap=example(tmp_path);proof=copy.deepcopy(q)
    kw=dict(source_path=path,board_hint='synthetic',allow_cardinal_rotations=True)
    if fault=='source_hash':proof['source_sha256']='not-source'
    elif fault=='source_binding':proof['source_native_binding']='not-native-source'
    elif fault=='entry':proof['source_entry_nm'][0]+=1
    elif fault=='entry_width':proof['entry_width_nm']-=1
    elif fault=='return':proof['source_return_mm']+=1
    elif fault=='land':proof['future_land_sha256']='invented-land'
    elif fault=='role':proof['source_ground_role']['kind']='not-a-manufacturer-role'
    elif fault=='target':proof['target_pose'][0]+=.1
    elif fault=='missing_source_path':kw.pop('source_path')
    elif fault=='wrong_hint':kw['board_hint']='other-source-policy'
    elif fault=='unknown_terminal':proof['pad_uuid']='not-the-native-terminal'
    elif fault=='candidate_anchor':next(t for t in c.GetTracks() if force._uid(t) in q['source_entry_native_uuids']).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='candidate_plane':next(iter(c.Zones())).UnFill()
    elif fault=='in_memory_source':next(iter(b.GetTracks())).SetLocked(True)
    before=macro_inventory(c)
    with pytest.raises(ValueError):macro.apply(b,c,**kw,retained_ground_contacts=[proof,proof] if fault=='duplicate' else [proof])
    assert macro_inventory(c)==before


def macro_inventory(b):
    return (inventory(b),tuple((force._uid(z),bool(z.IsFilled())) for z in b.Zones()))


def test_shared_anchor_cannot_ignore_motion_of_its_other_actual_native_terminal(tmp_path):
    b,c,path,q,root,cap=example(tmp_path)
    owner=next(fp for fp in c.GetFootprints() if fp.GetReference()!=cap.GetReference())
    owner.Move(pcbnew.VECTOR2I_MM(.1,0));before=inventory(c)
    with pytest.raises(ValueError,match='retained_ground_anchor_has_conflicting_endpoint_motion'):
        macro.apply(b,c,source_path=path,board_hint='synthetic',allow_cardinal_rotations=True,retained_ground_contacts=[q])
    assert inventory(c)==before


def test_post_transport_loss_rolls_back_every_changed_conductor(tmp_path,monkeypatch):
    b,c,path,q,root,cap=example(tmp_path);before=inventory(c);original=contact.observe;calls=[]
    def injected(board,pad,proof,**kw):
        calls.append(1)
        return original(board,pad,proof,**kw) if len(calls)==1 else None
    monkeypatch.setattr(contact,'observe',injected)
    with pytest.raises(ValueError,match='lost_after_complete_native_transport'):
        macro.apply(b,c,source_path=path,board_hint='synthetic',allow_cardinal_rotations=True,retained_ground_contacts=[q])
    assert len(calls)==2 and inventory(c)==before


@pytest.mark.parametrize('value',[False,True,None,{},'ground',['bad-proof'],[{}]*17])
def test_retention_scope_is_explicit_finite_and_never_a_boolean_motion_waiver(tmp_path,value):
    b,c,path,q,root,cap=example(tmp_path);before=inventory(c)
    with pytest.raises(ValueError):
        macro.apply(b,c,source_path=path,board_hint='synthetic',allow_cardinal_rotations=True,retained_ground_contacts=value)
    assert inventory(c)==before


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_changed_ground_land_centre_does_not_move_a_still_fully_contained_source_entry(tmp_path,quarter,back):
    b,path,owner,cap,root,via,target=fixture(tmp_path,quarter,back,turn=90)
    target[0]+=.02;target[1]+=.02
    q=contact.plan(b,force._uid(root),target,board_hint='synthetic');c=pcbnew.LoadBoard(str(path))
    future=c.FindFootprintByReference(cap.GetReference());apply(c,future,target)
    assert tuple(future.FindPadByNumber('2').GetPosition())!=tuple(root.GetPosition())
    old=inventory(b)
    r=macro.apply(b,c,source_path=path,board_hint='synthetic',allow_cardinal_rotations=True,retained_ground_contacts=[q])
    assert all(inventory(c)[u]==old[u] for u in r['retained_projected_ground_native_uuids'])
    assert r['independently_retained_projected_ground_contacts'][0]['after_complete_transport']['full_source_entry_preserved_after_all_cuts']
