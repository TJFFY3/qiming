import json,sys,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from render_outline import render_document
from outline_contract import OutlineValidationError
from docx import Document

def data():
 return {'outline':{'title':'格式测试课时','goals':['通过比较能够标出化合价。'],'sections':[{'title':'任务一','blocks':[{'type':'paragraph','content':'判断 [H2O]。'},{'type':'table','headers':['编号','判断'],'rows':[['①',None],['②',None]]}]}]},'sources':[{'id':'book','category':'textbook','title':'测试教材','locator':'测试位置','evidence':'测试摘录','verified':True}]}
class RenderTests(unittest.TestCase):
 def test_outline_only_no_exam_or_paper_required(self):
  with tempfile.TemporaryDirectory() as t:
   out=Path(t)/'v001';report=render_document(data(),out)
   self.assertFalse(report['draft']);self.assertTrue(report['validation']['passed'])
   self.assertEqual(len(list(out.glob('*.docx'))),1)
   self.assertEqual(len(Document(out/'outline.docx').tables),2)
   self.assertEqual(report['statistics']['content_tables'],1)
   self.assertEqual(report['statistics']['data_rows'],2)
   saved=json.loads((out/'content.json').read_text())
   self.assertTrue(saved['sections'][0]['blocks'][0]['id'])
   with self.assertRaises((ValueError,FileExistsError)):render_document(data(),out)
 def test_missing_sources_blocks_unless_explicit_draft(self):
  x=data();x['sources']=[]
  with tempfile.TemporaryDirectory() as t:
   out=Path(t)/'draft'
   with self.assertRaises(OutlineValidationError):render_document(x,out)
   self.assertFalse(out.exists())
   r=render_document(x,out,allow_unverified=True)
   self.assertEqual(r['status'],'draft_missing_sources')
   self.assertTrue(Document(out/'outline.docx').paragraphs[0].text.startswith('待核验'))
 def test_schema_error_writes_no_documents(self):
  x=data();x['outline']['sections'][0]['blocks'][1]['rows']=[['缺列']]
  with tempfile.TemporaryDirectory() as t:
   out=Path(t)/'bad'
   with self.assertRaises(OutlineValidationError) as ctx:render_document(x,out)
   self.assertIn('rows[0]',str(ctx.exception));self.assertFalse(out.exists())
 def test_cli_check_only_and_errors_are_machine_readable(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'in.json';p.write_text(json.dumps(data(),ensure_ascii=False))
   cmd=[sys.executable,str(ROOT/'scripts/render_outline.py'),'--input',str(p),'--check-only']
   r=subprocess.run(cmd,capture_output=True,text=True)
   self.assertEqual(r.returncode,0,r.stdout+r.stderr);self.assertEqual(json.loads(r.stdout)['status'],'validated')
   p.write_text('{bad json')
   r=subprocess.run(cmd,capture_output=True,text=True)
   self.assertEqual(r.returncode,2);self.assertTrue(json.loads(r.stdout)['errors'])
 def test_known_source_gaps_and_inherited_draft_do_not_upgrade(self):
  with tempfile.TemporaryDirectory() as t:
   r=render_document(data(),Path(t)/'draft',allow_unverified=True,previous={'draft':True})
   self.assertTrue(r['draft'])
if __name__=='__main__':unittest.main()
