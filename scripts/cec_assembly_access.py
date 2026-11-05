"""Hash-bound planar access screen for an explicitly selected pair of PCBs.

Use actual mating datums, board contours and connector courtyards. This is
not a 3D engagement, tool-access or hardware-qualification certificate.
Nothing is moved and a successful screen never grants fabrication release.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path


def screen(carrier_points, cover_points, cover_polygon, ports, *,
           mirror_x=False, rotation_deg=0., tolerance_mm=.05):
    """Pure, board-independent screen in the carrier's coordinate frame."""
    from shapely import affinity
    from shapely.geometry import Polygon, box
    if (len(carrier_points) < 3 or len(carrier_points) != len(cover_points)
            or not math.isfinite(tolerance_mm) or tolerance_mm <= 0):
        raise ValueError('at least three paired datums and a positive tolerance are required')
    values = [v for p in [*carrier_points, *cover_points] for v in p]
    if (any(len(p) != 2 for p in [*carrier_points, *cover_points])
            or not all(math.isfinite(float(v)) for v in values)):
        raise ValueError('finite two-dimensional mating datums are required')
    if Polygon(cover_points).convex_hull.area <= tolerance_mm**2:
        raise ValueError('mating datums must not be collinear')
    if (cover_polygon.is_empty or not cover_polygon.is_valid
            or not math.isfinite(float(rotation_deg))):
        raise ValueError('valid actual cover contour and finite rotation required')
    angle=math.radians(rotation_deg)
    c,s=math.cos(angle),math.sin(angle)
    reflection=-1. if mirror_x else 1.
    matrix=(c*reflection,-s,s*reflection,c)
    a,b,d,e=matrix
    shifts=[(tx-a*x-b*y,ty-d*x-e*y)
            for (tx,ty),(x,y) in zip(carrier_points,cover_points)]
    dx=sum(p[0] for p in shifts)/len(shifts)
    dy=sum(p[1] for p in shifts)/len(shifts)
    error=max(math.dist((dx,dy),p) for p in shifts)
    if error > tolerance_mm:
        return {'ok':False,'reason':'mating_datums_disagree','max_datum_error_mm':error,
                'ports':[],'release_accepted':False}
    cover=affinity.affine_transform(cover_polygon,[*matrix,dx,dy])
    rows=[]
    if not ports:
        raise ValueError('access ports must be explicitly declared')
    for port in ports:
        edge=port['edge']; guard=float(port['clearance_mm'])
        coords=tuple(float(v) for v in port['courtyard_xyxy'])
        if (edge not in ('top','bottom','left','right') or len(coords)!=4
                or not all(math.isfinite(v) for v in (*coords,guard))
                or guard<0 or coords[2]<=coords[0] or coords[3]<=coords[1]):
            raise ValueError('invalid declared access envelope')
        x0,y0,x1,y1=coords
        left,top,right,bottom=cover.bounds
        strip=(box(x0-guard,top-guard-1,x1+guard,bottom+guard+1)
               if edge in ('top','bottom') else
               box(left-guard-1,y0-guard,right+guard+1,y1+guard))
        clipped=cover.intersection(strip)
        gap=None
        if not clipped.is_empty:
            cl,ct,cr,cb=clipped.bounds
            gap={'top':ct-y1,'bottom':y0-cb,'left':cl-x1,'right':x0-cr}[edge]
        rows.append({**port,'gap_mm':gap,'ok':gap is None or gap+1e-9>=guard,
                     'tangential_overlap':not clipped.is_empty})
    return {'schema':1,'ok':all(p['ok'] for p in rows),
            'transform':{'matrix':list(matrix),'translation_mm':[dx,dy]},
            'max_datum_error_mm':error,'cover_bounds_xyxy':list(cover.bounds),
            'cover_outline_xy':list(cover.exterior.coords), 'ports':rows,
            'release_accepted':False,'qualification':'planar-courtyard-access-only'}


def evaluate(carrier_path, cover_path, contract):
    import pcbnew
    import cec_swig_guard
    cec_swig_guard.pin()
    from shapely.geometry import Polygon
    from cec_placement_checkpoint import sha
    carrier_path,cover_path=Path(carrier_path).resolve(),Path(cover_path).resolve()
    identities={'carrier':{'path':str(carrier_path),'sha256':sha(carrier_path)},
                'cover':{'path':str(cover_path),'sha256':sha(cover_path)}}
    carrier=pcbnew.LoadBoard(str(carrier_path)); cover=pcbnew.LoadBoard(str(cover_path))
    fps=[{fp.GetReference():fp for fp in board.GetFootprints()} for board in (carrier,cover)]
    try:
        points=[[],[]]
        for pair in contract['anchor_pairs']:
            for i,ref in enumerate(pair):
                pos=fps[i][ref].GetPosition()
                points[i].append((pos.x/1e6,pos.y/1e6))
        poly=pcbnew.SHAPE_POLY_SET()
        if not cover.GetBoardPolygonOutlines(poly,False) or poly.OutlineCount()!=1:
            raise ValueError('cover needs one closed actual board contour')
        chain=poly.Outline(0)
        # Interior holes are not assumed to be qualified cable-access windows.
        outline=Polygon([(chain.CPoint(i).x/1e6,chain.CPoint(i).y/1e6)
                         for i in range(chain.PointCount())])
        ports=[]
        for row in contract['ports']:
            fp=fps[0][row['ref']]
            courtyard=fp.GetCourtyard(fp.GetLayer())
            if courtyard.OutlineCount()<1:
                raise ValueError('access footprint has no native courtyard: '+row['ref'])
            bounds=courtyard.BBox()
            ports.append({**row,'courtyard_xyxy':[
                bounds.GetLeft()/1e6,bounds.GetTop()/1e6,
                bounds.GetRight()/1e6,bounds.GetBottom()/1e6]})
        result=screen(*points,outline,ports,
            mirror_x=bool(contract.get('mirror_x',False)),
            rotation_deg=float(contract.get('rotation_deg',0.)),
            tolerance_mm=float(contract.get('datum_tolerance_mm',.05)))
        if result.get('transform') and contract.get('contact_pairs'):
            from cec_stack_fit_screen import contact_registration
            tf=[*result['transform']['matrix'],*result['transform']['translation_mm']]
            fields=[]
            for pair in contract['contact_pairs']:
                contacts=[]
                for i,ref in enumerate(pair):
                    contacts.append([dict(id=p.GetNumber(),
                        xy=[p.GetPosition().x/1e6,p.GetPosition().y/1e6],
                        role='declared-contact:'+p.GetNumber()) for p in fps[i][ref].Pads()])
                fields.append(dict(pair=pair,**contact_registration(*contacts,tf,
                    tolerance_mm=float(contract.get('datum_tolerance_mm',.05)))))
            result['contact_registration']=fields
            result['electrical_pin_roles_checked']=False  # separate domain contract
            if not all(field['ok'] for field in fields):
                result.update(ok=False,reason='physical_contact_registration_failed')
    except (KeyError,ValueError,TypeError,IndexError) as exc:
        result={'ok':False,'reason':str(exc),'ports':[],'release_accepted':False}
    result['sources']=identities
    result['source_inputs_unchanged']=all(sha(row['path'])==row['sha256'] for row in identities.values())
    if not result['source_inputs_unchanged']:
        result.update(ok=False,reason='paired source changed during evaluation')
    return result


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--carrier',required=True)
    parser.add_argument('--cover',required=True)
    parser.add_argument('--contract',required=True)
    parser.add_argument('--out',required=True)
    args=parser.parse_args(argv)
    from cec_placement_checkpoint import atomic_json,sha
    contract=Path(args.contract).resolve()
    digest=sha(contract)
    result=evaluate(args.carrier,args.cover,json.loads(contract.read_text()))
    result['contract']={'path':str(contract),'sha256':digest}
    if sha(contract)!=digest:
        result.update(ok=False,reason='assembly contract changed during evaluation')
    atomic_json(Path(args.out),result)
    print(json.dumps({k:result.get(k) for k in ('ok','reason','ports','release_accepted')},indent=2))
    return 0 if result['ok'] else 2


if __name__=='__main__':
    raise SystemExit(main())
