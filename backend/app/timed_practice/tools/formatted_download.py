"""【下载工具·限时练习】缓存历史练习的格式修正导出，保留原始版本。"""

import hashlib
import json
import os
import tempfile
import threading
import shutil
from pathlib import Path

from backend.app.timed_practice.tools.documents import render
from backend.app.timed_practice.domain.equations import format_content
from backend.app.timed_practice.tools.images import prepare_images

_LOCK = threading.Lock()
FORMAT_VERSION = "practice-chemistry-v6-original-images"


def formatted_artifact(version, kind, settings=None):
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
                images = Path(temporary) / "images"
                if (directory / "images").is_dir():
                    shutil.copytree(directory / "images", images)
                assets = prepare_images(
                    content,
                    version["sources"],
                    images,
                    allowed_origin=getattr(settings, "fastgpt_url", "")
                    or "https://cloud.fastgpt.cn",
                )
                render(content, version["sources"], target, False, image_assets=assets)
                os.replace(target, cache)
    return cache / (kind + ".docx")
