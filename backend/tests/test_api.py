from fastapi.testclient import TestClient
from backend.app.config import Settings
from backend.app.main import create_app


def test_health_and_session(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        health=client.get('/api/health').json()
        assert health['ready'] is False
        assert 'fastgpt_key' in health['missing']
        session=client.post('/api/sessions',json={'chapter':'氧化还原反应'}).json()
        assert client.get('/api/sessions/'+session['id']).json()['settings']['chapter']=='氧化还原反应'
        assert client.get('/api/sessions/not-found').status_code==404
        assert client.get('/api/sessions/'+session['id']+'/versions/no/files/outline').status_code==404
        assert client.get('/api/no-such-route').status_code==404


def test_upload_and_review(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        sid=client.post('/api/sessions',json={}).json()['id']
        response=client.post(f'/api/sessions/{sid}/resources',files={'file':('教材.txt','教材原文'.encode(),'text/plain')},data={'category':'textbook'})
        assert response.status_code==200,response.text
        source=response.json()
        assert 'file_path' not in source
        assert source['verified'] is False
        assert client.post(f'/api/sessions/{sid}/sources/{source["id"]}/review',json={'verified':True,'note':'已核对原文'}).status_code==200
        session=client.get(f'/api/sessions/{sid}').json()
        assert session['resources'][0]['verified'] is True
        response=client.post(f'/api/sessions/{sid}/resources',files={'file':('fake.docx',b'bad','application/octet-stream')})
        assert response.status_code==400


def test_unknown_review_and_invalid_revision(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        sid=client.post('/api/sessions',json={}).json()['id']
        assert client.post(f'/api/sessions/{sid}/sources/fake/review',json={'verified':True,'note':'核验'}).status_code==404
        assert client.post(f'/api/sessions/{sid}/revise',json={'prompt':'修改','base_version_id':'fake'}).status_code==409
        assert client.post(f'/api/sessions/{sid}/generate',json={'prompt':'x'*9000}).status_code==422
