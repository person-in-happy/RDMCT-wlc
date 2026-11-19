"""Produce English vector figures from current diagrams and frozen schedule events."""
from pathlib import Path
import re
import json
import hashlib
import xml.etree.ElementTree as ET
import types
import shutil
import copy
import pymupdf
from compact_figure_layout import crop_vector_figure

PAPER=Path(__file__).resolve().parents[1]
OUT=PAPER/'figures/submission_en'
NS='http://www.w3.org/2000/svg'

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def topology(stem, number):
    source=PAPER/'figures/pjob_sequence_cn'/(stem+'.svg')
    tree=ET.parse(source)
    translations={
        '大气域':'Atmosphere','真空域':'Vacuum','ATR轨道':'ATR rail',
        'LL (U=上/L=下)':'LL (U=upper / L=lower)',
        '放片':'Place','取片':'Pick','产品进':'Product in','产品回':'Product return',
        '辅助进':'Auxiliary in','辅助回':'Auxiliary return',
        '辅助晶圆存储':'Auxiliary storage',
        '随行：辅助片留在ATR，产品对准后共同入LL':'Auxiliary stays on ATR during alignment; both enter LL together.',
    }
    for t in tree.findall('.//{'+NS+'}text'):
        old=''.join(t.itertext())
        if old in translations:t.text=translations[old]
        style=t.attrib.get('style','')
        style=re.sub(r'font-family:[^;]+', 'font-family: Arial, Helvetica, sans-serif',style)
        # The English LL expansion is wider than the Chinese abbreviation.
        if old=='LL (U=上/L=下)':style=re.sub(r'font-size: [\d.]+px','font-size: 4.1px',style)
        if old.startswith('随行：'):style=re.sub(r'font-size: [\d.]+px','font-size: 4.1px',style)
        t.set('style',style)
    ET.register_namespace('',NS)
    ET.register_namespace('xlink','http://www.w3.org/1999/xlink')
    target=OUT/f'Figure{number}.svg'
    tree.write(target,encoding='utf-8',xml_declaration=True)
    assert not re.search('[\u4e00-\u9fff]',target.read_text('utf-8'))
    # Preserve the original vector paths (including dashed route styles).
    # MuPDF's SVG converter does not retain all stroke-dasharray styles.
    text_root=ET.Element('{'+NS+'}svg',tree.getroot().attrib)
    for node in tree.findall('.//{'+NS+'}text'):
        text_root.append(copy.deepcopy(node))
    text_svg=pymupdf.open(stream=ET.tostring(text_root,encoding='utf-8'),filetype='svg')
    text_pdf=pymupdf.open('pdf',text_svg.convert_to_pdf())
    pdf=pymupdf.open(source.with_suffix('.pdf'))
    pdf[0].add_redact_annot(pdf[0].rect,fill=None)
    pdf[0].apply_redactions(images=0,graphics=0,text=0)
    pdf[0].show_pdf_page(pdf[0].rect,text_pdf,0,overlay=True)
    pdf.save(target.with_suffix('.pdf'))
    pdf[0].get_pixmap(matrix=pymupdf.Matrix(4,4),alpha=False).save(target.with_suffix('.png'))
    return {'source':str(source.relative_to(PAPER)),'source_sha256':sha(source),'figure':number}

def legended_figures():
    source=Path(__file__).with_name('render_in_figure_legends_cn.py')
    code=source.read_text('utf-8')
    translations={
        '"产品晶圆"':'"Product"', '"时间 / s"':'"Time / s"',
        '"生产加工及补位借用"':'"Production / filling"',
        '"清洁借用"':'"Cleaning loans"',
        '批次完工：':'Batch makespan: ',
        '设备占用结束：':'Equipment occupancy ends: ',
        'D1–D7：辅助晶圆':'D1-D7: auxiliary wafers',
        'P1[i:j]：Pjob1中第i至j片产品':'P1[i:j]: Pjob1 products i-j',
        'P1[1:2]：Pjob1的两片产品    D1、D2：辅助片':'P1[1:2]: Pjob1 products 1-2; D1, D2: auxiliaries',
        'fig_coupled_schedule_merged_cn':'Figure5',
    }
    for a,b in translations.items():code=code.replace(a,b)
    code=code.replace('ax.set_yticks(range(len(lanes)), display_lanes,',
                      'ax.set_yticks(range(len(lanes)), [lane_en(x) for x in display_lanes],')
    # Keep four action-legend columns within the single-column figure width.
    code=code.replace('ncol=4, frameon=False, fontsize=7.2, columnspacing=.85',
                      'ncol=4, frameon=False, fontsize=6.6, columnspacing=.7')
    module=types.ModuleType('english_legended_renderer');module.__file__=str(source)
    exec(compile(code,str(source),'exec'),module.__dict__)
    module.OUT=OUT
    module.LEGEND_LABELS={
        'ATR取片':'ATR pick','ATR放片':'ATR place','带片移动':'Loaded move',
        '承片等待':'Wafer hold','AL对准':'Align','LL抽气':'LL pump',
        'LL真空等待':'LL vacuum','LL放气':'LL vent','LL大气等待':'Atm. wait',
        'VTR取放':'VTR transfer','腔室加工':'Process','腔内等待':'Chamber wait',
        '腔室旋转':'Rotate','空载移动/复位':'Empty/reset',
    }
    def lane_en(s):
        for a,b in [('真空辅助库 VS','Vacuum store'),('旋转腔 ','') ,('对准器 ','') ,('机械手',''),('上装载锁槽','Upper LL'),('下装载锁槽','Lower LL')]:s=s.replace(a,b)
        assert not re.search('[\u4e00-\u9fff]',s),s
        return s
    module.lane_en=lane_en
    module.plt.rcParams.update({'font.family':'Arial','font.sans-serif':['Arial','DejaVu Sans'],
                                'pdf.fonttype':42,'svg.fonttype':'none','axes.unicode_minus':False})
    old=module.read(PAPER/'figures/schedule_examples_unified_20261112/manifest.json')
    schedules=[]
    for number,entry in enumerate(old['figures'],5):
        entry=dict(entry,stem=f'Figure{number}')
        info=module.draw_schedule(entry, compact_layout=True)
        info.update(legend_columns=4,single_column=True)
        schedules.append(info)
    return schedules

def chain_legend():
    source=PAPER/'figures/terminology_en/fig_chain_en_nature.pdf'
    doc=pymupdf.open(source);page=doc[0]
    assert max(w[3] for w in page.get_text('words'))<216
    font=pymupdf.Font(fontfile='C:/Windows/Fonts/arial.ttf')
    label,size='Auxiliary PW pair',6.8
    x=(page.rect.width-23-font.text_length(label,fontsize=size))/2
    y,radius=223.,3.9
    page.insert_font(fontname='LegendEN',fontbuffer=font.buffer)
    for dx in (4,14):
        page.draw_circle((x+dx,y),radius,color=(.17,.17,.17),fill=(1.,.82,.36),width=.6,dashes='[2 1] 0')
        page.insert_text((x+dx-font.text_length('D',fontsize=6)/2,y+2.15),'D',fontsize=6,fontname='LegendEN')
    page.insert_text((x+23,y+2.5),label,fontsize=size,fontname='LegendEN')
    doc.subset_fonts();doc.save(OUT/'Figure3.pdf',garbage=4,deflate=True)
    page.get_pixmap(matrix=pymupdf.Matrix(3,3),alpha=False).save(OUT/'Figure3.png')
    (OUT/'Figure3.svg').write_text(page.get_svg_image(),'utf-8')
    original=pymupdf.open(source);clip=pymupdf.Rect(0,0,page.rect.width,216)
    assert original[0].get_pixmap(clip=clip).samples==page.get_pixmap(clip=clip).samples
    return {'source':str(source),'source_sha256':sha(source),'legend':label,'original_drawing_unchanged':True}

def parallel_labels():
    source=PAPER/'figures/fig_parallel_en_nature.pdf'
    doc=pymupdf.open(source);page=doc[0]
    replacements={'four slots full':'full occupancy','four spaces':'all four wafers'}
    spans=[s for b in page.get_text('dict')['blocks'] if 'lines' in b for line in b['lines'] for s in line['spans']]
    targets=[s for s in spans if s['text'] in replacements]
    assert len(targets)==2
    for span in targets:
        rect=pymupdf.Rect(span['bbox']);middle=(rect.y0+rect.y1)/2
        # A narrow center strip avoids touching the adjacent line's glyph box.
        page.add_redact_annot(pymupdf.Rect(rect.x0,middle-.3,rect.x1,middle+.3),fill=None)
    page.apply_redactions(images=0,graphics=0,text=0)
    font=pymupdf.Font(fontfile='C:/Windows/Fonts/arial.ttf')
    page.insert_font(fontname='TermEN',fontbuffer=font.buffer)
    for span in targets:
        rect=pymupdf.Rect(span['bbox']);label=replacements[span['text']];size=span['size']
        x=(rect.x0+rect.x1-font.text_length(label,fontsize=size))/2
        page.insert_text((x,span['origin'][1]),label,fontname='TermEN',fontsize=size)
    for label in replacements.values():assert label in page.get_text().replace('\xa0',' '),label
    assert 'Process' in page.get_text() and 'Load P2' in page.get_text()
    doc.subset_fonts();doc.save(OUT/'Figure4.pdf',garbage=4,deflate=True)
    page.get_pixmap(matrix=pymupdf.Matrix(4,4),alpha=False).save(OUT/'Figure4.png')
    (OUT/'Figure4.svg').write_text(page.get_svg_image(),'utf-8')
    return {'source':str(source),'source_sha256':sha(source),'label_replacements':replacements}


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report={'topology':[topology('fig_system_pjob_cn',1),topology('fig_single_source_pjob_cn',2)]}
    report['parallel']=parallel_labels()
    report['chain']=chain_legend()
    report['schedules']=legended_figures()
    report['cropping']={f'Figure{i}':crop_vector_figure(OUT/f'Figure{i}.pdf') for i in range(1,7)}
    for p in OUT.glob('*.pdf'):
        d=pymupdf.open(p)
        assert not re.search('[\u4e00-\u9fff]', ''.join(pg.get_text() for pg in d)),p
    report['optimization_calls']=0
    report['renderer_sha256']=sha(Path(__file__))
    report['artifacts']={p.name:sha(p) for p in OUT.iterdir() if p.suffix in ('.pdf','.svg','.png')}
    (OUT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print('English figures 1-6 generated; frozen schedule intervals retained; no optimizer used.')

if __name__=='__main__':main()
