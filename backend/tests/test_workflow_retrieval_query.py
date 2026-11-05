"""检索词保留教学内容，生成控制信息不参与召回。"""
from backend.app.shared.workflow.retrieval_query import build_retrieval_query


def test_retrieval_preserves_content_with_colon_and_page_requirement():
    query = build_retrieval_query({'chapter':'氧化还原反应'},
                                  '增加实验：钠与水反应现象和方程式。围绕电子转移制作10页课件。')
    assert '钠与水反应现象和方程式' in query
    assert '电子转移' in query
    assert '10页' not in query


def test_teacher_edited_focus_overrides_structured_focus():
    query = build_retrieval_query({'chapter':'离子反应','options':{'focus':['钠与水反应']}},
                                  '本课重点：离子方程式书写\n课堂时长：30分钟')
    assert '离子方程式书写' in query
    assert '钠与水反应' not in query
    assert '30分钟' not in query


def test_format_words_do_not_remove_the_requested_chemistry_topic():
    for prompt, topic in [('用表格格式总结原电池工作原理', '原电池工作原理'), ('用PPT格式介绍氯碱工业', '氯碱工业')]:
        query = build_retrieval_query({'chapter':'氧化还原反应'}, prompt)
        assert topic in query
        assert '格式' not in query


def test_practice_edited_focus_does_not_restore_old_focus_or_question_settings():
    query = build_retrieval_query({'chapter':'硫及其化合物','options':{'focus':['浓硫酸吸水性']}},
                                  '重点练什么：二氧化硫漂白性\n题型和数量：10道选择题\n题目难度：中等')
    assert '二氧化硫漂白性' in query
    for noise in ['浓硫酸吸水性', '选择题', '中等', '题型和数量']:
        assert noise not in query
