"""【知识库图片】稳定预览地址、本地原图缓存，以及过期链接的按文档刷新。"""

import copy
import hashlib
import os
import tempfile
import threading
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

from .library import KnowledgeLibrary
from ..tools.images import (
    ImageAssetError, _IMAGE_MARKDOWN, _MAX_BYTES, _MAX_PIXELS,
    _download_bytes, _validate_url, image_catalog,
)


def _snapshot_version(snapshot):
    return hashlib.sha256(str(snapshot.get('synced_at')).encode()).hexdigest()[:16]


def browser_library(snapshot, allowed_origin):
    """仅改写浏览响应；数据库和生成任务仍保留原始来源证据。"""
    result = copy.deepcopy(snapshot)
    version = _snapshot_version(snapshot)
    for document in result.get('documents', []):
        for source in document.get('chunks', []):
            indexes = {item['url']: i for i, item in enumerate(image_catalog([source]))}

            def replace(match):
                url = match['url'].removeprefix('<').removesuffix('>')
                try:
                    _validate_url(url, allowed_origin)
                except ImageAssetError:
                    # 外站普通配图继续由浏览器直接展示，不放宽后端下载的地址范围。
                    return match[0]
                stable = f"/api/library/images/{source['id']}/{indexes[url]}?v={version}"
                start, end = match.span('url')
                return match[0][:start - match.start()] + stable + match[0][end - match.start():]

            source['evidence'] = _IMAGE_MARKDOWN.sub(replace, source.get('evidence', ''))
    return result


def _image_type(blob):
    """保留 WMF/EMF 原始字节，交给现有前端转换器；拒绝非图片响应。"""
    if not blob or len(blob) > _MAX_BYTES:
        raise ImageAssetError('知识库图片为空或超过 8 MiB 限制。')
    if len(blob) >= 22 and (blob[:4] == b'\xd7\xcd\xc6\x9a'
                            or blob[:6] in (b'\x01\x00\x09\x00\x00\x03', b'\x02\x00\x09\x00\x00\x03')):
        return 'image/wmf'
    if len(blob) >= 88 and blob[:4] == b'\x01\x00\x00\x00' and blob[40:44] == b' EMF':
        return 'image/emf'
    try:
        with Image.open(BytesIO(blob)) as raster:
            mime = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'GIF': 'image/gif', 'WEBP': 'image/webp'}.get(raster.format)
            if not mime or not 0 < raster.width * raster.height <= _MAX_PIXELS:
                raise ValueError('unsupported image')
            raster.load()
        return mime
    except Exception:
        raise ImageAssetError('知识库原图无法解码，图片可能损坏或不完整。') from None


def _without_links(evidence):
    return _IMAGE_MARKDOWN.sub(lambda m: f"![{m['alt']}](image)", evidence).strip()


class LibraryImages:
    def __init__(self, settings, library_identity, snapshot_reader, transport=None):
        self.settings = settings
        self.identity = library_identity
        self.snapshot_reader = snapshot_reader
        self.transport = transport
        self.library = KnowledgeLibrary(settings, transport)
        self.directory = Path(settings.data_dir) / 'library-images' / library_identity
        self.locks = [threading.Lock() for _ in range(32)]

    def _fresh_url(self, source, index):
        # FastGPT 的列表接口按所属文档分页，只找当前分块，不做全库同步。
        with httpx.Client(timeout=20, transport=self.transport, trust_env=False) as client:
            for chunk in self.library._pages(client, 'data/list', {'collectionId': source['collection_id']}):
                if chunk.get('_id') != source['hit_id']:
                    continue
                evidence = (chunk.get('q', '') + '\n' + chunk.get('a', '')).strip()
                images = image_catalog([{'id': source['id'], 'evidence': evidence}])
                if (_without_links(evidence) != _without_links(source['evidence'])
                        or index >= len(images)):
                    raise ImageAssetError('分块内容已更新，请同步知识库后查看图片。')
                return images[index]['url']
        raise ImageAssetError('该分块已不存在，请同步知识库后查看图片。')

    def _fetch(self, url):
        _validate_url(url, self.settings.fastgpt_url)
        with httpx.Client(timeout=20, transport=self.transport, follow_redirects=False, trust_env=False) as client:
            blob = _download_bytes(client, url, self.settings.fastgpt_url)
        return blob, _image_type(blob)

    def resolve(self, source_id, index, version=None):
        # 先核对当前目录归属，再访问缓存，避免已删除资料继续通过旧地址访问。
        snapshot = self.snapshot_reader()
        if version is not None and version != _snapshot_version(snapshot):
            raise KeyError('知识库版本已更新，请刷新目录')
        source = next((s for d in snapshot.get('documents', []) for s in d.get('chunks', [])
                       if s.get('id') == source_id), None)
        if source is None or not isinstance(index, int) or index < 0:
            raise KeyError('图片不存在，请刷新知识库目录')
        images = image_catalog([source])
        if index >= len(images):
            raise KeyError('图片不存在，请刷新知识库目录')
        # 同步时间隔离不同版本；临时签名变化不会改变图片在本次快照中的标识。
        key = hashlib.sha256(f"{self.identity}:{snapshot.get('synced_at')}:{source_id}:{index}".encode()).hexdigest()
        path = self.directory / f'{key}.bin'
        with self.locks[int(key[:8], 16) % len(self.locks)]:
            try:
                return path, _image_type(path.read_bytes())
            except (OSError, ImageAssetError):
                pass
            try:
                blob, mime = self._fetch(images[index]['url'])
            except ImageAssetError:
                try:
                    blob, mime = self._fetch(self._fresh_url(source, index))
                except ValueError as exc:
                    raise ImageAssetError(str(exc)) from None
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=self.directory, prefix='.', delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(blob)
                os.replace(temporary, path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            return path, mime
