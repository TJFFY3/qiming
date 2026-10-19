"""Portable PowerPoint template assembly with native DrawingML (lxml + zipfile).

No PowerPoint installation or python-pptx is needed. Text stays editable. Layout
fit is deliberately conservative: split rejected content into another slide rather
than shrink the 24pt body font. Template master/layout/background parts are copied
unchanged. Single-line reaction conditions use editable stacked textboxes; formulas that
need wrapping are rejected rather than silently misaligned.
"""
from copy import deepcopy
import math
from pathlib import Path
import posixpath
import re
import struct
import unicodedata
from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
from chemistry_runs import normalize_runs

P='http://schemas.openxmlformats.org/presentationml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PKG='http://schemas.openxmlformats.org/package/2006/relationships'
CT='http://schemas.openxmlformats.org/package/2006/content-types'
NS={'p':P,'a':A,'r':R}
STAGES={'启','探','析','辩','辩—自由讨论','辩—预设讨论','辩—自由展示','辩—预设展示','辩—梳理内化'}
DEFAULT_TEMPLATE=Path(__file__).resolve().parents[1]/'assets/templates/课件模板.pptx'
SLIDE_TYPE='application/vnd.openxmlformats-officedocument.presentationml.slide+xml'
NOTES_TYPE='application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml'


def _node(parent, namespace, tag, **attrs):
    return E.SubElement(parent, '{'+namespace+'}'+tag, {k:str(v) for k,v in attrs.items()})


def _xml(root):
    return E.tostring(root,xml_declaration=True,encoding='UTF-8',standalone=True)


def _width(text):
    return sum(1 if unicodedata.east_asian_width(c) in ('W','F') else .6 for c in text)


def _runs(value):
    result=[]
    for r in normalize_runs(value):
        if r.get('isotope'):
            iso=r['isotope']
            if not isinstance(iso,dict) or not str(iso.get('mass','')).isdigit() or not str(iso.get('atomic','')).isdigit():
                raise ValueError('同位素需要数字 mass 和 atomic')
            result.extend([{'text':str(iso['mass']),'sup':True},{'text':str(iso['atomic']),'sub':True},{'text':r['text']}])
        else:
            r=dict(r)
            if r.get('condition'):
                label=r['text']
                result.append({'text':'=======' if label=='高温' else '=====','condition_label':label})
                continue
            if r.get('charge'):r['sup']=True
            if r.get('sub') and r.get('sup'):raise ValueError('不能同时设置上标和下标')
            result.append(r)
    return result


def _transform(parent,x,y,w,h):
    xf=_node(parent,A,'xfrm')
    _node(xf,A,'off',x=round(x*360000),y=round(y*360000))
    _node(xf,A,'ext',cx=round(w*360000),cy=round(h*360000))


def _textbox(tree,ident,name,paragraphs,x,y,w,h,size=2400,color='000000',fill=None,align='l',font='阿里巴巴普惠体 M'):
    sp=_node(tree,P,'sp')
    nv=_node(sp,P,'nvSpPr');_node(nv,P,'cNvPr',id=ident,name=name)
    _node(nv,P,'cNvSpPr',txBox='1');_node(nv,P,'nvPr')
    props=_node(sp,P,'spPr');_transform(props,x,y,w,h)
    geom=_node(props,A,'prstGeom',prst='rect');_node(geom,A,'avLst')
    if fill:_node(_node(props,A,'solidFill'),A,'srgbClr',val=fill)
    else:_node(props,A,'noFill')
    _node(_node(props,A,'ln'),A,'noFill')
    tx=_node(sp,P,'txBody')
    bp=_node(tx,A,'bodyPr',wrap='square',lIns='72000',rIns='72000',tIns='72000',bIns='72000',anchor='ctr' if fill else 't')
    _node(bp,A,'noAutofit');_node(tx,A,'lstStyle')
    for paragraph in paragraphs:
        p=_node(tx,A,'p');pr=_node(p,A,'pPr',algn=align)
        _node(_node(pr,A,'lnSpc'),A,'spcPct',val=115000)
        _node(_node(pr,A,'spcAft'),A,'spcPts',val=900 if not fill else 0)
        for run in paragraph:
            rr=_node(p,A,'r')
            attrs={'sz':size,'lang':'zh-CN','dirty':'0'}
            if run.get('sup'):attrs['baseline']='30000'
            if run.get('sub'):attrs['baseline']='-25000'
            if run.get('italic'):attrs['i']='1'
            if run.get('bold'):attrs['b']='1'
            if run.get('underline'):attrs['u']='sng'
            rp=_node(rr,A,'rPr',**attrs)
            _node(_node(rp,A,'solidFill'),A,'srgbClr',val=color)
            _node(rp,A,'latin',typeface=font);_node(rp,A,'ea',typeface=font)
            t=_node(rr,A,'t');t.text=run['text']
            if run['text'][:1].isspace() or run['text'][-1:].isspace():t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
        _node(p,A,'endParaRPr',sz=size)
    return sp


def _body(tree, paragraphs, x, y, w, capacity):
    """Give condition lines their own baseline and reserved label row.

    ASCII equation text uses a monospace font so the measured six-tenths-em
    advance and the operator/label centers agree in Office without a renderer.
    """
    ident=10
    for paragraph in paragraphs:
        text=''.join(r['text'] for r in paragraph)
        conditions=[r for r in paragraph if r.get('condition_label')]
        if conditions:
            _textbox(tree,ident,'反应方程式',[paragraph],x,y+1.35,w,1.45,font='Courier New')
            ident+=1;prefix=''
            for run in paragraph:
                if run.get('condition_label'):
                    label=run['condition_label'];label_width=_width(label)*24*2.54/72+.4
                    operator_width=_width(run['text'])*24*2.54/72
                    label_x=x+.2+_width(prefix)*24*2.54/72+(operator_width-label_width)/2
                    _textbox(tree,ident,'反应条件',[[{'text':label}]],label_x,y,label_width,1.45,align='ctr',font='黑体')
                    ident+=1
                prefix+=run['text']
            y+=2.8
        else:
            lines=sum(max(1,math.ceil(_width(line)/capacity)) for line in text.split('\n'))
            h=lines*1.02+.32
            _textbox(tree,ident,'正文',[paragraph],x,y,w,h)
            ident+=1;y+=h


def _relationship(root,kind,target):
    ids={r.get('Id') for r in root};i=1
    while 'rId'+str(i) in ids:i+=1
    ident='rId'+str(i)
    _node(root,PKG,'Relationship',Id=ident,Type=R+'/'+kind,Target=target)
    return ident


def _image(path):
    data=path.read_bytes()
    if data.startswith(b'\x89PNG\r\n\x1a\n') and len(data)>=24:
        w,h=struct.unpack('>II',data[16:24]);ext='png';mime='image/png'
    elif data.startswith(b'\xff\xd8'):
        offset=2;w=h=0
        while offset<len(data):
            if data[offset]!=255:offset+=1;continue
            while offset<len(data) and data[offset]==255:offset+=1
            if offset>=len(data):break
            marker=data[offset];offset+=1
            if marker in (0xD8,0xD9,0x01) or 0xD0<=marker<=0xD7:continue
            if offset+2>len(data):break
            length=int.from_bytes(data[offset:offset+2],'big')
            if marker in (0xC0,0xC1,0xC2,0xC3,0xC5,0xC6,0xC7,0xC9,0xCA,0xCB,0xCD,0xCE,0xCF):
                h,w=struct.unpack('>HH',data[offset+3:offset+7]);break
            if length<2:break
            offset+=length
        ext='jpg';mime='image/jpeg'
    else:raise ValueError('图片仅支持本地 PNG 或 JPEG')
    if not w or not h:raise ValueError('无法读取图片尺寸')
    return data,ext,mime,w,h


def _picture(tree,ident,rid,x,y,w,h):
    pic=_node(tree,P,'pic');nv=_node(pic,P,'nvPicPr')
    _node(nv,P,'cNvPr',id=ident,name='教学图片');_node(_node(nv,P,'cNvPicPr'),A,'picLocks',noChangeAspect='1');_node(nv,P,'nvPr')
    bf=_node(pic,P,'blipFill');blip=_node(bf,A,'blip');blip.set('{'+R+'}embed',rid)
    _node(_node(bf,A,'stretch'),A,'fillRect')
    props=_node(pic,P,'spPr');_transform(props,x,y,w,h)
    _node(_node(props,A,'prstGeom',prst='rect'),A,'avLst')


def _notes(text):
    root=E.Element('{'+P+'}notes',nsmap={'p':P,'a':A,'r':R})
    tree=_node(_node(root,P,'cSld'),P,'spTree')
    nv=_node(tree,P,'nvGrpSpPr');_node(nv,P,'cNvPr',id=1,name='');_node(nv,P,'cNvGrpSpPr');_node(nv,P,'nvPr')
    _node(tree,P,'grpSpPr')
    sp=_textbox(tree,2,'教师备注',[_runs(text)],1,1,16,20)
    nvpr=sp.find('p:nvSpPr/p:nvPr',NS);_node(nvpr,P,'ph',type='body',idx='1')
    _node(_node(root,P,'clrMapOvr'),A,'masterClrMapping')
    return root


def _validate_package(parts):
    for name,data in parts.items():
        if not name.endswith(('.xml','.rels')):continue
        root=E.fromstring(data)
        if name.endswith('.rels'):
            ids=[r.get('Id') for r in root]
            if len(ids)!=len(set(ids)):raise ValueError('关系 ID 重复: '+name)
            base=posixpath.dirname(name).replace('/_rels','') if name!='_rels/.rels' else ''
            for rel in root:
                if rel.get('TargetMode')=='External':continue
                target=posixpath.normpath(posixpath.join(base,rel.get('Target'))).lstrip('/')
                if target not in parts:raise ValueError('关系目标缺失: '+target)


def generate_pptx(slides, output_path, template_path=None, base_dir=None):
    """Generate editable slides; paragraphs = strings or semantic-run lists.

    Relative image paths resolve against base_dir (default current directory).
    Only local PNG/JPEG files are accepted. Returns the saved Path. Inputs are
    validated before the destination is written; bad or crowded content raises
    ValueError. The expected template is a 33.9 x 19.1cm teaching deck.
    """
    if not isinstance(slides,list) or not slides:raise ValueError('slides 必须为非空列表')
    prepared=[];base=Path(base_dir or Path.cwd()).resolve()
    for slide in slides:
        if not isinstance(slide,dict):raise ValueError('每页必须为对象')
        if slide.get('stage') not in STAGES:raise ValueError('无效教学环节')
        title=slide.get('title')
        if not isinstance(title,str) or not title.strip():raise ValueError('标题必须是非空字符串')
        title_runs=_runs(title)
        if '\n' in title or _width(''.join(r['text'] for r in title_runs))>23:raise ValueError('标题过长，请拆分页面')
        raw=slide.get('paragraphs',[])
        if not isinstance(raw,list):raise ValueError('paragraphs 必须为列表')
        if raw and all(isinstance(r,dict) for r in raw):raw=[raw]
        if len(raw)>6:raise ValueError('每页最多 6 段')
        paragraphs=[_runs(p) for p in raw]
        texts=[''.join(r['text'] for r in p) for p in paragraphs]
        if sum(len(t) for t in texts)>200:raise ValueError('正文超过 200 字，请拆分页面')
        image=None
        if slide.get('image') is not None:
            value=slide['image']
            if not isinstance(value,(str,Path)) or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',str(value)) or str(value).startswith('//'):raise ValueError('仅接受本地图片路径')
            path=Path(value);path=path if path.is_absolute() else base/path
            if not path.is_file():raise ValueError('图片不存在: '+str(path))
            image=_image(path)
        capacity=16 if image else 34
        condition_count=0
        for paragraph,text in zip(paragraphs,texts):
            labels=[r for r in paragraph if r.get('condition_label')]
            if labels:
                condition_count+=1
                if '\n' in text or _width(text)>capacity:
                    raise ValueError('反应条件仅支持单行公式，请拆分页面或使用公式图片')
                for run in labels:
                    if not run['condition_label'].strip() or _width(run['condition_label'])+.5>_width(run['text']):
                        raise ValueError('反应条件过长，请使用公式图片')
        line_count=sum(sum(max(1,math.ceil(_width(line)/capacity)) for line in t.split('\n')) for t in texts)
        if line_count*1.02+len(texts)*.32+condition_count*1.46>13.3:raise ValueError('正文估算溢出，请减少内容或拆分页面')
        notes=slide.get('notes','')
        if not isinstance(notes,str):raise ValueError('notes 必须为字符串')
        prepared.append((slide['stage'],title_runs,paragraphs,image,notes))
    with ZipFile(template_path or DEFAULT_TEMPLATE) as z:parts={n:z.read(n) for n in z.namelist()}
    pres=E.fromstring(parts['ppt/presentation.xml']);rels=E.fromstring(parts['ppt/_rels/presentation.xml.rels']);types=E.fromstring(parts['[Content_Types].xml'])
    size=pres.find('p:sldSz',NS);width=int(size.get('cx'))/360000;height=int(size.get('cy'))/360000
    if width<33 or height<18.5:raise ValueError('模板画布过小；需要约 33.9 × 19.1cm')
    # Select the actual blank page by content, rather than assume physical slide2.
    old=[n for n in parts if re.fullmatch(r'ppt/slides/slide\d+\.xml',n)]
    if not old:raise ValueError('模板没有幻灯片')
    blank=min(old,key=lambda n:len(E.fromstring(parts[n]).xpath('//a:t | //p:pic',namespaces=NS)))
    blank_xml=E.fromstring(parts[blank])
    blank_rels=E.fromstring(parts[posixpath.dirname(blank)+'/_rels/'+posixpath.basename(blank)+'.rels'])
    layout=[deepcopy(r) for r in blank_rels if r.get('Type')==R+'/slideLayout']
    if len(layout)!=1:raise ValueError('模板空白页缺少版式关系')
    for n in list(parts):
        if n.startswith(('ppt/slides/','ppt/notesSlides/')):del parts[n]
    for r in list(rels):
        if r.get('Type')==R+'/slide':rels.remove(r)
    for t in list(types):
        if t.get('PartName','').startswith(('/ppt/slides/','/ppt/notesSlides/')):types.remove(t)
    sids=pres.find('p:sldIdLst',NS);sids.clear()
    for cs in pres.findall('p:custShowLst',NS):pres.remove(cs)
    defaults={x.get('Extension') for x in types if x.tag=='{'+CT+'}Default'}
    for i,(stage,title,paragraphs,image,notes) in enumerate(prepared,1):
        root=deepcopy(blank_xml);tree=root.find('p:cSld/p:spTree',NS)
        for shape in list(tree):
            if shape.tag not in ('{'+P+'}nvGrpSpPr','{'+P+'}grpSpPr'):tree.remove(shape)
        for child in list(root):
            if child.tag not in ('{'+P+'}cSld','{'+P+'}clrMapOvr'):root.remove(child)
        root.set('showMasterSp','1')
        sr=E.Element('{'+PKG+'}Relationships',nsmap={None:PKG});sr.append(deepcopy(layout[0]))
        _textbox(tree,2,'标题',[title],1.2,2.15,width-2.4,1.65,size=3200,font='黑体')
        _body(tree,paragraphs,1.2,4.1,15.2 if image else width-2.4,16 if image else 34)
        if len(stage)==1:x,y,w,h,sz=31.8,0,2.1,2,4000
        else:x,y,w,h,sz=width-8.7,0,8.7,1.8,3600
        _textbox(tree,4,'环节标签',[[{'text':stage}]],x,y,w,h,size=sz,color='FFFFFF',fill='FF0000',align='ctr',font='黑体')
        if image:
            data,ext,mime,iw,ih=image;media=f'chemistry_slide_{i}.{ext}'
            while 'ppt/media/'+media in parts:media='new_'+media
            parts['ppt/media/'+media]=data
            rid=_relationship(sr,'image','../media/'+media)
            if ext not in defaults:_node(types,CT,'Default',Extension=ext,ContentType=mime);defaults.add(ext)
            maxw=width-18;maxh=height-5.3;scale=min(maxw/iw,maxh/ih)
            w,h=iw*scale,ih*scale;_picture(tree,5,rid,17.2+(maxw-w)/2,4.2+(maxh-h)/2,w,h)
        name=f'ppt/slides/slide{i}.xml'
        if notes:
            _relationship(sr,'notesSlide',f'../notesSlides/notesSlide{i}.xml')
            parts[f'ppt/notesSlides/notesSlide{i}.xml']=_xml(_notes(notes))
            nr=E.Element('{'+PKG+'}Relationships',nsmap={None:PKG})
            _relationship(nr,'slide',f'../slides/slide{i}.xml')
            if 'ppt/notesMasters/notesMaster1.xml' in parts:_relationship(nr,'notesMaster','../notesMasters/notesMaster1.xml')
            parts[f'ppt/notesSlides/_rels/notesSlide{i}.xml.rels']=_xml(nr)
            _node(types,CT,'Override',PartName=f'/ppt/notesSlides/notesSlide{i}.xml',ContentType=NOTES_TYPE)
        parts[name]=_xml(root);parts[f'ppt/slides/_rels/slide{i}.xml.rels']=_xml(sr)
        rid=_relationship(rels,'slide',f'slides/slide{i}.xml')
        sid=_node(sids,P,'sldId',id=255+i);sid.set('{'+R+'}id',rid)
        _node(types,CT,'Override',PartName='/'+name,ContentType=SLIDE_TYPE)
    parts['ppt/presentation.xml']=_xml(pres);parts['ppt/_rels/presentation.xml.rels']=_xml(rels);parts['[Content_Types].xml']=_xml(types)
    _validate_package(parts)
    destination=Path(output_path);destination.parent.mkdir(parents=True,exist_ok=True)
    with ZipFile(destination,'w',ZIP_DEFLATED) as z:
        for name,data in parts.items():z.writestr(name,data)
    return destination
