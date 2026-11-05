"""Fresh continuation authority is not reclassified as a pad-incident lead."""
import time
import pytest
import cec_source_ground_continuation as continuation
import cec_source_ground_boundary_connection as observer
import cec_cell_macro_requests as compiler
import cec_selected_cap_ground_boundary as cap_scope
from test_source_ground_continuation_observer import _fixture,_prepare
from test_selected_cap_ground_boundary import fixture as actual_canonical_cap


def test_fresh_whole_compile_dispatches_continuations_without_legacy_reclassification(tmp_path,monkeypatch):
    case=_fixture(tmp_path,monkeypatch)
    ids={v['native_source_uuid']for v in case['request']['exact_additional_macro_component_source_ownership']
        if v['kind']==continuation.KIND};assert ids
    original_compile=compiler.compile;original_authority=compiler._ground_boundary_authority
    compiling=[False];reclassified=[]
    def compile_fresh(*args,**kwargs):
        compiling[0]=True
        try:return original_compile(*args,**kwargs)
        finally:compiling[0]=False
    def authority(*args,**kwargs):
        if not compiling[0]and observer.force._uid(args[1])in ids:
            reclassified.append(observer.force._uid(args[1]))
        return original_authority(*args,**kwargs)
    monkeypatch.setattr(compiler,'compile',compile_fresh)
    monkeypatch.setattr(compiler,'_ground_boundary_authority',authority)
    live=_prepare(case);proof=live(case['board'],timeout_s=8.)[case['key']]
    assert proof and proof['all_named_contacts_connected']and proof['independently_received_local_ground_returns']
    assert not reclassified and proof['remote_smd_return_not_inferred']
    assert not proof['current_qualified']and not proof['routing_admitted']and not proof['release_authority']


def test_absent_canonical_cap_root_is_explicit_refusal_not_an_attribute_crash(tmp_path,monkeypatch):
    source,unused,proposal,ids,root=actual_canonical_cap(tmp_path,monkeypatch)
    monkeypatch.setattr(cap_scope.canonical.source_nc,'_root',lambda *args:None)
    with pytest.raises(ValueError,match='canonical_selected_cap_Source_root_required'):
        cap_scope._source_context(source,proposal,time.monotonic()+8.)
