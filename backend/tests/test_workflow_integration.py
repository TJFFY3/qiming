"""真实应用、三套流程和文件导出；只用 MockTransport 替换工作流服务。"""
import copy
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.shared.workflow.client import WorkflowClient, WORKFLOW_APP_ID
from test_courseware import deck
from test_timed_practice import paper, settings as practice_settings


@pytest.mark.parametrize('category,prefix', [
    ('导学案','/api'), ('互动课件','/api/courseware'), ('限时练习','/api/timed-practice'),
])
def test_default_app_generates_and_revises_via_workflow_only(tmp_path, monkeypatch, category, prefix):
    calls=[]
    guide=json.loads(Path('vendor/chemistry/examples/outline.json').read_text())
    def handle(request):
        assert request.url.path=='/api/v1/chat/completions', '不得调用本地知识库预检索接口'
        payload=json.loads(request.content); calls.append(payload)
        assert payload['appId']==WORKFLOW_APP_ID
        v=payload['variables']; assert v['agentCategory']==category
        assert 'repoSearchInfo' in v and '氧化还原反应' in v['repoSearchInfo']
        assert v['dynamicPromot'].startswith('四、化学表达')
        assert '氧化还原反应' not in v['dynamicPromot']
        if category=='导学案':
            content=copy.deepcopy(guide)
            if v['operation']=='微调':
                content={'mode':'patch','changes':[{'block_id':'question-1','replacement':[{'type':'paragraph','content':'请比较反应前后化合价并说明判断依据。'}]}]}
        elif category=='互动课件':
            content=deck()
            if v['operation']=='微调':
                slide=copy.deepcopy(content['slides'][1]); slide['paragraphs'].append('比较电子得失。')
                content={'mode':'patch','changes':[{'page':2,'slide':slide}]}
        else:
            content=paper()
            if v['operation']=='微调': content['choice'][0]['explanation']='比较化合价升降，判断电子转移。'
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(content,ensure_ascii=False)}}],
            'responseData':[{'quoteList':[{'id':'s1','datasetId':'dataset','collectionId':'book','sourceName':'教材',
                                         'q':'氧化还原反应','a':'比较元素反应前后的化合价，分析电子转移。'}]}]})
    mock=httpx.MockTransport(handle)
    original=WorkflowClient.__init__
    monkeypatch.setattr(WorkflowClient,'__init__',lambda self,s,transport=None:original(self,s,mock))
    config=Settings(data_dir=tmp_path,fastgpt_url='https://workflow.test',fastgpt_key='KEY',
                    datasets=[{'id':'dataset'}])
    with TestClient(create_app(config)) as client:
        response=client.post(prefix+'/sessions',json=practice_settings() if category=='限时练习' else {"chapter":"第三节 氧化还原反应"})
        sid=response.json()['id']
        first=client.post(f'{prefix}/sessions/{sid}/generate',json={'prompt':'生成本课内容'}).json()
        job=client.get(f'{prefix}/jobs/'+first['id']).json()
        assert job['status']=='completed', job
        assert job['duration_seconds'] >= 0
        assert job['ended_at']
        assert all(stage['duration_seconds'] >= 0 for stage in job['stages'])
        session=client.get(f'{prefix}/sessions/{sid}').json()
        assert session['versions'][0]['sources'][0]['id']=='s1'
        assert session['sources'][0]['id']=='s1'
        previous=session['versions'][0]
        revision=client.post(f'{prefix}/sessions/{sid}/revise',json={
            'prompt':'修改第2页的说明' if category=='互动课件' else '修改第1题解析' if category=='限时练习' else '修改第一个任务',
            'base_version_id':previous['id'],
        }).json()
        done=client.get(f'{prefix}/jobs/'+revision['id']).json()
        assert done['status']=='completed', done
        assert [c['variables']['operation'] for c in calls]==['初始化','微调']
        assert len(client.get(f'{prefix}/sessions/{sid}').json()['versions'])==2


def test_first_workflow_image_can_be_exported_from_trusted_quote(tmp_path,monkeypatch):
    from backend.app.study_guide.tools.documents import DocumentEngine
    from test_study_image_documents import png
    from backend.app.shared.tools.images import image_catalog
    raw=json.loads(Path('vendor/chemistry/examples/outline.json').read_text())
    raw['outline']['sections'][0]['blocks'].insert(0,dict(id='new-image',type='image',image_id='hit:image:1',caption='装置图'))
    image_url='https://workflow.test/api/system/file/d/image'
    def handle(request):
        if request.method=='GET':
            assert str(request.url)==image_url
            assert 'authorization' not in request.headers
            return httpx.Response(200,content=png(),headers={'content-type':'image/png'})
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(raw)}}],
            'responseData':[{'quoteList':[{'id':'hit','datasetId':'dataset','q':'装置','a':f'![原图]({image_url})'}]}]})
    mock=httpx.MockTransport(handle)
    init=WorkflowClient.__init__
    monkeypatch.setattr(WorkflowClient,'__init__',lambda self,s,transport=None:init(self,s,mock))
    doc_init=DocumentEngine.__init__
    monkeypatch.setattr(DocumentEngine,'__init__',lambda self,settings=None,image_transport=None:doc_init(self,settings,mock))
    config=Settings(data_dir=tmp_path,fastgpt_url='https://workflow.test',fastgpt_key='KEY',datasets=[{'id':'dataset'}])
    with TestClient(create_app(config)) as client:
        sid=client.post('/api/sessions',json={"chapter":"第三节 氧化还原反应"}).json()['id']
        jid=client.post(f'/api/sessions/{sid}/generate',json={'prompt':'请配图生成导学案'}).json()['id']
        job=client.get('/api/jobs/'+jid).json()
        assert job['status']=='completed',job
        version=client.get(f'/api/sessions/{sid}').json()['versions'][0]
        image_id=image_catalog(version['sources'])[0]['image_id']
        assert version['content']['sections'][0]['blocks'][0]['image_id']==image_id
        assert (tmp_path/sid/'versions'/version['id']/'images'/f'{image_id}.bin').is_file()


@pytest.mark.parametrize('category,prefix', [
    ('导学案','/api'), ('互动课件','/api/courseware'), ('限时练习','/api/timed-practice'),
])
@pytest.mark.parametrize('operation', ['初始化', '微调'])
def test_search_error_info_reaches_failed_agent_job_without_repair(tmp_path, monkeypatch, category, prefix, operation):
    reason = '其他学科即将开放，敬请期待。'
    calls = []
    def handle(request):
        payload = json.loads(request.content)
        current = payload['variables']['operation']
        calls.append(current)
        if current == operation:
            content = {'errorInfo':reason}
        elif category == '导学案':
            content = json.loads(Path('vendor/chemistry/examples/outline.json').read_text())
        elif category == '互动课件':
            content = deck()
        else:
            content = paper()
        return httpx.Response(200, json={'choices':[{'message':{'content':json.dumps(content, ensure_ascii=False)}}],
            'responseData':[{'quoteList':[{'id':'s1','datasetId':'dataset','q':'氧化还原反应','a':'比较元素化合价，分析电子转移。'}]}]})
    transport_mock = httpx.MockTransport(handle)
    original = WorkflowClient.__init__
    monkeypatch.setattr(WorkflowClient, '__init__', lambda self,s,transport=None:original(self,s,transport_mock))
    config = Settings(data_dir=tmp_path, fastgpt_url='https://workflow.test', fastgpt_key='KEY', datasets=[{'id':'dataset'}])
    with TestClient(create_app(config)) as client:
        sid = client.post(prefix+'/sessions', json=practice_settings() if category=='限时练习' else {"chapter":"第三节 氧化还原反应"}).json()['id']
        first = client.post(f'{prefix}/sessions/{sid}/generate', json={'prompt':'生成本课内容'}).json()
        if operation == '微调':
            assert client.get(f'{prefix}/jobs/'+first['id']).json()['status'] == 'completed'
            version = client.get(f'{prefix}/sessions/{sid}').json()['versions'][0]
            first = client.post(f'{prefix}/sessions/{sid}/revise', json={
                'prompt':'调整本课内容', 'base_version_id':version['id'],
            }).json()
        failed = client.get(f'{prefix}/jobs/'+first['id']).json()
        assert failed['status'] == 'failed'
        assert failed['error'] == reason
        assert calls == (['初始化'] if operation=='初始化' else ['初始化','微调'])
        assert len(client.get(f'{prefix}/sessions/{sid}').json()['versions']) == (0 if operation=='初始化' else 1)
