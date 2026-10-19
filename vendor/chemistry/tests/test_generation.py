import sys, tempfile, unittest, zipfile
from pathlib import Path
from lxml import etree
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from chemistry_runs import normalize_runs, add_docx_runs
from docx_tools import generate_outline, generate_paper, generate_answers
from docx import Document
W = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

class ChemistryTests(unittest.TestCase):
    def test_coefficient_and_charge(self):
        runs = normalize_runs('2[SO4^2-] + [Fe^3+] + [H2O]')
        self.assertEqual(runs[0]['text'], '2')
        self.assertFalse(runs[0].get('sub',False))
        self.assertTrue(any(r['text']=='4' and r.get('sub') for r in runs))
        self.assertTrue(any(r['text']=='2-' and r.get('charge') for r in runs))
    def test_unicode_is_normalized(self):
        r=normalize_runs('H₂O 和 Fe³⁺')
        self.assertFalse(any(any(c in x['text'] for c in '₂³⁺') for x in r))
        self.assertTrue(any(x.get('charge') for x in r))
    def test_cached_ion_field(self):
        d=Document(); p=d.add_paragraph(); add_docx_runs(p,'[SO4^2-]')
        x=p._p
        self.assertEqual(x.xpath('.//w:fldChar/@w:fldCharType'),['begin','separate','end'])
        instr=''.join(x.xpath('.//w:instrText/text()'))
        self.assertIn('2-',instr); self.assertIn('4',instr)
        self.assertTrue(x.xpath('.//w:t[text()="2-"]'))
    def test_full_width_answer_blanks_underlined(self):
        d=Document();p=d.add_paragraph()
        add_docx_runs(p,'现象：　　　　；结论：　　　　。')
        blank=p._p.xpath('.//w:r[w:t="　　　　"]')
        self.assertEqual(len(blank),2)
        self.assertTrue(all(x.xpath('./w:rPr/w:u') for x in blank))
    def test_explicit_conditions_and_isotope(self):
        d=Document();p=d.add_paragraph()
        add_docx_runs(p,[{'text':'点燃','condition':True},{'text':'C','isotope':{'mass':'12','atomic':'6'}}])
        self.assertEqual(p._p.xpath('.//w:fldChar/@w:fldCharType').count('begin'),2)

class DocumentTests(unittest.TestCase):
    def test_template_replacement_and_page_settings(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'outline.docx'
            generate_outline({'title':'测试课时','goals':['通过观察能够解释现象。'], 'sections':[{'title':'基础','paragraphs':['[H2O] 的组成：____']}], 'thinking':['比较性质。']},p)
            d=Document(p)
            self.assertEqual(len(d.tables[-1].rows),25)
            self.assertNotIn('泄露',''.join(x.text for x in d.paragraphs))
            self.assertEqual(round(d.sections[0].page_width/635),10431)
            self.assertIn('H2O',''.join(x.text for x in d.paragraphs))
    def test_paper_score_time_and_separate_answers(self):
        questions=[{'stem':f'第{i}题 [H2O] 的性质', 'options':['甲','乙','丙','丁'], 'answer':'A','explanation':'测试说明','score':4,'minutes':1.5,'difficulty':'基础'} for i in range(14)]
        written=[{'stem':'写出过程','answer':'答案','explanation':'解析','score':44,'minutes':11,'difficulty':'中档','work_lines':2}]
        paper={'title':'测试课时','choice':questions,'written':written,'optional':[{'stem':'选做','answer':'答案','explanation':'解析','minutes':3,'difficulty':'较难'},{'stem':'选做二','answer':'答案','explanation':'解析','minutes':3,'difficulty':'较难'}]}
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'paper.docx'; a=Path(t)/'answer.docx'
            generate_paper(paper,p); generate_answers(paper,a)
            text=''.join(x.text for x in Document(p).paragraphs)
            self.assertNotIn('测试说明',text)
            self.assertIn('测试说明',''.join(x.text for x in Document(a).paragraphs))
            self.assertEqual(len(Document(p).tables[0].columns),15)
            empty_options=dict(paper,choice=[dict(q,options=['','','','']) for q in questions])
            with self.assertRaises(ValueError):generate_paper(empty_options,p)
            bad=dict(paper,written=[dict(written[0],score=40)])
            with self.assertRaises(ValueError):generate_paper(bad,p)
            bad=dict(paper,written=[dict(written[0],minutes=20)])
            with self.assertRaises(ValueError):generate_paper(bad,p)

if __name__=='__main__':unittest.main()
