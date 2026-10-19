import httpx
import pytest
from backend.app.config import Settings
from backend.app.retrieval import FastGPTRetriever
from backend.app.model_client import ModelClient


def configured(**kw):
    return Settings(fastgpt_url='https://kb.test/api', fastgpt_key='SECRET', datasets=[{'id':'dataset1','category':'textbook'}], model_url='https://model.test/v1', model_key='MODELSECRET', model='model', **kw)


def test_search_retains_evidence_and_path():
    def handle(request):
        assert request.url.path == '/api/core/dataset/searchTest'
        assert request.headers['authorization'] == 'Bearer SECRET'
        return httpx.Response(200,json={'code':200,'data':[{'id':'hit1','q':'反应','a':'化合价变化','sourceName':'教材.pdf','collectionId':'col1','score':0.9}]})
    hits = FastGPTRetriever(configured(), httpx.MockTransport(handle)).search('氧化还原')
    assert hits[0]['verified'] is False
    assert hits[0]['evidence'] == '反应\n化合价变化'
    assert hits[0]['category'] == 'textbook'


@pytest.mark.parametrize('body', [{'code':401,'message':'bad SECRET'}, {'code':200,'data':{}}, {'code':200,'data':[{'id':'bad','a':None}]}])
def test_invalid_or_business_error(body):
    with pytest.raises(ValueError) as exc:
        FastGPTRetriever(configured(), httpx.MockTransport(lambda _:httpx.Response(200,json=body))).search('q')
    assert 'SECRET' not in str(exc.value)


def test_empty_hits():
    assert FastGPTRetriever(configured(), httpx.MockTransport(lambda _:httpx.Response(200,json={'code':200,'data':[]}))).search('q') == []


def test_model_bad_json():
    client = ModelClient(configured(), httpx.MockTransport(lambda _:httpx.Response(200,json={'choices':[{'message':{'content':'not json'}}]})))
    with pytest.raises(ValueError, match='JSON'):
        client.generate_json([])
