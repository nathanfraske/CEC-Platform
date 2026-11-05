"""Critical terminal space is source-derived and can never become copper."""
import copy
import math
import json
import pcbnew
import pytest
import cec_force_current as force
import cec_field_coupling as field
import cec_future_pair_terminal_reservations as future
import cec_future_power_reservations as removal
from cec_native_items import discard_items
from test_lastmile import _board


def fixture(tmp_path,rotation=0,mirror=False):
    board=_board([],edge=(0,0,40,40));board.SetCopperLayerCount(6)
    properties=board.GetProperties();properties['CEC_FAB_PROFILE']='jlcpcb_6l_pofv_signal';board.SetProperties(properties)
    for name in ('/DIFFERENT/CAN_H','/DIFFERENT/CAN_L'):board.Add(pcbnew.NETINFO_ITEM(board,name))
    def transformed(point):
        x,y=point[0]/1e6-16,point[1]/1e6-16
        if mirror:x=-x
        angle=math.radians(rotation)
        return [round((16+x*math.cos(angle)-y*math.sin(angle))*1e6),
            round((16+x*math.sin(angle)+y*math.cos(angle))*1e6)]
    lands=[]
    for ref,locations in [('RENAMED_HEADER',[(13270000,16000000),(10730000,16000000)]),
            ('OTHER_ENDPOINT',[(20000000,24000000),(20450000,24000000)])]:
        fp=pcbnew.FOOTPRINT(board);fp.SetReference(ref);board.Add(fp)
        for index,(net,at) in enumerate(zip(('/DIFFERENT/CAN_H','/DIFFERENT/CAN_L'),locations),1):
            pad=pcbnew.PAD(fp);pad.SetNumber(str(index));pad.SetNetCode(board.GetNetcodeFromNetname(net))
            pad.SetPosition(pcbnew.VECTOR2I(*transformed(at)));pad.SetSize(pcbnew.VECTOR2I_MM(1.7,1.7))
            pad.SetAttribute(pcbnew.PAD_ATTRIB_PTH);pad.SetLayerSet(pcbnew.PAD.PTHMask());pad.SetDrillSize(pcbnew.VECTOR2I_MM(1,1))
            fp.Add(pad)
            if ref=='RENAMED_HEADER':lands.append(force._uid(pad))
    source=tmp_path/'source.kicad_pcb'
    source.with_suffix('.kicad_pro').write_text(json.dumps(dict(net_settings=dict(classes=[
        dict(name='CAN',diff_pair_width=.25,diff_pair_gap=.2,track_width=.25,
            clearance=.2,via_diameter=.6,via_drill=.3),
        dict(name='Default',track_width=.25,clearance=.2,via_diameter=.6,via_drill=.3)]))))
    field._save_field_snapshot(board,source);digest=force._hash(source)
    import cec_precision_route as precision
    pair=next(p for p in precision.derive_coupled_pairs(str(source),board=board)
        if p['p']=='/DIFFERENT/CAN_H' and p['n']=='/DIFFERENT/CAN_L')
    request=dict(source_sha256=digest,pair=pair['name'],layer='In2.Cu',p_pad_uuid=lands[0],n_pad_uuid=lands[1],
        p_points_nm=list(map(transformed,[[13270000,16000000],[13270000,15000000],[12225000,13955000],[12225000,12000000]])),
        n_points_nm=list(map(transformed,[[10730000,16000000],[10730000,15000000],[11775000,13955000],[11775000,12000000]])))
    return source,board,request


@pytest.mark.parametrize('rotation',[0,90,180,270])
@pytest.mark.parametrize('mirror',[False,True])
def test_rotated_or_mirrored_actual_terminal_reserves_both_members_and_must_be_removed(tmp_path,rotation,mirror):
    source,board,q=fixture(tmp_path,rotation,mirror);before=source.read_bytes()
    ghosts,proof=future.construct(board,source,[q],source_sha256=force._hash(source),
        blocked_net='/ordinary_control',board_hint='synthetic')
    assert len(ghosts)==6 and len(proof['source_terminal_contracts'])==2
    assert all(t.GetWidth()==250000 and t.IsLocked() and t.GetLayer()==pcbnew.In2_Cu for t in ghosts)
    assert not proof['saved_copper_authority'] and not proof['retirement_authority']
    assert not proof['coupling_or_reference_qualified'] and not proof['release_authority']
    with pytest.raises(ValueError,match='leaked'):removal.require_removed(board,proof)
    discard_items(board,ghosts);assert removal.require_removed(board,proof)['ok']
    assert not list(board.GetTracks()) and source.read_bytes()==before


@pytest.mark.parametrize('fault',['hash','pair','power_layer','wrong_land','live_motion','live_dnp',
    'pad_size','drill','extra_width','off_land','non45','duplicate','same_member','cross','outside'])
def test_missing_authority_changed_lands_and_invalid_paths_are_rejected_before_any_ghost(tmp_path,fault):
    source,board,q=fixture(tmp_path);q=copy.deepcopy(q)
    if fault=='hash':q['source_sha256']='0'*64
    elif fault=='pair':q['pair']='NOT_DECLARED'
    elif fault=='power_layer':q['layer']='In3.Cu'
    elif fault=='wrong_land':q['p_pad_uuid']='missing'
    elif fault=='live_motion':
        pad=next(p for f in board.GetFootprints() for p in f.Pads() if force._uid(p)==q['p_pad_uuid'])
        pad.Move(pcbnew.VECTOR2I_MM(.1,0))
    elif fault=='live_dnp':board.FindFootprintByReference('RENAMED_HEADER').SetDNP(True)
    elif fault in ('pad_size','drill'):
        pad=next(p for f in board.GetFootprints() for p in f.Pads() if force._uid(p)==q['p_pad_uuid'])
        if fault=='pad_size':pad.SetSize(pcbnew.VECTOR2I_MM(2,2))
        else:pad.SetDrillSize(pcbnew.VECTOR2I_MM(.8,.8))
    elif fault=='extra_width':q['width']=.1
    elif fault=='off_land':q['p_points_nm'][0][0]+=100000
    elif fault=='non45':q['p_points_nm'][1][0]+=100000
    elif fault=='duplicate':pass
    elif fault=='same_member':q['n_pad_uuid']=q['p_pad_uuid']
    elif fault=='cross':q['n_points_nm'][-1]=q['p_points_nm'][-1]
    elif fault=='outside':q['p_points_nm'][-1]=[12225000,-1000000]
    before=source.read_bytes()
    with pytest.raises(ValueError):future.construct(board,source,[q,q] if fault=='duplicate' else [q],
        source_sha256=force._hash(source),blocked_net='/ordinary_control',board_hint='synthetic')
    assert not list(board.GetTracks()) and source.read_bytes()==before


def test_pair_member_itself_cannot_receive_foreign_pair_reservation(tmp_path):
    source,board,q=fixture(tmp_path)
    with pytest.raises(ValueError,match='foreign_nonpower'):
        future.construct(board,source,[q],source_sha256=force._hash(source),blocked_net='/DIFFERENT/CAN_H',board_hint='synthetic')
    assert not list(board.GetTracks())
