"""Saved antipads do not authorize new holes or bypass live copper/process checks."""
import time

import pcbnew
import pytest

import cec_field_coupling as field
import cec_force_current as force
import cec_fr as fr
import cec_native_frozen_zone_access as frozen
import cec_retained_ground_barrel_clearance as op
from test_field_proposals import track
from test_lastmile import _board


def fixture(tmp_path, quarter=0, mirror=False):
    def point(x, y):
        if mirror:
            x = 30-x
        for _ in range(quarter):
            x, y = 30-y, x
        return pcbnew.VECTOR2I_MM(x, y)
    b = _board([], edge=(0, 0, 30, 30))
    b.SetCopperLayerCount(6)
    props = b.GetProperties()
    props['CEC_FAB_PROFILE'] = 'jlcpcb_6l_pofv_signal'
    b.SetProperties(props)
    for net in ('GND', '/RENAMED_POWER'):
        b.Add(pcbnew.NETINFO_ITEM(b, net))
    for ref, net, at, size in (('ANY_REF', 'GND', (10, 10), (2, 2)),
                              ('OTHER_REF', '/RENAMED_POWER', (6, 6), (1, 1))):
        fp = pcbnew.FOOTPRINT(b); fp.SetReference(ref); b.Add(fp)
        pad = pcbnew.PAD(fp); pad.SetNumber('1'); pad.SetNet(b.FindNet(net))
        pad.SetAttribute(pcbnew.PAD_ATTRIB_SMD); pad.SetShape(pcbnew.PAD_SHAPE_RECT)
        pad.SetLayerSet(pcbnew.PAD.SMDMask()); pad.SetSize(pcbnew.VECTOR2I_MM(*size))
        pad.SetPosition(point(*at)); fp.Add(pad)
    via = pcbnew.PCB_VIA(b); via.SetNet(b.FindNet('GND')); via.SetPosition(point(10, 10))
    via.SetWidth(600000); via.SetDrill(300000)
    via.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); via.SetLocked(True); b.Add(via)
    z = pcbnew.ZONE(b); z.SetLayer(pcbnew.F_Cu); z.SetNet(b.FindNet('/RENAMED_POWER'))
    z.SetLocalClearance(500000); z.SetMinThickness(100000); z.Outline().NewOutline()
    for at in ((5, 5), (15, 5), (15, 15), (5, 15)):
        z.Outline().Append(point(*at))
    b.Add(z); b.BuildConnectivity(); assert pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    assert z.IsFilled() and z.GetFilledPolysList(pcbnew.F_Cu).OutlineCount() > 0
    source = tmp_path/'saved.kicad_pcb'; field._save_field_snapshot(b, source)
    # Reload so FileName and every native object come from the actual epoch.
    b = pcbnew.LoadBoard(str(source))
    via = next(t for t in b.GetTracks() if t.GetClass() == 'PCB_VIA')
    return b, source, via, point


def probe(b, via, **kw):
    return op.clear(b, via, 200000, deadline=kw.pop('deadline', time.monotonic()+10.), **kw)


@pytest.mark.parametrize('quarter', range(4))
@pytest.mark.parametrize('mirror', [False, True])
def test_exact_saved_barrel_can_reuse_its_real_filled_antipad_without_changing_any_source(
        tmp_path, quarter, mirror):
    b, source, via, _ = fixture(tmp_path, quarter, mirror)
    raw = source.read_bytes(); before = field._field_snapshot_inventory(b); cache = {}
    assert not fr._via_spot_clear(b, via.GetPosition(), 600000, 200000,
        {via.GetNetCode()}, drill_nm=300000, net_code=via.GetNetCode(),
        existing_via_uuid=force._uid(via), foreign_cache=cache)
    assert probe(b, via, foreign_cache=cache)
    assert frozen.cache_token(b) is None
    assert field._field_snapshot_inventory(b) == before and source.read_bytes() == raw
    # Filled-mode cached shapes cannot leak into a later authored query.
    assert not fr._via_spot_clear(b, via.GetPosition(), 600000, 200000,
        {via.GetNetCode()}, drill_nm=300000, net_code=via.GetNetCode(),
        existing_via_uuid=force._uid(via), foreign_cache=cache)


@pytest.mark.parametrize('fault', ['moved', 'width', 'drill', 'lock', 'group', 'profile',
                                 'source_missing', 'unfilled', 'clearance', 'new_uuid'])
def test_source_identity_and_unchanged_native_fill_are_mandatory_for_antipad_access(tmp_path, fault):
    b, source, via, _ = fixture(tmp_path)
    if fault == 'moved':
        via.Move(pcbnew.VECTOR2I(1000, 0))
    elif fault == 'width':
        via.SetWidth(610000)
    elif fault == 'drill':
        via.SetDrill(310000)
    elif fault == 'lock':
        via.SetLocked(False)
    elif fault == 'group':
        group = pcbnew.PCB_GROUP(b); group.SetName('ANY_GROUP'); b.Add(group); group.AddItem(via)
    elif fault == 'profile':
        props = b.GetProperties(); props['CEC_FAB_PROFILE'] = ''; b.SetProperties(props)
    elif fault == 'source_missing':
        b.SetFileName(str(tmp_path/'absent.kicad_pcb'))
    elif fault == 'unfilled':
        next(iter(b.Zones())).UnFill()
    elif fault == 'clearance':
        next(iter(b.Zones())).SetLocalClearance(600000)
    else:
        via.m_Uuid.Clone(pcbnew.KIID())
    before = field._field_snapshot_inventory(b); raw = source.read_bytes()
    assert not probe(b, via)
    assert field._field_snapshot_inventory(b) == before and source.read_bytes() == raw
    assert frozen.cache_token(b) is None


@pytest.mark.parametrize('layer', [pcbnew.B_Cu, pcbnew.In2_Cu, pcbnew.In3_Cu])
def test_a_source_antipad_never_hides_current_foreign_tracks_on_any_copper_face(tmp_path, layer):
    b, source, via, _ = fixture(tmp_path)
    track(b, '/RENAMED_POWER', (9, 10), (11, 10), width=.2, layer=layer)
    before = field._field_snapshot_inventory(b); raw = source.read_bytes()
    assert not probe(b, via)
    assert field._field_snapshot_inventory(b) == before and source.read_bytes() == raw


def test_already_frozen_context_keeps_its_scope_and_literal_source_barrel_requirement(tmp_path):
    b, source, via, _ = fixture(tmp_path)
    with frozen.frozen(b, source) as proof:
        assert probe(b, via)
        via.Move(pcbnew.VECTOR2I(1000, 0))
        assert not probe(b, via)
        via.Move(pcbnew.VECTOR2I(-1000, 0))
    assert proof['source_and_zones_unchanged']


@pytest.mark.parametrize('deadline', [-1., float('nan'), float('inf'), True])
def test_deadline_does_not_grant_unbounded_or_stale_native_access(tmp_path, deadline):
    b, source, via, _ = fixture(tmp_path)
    if deadline == -1.:
        assert not probe(b, via, deadline=time.monotonic()-1.)
    else:
        with pytest.raises(ValueError, match='bounded_literal'):
            probe(b, via, deadline=deadline)


def test_unsaved_or_changed_barrel_can_still_use_ordinary_authored_clearance_without_fill_authority(tmp_path):
    b, source, via, point = fixture(tmp_path)
    # Outside the power zone, no source-frozen permission is needed.
    via.SetPosition(point(20, 20)); b.SetFileName('')
    before = field._field_snapshot_inventory(b)
    assert probe(b, via)
    assert field._field_snapshot_inventory(b) == before
    assert frozen.cache_token(b) is None
