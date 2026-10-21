"""Format archived serialized equations in a copy, preserving historical text."""

import hashlib
import json
import os
import tempfile
import threading

from ..serialized_rich import START
from .equations import normalize_deck
from .export import export_deck

_LOCK = threading.Lock()


def has_serialized(content):
    return any(
        START.search(p if isinstance(p, str) else "".join(r["text"] for r in p))
        for slide in content["slides"] for p in slide["paragraphs"]
    )


def display_content(content):
    # Read compatibility does not change the archived chemical coefficients.
    return normalize_deck(content, check_balance=False) if has_serialized(content) else content


def formatted_artifact(version, path):
    if not has_serialized(version["content"]):
        return path
    content = display_content(version["content"])
    key = hashlib.sha256(json.dumps(["serialized-ppt-v2", content], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    cache = path.parent / ".formatted" / key
    with _LOCK:
        if not cache.is_dir():
            cache.parent.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=cache.parent) as temporary:
                from pathlib import Path
                directory = Path(temporary) / "artifacts"
                directory.mkdir()
                # Typography-only repair of an already archived version. New
                # generation still uses the full chemistry validation path.
                export_deck(content, directory, False, paginate=False, check_balance=False)
                os.replace(directory, cache)
    return cache / "courseware.pptx"
