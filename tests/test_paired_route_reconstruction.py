"""Whole declared pairs never borrow ordinary-signal retirement authority."""
import pytest
from cec_paired_route_reconstruction import validate_track_scope, validate_barrel_scope


def fixture(kind='can'):
    pair = dict(name='renamed-bus',kind=kind,p='/different/P',n='/different/N',
        width=.25,gap=.2,clearance=.2)
    rows = [dict(uuid=u,net=pair[k],kind='PCB_TRACK',width_nm=250000)
        for u,k in [('a','p'),('b','p'),('c','n')]]
    rows += [dict(uuid='barrel',net=pair['p'],kind='PCB_VIA',width_nm=None),
        dict(uuid='power',net='/5V',kind='PCB_TRACK',width_nm=1000000)]
    return pair,rows


@pytest.mark.parametrize('kind',['can','usb','diff'])
def test_declared_pair_source_scope_is_independent_of_board_name(kind):
    pair,rows=fixture(kind)
    assert validate_track_scope(pair,rows,['c','a','b']) == ['a','b','c']


def test_frozen_half_bus_can_be_owned_but_receiver_still_requires_both_new_members():
    pair,rows=fixture();rows=[r for r in rows if r['uuid']!='c']
    assert validate_track_scope(pair,rows,['a','b']) == ['a','b']


@pytest.mark.parametrize('scope',[['a'],['a','b'],['a','b','c','barrel'],['a','b','c','power']])
def test_partial_source_scope_or_barrel_or_power_retirement_refused(scope):
    pair,rows=fixture()
    with pytest.raises(ValueError,match='both_members_whole_source_track_scope'):
        validate_track_scope(pair,rows,scope)


@pytest.mark.parametrize('scope',[[],['a','a'],[1],list(map(str,range(513)))])
def test_exact_retirement_inventory_is_bounded(scope):
    pair,rows=fixture()
    with pytest.raises(ValueError,match='bounded_exact_pair_track'):
        validate_track_scope(pair,rows,scope)


@pytest.mark.parametrize('field,value',[('p',''),('n','/different/P'),('kind','power'),
    ('width',0),('gap',float('nan')),('clearance',float('inf')),('name',None)])
def test_missing_or_nonfinite_source_pair_authority_refused(field,value):
    pair,rows=fixture();pair[field]=value
    with pytest.raises(ValueError,match='positive_source_coupled_pair_contract'):
        validate_track_scope(pair,rows,['a','b','c'])


@pytest.mark.parametrize('net',['/different/P','/different/N'])
def test_current_and_pour_ownership_overrides_pair_label(net):
    pair,rows=fixture()
    with pytest.raises(ValueError,match='current_or_pour_owned'):
        validate_track_scope(pair,rows,['a','b','c'],protected=[net])


def test_group_tracks_cannot_be_silently_released():
    pair,rows=fixture()
    with pytest.raises(ValueError,match='group_owned_pair_tracks'):
        validate_track_scope(pair,rows,['a','b','c'],grouped=['a'])


def test_source_width_is_not_reinterpreted_as_new_authority():
    pair,rows=fixture();rows[0]['width_nm']=200000
    with pytest.raises(ValueError,match='width_disagrees'):
        validate_track_scope(pair,rows,['a','b','c'])


@pytest.mark.parametrize('width_nm',[150000,300000,750000])
def test_explicit_whole_pair_rebuild_can_retire_a_nonconforming_old_width(width_nm):
    pair,rows=fixture('usb');rows[0]['width_nm']=width_nm
    assert validate_track_scope(pair,rows,['a','b','c'],allow_source_width_repair=True)==['a','b','c']
    assert pair['width']==.25  # Old geometry never becomes the new contract.
    with pytest.raises(ValueError,match='whole_source_track_scope'):
        validate_track_scope(pair,rows,['a','c'],allow_source_width_repair=True)
    with pytest.raises(ValueError,match='current_or_pour_owned'):
        validate_track_scope(pair,rows,['a','b','c'],protected=[pair['p']],allow_source_width_repair=True)
    with pytest.raises(ValueError,match='group_owned_pair_tracks'):
        validate_track_scope(pair,rows,['a','b','c'],grouped=['a'],allow_source_width_repair=True)


@pytest.mark.parametrize('value',[None,0,1,'true',[],{}])
def test_source_width_repair_requires_an_explicit_boolean(value):
    pair,rows=fixture()
    with pytest.raises(ValueError,match='explicit_source_pair_width_repair_policy'):
        validate_track_scope(pair,rows,['a','b','c'],allow_source_width_repair=value)


@pytest.mark.parametrize('width_nm',[None,True,0,-1,250000.,2_000_000_001])
def test_source_width_repair_cannot_invent_or_accept_unknown_old_geometry(width_nm):
    pair,rows=fixture();rows[0]['width_nm']=width_nm
    with pytest.raises(ValueError,match='positive_actual_source_pair_track_width'):
        validate_track_scope(pair,rows,['a','b','c'],allow_source_width_repair=True)


def test_unsupported_arc_and_duplicate_native_identity_refused():
    pair,rows=fixture();rows.append(dict(uuid='arc',net=pair['p'],kind='PCB_ARC'))
    with pytest.raises(ValueError,match='unsupported_source_pair_copper'):
        validate_track_scope(pair,rows,['a','b','c'])
    pair,rows=fixture();rows.append(rows[0])
    with pytest.raises(ValueError,match='ambiguous_source_pair_inventory'):
        validate_track_scope(pair,rows,['a','b','c'])


def barrel_fixture():
    pair,rows=fixture()
    rows[-2].update(through=True,drill_nm=250000)
    rows.append(dict(uuid='second-barrel',net=pair['n'],kind='PCB_VIA',
        width_nm=None,through=True,drill_nm=300000))
    return pair,rows


@pytest.mark.parametrize('kind',['can','usb','diff'])
def test_whole_barrel_retirement_not_selected_obstacle_removal(kind):
    pair,rows=barrel_fixture();pair['kind']=kind
    assert validate_barrel_scope(pair,rows,['second-barrel','barrel'],
        factory_group='factory') == (['barrel','second-barrel'],[])


@pytest.mark.parametrize('requested',[['barrel'],['second-barrel'],['barrel','second-barrel','power']])
def test_partial_or_foreign_barrel_retirement_refused(requested):
    pair,rows=barrel_fixture()
    with pytest.raises(ValueError,match='all_source_pair_barrels'):
        validate_barrel_scope(pair,rows,requested,factory_group='factory')


@pytest.mark.parametrize('requested',[[],['barrel','barrel'],[1],list(map(str,range(129)))])
def test_whole_barrel_scope_bounded(requested):
    pair,rows=barrel_fixture()
    with pytest.raises(ValueError,match='bounded_exact_whole_pair_barrel_scope'):
        validate_barrel_scope(pair,rows,requested,factory_group='factory')


@pytest.mark.parametrize('changed',[dict(through=False),dict(through=None),dict(drill_nm=0),
    dict(drill_nm=True),dict(drill_nm=.25)])
def test_blind_or_unknown_source_barrel_cannot_be_owned(changed):
    pair,rows=barrel_fixture();rows[-1].update(changed)
    with pytest.raises(ValueError,match='positive_through_holes'):
        validate_barrel_scope(pair,rows,['barrel','second-barrel'],factory_group='factory')


def test_mixed_factory_group_only_releases_exact_pair_members():
    pair,rows=barrel_fixture()
    group=dict(name='factory',uuid='g',members=['barrel','unrelated-via'],all_members_vias=True)
    assert validate_barrel_scope(pair,rows,['barrel','second-barrel'],
        group_rows=[group],factory_group='factory') == (['barrel','second-barrel'],['g'])


@pytest.mark.parametrize('groups',[
    [dict(name='protected',uuid='g',members=['barrel'],all_members_vias=True)],
    [dict(name='factory',uuid='g',members=['barrel'],all_members_vias=False)],
    [dict(name='factory',uuid='g',members=['barrel'],all_members_vias=True),
     dict(name='factory',uuid='h',members=['second-barrel'],all_members_vias=True)]])
def test_opaque_or_ambiguous_native_group_is_not_release_authority(groups):
    pair,rows=barrel_fixture()
    with pytest.raises(ValueError,match='opaque_or_ambiguous_group'):
        validate_barrel_scope(pair,rows,['barrel','second-barrel'],
            group_rows=groups,factory_group='factory')


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_native_whole_pair_scope_owns_only_renamed_rotated_signal_material(angle):
    import contextlib
    import math
    from unittest import mock
    import pcbnew
    import cec_force_current as force
    import cec_fr as fr
    import cec_precision_route as precision
    import cec_current_topology as topology
    import cec_synth_pipeline as synth
    import cec_paired_route_reconstruction as owned
    board=pcbnew.CreateEmptyBoard()
    pair,unused=fixture('usb');nets={}
    for name in (pair['p'],pair['n'],'different-power'):
        net=pcbnew.NETINFO_ITEM(board,name);board.Add(net);nets[name]=net
    def at(x,y):
        a=math.radians(angle)
        return pcbnew.VECTOR2I_MM(40+x*math.cos(a)-y*math.sin(a),
            30+x*math.sin(a)+y*math.cos(a))
    for x in (0,10):
        fp=pcbnew.FOOTPRINT(board);fp.SetReference('unfamiliar'+str(x))
        for member,y in (('p',0),('n',1)):
            pad=pcbnew.PAD(fp);pad.SetNumber(member);pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
            pad.SetLayerSet(pcbnew.PAD.SMDMask());pad.SetShape(pcbnew.PAD_SHAPE_RECT)
            pad.SetSize(pcbnew.VECTOR2I_MM(1,1));pad.SetPosition(at(x,y))
            pad.SetNet(nets[pair[member]]);fp.Add(pad)
        board.Add(fp)
    vias=[];tracks=[]
    group=pcbnew.PCB_GROUP(board);group.SetName(fr.LOCAL_POFV_SIGNAL_VIA_GROUP);board.Add(group)
    for name,y in ((pair['p'],0),(pair['n'],1),('different-power',5)):
        track=pcbnew.PCB_TRACK(board);track.SetStart(at(0,y));track.SetEnd(at(2,y))
        track.SetWidth(250000 if name!='different-power' else 1000000)
        track.SetLayer(pcbnew.F_Cu);track.SetNet(nets[name]);board.Add(track);tracks.append(track)
        via=pcbnew.PCB_VIA(board);via.SetViaType(pcbnew.VIATYPE_THROUGH)
        via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);via.SetWidth(600000);via.SetDrill(300000)
        via.SetPosition(at(2,y));via.SetNet(nets[name]);board.Add(via);group.AddItem(via);vias.append(via)
    with mock.patch.object(precision,'derive_coupled_pairs',return_value=[pair]), \
            mock.patch.object(force,'_thermal_hint',return_value=contextlib.nullcontext()), \
            mock.patch.object(topology,'board_current_domains',return_value={}), \
            mock.patch.object(synth,'spec_net_current_contract',return_value=None):
        plan=owned.plan(board,'standalone.kicad_pcb',board_hint='renamed-source',
            pair_name=pair['name'],retired_via_uuids=[force._uid(v) for v in vias[:2]])
    assert plan['retired_track_uuids']==sorted(force._uid(t) for t in tracks[:2])
    assert plan['retired_via_uuids']==sorted(force._uid(v) for v in vias[:2])
    assert plan['source_local_factory_group_uuids']==[force._uid(group)]
    assert plan['retained_pair_via_uuids']==[]
    assert not plan['external_lands_retired']
    assert len(list(board.GetTracks()))==6  # Planner is read-only.
