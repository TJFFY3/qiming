import json, subprocess, sys, tempfile, unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class CLITests(unittest.TestCase):
    def test_no_sources_blocks_final_generation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=subprocess.run([sys.executable,str(ROOT/'scripts/generate_materials.py'),'--input',str(ROOT/'examples/lesson.json'),'--output-dir',tmp],capture_output=True,text=True)
            self.assertEqual(p.returncode,2,p.stdout+p.stderr)
            self.assertFalse(list(Path(tmp).glob('*.docx')))
            report=json.loads((Path(tmp)/'generation_report.json').read_text())
            self.assertEqual(report['status'],'blocked_missing_sources')
    def test_unverified_fixture_generates_four_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=subprocess.run([sys.executable,str(ROOT/'scripts/generate_materials.py'),'--input',str(ROOT/'examples/lesson.json'),'--output-dir',tmp,'--allow-unverified'],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            report=json.loads((Path(tmp)/'generation_report.json').read_text())
            self.assertEqual(report['status'],'draft_missing_sources')
            self.assertEqual(len(report['files']),4)
            self.assertTrue(report['validation']['passed'],report['validation'])
            self.assertEqual(len(list(Path(tmp).glob('*.docx'))),3)
    def test_verified_source_records_still_require_visual_review(self):
        data=json.loads((ROOT/'examples/lesson.json').read_text())
        data['sources']=[{'id':category,'category':category,'title':'单元测试来源记录','locator':'测试文件位置','evidence':'测试数据，非正式资料','verified':True} for category in ('textbook','teacher_book','exercises','exam')]
        for group in ('choice','written','optional'):
            for question in data['paper'][group]:question['source_ids']=['exercises']
        with tempfile.TemporaryDirectory() as tmp:
            src=Path(tmp)/'input.json';src.write_text(json.dumps(data,ensure_ascii=False))
            out=Path(tmp)/'output'
            p=subprocess.run([sys.executable,str(ROOT/'scripts/generate_materials.py'),'--input',str(src),'--output-dir',str(out)],capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            report=json.loads((out/'generation_report.json').read_text())
            self.assertEqual(report['status'],'generated_pending_visual_review')
            self.assertEqual(len(report['files']),4)
            self.assertTrue(report['review_required'])
            self.assertFalse(any('待核验' in Path(x).name for x in report['files']))
    def test_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            args=[sys.executable,str(ROOT/'scripts/generate_materials.py'),'--input',str(ROOT/'examples/lesson.json'),'--output-dir',tmp,'--allow-unverified']
            a=subprocess.run(args,capture_output=True,text=True)
            self.assertEqual(a.returncode,0,a.stdout+a.stderr)
            b=subprocess.run(args,capture_output=True,text=True)
            self.assertEqual(b.returncode,2,b.stdout+b.stderr)
            self.assertIn('已存在',b.stdout+b.stderr)
if __name__=='__main__':unittest.main()
