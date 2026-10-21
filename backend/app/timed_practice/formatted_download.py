"""Cache corrected historical practice exports without replacing original versions."""

import hashlib
import json
import os
import tempfile
import threading
from pathlib import Path

from .documents import render
from .equations import format_content

_LOCK = threading.Lock()
FORMAT_VERSION = "practice-chemistry-v5-subscript-markers"


def formatted_artifact(version, kind):
    directory = Path(version["directory"])
    content = format_content(version["content"])
    signature = hashlib.sha256(
        json.dumps(
            [FORMAT_VERSION, content, version["sources"]],
            ensure_ascii=False,
            sort_keys=True,
        ).encode()
    ).hexdigest()
    cache = directory / ".formatted" / signature
    with _LOCK:
        if not cache.is_dir():
            cache.parent.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(dir=cache.parent) as temporary:
                target = Path(temporary) / "artifacts"
                render(content, version["sources"], target, False)
                os.replace(target, cache)
    return cache / (kind + ".docx")
