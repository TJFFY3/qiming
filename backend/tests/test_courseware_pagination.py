import copy
from zipfile import ZipFile
import pytest
from backend.app.courseware.tools.export import export_deck
from backend.tests.test_courseware import app_for, PREFIX
from fastapi.testclient import TestClient
from lxml import etree


def crowded():
    return {"title": "氧化还原反应", "slides": [{
        "title": "概念辨析", "stage": "探", "notes": "保留教师备注",
        "paragraphs": ["观察元素化合价变化，分析电子转移的方向。" * 7,
                       [{"text": "2[CuO]+[C]"}, {"text": "高温", "condition": True}, {"text": "2[Cu]+[CO2]↑"}],
                       "小组交流判断依据，并用完整语言说明理由。" * 5],
    }]}


def test_crowded_slides_paginate_without_losing_text_styles_or_equations(tmp_path):
    raw = crowded(); before = copy.deepcopy(raw)
    content, report = export_deck(raw, tmp_path, True)
    assert raw == before and report["passed"]
    assert len(content["slides"]) > 1
    flatten = lambda ps: ''.join(p if isinstance(p,str) else ''.join(r['text'] for r in p) for p in ps)
    assert flatten([p for s in content['slides'] for p in s['paragraphs']]) == flatten(raw['slides'][0]['paragraphs'])
    assert all(s['stage']=='探' and s['notes']=='保留教师备注' for s in content['slides'])
    assert sum(bool(r.get('condition')) for s in content['slides'] for p in s['paragraphs'] if isinstance(p,list) for r in p) == 1
    with ZipFile(tmp_path/'courseware.pptx') as z:
        ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main','p':'http://schemas.openxmlformats.org/presentationml/2006/main'}
        for name in z.namelist():
            if name.startswith('ppt/slides/slide') and name.endswith('.xml'):
                root=etree.fromstring(z.read(name))
                assert all(int(sz)>=2400 for sz in root.xpath('//p:sp[not(p:nvSpPr/p:cNvPr[starts-with(@name,"反应条件")])]//a:rPr/@sz',namespaces=ns))


def test_long_styled_paragraph_splits_and_keeps_formatting(tmp_path):
    raw=crowded();raw['slides'][0]['paragraphs']=[[{'text':'字'*430,'bold':True}]]
    content,_=export_deck(raw,tmp_path,True)
    runs=[r for s in content['slides'] for p in s['paragraphs'] for r in p]
    assert ''.join(r['text'] for r in runs)=='字'*430
    assert all(r['bold'] for r in runs)


def test_local_page_patch_does_not_silently_renumber_other_pages(tmp_path):
    with pytest.raises(ValueError,match='第1页'):
        export_deck(crowded(),tmp_path,True,paginate=False)


def test_short_text_with_many_lines_is_paginated_by_height(tmp_path):
    raw = crowded(); raw['slides'][0]['paragraphs'] = ['辨析\n' * 18 + '总结']
    content, report = export_deck(raw, tmp_path, True)
    assert report['passed'] and len(content['slides']) > 1
    assert ''.join(p for s in content['slides'] for p in s['paragraphs']) == raw['slides'][0]['paragraphs'][0]


def test_page_boundary_never_separates_a_coefficient_from_its_formula(tmp_path):
    raw = crowded(); raw['slides'][0]['paragraphs'] = ['字' * 199 + '2[H2O]' + '末' * 30]
    content, _ = export_deck(raw, tmp_path, True)
    assert not any(p.endswith('2') for s in content['slides'] for p in s['paragraphs'])
    assert any('2[H2O]' in p for s in content['slides'] for p in s['paragraphs'])


def test_explicit_page_count_remains_visible_as_a_conflict_after_pagination(tmp_path):
    app, _ = app_for(tmp_path, [crowded()])
    with TestClient(app) as client:
        sid = client.post(PREFIX + '/sessions', json={}).json()['id']
        job = client.post(f'{PREFIX}/sessions/{sid}/generate', json={'prompt': '生成1页课件'}).json()
        done = client.get(PREFIX + '/jobs/' + job['id']).json()
        version = client.get(f'{PREFIX}/sessions/{sid}/versions/'+done['version_id']).json()
        assert version['report']['page_count'] > 1
        assert any('要求总页数 1' in s for s in version['report']['conflicts'])


def test_generation_automatically_paginates_instead_of_three_failed_model_calls(tmp_path):
    app,requests=app_for(tmp_path,[crowded()])
    with TestClient(app) as client:
        sid=client.post(PREFIX+'/sessions',json={}).json()['id']
        job=client.post(f'{PREFIX}/sessions/{sid}/generate',json={'prompt':'生成课件'}).json()
        done=client.get(PREFIX+'/jobs/'+job['id']).json()
        assert done['status']=='completed',done
        assert sum('messages' in r for r in requests)==1
