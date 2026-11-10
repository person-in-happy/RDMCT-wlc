"""Edit two vector labels per diagram while retaining all coordinates."""
from pathlib import Path
import json,re
import pymupdf
from PIL import Image,ImageChops,ImageDraw

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
OUT=PAPER/'figures/pjob_sequence_cn'
OUT.mkdir(exist_ok=True)
records=[]
for old,new in [('fig_system_cn_nature','fig_system_pjob_cn'),
                ('fig_single_source_cn','fig_single_source_pjob_cn')]:
    original=pymupdf.open(PAPER/'figures'/(old+'.pdf'))
    page=original[0]
    before=page.get_pixmap(matrix=pymupdf.Matrix(4,4))
    labels=[]
    for block in page.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            for span in line['spans']:
                if span['text'] in ('CH1','CH2'):labels.append(span)
    assert len(labels)==2
    fontxref=next(f[0] for f in page.get_fonts() if f[3].endswith('MicrosoftYaHei-Bold'))
    font=original.extract_font(fontxref)[3]
    for span in labels:page.add_redact_annot(span['bbox'],fill=None,cross_out=False)
    page.apply_redactions(images=0,graphics=0)
    page.insert_font(fontname='PjobDiagramBold',fontbuffer=font)
    for span in labels:
        page.insert_text(span['origin'],{'CH1':'CH2','CH2':'CH3'}[span['text']],
                         fontsize=span['size'],fontname='PjobDiagramBold',color=(39/255,)*3)
    path=OUT/(new+'.pdf');original.save(path,garbage=4,deflate=True)
    after=page.get_pixmap(matrix=pymupdf.Matrix(4,4))
    a=Image.frombytes('RGB',(before.width,before.height),before.samples)
    b=Image.frombytes('RGB',(after.width,after.height),after.samples)
    delta=ImageChops.difference(a,b)
    draw=ImageDraw.Draw(delta)
    for span in labels:
        rect=pymupdf.Rect(span['bbox']);rect+=(-1,-1,1,1)
        draw.rectangle(tuple(round(v*4) for v in rect),fill=(0,0,0))
    assert delta.getbbox() is None,'Non-label artwork changed'
    after.save(OUT/(new+'.png'))
    svg=(PAPER/'figures'/(old+'.svg')).read_text('utf-8')
    svg,count=re.subn(r'>(CH1|CH2)<',lambda m:'>'+{'CH1':'CH2','CH2':'CH3'}[m[1]]+'<',svg)
    assert count==2
    (OUT/(new+'.svg')).write_text(svg,'utf-8')
    assert 'CH1' not in page.get_text() and 'CH3' in page.get_text()
    records.append(dict(original=old,revised=new,labels_changed=2,pixels_outside_labels_unchanged=True))
    original.close()

path=PAPER/'JMS_Review_CN.tex';source=path.read_text('utf-8')
source=source.replace(r'\graphicspath{{figures/terminology_cn/}{figures/}}',
                      r'\graphicspath{{figures/pjob_sequence_cn/}{figures/terminology_cn/}{figures/}}')
for old,new in [('fig_system_cn_nature','fig_system_pjob_cn'),('fig_single_source_cn','fig_single_source_pjob_cn')]:
    assert source.count('{'+old+'}')==1
    source=source.replace('{'+old+'}','{'+new+'}')
path.write_text(source,'utf-8')
(HERE/'figure_label_check.json').write_text(json.dumps(records,indent=2),'utf-8')
print('Only CH1/CH2 labels changed to CH2/CH3; other pixels unchanged')
