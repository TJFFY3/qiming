#!/usr/bin/env python3
"""Apply a hash-guarded local block patch to a new outline version."""
import argparse
import copy
import json
from pathlib import Path
import re
import sys

from outline_contract import normalize_outline, outline_digest


def _read_object(path):
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise ValueError(f'{path.name} must contain a JSON object')
    return value


def revise_document(current_dir, patch, output_dir, version='v002'):
    """Replace declared blocks, preserving all other content and source evidence.

    The patch is a JSON object with ``base_sha256`` and ``changes``. Each
    change names an existing ``block_id`` and a nonempty ``replacement`` list.
    The first replacement retains the old ID; further blocks receive stable
    ``<old-id>-2`` IDs (skipping reserved suffixes) unless the caller
    supplies an unused explicit ID.
    """
    current = Path(current_dir).resolve()
    target = Path(output_dir).resolve()
    if target == current or current in target.parents:
        raise ValueError('output directory must be outside the current version')
    if target.exists():
        raise ValueError('output directory already exists; use a new version directory')
    if not isinstance(version, str) or not re.fullmatch(r'v[0-9]{3,}', version):
        raise ValueError('version must have the form v002')
    report = _read_object(current / 'generation_report.json')
    if not report.get('version') or version == report['version']:
        raise ValueError('new version must differ from the current version')
    content = _read_object(current / 'content.json')
    canonical = normalize_outline(content)
    if canonical != content:
        raise ValueError('content.json is not a canonical outline')
    digest = outline_digest(canonical)
    if report.get('content_sha256') != digest:
        raise ValueError('current content does not match the generation report hash')
    source = _read_object(current / 'source_input.json')
    if not isinstance(patch, dict) or set(patch) != {'base_sha256', 'changes'}:
        raise ValueError('patch requires exactly base_sha256 and changes')
    if patch['base_sha256'] != digest:
        raise ValueError('stale patch: base_sha256 does not match the current content')
    changes = patch['changes']
    if not isinstance(changes, list) or not changes:
        raise ValueError('changes must be a nonempty list')
    original_blocks = {block['id']: block for section in canonical['sections']
                       for block in section['blocks']}
    # Reserve every existing ID, including targeted IDs. Reusing a removed
    # block's ID elsewhere would silently change its identity.
    reserved = set(original_blocks) | {section['id'] for section in canonical['sections']}
    replacements = {}
    for change in changes:
        if not isinstance(change, dict) or set(change) != {'block_id', 'replacement'}:
            raise ValueError('each change requires exactly block_id and replacement')
        block_id = change['block_id']
        if not isinstance(block_id, str) or block_id not in original_blocks:
            raise ValueError(f'unknown block_id: {block_id!r}')
        if block_id in replacements:
            raise ValueError(f'duplicate target block_id: {block_id}')
        blocks = change['replacement']
        if not isinstance(blocks, list) or not blocks:
            raise ValueError('replacement must be a nonempty list; deletion is unsupported')
        replacement = []
        for index, raw in enumerate(blocks):
            if not isinstance(raw, dict):
                raise ValueError('each replacement must be a block object')
            block = copy.deepcopy(raw)
            if index == 0:
                if 'id' in block and block['id'] != block_id:
                    raise ValueError('first replacement must retain the target block ID')
                block['id'] = block_id
            else:
                if 'id' in block:
                    new_id = block['id']
                else:
                    suffix = index + 1
                    new_id = f'{block_id}-{suffix}'
                    while new_id in reserved:
                        suffix += 1
                        new_id = f'{block_id}-{suffix}'
                if not isinstance(new_id, str) or not new_id or new_id in reserved:
                    raise ValueError(f'duplicate or invalid replacement ID: {new_id!r}')
                block['id'] = new_id
                reserved.add(new_id)
            replacement.append(block)
        replacements[block_id] = replacement
    revised = copy.deepcopy(canonical)
    for section in revised['sections']:
        section['blocks'] = [new_block for block in section['blocks']
                             for new_block in replacements.get(block['id'], [block])]
    normalized = normalize_outline(revised)
    if normalized != revised:
        raise ValueError('replacement must use canonical block fields')
    # Reconstruct from the original independently of normalization, so it
    # cannot silently alter undeclared blocks or section/top-level metadata.
    for old_section, new_section in zip(canonical['sections'], normalized['sections']):
        old_metadata = {k: v for k, v in old_section.items() if k != 'blocks'}
        new_metadata = {k: v for k, v in new_section.items() if k != 'blocks'}
        if old_metadata != new_metadata:
            raise ValueError('revision changed section metadata')
        for block in new_section['blocks']:
            if block['id'] in original_blocks and block['id'] not in replacements:
                if block != original_blocks[block['id']]:
                    raise ValueError('revision changed an undeclared block')
    data = copy.deepcopy(source)
    data['outline'] = normalized
    previous = {'directory': str(current), 'version': report['version'],
                'content_sha256': digest, 'changes': copy.deepcopy(changes)}
    # Source gaps are inherited from the original evidence; the renderer
    # keeps both the draft marker and source-checking requirements intact.
    draft = 'draft' in str(report.get('status', '')).lower() or report.get('draft') is True
    previous['draft'] = draft
    from render_outline import render_document
    return render_document(data, target, allow_unverified=draft, version=version,
                           previous=previous)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--current', required=True, type=Path)
    parser.add_argument('--patch', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    parser.add_argument('--version', default='v002')
    args = parser.parse_args()
    try:
        report = revise_document(args.current, _read_object(args.patch), args.output_dir,
                                 version=args.version)
    except (ValueError, KeyError, TypeError, OSError) as error:
        print(f'修订失败：{error}', file=sys.stderr)
        return 2
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report.get('files') else 2


if __name__ == '__main__':
    raise SystemExit(main())
