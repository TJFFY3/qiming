#!/usr/bin/env python3
"""Validate, normalize and render ONE outline. No model-generated helper scripts."""
import argparse
import copy
import json
from pathlib import Path
import re
import tempfile
from docx import Document
from outline_contract import normalize_outline, outline_digest, OutlineValidationError, fail
from docx_tools import generate_outline
from validate_outputs import validate_paths


def prepare_document(data):
    if not isinstance(data,dict):fail('$','输入必须为JSON对象')
    raw=data.get('outline') if 'outline' in data else data
    canonical=normalize_outline(raw)
    sources=data.get('sources',[]) if 'outline' in data else []
    if not isinstance(sources,list):fail('$.sources','必须为数组')
    trusted=[]
    for i,source in enumerate(sources):
        if not isinstance(source,dict):fail(f'$.sources[{i}]','必须为对象')
        if source.get('verified') is True and source.get('category') in ('textbook','teacher_book'):
            if all(isinstance(source.get(k),str) and source[k].strip() for k in ('title','locator','evidence')):trusted.append(source)
    issues=[]
    if not trusted:issues.append('未提供已核对的教材或教师用书（title、locator、evidence及verified=true）')
    for key,label in [('source_gaps','资料缺口'),('source_conflicts','资料冲突')]:
        values=data.get(key,[]) if 'outline' in data else []
        if values is None:values=[]
        if not isinstance(values,list):fail('$.'+key,'必须为数组')
        for item in values:
            if item:issues.append(label+'：'+(item if isinstance(item,str) else json.dumps(item,ensure_ascii=False)))
    if canonical['title'].lstrip().startswith('待核验'):issues.append('原内容已标记待核验，不能自动升级为正式成果')
    return canonical,issues


def render_document(data,output_dir,allow_unverified=False,version='v001',previous=None):
    if not isinstance(version,str) or not re.fullmatch(r'v[0-9]{3,}',version):fail('$.version','版本号须为v001、v002等')
    canonical,source_issues=prepare_document(data)
    if previous is not None and not isinstance(previous,dict):fail('$.previous','必须为对象')
    draft=bool(source_issues) or bool((previous or {}).get('draft'))
    if draft and not allow_unverified:fail('$.sources','；'.join(source_issues) or '沿用待核验草案，需显式 --allow-unverified','MISSING_SOURCES')
    out=Path(output_dir).expanduser().resolve()
    if out.exists():raise FileExistsError('输出目录已存在；请使用新目录，禁止覆盖旧版本：'+str(out))
    content_tables=[b for s in canonical['sections'] for b in s['blocks'] if b['type']=='table']
    statistics={'sections':len(canonical['sections']),'paragraphs':sum(b['type']=='paragraph' for s in canonical['sections'] for b in s['blocks']),'content_tables':len(content_tables),'data_rows':sum(len(t['rows']) for t in content_tables),'note_rows':25}
    out.parent.mkdir(parents=True,exist_ok=True)
    files={name:str(out/filename) for name,filename in [('outline','outline.docx'),('content','content.json'),('source_input','source_input.json'),('report','generation_report.json')]}
    with tempfile.TemporaryDirectory(prefix='.outline-',dir=out.parent) as tmp:
        stage=Path(tmp)/'version';stage.mkdir()
        display=copy.deepcopy(canonical)
        if draft and not display['title'].lstrip().startswith('待核验'):display['title']='待核验 '+display['title']
        generate_outline(display,stage/'outline.docx')
        doc=Document(stage/'outline.docx')
        if len(doc.tables)!=len(content_tables)+1:fail('$.outline','生成的教学表格数与输入不一致，拒绝交付','TABLE_LOSS')
        for i,(table,expected) in enumerate(zip(doc.tables,content_tables)):
            if len(table.rows)!=len(expected['rows'])+1 or len(table.columns)!=len(expected['headers']):fail(f'$.outline.tables[{i}]','生成的行列数与输入不一致','TABLE_SIZE')
        if len(doc.tables[-1].rows)!=25:fail('$.outline.notes','笔记区域行数不一致')
        validation=validate_paths([stage/'outline.docx'])
        for severity in ('issues','warnings'):
            for issue in validation.get(severity,[]):issue['file']='outline.docx'
        if not validation['passed']:
            raise OutlineValidationError([{'path':i.get('location','outline.docx'),'code':i.get('code','OUTPUT_VALIDATION'),'message':i['message']} for i in validation['issues']])
        report={'status':'draft_missing_sources' if draft else 'generated_pending_visual_review','draft':draft,'version':version,'product':'outline_only','content_sha256':outline_digest(canonical),'files':files,'statistics':statistics,'source_issues':source_issues,'validation':validation,'review_required':['核对资料来源、教材版次及页码','在Word/WPS检查化学域显示、表格分页及答题空间'],'notes':['来源verified由执行者核对，脚本不认证资料真伪。','教学表格按输入顺序生成原生Word表格；列宽比例缩放至可打印宽度。','结构检查不等同于教学质量或视觉验收。']}
        if previous is not None:report['previous']=copy.deepcopy(previous)
        (stage/'content.json').write_text(json.dumps(canonical,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        (stage/'source_input.json').write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        (stage/'generation_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
        # Rename one complete directory, with no pre-existing target. On POSIX an
        # existing empty directory could be replaced; reject it again first.
        if out.exists():raise FileExistsError('输出目录已存在，禁止覆盖：'+str(out))
        stage.rename(out)
    return report


def _read_json(path):
    def invalid(value):raise ValueError('JSON不允许非有限数值：'+value)
    return json.loads(Path(path).read_text(encoding='utf-8'),parse_constant=invalid)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--version',default='v001')
    parser.add_argument('--check-only',action='store_true',help='仅校验/标准化，不生成文件，不要求试卷/PPT/高考题源')
    parser.add_argument('--allow-unverified',action='store_true',help='允许输出带待核验标题的草案')
    args=parser.parse_args()
    try:
        data=_read_json(args.input)
        if args.check_only:
            canonical,issues=prepare_document(data)
            result={'status':'validated','content_sha256':outline_digest(canonical),'source_issues':issues,'sections':len(canonical['sections'])}
        else:
            if args.output_dir is None:fail('$.output_dir','生成时需要 --output-dir')
            result=render_document(data,args.output_dir,args.allow_unverified,args.version)
        print(json.dumps(result,ensure_ascii=False));return 0
    except OutlineValidationError as ex:
        print(json.dumps({'status':'invalid_input','errors':ex.issues},ensure_ascii=False));return 2
    except json.JSONDecodeError as ex:
        print(json.dumps({'status':'invalid_input','errors':[{'path':f'$ (line {ex.lineno}, column {ex.colno})','code':'JSON_PARSE','message':ex.msg}]},ensure_ascii=False));return 2
    except (OSError,ValueError,TypeError,KeyError) as ex:
        print(json.dumps({'status':'failed','errors':[{'path':'$','code':type(ex).__name__,'message':str(ex)}]},ensure_ascii=False));return 2

if __name__=='__main__':raise SystemExit(main())
