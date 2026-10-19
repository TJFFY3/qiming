"""Package-level invariants catch corrupt duplicated slides and chemical typography."""
import base64
import importlib
import posixpath
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
NS = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main', 'a':'http://schemas.openxmlformats.org/drawingml/2006/main', 'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}

class PowerPointTests(unittest.TestCase):
    def generate(self, slides, target, **kwargs):
        self.assertTrue((ROOT/'scripts/ppt_tools.py').exists(), 'PPT generator is missing')
        return importlib.import_module('ppt_tools').generate_pptx(slides, target, **kwargs)

    def test_more_than_eight_slides_have_complete_ordered_package(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'deck.pptx'
            self.generate([{'title':f'课程{i}', 'stage':'析','paragraphs':['2[H2O] + [SO4^2-]']} for i in range(11)], output)
            with ZipFile(output) as z, ZipFile(ROOT/'assets/templates/课件模板.pptx') as template:
                files=set(z.namelist())
                pres=E.fromstring(z.read('ppt/presentation.xml'))
                rels=E.fromstring(z.read('ppt/_rels/presentation.xml.rels'))
                mapping={r.get('Id'):r.get('Target') for r in rels}
                ordered=['ppt/'+mapping[s.get('{'+NS['r']+'}id')] for s in pres.find('p:sldIdLst',NS)]
                self.assertEqual(len(ordered),11)
                overrides=E.fromstring(z.read('[Content_Types].xml'))
                slides={x.get('PartName')[1:] for x in overrides if x.get('ContentType','').endswith('presentationml.slide+xml')}
                self.assertEqual(slides,set(ordered))
                for i,name in enumerate(ordered):
                    xml=E.fromstring(z.read(name))
                    texts=xml.xpath('//a:t/text()',namespaces=NS)
                    self.assertIn(f'课程{i}',texts)
                    self.assertNotIn('课程'+str((i+1)%11),texts)
                    self.assertTrue(xml.xpath('//a:rPr[@baseline="-25000"]/../a:t[text()="2"]',namespaces=NS))
                    self.assertTrue(xml.xpath('//a:rPr[@baseline="30000"]/../a:t[text()="2-"]',namespaces=NS))
                    self.assertTrue(xml.xpath('//a:r[a:t="2"]/a:rPr[not(@baseline)]',namespaces=NS))
                    for xf in xml.xpath('//a:xfrm',namespaces=NS):
                        self.assertEqual(len(xf.findall('a:off',NS)),1)
                        self.assertEqual(set(xf.find('a:off',NS).attrib),{'x','y'})
                    self.assertTrue(all(int(x)>=2400 for x in xml.xpath('//@sz')))
                for n in template.namelist():
                    if n.startswith(('ppt/slideMasters/','ppt/slideLayouts/')):
                        self.assertEqual(z.read(n),template.read(n))
                for n in files:
                    if n.endswith('.rels'):
                        relxml=E.fromstring(z.read(n)); ids=[r.get('Id') for r in relxml]
                        self.assertEqual(len(ids),len(set(ids)))
                        base=posixpath.dirname(n).replace('/_rels','')
                        if n=='_rels/.rels':base=''
                        for r in relxml:
                            if r.get('TargetMode')!='External':
                                self.assertIn(posixpath.normpath(posixpath.join(base,r.get('Target'))).lstrip('/'),files)

    def test_repeated_images_notes_unicode_and_long_badge(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            (p/'photo.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aU1sAAAAASUVORK5CYII='))
            self.generate([{'title':'观察','stage':'辩—预设展示','paragraphs':['CO₂↑ 与 Fe³⁺'], 'image':'photo.png','notes':'讲解提醒'}]*2,p/'out.pptx',base_dir=p)
            with ZipFile(p/'out.pptx') as z:
                for i in (1,2):
                    x=E.fromstring(z.read(f'ppt/slides/slide{i}.xml'))
                    self.assertFalse(any(c in ''.join(x.xpath('//a:t/text()',namespaces=NS)) for c in '₂³⁺'))
                    self.assertEqual(len(x.xpath('//p:pic',namespaces=NS)),1)
                    self.assertTrue(x.xpath('//a:t[text()="辩—预设展示"]',namespaces=NS))
                    self.assertIn('讲解提醒',z.read(f'ppt/notesSlides/notesSlide{i}.xml').decode())

    def test_rejects_invalid_stage_overflow_and_remote_media(self):
        valid={'title':'标题','stage':'启','paragraphs':['正文']}
        cases=[dict(valid,stage='结束'),dict(valid,paragraphs=['字'*201]),dict(valid,paragraphs=['一']*7),dict(valid,title='字'*80),dict(valid,image='https://example.com/x.png'),dict(valid,paragraphs=[['bad']])]
        with tempfile.TemporaryDirectory() as d:
            for slide in cases:
                with self.subTest(slide=slide), self.assertRaises(ValueError):
                    self.generate([slide],Path(d)/'bad.pptx')

    def test_explicit_condition_isotope_and_charge_have_baseline(self):
        slide={'title':'符号','stage':'探','paragraphs':[[{'text':'点燃','condition':True},{'text':'C','isotope':{'mass':12,'atomic':6}},{'text':'3+','charge':True}]]}
        with tempfile.TemporaryDirectory() as d:
            self.generate([slide],Path(d)/'out.pptx')
            with ZipFile(Path(d)/'out.pptx') as z:
                x=E.fromstring(z.read('ppt/slides/slide1.xml'))
                for t in ['12','3+']:
                    self.assertTrue(x.xpath('//a:r[a:t=$text]/a:rPr[@baseline="30000"]',namespaces=NS,text=t))
                self.assertTrue(x.xpath('//a:r[a:t="6"]/a:rPr[@baseline="-25000"]',namespaces=NS))

    def test_condition_label_is_editable_above_normal_equals(self):
        with tempfile.TemporaryDirectory() as d:
            output=Path(d)/'reaction.pptx'
            self.generate([{'title':'反应','stage':'析','paragraphs':[[{'text':'2[H2] + [O2] '},{'text':'点燃','condition':True},{'text':' 2[H2O]'}]]}],output)
            with ZipFile(output) as z:
                x=E.fromstring(z.read('ppt/slides/slide1.xml'))
                self.assertTrue(x.xpath('//a:r[a:t="====="]/a:rPr[not(@baseline)]',namespaces=NS))
                eq=x.xpath('//p:sp[.//a:t="====="]',namespaces=NS)[0]
                label=x.xpath('//p:sp[.//a:t="点燃"]',namespaces=NS)[0]
                eqoff=eq.find('p:spPr/a:xfrm/a:off',NS)
                labeloff=label.find('p:spPr/a:xfrm/a:off',NS)
                self.assertLess(int(labeloff.get('y')),int(eqoff.get('y')))
                self.assertTrue(label.xpath('.//a:rPr[@sz="2400"]',namespaces=NS))
            long={'title':'反应','stage':'析','paragraphs':[[{'text':'字'*36},{'text':'高温','condition':True}]]}
            with self.assertRaises(ValueError):self.generate([long],output)

if __name__=='__main__':unittest.main()
