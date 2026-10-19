#!/usr/bin/env python3
"""Generate template-based chemistry teaching files from a local JSON content plan."""
import argparse
import copy
import json
from pathlib import Path
import re
import sys
import tempfile
from docx_tools import generate_outline, generate_paper, generate_answers, validate_paper
from ppt_tools import generate_pptx
from validate_outputs import validate_paths

CATEGORIES={'textbook','teacher_book','exercises','practice','exam'}
REQUIRED=CATEGORIES-{'practice'}

def check_sources(data):
    sources=data.get('sources',[]);ids={};issues=[]
    for source in sources:
        if not isinstance(source,dict) or not all(source.get(k) for k in ('id','category','title','locator','evidence')):
            raise ValueError('每个来源需要 id/category/title/locator/evidence；evidence 为已核对的摘录或文件位置')
        if source['category'] not in CATEGORIES:raise ValueError('未知资料分类：'+str(source['category']))
        if source['id'] in ids:raise ValueError('来源ID重复：'+source['id'])
        ids[source['id']]=source
    verified={x['category'] for x in sources if x.get('verified') is True}
    for category in sorted(REQUIRED-verified):issues.append('缺少已核实资料分类：'+category)
    for group in ('choice','written','optional'):
        for i,q in enumerate(data.get('paper',{}).get(group,[]),1):
            refs=q.get('source_ids',[])
            if not refs:issues.append(f'{group} 第{i}题缺少来源；如为自编题须另经教师审核')
            if not isinstance(refs,list):raise ValueError('source_ids 必须为列表')
            if any(s not in ids for s in refs):raise ValueError(f'{group} 第{i}题引用了不存在的来源ID')
            if any(ids[s].get('verified') is not True for s in refs):issues.append(f'{group} 第{i}题来源未核实')
            q['source']='；'.join(ids[s]['title']+' '+str(ids[s]['locator']) for s in refs)
    if 'practice' not in verified:issues.append('必刷题来源缺失：按原规范回退到其他课时题库并注明')
    return issues

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--output-dir',required=True,type=Path)
    parser.add_argument('--allow-unverified',action='store_true',help='允许生成带待核验标记的草案，不等于来源审核通过')
    args=parser.parse_args()
    try:
        data=json.loads(args.input.read_text(encoding='utf-8'))
        if not isinstance(data,dict):raise ValueError('输入必须为JSON对象')
        for key in ('title','outline','paper','slides'):
            if not data.get(key):raise ValueError('缺少字段：'+key)
        data=copy.deepcopy(data)
        validate_paper(data['paper'])
        gaps=check_sources(data)
        # Missing optional practice source is informational, not a publication blocker.
        blockers=[x for x in gaps if not x.startswith('必刷题来源缺失')]
        args.output_dir.mkdir(parents=True,exist_ok=True)
        report_path=args.output_dir/'generation_report.json'
        stem=re.sub(r'[^\w\-\u4e00-\u9fff]+','_',str(data['title']),flags=re.UNICODE).strip('_')[:70] or 'lesson'
        draft=bool(blockers)
        if draft:stem='待核验_'+stem
        outputs=[args.output_dir/(stem+x) for x in ('_导学提纲.docx','_限时练.docx','_答案.docx','_课件.pptx')]
        if any(x.exists() for x in outputs) or report_path.exists():raise ValueError('输出文件已存在，请使用新的任务输出目录，避免覆盖')
        report={'status':'blocked_missing_sources' if draft else 'generated_pending_visual_review','source_issues':gaps,'files':[],
                'review_required':['检查来源与答案','打开Word核查EQ域显示与分页','打开PPT检查字体、溢出和图片'],
                'notes':['verified 为调用者核对记录，脚本无法独立认证资料真伪。','结构检查通过不代表教学或视觉验收通过。']}
        if draft and not args.allow_unverified:
            report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(report,ensure_ascii=False));return 2
        if draft:
            for key in ('outline','paper'):data[key]['title']='待核验 '+data[key]['title']
            for slide in data['slides']:slide['title']='待核验 '+slide['title']
        with tempfile.TemporaryDirectory(prefix='.chemistry-',dir=args.output_dir) as tmp:
            working=[Path(tmp)/x.name for x in outputs]
            generate_outline(data['outline'],working[0])
            generate_paper(data['paper'],working[1],base_dir=args.input.resolve().parent)
            generate_answers(data['paper'],working[2])
            generate_pptx(data['slides'],working[3],base_dir=args.input.resolve().parent)
            validation=validate_paths(working)
            # Store portable locations rather than a soon-deleted temporary directory.
            for level in ('issues','warnings'):
                for issue in validation.get(level,[]):issue['file']=Path(issue['file']).name
            report['validation']=validation
            if not validation['passed']:
                report['status']='failed_validation'
            else:
                for src,dst in zip(working,outputs):src.replace(dst)
                report['files']=[str(x.resolve()) for x in outputs]
                if draft:report['status']='draft_missing_sources'
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False));return 0 if report['files'] else 2
    except (ValueError,KeyError,TypeError,OSError) as ex:
        print('生成失败：'+str(ex),file=sys.stderr);return 2

if __name__=='__main__':raise SystemExit(main())
