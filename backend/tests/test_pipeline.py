import copy
import json
from pathlib import Path
import pytest
from backend.app.config import Settings
from backend.app.store import Store, Conflict
from backend.app.pipeline import Pipeline
from backend.app.documents import DocumentEngine

SAMPLE=json.loads(Path('vendor/chemistry/examples/outline.json').read_text())
class Retriever:
    def search(self, query):
        return [{'id':'src','title':'教材','category':'textbook','evidence':'元素化合价变化','locator':'切片1','verified':False}]
class Model:
    def __init__(self):self.count=0
    def generate_json(self,messages):
        self.count+=1
        return copy.deepcopy(SAMPLE)

def setup(tmp_path,model=None):
    s=Settings(data_dir=tmp_path); store=Store(tmp_path/'db')
    session=store.create_session({'chapter':'氧化还原反应','period':'第一课时'})
    return store,session,Pipeline(s,store,Retriever(),model or Model(),DocumentEngine())

def test_source_gate_and_real_generation(tmp_path):
    store,s,p=setup(tmp_path)
    job=p.start_generation(s['id'],{'prompt':'生成','allow_draft':False});p.run(job['id'])
    assert store.get_job(job['id'])['status']=='failed'
    assert store.get_session(s['id'])['versions']==[]
    job=p.start_generation(s['id'],{'prompt':'生成','allow_draft':True});p.run(job['id'])
    done=store.get_job(job['id']);assert done['status']=='completed',done
    version=store.get_session(s['id'])['versions'][-1]
    assert Path(version['directory'],'outline.docx').is_file()
    assert version['report']['draft']
    assert version['sources'][0]['verified'] is False

def test_repair_limit(tmp_path):
    class Bad(Model):
        def generate_json(self,messages):self.count+=1;return {'outline':{'title':'bad'}}
    model=Bad();store,s,p=setup(tmp_path,model)
    job=p.start_generation(s['id'],{'prompt':'生成','allow_draft':True});p.run(job['id'])
    assert model.count==3
    assert store.get_job(job['id'])['status']=='failed'
    assert not store.get_session(s['id'])['versions']

def test_revision_and_stale_guard(tmp_path):
    model=Model();store,s,p=setup(tmp_path,model)
    j=p.start_generation(s['id'],{'prompt':'生成','allow_draft':True});p.run(j['id'])
    v=store.get_session(s['id'])['versions'][-1]
    model.generate_json=lambda _: {'mode':'patch','changes':[{'block_id':'question-1','replacement':[{'type':'paragraph','content':'请增加判断步骤。'}]}]}
    j=p.start_revision(s['id'],{'prompt':'增加提示','base_version_id':v['id']});p.run(j['id'])
    assert store.get_job(j['id'])['status']=='completed'
    latest=store.get_session(s['id'])['versions'][-1]
    assert latest['content']['sections'][1:]==v['content']['sections'][1:]
    with pytest.raises(Conflict):p.start_revision(s['id'],{'prompt':'stale','base_version_id':v['id']})
