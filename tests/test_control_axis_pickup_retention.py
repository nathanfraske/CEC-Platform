"""Native compiler retention of an exact Source-owned shortened pickup."""
import copy
import pytest
import cec_control_shunt_ground_return_axes as axes
import cec_smd_macro_transport as transport
import cec_cell_macro_requests as compiler
import cec_force_current as force
from test_control_shunt_ground_return_axes import case


def native_frame(tmp_path,monkeypatch,turn=0,back=False):
    parent,posed,proposal,request,via,tail=case(tmp_path,monkeypatch,turn,back)
    derived=axes.derive(parent,posed,proposal,[request],timeout_s=10.)
    proof=transport.apply(parent,posed,source_path=parent.GetFileName(),board_hint=proposal['board_hint'],
        local_signal_return_via_poses=[{k:derived[0][k]for k in('uuid','owner_pad_uuid','position_nm')}])
    axes.apply_and_promote(proof,derived)
    return parent,posed,proof,force._uid(tail)


@pytest.mark.parametrize('turn',range(4))
@pytest.mark.parametrize('back',[False,True])
def test_native_shorter_control_pickup_survives_compiler_cut_classification(tmp_path,monkeypatch,turn,back):
    parent,posed,proof,uid=native_frame(tmp_path,monkeypatch,turn,back)
    change=next(q for q in proof['changes']if q['uuid']==uid)
    assert change['provisional_boundary_reconstruction_required']
    before=[compiler.row._source_binding(b)for b in(parent,posed)]
    retained=compiler._retained_ground_dogbones(parent,posed,proof)
    assert len(retained)==1 and retained[0]['uuid']==uid
    assert retained[0]['source_factory_pickup_retained_not_retired']
    assert before==[compiler.row._source_binding(b)for b in(parent,posed)]


@pytest.mark.parametrize('fault',['unowned','wrong_tail','wrong_owner','thin','wrongface','longer'])
def test_only_exact_source_axis_owned_fullclass_shorter_native_tail_retained(tmp_path,monkeypatch,fault):
    parent,posed,proof,uid=native_frame(tmp_path,monkeypatch)
    record=proof['source_process_barrel_motion'][0]
    seat=record['source_control_shunt_return_axis']
    actual=next(t for t in posed.GetTracks()if force._uid(t)==uid)
    if fault=='unowned':record.pop('source_control_shunt_return_axis')
    elif fault=='wrong_tail':seat['source_tail_uuid']='not-an-owned-native-tail'
    elif fault=='wrong_owner':seat['owner_pad_uuid']='not-an-owned-native-land'
    elif fault=='thin':actual.SetWidth(220000)
    elif fault=='wrongface':actual.SetLayer(2)
    elif fault=='longer':actual.SetEnd(actual.GetEnd()+type(actual.GetEnd())(1000000,0))
    if fault in('unowned','wrong_tail','wrong_owner'):
        assert compiler._retained_ground_dogbones(parent,posed,proof)==[]
    else:
        with pytest.raises(ValueError):compiler._retained_ground_dogbones(parent,posed,proof)
