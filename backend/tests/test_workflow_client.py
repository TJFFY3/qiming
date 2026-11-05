"""新工作流变量、完整响应与可信来源的协议测试。"""
import json
from types import SimpleNamespace

import httpx
import pytest

from backend.app.shared.workflow.client import (
    WorkflowClient, WorkflowServiceError, WorkflowOutputError, WORKFLOW_APP_ID,
)


def settings(**overrides):
    return SimpleNamespace(fastgpt_url='https://workflow.test/api', fastgpt_key='SECRET',
                           datasets=[{'id': 'dataset', 'name': '教材', 'category': 'textbook'}],
                           model_read_timeout=300, model_total_timeout=600,
                           **overrides)


def task():
    return dict(agent_category='导学案', teacher_settings={'chapter': '钠及其化合物'},
                prompt='请生成本课内容', operation='初始化', sources=[])


def event(value, name='answer'):
    return ('event: '+name+'\ndata: '+(value if isinstance(value,str) else json.dumps(value))+'\n\n').encode()


class Chunks(httpx.SyncByteStream):
    def __init__(self, chunks): self.chunks=chunks
    def __iter__(self): yield from self.chunks


@pytest.mark.parametrize('category', ['导学案', '互动课件', '限时练习'])
def test_variables_and_plain_response_keep_old_content_shape(category):
    def handle(request):
        body=json.loads(request.content)
        assert request.url.path=='/api/v1/chat/completions'
        assert body['appId']==WORKFLOW_APP_ID
        assert body['detail'] is True
        assert 'chatId' not in body
        variables=body['variables']
        assert set(variables)=={'datasetIds','chapters','repoLabelConfig','subject','repoSearchInfo','dynamicPromot','agentCategory','basePromot','operation'}
        assert variables['datasetIds']==[{'datasetId':'dataset'}]
        assert json.loads(variables['chapters'])==['钠及其化合物']
        assert json.loads(variables['repoLabelConfig'])=={}
        assert variables['subject']=='化学' and variables['operation']=='初始化'
        assert variables['agentCategory']==category
        assert 'Schema' in variables['basePromot']
        assert '钠及其化合物' in variables['repoSearchInfo']
        assert '请生成本课内容' not in variables['repoSearchInfo']
        assert 'current_outline' not in variables['repoSearchInfo']
        assert 'current_outline' in body['messages'][-1]['content']
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"outline": {}}'},'finish_reason':'stop'}]})
    arguments=task() | {'agent_category':category}
    result=WorkflowClient(settings(),httpx.MockTransport(handle)).generate_task(
        [{'role':'system','content':'Schema: {}'},{'role':'user','content':'{"current_outline":{}}'}],**arguments)
    assert result.content=={'outline':{}}
    assert result.sources==[]


def test_stream_metadata_after_answer_stop_is_collected_and_never_used_as_content():
    quote={'id':'hit','datasetId':'dataset','collectionId':'collection','sourceName':'教材.pdf','q':'钠','a':'与水反应'}
    def handle(request):
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Chunks([
            event({'choices':[{'delta':{'content':'{"slides": []}'},'finish_reason':'stop'}]}),
            event([{'quoteList':[quote]}],'flowResponses'),event('[DONE]'),
        ]))
    result=WorkflowClient(settings(),httpx.MockTransport(handle)).generate_task([],**task())
    assert result.content=={'slides':[]}
    assert result.sources[0]['id']=='hit'
    assert result.sources[0]['evidence']=='钠\n与水反应'
    assert result.sources[0]['verified'] is False


def test_response_data_deduplicates_quotes_and_ignores_model_claims():
    quote={'id':'hit','dataset_id':'dataset','q':'钠','a':'真实证据','verified':True}
    def handle(request):
        return httpx.Response(200,json={'responseData':[{'quoteList':[quote,quote]}],
            'choices':[{'message':{'content':json.dumps({'sources':[{'id':'fake','evidence':'伪造'}]})}}]})
    result=WorkflowClient(settings(),httpx.MockTransport(handle)).generate_task([],**task())
    assert [s['id'] for s in result.sources]==['hit']
    assert not result.sources[0]['verified']


@pytest.mark.parametrize('mode',['error','disconnect','length','business_error'])
def test_transport_errors_are_not_repaired_as_content(mode):
    def handle(request):
        if mode=='business_error': return httpx.Response(200,json={'code':500,'message':'secret'})
        chunks=[event({'choices':[{'delta':{'content':'{"outline":'}}]})]
        if mode=='error': chunks.append(event({'message':'SECRET'},'error'))
        if mode=='length': chunks.append(event({'choices':[{'delta':{},'finish_reason':'length'}]}))
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Chunks(chunks))
    error=WorkflowOutputError if mode=='length' else WorkflowServiceError
    with pytest.raises(error):
        WorkflowClient(settings(),httpx.MockTransport(handle)).generate_task([],**task())


def test_bad_json_preserves_response_for_bounded_repair():
    client=WorkflowClient(settings(),httpx.MockTransport(lambda r:httpx.Response(200,json={'choices':[{'message':{'content':'{"broken":'}}]})))
    with pytest.raises(WorkflowOutputError) as error: client.generate_task([],**task())
    assert error.value.response_text=='{"broken":'


@pytest.mark.parametrize('mode', ['body', 'message', 'stream_message', 'stream_event', 'metadata_json', 'metadata_stream', 'stream_error'])
def test_search_error_info_is_a_service_failure_with_original_reason(mode):
    reason = '其他学科即将开放，敬请期待。'
    failure = {'errorInfo': reason}
    def handle(request):
        if mode == 'body':
            return httpx.Response(200, json=failure)
        if mode == 'message':
            return httpx.Response(200, json={'choices':[{'message':{'content':json.dumps(failure)}}]})
        if mode == 'metadata_json':
            return httpx.Response(200, json={'choices':[{'message':{'content':'{}'}}], 'responseData':[failure]})
        if mode == 'stream_message':
            # JSON 错误对象可以跨多个增量返回，需组装后识别。
            text = json.dumps(failure, ensure_ascii=False)
            chunks = [event({'choices':[{'delta':{'content':text[:12]}}]}),
                      event({'choices':[{'delta':{'content':text[12:]},'finish_reason':'stop'}]}), event('[DONE]')]
        elif mode == 'metadata_stream':
            chunks = [event({'choices':[{'delta':{'content':'{}'},'finish_reason':'stop'}]}),
                      event('[DONE]'), event([failure], 'flowResponses')]
        else:
            chunks = [event(failure, 'error' if mode == 'stream_error' else 'answer'), event('[DONE]')]
        return httpx.Response(200, headers={'content-type':'text/event-stream'}, stream=Chunks(chunks))
    with pytest.raises(WorkflowServiceError) as error:
        WorkflowClient(settings(), httpx.MockTransport(handle)).generate_task([], **task())
    assert str(error.value) == reason


def test_error_info_in_source_evidence_is_not_a_workflow_failure():
    evidence = '{"errorInfo":"资料中的示例文本"}'
    response = {'choices':[{'message':{'content':'{}'}}],
                'responseData':[{'quoteList':[{'id':'s1','q':evidence,'a':''}]}]}
    result = WorkflowClient(settings(), httpx.MockTransport(lambda _:httpx.Response(200, json=response))).generate_task([], **task())
    assert result.content == {} and result.sources[0]['evidence'] == evidence


def test_revision_and_filters_and_uploads_are_sent_on_every_call():
    def handle(request):
        body=json.loads(request.content); v=body['variables']
        assert v['operation']=='微调'
        assert json.loads(v['repoLabelConfig'])=={'tags':{'课题':'钠'}}
        assert '上传证据' not in v['repoSearchInfo'] and '修复错误' not in v['repoSearchInfo']
        assert '上传证据' in body['messages'][-1]['content']
        assert '修复错误' in body['messages'][-1]['content']
        assert '只返回Schema' in v['basePromot']
        return httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}]})
    config=settings(repo_label_config={'tags':{'课题':'钠'}})
    source={'id':'upload','evidence':'上传证据','source_type':'upload'}
    WorkflowClient(config,httpx.MockTransport(handle)).generate_task(
        [{'role':'system','content':'只返回Schema'},{'role':'user','content':'修复错误'}],
        **(task()|{'operation':'微调','sources':[source]}))


def test_folder_config_is_expanded_to_real_dataset_ids_without_content_search():
    paths=[]
    def handle(request):
        paths.append(request.url.path)
        if request.url.path.endswith('/core/dataset/list'):
            assert json.loads(request.content)['parentId']=='folder'
            return httpx.Response(200,json={'code':200,'data':[{'_id':'child','type':'dataset','name':'教材'}]})
        assert json.loads(request.content)['variables']['datasetIds']==[{'datasetId':'child'}]
        return httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}]})
    config=settings(); config.datasets=[{'id':'folder','type':'folder'}]
    WorkflowClient(config,httpx.MockTransport(handle)).generate_task([],**task())
    assert paths==['/api/core/dataset/list','/api/v1/chat/completions']


def test_source_details_after_done_are_still_preserved():
    def handle(request):
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Chunks([
            event({'choices':[{'delta':{'content':'{}'}}]}),event('[DONE]'),
            event([{'quoteList':[{'id':'after','q':'证据','a':''}]}],'flowResponses'),
        ]))
    result=WorkflowClient(settings(),httpx.MockTransport(handle)).generate_task([],**task())
    assert result.sources[0]['id']=='after'


def test_empty_fastgpt_delta_with_null_content_is_not_answer_text():
    def handle(request):
        return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Chunks([
            event({'choices':[{'delta':{'content':None}}]}),
            event({'choices':[{'delta':{'content':'{}'}}]}),
            event({'choices':[{'delta':{'content':None},'finish_reason':'stop'}]}),event('[DONE]'),
        ]))
    assert WorkflowClient(settings(),httpx.MockTransport(handle)).generate_task([],**task()).content=={}


def test_workflow_prompt_defines_source_scoped_image_ids():
    def handle(request):
        v=json.loads(request.content)['variables']
        assert ':image:' in v['basePromot']
        return httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}]})
    WorkflowClient(settings(),httpx.MockTransport(handle)).generate_task([],**task())


def test_source_image_alias_is_normalized_only_with_trusted_quote_evidence():
    from backend.app.shared.workflow.binding import generate
    from backend.app.shared.tools.images import image_catalog
    url='https://workflow.test/api/system/file/d/picture.png'
    def handle(request):
        content={'outline':{'sections':[{'blocks':[
            {'type':'image','image_id':'hit:image:1','caption':'装置图'},
            {'type':'image','image_id':'fake:image:1','caption':'未知图'},
        ]}]}}
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps(content)}}],
            'responseData':[{'quoteList':[{'id':'hit','q':'原图','a':f'![装置]({url})'}]}]})
    sources=[]
    content=generate(WorkflowClient(settings(),httpx.MockTransport(handle)),[],**(task()|{'sources':sources}))
    blocks=content['outline']['sections'][0]['blocks']
    assert blocks[0]['image_id']==image_catalog(sources)[0]['image_id']
    assert blocks[1]['image_id']=='fake:image:1'  # 仍交由原有导出校验拒绝。


def test_directory_time_budget_prevents_late_workflow_post(monkeypatch):
    import backend.app.shared.workflow.client as module
    elapsed=[0.0]; calls=[]
    monkeypatch.setattr(module.time,'monotonic',lambda:elapsed[0])
    def handle(request):
        calls.append(request.url.path)
        if request.url.path.endswith('/core/dataset/list'):
            elapsed[0]=5.0
            return httpx.Response(200,json={'code':200,'data':[{'_id':'child','type':'dataset'}]})
        raise AssertionError('目录解析后预算已用尽，不应发送工作流请求')
    config=settings();config.datasets=[{'id':'folder','type':'folder'}];config.model_total_timeout=2
    with pytest.raises(WorkflowServiceError,match='时限|超时|超过'):
        WorkflowClient(config,httpx.MockTransport(handle)).generate_task([],**task())
    assert len(calls)==1


def test_folder_slow_body_is_interrupted_by_total_deadline():
    import time
    class Slow(httpx.SyncByteStream):
        def __iter__(self):
            for i in range(100):
                time.sleep(.01)
                yield b' '
        def close(self): pass
    def handle(request):
        return httpx.Response(200,stream=Slow())
    config=settings();config.datasets=[{'id':'folder','type':'folder'}];config.model_total_timeout=.05
    started=time.monotonic()
    with pytest.raises(WorkflowServiceError,match='超过|时限'):
        WorkflowClient(config,httpx.MockTransport(handle)).generate_task([],**task())
    assert time.monotonic()-started < .5


@pytest.mark.parametrize('stream',[False,True])
def test_node_dataset_failure_is_service_error_not_empty_json_repair(stream):
    details=[{'moduleName':'标签过滤与动态知识库','moduleType':'datasetSearchNode','errorText':'common:core.dataset.error.unExistDataset'}]
    def handle(request):
        if stream:
            return httpx.Response(200,headers={'content-type':'text/event-stream'},stream=Chunks([
                event({'choices':[{'delta':{'content':None},'finish_reason':'stop'}]}),
                event('[DONE]'),event(details,'flowResponses'),
            ]))
        return httpx.Response(200,json={'choices':[{'message':{'content':''},'finish_reason':'stop'}],'responseData':details})
    with pytest.raises(WorkflowServiceError,match='知识库'):
        WorkflowClient(settings(),httpx.MockTransport(handle)).generate_task([],**task())


def test_final_user_question_carries_contract_and_latest_repair_feedback():
    # 工作流节点可能直接引用用户问题；仅传variables会让修复仍执行旧问题。
    def handle(request):
        body=json.loads(request.content)
        question=body['messages'][-1]['content']
        assert 'Schema' in question and 'minutes' in question
        assert '修复：删除estimated_minutes并使用minutes' in question
        return httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}]})
    WorkflowClient(settings(),httpx.MockTransport(handle)).generate_task([
        {'role':'system','content':'Schema: {"minutes": "number"}'},
        {'role':'user','content':'修复：删除estimated_minutes并使用minutes'},
    ],**task())

@pytest.mark.parametrize('category', ['导学案', '互动课件', '限时练习'])
def test_repo_search_info_only_contains_retrieval_content(category):
    def handle(request):
        body=json.loads(request.content)
        query=body['variables']['repoSearchInfo']
        for topic in ['氧化还原反应', '第一课时', '电子转移', '铜与氧气反应']:
            assert topic in query
        for noise in ['JSON', 'Schema', 'current_outline', '上传证据', '24pt', '10页', '30分钟', '100分']:
            assert noise not in query
        assert '上传证据' in body['messages'][-1]['content']
        assert 'Schema' in body['variables']['basePromot']
        return httpx.Response(200,json={'choices':[{'message':{'content':'{}'}}]})
    WorkflowClient(settings(),httpx.MockTransport(handle)).generate_task(
        [{'role':'system','content':'Schema: {}'}, {'role':'user','content':'{"current_outline":{}}'}],
        **(task() | {'agent_category':category,
          'teacher_settings':{'edition':'人教版 必修第一册','grade':'高一','chapter':'氧化还原反应','period':'第一课时','options':{'focus':['电子转移']}},
          'prompt':'补充铜与氧气反应实验。生成10页，字体24pt，只返回JSON。\n【优化提示】\n课堂时长：30分钟\n满分：100分\n本课重点：电子转移\n【优化结束】',
          'sources':[{'id':'upload','evidence':'上传证据'}]}))


@pytest.mark.parametrize('category', ['导学案', '互动课件', '限时练习'])
@pytest.mark.parametrize('operation', ['初始化', '微调'])
def test_chemistry_dynamic_prompt_is_independent_of_retrieval_and_task(category, operation):
    def handle(request):
        variables = json.loads(request.content)['variables']
        dynamic = variables['dynamicPromot']
        for requirement in [
            '四、化学表达', '[H2O]、[SO4^2-]', '2[KMnO4]', '不得写成 [2KMnO4]',
            '物种正确、连接符完整并配平', '不得为满足格式要求随意改变反应物、生成物或反应条件',
            '{"text":"点燃","condition":true}', '{"text":"△","condition":true}',
            '不写 △→ 或 Δ→', '渲染器负责绘制连续双实线连接符',
            '普通等号使用单个 =', '同一个扁平 run 数组',
            '{"text":"[CaCO3] "}', '{"text":"高温","condition":true}',
            '{"text":" [CaO] + [CO2]↑"}', '不输出 HTML <br>', r'JSON 字符串中的 \n',
        ]:
            assert requirement in dynamic
        assert variables['repoSearchInfo'] == '化学 钠及其化合物 钠与水反应'
        assert '钠与水反应' not in dynamic and 'Schema' not in dynamic
        assert variables['operation'] == operation
        return httpx.Response(200, json={'choices':[{'message':{'content':'{}'}}]})
    WorkflowClient(settings(), httpx.MockTransport(handle)).generate_task(
        [{'role':'system', 'content':'Schema: {}'}],
        **(task() | {'agent_category':category, 'operation':operation, 'prompt':'补充钠与水反应'}))


@pytest.mark.parametrize('subject', ['语文', '数学', '英语', '物理', '生物', '政治', '历史', '地理'])
def test_other_subjects_do_not_receive_chemistry_dynamic_prompt(subject):
    def handle(request):
        variables = json.loads(request.content)['variables']
        assert variables['repoSearchInfo'] == f'{subject} 本课知识点'
        assert variables['dynamicPromot'] == ''
        return httpx.Response(200, json={'choices':[{'message':{'content':'{}'}}]})
    config = settings()
    config.datasets = [{'id':'dataset', 'name':subject+'教材'}]
    WorkflowClient(config, httpx.MockTransport(handle)).generate_task([], **(task() | {
        'teacher_settings':{'subject':subject, 'chapter':'本课知识点'}, 'prompt':''}))
