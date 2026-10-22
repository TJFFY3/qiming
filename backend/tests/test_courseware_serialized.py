import copy
import io
import json
from pathlib import Path
from zipfile import ZipFile
import pytest
from fastapi.testclient import TestClient
from lxml import etree
from backend.app.courseware.tools.export import export_deck
from backend.tests.test_courseware import app_for, PREFIX

NS = {'a': 'http://schemas.openxmlformats.org/drawingml/2006/main', 'p': 'http://schemas.openxmlformats.org/presentationml/2006/main'}

def example(copper='2Cu + O2 ', product=' 2CuO'):
    return {'title': '反应探究', 'slides': [{'title': '情境导入', 'stage': '启', 'paragraphs': [
        json.dumps([{'text': copper}, {'text': '△', 'condition': True}, {'text': product}], ensure_ascii=False),
        json.dumps([{'text': 'H2 + Cl2 '}, {'text': '点燃', 'condition': True}, {'text': ' 2HCl'}], ensure_ascii=False),
    ]}]}


def assert_native(data):
    with ZipFile(io.BytesIO(data)) as z:
        root=etree.fromstring(z.read('ppt/slides/slide1.xml'))
    texts=root.xpath('//a:t/text()',namespaces=NS)
    assert not any('"text"' in t or '"condition"' in t for t in texts)
    assert '△' in texts and '点燃' in texts
    assert root.xpath('//p:sp[p:nvSpPr/p:cNvPr[starts-with(@name,"反应条件")]]//a:rPr[@sz="1560"]',namespaces=NS)
    assert root.xpath('//a:r[a:rPr/@baseline="-25000"]/a:t[text()="2"]',namespaces=NS)


def test_serialized_arrays_decode_before_validation_and_native_export(tmp_path):
    raw=example();before=copy.deepcopy(raw)
    content,report=export_deck(raw,tmp_path,True)
    assert raw==before and report['passed']
    assert all(isinstance(p,list) for p in content['slides'][0]['paragraphs'])
    assert_native((tmp_path/'courseware.pptx').read_bytes())


def test_serialized_equations_cannot_hide_unbalanced_atoms_or_bad_schema(tmp_path):
    with pytest.raises(ValueError,match='原子数不守恒'):
        export_deck(example('Cu + O2 ', ' CuO'),tmp_path,True)
    raw=example();raw['slides'][0]['paragraphs'][0]='[{"text":"Cu","evil":"payload"}]'
    with pytest.raises(ValueError,match='结构化'):
        export_deck(raw,tmp_path,True)


def test_serialized_unbalanced_reaction_is_repaired_by_model_before_publication(tmp_path):
    app, requests = app_for(tmp_path, [example('Cu + O2 ', ' CuO'), example()])
    with TestClient(app) as c:
        sid = c.post(PREFIX+'/sessions', json={}).json()['id']
        j = c.post(f'{PREFIX}/sessions/{sid}/generate', json={'prompt':'课件'}).json()
        done = c.get(PREFIX+'/jobs/'+j['id']).json()
        assert done['status'] == 'completed'
        assert sum('messages' in r for r in requests) == 2


def test_small_condition_exception_does_not_allow_small_body_text(tmp_path):
    from backend.app.courseware.tools.export import generate_pptx, validate_courseware
    path = tmp_path/'small.pptx'
    generate_pptx([{'title':'标题','stage':'启','paragraphs':['正文']}],path)
    with ZipFile(path) as z:
        parts={name:z.read(name) for name in z.namelist()}
    root=etree.fromstring(parts['ppt/slides/slide1.xml'])
    for properties in root.xpath('//p:sp[p:nvSpPr/p:cNvPr[@name="正文"]]//a:rPr', namespaces=NS):
        properties.set('sz','1560')
    # Template names vary; the body text itself is the authoritative target.
    for properties in root.xpath('//a:r[a:t="正文"]/a:rPr',namespaces=NS):
        properties.set('sz','1560')
    parts['ppt/slides/slide1.xml']=etree.tostring(root)
    with ZipFile(path,'w') as z:
        for name,data in parts.items():z.writestr(name,data)
    report=validate_courseware(path)
    assert not report['passed']
    assert any(i['code']=='PPT_FONT_SMALL' for i in report['issues'])


def test_history_preview_and_download_repair_serialized_arrays_without_editing_original(tmp_path):
    with TestClient(app_for(tmp_path,[example()])[0]) as c:
        sid=c.post(PREFIX+'/sessions',json={}).json()['id']
        j=c.post(f'{PREFIX}/sessions/{sid}/generate',json={'prompt':'课件'}).json()
        vid=c.get(PREFIX+'/jobs/'+j['id']).json()['version_id']
        import sqlite3
        with sqlite3.connect(tmp_path/'courseware'/'agent.sqlite') as db:
            value=json.loads(db.execute("select data from records where kind='session' and id=?",(sid,)).fetchone()[0])
            value['versions'][0]['content']=example('Cu + O2 ',' CuO')
            db.execute("update records set data=? where kind='session' and id=?",(json.dumps(value),sid))
        directory=tmp_path/'courseware'/sid/'versions'/vid
        original=(directory/'courseware.pptx').read_bytes()
        for suffix in ('', '/files/content'):
            r=c.get(f'{PREFIX}/sessions/{sid}/versions/{vid}'+suffix)
            assert r.status_code==200
            v=r.json().get('content',r.json())
            assert isinstance(v['slides'][0]['paragraphs'][0],list)
        assert isinstance(c.get(f'{PREFIX}/sessions/{sid}').json()['versions'][0]['content']['slides'][0]['paragraphs'][0],list)
        r=c.get(f'{PREFIX}/sessions/{sid}/versions/{vid}/files/pptx')
        assert r.status_code==200
        assert_native(r.content)
        assert (directory/'courseware.pptx').read_bytes()==original
