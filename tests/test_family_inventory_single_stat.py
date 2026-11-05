from pathlib import Path
import pytest
import cec_force_current as force


def test_each_companion_uses_one_nonfollowing_metadata_read(tmp_path,monkeypatch):
    source=tmp_path/'renamed.kicad_pcb';source.write_bytes(b'board')
    source.with_suffix('.kicad_pro').write_bytes(b'project')
    source.with_suffix('.future-opaque').write_bytes(b'opaque')
    calls=[];old_lstat=Path.lstat
    def lstat(path):calls.append(path);return old_lstat(path)
    monkeypatch.setattr(Path,'lstat',lstat)
    companions,metadata=force._companion_inventory(source)
    assert sorted(calls)==sorted(companions.values())
    assert len(calls)==len(set(calls))
    assert metadata['.kicad_pro']and metadata['.future-opaque']
    assert metadata['.kicad_dru']is None


@pytest.mark.parametrize('fault',['symlink','broken_symlink','hardlink','directory','vanished_unknown'])
def test_fast_metadata_path_preserves_alias_and_unknown_absence_refusals(tmp_path,monkeypatch,fault):
    source=tmp_path/'renamed.kicad_pcb';source.write_bytes(b'board')
    other=source.with_suffix('.future-opaque')
    if fault=='symlink':other.symlink_to(source)
    elif fault=='broken_symlink':other.symlink_to(tmp_path/'missing')
    elif fault=='hardlink':other.hardlink_to(source)
    elif fault=='directory':other.mkdir()
    else:
        other.write_bytes(b'opaque');old=Path.lstat
        def lstat(path):
            if path==other:raise FileNotFoundError(path)
            return old(path)
        monkeypatch.setattr(Path,'lstat',lstat)
    with pytest.raises(ValueError,match='saved-family companion'):
        force._companion_inventory(source)
