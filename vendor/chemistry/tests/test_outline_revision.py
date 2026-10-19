import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from outline_contract import normalize_outline, outline_digest
from revise_outline import revise_document


def outline():
    return {'title': '氧化还原', 'goals': ['解释电子转移。'], 'sections': [
        {'id': 's1', 'title': '课堂任务', 'blocks': [
            {'id': 'p1', 'type': 'paragraph', 'content': '原检查点'},
            {'id': 'p2', 'type': 'paragraph', 'content': '保留段落'},
            {'id': 't1', 'type': 'table', 'headers': ['反应', '判断'],
             'rows': [['[H2O]', None]], 'widths_cm': [8, 10]}]}],
        'thinking': ['保留思考'], 'schedule_note': '保留时间安排'}


class RevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.current = self.base / 'v001'
        self.current.mkdir()
        self.content = normalize_outline(outline())
        self.source = {'title': '氧化还原', 'outline': outline(), 'sources': [
            {'id': 'book', 'category': 'textbook', 'title': '教材',
             'locator': '第1页', 'evidence': '原始证据', 'verified': False}]}
        self.report = {'version': 'v001', 'content_sha256': outline_digest(self.content),
                       'status': 'draft_missing_sources', 'files': ['outline.docx']}
        for name, value in [('content.json', self.content), ('source_input.json', self.source),
                            ('generation_report.json', self.report)]:
            self.write(self.current / name, value)
        (self.current / 'outline.docx').write_bytes(b'original document snapshot')
        self.original = {p.name: p.read_bytes() for p in self.current.iterdir()}
        self.patch = {'base_sha256': self.report['content_sha256'], 'changes': [
            {'block_id': 'p1', 'replacement': [{'type': 'paragraph', 'content': '新检查点'}]}]}

    def write(self, path, value):
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    def assert_original(self):
        self.assertEqual({p.name: p.read_bytes() for p in self.current.iterdir()}, self.original)

    def test_rejects_stale_hash_and_preserves_original(self):
        self.patch['base_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            revise_document(self.current, self.patch, self.base / 'v002')
        self.assert_original()
        self.assertFalse((self.base / 'v002').exists())

    def test_rejects_tampered_content_even_when_patch_matches_report(self):
        self.content['sections'][0]['blocks'][1]['content'] = '篡改'
        self.write(self.current / 'content.json', self.content)
        with self.assertRaises(ValueError):
            revise_document(self.current, self.patch, self.base / 'v002')
        self.assertFalse((self.base / 'v002').exists())

    def test_rejects_invalid_patch_before_creating_output(self):
        cases = []
        for key, value in [('base_sha256', None), ('changes', []), ('extra', True)]:
            patch = copy.deepcopy(self.patch)
            patch[key] = value
            cases.append(patch)
        for changes in [
            [{'block_id': 'missing', 'replacement': [{'type': 'paragraph', 'content': 'x'}]}],
            [self.patch['changes'][0], self.patch['changes'][0]],
            [{'block_id': 'p1', 'replacement': []}],
            [{'block_id': 'p1', 'replacement': [{'type': 'image', 'content': 'x'}]}],
            [{'block_id': 'p1', 'replacement': [{'id': 'p2', 'type': 'paragraph', 'content': 'x'}]}],
            [{'block_id': 'p1', 'replacement': [{'type': 'table', 'headers': ['a', 'b'], 'rows': [['bad']]}]}],
            [{'block_id': 'p1', 'replacement': [{'type': 'paragraph', 'content': 'x'}], 'title': '禁止'}],
        ]:
            cases.append(dict(self.patch, changes=changes))
        for patch in cases:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                revise_document(self.current, patch, self.base / 'v002')
            self.assertFalse((self.base / 'v002').exists())
            self.assert_original()

    def test_rejects_same_nested_existing_directory_and_reused_version(self):
        occupied = self.base / 'occupied'
        occupied.mkdir()
        (occupied / 'keep').write_text('keep')
        for target, version in [(self.current, 'v002'), (self.current / 'child', 'v002'),
                                (occupied, 'v002'), (self.base / 'v002', 'v001')]:
            with self.subTest(target=target, version=version), self.assertRaises(ValueError):
                revise_document(self.current, self.patch, target, version=version)
        self.assert_original()
        self.assertEqual((occupied / 'keep').read_text(), 'keep')

    def test_real_revision_preserves_unrelated_content_sources_and_draft(self):
        self.patch['changes'][0]['replacement'].append({'type': 'paragraph', 'content': '追问依据'})
        before_patch = copy.deepcopy(self.patch)
        target = self.base / 'v002'
        report = revise_document(self.current, self.patch, target)
        revised = json.loads((target / 'content.json').read_text())
        expected = copy.deepcopy(self.content)
        expected['sections'][0]['blocks'][0:1] = [
            {'id': 'p1', 'type': 'paragraph', 'content': '新检查点'},
            {'id': 'p1-2', 'type': 'paragraph', 'content': '追问依据'}]
        self.assertEqual(revised, expected)
        new_source = json.loads((target / 'source_input.json').read_text())
        self.assertEqual(new_source, dict(self.source, outline=expected))
        self.assertEqual(report['version'], 'v002')
        self.assertEqual(report['content_sha256'], outline_digest(expected))
        self.assertIn('draft', report['status'])
        self.assertTrue((target / 'outline.docx').is_file())
        self.assertEqual(self.patch, before_patch)
        self.assert_original()

    def test_rejects_replacement_id_collisions_with_sections_and_other_changes(self):
        for new_id in ['s1', 'p2', 'new-unique']:
            patch = copy.deepcopy(self.patch)
            patch['changes'][0]['replacement'].append(
                {'id': new_id, 'type': 'paragraph', 'content': '新增'})
            if new_id == 'new-unique':
                patch['changes'].append({'block_id': 'p2', 'replacement': [
                    {'type': 'paragraph', 'content': '新段落'},
                    {'id': 'new-unique', 'type': 'paragraph', 'content': '冲突'}]})
            with self.subTest(new_id=new_id), self.assertRaises(ValueError):
                revise_document(self.current, patch, self.base / 'v002')
            self.assert_original()
            self.assertFalse((self.base / 'v002').exists())

    def test_real_table_revision_accepts_unique_explicit_additional_id(self):
        self.patch['changes'] = [{'block_id': 't1', 'replacement': [
            {'type': 'table', 'headers': ['反应', '判断'], 'rows': [['[Fe^3+]', '氧化剂']],
             'widths_cm': [8, 10]},
            {'id': 'followup', 'type': 'paragraph',
             'content': [{'text': '依据：'}, {'text': '3+', 'sup': True}]}]}]
        report = revise_document(self.current, self.patch, self.base / 'v002')
        revised = json.loads((self.base / 'v002/content.json').read_text())
        blocks = revised['sections'][0]['blocks']
        self.assertEqual(blocks[:2], self.content['sections'][0]['blocks'][:2])
        self.assertEqual(blocks[2]['id'], 't1')
        self.assertEqual(blocks[2]['rows'], [['[Fe^3+]', '氧化剂']])
        self.assertEqual(blocks[3]['id'], 'followup')
        self.assertEqual(report['content_sha256'], outline_digest(revised))
        self.assert_original()

    def test_inherited_draft_is_never_upgraded_when_sources_are_complete(self):
        self.source['sources'][0]['verified'] = True
        self.write(self.current / 'source_input.json', self.source)
        report = revise_document(self.current, self.patch, self.base / 'v002')
        self.assertTrue(report['draft'])
        self.assertIn('draft', report['status'])
        source = json.loads((self.base / 'v002/source_input.json').read_text())
        self.assertEqual(source['sources'], self.source['sources'])

    def test_repeated_split_allocates_unused_ids_and_preserves_prior_additions(self):
        self.patch['changes'][0]['replacement'].append({'type': 'paragraph', 'content': '第一次新增'})
        v2 = self.base / 'v002'
        first = revise_document(self.current, self.patch, v2)
        second_patch = {'base_sha256': first['content_sha256'], 'changes': [
            {'block_id': 'p1', 'replacement': [
                {'type': 'paragraph', 'content': '再次修改'},
                {'type': 'paragraph', 'content': '第二次新增'}]}]}
        v3 = self.base / 'v003'
        revise_document(v2, second_patch, v3, version='v003')
        blocks = json.loads((v3 / 'content.json').read_text())['sections'][0]['blocks']
        self.assertEqual([b['id'] for b in blocks], ['p1', 'p1-3', 'p1-2', 'p2', 't1'])
        self.assertEqual(blocks[2]['content'], '第一次新增')
        self.assert_original()

    def test_cli_invalid_patch_returns_nonzero_without_success_artifact(self):
        patch_path = self.base / 'patch.json'
        self.patch['base_sha256'] = 'stale'
        self.write(patch_path, self.patch)
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/revise_outline.py'),
                                 '--current', str(self.current), '--patch', str(patch_path),
                                 '--output-dir', str(self.base / 'v002')], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.base / 'v002').exists())
        self.assert_original()


if __name__ == '__main__':
    unittest.main()
