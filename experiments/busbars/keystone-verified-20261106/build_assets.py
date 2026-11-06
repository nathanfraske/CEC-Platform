"""Build the documented component only; never modify a product PCB or netlist.

The component outline is tolerance-bounded. No constant-height clearance tunnel
or PCB copper span is fabricated from the drawing's undimensioned bend profile.
"""
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid

WORK = Path(__file__).resolve().parent
ROOT = WORK.parents[2]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'src')]
from cec_pipeline.native import _native
import cec_assembly_envelope as assembly

p, _quiet = _native()
profile_path = WORK / 'part.json'
profile = json.loads(profile_path.read_text())
source = ROOT / profile['drawing']['path']
sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
assert sha(source) == profile['drawing']['sha256']

# Enclose both printed unit systems rather than exploit rounding differences.
def bounds(dimension):
    tol = profile['drawing']
    return [round(min(dimension['mm'] - tol['general_tolerance_mm'],
                      (dimension['inch'] - tol['general_tolerance_in']) * 25.4), 7),
            round(max(dimension['mm'] + tol['general_tolerance_mm'],
                      (dimension['inch'] + tol['general_tolerance_in']) * 25.4), 7)]

dimensions = {name: bounds(value) for name, value in profile['component_dimensions'].items()}
lands = profile['land_pattern_mm']
assert abs((lands['outer_extent'] - lands['inner_gap']) / 2 - lands['derived_length']) < 1e-9
assert abs(lands['derived_length'] + lands['inner_gap'] - lands['derived_center_pitch']) < 1e-9
assert dimensions['height_from_foot_bottom'][1] > profile['installed_geometry']['backside_reference_minimum_mm']

name = 'Keystone_5104TR_DrawingA_ApplicationPending'
library_name = 'CEC_Keystone_Study'
library = WORK / (library_name + '.pretty')
library.mkdir(exist_ok=True)
fp = p.FOOTPRINT(None)
fp.SetFPID(p.LIB_ID(library_name, name))
fp.SetReference('BB**')
fp.SetValue('5104TR')
fp.SetLayer(p.F_Cu)
fp.SetAttributes(p.FP_SMD)
fp.SetDuplicatePadNumbersAreJumpers(True)
fp.SetLibDescription('Keystone 5104 Rev A recommended lands; source-bounded body. Application and installed-clearance qualification pending. Only solder lands are PCB copper.')
fields = dict(Manufacturer=profile['manufacturer'], MPN='5104TR', LCSC='C7466142',
              Datasheet=profile['drawing']['manufacturer_url'],
              Source_profile_sha256=sha(profile_path),
              Qualification='DOCUMENTED_COMPONENT_APPLICATION_PENDING',
              Height_bare_part_max_mm=str(dimensions['height_from_foot_bottom'][1]),
              Underbridge_clearance='UNKNOWN_NOT_A_CONSTANT_HEIGHT_TUNNEL',
              Catalog_current_A='20_WITH_PUBLISHED_TEMPERATURE_CONDITIONS',
              Application_current_qualification='PENDING',
              Electrical_model='COMPONENT_METAL_AND_TWO_SEPARATE_SOLDER_JOINTS')
for key, value in fields.items():
    fp.SetField(key, value)
for field in fp.GetFields():
    field.SetLayer(p.F_Fab)
    field.SetVisible(False)
fp.Reference().SetLayer(p.F_SilkS)
fp.Reference().SetVisible(True)
fp.Reference().SetPosition(p.VECTOR2I_MM(0, -2.6))
for side in (-1, 1):
    pad = p.PAD(fp)
    pad.SetNumber('1')
    pad.SetAttribute(p.PAD_ATTRIB_SMD)
    pad.SetShape(p.PAD_SHAPE_RECT)
    pad.SetPosition(p.VECTOR2I_MM(side * lands['derived_center_pitch'] / 2, 0))
    pad.SetSize(p.VECTOR2I_MM(lands['derived_length'], lands['width']))
    layers = p.LSET()
    for layer in (p.F_Cu, p.F_Paste, p.F_Mask):
        layers.AddLayer(layer)
    pad.SetLayerSet(layers)
    fp.Add(pad)

def rectangle(half_x, half_y, layer, stroke):
    corners = [(-half_x,-half_y), (half_x,-half_y), (half_x,half_y), (-half_x,half_y)]
    for a, b in zip(corners, corners[1:] + corners[:1]):
        edge = p.PCB_SHAPE(fp)
        edge.SetShape(p.SHAPE_T_SEGMENT)
        edge.SetStart(p.VECTOR2I_MM(*a))
        edge.SetEnd(p.VECTOR2I_MM(*b))
        edge.SetWidth(p.FromMM(stroke))
        edge.SetLayer(layer)
        fp.Add(edge)

rectangle(dimensions['length'][1] / 2, dimensions['maximum_plan_width'][1] / 2, p.F_Fab, .1)
rectangle(max(lands['outer_extent'], dimensions['length'][1]) / 2 + .25,
          max(lands['width'], dimensions['maximum_plan_width'][1]) / 2 + .25, p.F_CrtYd, .05)
fields_for_ids = fp.GetFields()
for index, item in enumerate([fp, *fp.Pads(), *fp.GraphicalItems(), *fields_for_ids]):
    item.m_Uuid.Clone(p.KIID(str(uuid.uuid5(uuid.NAMESPACE_URL, 'cec:keystone5104:DrawingA:' + str(index)))))
p.PCB_IO_KICAD_SEXPR().FootprintSave(str(library), fp)
footprint_path = library / (name + '.kicad_mod')
# KiCad's library serializer refreshes mandatory field UUIDs. Normalize this
# NEW library asset only, then read it back natively. No board identities change.
serial_index = iter(range(1000))
footprint_path.write_text(re.sub(r'\(uuid "[^\"]+"\)',
    lambda _: '(uuid "' + str(uuid.uuid5(uuid.NAMESPACE_URL,
        'cec:keystone5104:DrawingA:serialized:' + str(next(serial_index)))) + '")',
    footprint_path.read_text()))
saved = p.FootprintLoad(str(library), name)
assert saved.GetDuplicatePadNumbersAreJumpers()
pads = list(saved.Pads())
assert len(pads) == 2
assert all(pad.GetNumber() == '1' and not pad.HasHole() for pad in pads)
assert sorted(tuple(pad.GetPosition()) for pad in pads) == [(-5350000,0), (5350000,0)]
assert all(tuple(pad.GetSize()) == (2600000,2800000) for pad in pads)
assert all(set(pad.GetLayerSet().Seq()) == {p.F_Cu,p.F_Paste,p.F_Mask} for pad in pads)
assert not list(saved.Zones())
assert all(g.GetLayer() in (p.F_Fab,p.F_CrtYd) for g in saved.GraphicalItems())
saved.BuildCourtyardCaches()
court = assembly.polygon_from_native(saved.GetCourtyard(p.F_Cu))
assert all(court.covers(assembly.polygon_from_native(pad.GetEffectivePolygon(p.F_Cu))) for pad in pads)

symbol = ['(kicad_symbol_lib (version 20251024) (generator "kicad_symbol_editor")',
          f'(symbol "{name}" (exclude_from_sim yes) (in_bom yes) (on_board yes) (duplicate_pin_numbers_are_jumpers yes)']
for key, value in dict(Reference='BB', Value='5104TR', Footprint=library_name+':'+name, **fields).items():
    hide = '' if key in ('Reference','Value') else '(hide yes)'
    y = -5.08 if key == 'Value' else 5.08
    symbol.append(f'(property {json.dumps(key)} {json.dumps(value)} (at 0 {y} 0) {hide} (effects (font (size 1.27 1.27))))')
symbol += [f'(symbol "{name}_0_1" (rectangle (start -2.54 2.54) (end 2.54 -2.54) (stroke (width 0) (type default)) (fill (type background))))',
           f'(symbol "{name}_1_1" (pin passive line (at -5.08 0 0) (length 2.54) (name "LINK" (effects (font (size 1.27 1.27)))) (number "1" (effects (font (size 1.27 1.27)))))))', ')']
(WORK / (library_name + '.kicad_sym')).write_text('\n'.join(symbol) + '\n')
report = dict(schema=1, scope='SOURCE_BOUND_COMPONENT_ASSETS_NOT_INSTALLED_OR_APPLICATION_QUALIFIED',
              drawing_sha256=sha(source), profile_sha256=sha(profile_path), dimension_ranges_mm=dimensions,
              bare_part_maximum_height_mm=dimensions['height_from_foot_bottom'][1],
              conditional_central_underside_arithmetic_mm=round(dimensions['height_from_foot_bottom'][0]-dimensions['material_thickness'][1],7),
              underside_arithmetic_is_not_guaranteed_clearance=True,
              guaranteed_underbridge_rectangle=None,
              backside_original_reference_rejected=True,
              footprint_sha256=sha(library/(name+'.kicad_mod')),
              symbol_sha256=sha(WORK/(library_name+'.kicad_sym')),
              native_land_centers_nm=[[-5350000,0],[5350000,0]], land_size_nm=[2600000,2800000],
              native_cached_courtyard_bounds_mm=list(court.bounds),
              native_readback_pass=True, span_PCB_copper_present=False, product_boards_written=0,
              source_schematic_integrated=False, current_qualified=False, assembled_Z_qualified=False,
              release_authority=False)
(WORK / 'asset-receipt.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report, indent=2))
