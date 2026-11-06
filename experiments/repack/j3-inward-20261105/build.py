"""Explicit, source-bound engineering experiment. Not a board generator/release.

The selected J3 bank and its current-bearing fingers move 2 mm inwards. The
12 V lower loop is reauthored at its ORIGINAL width with a cleaner outline;
the existing upper force route and the reviewed sources remain immutable.
Run from repository root; every label creates a new private draft directory.
"""
from pathlib import Path
import argparse
import json

from shapely.geometry import Polygon, MultiPoint, box
from shapely.ops import unary_union

from cec_pipeline import drafts, repack, geometry
from cec_pipeline.native import _native

EVIDENCE = Path('docs/evidence/20261105-bottom-compaction')
BASE = Path('experiments/repack/j3-inward-20261105')
CARRIER = Path('experiments/repack/bar-corridor-20261105/carrier/board.kicad_pcb')
COVER = Path('experiments/repack/j6c-connected-20261105/cover/board.kicad_pcb')
HASH = '496e90672ac0eb24920bccde582661b895ebebb88aaca5bb46ee32db86216749'


def clean(points):
    """Drop only exactly collinear vertices, never snap or approximate."""
    out = [list(map(int, p)) for p in points]
    if out[0] == out[-1]:
        out.pop()
    while True:
        keep = []
        for i, b in enumerate(out):
            a, c = out[i-1], out[(i+1) % len(out)]
            if (b[0]-a[0])*(c[1]-b[1]) != (b[1]-a[1])*(c[0]-b[0]):
                keep.append(b)
        if len(keep) == len(out):
            return keep
        out = keep


def ring(chain):
    return [[chain.CPoint(i).x, chain.CPoint(i).y] for i in range(chain.PointCount())]


def translated_lower(point, cut=60_000_000):
    x, y = point
    return [x, y-2_000_000 if y >= cut else y]


def stroke(a, b, r=1_618_000, t=671_000):
    # Circumscribed integer octagon: apothem 1.618 mm exceeds native 12 V
    # track radius 1.615296 mm. This shapes the outline; capacity is NOT derived.
    offsets = [(r,t),(t,r),(-t,r),(-r,t),(-r,-t),(-t,-r),(t,-r),(r,-t)]
    return MultiPoint([(p[0]+dx,p[1]+dy) for p in (a,b) for dx,dy in offsets]).convex_hull


def main(label):
    assert repack.inspection.sha(CARRIER) == HASH
    pcb, quiet = _native()
    board = pcb.LoadBoard(str(CARRIER))
    tracks = {t.m_Uuid.AsString():t for t in board.GetTracks()}
    zones = {z.m_Uuid.AsString():z for z in board.Zones()}
    approved = json.loads(Path('docs/evidence/20261105-busbar-candidates/paired-request.json').read_text())
    plan = dict(schema=1,
        carrier=dict(path=str(CARRIER),sha256=HASH,
            poses=[p for p in approved['carrier']['poses'] if p['reference'] in ('J3','C9','R54')]),
        cover=dict(path=str(COVER),sha256=repack.inspection.sha(COVER),
            poses=[p for p in approved['cover']['poses'] if p['reference'] in
                   ('C37','J_KVM','C_bulk1','F5','D7','R28','C32')]),
        contract=approved['contract'],edge_ports=approved['edge_ports'])
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    planpath=EVIDENCE/(label+'-placement.json')
    assert not planpath.exists(), 'new experiment label required'
    repack.inspection.write_json(planpath,plan)
    edits={};retired=set();zone_edits=[]

    def redraw(key,points):
        assert key in tracks and key not in edits and key not in retired
        geometry.path(points,minimum_phase_nm=20_000)
        edits[key]=dict(uuid=key,points_nm=points)

    # Preserve the existing front/inner split-bank topology, each exact width,
    # layer and UUID. No capacity redistribution or parallel-sharing assumption.
    for key,t in tracks.items():
        if t.GetClass()!='PCB_TRACK':continue
        a,b=list(t.GetStart()),list(t.GetEnd())
        if t.GetNetname()=='/SENSE5V_HI' and max(a[1],b[1])>=68_000_000:
            redraw(key,[translated_lower(a,66_000_000),translated_lower(b,66_000_000)])
        if t.GetNetname()=='/SENSE3V3_HI' and max(a[1],b[1])>=68_000_000:
            redraw(key,[translated_lower(a),translated_lower(b)])

    # Reconnect 12 V input pins and replace the entire selected lower wrap with
    # one deliberate 45-degree path. Shared upper shunt route is not moved.
    loop=[[18_350_000,77_400_000],[18_350_000,78_250_000],
          [11_400_000,85_200_000],[8_300_000,85_200_000],
          [2_200_000,79_100_000],[2_200_000,36_000_000]]
    redraw('b2e852b1-b446-4347-80e2-141dd773b1d4',loop)
    bridge=[[18_349_999,77_400_000],[22_549_999,77_400_000]]
    redraw('70d61afc-3210-4567-a68b-db3813502b5c',bridge)
    retired.update(['6838fe97-289e-4967-a26f-b47df4a49f61',
        '274d7e27-7198-46ee-96b3-cfb0f048ad80','55fff7c2-e41c-42b6-a3da-2bab3d319ebf',
        '79fe3cdf-36b1-4e17-a230-d92a6543f34e','23a4f7c1-7f7b-4575-936c-b5699920bb2c',
        '84d463ed-6ea6-49ee-bd1e-95d7f24b518e','114594ee-2e2c-42c6-90ff-06c0a9936182',
        'c575735d-85ab-4969-9f1c-81227cf372ae'])

    scope=json.loads(Path('docs/evidence/20261105-bar-land/j3-up2-source-contacts.json').read_text())
    for item in scope['manual_route_suggestions_not_clearance_received']:
        keys=item['replace_source_uuid_scope']
        redraw(keys[0],[[round(x*1e6),round(y*1e6)] for x,y in item['points_mm']])
        retired.update(keys[1:])
    via_moves=[{k:r[k] for k in ('uuid','at_nm')}
               for r in scope['manual_support_via_moves_not_received']]

    def replace(key, points):
        edits.pop(key,None);retired.discard(key);redraw(key,points)

    # Retain the original safe C9 ground barrel; its new pad still overlaps it.
    # Rebuild both signal paths around R54 instead of dragging their endpoints.
    via_moves=[r for r in via_moves if r['uuid']!='143bcb91-4502-4b8d-9263-c99e2b464451']
    via_moves.append(dict(uuid='19b72a21-fd9a-4eca-8a49-234863e73e00',at_nm=[11_900_000,48_800_000]))
    replace('c3d781c3-fd04-4865-b0d1-23b073a604dc',
        [[10_550_000,47_050_000],[10_550_000,47_100_000],[10_850_000,47_400_000],
         [13_949_989,47_400_000],[14_324_990,47_775_001]])
    retired.add('319483fd-5706-4043-917d-c62a8c023aad')
    replace('260484da-9029-4624-bbe7-634592e0db1f',
        [[11_900_000,48_800_000],[11_900_000,48_500_000],[12_285_000,48_115_000],[12_800_000,48_115_000]])
    retired.update(['2ee69cb8-9798-46be-a78a-ae23351caec4','90a22bd0-3275-4a94-8da8-35fa04904bd4'])
    replace('68d5b9bc-1384-4602-b8e0-8f88943ca98e',
        [[15_400_000,45_400_000],[12_000_000,48_800_000],[11_900_000,48_800_000]])
    retired.add('bddfad92-6a70-4620-afea-309e71a6263d')

    # Do not sweep the 3V3 force trunk through C7's approved return barrel.
    edits.pop('07de3bfe-67b6-4852-b39c-be976c802185')
    right3v3=[[69_200_000,70_300_000],[63_100_000,76_400_000],[61_100_000,76_400_000]]
    replace('2d54aae3-bc76-41b1-b86d-80f1058b1f1d',right3v3)
    replace('e62a0468-da42-4dad-83af-8edcd8d499d5',
        [[60_088_000,69_488_000],[60_200_000,69_600_000],[61_000_000,69_600_000]])
    retired.update(['7d4f8c06-65a9-4308-8186-4dadd5b0bbb1','b4a9fa77-601d-4380-9e7a-170d783497f6'])

    # Full 1.256680 mm -12V route above the relocated header, same SIG2 layer.
    replace('5f99196f-9972-4af8-9201-11df7528018e',
        [[56_149_999,71_900_000],[56_149_999,69_950_001],[57_100_000,69_000_000],
         [62_000_000,69_000_000],[64_000_000,71_000_000],[67_000_000,71_000_000],
         [69_000_000,69_000_000],[69_000_000,40_500_000]])
    retired.update(['c52c85ae-9124-44ab-b390-3ba88b9a4aa1','451d357a-4584-4841-b765-bbdcf2ccfe82',
        '08dcad1a-ce6b-4c06-8c67-2aa38441cc39','b4ce7f7e-5e4c-43fe-8dd8-7ef44240379c'])
    via_moves.append(dict(uuid='3f2a0bc2-d484-4de3-a911-86f4feaad59a',at_nm=[63_000_000,68_200_000]))
    replace('d85f7780-3176-4104-a0fa-2f313e1e4cb0',[[63_000_000,68_200_000],[63_200_000,68_000_000]])
    replace('2f5bb6dc-33fc-4bfe-b3cd-208f95e61a3e',[[58_800_000,68_200_000],[63_000_000,68_200_000]])
    retired.update(['27cf239e-c466-4d07-a6ce-01590dac3471','1c8a144b-2152-42ab-aa20-792f65e896f9'])

    standby=[[26_749_999,77_400_000],[27_500_000,78_150_001],[27_500_000,79_650_000],
             [28_000_000,80_150_000],[32_100_000,80_150_000],[33_000_000,79_250_000],
             [33_000_000,77_200_000]]
    replace('61ee21af-b79c-5282-afcc-116a1d5e35bd',standby)
    retired.update(['61fb1eb8-ea49-48cd-aad3-05f124165f73','f976aec1-849f-5e86-a838-554eda6802c9',
        'bc302ef5-a63f-4e79-809c-3acdfa1e33b0','ec5d39c4-22ad-4662-abd8-fcf6e356cc36',
        'fdfd2672-7ef7-48fa-80c3-a8ef2a3da01c','5cfed91a-b3a1-4bce-ad87-50d0f8de490f',
        '387a6ca8-c384-43bc-919d-1ea35ade48d6'])
    standby_back=[[22_200_000,67_700_000],[22_200_000,68_000_000],
                  [23_400_000,69_200_000],[32_153_999,69_200_000],
                  [33_153_999,70_200_000],[33_153_999,73_954_000]]
    replace('8e3c3048-e007-4523-84a0-7827446577a5',standby_back)
    retired.update(['542d7186-7267-432f-80d5-ba4f1db3df47','5dc06a0e-3e20-4c7a-8be3-d4b4fcd19a28',
        '2efc5b3e-ded6-5789-b9e4-203545e8a5c6','d9c962e7-30ac-5b09-935d-4e93cdde1214',
        '93b27e28-0259-5a95-9215-7de01bde512b'])
    c9_overlay=json.loads((EVIDENCE/'c9-r54-local-overlay.json').read_text())
    assert c9_overlay['source_carrier']['sha256']==HASH
    for row in c9_overlay['replace_or_append_carrier_redraws']:
        replace(row['uuid'],row['points_nm'])
    retired.update(c9_overlay['append_carrier_retired_tracks'])

    # The moved opposing bulk capacitor also moves its vent projection. Keep
    # this original-width VBUS branch above that actual paired vent envelope;
    # the paired reservation itself is received in a separate explicit step.
    replace('37b10db5-01f5-4df2-b085-c2e135e7e8d5',
        [[13_500_000,49_500_000],[13_800_000,49_800_000],
         [16_450_000,49_800_000],[16_750_000,49_500_000]])
    retired.update(['d537ea09-4bf8-43d9-96e4-f9c0b496203b',
                    '6ace8f1b-0eca-4af8-88c7-88be1fd3f1e5'])

    # The relocated PTH row occupies every copper layer. Reconstruct the two
    # existing service transits at their exact native widths; do not credit a
    # front-only placement screen as evidence of an inner-layer passage.
    # +5V_SYS is an explicitly allocated consumer branch. Its separate native
    # reconstruction must re-prove that typed owner, not pass as an ordinary
    # draft redraw. The ungrouped VBUS transit can be constructed here.
    replace('bba869de-dca8-4367-b90a-5df00245a93c',
        [[27_000_000,64_500_000],[30_400_000,67_900_000],
         [50_600_000,67_900_000],[53_250_000,65_250_000]])
    retired.update(['0f06bec9-90b2-4803-8d34-3b053f7193f5',
                    '47f76ee9-d42b-4090-b87e-c784adf9d845'])

    # Explicit lower bank contours. All original holes are retained and moved
    # together with their owners; no hidden fill or hole loss is permitted.
    for key in ['4298863e-593a-4614-93d4-b005e5fa434e',
                'd76cf54f-b6a2-4073-82a1-4bbc96bd12af',
                'bc1523e2-f8ed-4455-931d-ad33ff7559e4',
                '5f1e0512-cc2a-4394-a40e-4d151e146dc8']:
        poly=zones[key].Outline();assert poly.OutlineCount()==1
        cut=66_000_000 if zones[key].GetNetname()=='/SENSE5V_HI' else 60_000_000
        outer=clean([translated_lower(p,cut) for p in ring(poly.Outline(0))])
        holes=[clean([translated_lower(p,cut) for p in ring(poly.Hole(0,i))])
               for i in range(poly.HoleCount(0))]
        edit=dict(uuid=key,polygon_nm=outer)
        if holes:edit['holes_nm']=holes
        zone_edits.append(edit)

    key='2bf47d0a-918a-48da-9713-1fa59bf7fd2b'
    old=Polygon(ring(zones[key].Outline().Outline(0)))
    domain=box(55_000_000,58_000_000,100_000_000,100_000_000)
    route=[[69_200_000,57_800_000],*right3v3]
    new=unary_union([old.difference(domain),*[stroke(a,b,3_271_000,1_355_000)
                     for a,b in zip(route,route[1:])]])
    assert new.geom_type=='Polygon' and new.is_valid and not new.interiors
    zone_edits.append(dict(uuid=key,polygon_nm=clean(new.exterior.coords)))

    key='0f7c0835-f6bb-486c-b4cb-2603fbe75190'
    old=Polygon(ring(zones[key].Outline().Outline(0)))
    new=unary_union([old.intersection(box(-1e8,73_000_000,1e8,1e8)),
        *[stroke(a,b,302_000,126_000) for a,b in zip(standby_back,standby_back[1:])]])
    assert new.geom_type=='Polygon' and new.is_valid and not new.interiors
    zone_edits.append(dict(uuid=key,polygon_nm=clean(new.exterior.coords)))

    key='4d6fd6d5-8a6d-45b3-900a-ba464f12dcb1'
    zone_standby=standby[:-1]+[[33_000_000,78_000_000]]
    new=unary_union([stroke(a,b,302_000,126_000) for a,b in zip(zone_standby,zone_standby[1:])])
    zone_edits.append(dict(uuid=key,polygon_nm=clean(new.exterior.coords)))

    key='7c664019-6774-4c0c-aded-21ce3846fbe2'
    old=Polygon(ring(zones[key].Outline().Outline(0)))
    upper=box(-1e8,-1e8,1e8,60_000_000)
    lower_loop=loop[:-1]+[[2_200_000,59_900_000]]
    lower_strokes=[stroke(a,b) for a,b in zip(lower_loop,lower_loop[1:])]
    new=unary_union([old.intersection(upper),*lower_strokes,stroke(*bridge)])
    assert new.geom_type=='Polygon' and not new.interiors and new.is_valid
    assert new.intersection(upper).symmetric_difference(old.intersection(upper)).area==0
    zone_edits.append(dict(uuid=key,polygon_nm=clean(new.exterior.coords)))

    request=dict(schema=5,placement=dict(path=str(planpath),sha256=repack.inspection.sha(planpath)),
        board_hints=dict(carrier='atx-24pin-rev3',cover='hub-standard-rev2'),
        redraws=dict(carrier=list(edits.values()),cover=[]),
        retired_tracks=dict(carrier=sorted(retired),cover=[]),
        via_moves=dict(carrier=via_moves,cover=[]),flatbars=dict(carrier=[],cover=[]),
        via_copies=dict(carrier=[],cover=[]),zone_redraws=dict(carrier=zone_edits,cover=[]))
    repack.inspection.write_json(EVIDENCE/(label+'-request.json'),request)
    repack.inspection.write_json(EVIDENCE/(label+'-construction-scope.json'),dict(
        source_sha256=HASH,carrier_pose_count=len(plan['carrier']['poses']),
        redraw_count=len(edits),retired_count=len(retired),zone_count=len(zone_edits),
        unchanged_upper_12V_zone_symmetric_difference_area_nm2=0,
        retained_12V_track_width_nm=3_230_592,routing_admitted=False,
        current_qualified=False,outline_changed=False,
        cover_is_mechanical_pose_only=True))
    receipt=drafts.stage(request,BASE/label,refill=True)
    print(json.dumps(dict(complete=receipt['complete'],boards=[r['path'] for r in receipt['boards']],
                         routing_admitted=False)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('label');args=parser.parse_args()
    main(args.label)
