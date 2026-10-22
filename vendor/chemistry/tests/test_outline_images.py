import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from zipfile import ZipFile
import zlib

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from docx_tools import generate_outline
from outline_contract import normalize_outline, OutlineValidationError
from render_outline import render_document
from revise_outline import revise_document

IMAGE_ID = '0123456789abcdef01234567'
OTHER_ID = 'fedcba9876543210fedcba98'


def png(width, height):
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + b'\x11\x55\x99' * width) * height)) + chunk(b'IEND', b''))


def source():
    return {'outline': {'title': '实验观察', 'goals': ['观察现象'], 'sections': [
        {'id': 's1', 'title': '实验', 'blocks': [
            {'id': 'before', 'type': 'paragraph', 'content': '图片前'},
            {'id': 'img1', 'type': 'image', 'image_id': IMAGE_ID, 'caption': '装置示意图'},
            {'id': 'after', 'type': 'paragraph', 'content': '图片后'}]}]},
        'sources': [{'category': 'textbook', 'title': '教材', 'locator': '第1页', 'evidence': '摘录', 'verified': True}]}


class OutlineImageTests(unittest.TestCase):
    def test_image_contract_and_closed_fields(self):
        self.assertEqual(normalize_outline(source()['outline']), source()['outline'])
        for changed in ({'image_id': '../unsafe'}, {'image_id': IMAGE_ID.upper()}, {'caption': '  '}, {'caption': ''},
                        {'url': 'https://example.com/a.png'}, {'path': '/tmp/a.png'}, {'content': 'unexpected'}):
            data = source()['outline']
            data['sections'][0]['blocks'][1].update(changed)
            with self.subTest(changed=changed), self.assertRaises(OutlineValidationError):
                normalize_outline(data)

    def test_word_embeds_at_block_position_and_fits_width_and_height(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            for width, height in ((1800, 200), (200, 1800)):
                asset = base / 'input.bin'
                asset.write_bytes(png(width, height))
                output = base / 'outline.docx'
                generate_outline(source()['outline'], output, image_assets={IMAGE_ID: asset})
                doc = Document(output)
                self.assertEqual(len(doc.inline_shapes), 1)
                shape = doc.inline_shapes[0]
                section = doc.sections[0]
                self.assertLessEqual(shape.width, section.page_width - section.left_margin - section.right_margin)
                self.assertLessEqual(shape.height, Cm(9))
                self.assertAlmostEqual(shape.width / shape.height, width / height, places=4)
                paragraphs = doc.paragraphs
                before = next(i for i, p in enumerate(paragraphs) if p.text == '图片前')
                caption = next(i for i, p in enumerate(paragraphs) if p.text == '装置示意图')
                after = next(i for i, p in enumerate(paragraphs) if p.text == '图片后')
                self.assertEqual(caption, before + 2)
                self.assertLess(caption, after)
                self.assertTrue(paragraphs[before + 1]._p.xpath('.//wp:inline'))
                self.assertEqual(paragraphs[caption].alignment, WD_ALIGN_PARAGRAPH.CENTER)
                with ZipFile(output) as archive:
                    media = [name for name in archive.namelist() if name.startswith('word/media/')]
                    self.assertEqual(len(media), 1)
                    self.assertEqual(archive.read(media[0]), asset.read_bytes())

    def test_render_snapshots_only_references_and_revision_retains_images(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            asset = base / 'input.png'
            image_bytes = png(80, 40)
            asset.write_bytes(image_bytes)
            current = base / 'v001'
            report = render_document(source(), current, image_assets={IMAGE_ID: asset, OTHER_ID: base / 'nonexistent'})
            self.assertEqual(report['statistics']['images'], 1)
            self.assertEqual(list((current / 'images').iterdir()), [current / 'images' / (IMAGE_ID + '.bin')])
            self.assertEqual((current / 'images' / (IMAGE_ID + '.bin')).read_bytes(), image_bytes)
            self.assertEqual(json.loads((current / 'content.json').read_text()), source()['outline'])
            asset.unlink()
            patch = {'base_sha256': report['content_sha256'], 'changes': [
                {'block_id': 'after', 'replacement': [{'type': 'paragraph', 'content': '修订后'}]}]}
            revised = base / 'v002'
            revise_document(current, patch, revised)
            self.assertEqual((revised / 'images' / (IMAGE_ID + '.bin')).read_bytes(), image_bytes)
            self.assertEqual(len(Document(revised / 'outline.docx').inline_shapes), 1)

    def test_revision_uses_supplied_assets_for_replacement_image(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            asset = base / 'input.png'
            asset.write_bytes(png(50, 100))
            current = base / 'v001'
            report = render_document(source(), current, image_assets={IMAGE_ID: asset})
            patch = {'base_sha256': report['content_sha256'], 'changes': [
                {'block_id': 'img1', 'replacement': [
                    {'type': 'image', 'image_id': OTHER_ID, 'caption': '新图片'}]}]}
            revised = base / 'v002'
            revise_document(current, patch, revised, image_assets={OTHER_ID: asset})
            self.assertEqual([p.name for p in (revised / 'images').iterdir()], [OTHER_ID + '.bin'])
            self.assertIn('新图片', [p.text for p in Document(revised / 'outline.docx').paragraphs])

    def test_revision_does_not_follow_snapshot_directory_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            asset = base / 'input.png'
            asset.write_bytes(png(50, 100))
            current = base / 'v001'
            report = render_document(source(), current, image_assets={IMAGE_ID: asset})
            outside = base / 'outside'
            (current / 'images').rename(outside)
            (current / 'images').symlink_to(outside, target_is_directory=True)
            patch = {'base_sha256': report['content_sha256'], 'changes': [
                {'block_id': 'after', 'replacement': [{'type': 'paragraph', 'content': '修订后'}]}]}
            with self.assertRaises(ValueError):
                revise_document(current, patch, base / 'v002')
            self.assertFalse((base / 'v002').exists())

    def test_missing_asset_fails_without_publishing_version(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'v001'
            with self.assertRaises(ValueError):
                render_document(source(), output)
            self.assertFalse(output.exists())
            with self.assertRaises(ValueError):
                generate_outline(source()['outline'], Path(folder) / 'outline.docx')
            self.assertFalse((Path(folder) / 'outline.docx').exists())


if __name__ == '__main__':
    unittest.main()
