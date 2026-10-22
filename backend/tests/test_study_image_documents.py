import copy
import hashlib
import json
import struct
import zlib
from pathlib import Path
from zipfile import ZipFile

import httpx
import pytest
from docx import Document
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.study_guide.tools.documents import DocumentEngine
from backend.app.main import create_app

URL = 'https://cloud.fastgpt.cn/api/system/file/d/test-image'
IMAGE_ID = hashlib.sha256(URL.encode()).hexdigest()[:24]
SAMPLE = json.loads(Path('vendor/chemistry/examples/outline.json').read_text())


def png():
    def chunk(kind, data):
        return struct.pack('!I',len(data))+kind+data+struct.pack('!I',zlib.crc32(kind+data)&0xffffffff)
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('!2I5B',120,80,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+b'\x44\x88\xcc'*120)*80))+chunk(b'IEND',b'')


def payload():
    raw = copy.deepcopy(SAMPLE)
    raw['sources'] = [{'id':'source-image','title':'教材原图','locator':'片段1',
        'category':'textbook','verified':False,'evidence':f'![氢氧化钙性质图]({URL})'}]
    raw['outline']['sections'][0]['blocks'].insert(0,{
        'id':'kb-figure','type':'image','image_id':IMAGE_ID,'caption':'氢氧化钙性质图'})
    return raw


def test_engine_embeds_and_snapshots_only_source_bound_image(tmp_path):
    requests=[]
    def remote(request):
        requests.append(request)
        return httpx.Response(200,content=png(),headers={'content-type':'image/png'})
    engine=DocumentEngine(image_transport=httpx.MockTransport(remote))
    report=engine.render(payload(),tmp_path/'v001','v001',True)
    assert report['statistics']['images']==1
    assert (tmp_path/'v001/images'/f'{IMAGE_ID}.bin').read_bytes()==png()
    assert len(Document(tmp_path/'v001/outline.docx').inline_shapes)==1
    with ZipFile(tmp_path/'v001/outline.docx') as archive:
        assert any(n.startswith('word/media/') for n in archive.namelist())
    assert len(requests)==1


def test_image_revision_preserves_cached_original_when_offline(tmp_path):
    engine=DocumentEngine(image_transport=httpx.MockTransport(lambda r:httpx.Response(200,content=png())))
    report=engine.render(payload(),tmp_path/'v001','v001',True)
    before=(tmp_path/'v001/outline.docx').read_bytes()
    offline=[]
    def remote(request):
        offline.append(request)
        raise httpx.ConnectError('offline')
    engine.image_transport=httpx.MockTransport(remote)
    revised=engine.revise(tmp_path/'v001',{
        'base_sha256':report['content_sha256'],
        'changes':[{'block_id':'question-1','replacement':[{'type':'paragraph','content':'请观察图中物质分类。'}]}]
    },tmp_path/'v002','v002')
    assert revised['statistics']['images']==1
    assert not offline
    assert (tmp_path/'v001/outline.docx').read_bytes()==before
    assert (tmp_path/'v002/images'/f'{IMAGE_ID}.bin').read_bytes()==png()


def test_foreign_image_id_rejected_before_download_or_publication(tmp_path):
    raw=payload();raw['outline']['sections'][0]['blocks'][0]['image_id']='f'*24
    calls=[]
    engine=DocumentEngine(image_transport=httpx.MockTransport(lambda r:calls.append(r)))
    with pytest.raises(ValueError,match='图片|原图'):
        engine.render(raw,tmp_path/'v001','v001',True)
    assert not calls
    assert not (tmp_path/'v001').exists()


def test_version_image_api_serves_only_referenced_snapshot(tmp_path):
    config=Settings(data_dir=tmp_path)
    with TestClient(create_app(config)) as client:
        store=client.app.state.store
        s=store.create_session({})
        job=store.create_job(s['id'],{'kind':'generation','prompt':'生成'})
        vid='image-version';directory=tmp_path/s['id']/'versions'/vid
        engine=DocumentEngine(image_transport=httpx.MockTransport(lambda r:httpx.Response(200,content=png())))
        raw=payload();report=engine.render(raw,directory,'v001',True)
        store.publish(job['id'],{'id':vid,'number':'v001','parent_id':None,'change_kind':'首次生成',
            'created_at':'2026-10-21','content_sha256':report['content_sha256'],
            'content':json.loads((directory/'content.json').read_text()),'sources':raw['sources'],
            'directory':str(directory),'report':report})
        prefix=f"/api/sessions/{s['id']}/versions/{vid}/images/"
        response=client.get(prefix+IMAGE_ID)
        assert response.status_code==200,response.text
        assert response.headers['content-type']=='image/png'
        assert response.content==png()
        (directory/'images'/('e'*24+'.bin')).write_bytes(png())
        assert client.get(prefix+'e'*24).status_code==404
        assert client.get(prefix+'not-an-id').status_code==404


def test_pipeline_sends_original_image_catalog_and_publishes_image(tmp_path):
    from backend.app.study_guide.application.pipeline import Pipeline
    from backend.app.study_guide.storage.store import Store
    raw=payload()
    class Retriever:
        def search(self,q):
            # Image description must survive revision excerpting independently.
            source=copy.deepcopy(raw['sources'][0]);source['evidence']='正文'*600+source['evidence']
            return [source]
    class Model:
        def generate_json(self,messages):
            context=json.loads(messages[1]['content'])
            assert context['image_catalog'][0]['image_id']==IMAGE_ID
            assert '氢氧化钙' in context['image_catalog'][0]['description']
            assert '图片展示' in messages[0]['content']
            return copy.deepcopy(raw)
    store=Store(tmp_path/'test.sqlite');session=store.create_session({})
    engine=DocumentEngine(image_transport=httpx.MockTransport(lambda r:httpx.Response(200,content=png())))
    pipeline=Pipeline(Settings(data_dir=tmp_path),store,Retriever(),Model(),engine)
    job=pipeline.start_generation(session['id'],{'prompt':'结合原图生成导学案'})
    pipeline.run(job['id'])
    done=store.get_job(job['id'])
    assert done['status']=='completed',done
    assert store.get_session(session['id'])['versions'][-1]['report']['statistics']['images']==1


def test_picture_description_placeholder_is_rejected():
    from backend.app.shared.rules.content_quality import check_student_content
    with pytest.raises(ValueError,match='IMAGE_PLACEHOLDER'):
        check_student_content({'outline':{'sections':[{'blocks':[{
            'type':'paragraph','content':'【图片展示·氢氧化钙性质图】中心椭圆框……'}]}]}})


def test_image_download_failure_does_not_retry_model_as_content(tmp_path):
    from backend.app.study_guide.application.pipeline import Pipeline
    from backend.app.study_guide.storage.store import Store
    raw=payload();calls=[]
    class Retriever:
        def search(self,q): return copy.deepcopy(raw['sources'])
    class Model:
        def generate_json(self,messages):
            calls.append(messages)
            return copy.deepcopy(raw)
    store=Store(tmp_path/'test.sqlite');session=store.create_session({})
    engine=DocumentEngine(image_transport=httpx.MockTransport(lambda r:httpx.Response(503)))
    pipeline=Pipeline(Settings(data_dir=tmp_path),store,Retriever(),Model(),engine)
    job=pipeline.start_generation(session['id'],{'prompt':'配图'})
    pipeline.run(job['id']);done=store.get_job(job['id'])
    assert len(calls)==1
    assert done['status']=='failed'
    assert '自动修复' not in done['error']
    assert not store.get_session(session['id'])['versions']


def test_malformed_replacement_is_repaired_instead_of_crashing_image_preflight(tmp_path):
    from backend.app.study_guide.application.pipeline import Pipeline
    from backend.app.study_guide.storage.store import Store
    class Retriever:
        def search(self,q): return copy.deepcopy(payload()['sources'])
    class Model:
        calls=0
        def generate_json(self,messages):
            self.calls+=1
            if self.calls==1: return copy.deepcopy(SAMPLE)
            return {'mode':'patch','changes':[{'block_id':'question-1','replacement':
                ['bad'] if self.calls==2 else [{'type':'paragraph','content':'请根据原图判断物质类别。'}]}]}
    store=Store(tmp_path/'test.sqlite');session=store.create_session({});model=Model()
    pipeline=Pipeline(Settings(data_dir=tmp_path),store,Retriever(),model,DocumentEngine())
    first=pipeline.start_generation(session['id'],{'prompt':'生成'})
    pipeline.run(first['id']);base=store.get_session(session['id'])['versions'][-1]
    job=pipeline.start_revision(session['id'],{'prompt':'修改问题','base_version_id':base['id']})
    pipeline.run(job['id']);done=store.get_job(job['id'])
    assert done['status']=='completed',done
    assert model.calls==3
    assert len(store.get_session(session['id'])['versions'])==2


def test_non_jfif_jpeg_can_be_exported_and_served_from_version_snapshot(tmp_path):
    from io import BytesIO
    from PIL import Image as RasterImage
    stream=BytesIO();RasterImage.new('RGB',(64,48),'#447799').save(stream,format='JPEG')
    original=stream.getvalue();size=int.from_bytes(original[4:6],'big')
    jpeg=original[:2]+original[4+size:]
    engine=DocumentEngine(image_transport=httpx.MockTransport(lambda _:httpx.Response(200,content=jpeg)))
    config=Settings(data_dir=tmp_path)
    with TestClient(create_app(config)) as client:
        store=client.app.state.store;s=store.create_session({})
        job=store.create_job(s['id'],{'kind':'generation','prompt':'生成'})
        vid='jpeg-version';directory=tmp_path/s['id']/'versions'/vid
        report=engine.render(payload(),directory,'v001',True)
        content=json.loads((directory/'content.json').read_text())
        store.publish(job['id'],{'id':vid,'number':'v001','parent_id':None,'change_kind':'首次生成',
            'directory':str(directory),'content':content,'report':report,'content_sha256':report['content_sha256']})
        assert len(Document(directory/'outline.docx').inline_shapes)==1
        response=client.get(f'/api/sessions/{s["id"]}/versions/{vid}/images/{IMAGE_ID}')
        assert response.status_code==200
        assert response.headers['content-type']=='image/png'
        with RasterImage.open(BytesIO(response.content)) as actual:
            assert actual.size==(64,48)
