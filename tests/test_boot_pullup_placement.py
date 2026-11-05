"""A selected BOOT pull-up is a complete canonical passive, not EN or power."""
import re,sys,time
from pathlib import Path
import pcbnew,pytest
import cec_control_pullup_placement as op
import cec_field_coupling as field
from test_c6_boot_strap_shunt import fixture as boot_fixture


def fixture(tmp_path,monkeypatch,turn=0,back=False):
    b,m,c,r,s,root,tree=boot_fixture(tmp_path,monkeypatch)
    exporter=op.leaf._export
    def export(*args):
        tree,metadata=exporter(*args)
        metadata.update(exporter=sys.executable,exporter_sha256=op.force._hash(Path(sys.executable)),
            **op.shunt.semantic.metadata(tree))
        return tree,metadata
    monkeypatch.setattr(op.leaf,'_export',export)
    for fp in b.GetFootprints():
        fp.SetOrientationDegrees(turn)
        if back:fp.Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    field._save_field_snapshot(b,Path(b.GetFileName()))
    poses={r.GetReference():[r.GetPosition().x/1e6+.5,r.GetPosition().y/1e6,(turn+90)%360]}
    return b,m,c,r,s,root,tree,poses


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_manufacturer_strap_complete_topology_survives_names_rotation_and_face(tmp_path,monkeypatch,turn,back):
    b,m,c,r,s,root,tree,poses=fixture(tmp_path,monkeypatch,turn,back)
    binding=op.row._source_binding(b);literal=Path(b.GetFileName()).read_bytes()
    assert op.plan(b,poses,board_hint=str(root))=={}  # Legacy EN API unchanged.
    selected=op.boot_plan(b,poses,board_hint=str(root));q=selected[r.GetReference()]
    assert q['role']=='source_boot_mode_strap_pullup_passive'and q['control_pin']=='23'
    assert q['nominal_resistance_ohms']==10000 and q['control_owner']==m.GetReference()
    assert q['source_proof']['manufacturer']['boot_gpio']=='GPIO9'
    assert q['source_proof']['manufacturer']['function']=='IO9'
    assert op.complete_plan(b,poses,board_hint=str(root))==selected
    for key in('current_authority','source_trace_retirement_authority','bypass_owner',
            'reset_timing_qualified','boot_timing_qualified','postboot_gpio_mode_assumed','release_authority'):
        assert q[key]is False
    assert op.row._source_binding(b)==binding and Path(b.GetFileName()).read_bytes()==literal


@pytest.mark.parametrize('fault',['native_function','source_pin','missing_button','wrong_pull_rail',
    'extra_gpio','mpn','resistor_source_mpn','value','dnp','locked','group','owner_move','vdd_type'])
def test_boot_name_and_partial_or_changed_source_never_grant_a_passive_owner(tmp_path,monkeypatch,fault):
    b,m,c,r,s,root,tree,poses=fixture(tmp_path,monkeypatch)
    if fault=='native_function':m.FindPadByNumber('23').SetPinFunction('IO0')
    elif fault=='source_pin':root.write_text(root.read_text().replace('(name "IO9")','(name "IO0")'))
    elif fault=='missing_button':b.Remove(s)
    elif fault=='wrong_pull_rail':r.FindPadByNumber('1').SetNetCode(c.FindPadByNumber('2').GetNetCode())
    elif fault=='extra_gpio':m.FindPadByNumber('12').SetNetCode(m.FindPadByNumber('23').GetNetCode())
    elif fault=='mpn':m.SetField('MPN','ESP32-C6-MINI-1-N8')
    elif fault=='resistor_source_mpn':root.write_text(root.read_text().replace('0402WGF1002TCE','forged'))
    elif fault=='value':r.SetValue('0')
    elif fault=='dnp':r.SetDNP(True)
    elif fault=='locked':r.SetLocked(True)
    elif fault=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(r)
    elif fault=='owner_move':poses[m.GetReference()]=[1,2,0]
    elif fault=='vdd_type':
        text,count=re.subn(r'\(pin power_in(?= line \(at [^)]+\) \(length 1\) \(name "P3"\) \(number "3"\))',
            '(pin passive',root.read_text())
        assert count==1;root.write_text(text)
    try:q=op.boot_plan(b,poses,board_hint=str(root))
    except ValueError:return
    assert q=={}


@pytest.mark.parametrize('fault',[None,'forged','owner','net','face','missing_current','part','geometry','population'])
def test_boot_requests_recompile_both_actual_pins_and_keep_complete_aggregate_rail(tmp_path,monkeypatch,fault):
    import cec_decoupler_cell as cells
    b,m,c,r,s,root,tree,poses=fixture(tmp_path,monkeypatch)
    selected=op.boot_plan(b,poses,board_hint=str(root));proposal=dict(poses=poses,
        selected_control_pullups=selected,board_hint=str(root))
    child=pcbnew.LoadBoard(b.GetFileName());authority=dict(fixture_only=True)
    monkeypatch.setattr(cells,'_supply_current_widths',lambda board,net:None if fault=='missing_current'else dict(
        required_by_layer_nm={int(l):800000 for l in board.GetEnabledLayers().CuStack()},current_authority=authority))
    if fault=='forged':selected[r.GetReference()]['nominal_resistance_ohms']=1
    elif fault=='owner':child.FindFootprintByReference(m.GetReference()).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='net':child.FindFootprintByReference(r.GetReference()).FindPadByNumber('1').SetNetCode(0)
    elif fault=='face':child.FindFootprintByReference(r.GetReference()).Flip(pcbnew.VECTOR2I(0,0),pcbnew.FLIP_DIRECTION_LEFT_RIGHT)
    elif fault=='part':child.FindFootprintByReference(r.GetReference()).SetField('MPN','forged')
    elif fault=='geometry':child.FindFootprintByReference(r.GetReference()).FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(2,2))
    elif fault=='population':child.FindFootprintByReference(r.GetReference()).SetDNP(True)
    if fault is not None:
        with pytest.raises(ValueError):op.requests(b,child,proposal)
        return
    requests=op.requests(b,child,proposal)
    assert len(requests)==2 and {v['role']for v in requests.values()}=={'control_signal','nonload_pullup_supply'}
    rail=next(v for v in requests.values()if v['role']=='nonload_pullup_supply')
    assert rail['width_nm']>=800000 and rail['unchanged_full_rail_current_contract']['current_authority']==authority
    assert not rail['new_barrel_authority']and not rail['class_only_supply_prefix_authority']


def test_boot_complete_compiler_and_independent_actual_pose_receiver_are_both_typed(tmp_path,monkeypatch):
    import cec_cell_escape_replan as escape
    import cec_complete_cell_receiving as saved
    import cec_decoupler_cell as cells
    b,m,c,r,s,root,tree,poses=fixture(tmp_path,monkeypatch)
    monkeypatch.setattr(escape.constraints,'_device_bypass_assignment',lambda *a,**k:{'assigned':{}})
    q=escape.prepare(b,poses,board_hint=str(root))
    assert set(q['selected_control_pullups'])==set(poses)
    assert not q['selected_bypasses']and not q['device_contracts']and 'selected_control_shunts'not in q
    assert q['selected_control_pullups'][r.GetReference()]['role']=='source_boot_mode_strap_pullup_passive'
    monkeypatch.setattr(saved,'_assignments',lambda *a:{})
    monkeypatch.setattr(cells,'_supply_current_widths',lambda board,net:dict(
        required_by_layer_nm={int(l):800000 for l in board.GetEnabledLayers().CuStack()},current_authority={'fixture_only':True}))
    child=pcbnew.LoadBoard(b.GetFileName());fp=child.FindFootprintByReference(r.GetReference());pose=poses[r.GetReference()]
    fp.SetPosition(pcbnew.VECTOR2I(*(round(v*1e6)for v in pose[:2])));fp.SetOrientationDegrees(pose[2])
    actual,moved=saved._poses(b,child,str(root))
    assert actual==poses and moved==set(poses)


def test_explicit_roles_share_one_source_lease_without_reset(monkeypatch):
    now=[100.];calls=[]
    monkeypatch.setattr(op.time,'monotonic',lambda:now[0])
    def enable(*args,**kwargs):calls.append(kwargs['timeout_s']);now[0]+=2.;return {}
    def boot(*args,**kwargs):calls.append(kwargs['timeout_s']);return {}
    monkeypatch.setattr(op,'plan',enable);monkeypatch.setattr(op,'boot_plan',boot)
    assert op.complete_plan(None,{},board_hint='synthetic',timeout_s=5.)=={}
    assert calls==[5.,3.]


@pytest.mark.parametrize('seconds',[True,0,-1,11,float('nan'),float('inf')])
def test_complete_pullup_compilers_are_explicitly_bounded(seconds):
    with pytest.raises(ValueError):op.complete_plan(None,{},board_hint='synthetic',timeout_s=seconds)
