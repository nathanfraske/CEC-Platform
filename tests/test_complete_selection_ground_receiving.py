"""A candidate must pass the saved local-return predicate before selection."""
import cec_complete_macro_cell as macro
import cec_decoupler_cell as cells
import cec_saved_ground_hierarchy as hierarchy
from test_complete_macro_cell import fixture


def test_electrical_plane_reachability_does_not_skip_saved_local_ground_receiver(tmp_path,monkeypatch):
    source,parent,private,packet=fixture(tmp_path,monkeypatch)
    original=cells._existing_return
    baseline=len(private.GetTracks())
    def after_staging(board,*args,**kwargs):
        if board is private and len(board.GetTracks())>baseline:
            return None
        return original(board,*args,**kwargs)
    monkeypatch.setattr(cells,'_existing_return',after_staging)
    calls=[]
    def reject(*args,**kwargs):
        calls.append(args[2]['a']['pad_uuid'])
        raise ValueError('injected_saved_local_return_refusal')
    monkeypatch.setattr(hierarchy,'receive',reject)
    proof=macro.screen(source,private,packet,board_hint='opaque',timeout_s=2.,
        require_trace_craft_nonregression=False)
    assert proof['complete']is False and calls
    trials=proof['complete_selection_terminal_ground_return_trials']
    assert trials and all(p['ok']is False and p['failed_request']and
        p['error']=='injected_saved_local_return_refusal'for p in trials)
