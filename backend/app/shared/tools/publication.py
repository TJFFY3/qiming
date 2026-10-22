"""【发布工具·共享】清理公开 JSON 和 Office 副本中的内部标记。"""

import copy
import hashlib
import os
import re
import tempfile
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

PREFIX = re.compile(
    r"^\s*(?:[（(\[]\s*)?(?:待核验(?:草案)?|待验证(?:草案)?|未核验(?:草案)?)(?:\s*[）)\]])?[\s·：:\-—]*"
)
SUFFIX = re.compile(
    r"\s*(?:[（(\[]\s*(?:待核验(?:草案)?|待验证(?:草案)?|未核验(?:草案)?)\s*[）)\]]|[·：:\-—]\s*(?:待核验(?:草案)?|待验证(?:草案)?|未核验(?:草案)?))\s*$"
)
REVIEW_NOTE = re.compile(
    r"verified\s*=\s*true|未提供已核对|缺少已核实|来源未核实|尚未核验|尚未核对|原内容已标记待核验|待核验|视觉.*待核|来源verified"
)
REVIEW_ONLY = re.compile(
    r"verified\s*=\s*true|^未提供已核对|^缺少已核实|^第\d+题来源未核实|^来源未核实|原内容已标记待核验|^来源verified|^(?:Office|Word|WPS|视觉).*待核"
)


def clean_note(value):
    value = re.sub(r"(?:尚待|尚未|需要|需)?核对", "信息待补充", value)
    value = re.sub(r"待核验(?:草案)?|待验证(?:草案)?|未核验", "", value)
    return re.sub(r"[，；、]\s*$", "", value).strip()


def clean_title(value):
    while True:
        cleaned = SUFFIX.sub("", PREFIX.sub("", value))
        if cleaned == value:
            return cleaned
        value = cleaned


def clean_public(value):
    if isinstance(value, list):
        return [clean_public(item) for item in value]
    if not isinstance(value, dict):
        return copy.deepcopy(value)
    result = {}
    for key, item in value.items():
        if key == "title" and isinstance(item, str):
            result[key] = clean_title(item)
        elif key in (
            "source_issues",
            "source_gaps",
            "source_conflicts",
            "review_required",
            "notes",
        ) and isinstance(item, list):
            result[key] = [
                clean_note(note) if isinstance(note, str) else clean_public(note)
                for note in item
                if not isinstance(note, str)
                or (not REVIEW_ONLY.search(note) and clean_note(note))
            ]
        elif (
            key == "visual_review"
            and isinstance(item, str)
            and REVIEW_NOTE.search(item)
        ):
            result[key] = ""
        elif key == "status" and item in (
            "draft_missing_sources",
            "generated_pending_visual_review",
        ):
            result[key] = "generated"
        elif key == "error" and isinstance(item, str) and REVIEW_NOTE.search(item):
            result[key] = "上次生成未完成，请重试。"
        else:
            result[key] = clean_public(item)
    return result


def _clean_paragraph(nodes):
    text = "".join(node.text or "" for node in nodes)
    left = 0
    while match := PREFIX.match(text[left:]):
        left += match.end()
    remainder = text[left:]
    while suffix := SUFFIX.search(remainder):
        remainder = remainder[: suffix.start()]
    right = len(text) - left - len(remainder)
    changed = bool(left or right)
    for node in nodes:
        value = node.text or ""
        cut = min(left, len(value))
        node.text = value[cut:]
        left -= cut
    for node in reversed(nodes):
        value = node.text or ""
        cut = min(right, len(value))
        node.text = value[: len(value) - cut] if cut else value
        right -= cut
    return changed


def _clean_package(source, target):
    with ZipFile(source) as archive, ZipFile(target, "w") as output:
        for info in archive.infolist():
            data = archive.read(info.filename)
            if info.filename.endswith(".xml") and info.filename.startswith(
                ("word/", "ppt/", "docProps/")
            ):
                parser = etree.XMLParser(
                    resolve_entities=False, load_dtd=False, no_network=True
                )
                root = etree.fromstring(data, parser)
                changed = False
                for paragraph in root.xpath(
                    '//*[local-name()="p" and (namespace-uri()="http://schemas.openxmlformats.org/wordprocessingml/2006/main" or namespace-uri()="http://schemas.openxmlformats.org/drawingml/2006/main")]'
                ):
                    nodes = paragraph.xpath('.//*[local-name()="t"]')
                    changed = _clean_paragraph(nodes) or changed
                for node in root.xpath(
                    '//*[local-name()="title" or local-name()="subject"]'
                ):
                    if node.text:
                        title = clean_title(node.text)
                        changed = changed or title != node.text
                        node.text = title
                if changed:
                    data = etree.tostring(
                        root, xml_declaration=True, encoding="UTF-8", standalone=True
                    )
            output.writestr(info, data)


def clean_office_in_place(path):
    path = Path(path)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, suffix=path.suffix, delete=False
    ) as temporary:
        target = Path(temporary.name)
    try:
        _clean_package(path, target)
        os.replace(target, path)
    finally:
        target.unlink(missing_ok=True)
    return path


def clean_office_download(path):
    path = Path(path)
    stamp = path.stat()
    fingerprint = hashlib.sha256(
        f"{path.name}:{stamp.st_mtime_ns}:{stamp.st_size}:review-labels-v2".encode()
    ).hexdigest()
    directory = path.parent / ".public"
    directory.mkdir(exist_ok=True)
    target = directory / (fingerprint + path.suffix)
    if not target.is_file():
        with tempfile.NamedTemporaryFile(
            dir=directory, suffix=path.suffix, delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
        try:
            _clean_package(path, temporary_path)
            os.replace(temporary_path, target)
        finally:
            temporary_path.unlink(missing_ok=True)
    return target
