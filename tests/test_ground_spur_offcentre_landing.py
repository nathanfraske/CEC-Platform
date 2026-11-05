"""Actual native landing, not centre equality or tangent permission."""
import copy
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_source_class_ground_land_root_spur as spur
from test_source_class_ground_land_root_spur import fixture, save_child
from test_field_proposals import track


def offcentre(tmp_path,turn=0,back=False,nm=False):
    source,b,ids,xy=fixture(tmp_path,turn=turn,back=back)
    body=next(t for t in b.GetTracks()if force._uid(t)==ids['body'])
    point=pcbnew.VECTOR2I_MM(*xy((14.2,20)))
    if nm:
        point=body.GetStart()+pcbnew.VECTOR2I(1,0)
    body.SetStart(point)
    field._save_field_snapshot(b,source)
    return source,pcbnew.LoadBoard(str(source)),ids,xy


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_offcentre_whole_branch_saved_receive(tmp_path,turn,back):
    source,b,ids,xy=offcentre(tmp_path,turn,back)
    q=spur.plan(b,source,ids['seed'])
    assert q['retired_track_uuids']==[ids['seed'],ids['nub'],ids['body']]
    assert q['retained_root_track_uuids']==[ids['retained']]
    child=save_child(source,b,q,tmp_path)
    result=spur.receive(source,child,q,board_hint='synthetic')
    assert result['ok']and result['all_surviving_native_partitions_preserved'],result
    assert result['proved_short_ground_returns_preserved']


def test_one_nm_landing_is_not_centre_equality(tmp_path):
    source,b,ids,xy=offcentre(tmp_path,nm=True)
    assert spur.plan(b,source,ids['seed'])['retained_root_pad_uuid']==ids['root']


@pytest.mark.parametrize('fault',['outside_overlap','hidden_tee','barrel','holed','dnp','wrong_face','second_land','foreign','tangent','no_reference'])
def test_landing_never_owns_unproved_branch(tmp_path,fault):
    source,b,ids,xy=offcentre(tmp_path)
    root=b.FindFootprintByReference('RENAMED_ROOT').FindPadByNumber('2')
    if fault=='outside_overlap':track(b,'GND',(16,20),(16,22),width=.5)
    elif fault=='hidden_tee':track(b,'GND',(18,20),(18,21),width=.5)
    elif fault=='barrel':
        v=pcbnew.PCB_VIA(b);v.SetNet(b.FindNet('GND'));v.SetPosition(pcbnew.VECTOR2I_MM(17,20))
        v.SetWidth(600000);v.SetDrill(300000);v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(v)
    elif fault=='holed':
        root.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        root.SetLayerSet(pcbnew.PAD.PTHMask())
        root.SetDrillSize(pcbnew.VECTOR2I_MM(.3,.3))
    elif fault=='dnp':root.GetParentFootprint().SetDNP(True)
    elif fault=='wrong_face':
        layers=pcbnew.LSET();layers.AddLayer(pcbnew.B_Cu);root.SetLayerSet(layers)
    elif fault=='second_land':
        fp=pcbnew.FOOTPRINT(b);fp.SetReference('EXTRA');b.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('1');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(pcbnew.PAD.SMDMask());p.SetSize(pcbnew.VECTOR2I_MM(.5,.5))
        p.SetPosition(pcbnew.VECTOR2I_MM(17,20));p.SetNet(b.FindNet('GND'));fp.Add(p)
    elif fault=='foreign':root.SetNet(b.FindNet('OTHER'))
    elif fault=='tangent':
        root.SetPosition(pcbnew.VECTOR2I_MM(14.2,19.15))
    else:b.Remove(next(t for t in b.GetTracks()if force._uid(t)==ids['via']))
    field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):spur.plan(pcbnew.LoadBoard(str(source)),source,ids['seed'])


def test_offcentre_forgery_and_deadline_fail_closed(tmp_path,monkeypatch):
    source,b,ids,xy=offcentre(tmp_path);q=spur.plan(b,source,ids['seed'])
    bad=copy.deepcopy(q);bad['retained_root_position_nm'][0]+=1
    with pytest.raises(ValueError,match='stale_or_forged'):spur.subtract(b,bad)
    monkeypatch.setattr(spur.time,'monotonic',lambda:float('inf'))
    with pytest.raises(ValueError):spur.plan(b,source,ids['seed'])
