#!/usr/bin/env python3
"""Validate DOCX/PPTX packages without Office. Structural checks do not replace visual review.

Usage: validate_outputs.py FILE_OR_DIRECTORY... [--json] [--report report.json]
Exit codes: 0 no issues (inspect warnings), 2 validation issues, 1 invalid input.
"""
import argparse
import json
import os
from pathlib import Path
import posixpath
import re
import sys
import unicodedata
from urllib.parse import unquote, urlsplit
import zipfile
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
NS = {'w': W, 'a': A, 'p': P, 'r': R}


def _record(report, path, location, code, message, warning=False):
    report['warnings' if warning else 'issues'].append({
        'file': str(path), 'location': location, 'code': code, 'message': message})


def _location(part, node=None):
    return part + (':' + node.getroottree().getpath(node) if node is not None else '')


def _scripts(text):
    return any('SUPERSCRIPT' in unicodedata.name(c, '') or
               'SUBSCRIPT' in unicodedata.name(c, '') or c in '⥫⥬' for c in text)


def _rel_source(part):
    if part == '_rels/.rels':
        return ''
    folder, name = posixpath.split(part)
    if posixpath.basename(folder) != '_rels' or not name.endswith('.rels'):
        return None
    return posixpath.join(posixpath.dirname(folder), name[:-5])


def _target(source, target):
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path:
        raise ValueError('internal target must be a package part URI')
    path = unquote(parsed.path)
    resolved = posixpath.normpath(path.lstrip('/') if path.startswith('/') else
                                  posixpath.join(posixpath.dirname(source), path))
    if resolved == '..' or resolved.startswith('../') or '\\' in resolved:
        raise ValueError('target escapes package')
    return resolved


def _relationships(trees, names, emit):
    by_source = {}
    for part, root in trees.items():
        if not part.endswith('.rels'):
            continue
        source = _rel_source(part)
        if source is None:
            emit(part, 'REL_LOCATION', 'Relationship part is not in an OPC _rels directory.')
            continue
        rels = by_source.setdefault(source, {})
        for rel in root:
            if rel.tag != '{%s}Relationship' % PKG:
                continue
            rid = rel.get('Id')
            if not rid or rid in rels:
                emit(_location(part, rel), 'REL_DUPLICATE_ID', 'Relationship Id is absent or duplicated.')
            target = rel.get('Target', '')
            entry = {'type': rel.get('Type', ''), 'target': None}
            if rel.get('TargetMode') != 'External':
                try:
                    entry['target'] = _target(source, target)
                    if entry['target'] not in names:
                        emit(_location(part, rel), 'REL_TARGET_MISSING', f'Internal target does not exist: {target}')
                except ValueError as ex:
                    emit(_location(part, rel), 'REL_TARGET_INVALID', str(ex))
            rels[rid] = entry
    for part, root in trees.items():
        if part.endswith('.rels'):
            continue
        for node in root.iter():
            for attr, rid in node.attrib.items():
                if attr in ('{%s}id' % R, '{%s}embed' % R, '{%s}link' % R):
                    if rid not in by_source.get(part, {}):
                        emit(_location(part, node), 'REL_REFERENCE_MISSING', f'Relationship reference {rid!r} has no definition.')
    return by_source


def _answer_blanks(tree, part, emit):
    for paragraph in tree.iter('{%s}p' % W):
        text_nodes = list(paragraph.iter('{%s}t' % W))
        text = ''.join(node.text or '' for node in text_nodes)
        spans = []
        offset = 0
        for node in text_nodes:
            length = len(node.text or '')
            spans.append((offset, offset + length, node))
            offset += length
        for blank in re.finditer('\u3000{4,}', text):
            before, after = text[:blank.start()], text[blank.end():]
            if not before.strip():
                continue  # Paragraph indentation, including an otherwise empty paragraph.
            if before.rstrip().endswith(('（', '(')) and after.lstrip().startswith(('）', ')')):
                continue  # Empty parentheses in judgment questions.
            for start, end, node in spans:
                if start >= blank.end() or end <= blank.start():
                    continue
                runs = node.xpath('ancestor::w:r', namespaces=NS)
                underline = runs[-1].find('w:rPr/w:u', NS) if runs else None
                if underline is None or underline.get('{%s}val' % W, 'single').lower() in ('none', '0', 'false', 'off'):
                    emit(_location(part, node), 'MISSING_ANSWER_UNDERLINE',
                         'Answer blanks of four or more full-width spaces require explicit run-level underline.')
                    break


def _docx(trees, emit):
    root = trees.get('word/document.xml')
    if root is None:
        emit('word/document.xml', 'DOCX_DOCUMENT_MISSING', 'Missing or unreadable main document.')
        return
    body = root.find('w:body', NS)
    if body is None or body.find('w:sectPr', NS) is None:
        emit('word/document.xml', 'DOCX_SECTION', 'Main body requires a final sectPr page setup.')
    for part, tree in trees.items():
        if not part.startswith('word/'):
            continue
        _answer_blanks(tree, part, emit)
        stack = []
        for node in tree.iter():
            loc = _location(part, node)
            if node.tag == '{%s}t' % W:
                text = node.text or ''
                if _scripts(text):
                    emit(loc, 'UNICODE_SCRIPT', 'Visible text contains Unicode superscript/subscript characters; use native formatting.')
                for keyword in ('注：', '题改为', '（9分，每空'):
                    if keyword in text and not (keyword == '注：' and '注：请在空白区完整写出你的疑惑' in text):
                        emit(loc, 'DOCX_EDIT_RESIDUE', f'Possible editing residue: {keyword}')
            elif node.tag == '{%s}fldChar' % W:
                kind = node.get('{%s}fldCharType' % W)
                if kind == 'begin':
                    stack.append(False)
                elif kind == 'separate':
                    if not stack or stack[-1]:
                        emit(loc, 'DOCX_FIELD_ORDER', 'Field separator has no open instruction or is repeated.')
                    else:
                        stack[-1] = True
                elif kind == 'end':
                    if stack:
                        stack.pop()
                    else:
                        emit(loc, 'DOCX_FIELD_ORDER', 'Field end occurs without a matching begin.')
                else:
                    emit(loc, 'DOCX_FIELD_ORDER', f'Unknown field character type: {kind!r}')
        if stack:
            emit(part, 'DOCX_FIELD_ORDER', f'{len(stack)} unclosed field(s).')
    for section in root.iter('{%s}sectPr' % W):
        size = section.find('w:pgSz', NS)
        try:
            width, height = int(size.get('{%s}w' % W)), int(size.get('{%s}h' % W))
            valid = abs(width - 10431) <= 20 and abs(height - 14740) <= 20
        except (AttributeError, TypeError, ValueError):
            valid = False
        if not valid:
            emit(_location('word/document.xml', section), 'DOCX_PAGE_SIZE', 'Each section requires pgSz near 10431 × 14740 twips (±20).')


def _related(part, suffix, trees, rels):
    for rel in rels.get(part, {}).values():
        if rel['type'].endswith('/' + suffix):
            target = rel['target']
            if target in trees:
                return target, trees[target]
    return None, None


def _placeholder(shape):
    if shape is None:
        return None
    return shape.find('.//p:ph', NS)


def _inherited_shape(root, ph):
    if root is None or ph is None:
        return None
    shapes = root.findall('.//p:sp', NS)
    for shape in shapes:
        candidate = _placeholder(shape)
        if candidate is not None and candidate.get('idx', '0') == ph.get('idx', '0'):
            return shape
    for shape in shapes:
        candidate = _placeholder(shape)
        if candidate is not None and candidate.get('type', 'obj') == ph.get('type', 'obj'):
            return shape
    return None


def _font_size(run, paragraph, shape, inherited, master, presentation):
    props = [run.find('a:rPr', NS), paragraph.find('a:pPr/a:defRPr', NS)]
    ppr = paragraph.find('a:pPr', NS)
    try:
        level = int(ppr.get('lvl', '0')) + 1 if ppr is not None else 1
    except ValueError:
        return None
    level_tag = f'a:lvl{level}pPr/a:defRPr'
    if shape is not None:
        props.append(shape.find('p:txBody/a:lstStyle/' + level_tag, NS))
    for parent in inherited:
        if parent is not None:
            props.extend([parent.find('p:txBody/a:p/a:pPr/a:defRPr', NS),
                          parent.find('p:txBody/a:lstStyle/' + level_tag, NS)])
    ph = _placeholder(shape)
    kind = ph.get('type', 'obj') if ph is not None else 'other'
    style = 'titleStyle' if kind in ('title', 'ctrTitle') else 'bodyStyle' if kind in ('body', 'obj', 'subTitle') else 'otherStyle'
    if master is not None:
        props.append(master.find('p:txStyles/p:' + style + '/' + level_tag, NS))
    if presentation is not None:
        props.append(presentation.find('p:defaultTextStyle/' + level_tag, NS))
    for prop in props:
        if prop is not None and prop.get('sz') is not None:
            try:
                return int(prop.get('sz'))
            except ValueError:
                return None
    return None


def _pptx(trees, names, rels, emit):
    slides = {n for n in names if re.fullmatch(r'ppt/slides/[^/]+\.xml', n)}
    content = trees.get('[Content_Types].xml')
    overrides = set()
    if content is not None:
        for node in content.findall('{%s}Override' % CT):
            if node.get('ContentType', '').endswith('presentationml.slide+xml'):
                overrides.add(node.get('PartName', '').lstrip('/'))
    if overrides != slides or content is None:
        emit('[Content_Types].xml', 'PPT_CONTENT_TYPES', 'Slide content-type overrides must match the slide parts exactly.')
    presentation = trees.get('ppt/presentation.xml')
    canvas = None
    if presentation is not None:
        size = presentation.find('p:sldSz', NS)
        try:
            canvas = (int(size.get('cx')), int(size.get('cy')))
            if min(canvas) <= 0:
                raise ValueError('nonpositive canvas')
        except (AttributeError, ValueError, TypeError):
            canvas = None
        referenced = []
        for node in presentation.findall('p:sldIdLst/p:sldId', NS):
            rel = rels.get('ppt/presentation.xml', {}).get(node.get('{%s}id' % R))
            if rel:
                if not rel['type'].endswith('/slide') or rel['target'] not in slides:
                    emit('ppt/presentation.xml', 'PPT_SLIDE_REFERENCE', 'Presentation slide reference does not resolve to a slide part.')
                referenced.append(rel['target'])
        if set(referenced) != slides or len(referenced) != len(set(referenced)):
            emit('ppt/presentation.xml', 'PPT_SLIDE_REFERENCE', 'Presentation slide list must reference every slide exactly once.')
    if canvas is None:
        emit('ppt/presentation.xml', 'PPT_CANVAS', 'Missing or invalid presentation sldSz canvas.')
    for part in sorted(slides):
        root = trees.get(part)
        if root is None:
            continue
        _, layout = _related(part, 'slideLayout', trees, rels)
        layout_part, _ = _related(part, 'slideLayout', trees, rels)
        _, master = _related(layout_part, 'slideMaster', trees, rels)
        for xf in root.xpath('.//a:xfrm | .//p:xfrm', namespaces=NS):
            loc = _location(part, xf)
            offs, exts = xf.findall('a:off', NS), xf.findall('a:ext', NS)
            try:
                if len(offs) != 1 or len(exts) != 1:
                    raise ValueError('Transform requires exactly one off and one ext.')
                x, y = int(offs[0].get('x')), int(offs[0].get('y'))
                width, height = int(exts[0].get('cx')), int(exts[0].get('cy'))
                if min(width, height) < 0:
                    raise ValueError('Transform extents must be nonnegative.')
            except (ValueError, TypeError) as ex:
                emit(loc, 'PPT_TRANSFORM', str(ex))
                continue
            # Group children are in a separate coordinate system: report this limit.
            groups = xf.xpath('ancestor::p:grpSp', namespaces=NS)
            if groups or xf.get('rot') not in (None, '0'):
                emit(loc, 'PPT_GEOMETRY_UNSUPPORTED', 'Grouped or rotated geometry requires visual bounds review.', True)
                continue
            if canvas and (x < -18000 or y < -18000 or x + width > canvas[0] + 18000 or y + height > canvas[1] + 18000):
                emit(loc, 'PPT_BOUNDS', f'Shape extends beyond slide canvas {canvas[0]} × {canvas[1]} EMU.')
        for text in root.iter('{%s}t' % A):
            if not text.text:
                continue
            loc = _location(part, text)
            if _scripts(text.text):
                emit(loc, 'UNICODE_SCRIPT', 'Visible text contains Unicode superscript/subscript characters; use native formatting.')
            run = text.getparent()
            paragraph = run.getparent()
            shapes = text.xpath('ancestor::p:sp', namespaces=NS)
            shape = shapes[-1] if shapes else None
            layout_shape = _inherited_shape(layout, _placeholder(shape))
            master_shape = _inherited_shape(master, _placeholder(layout_shape) if layout_shape is not None else _placeholder(shape))
            size = _font_size(run, paragraph, shape, [layout_shape, master_shape], master, presentation)
            if size is None:
                emit(loc, 'PPT_FONT_UNRESOLVED', 'Font size inheritance could not be resolved; verify ≥24 pt visually.', True)
            elif size < 2400:
                emit(loc, 'PPT_FONT_SMALL', f'Visible text is {size / 100:g} pt; teaching slide text requires ≥24 pt.')
        for node in root.xpath('.//p:graphicFrame/a:graphic/a:graphicData', namespaces=NS):
            if not node.findall('{http://schemas.openxmlformats.org/drawingml/2006/table}tbl') and not node.findall('a:tbl', NS):
                emit(_location(part, node), 'PPT_CONTENT_UNSUPPORTED', 'Chart/SmartArt/OLE content requires separate visual and text review.', True)


def _validate_file(path, report):
    def emit(location, code, message, warning=False):
        _record(report, path, location, code, message, warning)
    try:
        with zipfile.ZipFile(path) as package:
            names = package.namelist()
            if len(names) != len(set(names)):
                emit('', 'PACKAGE_DUPLICATE_PART', 'ZIP contains duplicate part names.')
            trees = {}
            for name in names:
                if not name.endswith(('.xml', '.rels')):
                    continue
                try:
                    parser = etree.XMLParser(resolve_entities=False, load_dtd=False, no_network=True, recover=False, huge_tree=False)
                    tree = etree.fromstring(package.read(name), parser=parser)
                    if tree.getroottree().docinfo.doctype:
                        emit(name, 'XML_DTD', 'DTD declarations are unsupported and never resolved.')
                        continue
                    trees[name] = tree
                except (etree.XMLSyntaxError, ValueError, KeyError, RuntimeError) as ex:
                    emit(name, 'XML_PARSE', f'XML parsing failed: {ex}')
            rels = _relationships(trees, set(names), emit)
            if path.suffix.lower() == '.docx':
                _docx(trees, emit)
            else:
                _pptx(trees, set(names), rels, emit)
    except (OSError, zipfile.BadZipFile, RuntimeError, EOFError, NotImplementedError) as ex:
        emit('', 'PACKAGE_READ', f'Cannot read Office ZIP package: {ex}')


def validate_paths(paths):
    """Return a deterministic structured validation report; never ignore missing inputs."""
    report = {'passed': False, 'checked_files': 0, 'issues': [], 'warnings': []}
    files = set()
    for raw in paths:
        path = Path(raw).expanduser().absolute()
        if not path.exists():
            _record(report, path, '', 'INPUT_NOT_FOUND', 'Input path does not exist.')
        elif path.is_dir():
            for folder, dirs, names in os.walk(path):
                dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
                for name in names:
                    candidate = Path(folder) / name
                    if not name.startswith('.') and candidate.suffix.lower() in ('.docx', '.pptx'):
                        files.add(candidate.resolve())
        elif path.is_file() and path.suffix.lower() in ('.docx', '.pptx'):
            files.add(path.resolve())
        else:
            _record(report, path, '', 'INPUT_UNSUPPORTED', 'Expected a DOCX/PPTX file or directory.')
    if not files:
        _record(report, '', '', 'NO_FILES', 'No DOCX or PPTX files found.')
    for path in sorted(files):
        report['checked_files'] += 1
        _validate_file(path, report)
    report['passed'] = not report['issues']
    return report


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, f'{self.prog}: error: {message}\n')


def main(argv=None):
    parser = _ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='*', help='DOCX/PPTX files or folders (recursive)')
    parser.add_argument('--json', action='store_true', help='Print machine-readable JSON')
    parser.add_argument('--report', type=Path, help='Also save the JSON report to this path')
    args = parser.parse_args(argv)
    result = validate_paths(args.paths)
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        try:
            args.report.write_text(serialized + '\n', encoding='utf-8')
        except OSError as ex:
            print(f'Cannot write report: {ex}', file=sys.stderr)
            return 1
    if args.json:
        print(serialized)
    else:
        print(f"{'PASS' if result['passed'] else 'FAIL'}: {result['checked_files']} file(s), {len(result['issues'])} issue(s), {len(result['warnings'])} warning(s)")
        for kind in ('issues', 'warnings'):
            for item in result[kind]:
                print(f"[{kind.upper()} {item['code']}] {item['file']} {item['location']}: {item['message']}")
        if result['warnings']:
            print('Warnings require review; structural validation does not certify visual layout.')
    if any(i['code'].startswith('INPUT_') or i['code'] == 'NO_FILES' for i in result['issues']):
        return 1
    return 0 if result['passed'] else 2


if __name__ == '__main__':
    sys.exit(main())
