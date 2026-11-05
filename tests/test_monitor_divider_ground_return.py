"""Renamed F/B monitor returns, exact saved material and bounded leases."""
import copy,importlib.util,json
from pathlib import Path
import cec_swig_guard
cec_swig_guard.pin()
import wx
quiet=wx.LogNull()
import pcbnew
import pytest
import cec_field_coupling as field
import cec_force_current as force
import cec_additive_route_receiving as additive
import time
from test_source_divider_ground_span import fixture as canonical_fixture
from test_ground_component_join import fixture as base_fixture

import cec_monitor_divider_ground_return as op


def fixture(tmp_path,monkeypatch,*,bottom=False):
    layer=pcbnew.B_Cu if bottom else pcbnew.F_Cu
    b,source,_,_,via=base_fixture(tmp_path,layer=layer)
    via.SetWidth(900000);via.SetDrill(500000)
    def pad(ref,net,point):
        fp=pcbnew.FOOTPRINT(b);fp.SetReference(ref);fp.SetLayer(layer);b.Add(fp)
        p=pcbnew.PAD(fp);p.SetNumber('2');p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetPosition(pcbnew.VECTOR2I_MM(*point));p.SetSize(pcbnew.VECTOR2I_MM(1.2,1.2));p.SetNet(b.FindNet(net))
        ls=pcbnew.LSET();ls.AddLayer(layer);p.SetLayerSet(ls);fp.Add(p);return p
    root=pad('RENAMED_EXISTING_ROOT','GND',(12,12));lower=pad('RENAMED_DIVIDER_LOWER','GND',(20,20))
    b.GetNetInfo().GetNetItem('GND').GetNetClassSlow().SetTrackWidth(500000)
    additive._ground_refill(b);field._save_field_snapshot(b,source)
    pro=dict(net_settings=dict(classes=[dict(name='Ground',track_width=.5,clearance=.2,via_diameter=.9,via_drill=.5)],
        netclass_assignments={'GND':'Ground'},netclass_patterns=[dict(netclass='Ground',pattern='GND')]))
    source.with_suffix('.kicad_pro').write_text(json.dumps(pro))
    uid=force._uid(lower)
    def catalog(board,hint,pad_uuid,deadline):
        if pad_uuid!=uid:raise ValueError('synthetic_positive_source_catalog_scope')
        ground=next(p for fp in board.GetFootprints()for p in fp.Pads()if force._uid(p)==uid)
        return ground,dict(kind='synthetic_canonical_catalog_only',ground_pad_uuid=uid,
            schematic_files_sha256={str(source):force._hash(source)},
            exporter=dict(path=str(Path(__file__)),sha256=force._hash(Path(__file__))))
    monkeypatch.setattr(op,'_source_owner',catalog)
    return source,uid


@pytest.mark.parametrize('bottom',[False,True])
def test_complete_native_saved_join_with_exact_source_class_no_holes(tmp_path,monkeypatch,bottom):
    source,uid=fixture(tmp_path,monkeypatch,bottom=bottom);raw=source.read_bytes()
    q=op.plan(source,board_hint='synthetic',ground_pad_uuid=uid)
    assert all(r['width_nm']==500000 for r in q['rows'])and q['new_holes']==q['source_cuts']==0
    assert q['preflight']['child_ground_components']==q['preflight']['source_ground_components']-1
    assert not q['current_qualified']and not q['routing_admitted']
    # Saved proposal identity must survive ordinary JSON, not RAM tuples.
    q=json.loads(json.dumps(q))
    artifact=op.construct_private(source,q,tmp_path/'private')
    r=op.receive(source,artifact['candidate'],board_hint='synthetic',ground_pad_uuid=uid)
    assert r['ok']and r['complete'],r
    assert set(r['timings_s'])==set(r['bounded_composition']['constituents'])
    assert all(0<=v<10 for v in r['timings_s'].values())
    assert not r['routing_admitted']and not r['release_authority']
    assert source.read_bytes()==raw


@pytest.mark.parametrize('fault',['missing_role','missing_project','zero_class','wrong_class','no_root_pad','new_foreign_wall',
    'foreign_fill','unknown_fill','extra_ground_component','already_connected'])
def test_source_eligibility_and_geometry_are_not_caller_permissions(tmp_path,monkeypatch,fault):
    source,uid=fixture(tmp_path,monkeypatch)
    if fault=='missing_role':
        def refuse(*a,**k):raise ValueError('no_positive_canonical_source')
        monkeypatch.setattr(op,'_source_owner',refuse)
    elif fault=='missing_project':source.with_suffix('.kicad_pro').unlink()
    elif fault in('zero_class','wrong_class'):
        p=source.with_suffix('.kicad_pro');q=json.loads(p.read_text());q['net_settings']['classes'][0]['track_width']=0 if fault=='zero_class'else 3
        p.write_text(json.dumps(q))
    else:
        b=pcbnew.LoadBoard(str(source));pad=next(p for fp in b.GetFootprints()for p in fp.Pads()if force._uid(p)==uid)
        if fault=='no_root_pad':
            next(fp for fp in b.GetFootprints()if fp.GetReference()=='RENAMED_EXISTING_ROOT').Move(pcbnew.VECTOR2I(1000000,0))
        elif fault=='already_connected':
            t=pcbnew.PCB_TRACK(b);t.SetNet(pad.GetNet());t.SetLayer(pcbnew.F_Cu);t.SetWidth(500000)
            t.SetStart(pad.GetPosition());t.SetEnd(pcbnew.VECTOR2I_MM(12,12));b.Add(t)
        elif fault in('foreign_fill','unknown_fill'):
            z=pcbnew.ZONE(b);z.SetNet(b.FindNet('+3V3'));z.SetLayer(pcbnew.F_Cu);poly=pcbnew.SHAPE_POLY_SET();poly.NewOutline()
            for point in((10,15.8),(25,15.8),(25,16.2),(10,16.2)):poly.Append(pcbnew.VECTOR2I_MM(*point))
            z.Outline().Append(poly)
            if fault=='foreign_fill':z.SetFilledPolysList(pcbnew.F_Cu,poly);z.SetIsFilled(True)
            b.Add(z)
        elif fault=='extra_ground_component':
            fp=pcbnew.FOOTPRINT(b);fp.SetReference('UNOWNED_RETURN');b.Add(fp)
            p=pcbnew.PAD(fp);p.SetNumber('1');p.SetPosition(pcbnew.VECTOR2I_MM(16,16));p.SetSize(pcbnew.VECTOR2I_MM(.8,.8))
            p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetShape(pcbnew.PAD_SHAPE_RECT);p.SetNet(b.FindNet('GND'))
            ls=pcbnew.LSET();ls.AddLayer(pcbnew.F_Cu);p.SetLayerSet(ls);fp.Add(p)
        else:
            t=pcbnew.PCB_TRACK(b);t.SetNet(b.FindNet('+3V3'));t.SetLayer(pcbnew.F_Cu);t.SetWidth(5000000)
            t.SetStart(pcbnew.VECTOR2I_MM(0,16));t.SetEnd(pcbnew.VECTOR2I_MM(30,16));b.Add(t)
        field._save_field_snapshot(b,source)
    with pytest.raises(ValueError):op.plan(source,board_hint='synthetic',ground_pad_uuid=uid)


@pytest.mark.parametrize('fault',['narrow','new_via','old_pad','old_track','extra_spur','missing_segment','metadata'])
def test_independent_saved_receiver_rejects_any_unowned_literal_or_width_change(tmp_path,monkeypatch,fault):
    source,uid=fixture(tmp_path,monkeypatch);q=op.plan(source,board_hint='synthetic',ground_pad_uuid=uid)
    artifact=op.construct_private(source,q,tmp_path/'private');candidate=Path(artifact['candidate'])
    b=pcbnew.LoadBoard(str(candidate));old={force._uid(t)for t in pcbnew.LoadBoard(str(source)).GetTracks()}
    added=[t for t in b.GetTracks()if force._uid(t)not in old]
    if fault=='narrow':added[0].SetWidth(200000)
    elif fault=='new_via':
        v=pcbnew.PCB_VIA(b);v.SetPosition(added[0].GetStart());v.SetWidth(900000);v.SetDrill(500000)
        v.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);v.SetNet(added[0].GetNet());b.Add(v)
    elif fault=='old_pad':next(iter(next(iter(b.GetFootprints())).Pads())).Move(pcbnew.VECTOR2I(1,0))
    elif fault=='old_track':next(t for t in b.GetTracks()if force._uid(t)in old and t.GetClass()=='PCB_TRACK').SetWidth(123456)
    elif fault=='extra_spur':
        t=pcbnew.PCB_TRACK(b);t.SetStart(added[0].GetStart());t.SetEnd(added[0].GetStart()+pcbnew.VECTOR2I(100000,0))
        t.SetNet(added[0].GetNet());t.SetLayer(pcbnew.F_Cu);t.SetWidth(500000);b.Add(t)
    elif fault=='missing_segment':
        from cec_native_items import discard_items
        discard_items(b,[added[0]])
    else:next(iter(b.GetFootprints())).SetValue('different-part')
    field._save_field_snapshot(b,candidate)
    r=op.receive(source,candidate,board_hint='synthetic',ground_pad_uuid=uid)
    assert not r['ok']and not r['complete'],r


@pytest.mark.parametrize('seconds',[True,0,-1,11,float('nan'),float('inf'),1e-12])
def test_original_bounded_lease_only(tmp_path,monkeypatch,seconds):
    source,uid=fixture(tmp_path,monkeypatch)
    with pytest.raises(ValueError):op.plan(source,board_hint='synthetic',ground_pad_uuid=uid,timeout_s=seconds)


def test_forged_geometry_or_caller_authority_is_not_an_api(tmp_path,monkeypatch):
    source,uid=fixture(tmp_path,monkeypatch);q=op.plan(source,board_hint='synthetic',ground_pad_uuid=uid)
    q['rows'][0]['width_nm']=1
    with pytest.raises(ValueError,match='stale_or_forged'):op.construct_private(source,q,tmp_path/'private')
    with pytest.raises(TypeError):op.plan(source,board_hint='synthetic',ground_pad_uuid=uid,width_nm=1)
    with pytest.raises(TypeError):op.plan(source,board_hint='synthetic',ground_pad_uuid=uid,target_pad_uuid='guessed')


@pytest.mark.parametrize('phase',['source_inventory','actual_saved_native_material','final_current_and_liveidentity'])
def test_composition_cannot_borrow_time_or_accept_a_partial_guard_prefix(tmp_path,monkeypatch,phase):
    source,uid=fixture(tmp_path,monkeypatch);q=op.plan(source,board_hint='synthetic',ground_pad_uuid=uid)
    artifact=op.construct_private(source,q,tmp_path/'private');clock=[0.]
    monkeypatch.setattr(op.time,'monotonic',lambda:clock[0])
    if phase=='source_inventory':
        scope=op._scope
        def slow(*a,**k):r=scope(*a,**k);clock[0]+=10.;return r
        monkeypatch.setattr(op,'_scope',slow)
    elif phase=='actual_saved_native_material':
        qualify=op._qualify
        def slow(*a,**k):r=qualify(*a,**k);clock[0]+=10.;return r
        monkeypatch.setattr(op,'_qualify',slow)
    else:
        receive=op.current.receive
        def slow(*a,**k):r=receive(*a,**k);clock[0]+=10.;return r
        monkeypatch.setattr(op.current,'receive',slow)
    r=op.receive(source,artifact['candidate'],board_hint='synthetic',ground_pad_uuid=uid)
    assert not r['ok']and not r['complete']and phase not in r['timings_s'],r
    assert any('deadline'in error for error in r['errors'])


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_actual_selected_symbol_export_and_manufacturer_owner(tmp_path,monkeypatch,quarter,mirror):
    # Reuse a genuinely selected, renamed manufacturer divider/schematic.
    # Only the exporter process is synthetic, not the Source role compiler.
    f=canonical_fixture(tmp_path,monkeypatch,quarter=quarter,mirror=mirror)
    ground,proof=op._source_owner(f['board'],str(f['root']),force._uid(f['ground']),time.monotonic()+9.)
    assert force._uid(ground)==force._uid(f['ground'])
    assert proof['manufacturer_monitor']['function']=='OV1'
    assert len(proof['closed_node_members'])==3 and len(f['exports'])==1
    assert proof['no_new_current_or_operating_rating'] is True
    assert op._owner_live(proof)
    f['root'].write_text(f['root'].read_text()+'\n')
    assert not op._owner_live(proof)


@pytest.mark.parametrize('fault',['unknown_lower','unknown_monitor','dnp','extra_node',
    'wrong_upper_rail','wrong_ground','native_type','native_function','source_function',
    'source_pin_type','source_mpn','export_extra','export_renamed_net','exporter_hash',
    'exporter_missing','source_no_connect'])
def test_canonical_monitor_role_never_comes_from_a_caller_or_label(tmp_path,monkeypatch,fault):
    from test_source_divider_ground_span import _footprint
    f=canonical_fixture(tmp_path,monkeypatch);b=f['board'];text=f['root'].read_text()
    if fault=='unknown_lower':f['lower'].SetField('MPN','UNKNOWN')
    elif fault=='unknown_monitor':f['monitor'].SetField('MPN','UNKNOWN')
    elif fault=='dnp':f['lower'].SetDNP(True)
    elif fault=='extra_node':
        extra=_footprint(b,'UNOWNED','10kOhm','0402WGF1002TCE','R_0402_1005Metric',2)
        extra.FindPadByNumber('1').SetNet(f['lower'].FindPadByNumber('1').GetNet())
    elif fault=='wrong_upper_rail':f['upper'].FindPadByNumber('1').SetNet(f['ground'].GetNet())
    elif fault=='wrong_ground':f['ground'].SetNet(f['lower'].FindPadByNumber('1').GetNet())
    elif fault=='native_type':f['monitor'].FindPadByNumber('5').SetPinType('power_out')
    elif fault=='native_function':f['monitor'].FindPadByNumber('5').SetPinFunction('ILIM')
    elif fault=='source_function':f['root'].write_text(text.replace('(name "OV1")','(name "ILIM")'))
    elif fault=='source_pin_type':f['root'].write_text(text.replace('(symbol "Selected1_1_1" (pin passive',
        '(symbol "Selected1_1_1" (pin power_in',1))
    elif fault=='source_mpn':f['root'].write_text(text.replace('0402WGF1002TCE','0402WGF9999TCE'))
    elif fault in('export_extra','export_renamed_net'):
        nets=op.synth._first(f['tree'],'nets')
        node=next(n for n in op.synth._kids(nets,'net')if op.synth._val(n,'name','')=='renamed_monitor_node')
        if fault=='export_extra':node.append(['node',['ref','phantom'],['pin','1']])
        else:node[1]=['name','stale_spelling']
    elif fault in('exporter_hash','exporter_missing'):
        export=op.fresh._export
        def bad(*args,**kwargs):
            tree,proof=export(*args,**kwargs);proof=dict(proof)
            if fault=='exporter_hash':proof['exporter_sha256']='0'*64
            else:proof['exporter']=str(tmp_path/'MISSING-EXPORTER')
            return tree,proof
        monkeypatch.setattr(op.fresh,'_export',bad)
    else:
        _,_,instances=op.fresh._hierarchy(f['root'],time.monotonic()+9.)
        pin=next(p for p in instances[f['monitor'].GetReference()][0][2]['pins']if p['num']=='5')
        x,y=pin['pos']
        f['root'].write_text(text[:-1]+'(no_connect (at '+str(x)+' '+str(y)+') (uuid "'+
            'fb9f04c2-a063-4fb0-92f4-6a04c6e4d099'+'")))')
    with pytest.raises(ValueError):
        op._source_owner(b,str(f['root']),force._uid(f['ground']),time.monotonic()+9.)
