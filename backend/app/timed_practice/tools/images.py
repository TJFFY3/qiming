"""【图片规则与工具·限时练习】排除模板题源、校验题目图片关联并准备原图快照。"""

import re
from backend.app.shared.tools.images import image_catalog, prepare_image_assets

FORMAT_SOURCE = re.compile(r"模板|格式样例|测试样例|示例|样例")


def question_image_catalog(sources):
    # Templates can describe layout but must not become the question's evidence.
    return image_catalog(
        [
            source
            for source in sources
            if not FORMAT_SOURCE.search(source.get("title", ""))
        ]
    )


def image_blocks(content):
    return [
        {"type": "image", **image}
        for group in ("choice", "written", "optional")
        for question in content.get(group, [])
        for image in question.get("images", [])
    ]


def validate_images(content, sources):
    by_id = {source["id"]: source for source in sources}
    for group in ("choice", "written", "optional"):
        for question in content.get(group, []):
            available = {
                image["image_id"]
                for image in question_image_catalog(
                    [
                        by_id[ref]
                        for ref in question.get("source_ids", [])
                        if ref in by_id
                    ]
                )
            }
            for image in question.get("images", []):
                if image["image_id"] not in available:
                    raise ValueError(
                        "题目图片必须来自该题 source_ids 关联的知识库原图，请使用 image_catalog 中的图片ID"
                    )
                if not image["caption"].strip():
                    raise ValueError("图片说明不能为空白")
                if image["placement"].startswith("option_") and not question.get(
                    "options"
                ):
                    raise ValueError("没有选项的题目不能放置选项图片")


def prepare_images(content, sources, cache_dir, transport=None, allowed_origin=None):
    validate_images(content, sources)
    return prepare_image_assets(
        image_blocks(content),
        sources,
        cache_dir,
        transport=transport,
        allowed_origin=allowed_origin,
    )
