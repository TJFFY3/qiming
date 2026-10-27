"""Regression checks for editable, in-order chemistry outline tables."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path
from docx import Document
from docx.oxml.ns import qn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from docx_tools import generate_outline


def outline():
    blocks = []
    for index, (count, columns) in enumerate(((4, 5), (4, 5), (8, 4)), 1):
        blocks.append({'id': f'p{index}', 'type': 'paragraph', 'content': f'表{index}前'})
        rows = [[f'{index}-{row}', '[SO4^2-]', None, '现象：________'] + (['补充'] if columns == 5 else []) for row in range(count)]
        rows[0][1] = [{'text': 'C', 'isotope': {'mass': '12', 'atomic': '6'}}, {'text': '高温', 'condition': True}, {'text': '2', 'sub': True}]
        rows[1][3] = [{'text': '结论：________'}]
        blocks.append({'id': f't{index}', 'type': 'table', 'headers': [f'表{index}列{col}' for col in range(columns)], 'rows': rows, 'widths_cm': [2, 3.2, 3.2, 3.6, 3.4] if columns == 5 else [2, 4, 5, 6]})
    return {'title': '氧化还原反应', 'goals': ['填写表格并解释变化。'], 'schedule_note': '任务共计20分钟。', 'sections': [{'id': 's1', 'title': '任务一', 'group': '【基础自学】', 'blocks': blocks}, {'id': 's2', 'title': '任务二', 'group': '【课堂探究】', 'blocks': [{'id': 'end', 'type': 'paragraph', 'content': '末尾检查'}]}], 'thinking': ['如何验证？']}


class OutlineTableTests(unittest.TestCase):
    def render(self, data):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        target = Path(folder.name) / 'outline.docx'
        generate_outline(data, target)
        return Document(target)

    def test_all_three_native_tables_and_notes_survive_in_order(self):
        doc = self.render(outline())
        self.assertEqual([(len(t.rows), len(t.columns)) for t in doc.tables], [(5, 5), (5, 5), (9, 4), (25, 1)])
        stream = []
        for node in doc.element.body:
            text = ''.join(node.xpath('.//w:t/text()'))
            if text in ('表1前', '表2前', '表3前', '末尾检查', '【笔记区域】'):
                stream.append(text)
            elif node.tag == qn('w:tbl'):
                stream.append('table')
        self.assertEqual(stream, ['表1前', 'table', '表2前', 'table', '表3前', 'table', '末尾检查', '【笔记区域】', 'table'])
        paragraphs = [p.text for p in doc.paragraphs]
        self.assertEqual(paragraphs.count('【基础自学】'), 1)
        self.assertEqual(paragraphs.count('【课堂探究】'), 1)
        self.assertEqual(paragraphs.count('任务共计20分钟。'), 1)

    def test_table_geometry_pagination_and_editable_answer_space(self):
        doc = self.render(outline())
        available = int((doc.sections[0].page_width - doc.sections[0].left_margin - doc.sections[0].right_margin) / 635)
        self.assertEqual(len(doc.tables), 4)
        for table in doc.tables[:-1]:
            grid = [int(x) for x in table._tbl.xpath('./w:tblGrid/w:gridCol/@w:w')]
            self.assertLessEqual(sum(grid), available)
            self.assertEqual(table._tbl.xpath('./w:tblPr/w:tblLayout/@w:type'), ['fixed'])
            self.assertEqual(table.rows[0]._tr.xpath('./w:trPr/w:tblHeader/@w:val'), ['true'])
            for row in table.rows:
                self.assertTrue(row._tr.xpath('./w:trPr/w:cantSplit'))
                self.assertEqual([int(cell._tc.xpath('./w:tcPr/w:tcW/@w:w')[0]) for cell in row.cells], grid)
                self.assertFalse(row._tr.xpath('.//w:noWrap'))
            empty = table.cell(1, 2)
            self.assertEqual(empty.text, '')
            self.assertTrue(empty.paragraphs)
            self.assertGreaterEqual(table.rows[1].height.cm, .75)
            self.assertEqual(table.rows[1]._tr.xpath('./w:trPr/w:trHeight/@w:hRule'), ['atLeast'])
            for cell in table.rows[0].cells:
                self.assertTrue(cell._tc.xpath('./w:tcPr/w:shd/@w:fill'))
                self.assertTrue(all(run.bold for run in cell.paragraphs[0].runs))
                self.assertEqual(cell.paragraphs[0].alignment, 1)

    def test_cells_preserve_chemistry_fields_blanks_and_typography(self):
        doc = self.render(outline())
        self.assertGreater(len(doc.tables), 1, 'content tables must be native Word tables')
        table = doc.tables[0]
        chemistry = table.cell(1, 1)._tc
        self.assertIn('12', ''.join(chemistry.xpath('.//w:instrText/text()')))
        self.assertTrue(chemistry.xpath('.//w:ruby/w:rubyBase/w:r/w:rPr/w:u[@w:val="double"]'))
        self.assertTrue(chemistry.xpath('.//w:vertAlign[@w:val="subscript"]'))
        self.assertIn('2-', ''.join(table.cell(2, 1)._tc.xpath('.//w:instrText/text()')))
        self.assertTrue(table.cell(1, 3)._tc.xpath('.//w:r[w:rPr/w:u]'))
        self.assertTrue(table.cell(2, 3)._tc.xpath('.//w:r[w:rPr/w:u]'))
        for cell in table.rows[1].cells:
            for p in cell.paragraphs:
                self.assertAlmostEqual(p.paragraph_format.line_spacing, 1.1)
                for run in p.runs:
                    self.assertEqual(run.font.name, 'Times New Roman')
                    self.assertEqual(run.font.size.pt, 11)
                    self.assertEqual(run._r.xpath('./w:rPr/w:rFonts/@w:eastAsia'), ['宋体'])

    def test_invalid_direct_call_never_overwrites_existing_file(self):
        data = outline()
        data['sections'][0]['blocks'][1]['rows'][0].pop()
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / 'existing.docx'
            target.write_bytes(b'original')
            with self.assertRaises(ValueError):
                generate_outline(data, target)
            self.assertEqual(target.read_bytes(), b'original')

    def test_legacy_paragraphs_keep_chemistry_and_blank_notes(self):
        data = {'title': '旧版', 'goals': ['目标'], 'sections': [{'title': '任务', 'paragraphs': ['水[H2O]，现象________']}], 'thinking': []}
        before = copy.deepcopy(data)
        doc = self.render(data)
        self.assertEqual(data, before)
        self.assertEqual(len(doc.tables), 1)
        self.assertEqual(len(doc.tables[0].rows), 25)
        self.assertIn('水H2O', ''.join(p.text for p in doc.paragraphs))


if __name__ == '__main__':
    unittest.main()
