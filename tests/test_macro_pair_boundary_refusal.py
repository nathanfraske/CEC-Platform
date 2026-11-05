"""Protected two-member contacts cannot fall through to invented supply loads."""
import time
import pcbnew
import pytest
import cec_cell_macro_requests as compiler
from test_cell_macro_requests import moved_pair


@pytest.mark.parametrize('quarter',range(4))
@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('ordinary_overlap',[False,True])
def test_actual_protected_member_precedes_ordinary_or_supply_classifiers(tmp_path,monkeypatch,quarter,back,ordinary_overlap):
    source,child,transport,via=moved_pair(tmp_path,quarter=quarter,back=back,
        dogbone=True,net_name='/unrelated_pair_P')
    source.Add(pcbnew.NETINFO_ITEM(source,'/unrelated_pair_N'))
    assert {'/unrelated_pair_P','/unrelated_pair_N'}<=compiler.fr.coupled_pair_nets(source)
    # This isolated catalog-overlap fixture must not let a permissive
    # ordinary classification override the actual two-member protection.
    monkeypatch.setattr(compiler.ordinary,'eligible_nets',
        lambda *a,**k:{'/unrelated_pair_P'}if ordinary_overlap else set())
    def no_amperes(*a,**k):raise AssertionError('a protected pair is not a missing power budget')
    monkeypatch.setattr(compiler.full,'plan',no_amperes)
    before=compiler.row._source_binding(source)
    with pytest.raises(ValueError,match='complete_protected_pair_boundary_reconstruction_required:.*:/unrelated_pair_P'):
        compiler._extra_ownership(source,None,transport,dict(retired_track_uuids=[],board_hint='opaque'),
            time.monotonic()+10.)
    assert before==compiler.row._source_binding(source)
