"""Project replacement for the source module absent from the supplied skill.
Semantic runs, native scripts and cached EQ fields; requires Word/WPS review.
"""
import re
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

SUB = str.maketrans('₀₁₂₃₄₅₆₇₈₉','0123456789')
SUP = str.maketrans('⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻','0123456789+-')


def _formula(text):
    match = re.search(r'(?:\^([0-9]*[+-])|([+-]))$', text)
    charge = (match.group(1) or match.group(2)) if match else None
    body = text[:match.start()] if match else text
    result = [{'text':p, **({'sub':True} if p.isdigit() else {})} for p in re.findall(r'\d+|\D+',body)]
    if charge: result.append({'text':charge,'sup':True,'charge':True})
    return result


def normalize_runs(value):
    if isinstance(value, list):
        result=[]
        for item in value:
            if not isinstance(item,dict) or not isinstance(item.get('text'),str):
                raise ValueError('run 必须是含字符串 text 的扁平对象')
            if item.get('sub') and (item.get('sup') or item.get('charge')):
                raise ValueError('不能同时使用上标与下标')
            for run in normalize_runs(item['text']):
                result.append({**run, **{k:v for k,v in item.items() if k!='text'}})
        return result
    if not isinstance(value,str): raise ValueError('内容必须为字符串或 run 数组')
    result=[]
    pattern = r'\[([^\[\]]+)\]|([₀₁₂₃₄₅₆₇₈₉]+)|([⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)|(\u3000{4,})'
    position=0
    for match in re.finditer(pattern,value):
        if match.start()>position: result.append({'text':value[position:match.start()]})
        formula,sub,sup,blank=match.groups()
        if formula: result.extend(_formula(formula))
        elif sub: result.append({'text':sub.translate(SUB),'sub':True})
        elif sup:
            text=sup.translate(SUP)
            result.append({'text':text,'sup':True,**({'charge':True} if text.endswith(('+','-')) else {})})
        else: result.append({'text':blank,'underline':True})
        position=match.end()
    if position<len(value):result.append({'text':value[position:]})
    return result or [{'text':''}]


def _field_char(paragraph,kind):
    run=paragraph.add_run(); run.font.name='Times New Roman'; element=OxmlElement('w:fldChar');element.set(qn('w:fldCharType'),kind);run._r.append(element)


def _instruction(paragraph,text):
    run=paragraph.add_run();run.font.name='Times New Roman';element=OxmlElement('w:instrText');element.set(qn('xml:space'),'preserve');element.text=text;run._r.append(element)


def _native(paragraph,item):
    run=paragraph.add_run(item['text']);run.font.name='Times New Roman'
    run.font.subscript=bool(item.get('sub'))
    run.font.superscript=bool(item.get('sup') or item.get('charge'))
    for key in ('bold','italic','underline'):
        if key in item: setattr(run,key,bool(item[key]))
    return run


def add_docx_runs(paragraph,value):
    runs=normalize_runs(value)
    pending=[]
    for item in runs:
        if item.get('sub'):
            pending.append(item);continue
        if item.get('charge'):
            atoms=''.join(r['text'] for r in pending)
            _field_char(paragraph,'begin')
            _instruction(paragraph,' eq \\o\\al(\\s\\up8('+item['text']+'),\\s\\do4('+atoms+')) ')
            _field_char(paragraph,'separate')
            for p in pending:_native(paragraph,p)
            _native(paragraph,item)
            _field_char(paragraph,'end');pending=[];continue
        for p in pending:_native(paragraph,p)
        pending=[]
        if item.get('condition') or item.get('isotope'):
            _field_char(paragraph,'begin')
            if item.get('isotope'):
                iso=item['isotope']; _instruction(paragraph,f" eq \\o(\\s\\up11({iso['mass']}),\\s\\do4({iso['atomic']})) ")
            else:_instruction(paragraph,' eq \\o(=====,\\s\\up8('+item['text']+')) ')
            _field_char(paragraph,'separate')
            if item.get('isotope'):
                _native(paragraph,{'text':str(item['isotope']['mass']),'sup':True})
                _native(paragraph,{'text':str(item['isotope']['atomic']),'sub':True})
                _field_char(paragraph,'end');_native(paragraph,{'text':item['text']})
            else:
                # Native OMML upper limit preserves the stacked condition cache.
                math=OxmlElement('m:oMath');limit=OxmlElement('m:limUpp')
                for tag,text in [('m:e','====='),('m:lim',item['text'])]:
                    node=OxmlElement(tag);r=OxmlElement('m:r');t=OxmlElement('m:t');t.text=text;r.append(t);node.append(r);limit.append(node)
                math.append(limit);paragraph._p.append(math);_field_char(paragraph,'end')
        else:_native(paragraph,item)
    for p in pending:_native(paragraph,p)
