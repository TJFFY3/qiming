import copy,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from outline_contract import normalize_outline, OutlineValidationError, outline_digest

def canonical():
 return {'title':'氧化还原反应 第1课时','goals':['通过观察能够判断反应。'],'sections':[{'id':'task-one','title':'任务一','blocks':[{'id':'p-one','type':'paragraph','content':'标注 [H2O]。'},{'id':'t-one','type':'table','headers':['编号','化学式','判断'],'rows':[['①','[SO4^2-]',None]],'widths_cm':[2,8,8]}]}],'thinking':['如何核对？']}

def legacy():
 return {'title':'旧版测试','goals':['通过比较能够解释电子转移。'],'schedule_note':'任务一12分钟。','groups':[{'heading':'【课堂任务】','blocks':[{'kind':'section','title':'任务一','body':[{'kind':'lead','label':'学生动作','value':'标出化合价。'},{'kind':'eq','value':[['2[CuO] + [C] ',{'text':'高温','condition':True},' 2[Cu] + [CO2]↑']]},{'kind':'table','note':'请填写。','headers':['编号','判断'],'widths':[2,10],'rows':[['①',None],['②','']]},{'kind':'lead','label':'检查点','value':'说明判断依据。'}]}]}],'thinking':['为什么？']}

class ContractTests(unittest.TestCase):
 def test_canonical_roundtrip_and_ids(self):
  data=canonical();before=copy.deepcopy(data)
  self.assertEqual(normalize_outline(data),data)
  self.assertEqual(data,before)
 def test_old_paragraphs_remain_supported(self):
  data={'title':'旧版','goals':['目标'],'sections':[{'title':'任务','paragraphs':['正文',[{'text':'2','sup':True}]]}]}
  result=normalize_outline(data)
  self.assertEqual([b['content'] for b in result['sections'][0]['blocks']],data['sections'][0]['paragraphs'])
  self.assertEqual(outline_digest(result),outline_digest(normalize_outline(result)))
 def test_poc_legacy_table_equation_and_labels_preserved(self):
  data=legacy();old=copy.deepcopy(data);result=normalize_outline(data)
  sec=result['sections'][0]
  self.assertEqual(sec['group'],'【课堂任务】')
  self.assertEqual(sec['blocks'][0]['content'],'学生动作　标出化合价。')
  table=next(b for b in sec['blocks'] if b['type']=='table')
  self.assertEqual(table['rows'],[['①',None],['②','']])
  self.assertEqual(table['widths_cm'],[2,10])
  self.assertTrue(any('请填写。' in str(b['content']) for b in sec['blocks'] if b['type']=='paragraph'))
  equation=sec['blocks'][1]['content']
  self.assertTrue(all(isinstance(r,dict) and 'text' in r for r in equation))
  self.assertEqual(equation[1],{'text':'高温','condition':True})
  self.assertEqual(data,old)
 def test_invalid_runs_report_exact_field_path(self):
  data=canonical();data['sections'][0]['blocks'][0]['content']=[['bad']]
  with self.assertRaises(OutlineValidationError) as ctx:normalize_outline(data)
  self.assertIn('sections[0].blocks[0]',str(ctx.exception))
 def test_invalid_row_reports_row_path(self):
  data=canonical();data['sections'][0]['blocks'][1]['rows'][0]=['①']
  with self.assertRaises(OutlineValidationError) as ctx:normalize_outline(data)
  self.assertIn('rows[0]',str(ctx.exception))
 def test_unknown_fields_are_not_silently_discarded(self):
  data=canonical();data['sections'][0]['blokcs']=[]
  with self.assertRaises(OutlineValidationError):normalize_outline(data)
  data=legacy();data['groups'][0]['blocks'][0]['body'][0]['unrecognized']='内容'
  with self.assertRaises(OutlineValidationError):normalize_outline(data)
 def test_unsupported_legacy_blocks_fail(self):
  data=legacy();data['groups'][0]['blocks'][0]['body'].append({'kind':'image','value':'missing.png'})
  with self.assertRaises(OutlineValidationError):normalize_outline(data)
 def test_duplicate_ids_fail(self):
  data=canonical();data['sections'][0]['blocks'][1]['id']='p-one'
  with self.assertRaises(OutlineValidationError):normalize_outline(data)
 def test_wrong_width_count_or_nonfinite_fails(self):
  for widths in ([1],[1,2,float('nan')],[1,2,-1],[True,1,2]):
   data=canonical();data['sections'][0]['blocks'][1]['widths_cm']=widths
   with self.subTest(widths=widths),self.assertRaises(OutlineValidationError):normalize_outline(data)
 def test_conflicting_representations_fail(self):
  data=canonical();data['sections'][0]['paragraphs']=['不能丢失的内容']
  with self.assertRaises(OutlineValidationError):normalize_outline(data)
 def test_superscript_subscript_conflict_fails(self):
  data=canonical();data['sections'][0]['blocks'][0]['content']=[{'text':'2','sup':True,'sub':True}]
  with self.assertRaises(OutlineValidationError):normalize_outline(data)
if __name__=='__main__':unittest.main()
