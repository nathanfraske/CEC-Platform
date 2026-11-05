"""Unfinished annotation replay must not normalize still-unmoved copper."""
import pcbnew
import pytest
import cec_source_reference_group_transport as op
import cec_source_reference_group_cardinal_batch as batch
import cec_field_coupling as field
from test_source_reference_group_transport import fixture


def hybrid(tmp_path,cardinal=False):
    source,owner,group=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    properties=b.GetProperties();properties['CEC_TEST_NATIVE_QUERY']='exact-authored-property'
    b.SetProperties(properties)
    net=pcbnew.NETINFO_ITEM(b,'UNMOVED_FOREIGN_GROUND');b.Add(net)
    via=pcbnew.PCB_VIA(b);via.SetNet(net);via.SetPosition(pcbnew.VECTOR2I_MM(10,9))
    via.SetWidth(500000);via.SetDrill(300000);via.SetViaType(pcbnew.VIATYPE_THROUGH)
    via.SetLayerPair(pcbnew.F_Cu,pcbnew.B_Cu);b.Add(via)
    field._save_field_snapshot(b,source)
    proof=op.inspect(source,owner_uuid=owner,group_uuid=group)
    b=pcbnew.LoadBoard(str(source));requests=[(proof,0,(0,-1000000))]if cardinal else [(proof,(0,-1000000))]
    if cardinal:batch.transform_many(b,requests)
    else:op.transform_many(b,requests)
    return source,b,requests,owner,group


@pytest.mark.parametrize('cardinal',[False,True])
def test_real_hybrid_passes_annotation_only_without_mutating_caller_or_source(tmp_path,cardinal):
    source,b,requests,owner,group=hybrid(tmp_path,cardinal)
    before=op._cardinal_identity(b);data=source.read_bytes();filename=b.GetFileName()
    result=(batch if cardinal else op).verify_native(source,b,requests)
    assert result['ok']and result['complete']and result['copper_identity_reload_deferred']
    assert not result['full_field_snapshot_proved']and not result['current_authority']
    assert result['full_macro_physical_copper_and_final_saved_receiving_still_required']
    assert op._cardinal_identity(b)==before and b.GetFileName()==filename and source.read_bytes()==data
    # This is not a copper admission shortcut. The unchanged real full-field
    # snapshot still refuses the COMPLETE candidate if the barrel stays put.
    with pytest.raises(field._ProposalUnknown,match='changed_saved_identity'):
        field._save_field_snapshot(b,tmp_path/'invalid-complete.kicad_pcb')
    assert op._cardinal_identity(b)==before


@pytest.mark.parametrize('cardinal',[False,True])
@pytest.mark.parametrize('fault',['pad_net','pad_size','pad_angle','field','root_ink','group'])
def test_selected_footprint_and_every_root_ink_group_remain_exact(tmp_path,cardinal,fault):
    source,b,requests,owner,group=hybrid(tmp_path,cardinal)
    fp=next(f for f in b.GetFootprints()if op.force._uid(f)==owner);pad=next(iter(fp.Pads()))
    if fault=='pad_net':pad.SetNet(next(iter(b.GetTracks())).GetNet())
    elif fault=='pad_size':pad.SetSize(pad.GetSize()+pcbnew.VECTOR2I(1,0))
    elif fault=='pad_angle':pad.SetOrientation(pcbnew.EDA_ANGLE(23,pcbnew.DEGREES_T))
    elif fault=='field':fp.Reference().SetTextThickness(fp.Reference().GetTextThickness()+1)
    elif fault=='root_ink':next(i for i in b.GetDrawings()if i.GetClass()=='PCB_TEXT').SetText('FORGED')
    else:next(g for g in b.Groups()if op.force._uid(g)==group).SetName('FORGED')
    before=op._cardinal_identity(b);source_bytes=source.read_bytes()
    with pytest.raises(ValueError,match='reference.*replay_differs|reference_annotation_replay_differs'):
        (batch if cardinal else op).verify_native(source,b,requests)
    assert before==op._cardinal_identity(b)and source.read_bytes()==source_bytes


def test_query_detects_writer_mutation_of_unselected_copper(tmp_path,monkeypatch):
    source,b,requests,owner,group=hybrid(tmp_path);original=pcbnew.PCB_IO_KICAD_SEXPR
    class MutatingWriter:
        def __init__(self):self.writer=original()
        def Format(self,item):return self.writer.Format(item)
        def GetStringOutput(self,*a):return self.writer.GetStringOutput(*a)
        def SaveBoard(self,path,board):
            result=self.writer.SaveBoard(path,board)
            next(iter(board.GetTracks())).SetWidth(600000)
            return result
    monkeypatch.setattr(pcbnew,'PCB_IO_KICAD_SEXPR',MutatingWriter)
    with pytest.raises(ValueError,match='changed_caller_identity'):
        op._unfinished_annotation_snapshot(b,tmp_path/'mutation-query.kicad_pcb')


def test_query_compares_property_contents_not_wxstring_proxy_identity(tmp_path,monkeypatch):
    source,b,requests,owner,group=hybrid(tmp_path);original=pcbnew.PCB_IO_KICAD_SEXPR
    before=tuple(sorted((str(k),str(v))for k,v in b.GetProperties().asdict().items()))
    assert op.verify_native(source,b,requests)['ok']
    assert before==tuple(sorted((str(k),str(v))for k,v in b.GetProperties().asdict().items()))
    class MutatingWriter:
        def __init__(self):self.writer=original()
        def Format(self,item):return self.writer.Format(item)
        def GetStringOutput(self,*a):return self.writer.GetStringOutput(*a)
        def SaveBoard(self,path,board):
            result=self.writer.SaveBoard(path,board)
            props=board.GetProperties();props['CEC_TEST_NATIVE_QUERY']='forged-property';board.SetProperties(props)
            return result
    monkeypatch.setattr(pcbnew,'PCB_IO_KICAD_SEXPR',MutatingWriter)
    with pytest.raises(ValueError,match='changed_caller_identity'):
        op._unfinished_annotation_snapshot(b,tmp_path/'property-mutation-query.kicad_pcb')
