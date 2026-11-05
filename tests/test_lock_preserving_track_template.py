"""Mixed source locks strengthen replacements without laundering process."""
import pcbnew,pytest
import cec_lock_preserving_track_template as locks
import cec_force_current as force
import cec_additive_route_receiving as additive
import cec_field_coupling as field

def fixture(tmp_path,flags=(False,True),face=pcbnew.F_Cu):
    b=pcbnew.BOARD();n=pcbnew.NETINFO_ITEM(b,'opaque');b.Add(n);tracks=[]
    for i,flag in enumerate(flags):
        t=pcbnew.PCB_TRACK(b);t.SetNet(n);t.SetWidth(200000);t.SetLayer(face);t.SetLocked(flag)
        t.SetStart(pcbnew.VECTOR2I_MM(i,0));t.SetEnd(pcbnew.VECTOR2I_MM(i+1,0));b.Add(t);tracks.append(t)
    p=tmp_path/'source.kicad_pcb';field._save_field_snapshot(b,p);_,nodes=additive._nodes(p)
    return b,p,nodes,tracks,[force._uid(t) for t in tracks]

@pytest.mark.parametrize('flags',[(False,False),(True,True),(False,True),(True,False)])
@pytest.mark.parametrize('face',[pcbnew.F_Cu,pcbnew.B_Cu])
def test_strongest_literal_lock_is_retained_with_every_other_process_field(tmp_path,flags,face):
    b,p,nodes,tracks,ids=fixture(tmp_path,flags,face);raw=p.read_bytes()
    template,proof=locks.derive(b,p,ids)
    assert template.IsLocked()==any(flags) and template.GetWidth()==200000 and template.GetLayer()==face
    assert proof['source_locked_track_uuids']==sorted(u for u,f in zip(ids,flags) if f)
    assert proof['no_lock_weakened'] and proof['source_native_items_not_mutated']
    assert not proof['source_cut_permission_or_net_classification_granted'] and not proof['current_or_release_qualified']
    assert [t.IsLocked() for t in tracks]==list(flags) and p.read_bytes()==raw

@pytest.mark.parametrize('fault',['missing','duplicate','empty','not_track','group','mask','width','face'])
def test_only_actual_matching_plain_source_metadata_is_a_template(tmp_path,fault):
    b,p,nodes,tracks,ids=fixture(tmp_path)
    if fault=='missing':ids[0]='absent'
    elif fault=='duplicate':ids[1]=ids[0]
    elif fault=='empty':ids=[]
    elif fault=='not_track':
        t=pcbnew.PCB_VIA(b);b.Add(t);ids[0]=force._uid(t);nodes[ids[0]]=nodes[ids[1]]
    elif fault=='group':
        g=pcbnew.PCB_GROUP(b);b.Add(g);g.AddItem(tracks[0])
    elif fault=='mask':tracks[0].SetHasSolderMask(True)
    else:
        if fault=='width':tracks[0].SetWidth(200001)
        else:tracks[0].SetLayer(pcbnew.B_Cu)
        field._save_field_snapshot(b,p);_,nodes=additive._nodes(p)
    with pytest.raises(ValueError):locks.derive(b,p,ids)
