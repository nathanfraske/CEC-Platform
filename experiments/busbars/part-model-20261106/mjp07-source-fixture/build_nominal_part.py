"""Create the independent MJP-0.7 nominal asset, never modify other parts."""
import hashlib,json,sys,uuid
from pathlib import Path
WORK=Path(__file__).resolve().parent;ROOT=WORK.parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
import cec_swig_guard
import pcbnew
cec_swig_guard.pin()
profile=WORK/'mac8-mjp-0.7-nominal.json';p=json.loads(profile.read_text())
oldlib=WORK.parent/'CEC_Busbar_Prototype.pretty'
source=oldlib/'Mac8_MJP_1p0_NOMINAL_PROTOTYPE.kicad_mod'
before=hashlib.sha256(source.read_bytes()).hexdigest()
fp=pcbnew.FootprintLoad(str(oldlib),'Mac8_MJP_1p0_NOMINAL_PROTOTYPE')
name='Mac8_MJP_0p7_NOMINAL_PROTOTYPE'
fp.SetFPID(pcbnew.LIB_ID('CEC_MJP07_Prototype',name));fp.SetValue(name)
fp.SetLibDescription('MJP-0.7 exact MPN NOMINAL PROTOTYPE: phosphor bronze, Sn/Ni; NOT copper.20A catalog only, not solder-joint/path/current/Z qualification.')
for key,value in dict(MPN='MJP-0.7',Material='PHOSPHOR_BRONZE_NOT_COPPER',Finish='TIN_OVER_NICKEL',
    Source_profile_sha256=hashlib.sha256(profile.read_bytes()).hexdigest(),
    Reel_MPN='MJP-0.7-T',Reel_quantity='700',Reel_tape_width_mm='32',
    Qualification='NOMINAL_PROTOTYPE_NOT_RELEASED').items():fp.SetField(key,value)
for field in fp.GetFields():
    field.SetLayer(pcbnew.F_Fab);field.SetVisible(False)
fp.Reference().SetLayer(pcbnew.F_SilkS);fp.Reference().SetVisible(True)
fp.Reference().SetPosition(pcbnew.VECTOR2I(0,-2500000))
fp.Value().SetPosition(pcbnew.VECTOR2I(0,2500000))
for pad in fp.Pads():
    pad.SetPosition(pcbnew.VECTOR2I((-1 if pad.GetPosition().x<0 else 1)*p['pitch_nm']//2,0))
    pad.SetSize(pcbnew.VECTOR2I(p['land_length_nm'],p['land_width_nm']))
for edge in fp.GraphicalItems():
    assert edge.GetLayer()in(pcbnew.F_Fab,pcbnew.F_CrtYd)
    half=(p['body_length_nm']//2 if edge.GetLayer()==pcbnew.F_Fab else
          (p['pitch_nm']+p['land_length_nm'])//2+250000)
    for getter,setter in((edge.GetStart,edge.SetStart),(edge.GetEnd,edge.SetEnd)):
        point=getter();setter(pcbnew.VECTOR2I((-1 if point.x<0 else 1)*half,point.y))
for index,item in enumerate([fp,*fp.Pads(),*fp.GraphicalItems(),*fp.GetFields()]):
    item.m_Uuid.Clone(pcbnew.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL,'cec:mjp07:nominal:'+str(index)))))
assert fp.GetDuplicatePadNumbersAreJumpers()
library=WORK/'CEC_MJP07_Prototype.pretty';library.mkdir(exist_ok=True)
pcbnew.PCB_IO_KICAD_SEXPR().FootprintSave(str(library),fp)
assert hashlib.sha256(source.read_bytes()).hexdigest()==before
saved=pcbnew.FootprintLoad(str(library),name)
assert sorted(tuple(p.GetPosition())for p in saved.Pads())==[(-8890000,0),(8890000,0)]
assert all(p.GetNumber()=='1'for p in saved.Pads())
print(name)
