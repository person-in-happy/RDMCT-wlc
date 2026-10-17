"""Create vector English terminology variants; preserve original geometry/data."""
from pathlib import Path
import hashlib,json,re
import pymupdf

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
FIG=PAPER/'figures'; OUT=FIG/'terminology_en'; OUT.mkdir(exist_ok=True)
names=re.findall(r'includegraphics\[.*?\]\{(.*?)\}',(PAPER/'JMS_Submission_EN.tex').read_text(encoding='utf-8'))
mapping={'Dummy out':'Auxiliary out','Dummy return':'Auxiliary return','Dummy-wafer':'Auxiliary-wafer',
 'Accompanied entry: dummy held on ATR during product alignment':'Auxiliary held on ATR during product alignment',
 'Load dummy PW pair D':'Load auxiliary pair D','processing':'production','Processing':'Production',
 'Process / rotation':'Production / rotation','+ chain slide':'+ pair exchange'}
fontfile='C:/Windows/Fonts/arial.ttf';font=pymupdf.Font(fontfile=fontfile)
reports=[]
titles={'Route-total wait':'a','Route-maximum wait':'b','Cadence CV':'c','Cadence deviation':'d',
        'Mean PDI':'a','Proven optimal (%)':'b','Mean solve time (s)':'c'}
for name in names:
    src=FIG/(name+'.pdf'); original=hashlib.sha256(src.read_bytes()).hexdigest()
    doc=pymupdf.open(src); edits=[];page=doc[0]
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            for span in line['spans']:
                old=span['text']
                chart=name in ['fig04_workflow_en_nature','fig05_doe_en_nature']
                title=chart and old in titles
                letter=chart and old in ['a','b','c','d']
                xlabel=chart and old=='Wafers'
                if old not in mapping and not (title or letter or xlabel):continue
                new=f'({titles[old]}) {old}' if title else '' if letter else 'Product wafers' if xlabel else mapping[old]
                assert line['dir']==(1.0,0.0)
                box=pymupdf.Rect(span['bbox']); y=span['origin'][1]; size=span['size']
                page.add_redact_annot(pymupdf.Rect(box.x0-.05,y-size*.6,box.x1+.05,y-size*.2),fill=False)
                edits.append((span,new))
    if not edits:
        doc.close();continue
    page.apply_redactions(images=0,graphics=0,text=0)
    page.insert_font(fontname='EditorialArial',fontfile=fontfile)
    page.insert_font(fontname='EditorialArialBold',fontfile='C:/Windows/Fonts/arialbd.ttf')
    for span,new in edits:
        if not new:continue
        box=pymupdf.Rect(span['bbox']);size=min(span['size'],box.width/font.text_length(new,fontsize=1))
        x=(box.x0+box.x1-font.text_length(new,fontsize=size))/2
        y=span['origin'][1];fontname='EditorialArial'
        if span['text'] in titles:
            x=span['origin'][0]-4;y+=2.3;size=7.5;fontname='EditorialArialBold'
        elif span['text']=='Wafers':
            size=span['size'];x=(box.x0+box.x1-font.text_length(new,fontsize=size))/2
        page.insert_text((x,y),new,fontname=fontname,fontsize=size,color=pymupdf.sRGB_to_pdf(span['color']))
    doc.subset_fonts();doc.save(OUT/(name+'.pdf'),garbage=4,deflate=True);doc.close()
    revised=pymupdf.open(OUT/(name+'.pdf'))
    revised[0].get_pixmap(matrix=pymupdf.Matrix(3,3)).save(OUT/(name+'.png'))
    (OUT/(name+'.svg')).write_text(revised[0].get_svg_image(text_as_path=True),encoding='utf-8')
    assert not re.search('dummy|dummies',revised[0].get_text(),re.I)
    revised.close()
    assert hashlib.sha256(src.read_bytes()).hexdigest()==original
    reports.append({'figure':name,'original_sha256':original,'labels':[{'old':s['text'],'new':v} for s,v in edits]})
(HERE/'figure_label_audit.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
print(json.dumps({'figures':len(reports),'label_changes':sum(len(r['labels']) for r in reports)}))
