import importlib.util
from pathlib import Path
import tempfile
import types
import sys
import unittest
import ast
import os
import subprocess
import textwrap
from contextlib import nullcontext
from unittest.mock import patch

import cec_source_retaining_ses_import as m


class SourceRetention(unittest.TestCase):
    def test_cleanup_refusal_retains_both_independent_failure_stacks(self):
        replay={'ok': True, 'complete': True, 'errors': []}
        current={'ok': False, 'complete': True,
                 'new_faults': [['domain_trace', 'unsafe-force-net', 'exact-new-id', 'B.Cu']]}
        report={}
        with self.assertRaisesRegex(ValueError,'pre_cleanup_source_or_current_replay_refused'):
            m.require_cleanup_receiving(report,replay,current)
        self.assertEqual(report['dangling_cleanup_prechecks'],[
            {'source_delta': replay, 'current': current}])

    def test_cleanup_prechecks_require_explicit_complete_positive_receipts(self):
        report={};positive={'ok': True, 'complete': True}
        m.require_cleanup_receiving(report,positive,positive)
        for receipt in ({'ok': True}, {'complete': True}, {}):
            with self.assertRaises(ValueError):
                m.require_cleanup_receiving(report,receipt,positive)
        self.assertEqual(len(report['dangling_cleanup_prechecks']),4)

    def test_exact_introduced_dangling_only_not_inherited(self):
        fault=lambda uid:{'type':'track_dangling','severity':'warning','items':[{'uuid':uid}]}
        old={'violations':[fault('old')]};new={'violations':[fault('old'),fault('new')]}
        self.assertEqual(m.introduced_dangling_ids(old,new,{'old'},{'new':'(segment (uuid new))'}),{'new'})
        with self.assertRaises(ValueError):m.introduced_dangling_ids({'violations':[]},{'violations':[fault('old')]},{'old'},{'old':'(segment (uuid old))'})

    def test_dangling_budget_unknown_node_and_ambiguous_diagnostics(self):
        f=lambda ids:{'type':'track_dangling','severity':'warning','items':[{'uuid':u} for u in ids]}
        for after,nodes,retired in (([f(['n'])],{'n':'(via (uuid n))'},()),
                                   ([f(['n','m'])],{'n':'(segment)','m':'(segment)'},()),
                                   ([f(['n'])],{'n':'(segment)'},[str(i) for i in range(16)])):
            with self.assertRaises(ValueError):m.introduced_dangling_ids({'violations':[]},{'violations':after},set(),nodes,retired)

    def test_replay_retains_original_opaque_fields_not_new_defaults(self):
        stencil='(kicad_pcb (footprint (uuid fp) (property Datasheet "") (opaque x)) (zone (uuid g) (setting x) (filled_polygon old)) (segment (uuid n) (width .2)))'
        native='(kicad_pcb (footprint (uuid fp) (opaque normalized)) (zone (uuid g) (setting normalized) (filled_polygon fresh)) (segment (uuid n) (width .3)))'
        expected=m.retain_replay_source_nodes(stencil,native,{'fp','g'},{'g'})
        self.assertIn('(property Datasheet "") (opaque x)',expected)
        self.assertIn('(setting x)',expected);self.assertIn('(filled_polygon fresh)',expected)
        self.assertIn('(segment (uuid n) (width .3))',expected)
        self.assertNotIn('(width .2)',expected)

    def test_refusal_retains_bounded_unadmitted_family_and_json(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            proof=Path(d)/'proof';proof.mkdir();(proof/'candidate').mkdir()
            (proof/'candidate/board.kicad_pcb').write_text('(board)')
            (proof/'receiving.json').write_text('{"ok":false}')
            (proof/'worker.log').write_text('traceback')
            saved=m.preserve_refusal(proof,Path(d)/'diagnostics','native refusal')
            self.assertTrue((saved/'UNADMITTED-board-family/board.kicad_pcb').is_file())
            manifest=json.loads((saved/'UNADMITTED.json').read_text())
            self.assertFalse(manifest['ok']);self.assertFalse(manifest['admitted'])
            self.assertEqual(len(manifest['files']),3)
            limited=m.preserve_refusal(proof,Path(d)/'diagnostics','bounded',max_bytes=1)
            report=json.loads((limited/'UNADMITTED.json').read_text())
            self.assertEqual(report['retained_bytes'],0);self.assertEqual(len(report['omitted']),3)

    def test_callback_refusal_survives_temporary_cleanup_without_publishing(self):
        import json
        force=types.SimpleNamespace()
        def refusing(source,ses,output_dir,**kwargs):
            p=Path(output_dir);p.mkdir();(p/'candidate').mkdir()
            (p/'candidate/board.kicad_pcb').write_text('unadmitted candidate')
            (p/'receiving.json').write_text('{"ok":false,"error":"native geometry"}')
            (p/'worker.log').write_text('complete worker failure log')
            raise ValueError('native geometry')
        with tempfile.TemporaryDirectory() as d,patch.dict(sys.modules,{'cec_force_current':force}),patch.object(m,'import_retaining_source',side_effect=refusing):
            output=Path(d)/'board.kicad_pcb'
            with self.assertRaisesRegex(ValueError,'UNADMITTED'):
                m.route_once_operator('source','ses',output,board_hint='named',expected_source_sha256='0'*64)
            self.assertFalse(output.exists())
            self.assertFalse(any(Path(d).glob('cec-ses-retain-*')))
            saved=list((Path(d)/'source-retaining-diagnostics').iterdir())
            self.assertEqual(len(saved),1)
            self.assertTrue((saved[0]/'UNADMITTED-board-family/board.kicad_pcb').is_file())
            self.assertIn('native geometry',(saved[0]/'operator-error.json').read_text())
            self.assertFalse(json.loads((saved[0]/'UNADMITTED.json').read_text())['admitted'])

    def test_dangling_mode_explicit_boolean(self):
        with self.assertRaises(ValueError):m.import_retaining_source('x','y','never-created',
            board_hint='named',expected_source_sha256='0'*64,cleanup_dangling='false')
    def test_opaque_root_nodes_quotes_comments_and_original_copper(self):
        source='(kicad_pcb\n; (ignored)\n(unknown "a ) \\" b" (opaque x))\n(segment (uuid old) (width .7))\n)\n'
        raw='(kicad_pcb (segment (uuid old) (width .01)) (via (uuid new)))'
        result=m.assemble(source,raw)
        self.assertIn('(unknown "a ) \\" b" (opaque x))',result)
        self.assertIn('(segment (uuid old) (width .7))',result)
        self.assertIn('(via (uuid new))',result)
        self.assertIn('; (ignored)',result)

    def test_only_ground_cache_replaced_power_cache_exact(self):
        source='(kicad_pcb (zone (uuid g) (opaque preserve) (filled_polygon (pts old))) (zone (uuid p) (filled_polygon (pts power))))'
        raw='(kicad_pcb (segment (uuid n)))'
        filled='(kicad_pcb (zone (uuid g) (opaque LOST) (filled_polygon (pts fresh))))'
        result=m.assemble(source,raw,ground_text=filled,ground_ids=['g'])
        self.assertIn('(opaque preserve)',result)
        self.assertIn('(filled_polygon (pts fresh))',result)
        self.assertIn('(zone (uuid p) (filled_polygon (pts power)))',result)
        self.assertNotIn('LOST',result)

    def test_retirement_exact_new_only(self):
        source='(kicad_pcb (segment (uuid old)))'
        raw='(kicad_pcb (segment (uuid old)) (segment (uuid bad)) (via (uuid good)))'
        result=m.assemble(source,raw,['bad'])
        self.assertNotIn('(uuid bad)',result)
        self.assertIn('(uuid good)',result)
        for ids in (['old'],['absent']):
            with self.assertRaises(ValueError):m.assemble(source,raw,ids)

    def test_duplicate_uuid_refused(self):
        with self.assertRaisesRegex(ValueError,'ambiguous'):
            m.inventory('(kicad_pcb (via (uuid a)) (segment (uuid a)))')

    def test_unknown_new_primitive_refused(self):
        with self.assertRaisesRegex(ValueError,'unsupported'):
            m.assemble('(kicad_pcb)', '(kicad_pcb (footprint (uuid n)))')

    def test_malformed_refused(self):
        for raw in ('(kicad_pcb (x)', '(kicad_pcb "unterminated)', '(x))'):
            with self.assertRaises(ValueError):m.children(raw)

    def test_trailing_comment_parens_not_root_end(self):
        text='(kicad_pcb)\n; trailing ) comment\n'
        result=m.assemble(text,'(kicad_pcb (via (uuid n)))')
        self.assertEqual(len(m.children(result)),1)
        self.assertTrue(result.endswith('; trailing ) comment\n'))

    def test_raw_io_preserves_crlf(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'board'
            original=b'(kicad_pcb\r\n (opaque preserve)\r\n)\r\n'
            p.write_bytes(original)
            m.write_raw(p,m.raw_text(p))
            self.assertEqual(p.read_bytes(),original)

    def test_operator_source_alias_rejected(self):
        fake=types.SimpleNamespace()
        with patch.dict(sys.modules,{'cec_force_current':fake}):
            with self.assertRaisesRegex(ValueError,'source_output_alias'):
                m.route_once_operator('same','ses','same',board_hint='named',expected_source_sha256='bound')

    def test_rules_reset_before_canonical_order(self):
        calls=[]
        def bind(name):
            def run(board,path):
                p=Path(path).with_suffix('.kicad_dru')
                calls.append(name);p.write_text(p.read_text()+name)
            return run
        fake=types.SimpleNamespace(bind_local_via_rule=bind('Via'),bind_local_endpoint_rule=bind('Endpoint'))
        with tempfile.TemporaryDirectory() as d,patch.dict(sys.modules,{'cec_additive_route_receiving':fake}):
            source=Path(d)/'source.kicad_pcb';target=Path(d)/'target.kicad_pcb'
            source.with_suffix('.kicad_dru').write_text('SOURCE')
            target.with_suffix('.kicad_dru').write_text('SOURCEEndpointVia')
            m.canonical_rules(None,target,source)
            self.assertEqual(target.with_suffix('.kicad_dru').read_text(),'SOURCEViaEndpoint')
            self.assertEqual(calls,['Via','Endpoint'])

    def test_explicit_authority_and_native_lease(self):
        for kwargs in ({'board_hint':''},{'board_hint':'named','native_s':11},{'board_hint':'named','wall_s':301}):
            with self.assertRaises(ValueError):m.import_retaining_source('x','y','never-created',**kwargs)

    def test_whole_worker_timeout_kills_process_group(self):
        process=types.SimpleNamespace(pid=123,wait=unittest.mock.Mock(side_effect=[subprocess.TimeoutExpired('worker',.01),0]))
        with tempfile.TemporaryDirectory() as d,patch.object(m.subprocess,'Popen',return_value=process),patch.object(m.os,'killpg') as kill:
            with self.assertRaisesRegex(TimeoutError,'whole_lease_expired'):
                m.import_retaining_source('source','ses',Path(d)/'new',board_hint='named',wall_s=.01,expected_source_sha256='0'*64)
            kill.assert_called_once_with(123,m.signal.SIGKILL)

    def test_publication_source_eco_mutation_refused(self):
        force=types.SimpleNamespace(_family=lambda *a:{'source':'current'},_code_identity=lambda:'code',_thermal_hint=lambda k:nullcontext())
        synth=types.SimpleNamespace(Config=types.SimpleNamespace(load=lambda k:types.SimpleNamespace(params={})))
        native=types.SimpleNamespace(_describe_build=lambda p:'tool')
        with patch.dict(sys.modules,{'cec_force_current':force,'cec_synth_pipeline':synth,'cec_native_drc_runner':native}):
            with self.assertRaisesRegex(ValueError,'live_epoch_changed'):
                m.assert_receipt_live({'epoch':{'family':{'source':'old'}}},'source','ses','named')

    def test_parent_epoch_uses_same_json_tuple_normalization_as_worker(self):
        import json
        config=types.SimpleNamespace(params={'layers':('F.Cu','B.Cu'),'anchors':{'J1':(1.,2.,90)}})
        force=types.SimpleNamespace(_family=lambda *a:{'source':'same'},_code_identity=lambda:'code',_thermal_hint=lambda k:nullcontext())
        synth=types.SimpleNamespace(Config=types.SimpleNamespace(load=lambda k:config))
        native=types.SimpleNamespace(_describe_build=lambda p:'tool')
        receipt={'epoch':dict(family={'source':'same'},code='code',helper=m.digest(m.__file__),
            ses=None,inputs={},params=json.loads(json.dumps(config.params)),
            assembly_instance=None,assembly_identity=None,native_tool='tool')}
        with patch.dict(sys.modules,{'cec_force_current':force,'cec_synth_pipeline':synth,'cec_native_drc_runner':native}):
            m.assert_receipt_live(receipt,'source','no-such-ses','named')
            config.params['anchors']['J1']=(1.,2.001,90)
            with self.assertRaisesRegex(ValueError,'live_epoch_changed'):
                m.assert_receipt_live(receipt,'source','no-such-ses','named')

    def test_outer_intake_failure_never_hidden_by_inner_pass(self):
        for value in ({'ok':False,'intake':{'ok':True}}, {'ok':True,'intake':{'ok':False}}, {'intake':{'ok':True}}):
            with self.assertRaises(ValueError):m.require_intake(value)
        m.require_intake({'ok':True,'intake':{'ok':True}})

    def test_raw_hidden_usb_and_same_uuid_changed_geometry(self):
        row={'type':'track_width','severity':'error','description':'USB width .3998',
             'items':[{'uuid':'same','pos':{'x':1,'y':2}}]}
        source={'violations':[row]}
        self.assertTrue(m.raw_error_delta(source,source)['ok'])
        changed=dict(row,description='USB width .2000')
        self.assertFalse(m.raw_error_delta(source,{'violations':[changed]})['ok'])
        self.assertFalse(m.raw_error_delta({'violations':[]},source)['ok'])

    def test_scripts_directory_staged_and_installed_layout(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);scripts=root/'scripts';scripts.mkdir()
            for name in ('cec_fr.py','cec_force_current.py'):(scripts/name).touch()
            self.assertEqual(m.scripts_directory(scripts/'new.py'),scripts)
            self.assertEqual(m.scripts_directory(root/'build/stage/new.py'),scripts)

    def transaction_fixture(self,d):
        root=Path(d);private=root/'private';private.mkdir()
        source=private/'board.kicad_pcb';source.write_text('board')
        sidecar=private/'board.kicad_pro';sidecar.write_text('project')
        proof=private/'proof';proof.mkdir();(proof/'receiving.json').write_text('{}')
        output=root/'out.kicad_pcb'
        return root,source,sidecar,proof,output

    def test_publication_collision_does_not_touch_existing(self):
        with tempfile.TemporaryDirectory() as d:
            root,src,side,proof,out=self.transaction_fixture(d)
            finalproof=root/'source-retaining-proof-out';finalproof.mkdir()
            (finalproof/'owned-by-user').write_text('keep')
            with self.assertRaises(ValueError):m.publish_transaction({},src,out,[(side,out.with_suffix('.kicad_pro'))],proof,root/'stage',lambda:None)
            self.assertFalse(out.exists());self.assertFalse(out.with_suffix('.kicad_pro').exists())
            self.assertEqual((finalproof/'owned-by-user').read_text(),'keep')

    def test_unfamiliar_existing_output_companion_refused_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            root,src,side,proof,out=self.transaction_fixture(d)
            unfamiliar=root/'out.opaque-authority';unfamiliar.write_text('keep')
            with self.assertRaises(ValueError):m.publish_transaction({},src,out,[(side,out.with_suffix('.kicad_pro'))],proof,root/'stage',lambda:None)
            self.assertFalse(out.exists());self.assertEqual(unfamiliar.read_text(),'keep')

    def test_publication_second_copy_failure_leaves_no_board(self):
        import shutil
        original=shutil.copy2;calls=[]
        def copying(src,dst,*a,**k):
            calls.append(src)
            if len(calls)==2:raise OSError('second copy')
            return original(src,dst,*a,**k)
        with tempfile.TemporaryDirectory() as d,patch.object(shutil,'copy2',side_effect=copying):
            root,src,side,proof,out=self.transaction_fixture(d)
            with self.assertRaises(OSError):m.publish_transaction({},src,out,[(side,out.with_suffix('.kicad_pro'))],proof,root/'stage',lambda:None)
            self.assertFalse(out.exists());self.assertFalse(out.with_suffix('.kicad_pro').exists())

    def test_publication_proof_copy_failure_leaves_no_board(self):
        import shutil
        with tempfile.TemporaryDirectory() as d,patch.object(shutil,'copytree',side_effect=OSError('proof copy')):
            root,src,side,proof,out=self.transaction_fixture(d)
            with self.assertRaises(OSError):m.publish_transaction({},src,out,[(side,out.with_suffix('.kicad_pro'))],proof,root/'stage',lambda:None)
            self.assertFalse(out.exists());self.assertFalse(out.with_suffix('.kicad_pro').exists())

    def test_publication_late_eco_rolls_back_own_outputs(self):
        calls=[]
        def live():
            calls.append(1)
            if len(calls)==3:raise ValueError('late ECO')
        with tempfile.TemporaryDirectory() as d:
            root,src,side,proof,out=self.transaction_fixture(d)
            with self.assertRaises(ValueError):m.publish_transaction({},src,out,[(side,out.with_suffix('.kicad_pro'))],proof,root/'stage',live)
            self.assertFalse(out.exists());self.assertFalse(out.with_suffix('.kicad_pro').exists())
            self.assertFalse((root/'source-retaining-proof-out').exists())

    def test_publication_board_last_and_success(self):
        states=[]
        with tempfile.TemporaryDirectory() as d:
            root,src,side,proof,out=self.transaction_fixture(d)
            r=m.publish_transaction({},src,out,[(side,out.with_suffix('.kicad_pro'))],proof,root/'stage',lambda:states.append(out.exists()))
            self.assertEqual(states,[False,False,True])
            self.assertEqual(out.read_text(),'board');self.assertEqual(out.with_suffix('.kicad_pro').read_text(),'project')

    def test_published_family_inventory_ignores_external_proof_namespace(self):
        import cec_force_current as force
        with tempfile.TemporaryDirectory() as d:
            root,src,side,proof,out=self.transaction_fixture(d)
            def imported(source,ses,private,**kwargs):
                p=Path(private);p.mkdir();(p/'candidate').mkdir()
                board=p/'candidate/board.kicad_pcb';board.write_bytes(src.read_bytes())
                board.with_suffix('.kicad_pro').write_bytes(side.read_bytes())
                (p/'receiving.json').write_text('{"ok":true}')
                return {'ok':True,'candidate':str(board)}
            with patch.object(m,'import_retaining_source',side_effect=imported),patch.object(m,'assert_receipt_live'):
                receipt=m.route_once_operator(src,'ses',out,board_hint='named',expected_source_sha256='0'*64)
            companions,metadata=force._companion_inventory(out)
            self.assertEqual(companions['.kicad_pro'],out.with_suffix('.kicad_pro'))
            self.assertEqual(Path(receipt['proof_directory']),root/'source-retaining-proof-out')
            self.assertFalse(any(p.is_dir() for p in companions.values()))

    def test_publication_second_link_failure_rolls_back_sidecar(self):
        original=m.os.link;calls=[]
        def linking(src,dst):
            calls.append(dst)
            if len(calls)==2:raise OSError('second link')
            return original(src,dst)
        with tempfile.TemporaryDirectory() as d,patch.object(m.os,'link',side_effect=linking):
            root,src,side,proof,out=self.transaction_fixture(d)
            with self.assertRaises(OSError):m.publish_transaction({},src,out,[(side,out.with_suffix('.kicad_pro'))],proof,root/'stage',lambda:None)
            self.assertFalse(out.exists());self.assertFalse(out.with_suffix('.kicad_pro').exists())
            self.assertFalse((root/'source-retaining-proof-out').exists())

    def test_rollback_does_not_delete_externally_changed_own_sidecar(self):
        calls=[]
        with tempfile.TemporaryDirectory() as d:
            root,src,side,proof,out=self.transaction_fixture(d)
            def live():
                calls.append(1)
                if len(calls)==3:
                    out.with_suffix('.kicad_pro').write_text('external change')
                    raise ValueError('late refusal')
            with self.assertRaises(ValueError):m.publish_transaction({},src,out,[(side,out.with_suffix('.kicad_pro'))],proof,root/'stage',live)
            self.assertFalse(out.exists())
            self.assertEqual(out.with_suffix('.kicad_pro').read_text(),'external change')

    def test_assembly_context_serialized_to_worker_request(self):
        import json
        selected={'explicit':'assembly'}
        with tempfile.TemporaryDirectory() as d:
            out=Path(d)/'new'
            def launch(command,**kwargs):
                request=json.loads(Path(command[-1]).read_text())
                self.assertEqual(request['assembly_instance'],selected)
                (out/'receiving.json').write_text('{"ok":true}')
                return types.SimpleNamespace(wait=lambda **kwargs:0)
            with patch.object(m.subprocess,'Popen',side_effect=launch):
                m.import_retaining_source('source','ses',out,board_hint='named',
                    expected_source_sha256='0'*64,assembly_instance=selected)

    def test_real_assembly_authority_binds_peer_bytes(self):
        import json
        scripts=m.scripts_directory(__file__)
        spec=importlib.util.spec_from_file_location('real_assembly',scripts/'cec_assembly_instance.py')
        actual=importlib.util.module_from_spec(spec);spec.loader.exec_module(actual)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);files={name:root/name for name in ('carrier','cover','contract')}
            for name,p in files.items():p.write_text(name)
            record=lambda name:{'path':str(files[name]),'sha256':m.digest(files[name])}
            selected={'schema':1,'role':'carrier','contract':record('contract'),
                      'members':{name:record(name) for name in ('carrier','cover')}}
            with patch.dict(sys.modules,{'cec_assembly_instance':actual,'cec_full_pipeline':types.SimpleNamespace(ROOT=root)}):
                bound=m.assembly_identity(files['carrier'],selected)
                self.assertEqual(bound['hashes']['cover'],m.digest(files['cover']))
                files['cover'].write_text('changed peer')
                with self.assertRaises(ValueError):m.assembly_identity(files['carrier'],selected)

    def test_staged_route_hook_default_and_opt_in(self):
        tree=ast.parse((m.scripts_directory(__file__)/'cec_fr.py').read_text())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='route_once')
        branch=next(n for n in ast.walk(function) if isinstance(n,ast.If)
                    and isinstance(n.test,ast.Compare) and isinstance(n.test.left,ast.Name)
                    and n.test.left.id=='ses_import_operator')
        code=compile(ast.Module(body=[branch],type_ignores=[]),'<production-route-hook>','exec')
        calls=[]
        env=dict(ses_import_operator=None,import_ses=lambda *a,**k:calls.append((a,k)),
                 board_path='source',ses_path='session',out_path='target',power_pours=('ask',),
                 skip_locked_taps=True,_completed=('live-completed',),params={},
                 _IMPORT_REPORTS={os.path.abspath('target'):{'default':'unchanged'}},os=os)
        exec(code,env)
        self.assertEqual(calls,[(('source','session','target'),dict(power_pours=('ask',),skip_locked_taps=True,completed_nets=('live-completed',)))])
        self.assertEqual(env['params']['import_report'],{'default':'unchanged'})
        calls.clear()
        env['ses_import_operator']=lambda *args: calls.append(args) or {'ok':True,'completed_nets_grandfathered':[]}
        exec(code,env)
        self.assertEqual(calls,[('source','session','target')])
        env['ses_import_operator']=lambda *args:{'ok':False}
        with self.assertRaises(ValueError):exec(code,env)


if __name__=='__main__':unittest.main()
