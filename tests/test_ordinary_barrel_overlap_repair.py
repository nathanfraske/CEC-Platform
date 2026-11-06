"""Source pad-overlap debt may be repaired, never transported or waived."""
import pcbnew
import pytest
import cec_field_coupling as field
import cec_ordinary_barrel_reseat as reseat
import cec_force_current as force
from test_ordinary_barrel_reseat import fixture


def overlap_fixture(tmp_path,back=False,name='A'):
    source,target,uid=fixture(tmp_path,rename=name)
    old_source=pcbnew.LoadBoard(str(source));old_target=pcbnew.LoadBoard(str(target))
    old_ids={force._uid(t)for t in old_source.GetTracks()}
    additions=[t for t in old_target.GetTracks()if force._uid(t)not in old_ids]
    for path in (source,):
        b=pcbnew.LoadBoard(str(path))
        props=b.GetProperties();props['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';b.SetProperties(props)
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('PAD_'+name)
        pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        pad.SetShape(pcbnew.PAD_SHAPE_RECT);pad.SetSize(pcbnew.VECTOR2I_MM(.4,.4))
        pad.SetPosition(pcbnew.VECTOR2I_MM(10.3 if back else 9.7,8))
        ls=pcbnew.LSET();ls.AddLayer(pcbnew.B_Cu if back else pcbnew.F_Cu);pad.SetLayerSet(ls)
        pad.SetNet(b.FindNet('/ordinary_'+name));fp.Add(pad);b.Add(fp)
        if back:fp.SetLayer(pcbnew.B_Cu)
        field._save_field_snapshot(b,path)
    child=pcbnew.LoadBoard(str(source))
    q=reseat.plan(child,source,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True,repair_source_pad_overlap=True)
    reseat.subtract(child,source,q)
    for item in additions:
        if item.GetClass()=='PCB_VIA':
            clone=pcbnew.PCB_VIA(child);clone.SetPosition(item.GetPosition());clone.SetWidth(600000);clone.SetDrill(300000)
            clone.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);clone.SetViaType(pcbnew.VIATYPE_THROUGH)
        else:
            clone=pcbnew.PCB_TRACK(child);clone.SetStart(item.GetStart());clone.SetEnd(item.GetEnd());clone.SetLayer(item.GetLayer());clone.SetWidth(item.GetWidth())
        clone.SetNet(child.FindNet('/ordinary_'+name))
        child.Add(clone)
    field._save_field_snapshot(child,target)
    return source,target,uid


@pytest.mark.parametrize('back,name',[(False,'Renamed'),(True,'Different')])
def test_partial_overlap_corrected_with_original_pad_retained(tmp_path,back,name):
    source,target,uid=overlap_fixture(tmp_path,back,name)
    b=pcbnew.LoadBoard(str(source))
    with pytest.raises(ValueError):reseat.plan(b,source,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True)
    q=reseat.plan(b,source,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True,repair_source_pad_overlap=True)
    assert q['mandatory_source_pad_reference']=='PAD_'+name
    proof=reseat.receive(source,target,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True,repair_source_pad_overlap=True)
    assert proof['ok'],proof
    assert not proof['release_authority'] and proof['full_saved_board_receiving_still_required']


@pytest.mark.parametrize('value',[1,0,None,'yes',[],{}])
def test_overlap_repair_requires_strict_bool(tmp_path,value):
    source,target,uid=overlap_fixture(tmp_path)
    with pytest.raises(ValueError):reseat.plan(pcbnew.LoadBoard(str(source)),source,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True,repair_source_pad_overlap=value)
    assert not reseat.receive(source,target,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True,repair_source_pad_overlap=value)['ok']


@pytest.mark.parametrize('fault',['contained','foreign','second_pad','small','group','tee','destination'])
def test_overlap_repair_cannot_borrow_ownership_or_preserve_bad_destination(tmp_path,fault):
    source,target,uid=overlap_fixture(tmp_path)
    path=target if fault=='destination' else source;b=pcbnew.LoadBoard(str(path))
    fp=next(f for f in b.GetFootprints()if f.GetReference()=='PAD_A');pad=next(iter(fp.Pads()))
    v=next(t for t in b.GetTracks()if t.GetClass()=='PCB_VIA')
    if fault=='contained':pad.SetSize(pcbnew.VECTOR2I_MM(2,2))
    elif fault=='foreign':
        net=pcbnew.NETINFO_ITEM(b,'/foreign');b.Add(net);pad.SetNet(net)
    elif fault=='second_pad':copy=pcbnew.Cast_to_FOOTPRINT(fp.Duplicate(False));copy.SetReference('OTHER');b.Add(copy)
    elif fault=='small':v.SetWidth(350000);v.SetDrill(250000)
    elif fault=='group':g=pcbnew.PCB_GROUP(b);g.AddItem(v);b.Add(g)
    elif fault=='tee':
        from test_field_proposals import track
        track(b,'/ordinary_A',(9,7),(9,9))
    else:v.SetPosition(pcbnew.VECTOR2I_MM(10,8.1))
    if fault!='destination':
        with pytest.raises(ValueError):reseat.plan(b,source,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True,repair_source_pad_overlap=True)
        return
    field._save_field_snapshot(b,path)
    proof=reseat.receive(source,target,via_uuid=uid,board_hint='synthetic',allow_owned_locked=True,repair_source_pad_overlap=True)
    assert not proof['ok'] and proof['errors'],proof
