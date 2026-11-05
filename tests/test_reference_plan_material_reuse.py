"""Fresh native constructor material reuse; never cache a receiving verdict."""
import copy,json,uuid
from pathlib import Path
import pcbnew,pytest
import cec_dense_reference_mapping as op
import cec_mask_search_reference_mapping as masked
import cec_field_coupling as field
import cec_force_current as force
from test_dense_reference_mapping import fixture

HINT='synthetic_reference_material_reuse'

def proposal(source,grade,owner=op):
    return owner.plan(source,grade=grade,board_hint=HINT,maximum_components=1,
        reverse_ownership='rigid_root_group_per_component')

def kwargs(q):
    keys=('reverse_ownership','via_ink_policy','owner_uuid_scope','reviewed_courtyard_contract_ids',
        'peripheral_reverse_seats','interrupt_projected_body_guides','opposite_face_chart',
        'project_native_fab_body','positive_leaders_only','grade','board_hint','maximum_components','seed_index')
    return {k:q[k]for k in keys if k in q}

def legacy_projected_constructor(source,q,owner):
    """TEST ONLY old independent-load materializer, with fresh public plan.

    This fixture deliberately exercises only projected rigid-root maps. It
    supplies neither a production callback nor a cached success/proof.
    """
    assert owner.plan(source,**kwargs(q))==q
    assert q['mode']=='opposite_face_projected_courtyard'
    b=pcbnew.LoadBoard(str(source));source_ids=set(owner.additive._nodes(source)[1]);generated=set()
    locks={force._uid(fp):fp.IsLocked()for fp in b.GetFootprints()}
    token=q['binding']['source_sha256']+':'+str(q['seed_index']);added=[];roots=[];groups=[]
    def ident(kind,index):
        value=str(uuid.uuid5(uuid.NAMESPACE_URL,token+':'+kind+':'+str(index)))
        assert value not in source_ids and value not in generated;generated.add(value)
        return pcbnew.KIID(value)
    for n,row in enumerate(q['records']):
        fp=next(fp for fp in b.GetFootprints()if force._uid(fp)==row['footprint_uuid'])
        fp.Reference().SetVisible(False)
        g=pcbnew.PCB_GROUP(b);g.SetName(owner.GROUP+':'+row['reference'])
        g.m_Uuid.Clone(ident('reverse-group',n));b.Add(g);g.AddItem(fp);groups.append(force._uid(g))
        for k,item in enumerate(owner.record_items(b,row,q['target_layer_id'],q['binding']['factory_legend'])):
            item.m_Uuid.Clone(ident('record-'+str(n),k));item.SetLocked(True);b.Add(item);g.AddItem(item)
            added.append(force._uid(item));roots.append(force._uid(item))
        g.SetLocked(True)
    for fp in b.GetFootprints():fp.SetLocked(locks[force._uid(fp)])
    return b,dict(added_annotation_uuids=sorted(added),added_group_uuid=None,
        added_root_annotation_uuids=sorted(roots),added_reverse_group_uuids=groups,
        reverse_annotations_are_native_footprint_children=False,
        reverse_annotations_and_owner_rigid_root_group=bool(groups),
        front_map_and_members_form_one_rigid_native_group=False,
        modified_footprint_uuids=sorted(r['footprint_uuid']for r in q['records']))

@pytest.mark.parametrize('back',[False,True])
@pytest.mark.parametrize('quarter',range(4))
def test_constructor_one_fresh_source_load_parse_and_exact_legacy_native_result(tmp_path,monkeypatch,back,quarter):
    source,grade,_=fixture(tmp_path,back=back,quarter=quarter);q=proposal(source,grade)
    old,manifest=legacy_projected_constructor(source,q,op)
    baseline=tmp_path/'baseline.kicad_pcb';field._save_field_snapshot(old,baseline)
    original_load=pcbnew.LoadBoard;original_nodes=op.additive._nodes;loads=[];parses=[]
    def load(path,*a,**k):
        if Path(path).resolve()==source.resolve():loads.append(str(path))
        return original_load(path,*a,**k)
    def nodes(path,*a,**k):
        if Path(path).resolve()==source.resolve():parses.append(str(path))
        return original_nodes(path,*a,**k)
    with monkeypatch.context()as m:
        m.setattr(pcbnew,'LoadBoard',load);m.setattr(op.additive,'_nodes',nodes)
        b,actual=op.construct(source,copy.deepcopy(q))
    assert len(loads)==1 and len(parses)==1,(loads,parses)
    assert actual==manifest and proposal(source,grade)==q
    saved=tmp_path/'reused.kicad_pcb';field._save_field_snapshot(b,saved)
    assert op.syntax._freeze(op._root_annotation_order(original_nodes(saved)[0]))==op.syntax._freeze(op._root_annotation_order(original_nodes(baseline)[0]))
    import cec_source_retaining_ses_import as raw
    assert op._reference_literal(raw.raw_text(source),raw.raw_text(saved),q,actual)==op._reference_literal(raw.raw_text(source),raw.raw_text(baseline),q,manifest)
    child=force._copy_family(source,tmp_path/'child');op.write_private(source,child,q)
    proof=op.receive(source,child,q)
    assert proof['ok']and proof['complete']and proof['whole_saved_second_native_roundtrip_stable'],proof

@pytest.mark.parametrize('fault',['source','grade','rules','opaque'])
def test_changed_inputs_never_adopt_previous_plan_material(tmp_path,fault):
    source,grade,_=fixture(tmp_path);q=proposal(source,grade)
    if fault=='source':
        b=pcbnew.LoadBoard(str(source));next(iter(b.GetFootprints())).SetValue('changed');field._save_field_snapshot(b,source)
    elif fault=='grade':
        data=json.loads(grade.read_text());data['boards']['candidate']['native_producer']['report_sha256']='0'*64;force._write(grade,data)
    elif fault=='rules':source.with_suffix('.kicad_dru').write_text('(version 1)\n')
    else:source.write_text(source.read_text()+'\n; opaque retained Source evidence changed\n')
    with pytest.raises((ValueError,RuntimeError)):op.construct(source,q)
    assert op._CONSTRUCT_PLAN_MATERIAL.get()is None

@pytest.mark.parametrize('fault',['pad','copper','opaque_native'])
def test_actual_plan_board_mutation_before_reuse_refuses(tmp_path,monkeypatch,fault):
    source,grade,_=fixture(tmp_path);q=proposal(source,grade);real=op.plan
    def mutated(*a,**k):
        fresh=real(*a,**k);capture=op._CONSTRUCT_PLAN_MATERIAL.get();b=capture.board
        if fault=='pad':next(iter(next(iter(b.GetFootprints())).Pads())).Move(pcbnew.VECTOR2I(1,0))
        elif fault=='copper':
            t=pcbnew.PCB_TRACK(b);t.SetStart(pcbnew.VECTOR2I_MM(18,18));t.SetEnd(pcbnew.VECTOR2I_MM(19,18));t.SetWidth(200000);t.SetLayer(pcbnew.F_Cu);b.Add(t)
        else:
            props=b.GetProperties();props['UNRELATED_NATIVE_METADATA']='changed';b.SetProperties(props)
        return fresh
    monkeypatch.setattr(op,'plan',mutated)
    with pytest.raises(ValueError):op.construct(source,q)
    assert op._CONSTRUCT_PLAN_MATERIAL.get()is None

def test_masked_plan_wrapper_still_bound_and_receivers_get_fresh_contexts(tmp_path,monkeypatch):
    source,grade,_=fixture(tmp_path);q=proposal(source,grade,masked);owner=masked._private
    contexts=[];real=owner.plan
    def plan(*a,**k):
        contexts.append(owner._CONSTRUCT_PLAN_MATERIAL.get());return real(*a,**k)
    monkeypatch.setattr(owner,'plan',plan)
    b,m=masked.construct(source,q);child=force._copy_family(source,tmp_path/'masked')
    masked.write_private(source,child,q)
    proof=masked.receive(source,child,q)
    assert proof['ok']and proof['complete']and proof['actual_native_mask_artwork_in_search_and_replayed'],proof
    assert 'mask_search_binding'in q and len(contexts)==3 and all(c is not None for c in contexts)
    assert len({id(c)for c in contexts})==3 and owner._CONSTRUCT_PLAN_MATERIAL.get()is None
    bad=copy.deepcopy(q);bad['mask_search_binding']['policy']='forged'
    with pytest.raises(ValueError):masked.construct(source,bad)
    assert owner._CONSTRUCT_PLAN_MATERIAL.get()is None

def test_context_exception_restores_preexisting_scope(tmp_path,monkeypatch):
    source,grade,_=fixture(tmp_path);q=proposal(source,grade);outer=object()
    token=op._CONSTRUCT_PLAN_MATERIAL.set(outer)
    def failed(*a,**k):raise RuntimeError('synthetic fresh planner exception')
    monkeypatch.setattr(op,'plan',failed)
    try:
        with pytest.raises(RuntimeError):op.construct(source,q)
        assert op._CONSTRUCT_PLAN_MATERIAL.get()is outer
    finally:op._CONSTRUCT_PLAN_MATERIAL.reset(token)

def test_nested_construct_scopes_do_not_alias_or_leak(tmp_path,monkeypatch):
    a=tmp_path/'a';a.mkdir();b=tmp_path/'b';b.mkdir()
    source,grade,_=fixture(a);other,other_grade,_=fixture(b)
    q=proposal(source,grade);other_q=proposal(other,other_grade);real=op.plan;active=[False];seen=[]
    def plan(*args,**kw):
        current=op._CONSTRUCT_PLAN_MATERIAL.get();seen.append(current)
        if not active[0]:
            active[0]=True
            try:op.construct(other,other_q)
            finally:active[0]=False
            assert op._CONSTRUCT_PLAN_MATERIAL.get()is current
        return real(*args,**kw)
    monkeypatch.setattr(op,'plan',plan);op.construct(source,q)
    assert len(seen)==2 and seen[0]is not seen[1]and op._CONSTRUCT_PLAN_MATERIAL.get()is None

@pytest.mark.parametrize('declared',['jlcpcb_6l_pofv_signal','jlcpcb_6l_pofv_high_current'])
def test_floors_use_same_declared_stackup_authority_without_another_load(tmp_path,monkeypatch,declared):
    source,grade,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    props=b.GetProperties();props['CEC_FAB_PROFILE']=declared;b.SetProperties(props);field._save_field_snapshot(b,source)
    b=pcbnew.LoadBoard(str(source));monkeypatch.setenv('CEC_FAB_PROFILE','jlcpcb_6l_pofv_high_current')
    rules=op.fab.profile_rules(op.fab.PROFILES['jlcpcb'],op.fab.board_outer_copper_oz(source),declared)
    settings=b.GetDesignSettings()
    expected=dict(height=max(rules['silk_height'],settings.m_MinSilkTextHeight/1e6),
        stroke=max(rules['silk'],settings.m_MinSilkTextThickness/1e6),
        clearance=max(rules['silk_clearance'],settings.m_SilkClearance/1e6),
        edge=max(rules['edge'],rules['silk_clearance']),profile=declared)
    def forbidden(*a,**k):pytest.fail('same fresh Source board unnecessarily reloaded')
    monkeypatch.setattr(pcbnew,'LoadBoard',forbidden)
    assert op.floors(b,source)==expected

def test_unknown_declared_profile_does_not_inherit_environment_authority(tmp_path,monkeypatch):
    source,grade,_=fixture(tmp_path);b=pcbnew.LoadBoard(str(source))
    props=b.GetProperties();props['CEC_FAB_PROFILE']='unknown';b.SetProperties(props)
    monkeypatch.setenv('CEC_FAB_PROFILE','jlcpcb_6l_pofv_signal')
    with pytest.raises(ValueError,match='declared_source_factory_profile_required'):op.floors(b,source)
