"""Construct a mask-search-aware annotation through all frozen worker gates."""
from pathlib import Path
import cec_force_current as force
_MASK_WORKER_PARENT = Path('build/root_run_mask_guarded_reference_mapping_20261020.py')
_mask_worker_hash = force._hash(_MASK_WORKER_PARENT)
def source_code():
    text = _MASK_WORKER_PARENT.read_text()
    old = 'import cec_dense_reference_mapping as mapping'
    assert text.count(old) == 1
    text = text.replace(old, 'import cec_mask_search_reference_mapping as mapping')
    old = 'p = argparse.ArgumentParser(description=__doc__)'
    assert text.count(old) == 1
    text = text.replace(old, "assert force._hash(_MASK_WORKER_PARENT)==_mask_worker_hash\n" + old)
    old = 'input_sha256={str(q.resolve())'
    assert text.count(old) == 1
    text = text.replace(old, 'input_sha256={**{str(q.resolve())')
    old = "         Path(proposal['binding']['native_report'])]},"
    assert text.count(old) == 1
    text = text.replace(old, """         Path(proposal['binding']['native_report'])]},
        **{str(_MASK_WORKER_PARENT.resolve()):_mask_worker_hash},
        **proposal['mask_search_binding']['input_sha256']},""")
    return text


if __name__ == '__main__':
    exec(compile(source_code(), str(__file__), 'exec'), globals())
