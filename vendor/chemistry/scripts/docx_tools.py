"""Fill bundled templates while retaining their section and style definitions."""
from pathlib import Path
import math
import re
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_ROW_HEIGHT_RULE, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from chemistry_runs import add_docx_runs, normalize_runs

ROOT=Path(__file__).resolve().parents[1]

def _template(name):
    d=Document(ROOT/'assets'/'templates'/name)
    body=d._element.body
    for node in list(body):
        if node.tag!=qn('w:sectPr'):body.remove(node)
    d.core_properties.author='';d.core_properties.last_modified_by='';d.core_properties.title=''
    for section in d.sections:
        section.top_margin=section.bottom_margin=section.left_margin=section.right_margin=Cm(1.5)
    return d

def fix_docx_fonts(d):
    root=d.styles.element
    for node in root.iter(qn('w:rFonts')):
        for name in ('asciiTheme','hAnsiTheme','cstheme'):node.attrib.pop(qn('w:'+name),None)
        node.set(qn('w:ascii'),'Times New Roman');node.set(qn('w:hAnsi'),'Times New Roman');node.set(qn('w:cs'),'Times New Roman')
    default=root.find(qn('w:docDefaults'))
    if default is None:default=OxmlElement('w:docDefaults');root.insert(0,default)
    rdefault=default.find(qn('w:rPrDefault'))
    if rdefault is None:rdefault=OxmlElement('w:rPrDefault');default.append(rdefault)
    rpr=rdefault.find(qn('w:rPr'))
    if rpr is None:rpr=OxmlElement('w:rPr');rdefault.append(rpr)
    fonts=rpr.find(qn('w:rFonts'))
    if fonts is None:fonts=OxmlElement('w:rFonts');rpr.append(fonts)
    for key in ('ascii','hAnsi','cs'):fonts.set(qn('w:'+key),'Times New Roman')
    fonts.set(qn('w:eastAsia'),'宋体')
    for name in ('Normal','Body Text','Plain Text'):
        if name in d.styles:
            d.styles[name].font.name='Times New Roman';d.styles[name].font.size=Pt(11)
            d.styles[name].paragraph_format.line_spacing=1.1
    for node in d._element.iter(qn('w:rFonts')):
        for name in ('asciiTheme','hAnsiTheme','cstheme'):node.attrib.pop(qn('w:'+name),None)
        for key in ('ascii','hAnsi','cs'):node.set(qn('w:'+key),'Times New Roman')
    return d

def _p(d,value='',bold=False,size=11,cjk='宋体',align=None):
    p=d.add_paragraph();p.paragraph_format.line_spacing=1.1
    p.paragraph_format.space_after=Pt(4)
    if align is not None:p.alignment=align
    # Long full-width blanks must be explicitly underlined.
    if isinstance(value,str):
        parts=re.split(r'(　{4,}|_{3,})',value)
        for part in parts:
            if not part:continue
            if re.fullmatch(r'　{4,}|_{3,}',part):add_docx_runs(p,[{'text':part.replace('_',' '),'underline':True}])
            else:add_docx_runs(p,part)
    else:add_docx_runs(p,value)
    for r in p.runs:
        r.font.size=Pt(size)
        if bold:r.bold=True
        r._r.get_or_add_rPr().find(qn('w:rFonts')).set(qn('w:eastAsia'),cjk)
    return p

def _title(d,title,size):return _p(d,title,True,size,'黑体',WD_ALIGN_PARAGRAPH.CENTER)
def _heading(d,text):
    p=_p(d,text,True,12,'黑体');p.paragraph_format.keep_with_next=True;return p

def _save(d,path):
    fix_docx_fonts(d);path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);d.save(path);return path

def _outline_table(d,block):
    """Render editable cells; widths are ratios fitted to the printable area.

    The template's 15.4 cm printable width is an upper bound. Integer twip
    allocation keeps the table grid, table width and every cell width equal.
    """
    section=d.sections[-1]
    available=min(int(Cm(15.4)/635),int((section.page_width-section.left_margin-section.right_margin)/635))
    ratios=block.get('widths_cm',[1]*len(block['headers']))
    total=sum(ratios)
    widths=[int(available*ratio/total) for ratio in ratios]
    widths[-1]+=available-sum(widths)
    table=d.add_table(rows=1,cols=len(widths));table.style='Table Grid';table.autofit=False
    table._tbl.tblPr.find(qn('w:tblW')).set(qn('w:type'),'dxa')
    table._tbl.tblPr.find(qn('w:tblW')).set(qn('w:w'),str(available))
    for col,width in zip(table.columns,widths):col.width=width*635
    minimum_twips=math.ceil(Cm(max(.75,block.get('min_row_height_cm',.75)))/635)
    for index,values in enumerate([block['headers']]+block['rows']):
        row=table.rows[0] if index==0 else table.add_row()
        row.height=minimum_twips*635;row.height_rule=WD_ROW_HEIGHT_RULE.AT_LEAST
        properties=row._tr.get_or_add_trPr()
        properties.append(OxmlElement('w:cantSplit'))
        if index==0:
            repeat=OxmlElement('w:tblHeader');repeat.set(qn('w:val'),'true');properties.append(repeat)
        for cell,value,width in zip(row.cells,values,widths):
            cell.width=width*635
            cell.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            initial=cell.paragraphs[0]._p
            if isinstance(value,list):
                runs=[]
                for run in value:
                    if any(run.get(key) for key in ('charge','condition','isotope')):
                        runs.append(run);continue
                    for part in re.split(r'(_{3,})',run['text']):
                        if part:runs.append({**run,'text':part.replace('_',' ') if re.fullmatch(r'_{3,}',part) else part,**({'underline':True} if re.fullmatch(r'_{3,}',part) else {})})
                value=runs
            # Use the same semantic chemistry-run path as ordinary paragraphs.
            _p(cell,'' if value is None else value,bold=index==0,align=WD_ALIGN_PARAGRAPH.CENTER if index==0 else None)
            cell._tc.remove(initial)
            if index==0:
                shade=OxmlElement('w:shd');shade.set(qn('w:fill'),'E7EEF5');cell._tc.get_or_add_tcPr().append(shade)
    return table

def generate_outline(data,output_path):
    # Validate every block before opening a template or touching the destination.
    from outline_contract import normalize_outline
    data=normalize_outline(data)
    d=_template('导学提纲模板.docx');_title(d,data['title']+'导学提纲',16)
    _p(d,'班级________　姓名________　小组________')
    _heading(d,'【学习目标】')
    for text in data['goals']:_p(d,text)
    _heading(d,'【基础自学】')
    if data.get('schedule_note'):_p(d,data['schedule_note'])
    group='【基础自学】'
    for section in data['sections']:
        next_group=section.get('group')
        if next_group and next_group!=group:
            _heading(d,next_group);group=next_group
        _heading(d,section['title'])
        for block in section['blocks']:
            if block['type']=='table':_outline_table(d,block)
            else:_p(d,block['content'])
    for thought in data.get('thinking',[]):
        p=_p(d,'思考　',True,11,'楷体_GB2312');add_docx_runs(p,thought)
    _p(d,'注：请在空白区完整写出你的疑惑，以便交流探讨。',cjk='楷体_GB2312')
    _heading(d,'【笔记区域】')
    table=d.add_table(rows=25,cols=1);table.autofit=False;table.columns[0].width=Cm(15.4)
    for row in table.rows:row.height=Cm(0.6)
    borders=OxmlElement('w:tblBorders')
    for edge in ('top','left','bottom','right','insideH','insideV'):
        n=OxmlElement('w:'+edge);n.set(qn('w:val'),'single');n.set(qn('w:sz'),'4');n.set(qn('w:color'),'808080');borders.append(n)
    table._tbl.tblPr.append(borders)
    return _save(d,output_path)

def _number(value,label):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:raise ValueError(label+' 必须为正数')
    return value

def validate_paper(data):
    if not data.get('title'):raise ValueError('缺少试卷 title')
    choice=data.get('choice',[]);written=data.get('written',[]);optional=data.get('optional',[])
    if len(choice)!=14:raise ValueError('I卷必须有14道选择题')
    if not written:raise ValueError('II卷至少有一道题')
    if len(optional)!=2:raise ValueError('选做题必须为2道，不计入总分和时长')
    for i,q in enumerate(choice+written+optional,1):
        for k in ('stem','answer','explanation','difficulty'):
            if not q.get(k):raise ValueError(f'第{i}题缺少 {k}')
        if q['difficulty'] not in ('基础','中档','较难'):raise ValueError('difficulty 必须为基础/中档/较难')
        _number(q.get('minutes'),f'第{i}题 minutes')
        if q.get('work_lines',1) not in range(1,21):raise ValueError('work_lines 须为1到20的整数')
    for q in choice:
        options=q.get('options',[])
        if not isinstance(options,list) or len(options)!=4 or q['answer'] not in ('A','B','C','D'):raise ValueError('单选题需要4个选项和A到D的答案')
        if any(not ''.join(r['text'] for r in normalize_runs(option)).strip() for option in options):raise ValueError('单选题选项不能为空')
        if q.get('score')!=4:raise ValueError('I卷每题4分')
    for q in written:_number(q.get('score'),'score')
    if sum(q['score'] for q in written)!=44:raise ValueError('II卷必须共44分；I卷+II卷=100分')
    if any(q.get('score',0)!=0 for q in optional):raise ValueError('选做题不计分')
    minutes=sum(q['minutes'] for q in choice+written)
    if not 30<=minutes<=35:raise ValueError(f'必做题估时{minutes:g}分钟，须为30至35分钟')
    return minutes

def _question(d,q,number,choice=False,base_dir=None):
    _p(d,f'{number}. ')
    p=d.paragraphs[-1];add_docx_runs(p,q['stem'])
    if q.get('image'):
        image=Path(q['image']);image=image if image.is_absolute() else Path(base_dir or '.')/image
        if not image.is_file():raise ValueError(f'题目图片不存在：{image}')
        d.add_picture(str(image),width=Cm(12))
    if choice:
        for label,option in zip('ABCD',q['options']):
            p=_p(d,label+'. ');add_docx_runs(p,option)
    else:
        for _ in range(q.get('work_lines',1)):_p(d,[{'text':'　'*32,'underline':True}])

def generate_paper(data,output_path,base_dir=None):
    validate_paper(data)
    d=_template('限时练模板.docx');_title(d,data['title'],14)
    _heading(d,'I卷（56分）');_heading(d,'一、单项选择题（每题4分，共56分）')
    for i,q in enumerate(data['choice'],1):_question(d,q,i,True,base_dir)
    _heading(d,'选择题答题表');t=d.add_table(rows=2,cols=15);t.style='Table Grid'
    for i,c in enumerate(t.rows[0].cells):c.text='题号' if i==0 else str(i)
    t.cell(1,0).text='答案'
    _heading(d,'II卷（44分）');_p(d,'姓名________　班级________　组号________');_heading(d,'二、填空及简答题')
    for i,q in enumerate(data['written'],15):
        p=_p(d,f'{i}. （{q["score"]:g}分）');add_docx_runs(p,q['stem'])
        if q.get('image'):
            img=Path(q['image']);img=img if img.is_absolute() else Path(base_dir or '.')/img
            d.add_picture(str(img),width=Cm(12))
        for _ in range(q.get('work_lines',2)):_p(d,[{'text':'　'*32,'underline':True}])
    _heading(d,'【选做题】')
    for i,q in enumerate(data['optional'],15+len(data['written'])):_question(d,q,i,False,base_dir)
    return _save(d,output_path)

def generate_answers(data,output_path):
    minutes=validate_paper(data);d=_template('限时练模板.docx');_title(d,data['title']+'答案与解析',14)
    _p(d,f'必做题预估总时长：{minutes:g}分钟；总分：100分。')
    for label,questions,start in [('I卷',data['choice'],1),('II卷',data['written'],15),('选做题',data['optional'],15+len(data['written']))]:
        _heading(d,label)
        for i,q in enumerate(questions,start):
            _heading(d,f'{i}. 难度：{q["difficulty"]}　预估用时：{q["minutes"]:g}分钟')
            p=_p(d,'答案：');add_docx_runs(p,q['answer'])
            p=_p(d,'解析：');add_docx_runs(p,q['explanation'])
            source=q.get('source')
            if source:_p(d,'来源：'+str(source))
    return _save(d,output_path)
