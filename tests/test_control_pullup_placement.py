import copy,sys,re
from pathlib import Path
import pcbnew,pytest
import cec_control_pullup_placement as op
import cec_field_coupling as field
from test_c6_enable_shunt import fixture as source_fixture


def fixture(tmp_path,monkeypatch,turn=0,back=False):
    b,m,c,r,s,root,tree=source_fixture(tmp_path,monkeypatch)
    exporter=op.leaf._export
    def export(*args):
        tree,metadata=exporter(*args);metadata.update(exporter=sys.executable,
            exporter_sha256=op.force._hash(Path(sys.executable)),**op.shunt.semantic.metadata(tree));return tree,metadata
    monkeypatch.setattr(op.leaf,'_export',export)
    for fp in b.GetFootprints():
        fp.SetOrientationDegrees(turn)
        if back:fp.Flip(pcbnew.VECTOR2I(0,0),False)
    field._save_field_snapshot(b,Path(b.GetFileName()))
    poses={r.GetReference():[r.GetPosition().x/1e6+.5,r.GetPosition().y/1e6,(turn+90)%360]}
    return b,m,c,r,s,root,tree,poses


@pytest.mark.parametrize('turn',[0,90,180,270])
@pytest.mark.parametrize('back',[False,True])
def test_source_selected_pullup_is_not_power_bypass_or_current(tmp_path,monkeypatch,turn,back):
    b,m,c,r,s,root,tree,poses=fixture(tmp_path,monkeypatch,turn,back);before=op.row._source_binding(b)
    q=op.plan(b,poses,board_hint=str(root));item=q[r.GetReference()]
    assert item['nominal_resistance_ohms']==10000 and item['role']=='source_enable_reset_pullup_passive'
    assert item['control_pin']=='8'and item['supply_target_pad_uuid']==op.force._uid(m.FindPadByNumber('3'))
    assert not item['current_authority']and not item['source_trace_retirement_authority']and not item['bypass_owner']
    assert before==op.row._source_binding(b)


@pytest.mark.parametrize('fault',['rail','mpn','value','source_pin','ambiguous','extra_topology','partial','dnp','locked','group','owner_move','source_vdd_type'])
def test_wrong_or_partial_source_refuses(tmp_path,monkeypatch,fault):
    b,m,c,r,s,root,tree,poses=fixture(tmp_path,monkeypatch)
    if fault=='rail':r.FindPadByNumber('1').SetNetCode(c.FindPadByNumber('2').GetNetCode())
    elif fault=='mpn':r.SetField('MPN','forged')
    elif fault=='value':r.SetValue('0')
    elif fault=='source_pin':root.write_text(root.read_text().replace('(name "EN")','(name "GPIO0")'))
    elif fault=='source_vdd_type':
        text,count=re.subn(r'\(pin power_in(?= line \(at [^)]+\) \(length 1\) \(name "P3"\) \(number "3"\))','(pin passive',root.read_text())
        assert count==1;root.write_text(text)
    elif fault=='ambiguous':
        original=op.leaf._candidates
        def twice(*a):
            q=original(*a);value=next(v for v in q.values()if v[1]=='source_control_shunt_ground');q['duplicate']=value;return q
        monkeypatch.setattr(op.leaf,'_candidates',twice)
    elif fault=='extra_topology':m.FindPadByNumber('12').SetNetCode(m.FindPadByNumber('8').GetNetCode())
    elif fault=='partial':root.write_text(root.read_text().replace('(property "MPN" "0402WGF1002TCE")','(property "MPN" "unknown")'))
    elif fault=='dnp':r.SetDNP(True)
    elif fault=='locked':r.SetLocked(True)
    elif fault=='group':g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(r)
    elif fault=='owner_move':poses[m.GetReference()]=[1,2,0]
    if fault=='rail':assert op.plan(b,poses,board_hint=str(root))=={}
    else:
        with pytest.raises(ValueError):op.plan(b,poses,board_hint=str(root))


def test_bootstrap_not_enable_role(tmp_path,monkeypatch):
    from test_c6_boot_strap_shunt import fixture as boot
    b,m,c,r,s,root,tree=boot(tmp_path,monkeypatch)
    assert op.plan(b,{r.GetReference():[0,0,0]},board_hint=str(root))=={}


@pytest.mark.parametrize('fault',['forged','owner','net','face','unknown_current','part','padshape','population'])
def test_requests_both_mandatory_and_no_new_current_authority(tmp_path,monkeypatch,fault):
    import cec_decoupler_cell as cells
    b,m,c,r,s,root,tree,poses=fixture(tmp_path,monkeypatch);q=op.plan(b,poses,board_hint=str(root))
    proposal=dict(poses=poses,selected_control_pullups=q,board_hint=str(root));child=pcbnew.LoadBoard(b.GetFileName())
    monkeypatch.setattr(cells,'_supply_current_widths',lambda board,net:None if fault=='unknown_current'else dict(
        required_by_layer_nm={int(l):800000 for l in board.GetEnabledLayers().CuStack()},current_authority={'amps':1.}))
    if fault=='forged':q[r.GetReference()]['nominal_resistance_ohms']=1
    elif fault=='owner':child.FindFootprintByReference(m.GetReference()).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='net':child.FindFootprintByReference(r.GetReference()).FindPadByNumber('1').SetNetCode(0)
    elif fault=='face':child.FindFootprintByReference(r.GetReference()).Flip(pcbnew.VECTOR2I(0,0),False)
    elif fault=='part':child.FindFootprintByReference(r.GetReference()).SetField('MPN','forged')
    elif fault=='padshape':child.FindFootprintByReference(r.GetReference()).FindPadByNumber('1').SetSize(pcbnew.VECTOR2I_MM(2,2))
    elif fault=='population':child.FindFootprintByReference(r.GetReference()).SetDNP(True)
    with pytest.raises(ValueError):op.requests(b,child,proposal)


def test_two_exact_requests_preserve_aggregate_rail_floor(tmp_path,monkeypatch):
    import cec_decoupler_cell as cells
    b,m,c,r,s,root,tree,poses=fixture(tmp_path,monkeypatch);q=op.plan(b,poses,board_hint=str(root))
    monkeypatch.setattr(cells,'_supply_current_widths',lambda board,net:dict(
        required_by_layer_nm={int(l):800000 for l in board.GetEnabledLayers().CuStack()},current_authority={'amps':1.}))
    req=op.requests(b,pcbnew.LoadBoard(b.GetFileName()),dict(poses=poses,selected_control_pullups=q,board_hint=str(root)))
    assert len(req)==2 and {v['role']for v in req.values()}=={'control_signal','nonload_pullup_supply'}
    supply=next(v for v in req.values()if v['role']=='nonload_pullup_supply')
    assert supply['width_nm']>=800000 and supply['new_barrel_authority']is False
    assert supply['class_only_supply_prefix_authority']is False
    assert supply['unchanged_full_rail_current_contract']['current_authority']=={'amps':1.}


@pytest.mark.parametrize('timeout',[True,0,-1,11,float('nan')])
def test_bounded_context(tmp_path,monkeypatch,timeout):
    b,m,c,r,s,root,tree,poses=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):op.plan(b,poses,board_hint=str(root),timeout_s=timeout)
