import copy
import json
from pathlib import Path
from zipfile import ZipFile
import httpx
import pytest
from lxml import etree
from fastapi.testclient import TestClient
from backend.app.courseware.tools.export import export_deck
from backend.app.courseware.llm.prompts import messages_for
from backend.tests.test_study_images import png, sources, ID, URL
from backend.tests.test_courseware import deck, app_for, PREFIX


def illustrated():
    raw=deck();raw['slides'][0].update(image_id=ID,image_caption='实验装置原图',paragraphs=['观察装置，讨论实验现象。'])
    return raw


def test_prompt_supplies_source_image_ids_without_urls():
    messages=messages_for({'settings':{}},sources(),'配图')
    context=json.loads(messages[-1]['content'])
    assert context['image_catalog'][0]['image_id']==ID
    assert 'url' not in context['image_catalog'][0]


def test_source_image_is_embedded_and_saved_without_paths_in_public_content(tmp_path):
    raw=illustrated();before=copy.deepcopy(raw)
    content,report=export_deck(raw,tmp_path,True,sources=sources(),image_transport=httpx.MockTransport(lambda _:httpx.Response(200,content=png())))
    assert raw==before and report['passed']
    assert content['slides'][0]['image_id']==ID
    assert str(tmp_path) not in json.dumps(content)
    assert (tmp_path/'images'/f'{ID}.bin').read_bytes()==png()
    with ZipFile(tmp_path/'courseware.pptx') as z:
        root=etree.fromstring(z.read('ppt/slides/slide1.xml'))
        assert root.xpath('//*[local-name()="pic"]')
        assert '实验装置原图' in root.xpath('//*[local-name()="t"]/text()')
        assert any(z.read(n)==png() for n in z.namelist() if n.startswith('ppt/media/'))


def test_revision_reuses_snapshot_offline_and_rejects_unknown_ids(tmp_path):
    first=tmp_path/'v1';first.mkdir()
    export_deck(illustrated(),first,True,sources=sources(),image_transport=httpx.MockTransport(lambda _:httpx.Response(200,content=png())))
    second=tmp_path/'v2';second.mkdir()
    def offline(_):raise AssertionError('must reuse existing image snapshot')
    export_deck(illustrated(),second,True,sources=sources(),previous_images=first/'images',image_transport=httpx.MockTransport(offline))
    assert (second/'images'/f'{ID}.bin').read_bytes()==png()
    bad=illustrated();bad['slides'][0]['image_id']='f'*24
    with pytest.raises(ValueError,match='图片|原图'):
        export_deck(bad,second,True,sources=sources())


def test_image_endpoint_serves_only_referenced_version_snapshots(tmp_path):
    app,_=app_for(tmp_path,[deck()])
    with TestClient(app) as c:
        sid=c.post(PREFIX+'/sessions',json={}).json()['id']
        job=c.post(f'{PREFIX}/sessions/{sid}/generate',json={'prompt':'课件'}).json()
        vid=c.get(PREFIX+'/jobs/'+job['id']).json()['version_id']
        import sqlite3
        with sqlite3.connect(tmp_path/'courseware'/'agent.sqlite') as db:
            v=json.loads(db.execute("select data from records where kind='session' and id=?",(sid,)).fetchone()[0])
            v['versions'][0]['content']['slides'][0]['image_id']=ID
            db.execute("update records set data=? where kind='session' and id=?",(json.dumps(v),sid))
        directory=tmp_path/'courseware'/sid/'versions'/vid/'images';directory.mkdir()
        (directory/f'{ID}.bin').write_bytes(png())
        (directory/('f'*24+'.bin')).write_bytes(png())
        b=f'{PREFIX}/sessions/{sid}/versions/{vid}/images/'
        r=c.get(b+ID)
        assert r.status_code==200 and r.content==png() and r.headers['content-type']=='image/png'
        assert c.get(b+'f'*24).status_code==404


def test_pipeline_exports_images_and_download_failure_does_not_retry_model(tmp_path):
    from types import SimpleNamespace
    from backend.app.config import Settings
    from backend.app.courseware.storage.store import CoursewareStore
    from backend.app.courseware.application.pipeline import CoursewarePipeline
    config=Settings(data_dir=tmp_path)
    config.fastgpt_url='https://cloud.fastgpt.cn';config.fastgpt_key='test';config.datasets=('book',)
    for available in (True,False):
        store=CoursewareStore(tmp_path/str(available)/'agent.sqlite')
        from backend.app.courseware.domain.models import CoursewareSettings
        session=store.create_session(CoursewareSettings().model_dump())
        calls=[]
        class Model:
            def generate_json(self,messages):
                calls.append(messages)
                assert json.loads(messages[-1]['content'])['image_catalog'][0]['image_id']==ID
                return illustrated()
        pipeline=CoursewarePipeline(config,store,SimpleNamespace(search=lambda _:sources()),Model(),image_transport=httpx.MockTransport(lambda _:httpx.Response(200 if available else 503,content=png())))
        job=pipeline.start_generation(session['id'],{'prompt':'使用原图生成课件'})
        pipeline.run(job['id']);done=store.get_job(job['id'])
        assert done['status']==('completed' if available else 'failed'),done
        assert len(calls)==1
        if available:
            v=store.get_session(session['id'])['versions'][0]
            assert v['content']['slides'][0]['image_id']==ID
        else:
            assert '图片' in done['error']
            assert not store.get_session(session['id'])['versions']


def test_image_slides_use_half_width_pagination(tmp_path):
    raw=illustrated();raw['slides'][0]['paragraphs']=['观'*195]
    raw['slides']=raw['slides'][:1]
    content,report=export_deck(raw,tmp_path,True,sources=sources(),image_transport=httpx.MockTransport(lambda _:httpx.Response(200,content=png())))
    assert report['passed'] and len(content['slides'])>1
    assert all(s['image_id']==ID for s in content['slides'])
