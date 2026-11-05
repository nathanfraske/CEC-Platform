import hashlib
import json
from pathlib import Path

import cec_staged_fr as staged


def test_refused_tier_survives_interruption_before_next_return(tmp_path):
    source=tmp_path/'source.kicad_pcb'
    source.write_text('immutable source')
    output=tmp_path/'wave'/'board.kicad_pcb'
    report,persist=staged._tier_progress_report(source,output,work='disposable',threads=2)
    failure={'tier':['N','P'],'refused':True,'reason':'tier_pair_physics_refused',
             'pair_physics':{'ok':False,'violations':['layer asymmetry']}}
    report['active_tier']={'index':0,'nets':['N','P']}
    report['tiers'].append(failure)
    report['active_tier']={'index':1,'nets':['A','B']}
    persist()
    saved=json.loads(output.with_suffix('.tier-progress.json').read_text())
    assert saved['tiers']==[failure]
    assert saved['active_tier']['index']==1
    assert saved['status']=='running'
    assert saved['progress_only'] and not saved['release_accepted']
    assert saved['source_sha256']==hashlib.sha256(source.read_bytes()).hexdigest()
    assert not output.exists()


def test_finished_journal_is_not_a_release_claim(tmp_path):
    source=tmp_path/'source.kicad_pcb';source.write_text('source')
    output=tmp_path/'board.kicad_pcb'
    report,persist=staged._tier_progress_report(source,output,work=None,threads=1)
    report['tiers'].append({'refused':True})
    report.update(status='finished',active_tier=None)
    persist()
    saved=json.loads(output.with_suffix('.tier-progress.json').read_text())
    assert saved['status']=='finished'
    assert saved['tiers'][0]['refused']
    assert not saved['release_accepted']
