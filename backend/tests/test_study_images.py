import hashlib
import struct
import zlib

import httpx
import pytest

from backend.app.study_guide.tools import images as study_images

URL = 'https://cloud.fastgpt.cn/api/system/file/d/original'
ID = hashlib.sha256(URL.encode()).hexdigest()[:24]


def png(width=2, height=2):
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress((b'\0' + b'\xff\0\0' * 2) * 2)) + chunk(b'IEND', b''))


def sources(url=URL):
    return [{'id': 's1', 'evidence': f'正文 ![性质图]({url})'}]


def blocks(image_id=ID):
    return [{'type': 'paragraph', 'content': '正文'}, {'type': 'image', 'image_id': image_id}]


def test_catalog_extracts_actual_urls_and_deduplicates():
    assert study_images.image_catalog(sources() + sources()) == [
        {'image_id': ID, 'source_id': 's1', 'description': '性质图', 'url': URL}]
    assert study_images.image_catalog([{'id': 's', 'evidence': 'https://example.com/a.png'}]) == []


def test_downloads_required_original_and_reuses_valid_cache_offline(tmp_path):
    requests = []
    def handle(request):
        requests.append(request)
        assert 'authorization' not in request.headers
        assert request.extensions['timeout']['read'] == 20
        return httpx.Response(200, content=png(), headers={'content-type': 'image/png'})
    result = study_images.prepare_image_assets(blocks(), sources(), tmp_path, httpx.MockTransport(handle))
    assert result == {ID: tmp_path / f'{ID}.bin'}
    assert result[ID].read_bytes() == png()
    assert len(requests) == 1
    offline = httpx.MockTransport(lambda _: pytest.fail('valid cache should work offline'))
    assert study_images.prepare_image_assets(blocks(), sources(), tmp_path, offline) == result
    assert sorted(p.name for p in tmp_path.iterdir()) == [f'{ID}.bin']


def test_unknown_id_cannot_use_existing_cache(tmp_path):
    (tmp_path / ('f' * 24 + '.bin')).write_bytes(png())
    with pytest.raises(ValueError, match='图片|原图'):
        study_images.prepare_image_assets(blocks('f' * 24), sources(), tmp_path)


@pytest.mark.parametrize('url', [
    'http://cloud.fastgpt.cn/api/system/file/d/x',
    'https://evil.test/api/system/file/d/x',
    'https://cloud.fastgpt.cn:444/api/system/file/d/x',
    'https://secret@cloud.fastgpt.cn/api/system/file/d/x',
    'https://cloud.fastgpt.cn/api/system/file/d/x?token=secret',
    'https://cloud.fastgpt.cn/api/system/file/d/x#fragment',
    'https://cloud.fastgpt.cn/other/x',
    'https://cloud.fastgpt.cn/api/system/file/d/../../private',
])
def test_untrusted_source_url_rejected_before_fetch(tmp_path, url):
    image_id = hashlib.sha256(url.encode()).hexdigest()[:24]
    with pytest.raises(ValueError, match='图片|原图'):
        study_images.prepare_image_assets(blocks(image_id), sources(url), tmp_path,
            httpx.MockTransport(lambda _: pytest.fail('unsafe URL must not be fetched')))


def test_explicit_origin_and_only_required_images(tmp_path):
    url = 'https://kb.test:8443/api/system/file/d/x'
    image_id = hashlib.sha256(url.encode()).hexdigest()[:24]
    transport = httpx.MockTransport(lambda request: httpx.Response(200, content=png()))
    result = study_images.prepare_image_assets(blocks(image_id), sources(url) + sources(), tmp_path,
        transport, allowed_origin='https://kb.test:8443')
    assert set(result) == {image_id}
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize('response', [
    httpx.Response(302, headers={'location': URL}),
    httpx.Response(404, content=b'missing'),
    httpx.Response(200, content=b'<html>not an image</html>'),
    httpx.Response(200, content=png(10000, 10000)),
    httpx.Response(200, content=b'x' * (8 * 1024 * 1024 + 1)),
])
def test_bad_response_leaves_no_cache(tmp_path, response):
    with pytest.raises(ValueError, match='图片|原图'):
        study_images.prepare_image_assets(blocks(), sources(), tmp_path,
            httpx.MockTransport(lambda _: response))
    assert not list(tmp_path.glob('*.bin'))


def test_unavailable_image_is_clear_error_without_credentials(tmp_path):
    def offline(request):
        raise httpx.ConnectError('secret credentials')
    with pytest.raises(ValueError, match='图片|原图') as exc:
        study_images.prepare_image_assets(blocks(), sources(), tmp_path, httpx.MockTransport(offline))
    assert 'secret' not in str(exc.value)


def test_corrupt_cache_is_replaced_by_valid_original(tmp_path):
    (tmp_path / f'{ID}.bin').write_bytes(b'bad')
    result = study_images.prepare_image_assets(blocks(), sources(), tmp_path,
        httpx.MockTransport(lambda _: httpx.Response(200, content=png())))
    assert result[ID].read_bytes() == png()


def test_document_image_limit_checked_before_fetch(tmp_path):
    urls = [URL + str(i) for i in range(31)]
    ids = [hashlib.sha256(url.encode()).hexdigest()[:24] for url in urls]
    with pytest.raises(ValueError, match='图片|原图'):
        study_images.prepare_image_assets([{'type': 'image', 'image_id': value} for value in ids],
            [s for url in urls for s in sources(url)], tmp_path,
            httpx.MockTransport(lambda _: pytest.fail('limit must be checked before fetching')))


def test_trusted_cdn_redirect_accepts_signed_query_without_forwarding_credentials(tmp_path):
    calls = []
    cdn = 'https://file.fastgpt.cn/bucket/dataset/parsed/image.png?X-Amz-Signature=secret'
    def handle(request):
        calls.append(request)
        assert 'authorization' not in request.headers
        assert 'cookie' not in request.headers
        if len(calls) == 1:
            return httpx.Response(302, headers={'location': cdn, 'set-cookie': 'session=secret; Domain=.fastgpt.cn; Path=/'})
        assert str(request.url) == cdn
        return httpx.Response(200, content=png())
    result = study_images.prepare_image_assets(blocks(), sources(), tmp_path, httpx.MockTransport(handle))
    assert result[ID].read_bytes() == png()
    assert len(calls) == 2


@pytest.mark.parametrize('target', [
    'https://evil.test/image.png', 'https://127.0.0.1/image.png',
    'http://file.fastgpt.cn/image.png', 'https://file.fastgpt.cn:444/image.png',
    'https://secret@file.fastgpt.cn/image.png', 'https://file.fastgpt.cn/image.png#fragment',
    'https://file.fastgpt.cn\\evil/image.png', 'https://cloud.fastgpt.cn/private',
])
def test_untrusted_redirect_is_download_error_before_next_request(tmp_path, target):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(302, headers={'location': target})
    with pytest.raises(study_images.ImageAssetError, match='图片|原图'):
        study_images.prepare_image_assets(blocks(), sources(), tmp_path, httpx.MockTransport(handle))
    assert len(calls) == 1


def test_redirect_loop_stops_after_three_hops(tmp_path):
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(302, headers={'location': '/api/system/file/d/loop'})
    with pytest.raises(study_images.ImageAssetError, match='图片|原图'):
        study_images.prepare_image_assets(blocks(), sources(), tmp_path, httpx.MockTransport(handle))
    assert len(calls) == 4


def test_same_origin_original_path_redirect_works(tmp_path):
    calls = []
    def handle(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(307, headers={'location': '/api/system/file/d/second'})
        return httpx.Response(200, content=png())
    assert study_images.prepare_image_assets(blocks(), sources(), tmp_path,
        httpx.MockTransport(handle))[ID].read_bytes() == png()


@pytest.mark.parametrize('body', [b'not-image', b'x' * (8 * 1024 * 1024 + 1)], ids=['non-image', 'oversize'])
def test_download_failures_have_distinct_error_type(tmp_path, body):
    with pytest.raises(study_images.ImageAssetError):
        study_images.prepare_image_assets(blocks(), sources(), tmp_path,
            httpx.MockTransport(lambda _: httpx.Response(200, content=body)))
    with pytest.raises(ValueError) as exc:
        study_images.prepare_image_assets(blocks('f' * 24), sources(), tmp_path)
    assert not isinstance(exc.value, study_images.ImageAssetError)


def jpeg_without_app_marker():
    from io import BytesIO
    from PIL import Image
    stream = BytesIO()
    Image.new('RGB', (64, 48), '#447799').save(stream, format='JPEG')
    original = stream.getvalue()
    assert original[2:4] == b'\xff\xe0'
    length = int.from_bytes(original[4:6], 'big')
    return original[:2] + original[4 + length:]


def test_valid_jpeg_without_jfif_marker_is_normalized_for_word_and_cached(tmp_path):
    from docx.image.image import Image
    from docx import Document
    raw = jpeg_without_app_marker()
    with pytest.raises(Exception):
        Image.from_blob(raw)  # Same signature mismatch as the actual knowledge base.
    result = study_images.prepare_image_assets(blocks(), sources(), tmp_path,
        httpx.MockTransport(lambda _: httpx.Response(200, content=raw)))
    cached = result[ID].read_bytes()
    assert Image.from_blob(cached).content_type == 'image/png'
    assert (Image.from_blob(cached).px_width, Image.from_blob(cached).px_height) == (64, 48)
    doc = Document();doc.add_picture(str(result[ID]));doc.save(tmp_path/'test.docx')
    assert study_images.prepare_image_assets(blocks(), sources(), tmp_path,
        httpx.MockTransport(lambda _: pytest.fail('canonical cache works offline'))) == result


def test_header_only_png_is_rejected_before_caching(tmp_path):
    # A plausible IHDR passes python-docx metadata parsing but has no pixel data.
    truncated = png()[:33] + png()[-12:]
    with pytest.raises(study_images.ImageAssetError):
        study_images.prepare_image_assets(blocks(), sources(), tmp_path,
            httpx.MockTransport(lambda _: httpx.Response(200, content=truncated)))
    assert not list(tmp_path.glob('*.bin'))
