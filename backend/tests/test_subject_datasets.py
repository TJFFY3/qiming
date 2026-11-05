import json
import httpx
import pytest
from backend.app.shared.workflow.client import WorkflowClient
from test_workflow_client import settings, task


@pytest.mark.parametrize('category',['导学案','互动课件','限时练习'])
def test_workflow_routes_only_selected_subject_dataset(category):
    def handle(request):
        body=json.loads(request.content)
        if request.url.path.endswith('/dataset/list'):
            return httpx.Response(200,json={'code':200,'data':[
                {'_id':'chem','name':'化学教材','type':'dataset'},
                {'_id':'math','name':'数学教材','type':'dataset'}]})
        assert body['variables']['subject']=='数学'
        assert body['variables']['datasetIds']==[{'datasetId':'math'}]
        assert '数学' in body['variables']['repoSearchInfo']
        assert body['variables']['dynamicPromot'] == ''
        return httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}]})
    config=settings();config.datasets=[{'id':'root','type':'folder'}]
    WorkflowClient(config,httpx.MockTransport(handle)).generate_task([],**(task()|{
        'agent_category':category,'teacher_settings':{'subject':'数学','chapter':'集合'}}))


def test_subject_folder_label_survives_neutral_dataset_name():
    from backend.app.shared.workflow.datasets import expand_datasets
    from backend.app.shared.knowledge.subjects import select_subject_datasets
    def handle(request):
        parent=json.loads(request.content)['parentId']
        data=[{'_id':'math-folder','type':'folder','name':'数学'}] if parent=='root' else [{'_id':'book','type':'dataset','name':'必修第一册'}]
        return httpx.Response(200,json={'code':200,'data':data})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        datasets=expand_datasets(client,'https://workflow.test/api','KEY',[{'id':'root','type':'folder'}])
    assert select_subject_datasets(datasets,'数学')[0]['id']=='book'
    with pytest.raises(ValueError,match='化学'):
        select_subject_datasets(datasets,'化学')


def test_library_documents_keep_subject_and_dataset_hierarchy():
    from backend.app.shared.knowledge.library import KnowledgeLibrary
    def handle(request):
        path=request.url.path
        if path.endswith('/dataset/list'):
            parent=json.loads(request.content)['parentId']
            data=[{'_id':'folder','type':'folder','name':'数学'}] if parent=='root' else [{'_id':'math','type':'dataset','name':'必修第一册'}]
        elif path.endswith('/collection/listV2'):
            data={'list':[{'_id':'file','name':'集合.pdf','type':'file'}],'total':1}
        else: data={'list':[{'_id':'chunk','q':'集合','a':'元素','chunkIndex':0}],'total':1}
        return httpx.Response(200,json={'code':200,'data':data})
    config=settings();config.datasets=[{'id':'root','type':'folder'}];config.timeout=30
    docs=KnowledgeLibrary(config,httpx.MockTransport(handle)).synchronize()
    assert docs[0]['subject']=='数学'
    assert docs[0]['dataset_id']=='math'
    assert docs[0]['dataset_name']=='必修第一册'


def test_unlabelled_legacy_datasets_cannot_be_used_for_other_subjects():
    from backend.app.shared.knowledge.subjects import select_subject_datasets
    with pytest.raises(ValueError,match='数学'):
        select_subject_datasets([{'id':'legacy','name':'教学资料'}],'数学')


def test_selected_subject_limit_is_not_shared_with_other_subjects():
    def handle(request):
        body=json.loads(request.content)
        if request.url.path.endswith('/dataset/list'):
            data=[{'_id':'math','type':'dataset','name':'数学教材'}]+[
                {'_id':f'chem{i}','type':'dataset','name':f'化学教材{i}'} for i in range(31)]
            return httpx.Response(200,json={'code':200,'data':data})
        assert body['variables']['datasetIds']==[{'datasetId':'math'}]
        return httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}]})
    config=settings();config.datasets=[{'id':'root','type':'folder'}]
    WorkflowClient(config,httpx.MockTransport(handle)).generate_task([],**(task()|{
        'teacher_settings':{'subject':'数学','chapter':'集合'}}))


def test_chapters_are_read_from_selected_subject_file_titles_without_chunk_search():
    from backend.app.shared.knowledge.library import KnowledgeLibrary
    def handle(request):
        body=json.loads(request.content)
        if request.url.path.endswith('/dataset/list'):
            data=[{'_id':'chem','name':'化学教材','type':'dataset'}, {'_id':'math','name':'数学教材','type':'dataset'}]
        else:
            assert request.url.path.endswith('/collection/listV2')
            assert body['datasetId']=='chem'
            data={'total':2,'list':[{'_id':'f1','name':'化学 第一章 物质及其变化.pdf','type':'file'}, {'_id':'f2','name':'化学 第二章 海水中的重要元素——钠和氯.docx','type':'file'}]}
        return httpx.Response(200,json={'code':200,'data':data})
    config=settings();config.datasets=[{'id':'root','type':'folder'}];config.timeout=30
    assert KnowledgeLibrary(config,httpx.MockTransport(handle)).chapters('化学') == ['第一章 物质及其变化','第二章 海水中的重要元素——钠和氯']


def test_chapter_options_use_the_same_snapshot_as_the_library_browser(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.app.config import Settings
    from backend.app.study_guide.storage.store import Store
    from backend.app.study_guide.api.routes import make_router
    from backend.app.shared.knowledge.library import KnowledgeLibrary
    documents = [
        {'id':'c1','subject':'化学','dataset_id':'chem','dataset_name':'化学教材','title':'化学 第一章 物质及其变化.pdf','chunks':[]},
        {'id':'c2','subject':'化学','dataset_id':'chem','dataset_name':'化学教材','title':'化学 第一章 物质及其变化.pptx','chunks':[]},
        {'id':'m1','subject':'数学','dataset_id':'math','dataset_name':'数学教材','title':'数学 第一章 集合.pdf','chunks':[]},
    ]
    monkeypatch.setattr(KnowledgeLibrary, 'synchronize', lambda _:documents)
    monkeypatch.setattr(KnowledgeLibrary, 'chapters', lambda *_:pytest.fail('已有浏览快照时不应另查远端目录'))
    config = Settings(data_dir=tmp_path)
    app = FastAPI()
    app.include_router(make_router(config, Store(tmp_path/'test.sqlite'), None))
    client = TestClient(app)
    client.post('/api/library/sync').raise_for_status()
    assert client.get('/api/library/chapters?subject=化学').json()['chapters'] == ['第一章 物质及其变化']
    assert client.get('/api/library/chapters?subject=数学').json()['chapters'] == ['第一章 集合']
    assert client.get('/api/library/chapters?subject=物理').json()['chapters'] == []
    documents[:] = [dict(documents[0], title='化学 第二章 钠和氯.pdf')]
    client.post('/api/library/sync').raise_for_status()
    assert client.get('/api/library/chapters?subject=化学').json()['chapters'] == ['第二章 钠和氯']
