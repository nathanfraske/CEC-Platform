"""Native saved GND joining is not a cleanup partition-preservation waiver."""
import copy
import json
import pcbnew
import pytest
import cec_ground_component_join as op
import cec_force_current as force
import cec_field_coupling as field
import cec_additive_route_receiving as additive
import cec_device_power_roles as roles
import time
from cec_native_items import discard_items
from test_native_ground_terminal_branch import fixture as branch_fixture
from test_field_proposals import track


def test_disconnected_native_fill_island_is_not_whole_zone_root_credit(tmp_path):
    import cec_native_fill_geometry as fill
    b,source,owner,cap,via=fixture(tmp_path)
    zone=next(iter(b.Zones()));face=zone.GetLayer()
    shape=zone.GetFilledPolysList(face).CloneDropTriangulation()
    stripe=fill.reconstruct([[[[20000000,0],[21000000,0],[21000000,30000000],[20000000,30000000]]]],time.monotonic()+2.)
    shape.BooleanSubtract(stripe);assert shape.OutlineCount()==2
    zone.SetFilledPolysList(face,shape);zone.SetIsFilled(True)
    ctx=op._context(b,'synthetic',time.monotonic()+5.)
    assert len(ctx['ground'])==3 and len(ctx['islands'])==1
    other=[p for p in ctx['ground']if p!=ctx['root']and p not in ctx['islands']]
    assert len(other)==1 and all(ctx['live'][k].GetClass()=='ZONE'for k in other[0])
    pad=next(p for p in owner.Pads()if p.GetNetname()=='GND')
    assert not op._physical_root_reached(b,pad,ctx,time.monotonic()+5.)


def fixture(tmp_path,quarter=0,layer=pcbnew.F_Cu):
    b,source,ids,points,owner,cap,via=branch_fixture(tmp_path,quarter=quarter,layer=layer)
    # KiCad's detached default NETCLASS proxy can be shared by synthetic
    # boards in one process; reset actual fixture authority between cases.
    b.GetNetInfo().GetNetItem('GND').GetNetClassSlow().SetTrackWidth(200000)
    discard_items(b,[t for t in b.GetTracks() if force._uid(t) in ids])
    # Main-root trunk remains connected to an existing through axis and both
    # actual native filled reference planes. No new barrel is requested.
    x,y=tuple(via.GetPosition())
    track(b,'GND',(x/1e6,y/1e6),(x/1e6+2,y/1e6),layer=layer,width=.5)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    return b,source,owner,cap,via


def construct(tmp_path,**kw):
    b,source,*_=fixture(tmp_path,**kw)
    before=source.read_bytes();q=op.plan(b,board_hint='synthetic',timeout_s=10.)
    assert q['complete'] and q['ops'],q
    old={force._uid(t)for t in b.GetTracks()}
    op.construct_private(b,q,board_hint='synthetic')
    added={force._uid(t)for t in b.GetTracks()}-old
    assert added
    assert all(t.GetClass()=='PCB_TRACK' and t.GetNetname()=='GND'for t in b.GetTracks()if force._uid(t)in added)
    additive._ground_refill(b);child=force._copy_family(source,tmp_path/'child')
    field._save_field_snapshot(b,child)
    assert source.read_bytes()==before
    return source,child,q,added


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('layer',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_real_native_ground_merge_has_no_new_barrels_or_source_retirement(tmp_path,quarter,layer):
    source,child,q,added=construct(tmp_path,quarter=quarter,layer=layer)
    before=source.read_bytes();r=op.receive(source,child,board_hint='synthetic',timeout_s=10.)
    assert r['ok'] and r['complete'],r
    assert source.read_bytes()==before
    assert not r.get('current_qualified',False) and not r.get('release_authority',False)


@pytest.mark.parametrize('fault',['new_via','non_ground','raw_diagonal','old_source_overwrite',
    'no_progress','demotion','ungrouped','old_thin'])
def test_saved_join_receiver_rejects_out_of_scope_or_unreceived_material(tmp_path,fault):
    source,child,q,added=construct(tmp_path)
    b=pcbnew.LoadBoard(str(child));new=[t for t in b.GetTracks()if force._uid(t)in added]
    t=next(t for t in new if t.GetClass()=='PCB_TRACK')
    if fault=='new_via':
        via=pcbnew.PCB_VIA(b);via.SetPosition(t.GetStart());via.SetWidth(600000);via.SetDrill(300000)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetNet(b.FindNet('GND'));b.Add(via)
    elif fault=='non_ground':t.SetNet(b.FindNet('+3V3'))
    elif fault=='raw_diagonal':t.SetEnd(t.GetEnd()+pcbnew.VECTOR2I(1,2))
    elif fault=='old_source_overwrite':
        next(t for t in b.GetTracks()if force._uid(t)not in added and t.GetClass()=='PCB_TRACK').SetWidth(123456)
    elif fault=='no_progress':discard_items(b,new)
    elif fault=='demotion':discard_items(b,[next(t for t in b.GetTracks()if t.GetClass()=='PCB_VIA')])
    elif fault=='ungrouped':
        t.SetWidth(100000)
        for group in list(b.Groups()):
            if group.ContainsItem(t):group.RemoveItem(t)
    elif fault=='old_thin':
        # Existing source metal may not acquire endpoint permission merely
        # because a new joining group exists elsewhere in the saved child.
        old=pcbnew.LoadBoard(str(source));oldtrack=next(t for t in old.GetTracks()if t.GetNetname()=='GND')
        oldtrack.SetWidth(100000);field._save_field_snapshot(old,source)
    if fault=='non_ground':pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(child),b)
    else:field._save_field_snapshot(b,child)
    r=op.receive(source,child,board_hint='synthetic',timeout_s=10.)
    assert not r['ok'] and not r['complete'],r


@pytest.mark.parametrize('fault',['deadline','too_long','no_planes','untyped','converter'])
def test_source_plan_needs_bounded_positive_ground_kernel(tmp_path,fault):
    b,source,owner,cap,via=fixture(tmp_path);kw={}
    if fault=='deadline':kw['timeout_s']=0
    elif fault=='too_long':kw['max_length_mm']=.01
    elif fault=='no_planes':
        for z in list(b.Zones()):b.Remove(z)
    elif fault=='untyped':owner.SetValue('UNKNOWN_PART')
    elif fault=='converter':owner.SetValue('TPS2121RUXR')
    before=field._field_snapshot_inventory(b)
    try:q=op.plan(b,board_hint='synthetic',**kw)
    except ValueError:q={'complete':False}
    assert not q['complete'],q
    assert field._field_snapshot_inventory(b)==before


def test_real_full_class_fine_ground_launch_has_independently_received_prefix(tmp_path):
    b,source,owner,cap,via=fixture(tmp_path)
    klass=b.GetNetInfo().GetNetItem('GND').GetNetClassSlow()
    klass.SetTrackWidth(500000)
    # Native class authority, not a mocked geometry oracle. A neighbouring
    # foreign land leaves a fine escape but obstructs a full-class launch.
    ground=owner.FindPadByNumber('7');pos=ground.GetPosition()
    fp=pcbnew.FOOTPRINT(b);fp.SetReference('FOREIGN_NEIGHBOUR');b.Add(fp)
    pad=pcbnew.PAD(fp);pad.SetNumber('1');pad.SetNet(b.FindNet('+3V3'))
    pad.SetPosition(pos+pcbnew.VECTOR2I(0,500000));pad.SetSize(pcbnew.VECTOR2I(300000,300000))
    pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD);pad.SetShape(pcbnew.PAD_SHAPE_RECT)
    pad.SetLayerSet(pcbnew.PAD.SMDMask());fp.Add(pad)
    other=pad.Duplicate();other.m_Uuid.Clone(pcbnew.KIID());other.SetNumber('2')
    other.SetPosition(pos+pcbnew.VECTOR2I(0,-500000));fp.Add(other)
    for index,dy in enumerate((-500000,500000),3):
        extra=pad.Duplicate();extra.m_Uuid.Clone(pcbnew.KIID());extra.SetNumber(str(index))
        extra.SetPosition(pos+pcbnew.VECTOR2I(1500000,dy));fp.Add(extra)
    assert op.cells._netclass(b,'GND')['width']==500000
    binding=field._field_snapshot_inventory(b)
    q=op.plan(b,board_hint='synthetic',timeout_s=10.)
    assert field._field_snapshot_inventory(b)==binding
    assert q['complete'] and q['ops'],json.dumps(q,default=str)
    if q['complete']:
        added=op.construct_private(b,q,board_hint='synthetic')
        tracks=[t for t in added if t.GetClass()=='PCB_TRACK']
        assert tracks
        # Every emitted narrow track is actually grouped and qualified;
        # planning success alone must not license an invalid endpoint.
        proof=op.endpoints.receive(b,b,op._typed_requests(b,'synthetic'),tracks,
            board_hint='synthetic',deadline=__import__('time').monotonic()+10)
        narrow={force._uid(t)for t in tracks if t.GetWidth()<500000}
        assert narrow,'fixture must exercise actual thin endpoint copper, not a full-class alternative'
        assert narrow<=set(proof['track_uuids'])
    else:
        assert not q.get('ops'),q


def optional_fixture(tmp_path,package='D',quarter=0):
    b,source,owner,cap,via=fixture(tmp_path,quarter=quarter)
    ground=owner.FindPadByNumber('7');supply=owner.FindPadByNumber('6')
    ground.SetNumber('2'if package=='D'else'4');supply.SetNumber('6'if package=='D'else'5')
    owner.SetReference('RENAMED_SENSOR');owner.SetValue('INA240A3')
    owner.SetField('MPN','INA240A3DR'if package=='D'else'INA240A3PWR')
    owner.SetFPID(pcbnew.LIB_ID('Package_SO','SOIC-8_3.9x4.9mm_P1.27mm'if package=='D'else'TSSOP-8_3x3mm_P0.65mm'))
    nc=ground.Duplicate();nc.m_Uuid.Clone(pcbnew.KIID());nc.SetNumber('4'if package=='D'else'1')
    # The optional land touches the ORIGINAL external owner/cap strap. No
    # internal package connection is invented to qualify this component.
    link=next(t for t in b.GetTracks()if t.GetClass()=='PCB_TRACK'and t.GetNetname()=='GND'and t.GetWidth()==200000)
    a,z=tuple(link.GetStart()),tuple(link.GetEnd())
    nc.SetPosition(pcbnew.VECTOR2I(*[(x+y)//2 for x,y in zip(a,z)]));owner.Add(nc)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    return b,source,owner,cap,via,ground,nc


@pytest.mark.parametrize('package',['D','PW'])
@pytest.mark.parametrize('quarter',range(4))
def test_optional_ground_attachment_stays_passive_across_package_rotation_and_relabel(tmp_path,package,quarter):
    b,source,owner,cap,via,ground,nc=optional_fixture(tmp_path,package,quarter)
    model=roles.footprint_contract(owner)
    assert model['pins'][nc.GetNumber()]=='no_connect'
    assert model['pins'][ground.GetNumber()]=='ground'
    proof=roles.optional_ground_attachment_contract(owner,nc.GetNumber())
    assert proof and proof['functional_ground_return']is False
    requests=op._typed_requests(b,'synthetic')
    assert 'ground:'+force._uid(nc)not in requests
    assert 'ground:'+force._uid(ground)in requests
    context=op._context(b,'synthetic',time.monotonic()+10)
    assert any(any(context['live'][key].GetClass()=='PAD'and force._uid(context['live'][key])==force._uid(nc)
        for key in part)for part in context['islands'])
    q=op.plan(b,board_hint='synthetic');assert q['complete'],q
    assert list(force._item_key(nc))not in q.get('source_ports',[])
    op.construct_private(b,q,board_hint='synthetic');additive._ground_refill(b)
    child=force._copy_family(source,tmp_path/'optional-child');field._save_field_snapshot(b,child)
    r=op.receive(source,child,board_hint='synthetic');assert r['ok']and r['complete'],r


@pytest.mark.parametrize('fault',['singleton','unknown','contradictory_mpn'])
def test_optional_land_is_not_standalone_return_or_generic_no_connect_permission(tmp_path,fault):
    b,source,owner,cap,via,ground,nc=optional_fixture(tmp_path)
    if fault=='unknown':owner.SetValue('UNKNOWN_DEVICE');owner.SetField('MPN','UNKNOWN_DEVICE')
    elif fault=='contradictory_mpn':owner.SetField('MPN','TLV7011DBVR')
    else:
        nc.SetPosition(pcbnew.VECTOR2I(4000000,4000000))
        context=op._context(b,'synthetic',time.monotonic()+10)
        assert not any(any(context['live'][key].GetClass()=='PAD'and force._uid(context['live'][key])==force._uid(nc)
            for key in part)for part in context['islands'])
        assert 'ground:'+force._uid(nc)not in context['requests']
        return
    try:proof=roles.optional_ground_attachment_contract(owner,nc.GetNumber())
    except ValueError:proof=None
    assert not proof
