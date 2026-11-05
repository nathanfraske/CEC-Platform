"""Native Source RC span reconstruction, not an ordinary-role exception."""
import json

import pcbnew
import pytest
import cec_force_current as force
import root_source_rc_span_reflow_20261025 as op
from test_measurement_filter_span import fixture, observe


def points(f, *, side=1):
    a,z = [tuple(p) for p in (f['span'].GetStart(),f['span'].GetEnd())]
    dx,dy = z[0]-a[0],z[1]-a[1]
    along = ((dx>0)-(dx<0),(dy>0)-(dy<0)); normal = (-along[1]*side,along[0]*side)
    def at(length,height=0):
        return [a[k]+along[k]*length+normal[k]*height for k in (0,1)]
    extent = max(abs(dx),abs(dy))
    return [list(a),at(500000),at(1000000,500000),at(extent-1000000,500000),
            at(extent-500000),list(z)]


def plan(f, path=None):
    return op.plan(f['board'],f['source'],board_hint=f['hint'],pad_uuid=force._uid(f['root']),
        span_uuid=force._uid(f['span']),points_nm=points(f) if path is None else path)


def construct(f,tmp_path,q):
    candidate = force._copy_family(f['source'],tmp_path/'private')
    proof = op.construct_private(f['source'],candidate,q)
    assert proof['complete'] and not proof['routing_admitted']
    return candidate


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('mirror',[False,True])
def test_cardinal_reflected_renamed_source_span_has_independent_saved_receiver(tmp_path,monkeypatch,quarter,mirror):
    f = fixture(tmp_path,monkeypatch,quarter=quarter,mirror=mirror); source = f['source'].read_bytes()
    q = plan(f); candidate = construct(f,tmp_path,q)
    r = op.receive(f['source'],candidate,board_hint=f['hint'],pad_uuid=force._uid(f['root']),span_uuid=force._uid(f['span']))
    assert r['ok'] and r['complete'],r['errors']
    assert not any(r[k] for k in ('routing_admitted','current_qualified','kelvin_qualified','release_authority'))
    assert r['whole_parent_native_current_field_return_and_absolute_measurement_receiving_required']
    assert f['source'].read_bytes() == source
    child = pcbnew.LoadBoard(str(candidate))
    assert all(t.GetWidth() == 250000 and t.GetLayer() == pcbnew.F_Cu
        for t in child.GetTracks() if force._uid(t) in r['incoming_track_uuids'])


@pytest.mark.parametrize('fault',['bool','non45','hard90','different_port','different_tangent','too_long','loop'])
def test_point_packets_do_not_relax_geometry_or_contacts(tmp_path,monkeypatch,fault):
    f = fixture(tmp_path,monkeypatch); path = points(f)
    if fault == 'bool':path[1][0] = True
    elif fault == 'non45':path[2][0] += 1
    elif fault == 'hard90':path = [path[0],path[1],[path[1][0]+500000,path[1][1]],
        [path[-2][0]+500000,path[-2][1]],path[-2],path[-1]]
    elif fault == 'different_port':path[-1][1] += 1
    elif fault == 'different_tangent':path[1][0] -= 500000
    elif fault == 'too_long':path[2][0] -= 10000000
    elif fault == 'loop':path[3] = path[1]
    with pytest.raises(ValueError):plan(f,path)


@pytest.mark.parametrize('fault',['width','net','lock','face','extra','retained','root','pose','stale'])
def test_exact_saved_source_delta_and_epoch_are_required(tmp_path,monkeypatch,fault):
    f = fixture(tmp_path,monkeypatch); q = plan(f); candidate = construct(f,tmp_path,q)
    b = pcbnew.LoadBoard(str(candidate)); oldids = {force._uid(t) for t in f['board'].GetTracks()}
    new = next(t for t in b.GetTracks() if force._uid(t) not in oldids)
    if fault == 'width':new.SetWidth(260000)
    elif fault == 'net':new.SetNet(f['owner'].FindPadByNumber('6').GetNet())
    elif fault == 'lock':new.SetLocked(not new.IsLocked())
    elif fault == 'face':new.SetLayer(pcbnew.B_Cu)
    elif fault == 'retained':
        next(t for t in b.GetTracks() if force._uid(t) == force._uid(f['tracks'][0])).SetWidth(300000)
    elif fault == 'pose':b.FindFootprintByReference(f['cap'].GetReference()).Move(pcbnew.VECTOR2I(100000,0))
    elif fault == 'extra':
        t = new.Duplicate();t.m_Uuid.Clone(pcbnew.KIID());t.SetStart(pcbnew.VECTOR2I_MM(80,80));t.SetEnd(pcbnew.VECTOR2I_MM(81,80));b.Add(t)
    elif fault == 'root':candidate.write_text(candidate.read_text().replace('(general','(unknown_root yes) (general',1))
    elif fault == 'stale':f['source'].write_text(f['source'].read_text().replace('10Ω','100Ω'))
    if fault not in ('root','stale'):
        pcbnew.PCB_IO_KICAD_SEXPR().SaveBoard(str(candidate),b)
    r = op.receive(f['source'],candidate,board_hint=f['hint'],pad_uuid=force._uid(f['root']),span_uuid=force._uid(f['span']))
    assert not r['ok'] and not r['routing_admitted']


def test_same_node_body_pickup_is_not_an_allowed_new_junction(tmp_path,monkeypatch):
    f = fixture(tmp_path,monkeypatch)
    # The Source still has one connected exact three-land RC graph, but an
    # unrelated part of that graph now borders the proposed detour's middle.
    p = points(f); t = pcbnew.PCB_TRACK(f['board']);t.SetLayer(pcbnew.F_Cu)
    t.SetWidth(250000);t.SetNet(f['root'].GetNet());t.SetStart(pcbnew.VECTOR2I_MM(12,18))
    t.SetEnd(pcbnew.VECTOR2I(*p[2]));f['board'].Add(t)
    pcbnew.SaveBoard(str(f['source']),f['board'])
    with pytest.raises(ValueError):plan(f,p)


def test_worker_receipt_cannot_authorize_a_different_recipe(tmp_path,monkeypatch):
    f = fixture(tmp_path,monkeypatch); q = plan(f)
    q['Source_observation']['retirement_authority'] = True
    candidate = force._copy_family(f['source'],tmp_path/'private')
    with pytest.raises(ValueError,match='fresh_exact_Source_RC_span_recipe_required'):
        op.construct_private(f['source'],candidate,q)
