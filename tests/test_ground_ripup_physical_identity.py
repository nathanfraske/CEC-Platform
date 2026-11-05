"""Ground rip-up resolves all physical targets atomically before mutation."""
import json
import types
import pcbnew
import pytest
import cec_decoupler_cell as cells


def fixture(split=True):
    board=pcbnew.BOARD();fp=pcbnew.FOOTPRINT(board);fp.SetReference('renamed_owner');board.Add(fp)
    ground=pcbnew.NETINFO_ITEM(board,'GND');foreign=pcbnew.NETINFO_ITEM(board,'/ordinary')
    board.Add(ground);board.Add(foreign);pads=[];tracks=[]
    for x in ([10,30]if split else [10]):
        p=pcbnew.PAD(fp);p.SetNumber('49');p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD);p.SetLayerSet(pcbnew.PAD.SMDMask())
        p.SetSize(pcbnew.VECTOR2I_MM(.7,.7));p.SetPosition(pcbnew.VECTOR2I_MM(x,10))
        p.SetNet(ground);fp.Add(p);pads.append(p)
        t=pcbnew.PCB_TRACK(board);t.SetStart(pcbnew.VECTOR2I_MM(x-.5,10.8))
        t.SetEnd(pcbnew.VECTOR2I_MM(x+.5,10.8));t.SetWidth(220000)
        t.SetLayer(pcbnew.F_Cu);t.SetNet(foreign);board.Add(t);tracks.append(t)
    return board,fp,pads,tracks


def inventory(board):
    return sorted((t.m_Uuid.AsString(),t.GetNetname(),t.IsLocked(),t.GetWidth(),
        tuple(t.GetStart()),tuple(t.GetEnd()))for t in board.GetTracks())


def target(fp,pad):
    return dict(ref=fp.GetReference(),pad=pad.GetNumber(),pad_uuid=pad.m_Uuid.AsString())


def test_split_ground_legacy_is_ambiguous_and_never_mutates():
    board,fp,_,_=fixture();before=inventory(board)
    with pytest.raises(ValueError,match='requires_physical_pad_uuid'):
        cells.ripup_foreign_ground_access_copper(board,[dict(ref=fp.GetReference(),pad='49')])
    assert inventory(board)==before


@pytest.mark.parametrize('index',[0,1])
def test_exact_uuid_selects_only_one_physical_land(index):
    board,fp,pads,tracks=fixture();request=target(fp,pads[index])
    selected=tracks[index].m_Uuid.AsString();retained=tracks[1-index].m_Uuid.AsString()
    report=cells.ripup_foreign_ground_access_copper(board,[request])
    assert report['removed_count']==1 and report['removed_items'][0]['uuid']==selected
    assert report['removed_items'][0]['pad_uuid']==request['pad_uuid']
    assert report['physical_targets']==[request]
    assert [t.m_Uuid.AsString()for t in board.GetTracks()]==[retained]


@pytest.mark.parametrize('fault',['ref','number','uuid','empty_uuid','wrong_ground',
    'ambiguous_second','missing_second','duplicate_request','duplicate_uuid','duplicate_ref'])
def test_complete_target_inventory_rejects_before_any_removal(fault):
    board,fp,pads,_=fixture();requests=[target(fp,pads[0])]
    if fault=='ref':requests[0]['ref']='unrelated_owner'
    elif fault=='number':requests[0]['pad']='3'
    elif fault=='uuid':requests[0]['pad_uuid']='not-a-source-land'
    elif fault=='empty_uuid':requests[0]['pad_uuid']=''
    elif fault=='wrong_ground':pads[0].SetNet(board.FindNet('/ordinary'))
    elif fault=='ambiguous_second':requests.append(dict(ref=fp.GetReference(),pad='49'))
    elif fault=='missing_second':requests.append(dict(ref=fp.GetReference(),pad='999'))
    elif fault=='duplicate_request':requests.append(dict(requests[0]))
    elif fault=='duplicate_uuid':pads[1].m_Uuid.Clone(pcbnew.KIID(pads[0].m_Uuid.AsString()))
    else:
        duplicate=pcbnew.FOOTPRINT(board);duplicate.SetReference(fp.GetReference());board.Add(duplicate)
    before=inventory(board)
    with pytest.raises(ValueError):cells.ripup_foreign_ground_access_copper(board,requests)
    assert inventory(board)==before


def test_unique_legacy_number_still_works_and_reports_resolved_uuid():
    board,fp,pads,_=fixture(False);expected=pads[0].m_Uuid.AsString()
    report=cells.ripup_foreign_ground_access_copper(board,[dict(ref=fp.GetReference(),pad=49)])
    assert report['removed_count']==1 and report['removed_items'][0]['pad_uuid']==expected


@pytest.mark.parametrize('kind',['locked','protected','wide','ground'])
def test_exact_identity_never_weakens_existing_protection(kind):
    board,fp,pads,tracks=fixture(False);t=tracks[0];options={}
    if kind=='locked':t.SetLocked(True)
    elif kind=='protected':options['protected_nets']=['/ordinary']
    elif kind=='wide':t.SetWidth(1000000)
    else:t.SetNet(board.FindNet('GND'))
    before=inventory(board);request=target(fp,pads[0])
    result=cells.ripup_foreign_ground_access_copper(board,[request],**options)
    assert inventory(board)==before and result['removed_count']==0
    if kind=='wide':
        assert result['blocked_count']==1
        assert result['blocked_items'][0]['pad_uuid']==request['pad_uuid']


def test_json_worker_serialization_preserves_exact_uuid_and_ten_second_lease(tmp_path,monkeypatch):
    board,fp,pads,_=fixture();request=target(fp,pads[1]);observed={}
    def run(command,**kwargs):
        observed.update(command=command,kwargs=kwargs)
        tokens=[command[i+1]for i,v in enumerate(command)if v=='--target-ground-json']
        parsed=cells._parse_ground_ripup_targets([],tokens)
        assert parsed==[request]
        report=command[command.index('--report')+1]
        with open(report,'w')as sink:json.dump(dict(physical_targets=parsed),sink)
        return types.SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(cells.subprocess,'run',run)
    result=cells._ripup_file_subprocess(str(tmp_path/'seed.kicad_pcb'),max_assignment_mm=3.5,
        ground_reach_mm=1.5,protected_nets=['/power'],ground_targets=[request])
    assert result['physical_targets']==[request]
    assert observed['kwargs']['timeout']==10
    assert '--target-ground'not in observed['command']
    assert not list(tmp_path.glob('cec-decoupler-ripup-*'))


def test_cli_parser_roundtrip_and_unique_legacy_transport():
    request=dict(ref='some_ref',pad='49',pad_uuid='exact-physical-identity')
    assert cells._parse_ground_ripup_targets(['unique_ref:1'],[json.dumps(request)])==[
        dict(ref='unique_ref',pad='1'),request]


def test_actual_worker_cli_forwards_json_and_legacy_without_collapsing(monkeypatch):
    request=dict(ref='split_owner',pad='49',pad_uuid='actual-physical-land')
    received={}
    def worker(*a,**kw):received.update(kw)
    monkeypatch.setattr(cells,'_ripup_file_worker',worker)
    monkeypatch.setattr(cells.os,'_exit',lambda status:None)
    cells._main(['--ripup-worker','--board','unused','--report','unused',
        '--target-ground','unique:1','--target-ground-json',json.dumps(request)])
    assert received['ground_targets']==[dict(ref='unique',pad='1'),request]


def test_invalid_worker_inventory_never_reaches_saveboard(monkeypatch):
    board,fp,pads,_=fixture();before=inventory(board);saved=[]
    monkeypatch.setattr(cells.pcbnew,'LoadBoard',lambda path:board)
    monkeypatch.setattr(cells.pcbnew,'SaveBoard',lambda *a:saved.append(a))
    with pytest.raises(ValueError):cells._ripup_file_worker('unused','unused',
        max_assignment_mm=3.5,ground_reach_mm=1.5,protected_nets=(),
        ground_targets=[target(fp,pads[0]),dict(ref=fp.GetReference(),pad='49')])
    assert not saved and inventory(board)==before


@pytest.mark.parametrize('legacy,payload',[(['bad'],[]),([':49'],[]),(['U:'],[]),
    ([],['[]']),([],['{"ref":"U","pad":"49","pad_uuid":null}']),
    ([],['{"ref":"U","pad":false}']),([],['not-json'])])
def test_malformed_cli_identity_refuses(legacy,payload):
    with pytest.raises(ValueError):cells._parse_ground_ripup_targets(legacy,payload)
