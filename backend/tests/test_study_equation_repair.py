import copy
import json
from pathlib import Path

import pytest
from docx import Document

from backend.app.config import Settings
from backend.app.study_guide.tools.documents import DocumentEngine
from backend.app.shared.chemistry.validation import validate_study_guide_result
from backend.app.study_guide.application.pipeline import Pipeline
from backend.app.study_guide.storage.store import Store

SAMPLE=json.loads(Path('vendor/chemistry/examples/outline.json').read_text())


def bad_outline():
    raw=copy.deepcopy(SAMPLE)
    raw['outline']['sections'][0]['blocks'].extend([
        {'id':'water-equation','type':'paragraph','content':'H2 + O2 = H2O'},
        {'id':'copper-equation','type':'table','headers':['反应方程式'],
         'rows':[['Cu + O2 = CuO']]},
    ])
    return raw


def test_balance_error_collects_original_cells_paths_and_atom_counts():
    with pytest.raises(ValueError) as error:
        validate_study_guide_result(bad_outline())
    targets=getattr(error.value,'targets',[])
    assert len(targets)==2
    assert targets[0]['value']=='H2 + O2 = H2O'
    assert targets[0]['left_atoms']=={'H':2,'O':2}
    assert targets[0]['right_atoms']=={'H':2,'O':1}
    assert targets[1]['path'][-3:]==['rows',0,0]
    assert 'Cu + O2 = CuO' in str(error.value)


class Retriever:
    def search(self,q):
        return [{'id':'src','title':'教材','locator':'片段1','category':'textbook',
                 'evidence':'氢气和氧气反应生成水；铜和氧气反应生成氧化铜。','verified':False}]


def setup(tmp_path,model):
    store=Store(tmp_path/'test.sqlite');s=store.create_session({})
    return store,s,Pipeline(Settings(data_dir=tmp_path),store,Retriever(),model,DocumentEngine())


def repairs():
    return {'repairs':[{'id':'equation-1','content':'2H2 + O2 = 2H2O'},
                       {'id':'equation-2','content':'2Cu + O2 = 2CuO'}]}


def test_pipeline_repairs_both_fields_locally_and_preserves_other_content(tmp_path):
    raw=bad_outline();sent=[]
    class Model:
        def generate_json(self,messages):
            sent.append(copy.deepcopy(messages))
            return copy.deepcopy(raw) if len(sent)==1 else repairs()
    store,s,p=setup(tmp_path,Model());j=p.start_generation(s['id'],{'prompt':'生成导学案'})
    p.run(j['id']);job=store.get_job(j['id'])
    assert job['status']=='completed',job
    assert len(sent)==2
    request=json.loads(sent[1][1]['content'])
    assert len(request['equations'])==2
    assert request['equations'][0]['left_atoms']=={'H':2,'O':2}
    assert 'sources' not in request and 'outline' not in request
    v=store.get_session(s['id'])['versions'][-1]
    assert v['content']['sections'][1:]==SAMPLE['outline']['sections'][1:]
    assert v['content']['sections'][0]['blocks'][-2]['content']=='2[H2] + [O2] = 2[H2O]'
    assert v['report']['format_repairs'][-1]['method']=='equation_full_model'
    word=Document(Path(v['directory'])/'outline.docx')
    assert any('2H2 + O2 = 2H2O' in para.text for para in word.paragraphs)
    assert list((tmp_path/s['id']/'diagnostics'/j['id']).glob('equation-*.json'))


def test_invalid_local_repair_keeps_original_targets_for_second_try(tmp_path):
    sent=[]
    class Model:
        def generate_json(self,messages):
            sent.append(copy.deepcopy(messages))
            if len(sent)==1:return bad_outline()
            if len(sent)==2:return {'repairs':[{'id':'equation-1','content':'H2 + O2 = H2O'}]}
            return repairs()
    store,s,p=setup(tmp_path,Model());j=p.start_generation(s['id'],{'prompt':'生成'})
    p.run(j['id']);job=store.get_job(j['id'])
    assert job['status']=='completed',job
    assert len(sent)==3
    assert json.loads(sent[2][1]['content'])['equations'][0]['value']=='H2 + O2 = H2O'
    assert 'repairs' in sent[2][-2]['content']


@pytest.mark.parametrize('replacement',['水生成了','H2 = H2','2H2 + O2 = H2O'])
def test_bad_repair_cannot_hide_or_replace_the_reaction(tmp_path,replacement):
    calls=[]
    raw=bad_outline();raw['outline']['sections'][0]['blocks'].pop()
    class Model:
        def generate_json(self,messages):
            calls.append(messages)
            if len(calls)==1:return copy.deepcopy(raw)
            return {'repairs':[{'id':'equation-1','content':replacement}]}
    store,s,p=setup(tmp_path,Model());j=p.start_generation(s['id'],{'prompt':'生成'})
    p.run(j['id']);job=store.get_job(j['id'])
    assert len(calls)==3
    assert job['status']=='failed'
    assert '方程式' in job['error']
    assert not store.get_session(s['id'])['versions']


def test_patch_equations_are_repaired_without_touching_base(tmp_path):
    calls=[]
    class Model:
        def generate_json(self,messages):
            calls.append(messages)
            if len(calls)==1:return copy.deepcopy(SAMPLE)
            if len(calls)==2:return {'mode':'patch','changes':[{'block_id':'question-1','replacement':[
                {'type':'paragraph','content':'CaCO3 + HCl = CaCl2 + CO2 + H2O'}]}]}
            return {'repairs':[{'id':'equation-1','content':'CaCO3 + 2HCl = CaCl2 + CO2 + H2O'}]}
    store,s,p=setup(tmp_path,Model());first=p.start_generation(s['id'],{'prompt':'生成'});p.run(first['id'])
    before=copy.deepcopy(store.get_session(s['id'])['versions'][0])
    j=p.start_revision(s['id'],{'base_version_id':before['id'],'prompt':'增加方程式'});p.run(j['id'])
    assert store.get_job(j['id'])['status']=='completed',store.get_job(j['id'])
    versions=store.get_session(s['id'])['versions']
    assert versions[0]==before
    assert versions[-1]['content']['sections'][1:]==before['content']['sections'][1:]


def test_invalid_json_during_local_repair_keeps_targets_and_retry_budget(tmp_path):
    from backend.app.study_guide.llm.client import ModelOutputError
    sent=[]
    class Model:
        def generate_json(self,messages):
            sent.append(copy.deepcopy(messages))
            if len(sent)==1:return bad_outline()
            if len(sent)==2:raise ModelOutputError('JSON 第1行不完整','{"repairs":')
            return repairs()
    store,s,p=setup(tmp_path,Model());j=p.start_generation(s['id'],{'prompt':'生成'})
    p.run(j['id'])
    assert store.get_job(j['id'])['status']=='completed',store.get_job(j['id'])
    assert len(sent)==3
    assert sent[2][-2]=={'role':'assistant','content':'{"repairs":'}
    assert 'equations' in json.loads(sent[2][1]['content'])


def test_full_repair_can_correct_an_incorrect_reaction_condition(tmp_path):
    raw=copy.deepcopy(SAMPLE)
    raw['outline']['sections'][0]['blocks'].append({'id':'decomposition','type':'paragraph','content':[
        {'text':'[KClO3] '},{'text':'点燃','condition':True},{'text':' [KCl] + [O2]↑'}]})
    sent=[]
    class Model:
        def generate_json(self,messages):
            sent.append(messages)
            if len(sent)==1:return copy.deepcopy(raw)
            return {'repairs':[{'id':'equation-1','content':[
                {'text':'2[KClO3] '},{'text':'△','condition':True},{'text':' 2[KCl] + 3[O2]↑'}]}]}
    store,s,p=setup(tmp_path,Model());j=p.start_generation(s['id'],{'prompt':'生成'})
    p.run(j['id']);done=store.get_job(j['id'])
    assert done['status']=='completed',done
    assert len(sent)==2
    content=store.get_session(s['id'])['versions'][-1]['content']['sections'][0]['blocks'][-1]['content']
    assert any(run.get('condition') and run['text']=='△' for run in content)


@pytest.mark.parametrize('original,corrected',[
    ('2CaCO3 = CaO + CO2↓','CaCO3 = CaO + CO2↑'),
    ('CuO + HCl = CuCl2↑ + H2O','CuO + 2HCl = CuCl2 + H2O'),
    ('NaCl + AgNO3 = 2AgCl↑ + NaNO3','NaCl + AgNO3 = AgCl↓ + NaNO3'),
])
def test_full_equation_repair_can_correct_erroneous_state_markers(original,corrected):
    from backend.app.shared.chemistry.repair import apply_equation_repairs
    raw={'sections':[{'blocks':[{'type':'paragraph','content':original}]}]}
    with pytest.raises(ValueError) as caught:
        validate_study_guide_result(raw)
    fixed,_=apply_equation_repairs(raw,caught.value.targets,{'repairs':[{'id':'equation-1','content':corrected}]})
    validate_study_guide_result(fixed)
    assert fixed['sections'][0]['blocks'][0]['content']!=original
