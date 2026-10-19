"""Behavioral regression fixtures for Office package validation (no Office required)."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'validate_outputs.py'
spec = importlib.util.spec_from_file_location('validator', SCRIPT)
v = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v)
W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'

class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def package(self, name, parts):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(path, 'w') as z:
            for part, content in parts.items():
                z.writestr(part, content)
        return path

    def docx(self, text='H2O', fields='', size='<w:pgSz w:h="14740" w:w="10431"/>', extra=None):
        parts = {'word/document.xml': f'<w:document xmlns:w="{W}"><w:body><w:p><w:r><w:t>{text}</w:t>{fields}</w:r></w:p><w:sectPr>{size}</w:sectPr></w:body></w:document>'}
        parts.update(extra or {})
        return self.package('valid.docx', parts)

    def pptx(self, shape='', canvas=(7200000, 5400000), extra=None, relationships=''):
        parts = {
            '[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Override PartName="/ppt/slides/slide1.xml" ContentType="application/vnd.openxmlformats-officedocument.presentationml.slide+xml"/></Types>',
            'ppt/presentation.xml': f'<p:presentation xmlns:p="{P}" xmlns:r="{R}"><p:sldIdLst><p:sldId id="256" r:id="rId1"/></p:sldIdLst><p:sldSz cx="{canvas[0]}" cy="{canvas[1]}"/></p:presentation>',
            'ppt/_rels/presentation.xml.rels': f'<Relationships xmlns="{PKG}"><Relationship Id="rId1" Type="{R}/slide" Target="slides/slide1.xml"/></Relationships>',
            'ppt/slides/slide1.xml': f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld><p:spTree>{shape}</p:spTree></p:cSld></p:sld>',
        }
        if relationships:
            parts['ppt/slides/_rels/slide1.xml.rels'] = f'<Relationships xmlns="{PKG}">{relationships}</Relationships>'
        parts.update(extra or {})
        return self.package('valid.pptx', parts)

    def validate(self, paths):
        self.assertTrue(callable(getattr(v, 'validate_paths', None)), 'validator must expose structured validate_paths API')
        result = v.validate_paths(paths)
        self.assertEqual(set(result), {'passed', 'checked_files', 'issues', 'warnings'})
        for issue in result['issues'] + result['warnings']:
            self.assertEqual(set(issue), {'file', 'location', 'code', 'message'})
        return result

    def codes(self, paths):
        result = self.validate(paths)
        self.assertFalse(result['passed'])
        return {x['code'] for x in result['issues']}

    def test_empty_discovery_fails(self):
        self.assertIn('NO_FILES', self.codes([self.root]))

    def test_missing_explicit_path_is_not_masked_by_valid_file(self):
        self.assertIn('INPUT_NOT_FOUND', self.codes([self.docx(), self.root / 'missing.docx']))

    def test_page_attributes_are_order_independent(self):
        self.assertTrue(self.validate([self.docx()])['passed'])
        self.assertIn('DOCX_PAGE_SIZE', self.codes([self.docx(size='<w:pgSz w:h="15840" w:w="12240"/>')]))

    def test_missing_page_size_fails(self):
        self.assertIn('DOCX_PAGE_SIZE', self.codes([self.docx(size='')]))

    def test_equal_field_counts_wrong_order_fails(self):
        fields = ''.join(f'<w:fldChar w:fldCharType="{t}"/>' for t in ('end', 'begin', 'separate'))
        self.assertIn('DOCX_FIELD_ORDER', self.codes([self.docx(fields=fields)]))

    def test_nested_fields_and_instruction_only_field_are_valid(self):
        fields = ''.join(f'<w:fldChar w:fldCharType="{t}"/>' for t in ('begin', 'begin', 'separate', 'end', 'separate', 'end', 'begin', 'end'))
        self.assertTrue(self.validate([self.docx(fields=fields)])['passed'])

    def test_unicode_visible_text_fails(self):
        self.assertIn('UNICODE_SCRIPT', self.codes([self.docx(text='SO₄²⁻')]))

    def test_malformed_secondary_docx_xml_is_reported(self):
        self.assertIn('XML_PARSE', self.codes([self.docx(extra={'word/header1.xml': '<broken>'})]))

    def test_bad_zip_is_reported(self):
        path = self.root / 'bad.pptx'
        path.write_text('not a zip')
        self.assertIn('PACKAGE_READ', self.codes([path]))

    def test_recursive_discovery_skips_hidden_directories(self):
        p = self.docx()
        (self.root / 'nested').mkdir()
        p.rename(self.root / 'nested' / 'valid.docx')
        self.package('.hidden/bad.docx', {'word/document.xml': '<bad>'})
        self.assertEqual(self.validate([self.root])['checked_files'], 1)

    def test_duplicate_relationship_ids_fail(self):
        rel = f'<Relationship Id="dup" Type="{R}/hyperlink" Target="https://example.org" TargetMode="External"/>'
        self.assertIn('REL_DUPLICATE_ID', self.codes([self.pptx(relationships=rel + rel)]))

    def test_missing_media_target_fails(self):
        rel = f'<Relationship Id="img" Type="{R}/image" Target="../media/missing.png"/>'
        self.assertIn('REL_TARGET_MISSING', self.codes([self.pptx(relationships=rel)]))

    def test_absolute_package_target_and_external_links_are_valid(self):
        rel = f'<Relationship Id="img" Type="{R}/image" Target="/ppt/media/image.png"/><Relationship Id="web" Type="{R}/hyperlink" Target="https://example.org" TargetMode="External"/>'
        self.assertTrue(self.validate([self.pptx(extra={'ppt/media/image.png': b'png'}, relationships=rel)])['passed'])

    def test_embedded_relationship_reference_must_exist(self):
        self.assertIn('REL_REFERENCE_MISSING', self.codes([self.pptx(shape='<p:pic><p:blipFill><a:blip r:embed="missing"/></p:blipFill></p:pic>')]))

    def test_bounds_use_actual_variable_canvas(self):
        shape = '<p:sp><p:spPr><a:xfrm><a:off x="7000000" y="0"/><a:ext cx="300000" cy="300000"/></a:xfrm></p:spPr></p:sp>'
        self.assertIn('PPT_BOUNDS', self.codes([self.pptx(shape=shape)]))
        self.assertTrue(self.validate([self.pptx(shape=shape, canvas=(14400000, 8100000))])['passed'])

    def test_duplicate_offset_and_missing_extent_fail_without_crash(self):
        shape = '<p:sp><p:spPr><a:xfrm><a:off x="0" y="0"/><a:off x="0" y="0"/></a:xfrm></p:spPr></p:sp>'
        self.assertIn('PPT_TRANSFORM', self.codes([self.pptx(shape=shape)]))

    def test_small_inherited_paragraph_font_fails(self):
        shape = '<p:sp><p:txBody><a:bodyPr/><a:lstStyle/><a:p><a:pPr><a:defRPr sz="1800"/></a:pPr><a:r><a:t>Small inherited text</a:t></a:r></a:p></p:txBody></p:sp>'
        self.assertIn('PPT_FONT_SMALL', self.codes([self.pptx(shape=shape)]))

    def test_unknown_font_size_is_explicit_warning(self):
        result = self.validate([self.pptx(shape='<p:sp><p:txBody><a:p><a:r><a:t>Unspecified</a:t></a:r></a:p></p:txBody></p:sp>')])
        self.assertIn('PPT_FONT_UNRESOLVED', {x['code'] for x in result['warnings']})

    def test_content_types_and_presentation_slide_refs_fail(self):
        path = self.pptx(extra={'[Content_Types].xml': '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>', 'ppt/_rels/presentation.xml.rels': f'<Relationships xmlns="{PKG}"/>'})
        codes = self.codes([path])
        self.assertIn('PPT_CONTENT_TYPES', codes)
        self.assertIn('REL_REFERENCE_MISSING', codes)

    def test_answer_blank_requires_run_underline(self):
        path = self.docx(text='填写答案：' + '\u3000' * 4 + '。')
        self.assertIn('MISSING_ANSWER_UNDERLINE', self.codes([path]))

    def test_underlined_answer_blank_is_valid(self):
        path = self.docx(text='填写答案：')
        with zipfile.ZipFile(path) as z:
            xml = z.read('word/document.xml').decode()
        xml = xml.replace('</w:p>', '<w:r><w:rPr><w:u w:val="single"/></w:rPr><w:t>' + '\u3000' * 4 + '</w:t></w:r></w:p>')
        path = self.package('underlined.docx', {'word/document.xml': xml})
        self.assertTrue(self.validate([path])['passed'])

    def test_indentation_and_empty_judgment_parentheses_are_not_answer_blanks(self):
        self.assertTrue(self.validate([self.docx(text='\u3000' * 4 + '判断题（' + '\u3000' * 4 + '）')])['passed'])

    def test_answer_blank_with_explicitly_disabled_underline_fails(self):
        path = self.docx(text='答案：')
        with zipfile.ZipFile(path) as z:
            xml = z.read('word/document.xml').decode()
        xml = xml.replace('</w:p>', '<w:r><w:rPr><w:u w:val="none"/></w:rPr><w:t>' + '\u3000' * 4 + '</w:t></w:r></w:p>')
        self.assertIn('MISSING_ANSWER_UNDERLINE', self.codes([self.package('disabled.docx', {'word/document.xml': xml})]))

    def test_blank_split_across_runs_requires_each_blank_run_underlined(self):
        path = self.docx(text='答案：' + '\u3000' * 2)
        with zipfile.ZipFile(path) as z:
            xml = z.read('word/document.xml').decode()
        xml = xml.replace('</w:p>', '<w:r><w:rPr><w:u/></w:rPr><w:t>' + '\u3000' * 2 + '</w:t></w:r></w:p>')
        self.assertIn('MISSING_ANSWER_UNDERLINE', self.codes([self.package('split.docx', {'word/document.xml': xml})]))

    def test_dtd_is_rejected_without_expanding_local_entities(self):
        path = self.docx(extra={'word/header1.xml': '<!DOCTYPE x [<!ENTITY secret SYSTEM "file:///etc/passwd">]><x>&secret;</x>'})
        report = self.validate([path])
        self.assertIn('XML_DTD', {x['code'] for x in report['issues']})
        self.assertNotIn('root:', json.dumps(report))

    def test_group_geometry_requires_explicit_review_warning(self):
        shape = '<p:grpSp><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="100" cy="100"/><a:chOff x="0" y="0"/><a:chExt cx="100" cy="100"/></a:xfrm></p:grpSpPr></p:grpSp>'
        report = self.validate([self.pptx(shape=shape)])
        self.assertIn('PPT_GEOMETRY_UNSUPPORTED', {x['code'] for x in report['warnings']})

    def test_small_font_inherited_from_layout_is_detected(self):
        shape = '<p:sp><p:nvSpPr><p:nvPr><p:ph idx="1" type="body"/></p:nvPr></p:nvSpPr><p:txBody><a:p><a:r><a:t>Inherited</a:t></a:r></a:p></p:txBody></p:sp>'
        layout = f'<p:sldLayout xmlns:p="{P}" xmlns:a="{A}"><p:cSld><p:spTree><p:sp><p:nvSpPr><p:nvPr><p:ph idx="1" type="body"/></p:nvPr></p:nvSpPr><p:txBody><a:lstStyle><a:lvl1pPr><a:defRPr sz="2000"/></a:lvl1pPr></a:lstStyle></p:txBody></p:sp></p:spTree></p:cSld></p:sldLayout>'
        rel = f'<Relationship Id="layout" Type="{R}/slideLayout" Target="../slideLayouts/slideLayout1.xml"/>'
        self.assertIn('PPT_FONT_SMALL', self.codes([self.pptx(shape=shape, relationships=rel, extra={'ppt/slideLayouts/slideLayout1.xml': layout})]))

    def test_table_transform_bounds_are_checked(self):
        shape = '<p:graphicFrame><p:xfrm><a:off x="7190000" y="0"/><a:ext cx="200000" cy="100000"/></p:xfrm></p:graphicFrame>'
        self.assertIn('PPT_BOUNDS', self.codes([self.pptx(shape=shape)]))

    def test_bad_cli_option_has_bad_input_exit_code(self):
        run = subprocess.run([sys.executable, str(SCRIPT), '--nonsense'], capture_output=True)
        self.assertEqual(run.returncode, 1)

    def test_cli_json_report_and_exit_codes(self):
        valid = self.docx()
        report = self.root / 'report.json'
        run = subprocess.run([sys.executable, str(SCRIPT), str(valid), '--json', '--report', str(report)], capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(json.loads(run.stdout)['passed'])
        self.assertEqual(json.loads(report.read_text()), json.loads(run.stdout))
        missing = subprocess.run([sys.executable, str(SCRIPT), str(self.root / 'missing')], capture_output=True)
        self.assertEqual(missing.returncode, 1)
        bad = self.docx(text='H₂O')
        invalid = subprocess.run([sys.executable, str(SCRIPT), str(bad)], capture_output=True)
        self.assertEqual(invalid.returncode, 2)

if __name__ == '__main__':
    unittest.main()
