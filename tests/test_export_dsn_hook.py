import ast,hashlib,importlib.util,io,json,sys,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
import cec_rated_dsn_overlay as m

def patched_production_text():
    return '', (Path(__file__).parents[1]/'scripts/cec_fr.py').read_text()


class ExportHook(unittest.TestCase):
    def test_actual_production_AST_prior_body_unchanged_except_exact_guard_dedupe(self):
        _,after=patched_production_text()
        fn=next(n for n in ast.parse(after).body if isinstance(n,ast.FunctionDef) and n.name=='export_dsn')
        self.assertEqual(fn.args.kwonlyargs[-1].arg,'rated_current_context')
        self.assertIsNone(fn.args.kw_defaults[-1].value)
        branches=[n for n in fn.body if isinstance(n,ast.If) and 'rated_current_context' in ast.unparse(n.test)]
        self.assertEqual(len(branches),2)
        body=[n for n in fn.body if n not in branches]
        first=next(i for i,n in enumerate(body) if isinstance(n,ast.Import)
            and any(alias.name=='cec_dsn_exact_guard_dedupe' for alias in n.names))
        expected=ast.parse('''import cec_dsn_exact_guard_dedupe
_guard_dedupe = cec_dsn_exact_guard_dedupe.deduplicate_file(dsn_path)
with open(dsn_path + ".guard-dedup.json", "w", encoding="utf-8") as _guard_log:
    json.dump(_guard_dedupe, _guard_log, sort_keys=True)
_validate_dsn_after(dsn_path, "exact duplicate guard removal")
''').body
        self.assertEqual(ast.dump(ast.Module(body=body[first:first+4],type_ignores=[])),
            ast.dump(ast.Module(body=expected,type_ignores=[])))
        body=body[:first]+body[first+4:]
        self.assertEqual(hashlib.sha256(ast.dump(ast.Module(body=body,type_ignores=[])).encode()).hexdigest(),
            '870a2030b241d66adf0ad883b65706e8b0169a16ee0d6dbf513d658b96645d4c')

    def test_actual_AST_default_empty_context_no_adapter_or_report(self):
        _,after=patched_production_text()
        function=next(n for n in ast.parse(after).body if isinstance(n,ast.FunctionDef) and n.name=='export_dsn')
        code=compile(ast.Module(body=[function.body[-2]],type_ignores=[]),'<actual-production-export-hook>','exec')
        calls=[]
        fake=types.SimpleNamespace(apply_export_overlay=lambda *a:calls.append(a) or {'report_path':'proof'})
        for context in (None,{}):
            env=dict(rated_current_context=context,board_path='board',dsn_path='native.dsn',
                _validate_dsn_after=lambda *a:calls.append(('validated',a)),sys=types.SimpleNamespace(stderr=io.StringIO()))
            with patch.dict(sys.modules,{'cec_rated_dsn_overlay':fake}):exec(code,env)
            self.assertEqual(calls,[])
        env['rated_current_context']={'explicit':'source'}
        with patch.dict(sys.modules,{'cec_rated_dsn_overlay':fake}):exec(code,env)
        self.assertEqual(calls[0],('board','native.dsn',{'explicit':'source'}))
        self.assertEqual(calls[1][0],'validated')

    def test_hook_fail_closed_for_noncontext_or_caller_capability_claim(self):
        _,after=patched_production_text()
        f=next(n for n in ast.parse(after).body if isinstance(n,ast.FunctionDef) and n.name=='export_dsn')
        code=compile(ast.Module(body=[f.body[-2]],type_ignores=[]),'<actual-hook>','exec')
        for context in (False,[],{'receiver_ok':True,'proof_sha':'fake'}):
            env=dict(rated_current_context=context,board_path='board',dsn_path='absent.dsn',sys=sys)
            with patch.dict(sys.modules,{'cec_rated_dsn_overlay':m}),self.assertRaises(ValueError):exec(code,env)

    def test_context_exact_named_source_epoch_and_scope(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.kicad_pcb';source.write_bytes(b'(board)')
            context=dict(source=str(source),expected_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),board_hint='named',requested_nets=['/VBUS'])
            self.assertEqual(m.validate_export_context(context)['requested_nets'],['/VBUS'])
            for change in ({'extra':True},{'requested_nets':['/VBUS','/VBUS']},{'expected_source_sha256':'0'*64}):
                with self.assertRaises(ValueError):m.validate_export_context(dict(context,**change))

    def test_adapter_fresh_DSN_hash_and_report_not_PCB_companion(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'board.kicad_pcb';source.write_bytes(b'(board)')
            dsn=Path(d)/'fresh.dsn';dsn.write_bytes(b'native-export')
            context=dict(source=str(source),expected_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),board_hint='named',requested_nets=['/VBUS'])
            def overlay(source_arg,dsn_arg,**kwargs):
                self.assertEqual(kwargs['expected_dsn_sha256'],hashlib.sha256(b'native-export').hexdigest())
                self.assertEqual(source_arg,str(source));self.assertEqual(kwargs['requested_nets'],['/VBUS'])
                return 'rated-export',{'release_authority':False}
            with patch.object(m,'overlay_for_source',side_effect=overlay):r=m.apply_export_overlay(Path(d)/'hinted.kicad_pcb',dsn,context)
            self.assertEqual(dsn.read_bytes(),b'rated-export')
            report=Path(r['report_path'])
            self.assertEqual(report.parent.name,'rated-current-export-reports')
            self.assertFalse(report.parent.name.startswith(source.stem+'.'))
            self.assertFalse(json.loads(report.read_text())['release_authority'])

    def test_actual_export_AST_preflight_before_native_export_preserves_family(self):
        _,after=patched_production_text()
        function=next(n for n in ast.parse(after).body if isinstance(n,ast.FunctionDef) and n.name=='export_dsn')
        text=ast.unparse(function)
        self.assertLess(text.index('preflight_export_context('),text.index('pcbnew.ExportSpecctraDSN('))
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'board.kicad_pcb';source.write_bytes(b'original board')
            pro=root/'board.kicad_pro';pro.write_bytes(b'original project')
            dru=root/'board.kicad_dru';dru.write_bytes(b'original rules')
            context=dict(source=str(source),expected_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),board_hint='named',requested_nets=[])
            native=types.SimpleNamespace(ExportSpecctraDSN=unittest.mock.Mock())
            env=dict(pcbnew=native,os=__import__('os'),sys=sys)
            exec(compile(ast.Module(body=[function],type_ignores=[]),'<actual-export-DSN>', 'exec'),env)
            original={p:p.read_bytes() for p in (source,pro,dru)}
            for name in ('board.dsn','board.rated.dsn','board.kicad_pcb','board.kicad_pro'):
                target=root/name
                with patch.dict(sys.modules,{'cec_rated_dsn_overlay':m}),self.assertRaises(ValueError):
                    env['export_dsn'](str(source),str(target),rated_current_context=context)
                self.assertEqual(original,{p:p.read_bytes() for p in original})
                if target not in original:self.assertFalse(target.exists())
            native.ExportSpecctraDSN.assert_not_called()

    def test_preflight_nested_prefix_and_symlink_hardlink_alias_refused(self):
        import os
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);authority=root/'authority';authority.mkdir();outside=root/'outside';outside.mkdir()
            source=authority/'board.kicad_pcb';source.write_bytes(b'board')
            pro=authority/'board.kicad_pro';pro.write_bytes(b'project')
            context=dict(source=str(source),expected_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),board_hint='named',requested_nets=[])
            sub=authority/'sub';sub.mkdir()
            with self.assertRaises(ValueError):m.preflight_export_context(source,sub/'board.rated.dsn',context)
            alias=outside/'alias.dsn';alias.symlink_to(pro)
            with self.assertRaises(ValueError):m.preflight_export_context(source,alias,context)
            alias.unlink();os.link(pro,alias)
            with self.assertRaises(ValueError):m.preflight_export_context(source,alias,context)
            self.assertEqual(pro.read_bytes(),b'project');self.assertEqual(source.read_bytes(),b'board')

    def test_disjoint_same_directory_nonprefix_and_adapter_recheck(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'hinted.kicad_pcb';source.write_bytes(b'board')
            context=dict(source=str(source),expected_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),board_hint='named',requested_nets=[])
            self.assertIsNotNone(m.preflight_export_context(source,root/'board.dsn',context))
            bad=root/'hinted.rated.dsn';bad.write_bytes(b'keep')
            with self.assertRaises(ValueError):m.apply_export_overlay(source,bad,context)
            self.assertEqual(bad.read_bytes(),b'keep')

if __name__=='__main__':unittest.main()
