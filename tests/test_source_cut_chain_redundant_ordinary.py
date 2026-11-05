"""Compose independently typed ordinary cuts without relaxing any receiver."""
from pathlib import Path
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_source_cut_chain as chain
from cec_native_items import discard_items
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path,quarter=0,mirror=False,prefix='/neutral/'):
    net=prefix+'CONTROL'
    def point(x,y):
        x,y=x-15,y-15
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return 15+x,15+y
    b=_board([(*point(5,10),net),(*point(25,10),net)],edge=(0,0,30,30))
    trunk=track(b,net,point(5,10),point(25,10),width=.2)
    stem=track(b,net,point(15,10),point(15,12),width=.2,layer=pcbnew.B_Cu)
    stem.SetLocked(True);barrels=[]
    for xy in (point(15,10),point(15,12)):
        via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(*xy));via.SetWidth(600000);via.SetDrill(300000)
        via.SetNetCode(b.GetNetcodeFromNetname(net));via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetLocked(True);b.Add(via);barrels.append(force._uid(via))
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    ids=[barrels[1],force._uid(stem),barrels[0]];parent=source;phases=[]
    for index,uid in enumerate(ids):
        child=force._copy_family(parent,tmp_path/('stage-'+str(index)));c=pcbnew.LoadBoard(str(child))
        discard_items(c,[t for t in c.GetTracks() if force._uid(t)==uid]);field._save_field_snapshot(c,child)
        phase=dict(kind='ordinary_redundant_cut',candidate=str(child),retired_track_uuids=[],allow_locked_track_uuids=[],
            redundant_single_face_via_uuids=[],allow_locked_via_uuids=[])
        if index==1:phase.update(retired_track_uuids=[uid],allow_locked_track_uuids=[uid])
        else:phase.update(redundant_single_face_via_uuids=[uid],allow_locked_via_uuids=[uid])
        phases.append(phase);parent=child
    return source,parent,phases,ids,force._uid(trunk),net


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('prefix',['/a/','/renamed-different/'])
def test_whole_original_source_replay_receives_barrel_stem_barrel_cleanup(tmp_path,quarter,mirror,prefix):
    source,child,phases,ids,_,_=fixture(tmp_path,quarter,mirror,prefix)
    paths=[source,*[Path(p['candidate']) for p in phases]]
    snapshots=[p.read_bytes() for p in paths]
    proof=chain.receive(source,child,board_hint='synthetic',phases=phases,per_phase_leases=True)
    assert proof['ok'] and proof['complete'],proof
    assert proof['retired_track_uuids']==[ids[1]]
    assert set(proof['retired_via_uuids'])=={ids[0],ids[2]}
    assert proof['added_native_uuids']==[]
    assert proof['independently_received_subtraction_only_ordinary_cleanup']
    assert not proof['independently_received_subtraction_only_ground_echo']
    assert proof['whole_original_cut_additions_ground_and_rule_replay']['ok']
    assert not proof['release_authority'] and not proof['current_authority']
    assert snapshots==[p.read_bytes() for p in paths]


@pytest.mark.parametrize('fault',['empty','extra_switch','wrong_kind','no_track_lock','no_via_lock',
    'duplicate_via','unlisted_retirement','repeated_phase','pose','width','added_material','power'])
def test_composition_never_grants_more_scope_than_each_narrow_receiver(tmp_path,fault):
    source,child,phases,ids,trunk,net=fixture(tmp_path)
    if fault=='empty':
        phases[0]['redundant_single_face_via_uuids']=[];phases[0]['allow_locked_via_uuids']=[]
    elif fault=='extra_switch':phases[0]['allow_redundant_cut_only']=True
    elif fault=='wrong_kind':
        phases[0]=dict(kind='ordinary',candidate=phases[0]['candidate'],retired_track_uuids=[],allow_locked_track_uuids=[])
    elif fault=='no_track_lock':phases[1]['allow_locked_track_uuids']=[]
    elif fault=='no_via_lock':phases[0]['allow_locked_via_uuids']=[]
    elif fault=='duplicate_via':phases[0]['redundant_single_face_via_uuids']*=2
    elif fault=='repeated_phase':phases.insert(1,dict(phases[0]))
    elif fault=='power':
        for path in [source,*[Path(p['candidate']) for p in phases]]:
            b=pcbnew.LoadBoard(str(path));b.Add(pcbnew.NETINFO_ITEM(b,'+5V'))
            for i in [*b.GetTracks(),*(p for fp in b.GetFootprints() for p in fp.Pads())]:i.SetNetCode(b.GetNetcodeFromNetname('+5V'))
            field._save_field_snapshot(b,path)
    else:
        b=pcbnew.LoadBoard(str(child))
        if fault=='unlisted_retirement':discard_items(b,[t for t in b.GetTracks() if force._uid(t)==trunk])
        elif fault=='pose':next(iter(b.GetFootprints())).Move(pcbnew.VECTOR2I_MM(.1,0))
        elif fault=='width':next(iter(b.GetTracks())).SetWidth(300000)
        elif fault=='added_material':track(b,net,(10,10),(10,11),width=.2)
        field._save_field_snapshot(b,child)
    proof=chain.receive(source,child,board_hint='synthetic',phases=phases,per_phase_leases=True)
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof


def multilayer_fixture(tmp_path,quarter=0,mirror=False,prefix='/neutral/'):
    net=prefix+'CONTROL'
    def point(x,y):
        x,y=x-15,y-15
        if mirror:x=-x
        for _ in range(quarter):x,y=-y,x
        return 15+x,15+y
    b=_board([(*point(5,10),net),(*point(25,10),net)],edge=(0,0,30,30))
    trunk=track(b,net,point(5,10),point(25,10),width=.2)
    strokes=[track(b,net,point(10,10),point(10,12),width=.2),
        track(b,net,point(10,12),point(20,12),width=.2,layer=pcbnew.B_Cu),
        track(b,net,point(20,12),point(20,10),width=.2)]
    vias=[]
    for xy in (point(10,12),point(20,12)):
        via=pcbnew.PCB_VIA(b);via.SetPosition(pcbnew.VECTOR2I_MM(*xy));via.SetWidth(600000);via.SetDrill(300000)
        via.SetNetCode(b.GetNetcodeFromNetname(net));via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetLocked(True);b.Add(via);vias.append(via)
    for t in strokes:t.SetLocked(True)
    source=tmp_path/'source'/'board.kicad_pcb';source.parent.mkdir();field._save_field_snapshot(b,source)
    ids=[force._uid(t) for t in strokes];barrels=[force._uid(v) for v in vias]
    child=force._copy_family(source,tmp_path/'final');c=pcbnew.LoadBoard(str(child))
    discard_items(c,[t for t in c.GetTracks() if force._uid(t) in set(ids+barrels)])
    field._save_field_snapshot(c,child)
    phase=dict(kind='ordinary_redundant_cut',candidate=str(child),retired_track_uuids=ids,
        allow_locked_track_uuids=ids,retired_via_uuids=barrels,
        redundant_single_face_via_uuids=[],allow_locked_via_uuids=barrels)
    return source,child,phase,ids,barrels,force._uid(trunk)


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
@pytest.mark.parametrize('prefix',['/a/','/renamed-different/'])
def test_atomic_original_multilayer_obsolete_branch_retains_native_trunk(tmp_path,quarter,mirror,prefix):
    source,child,phase,ids,vias,_=multilayer_fixture(tmp_path,quarter,mirror,prefix)
    before=[p.read_bytes() for p in (source,child)]
    proof=chain.receive(source,child,board_hint='synthetic',phases=[phase])
    assert proof['ok'] and proof['complete'],proof
    assert set(proof['retired_track_uuids'])==set(ids) and set(proof['retired_via_uuids'])==set(vias)
    assert proof['independently_received_subtraction_only_ordinary_cleanup']
    assert proof['phase_receiving'][0]['proof']['exclusive_retired_via_ownership']
    assert before==[p.read_bytes() for p in (source,child)]


@pytest.mark.parametrize('fault',['duplicate','overlap_roles','too_many','missing_lock','wrong_role',
    'grouped','extra_track','extra_material','pad_contact'])
def test_exclusive_multilayer_cut_never_infers_barrel_authority(tmp_path,fault):
    source,child,phase,ids,vias,trunk=multilayer_fixture(tmp_path)
    if fault=='duplicate':phase['retired_via_uuids']*=2
    elif fault=='overlap_roles':phase['redundant_single_face_via_uuids']=[vias[0]]
    elif fault=='too_many':phase['retired_via_uuids']+=['foreign-'+str(i) for i in range(3)]
    elif fault=='missing_lock':phase['allow_locked_via_uuids']=[]
    elif fault=='wrong_role':
        phase['redundant_single_face_via_uuids']=vias;phase['retired_via_uuids']=[]
    elif fault in ('grouped','pad_contact'):
        b=pcbnew.LoadBoard(str(source));v=next(t for t in b.GetTracks() if force._uid(t)==vias[0])
        if fault=='grouped':
            group=pcbnew.PCB_GROUP(b);group.SetName('unowned');b.Add(group);group.AddItem(v)
        else:
            fp=pcbnew.FOOTPRINT(b);fp.SetReference('NEW');b.Add(fp)
            pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            layers=pcbnew.LSET();layers.AddLayer(pcbnew.F_Cu)
            pad.SetLayerSet(layers);pad.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
            pad.SetSize(pcbnew.VECTOR2I(300000,300000));pad.SetPosition(v.GetPosition())
            pad.SetNetCode(v.GetNetCode());fp.Add(pad)
        field._save_field_snapshot(b,source)
    else:
        b=pcbnew.LoadBoard(str(child))
        if fault=='extra_track':discard_items(b,[t for t in b.GetTracks() if force._uid(t)==trunk])
        else:track(b,'/neutral/CONTROL',(8,10),(8,11),width=.2)
        field._save_field_snapshot(b,child)
    proof=chain.receive(source,child,board_hint='synthetic',phases=[phase])
    assert not proof['ok'] and not proof['complete'] and proof['errors'],proof
