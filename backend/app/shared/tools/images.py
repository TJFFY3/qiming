"""【图片工具·共享】按来源目录下载原图并缓存本地快照，校验地址、类型与大小。"""

import hashlib
import os
import re
import tempfile
from io import BytesIO
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import httpx
from docx.image.image import Image
from PIL import Image as RasterImage

_MAX_BYTES = 8 * 1024 * 1024
_MAX_PIXELS = 40_000_000
_MAX_IMAGES = 30
_IMAGE_MARKDOWN = re.compile(
    r'!\[(?P<alt>(?:\\.|[^\]\\])*)\]\(\s*'
    r'(?P<url><https?://[^>\r\n]+>|https?://(?:[^\s()]|\([^\s()]*\))+)' 
    r'(?:\s+["\'][^\r\n]*?["\'])?\s*\)', re.IGNORECASE
)


class ImageAssetError(ValueError):
    """Original-image delivery failure; regenerating model content cannot fix it."""


def image_catalog(sources) -> list[dict]:
    """Extract unique original-image URLs from retrieval evidence, in source order."""
    images = []
    seen = set()
    for source in sources:
        evidence = source.get('evidence', '')
        if not isinstance(evidence, str):
            continue
        for match in _IMAGE_MARKDOWN.finditer(evidence):
            url = match['url'].removeprefix('<').removesuffix('>')
            if url in seen:
                continue
            seen.add(url)
            images.append({
                'image_id': hashlib.sha256(url.encode('utf-8')).hexdigest()[:24],
                'source_id': source['id'],
                'description': re.sub(r'\\([\[\]\\])', r'\1', match['alt']),
                'url': url,
            })
    return images


def _validate_url(url: str, allowed_origin: str) -> None:
    try:
        target = urlsplit(url)
        origin = urlsplit(allowed_origin)
        def identity(parsed):
            return (parsed.scheme.lower(), parsed.hostname, parsed.port or
                    {'https': 443, 'http': 80}.get(parsed.scheme.lower()))
        path = unquote(target.path)
        safe = (
            origin.scheme in ('https', 'http') and origin.hostname
            and identity(target) == identity(origin)
            and target.username is None and target.password is None
            and not target.query and not target.fragment
            and path.startswith('/api/system/file/d/')
            and bool(path.removeprefix('/api/system/file/d/'))
            and not any(part in ('.', '..') for part in path.split('/'))
            and '\\' not in path and not any(ord(char) < 32 for char in url)
        )
    except (TypeError, ValueError):
        safe = False
    if not safe:
        raise ImageAssetError('知识库原图地址不受信任，无法获取图片。')


def _normalize_image(blob: bytes) -> bytes:
    """Decode source pixels, keeping compatible originals and fixing Word headers."""
    if not blob or len(blob) > _MAX_BYTES:
        raise ImageAssetError('知识库图片为空或超过 8 MiB 限制。')
    try:
        with RasterImage.open(BytesIO(blob)) as raster:
            if raster.format not in ('PNG', 'JPEG'):
                raise ImageAssetError('知识库图片格式暂不支持，请使用 PNG 或 JPEG 原图。')
            if not (0 < raster.width * raster.height <= _MAX_PIXELS):
                raise ImageAssetError('知识库图片像素超过 4000 万限制。')
            raster.load()  # Metadata alone does not establish a decodable image.
            try:
                Image.from_blob(blob)
                return blob
            except Exception:
                # JPEG need not contain the JFIF/Exif signatures python-docx
                # requires. Lossless PNG preserves the decoded source pixels.
                stream = BytesIO()
                raster.convert('RGB').save(stream, format='PNG')
                normalized = stream.getvalue()
        if len(normalized) > _MAX_BYTES:
            raise ImageAssetError('知识库图片转换后超过 8 MiB 限制。')
        Image.from_blob(normalized)
        return normalized
    except ImageAssetError:
        raise
    except Exception as exc:
        raise ImageAssetError('知识库原图无法解码，图片可能损坏或不完整。') from exc


def _validate_image(blob: bytes) -> None:
    _normalize_image(blob)
    # Cached snapshots must already be usable by Word and all image APIs.
    try:
        Image.from_blob(blob)
    except Exception as exc:
        raise ImageAssetError('知识库图片缓存需要重新转换。') from exc


def _redirect_target(current_url: str, location: str, allowed_origin: str) -> str:
    if not location or any(ord(char) < 32 or ord(char) == 127 for char in location) or "\\" in location:
        raise ImageAssetError('知识库原图重定向地址不受信任。')
    try:
        url = urljoin(current_url, location)
        target = urlsplit(url)
        decoded_path = unquote(target.path)
        if (target.scheme != 'https' or target.username is not None
                or target.password is not None or target.fragment
                or '\\' in decoded_path
                or any(ord(char) < 32 or ord(char) == 127 for char in decoded_path)):
            raise ValueError('unsafe')
        if target.hostname == 'file.fastgpt.cn' and (target.port is None or target.port == 443):
            return url
        _validate_url(url, allowed_origin)
        return url
    except (ValueError, TypeError):
        raise ImageAssetError('知识库原图重定向地址不受信任。') from None


def _download(client: httpx.Client, url: str, allowed_origin: str) -> bytes:
    try:
        for hop in range(4):
            # Each request is anonymous, including redirects back to the same host.
            client.cookies.clear()
            with client.stream('GET', url) as response:
                if response.status_code in (301, 302, 303, 307, 308):
                    if hop == 3:
                        raise ImageAssetError('知识库原图重定向次数超过限制。')
                    url = _redirect_target(url, response.headers.get('location', ''), allowed_origin)
                    continue
                if response.status_code != 200:
                    raise ImageAssetError('知识库原图不可用，无法下载图片。')
                content = bytearray()
                for chunk in response.iter_bytes(chunk_size=64 * 1024):
                    if len(content) + len(chunk) > _MAX_BYTES:
                        raise ImageAssetError('知识库图片超过 8 MiB 限制。')
                    content.extend(chunk)
            blob = bytes(content)
            return _normalize_image(blob)
    except httpx.HTTPError:
        raise ImageAssetError('知识库原图暂时无法获取，请稍后重试。') from None


def prepare_image_assets(blocks, sources, cache_dir, transport=None, allowed_origin=None) -> dict[str, Path]:
    """Resolve referenced source images, reusing validated snapshots when offline."""
    catalog = {item['image_id']: item for item in image_catalog(sources)}
    requested = [block.get('image_id') for block in blocks if block.get('type') == 'image']
    if len(requested) > _MAX_IMAGES:
        raise ImageAssetError('单份资料最多允许 30 张图片。')
    for image_id in requested:
        if not isinstance(image_id, str) or image_id not in catalog:
            raise ValueError('图片未关联到知识库原图，或原图标识缺失。')
        _validate_url(catalog[image_id]['url'], allowed_origin or 'https://cloud.fastgpt.cn')
    if not requested:
        return {}

    directory = Path(cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    assets = {}
    with httpx.Client(transport=transport, timeout=20, follow_redirects=False, trust_env=False) as client:
        for image_id in dict.fromkeys(requested):
            path = directory / f'{image_id}.bin'
            try:
                _validate_image(path.read_bytes())
                assets[image_id] = path
                continue
            except (OSError, ValueError):
                pass
            blob = _download(client, catalog[image_id]['url'], allowed_origin or 'https://cloud.fastgpt.cn')
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(dir=directory, prefix=f'.{image_id}.', delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(blob)
                os.replace(temporary, path)
            finally:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
            assets[image_id] = path
    return assets
