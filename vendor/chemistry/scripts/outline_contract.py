"""Normalize supported outline formats and validate before any Office mutation."""
import copy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from jsonschema import Draft202012Validator
from chemistry_runs import normalize_runs

SCHEMA=Path(__file__).resolve().parents[1]/'references/outline.schema.json'

class OutlineValidationError(ValueError):
    def __init__(self,issues):
        self.issues=issues
        super().__init__('; '.join(x['path']+': '+x['message'] for x in issues))

def fail(path,message,code='INVALID_CONTENT'):
    raise OutlineValidationError([{'path':path,'code':code,'message':message}])

def _allowed(obj,keys,path):
    if not isinstance(obj,dict):fail(path,'必须是对象')
    unknown=set(obj)-set(keys)
    if unknown:fail(path+'.'+sorted(unknown)[0],'不支持的字段；不能静默丢弃内容','UNKNOWN_FIELD')

def _legacy_text(value,path,depth=0):
    """Only the documented legacy eq format may mix strings/runs/nested lists."""
    if isinstance(value,str):return value
    if isinstance(value,dict):
        if not isinstance(value.get('text'),str):fail(path,'run需要字符串text')
        return [copy.deepcopy(value)]
    if not isinstance(value,list) or not value:fail(path,'必须是文本、run或非空旧版方程式列表')
    if depth>6:fail(path,'旧版公式嵌套过深')
    runs=[]
    for i,item in enumerate(value):
        converted=_legacy_text(item,f'{path}[{i}]',depth+1)
        runs.extend([{'text':converted}] if isinstance(converted,str) else converted)
    return runs

def _legacy_blocks(body,path):
    if not isinstance(body,list) or not body:fail(path,'body必须为非空数组')
    result=[]
    for i,block in enumerate(body):
        p=f'{path}[{i}]'
        if not isinstance(block,dict):fail(p,'旧版block必须为对象')
        kind=block.get('kind')
        if kind in ('text','lead','eq'):
            _allowed(block,('kind','value','label'),p)
            if 'value' not in block:fail(p+'.value','缺少内容')
            value=_legacy_text(block['value'],p+'.value')
            label=block.get('label')
            if label is not None:
                if not isinstance(label,str):fail(p+'.label','必须为字符串')
                if label:value=label+'　'+value if isinstance(value,str) else [{'text':label+'　'}]+value
            result.append({'type':'paragraph','content':value})
        elif kind=='table':
            _allowed(block,('kind','headers','rows','widths','widths_cm','note','min_row_height_cm'),p)
            if 'widths' in block and 'widths_cm' in block:fail(p,'widths和widths_cm不能同时使用')
            table={'type':'table','headers':copy.deepcopy(block.get('headers')),'rows':copy.deepcopy(block.get('rows'))}
            for old,new in [('widths','widths_cm'),('widths_cm','widths_cm'),('min_row_height_cm','min_row_height_cm')]:
                if old in block:table[new]=copy.deepcopy(block[old])
            result.append(table)
            if 'note' in block:
                if not isinstance(block['note'],str):fail(p+'.note','必须为字符串')
                if block['note']:result.append({'type':'paragraph','content':block['note']})
        else:fail(p+'.kind',f'不支持的旧版block类型：{kind}；请使用段落或原生表格','UNSUPPORTED_BLOCK')
    return result

@lru_cache(maxsize=1)
def _validator():
    schema=json.loads(SCHEMA.read_text(encoding='utf-8'))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)

def _path(parts):
    p='$.outline'
    for part in parts:p+=f'[{part}]' if isinstance(part,int) else '.'+str(part)
    return p

def normalize_outline(data):
    if not isinstance(data,dict):fail('$.outline','必须为对象')
    _allowed(data,('title','goals','sections','thinking','schedule_note','groups'),'$.outline')
    result=copy.deepcopy(data)
    if 'groups' in result:
        if 'sections' in result:fail('$.outline','groups和sections不能同时出现')
        groups=result.pop('groups');sections=[]
        if not isinstance(groups,list) or not groups:fail('$.outline.groups','必须为非空数组')
        for gi,group in enumerate(groups):
            gp=f'$.outline.groups[{gi}]';_allowed(group,('heading','blocks'),gp)
            if not isinstance(group.get('heading'),str) or not group['heading'].strip():fail(gp+'.heading','需要非空组标题')
            if not isinstance(group.get('blocks'),list) or not group['blocks']:fail(gp+'.blocks','必须为非空数组')
            for bi,section in enumerate(group['blocks']):
                sp=f'{gp}.blocks[{bi}]';_allowed(section,('kind','title','body'),sp)
                if section.get('kind')!='section':fail(sp+'.kind','只接受section类型')
                sections.append({'group':group['heading'],'title':section.get('title'),'blocks':_legacy_blocks(section.get('body'),sp+'.body')})
        result['sections']=sections
    sections=result.get('sections')
    if isinstance(sections,list):
        for si,section in enumerate(sections):
            sp=f'$.outline.sections[{si}]';_allowed(section,('id','title','group','paragraphs','blocks'),sp)
            if 'paragraphs' in section:
                if 'blocks' in section:fail(sp,'paragraphs与blocks不能同时出现')
                values=section.pop('paragraphs')
                if not isinstance(values,list):fail(sp+'.paragraphs','必须是数组')
                section['blocks']=[{'type':'paragraph','content':copy.deepcopy(x)} for x in values]
            section.setdefault('id',f'section-{si+1:03d}')
            if isinstance(section.get('blocks'),list):
                for bi,block in enumerate(section['blocks']):
                    if isinstance(block,dict):block.setdefault('id',f'{section["id"]}-block-{bi+1:03d}')
    errors=list(_validator().iter_errors(result))
    if errors:
        issues=[]
        for error in errors[:20]:
            leaves=list(error.context)
            # Preserve the block location while showing more useful run errors when available.
            chosen=max(leaves,key=lambda e:len(list(e.absolute_path))) if leaves else error
            issues.append({'path':_path(chosen.absolute_path),'code':'SCHEMA_VALIDATION','message':chosen.message})
        raise OutlineValidationError(issues)
    if not result['title'].strip():fail('$.outline.title','标题不能为空白')
    ids=set()
    def check_id(value,path):
        if value in ids:fail(path,'ID重复；每个小节和block的ID须唯一','DUPLICATE_ID')
        ids.add(value)
    def check_text(value,path,nonempty=False):
        try:runs=normalize_runs(value)
        except (ValueError,TypeError,KeyError) as ex:fail(path,str(ex),'INVALID_RUN')
        if nonempty and not ''.join(r['text'] for r in runs).strip():fail(path,'文本不能为空白')
        for i,r in enumerate(runs):
            rp=f'{path}[{i}]'
            if r.get('condition') and (not r['text'].strip() or any(c in r['text'] for c in '\\(),')):fail(rp,'反应条件含不支持的域字符或为空')
            if sum(bool(r.get(k)) for k in ('condition','charge','isotope'))>1:fail(rp,'condition/charge/isotope不能同时设置')
    for gi,goal in enumerate(result['goals']):check_text(goal,f'$.outline.goals[{gi}]',True)
    for ti,text in enumerate(result.get('thinking',[])):check_text(text,f'$.outline.thinking[{ti}]',True)
    for si,section in enumerate(result['sections']):
        sp=f'$.outline.sections[{si}]';check_id(section['id'],sp+'.id')
        if not section['title'].strip():fail(sp+'.title','小节标题不能为空白')
        for bi,block in enumerate(section['blocks']):
            bp=f'{sp}.blocks[{bi}]';check_id(block['id'],bp+'.id')
            if block['type']=='paragraph':check_text(block['content'],bp+'.content');continue
            if block['type']=='image':
                if not block['caption'].strip():fail(bp+'.caption','图片说明不能为空白')
                continue
            n=len(block['headers'])
            for hi,header in enumerate(block['headers']):check_text(header,f'{bp}.headers[{hi}]',True)
            for ri,row in enumerate(block['rows']):
                if len(row)!=n:fail(f'{bp}.rows[{ri}]',f'应有{n}列，实际{len(row)}列','TABLE_COLUMN_COUNT')
                for ci,cell in enumerate(row):
                    if cell is not None:check_text(cell,f'{bp}.rows[{ri}][{ci}]')
            if 'widths_cm' in block:
                widths=block['widths_cm']
                if len(widths)!=n:fail(bp+'.widths_cm',f'列宽数应为{n}','TABLE_WIDTH_COUNT')
                if any(not math.isfinite(w) or w<=0 for w in widths):fail(bp+'.widths_cm','列宽须为有限正数')
            height=block.get('min_row_height_cm',0.75)
            if not math.isfinite(height):fail(bp+'.min_row_height_cm','行高须为有限数值')
    return result

def outline_digest(data):
    encoded=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()
