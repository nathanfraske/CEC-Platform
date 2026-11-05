from types import SimpleNamespace
from unittest.mock import patch
import cec_critical_checkpoint as checkpoint
import cec_synth_pipeline as synth
import pcbnew


def item(uid, net='arbitrary/positive', kind='PCB_TRACK'):
    return SimpleNamespace(m_Uuid=SimpleNamespace(AsString=lambda:uid),
                           GetNetname=lambda:net, GetClass=lambda:kind)


def test_native_cleanup_owns_only_exact_new_pair_tracks_and_refills():
    tracks=[item('old'), item('tail'), item('barrel',kind='PCB_VIA'),
            item('return','GND',kind='PCB_VIA'), item('other','power'),
            item('wrong-native-net','power')]
    solved=dict(pairs=dict(routed=[dict(p='arbitrary/positive',n='arbitrary/negative')]),
        generated_items=[dict(uuid=row.m_Uuid.AsString(),kind='PCB_TRACK',net='arbitrary/positive')
                         for row in tracks[1:]])
    # A generated report cannot grant mutation authority over a different
    # native kind/net, even if its claimed UUID matches.
    with patch.object(pcbnew,'LoadBoard',return_value=SimpleNamespace(GetTracks=lambda:tracks)), \
         patch.object(synth,'_prune_structural_dangling_transactionally',return_value=({'removed_count':1},None)) as prune:
        report=checkpoint.cleanup_generated_terminals('arbitrary.kicad_pcb',solved)
    assert report['writable_count']==1 and report['preserved_count']==5
    assert prune.call_args.kwargs==dict(preserve_uuids={'old','barrel','return','other','wrong-native-net'},
        max_rounds=4,refill_zones=True)


def test_missing_generated_provenance_never_grants_cleanup_authority():
    with patch.object(synth,'_prune_structural_dangling_transactionally') as prune:
        report=checkpoint.cleanup_generated_terminals('unused',{'pairs':{'routed':[{'p':'P','n':'N'}]}})
    assert not report['applicable'] and not prune.called


def test_cleanup_is_a_reference_handoff_before_independent_checkpoint_validation():
    import cec_full_pipeline as pipeline
    import cec_ground_plane
    with patch.object(pipeline,'_copy_sidecars'), \
         patch.object(cec_ground_plane,'fill_and_admit',return_value={'ok':True}), \
         patch.object(checkpoint,'cleanup_generated_terminals',return_value={'removed_count':1}) as clean:
        result=checkpoint.complete_reference_planes('source','destination',{'pairs_ok':True})
    assert clean.call_args.args[0].name=='destination'
    assert result['generated_terminal_cleanup']['removed_count']==1


def test_failed_reference_fill_does_not_start_cleanup():
    import cec_full_pipeline as pipeline
    import cec_ground_plane
    with patch.object(pipeline,'_copy_sidecars'), \
         patch.object(cec_ground_plane,'fill_and_admit',return_value={'ok':False}), \
         patch.object(checkpoint,'cleanup_generated_terminals') as clean:
        result=checkpoint.complete_reference_planes('source','destination',{})
    assert not result['ok'] and not clean.called
