import copy
import json
import pytest

from backend.app.shared.chemistry.validation import validate_study_guide_result
from backend.app.shared.chemistry.repair import apply_equation_repairs,equation_repair_messages,EquationBalanceError


def targets_for(value):
    raw={'sections':[{'title':'反应方程式','blocks':[{'type':'paragraph','content':value}]}]}
    with pytest.raises(EquationBalanceError) as error:
        validate_study_guide_result(raw)
    return raw,error.value.targets


def test_transformation_questions_are_not_treated_as_incomplete_reactions():
    rows=[['[NaOH] → [NaCl]',None,None],['[CuO] → [Cu(OH)2]',None,None],
          ['[HCl] → [AgCl]',None,None],['[CO2] → [CaCO3]',None,None]]
    raw={'sections':[{'title':'课堂辨析：能否一步转化？','blocks':[
        {'type':'paragraph','content':'判断下列转化能否通过一步反应实现。若能，写方程式；若不能，设计两步路径。'},
        {'type':'table','headers':['转化','能/不能','化学方程式或路径'],'rows':copy.deepcopy(rows)}]}]}
    validate_study_guide_result(raw)
    assert raw['sections'][0]['blocks'][1]['rows']==rows


def test_actual_equation_column_still_checks_balance_with_conversion_title():
    raw={'sections':[{'title':'物质转化','blocks':[{'type':'table',
        'headers':['化学方程式'],'rows':[['NaOH → NaCl']]}]}]}
    with pytest.raises(EquationBalanceError):validate_study_guide_result(raw)


@pytest.mark.parametrize('original,corrected',[
    ('NaOH = NaCl','NaOH + HCl = NaCl + H2O'),
    ('CaCO3 = CaO + CO',[{'text':'[CaCO3] '},{'text':'高温','condition':True},{'text':' [CaO] + [CO2]↑'}]),
    ('Mg + O2 = MgO3','2Mg + O2 = 2MgO'),
    ('HCl = AgCl','HCl + AgNO3 = AgCl↓ + HNO3'),
])
def test_whole_equation_repair_can_fix_species_reagents_products_and_conditions(original,corrected):
    raw,targets=targets_for(original)
    fixed,notes=apply_equation_repairs(raw,targets,{'repairs':[{'id':'equation-1','content':corrected}]})
    validate_study_guide_result(fixed)
    assert fixed!=raw
    assert raw['sections'][0]['blocks'][0]['content']==original
    assert notes[0]['method']=='equation_full_model'


def test_repair_prompt_receives_local_teaching_context_and_reference_evidence():
    raw={'outline':{'sections':[{'title':'碱的化学性质','blocks':[{'type':'table',
        'headers':['反应','条件'],'rows':[['NaOH = NaCl','与酸中和']]}]}]}}
    with pytest.raises(EquationBalanceError) as error:validate_study_guide_result(raw)
    messages=equation_repair_messages(error.value.targets,context={
        'teacher_request':'设计中和反应任务','sources':[{'id':'src','evidence_excerpt':'氢氧化钠与盐酸生成氯化钠和水。'}]})
    sent=json.loads(messages[1]['content'])
    assert sent['equations'][0]['context']['section_title']=='碱的化学性质'
    assert sent['equations'][0]['context']['table_row'][1]=='与酸中和'
    assert sent['context']['sources'][0]['id']=='src'
    assert '只修改化学计量数' not in messages[0]['content']


def test_full_repair_checks_each_equation_in_multi_step_route():
    raw,targets=targets_for('CuO = Cu(OH)2')
    route='CuO + 2HCl = CuCl2 + H2O\nCuCl2 + 2NaOH = Cu(OH)2↓ + 2NaCl'
    fixed,_=apply_equation_repairs(raw,targets,{'repairs':[{'id':'equation-1','content':route}]})
    validate_study_guide_result(fixed)
    with pytest.raises(ValueError,match='守恒'):
        apply_equation_repairs(raw,targets,{'repairs':[{'id':'equation-1','content':route.replace('2NaCl','NaCl')}]})


def test_full_repair_accepts_balanced_ionic_equation_and_rejects_charge_mismatch():
    raw,targets=targets_for('FeCl3 + H2O = Fe(OH)2 + HCl')
    correct=[{'text':'[Fe^3+] + 3[H2O] '},{'text':'△','condition':True},{'text':' [Fe(OH)3] + 3[H+]'}]
    apply_equation_repairs(raw,targets,{'repairs':[{'id':'equation-1','content':correct}]})
    with pytest.raises(ValueError,match='电荷'):
        apply_equation_repairs(raw,targets,{'repairs':[{'id':'equation-1','content':'[Fe^2+] + 3H2O = Fe(OH)3 + 3[H+]'}]})


@pytest.mark.parametrize('left,right', [('',' → '), (' → ',''), (' = ',' → ')])
def test_model_condition_with_explicit_arrow_is_one_reaction_boundary(left,right):
    raw,targets=targets_for('CaCO3 = CaO + CO')
    corrected=[{'text':'[CaCO3]'+left},{'text':'高温','condition':True},{'text':right+'[CaO] + [CO2]↑'}]
    fixed,_=apply_equation_repairs(raw,targets,{'repairs':[{'id':'equation-1','content':corrected}]})
    validate_study_guide_result(fixed)
