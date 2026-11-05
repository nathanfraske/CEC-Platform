"""Native package-access tests; identities and global rotation are arbitrary."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))
import pytest
import cec_swig_guard
cec_swig_guard.pin()
import pcbnew
import cec_fr
from test_kelvin_discipline import _fp,_pad_smd,_snap,_is_ortho


@pytest.mark.parametrize('angle',[0,90,180,270])
def test_unlocked_kelvin_cell_uses_exact_package_escape(angle):
    b=pcbnew.CreateEmptyBoard()
    nets={}
    for index,name in enumerate(('SENSE_HI','SENSE_LO','GROUND','SUPPLY'),1):
        net=pcbnew.NETINFO_ITEM(b,name,index);b.Add(net);nets[name]=net
    hi,lo,gnd,vcc=(nets[name] for name in ('SENSE_HI','SENSE_LO','GROUND','SUPPLY'))
    rs=_fp(b,'SHUNT_A','0.5mOhm')
    _pad_smd(rs,'1',lo,10,10,1.8,1.8)
    _pad_smd(rs,'2',hi,10,18,1.8,1.8)
    ina=_fp(b,'MONITOR_B','INA181')
    ina.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(14),pcbnew.FromMM(13)))
    for num,net,x,y in (('4',lo,14.95,11.8625),('5',gnd,14,11.8625),
                        ('6',vcc,13.05,11.8625),('3',hi,14.95,14.1375),
                        ('2',gnd,14,14.1375),('1',vcc,13.05,14.1375)):
        _pad_smd(ina,num,net,x,y,.6,1.325)
    for fp in b.GetFootprints():
        fp.Rotate(pcbnew.VECTOR2I(0,0),pcbnew.EDA_ANGLE(angle,pcbnew.DEGREES_T))
    assert not list(b.GetTracks())
    report=cec_fr.synthesize_kelvin_taps(b,kelvin_pairs=[('SENSE_HI','SENSE_LO')])
    assert not report['refused'],report
    assert report['taps']==2
    assert all(_is_ortho(segment) for segment in _snap(b))
    assert all('(canonical)' in label for labels in report['by_net'].values() for label in labels)
