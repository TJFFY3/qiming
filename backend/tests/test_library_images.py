"""分块图片使用稳定标识；失效时仅刷新该分块，并可离线复用缓存。"""
import copy
import json
import httpx
import pytest
from backend.app.config import Settings
from backend.app.shared.knowledge.library_images import LibraryImages, browser_library
from backend.app.shared.tools.images import ImageAssetError
from test_study_images import png

OLD='https://kb.test/api/system/file/d/expired'
NEW='https://kb.test/api/system/file/d/fresh'
SID='a'*24


def snapshot():
    return {'synced_at':'2026-11-04', 'documents':[{'chunks':[{'id':SID,'hit_id':'hit','collection_id':'collection', 'evidence':f'正文 ![图]({OLD})'}]}]}


def test_expired_link_refreshes_one_chunk_then_reuses_cached_pixels_offline(tmp_path):
    calls=[]
    def handle(request):
        calls.append(request.url.path)
        if request.method=='POST':
            assert request.headers['authorization']=='Bearer PRIVATE'
            assert json.loads(request.content)['collectionId']=='collection'
            return httpx.Response(200,json={'code':200,'data':{'total':1,'list':[{'_id':'hit','q':f'正文 ![图]({NEW})','a':''}]}})
        assert 'authorization' not in request.headers
        return httpx.Response(500,json={'code':507003}) if request.url.path.endswith('/expired') else httpx.Response(200,content=png())
    s=Settings(data_dir=tmp_path,fastgpt_url='https://kb.test/api',fastgpt_key='PRIVATE')
    images=LibraryImages(s,'library',snapshot,httpx.MockTransport(handle))
    path,mime=images.resolve(SID,0)
    assert path.read_bytes()==png() and mime=='image/png'
    assert calls==['/api/system/file/d/expired','/api/core/dataset/data/list','/api/system/file/d/fresh']
    offline=LibraryImages(s,'library',snapshot,httpx.MockTransport(lambda _:pytest.fail('缓存命中不得再请求FastGPT')))
    assert offline.resolve(SID,0)[0].read_bytes()==png()


def test_browser_urls_stay_stable_without_rewriting_saved_evidence():
    raw=snapshot(); original=copy.deepcopy(raw)
    shown=browser_library(raw, 'https://kb.test/api')
    assert f'/api/library/images/{SID}/0' in shown['documents'][0]['chunks'][0]['evidence']
    assert raw==original
    raw['documents'][0]['chunks'][0]['evidence']=f'正文 ![图]({NEW})'
    assert browser_library(raw, 'https://kb.test/api')['documents']==shown['documents']


def test_preview_url_changes_after_sync_and_old_version_is_rejected(tmp_path):
    import re
    state = snapshot()
    before = browser_library(state, 'https://kb.test/api')['documents'][0]['chunks'][0]['evidence']
    state['synced_at'] = '2026-11-05'
    after = browser_library(state, 'https://kb.test/api')['documents'][0]['chunks'][0]['evidence']
    assert before != after
    version = re.search(r'\?v=([0-9a-f]{16})', before).group(1)
    images = LibraryImages(Settings(data_dir=tmp_path), 'library', lambda: state,
                           httpx.MockTransport(lambda _: pytest.fail('旧版本不得访问网络')))
    with pytest.raises(KeyError):
        images.resolve(SID, 0, version)


def test_external_images_remain_direct_browser_links():
    state = snapshot()
    state['documents'][0]['chunks'][0]['evidence'] += ' ![外链](https://other.test/diagram.png)'
    evidence = browser_library(state, 'https://kb.test/api')['documents'][0]['chunks'][0]['evidence']
    assert '![外链](https://other.test/diagram.png)' in evidence


def test_unknown_source_is_rejected_before_network_or_cache_read(tmp_path):
    images=LibraryImages(Settings(data_dir=tmp_path),'library',snapshot,httpx.MockTransport(lambda _:pytest.fail('不应联网')))
    with pytest.raises(KeyError): images.resolve('b'*24,0)
    with pytest.raises(KeyError): images.resolve(SID,1)


def test_sync_invalidates_pixels_but_corrupt_cache_is_repaired(tmp_path):
    state = snapshot()
    calls = []
    def handle(request):
        calls.append(request.url.path)
        return httpx.Response(200, content=png())
    images = LibraryImages(Settings(data_dir=tmp_path, fastgpt_url='https://kb.test/api'),
                           'library', lambda: state, httpx.MockTransport(handle))
    first, _ = images.resolve(SID, 0)
    first.write_bytes(b'broken')
    assert images.resolve(SID, 0)[0].read_bytes() == png()
    state['synced_at'] = '2026-11-05'
    second, _ = images.resolve(SID, 0)
    assert second != first and len(calls) == 3
    state['documents'] = []
    with pytest.raises(KeyError):
        images.resolve(SID, 0)


def test_changed_chunk_does_not_silently_substitute_a_different_image(tmp_path):
    def handle(request):
        if request.method == 'POST':
            return httpx.Response(200, json={'code':200, 'data':{'total':1, 'list':[
                {'_id':'hit', 'q': f'另一道题 ![图]({NEW})', 'a':''}]}})
        return httpx.Response(500)
    images = LibraryImages(Settings(data_dir=tmp_path, fastgpt_url='https://kb.test/api', fastgpt_key='PRIVATE'),
                           'library', snapshot, httpx.MockTransport(handle))
    with pytest.raises(ImageAssetError, match='内容已更新'):
        images.resolve(SID, 0)
    assert not list(tmp_path.rglob('*.bin'))


@pytest.mark.parametrize('blob,mime', [
    (bytes.fromhex('d7cdc69a') + bytes(18), 'image/wmf'),
    (bytes.fromhex('01000000') + bytes(36) + b' EMF' + bytes(44), 'image/emf'),
])
def test_office_images_are_cached_for_frontend_conversion(tmp_path, blob, mime):
    images = LibraryImages(Settings(data_dir=tmp_path, fastgpt_url='https://kb.test/api'),
                           'library', snapshot, httpx.MockTransport(lambda _: httpx.Response(200, content=blob)))
    path, actual = images.resolve(SID, 0)
    assert path.read_bytes() == blob and actual == mime


def test_external_redirect_is_never_followed_or_cached(tmp_path):
    calls = []
    def handle(request):
        calls.append(request.url.host)
        if request.method == 'POST':
            return httpx.Response(200, json={'code':200, 'data':{'total':1, 'list':[
                {'_id':'hit', 'q':f'正文 ![图]({NEW})', 'a':''}]}})
        return httpx.Response(302, headers={'location':'https://evil.test/steal'})
    images = LibraryImages(Settings(data_dir=tmp_path, fastgpt_url='https://kb.test/api', fastgpt_key='PRIVATE'),
                           'library', snapshot, httpx.MockTransport(handle))
    with pytest.raises(ImageAssetError):
        images.resolve(SID, 0)
    assert set(calls) == {'kb.test'}
    assert not list(tmp_path.rglob('*.bin'))


def test_public_routes_rewrite_both_catalog_responses_and_deliver_pixels(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.study_guide.api.routes import make_router
    from backend.app.study_guide.storage.store import Store
    from backend.app.shared.knowledge.library import KnowledgeLibrary
    s = Settings(data_dir=tmp_path, fastgpt_url='https://kb.test/api')
    store = Store(tmp_path / 'test.sqlite')
    monkeypatch.setattr(KnowledgeLibrary, 'synchronize', lambda _: snapshot()['documents'])
    app = FastAPI()
    app.include_router(make_router(s, store, None))
    client = TestClient(app)
    synced = client.post('/api/library/sync').json()
    from urllib.parse import urlsplit, parse_qs
    stable = synced['documents'][0]['chunks'][0]['evidence'].split('](')[1][:-1]
    assert urlsplit(stable).path == f'/api/library/images/{SID}/0'
    assert len(parse_qs(urlsplit(stable).query)['v'][0]) == 16
    assert client.get('/api/library').json() == synced
    monkeypatch.setattr(LibraryImages, '_fetch', lambda *_: (png(), 'image/png'))
    response = client.get(stable)
    assert response.status_code == 200 and response.content == png()
    assert response.headers['content-type'] == 'image/png'
    assert response.headers['cache-control'] == 'private, no-cache'
    assert response.headers['x-content-type-options'] == 'nosniff'
    with store.connection() as db:
        persisted = json.loads(db.execute('SELECT data FROM library').fetchone()[0])
    assert OLD in persisted['documents'][0]['chunks'][0]['evidence']
