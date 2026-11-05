"""Native-only provenance and laptop interaction regressions; no CAD writes."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import cec_suite_inspection as report
import cec_dashboard as dashboard


class InspectionTests(unittest.TestCase):
    def fixture(self,directory):
        directory=Path(directory);pcb=directory/'unchanged.kicad_pcb';pcb.write_text('immutable saved copper')
        native=directory/'native.json';native.write_text(json.dumps(dict(unconnected_items=[],violations=[dict(severity='warning',type='silk')],excluded_violations=[])))
        row=dict(board='synthetic',path=str(pcb),sha256=report.sha(pcb),result=str(native),result_sha256=report.sha(native),counts=dict(opens=0,errors=0,warnings=1,exclusions=0))
        receipt=directory/'receipt.json';receipt.write_text(json.dumps(dict(complete=True,boards=[row])))
        return pcb,native,receipt

    def test_exact_receipt_reports_warnings_without_hiding_them(self):
        with tempfile.TemporaryDirectory()as d:
            pcb,native,receipt=self.fixture(d)
            before=pcb.read_bytes();r=report.verify_receipt(receipt,report.sha(receipt))
            self.assertEqual(r['boards'][0]['counts']['warnings'],1);self.assertEqual(pcb.read_bytes(),before)

    def test_changed_board_refuses_stale_native_success(self):
        with tempfile.TemporaryDirectory()as d:
            pcb,native,receipt=self.fixture(d);identity=report.sha(receipt);pcb.write_text('different board')
            with self.assertRaisesRegex(ValueError,'board_identity'):report.verify_receipt(receipt,identity)

    def test_changed_native_report_refuses_reuse(self):
        with tempfile.TemporaryDirectory()as d:
            pcb,native,receipt=self.fixture(d);identity=report.sha(receipt);native.write_text('{}')
            with self.assertRaisesRegex(ValueError,'native_report_identity'):report.verify_receipt(receipt,identity)

    def test_inconsistent_count_is_rejected(self):
        with tempfile.TemporaryDirectory()as d:
            pcb,native,receipt=self.fixture(d);r=json.loads(receipt.read_text());r['boards'][0]['counts']['warnings']=0;receipt.write_text(json.dumps(r))
            with self.assertRaisesRegex(ValueError,'native_count'):report.verify_receipt(receipt,report.sha(receipt))

    def test_plot_command_never_refills_changes_scale_or_mirrors_geometry(self):
        cmd=report.plot_command('source.kicad_pcb','native.svg',['F.Cu','Edge.Cuts'])
        self.assertNotIn('--check-zones',cmd);self.assertNotIn('--mirror',cmd)
        self.assertEqual(cmd[cmd.index('--page-size-mode')+1],'1')
        self.assertEqual(cmd[cmd.index('--drill-shape-opt')+1],'2')

    def test_ignored_checks_remain_visible_and_distinct_from_exclusions(self):
        native=dict(kicad_version='10.0.5',date='2026-11-01T20:31:18',
            included_severities=['error','warning','exclusion'],
            ignored_checks=[dict(key='track_not_centered_on_via',description='Saved ignored check')])
        result=report.native_configuration(native)
        self.assertEqual(result['ignored_checks'],native['ignored_checks'])
        self.assertEqual(result['measured_at'],native['date'])
        self.assertIn('Configured ignored checks',(report.STATIC/'cec_suite_inspection.js').read_text())

    def test_viewer_refresh_rejects_changed_source_before_reusing_plots(self):
        with tempfile.TemporaryDirectory()as d:
            pcb,native,receipt=self.fixture(d)
            manifest=Path(d)/'manifest.json'
            manifest.write_text(json.dumps(dict(source_receipt=str(receipt),
                source_receipt_sha256=report.sha(receipt),boards=[],assets={})))
            identity=report.sha(manifest);pcb.write_text('changed native board')
            with self.assertRaisesRegex(ValueError,'board_identity'):
                report.refresh(d,identity)

    def test_svg_reframing_preserves_every_native_child(self):
        with tempfile.TemporaryDirectory()as d:
            p=Path(d)/'native.svg';p.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 297 210"><g><path d="M22 31 L100 31"/><circle cx="24" cy="34" r="0.2"/></g></svg>')
            freeze=lambda n:(n.tag,dict(n.attrib),n.text,tuple(freeze(c)for c in n))
            before=freeze(ET.parse(p).getroot()[0]);report.reframe_svg(p,[20,29,82,94])
            self.assertEqual(freeze(ET.parse(p).getroot()[0]),before)
            self.assertEqual(ET.parse(p).getroot().get('viewBox'),'20.000000 29.000000 82.000000 94.000000')

    def test_asset_server_whitelist_and_exact_hash(self):
        with tempfile.TemporaryDirectory()as d:
            base=Path(d)/'bundle';base.mkdir();asset=base/'native.svg';asset.write_text('<svg/>')
            manifest=base/'manifest.json';manifest.write_text(json.dumps(dict(assets={'native.svg':report.sha(asset)})))
            index=Path(d)/'index.json';index.write_text(json.dumps(dict(directory=str(base),manifest_sha256=report.sha(manifest))))
            self.assertEqual(report.response('/inspection/native.svg',index=index)[0],b'<svg/>')
            self.assertIsNone(report.response('/inspection/%2e%2e/secret',index=index))
            asset.write_text('changed')
            with self.assertRaisesRegex(ValueError,'asset_identity'):report.response('/inspection/native.svg',index=index)

    def test_review_mode_disables_heavy_archive_startup(self):
        import inspect
        source=inspect.getsource(dashboard.main)
        self.assertLess(source.index('if a.inspection_only:'),source.index('os.makedirs(ARCHIVE_ROOT'))
        self.assertIn('review-only server; analysis endpoints disabled',inspect.getsource(dashboard.H.do_GET))

    def test_dashboard_scaling_does_not_recreate_image_elements(self):
        begin=dashboard.PAGE.index('function rerender()');end=dashboard.PAGE.index('\nfunction fit()',begin)
        self.assertNotIn('buildPanels',dashboard.PAGE[begin:end]);self.assertNotIn('pickAct',dashboard.PAGE[begin:end])
        self.assertIn('CECViewport.wheel',dashboard.PAGE);self.assertIn('pointercancel',dashboard.PAGE)

    def test_all_literal_inspector_control_ids_exist(self):
        import re
        html=(report.STATIC/'cec_suite_inspection.html').read_text();js=(report.STATIC/'cec_suite_inspection.js').read_text()
        ids=set(re.findall(r'id="([\w-]+)"',html));queries=set(re.findall(r"\$\('([\w-]+)'\)",js))
        self.assertFalse(queries-ids,queries-ids)

    @unittest.skipUnless(shutil.which('node'),'Node is required for viewer provenance simulation')
    def test_board_measurement_uses_its_own_report_not_suite_date_range(self):
        source=report.STATIC/'cec_suite_inspection.js'
        js='''const assert=require('assert'),fs=require('fs'),vm=require('vm');
const source=fs.readFileSync(process.argv[1],'utf8');
const helper=source.match(/function nativeMeasured\\(board\\)\\{[^\\n]*\\}/)[0];
const context={data:{native_verification_date:'2026-11-01, 2026-11-04'}};
vm.createContext(context);vm.runInContext(helper,context);
assert.strictEqual(context.nativeMeasured({native_verification:{measured_at:'2026-11-01T20:31:18'}}),'2026-11-01T20:31:18');
assert.strictEqual(context.nativeMeasured({native_verification:{measured_at:'2026-11-04T15:40:00'}}),'2026-11-04T15:40:00');
assert.strictEqual(context.nativeMeasured({}),'Not recorded');
assert(source.includes('esc(nativeMeasured(board))'));
assert(source.includes('esc(nativeMeasured(b))'));
assert(!source.includes('esc(data.native_verification_date)'));
console.log('Mixed-date suite preserves exact per-board native timestamps');'''
        subprocess.run(['node','-e',js,str(source)],check=True,capture_output=True,timeout=5)

    @unittest.skipUnless(shutil.which('node'),'Node is required for input simulation')
    def test_precision_trackpad_pan_pinch_and_anchor(self):
        source=str(report.STATIC/'cec_viewport.js')
        js='''const assert=require('assert'),v=require(process.argv[1]);
const pan=v.wheel({deltaX:.25,deltaY:1.5,deltaMode:0},800,400,false);
assert.deepStrictEqual(pan,{zoom:false,dx:.25,dy:1.5,factor:1});
assert.strictEqual(v.wheel({deltaY:1,deltaMode:1},800,400,false).dy,16);
assert.strictEqual(v.wheel({deltaY:1,deltaMode:2},800,400,false).dy,400);
const pinch=v.wheel({ctrlKey:true,deltaY:-.5},800,400,false);assert(pinch.zoom&&pinch.factor>1&&pinch.factor<1.01);
assert(v.wheel({deltaY:1},800,400,true).zoom);
const before={x:10,y:20,w:80,h:40},point={x:30,y:30};
const after=v.zoomBox(before,2,point,{min:1,max:1000});
assert.strictEqual((point.x-after.x)/after.w,(point.x-before.x)/before.w);
assert.strictEqual((point.y-after.y)/after.h,(point.y-before.y)/before.h);
assert.strictEqual(v.zoomBox(before,1e9,point,{min:1,max:1000}).w,1);
console.log('trackpad pan / fractional pinch / world anchor / zoom bounds pass');'''
        subprocess.run(['node','-e',js,source],check=True,capture_output=True,timeout=5)


if __name__=='__main__':unittest.main()
