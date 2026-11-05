"""Fresh typed Source-to-manufacturer footprint parity, never name aliases.

Only an existing exact-MPN catalog rule with a hash-bound primary drawing
can participate. Canonical symbol, fresh exporter, native selected part and
the complete registered lands must agree. No Source or PCB is modified.
This establishes a derived footprint relationship, not canonical Source
convergence, current/assembly/thermal/factory or release qualification.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import time

import pcbnew
import cec_force_current as force
import cec_manufacturer_land_pattern as patterns
import cec_measurement_leaf as binding
import cec_source_ground_leaf as source
import cec_sch_lint as sch
import cec_synth_pipeline as synth
from cec_footprint_fields import footprint_properties


def need(ok,why):
    if not ok:raise ValueError(why)


def stable(value):return json.loads(json.dumps(value,sort_keys=True,allow_nan=False))


def tick(deadline):need(time.monotonic()<deadline,'manufacturer_footprint_parity_deadline')


def candidate_present(board):
    names={r['library']+':'+r['new']for r in patterns.CATALOG.values()
        if r.get('selected_mpn')and r.get('manufacturer')and r.get('datasheet_sha256')}
    return any(fp.GetFPIDAsString()in names for fp in board.GetFootprints())


def native_epoch(board,*,deadline):
    """Whole RAM conductor binding PLUS complete FP-only native formatting.

    The old conductor walk deliberately omits fields, mask/paste overrides,
    courts, artwork and jumpers. It cannot fence a manufacturing-part proof.
    Never format BOARD or save/reload it: both could normalize connectivity.
    """
    owners=list(board.GetFootprints());need(len(owners)<=4096,'bounded_native_manufacturer_population_required')
    result={}
    for fp in owners:
        tick(deadline);uid=force._uid(fp);need(uid not in result,'unique_manufacturer_native_footprint_uuid_required')
        io=pcbnew.PCB_IO_KICAD_SEXPR();io.Format(fp)
        result[uid]=hashlib.sha256(io.GetStringOutput(False).encode()).hexdigest()
    tick(deadline)
    return dict(conductors=stable(binding._binding(board)),complete_footprint_material=result)


def _pad(p):
    need(p.Padstack().Mode()==pcbnew.PADSTACK.MODE_NORMAL,
        'manufacturer_parity_requires_ordinary_complete_padstack')
    return (patterns._pad(p),p.GetLocalClearance(),p.GetLocalSolderMaskMargin(),
        p.GetLocalSolderPasteMargin(),p.GetLocalSolderPasteMarginRatio(),
        int(p.GetZoneConnectionOverrides(None)))


def _art(fp):
    manufacturing=set(map(int,pcbnew.LSET.AllCuMask().Seq()))
    manufacturing|={int(pcbnew.F_Mask),int(pcbnew.B_Mask),int(pcbnew.F_Paste),int(pcbnew.B_Paste)}
    items=[*fp.GraphicalItems(),*[f for f in fp.GetFields()if f.IsVisible()]]
    selected=[item for item in items if int(item.GetLayer())in manufacturing]
    need(all(i.GetClass()=='PCB_SHAPE'and i.GetShape()in(pcbnew.SHAPE_T_SEGMENT,pcbnew.SHAPE_T_RECT)
        for i in selected),'unknown_manufacturing_artwork_in_manufacturer_footprint')
    return sorted(patterns._edge(i)for i in selected)


def _geometry(fp,rule):
    """Re-run the actual catalog recipe, not a nominal-name comparison."""
    library=patterns._library(rule)
    predecessor=patterns._placed(rule['old'],fp,library=library)
    predecessor.SetFPIDAsString(rule['library']+':'+rule['old'])
    predecessor.SetValue(fp.GetValue());predecessor.SetField('MPN',footprint_properties(fp)['MPN'])
    _model,actual_rule,old,target=patterns._selected(predecessor)
    need(actual_rule==rule,'unique_existing_manufacturer_recipe_required')
    actual=list(fp.Pads());expected=list(target.Pads())
    need(actual and len(actual)==len(expected)==len({p.GetNumber()for p in actual})
        and sorted(map(_pad,actual))==sorted(map(_pad,expected)),
        'actual_native_lands_differ_from_complete_manufacturer_recipe')
    need(all(i.GetClass()=='PCB_SHAPE'and i.GetShape()in(pcbnew.SHAPE_T_SEGMENT,pcbnew.SHAPE_T_RECT)
        for i in patterns._courts(fp))and sorted(map(patterns._edge,patterns._courts(fp)))
        ==sorted(map(patterns._edge,patterns._courts(target))),
        'actual_native_courtyard_differs_from_manufacturer_recipe')
    for getter in('GetLocalClearance','GetLocalSolderMaskMargin','GetLocalSolderPasteMargin','GetLocalSolderPasteMarginRatio'):
        need(getattr(fp,getter)()==getattr(target,getter)(),
            'footprint_manufacturing_override_differs:'+getter)
    need(_art(fp)==_art(target),'actual_manufacturing_artwork_differs_from_registered_recipe')
    need(fp.GetLibDescription()==target.GetLibDescription(),
        'actual_manufacturer_footprint_description_differs')
    return dict(actual_pad_numbers=sorted(p.GetNumber()for p in actual),
        complete_native_land_courtyard_and_manufacturing_overrides_received=True)


def _part(fp,comp,entries,node_nets,deadline):
    tick(deadline);ref=fp.GetReference()
    need(len(entries)==1 and comp is not None,'unique_canonical_and_exported_manufacturer_instance_required')
    path,sf,symbol,instance=entries[0]
    blocks=[block for tag,block in sf.children if tag=='symbol'and sch.prop_value(block,'Reference')==ref]
    need(len(blocks)==1 and symbol.get('uuid'),'unique_actual_manufacturer_symbol_required')
    block=blocks[0];tree=synth.parse_sexpr(block);properties=list(synth._kids(tree,'property'))
    names=[p[1]for p in properties if len(p)>=3]
    need(len(names)==len(properties)==len(set(names)),'unambiguous_canonical_manufacturer_properties_required')
    need(not fp.IsDNP()and not fp.IsExcludedFromBOM()
        and all(synth._val(tree,k,default)in(values)for k,default,values in(
            ('dnp','no',('no',)),('in_bom','yes',('yes',)),('on_board','yes',('yes',)))),
        'populated_source_selected_manufacturer_component_required')
    exported_nodes=list(synth._kids(comp,'property'))
    exported={synth._val(p,'name',''):synth._val(p,'value','')for p in exported_nodes}
    need(len(exported)==len(exported_nodes),'unambiguous_exported_manufacturer_properties_required')
    native=footprint_properties(fp)
    for key in('MPN','Manufacturer'):
        value=sch.prop_value(block,key)
        need(type(value)is str and value.strip()and value==exported.get(key)==native.get(key),
            'canonical_export_native_manufacturer_identity_differs:'+key)
    matches=[r for r in patterns.CATALOG.values()if r.get('selected_mpn')==native['MPN']
        and r.get('manufacturer')==native['Manufacturer']
        and r.get('datasheet')and r.get('datasheet_sha256')]
    need(len(matches)==1,'exact_selected_mpn_primary_drawing_recipe_required')
    rule=matches[0]
    need(sch.prop_value(block,'Footprint')==synth._val(comp,'footprint','')==rule['library']+':'+rule['old']
        and fp.GetFPIDAsString()==rule['library']+':'+rule['new'],
        'explicit_canonical_predecessor_and_actual_registered_successor_required')
    need(sch.prop_value(block,'Value')==synth._val(comp,'value','')==fp.GetValue(),
        'canonical_export_native_manufacturer_value_differs')
    need(synth._val(comp,'tstamps','')==symbol['uuid'],'manufacturer_symbol_uuid_differs')
    sheet=synth._first(comp,'sheetpath');native_path=fp.GetPath().AsString()
    need(not instance or synth._val(sheet,'tstamps','')=='/'+'/'.join(instance)+'/',
        'manufacturer_exported_sheet_instance_differs')
    need(not native_path or native_path.rstrip('/').split('/')[-1]==symbol['uuid']
        and(not instance or '/'+('/'.join(instance))+'/'in native_path),
        'manufacturer_native_sheet_instance_differs')
    libsource=synth._first(comp,'libsource');lib_id=symbol.get('lib_id','')
    need(':'in lib_id and (synth._val(libsource,'lib',''),synth._val(libsource,'part',''))
        ==tuple(lib_id.rsplit(':',1)),'manufacturer_source_symbol_library_differs')
    numbers=[p.GetNumber()for p in fp.Pads()]
    source_numbers=[p['num']for p in symbol['pins']]
    need(numbers and len(numbers)==len(set(numbers))and sorted(numbers)==sorted(source_numbers)
        and len(source_numbers)==len(set(source_numbers)),
        'complete_canonical_export_native_manufacturer_pin_population_required')
    need(all(p.GetNetname()and node_nets.get((ref,p.GetNumber()))==p.GetNetname()for p in fp.Pads()),
        'canonical_export_native_manufacturer_pin_nets_differ')
    geometry=_geometry(fp,rule);tick(deadline)
    return dict(reference=ref,footprint_uuid=force._uid(fp),source_symbol_uuid=symbol['uuid'],
        source_sheet=str(path),source_instance=list(instance),selected_mpn=native['MPN'],
        manufacturer=native['Manufacturer'],canonical_pattern=rule['library']+':'+rule['old'],
        actual_pattern=fp.GetFPIDAsString(),primary_drawing=rule['datasheet'],
        primary_drawing_sha256=rule['datasheet_sha256'],drawing=rule['drawing'],**geometry,
        canonical_source_converged=False,current_qualified=False,assembly_qualified=False,
        release_authority=False)


def assess(board,schematic,refs,*,timeout_s=9.1):
    """Fresh hierarchy/export and exact native geometry, no Source alias map."""
    report=dict(complete=False,ok=False,proofs={},errors={},release_authority=False,
        current_qualified=False,factory_qualified=False,canonical_source_converged=False)
    try:
        need(type(timeout_s)in(int,float)and math.isfinite(timeout_s)and 0<timeout_s<=9.1,
            'bounded_manufacturer_footprint_parity_required')
        deadline=time.monotonic()+timeout_s
        need(type(refs)in(list,tuple)and 1<=len(refs)<=32 and all(type(r)is str and r for r in refs)
            and len(set(refs))==len(refs),'finite_unique_actual_manufacturer_reference_scope_required')
        root=Path(schematic).resolve(strict=True)
        before=native_epoch(board,deadline=deadline);code=force._code_identity()
        assets=patterns.library_identity();catalog=stable(copy.deepcopy(patterns.CATALOG))
        files,hashes,instances=source._hierarchy(root,deadline)
        exported,exporter=source._export(root,deadline);comps,nets,node_nets=source._tables(exported)
        owners={r:[f for f in board.GetFootprints()if f.GetReference()==r]for r in refs}
        for ref in refs:
            tick(deadline)
            try:
                need(len(owners[ref])==1,'unique_native_manufacturer_owner_required')
                report['proofs'][ref]=_part(owners[ref][0],comps.get(ref),instances.get(ref,[]),node_nets,deadline)
            except (ValueError,RuntimeError,KeyError,TypeError,OSError)as exc:
                report['errors'][ref]=type(exc).__name__+':'+str(exc)
        report.update(native_binding=before,source_files=hashes,exporter=exporter,
            code_identity=code,manufacturer_asset_identities=assets,catalog_identity=catalog,
            deadline=deadline)
        need(still_current(report,board),'manufacturer_parity_source_code_library_or_native_epoch_changed')
        report['complete']=True;report['ok']=len(report['proofs'])==len(refs)
    except Exception as exc:
        report['error']=type(exc).__name__+':'+str(exc);report['proofs']={}
    return stable(report)


def still_current(report,board):
    """Recheck after the enclosing checker's final Source/jumper work too."""
    try:
        tick(report['deadline'])
        return (native_epoch(board,deadline=report['deadline'])==report['native_binding']
            and force._code_identity()==report['code_identity']
            and patterns.library_identity()==report['manufacturer_asset_identities']
            and stable(patterns.CATALOG)==report['catalog_identity']
            and all(force._hash(p)==sha for p,sha in report['source_files'].items())
            and force._hash(report['exporter']['exporter'])==report['exporter']['exporter_sha256'])
    except (ValueError,RuntimeError,KeyError,TypeError,OSError):return False
