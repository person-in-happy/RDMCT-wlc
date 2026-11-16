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

def schedules():
    source=Path(__file__).with_name('render_journal_schedule_examples.py')
    code=source.read_text('utf-8')
    # Reuse the validated interval builder and assertions; change display text only.
    code=code.replace('"时间 / s"','"Time / s"')
    code=code.replace('ax.set_yticks(range(len(lanes)), display_lanes,',
                      'ax.set_yticks(range(len(lanes)), [lane_en(x) for x in display_lanes],')
    code=code.replace('"legend": 7.2','"legend": 6.6')
    code=code.replace('3.55, .21, 1.10, .10','3.55, .21, .90, .10')
    module=types.ModuleType('english_schedule_renderer')
    module.__file__=str(source)
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
    sm=module.read(PAPER/'figures/current_defaults_20261103/manifest.json')
    lg=module.read(PAPER/'figures/current_d_n16_20261111/manifest.json')
    entries=[(Path(sm['result']),sm['result_sha256'],PAPER/'figures/current_defaults_20261103/swimlane_actions.json',6),
             (Path(lg['source']),lg['source_sha256'],PAPER/'review/gantt_current_model_20261111/n16_current_D_920/figure_evidence.json',7)]
    report=[]
    for path,digest,evidence,n in entries:
        assert sha(path)==digest
        info=module.draw(module.read(path),module.read(evidence),f'Figure{n}',single_column=True)
        info.update(source=str(path),source_sha256=digest)
        report.append(info)
    return report

def coupled():
    source=Path(__file__).with_name('render_coupled_schedule_cn.py')
    code=source.read_text('utf-8').replace('"Microsoft YaHei"','"Arial"').replace('"产品晶圆"','"Product"').replace('"时间 / s"','"Time / s"')
    code=code.replace('"fig_coupled_schedule_merged_cn"','"Figure5"').replace('for ext in ("pdf", "png"):','for ext in ("pdf", "png", "svg"):')
    code=code.replace('"ps.fonttype": 42','"ps.fonttype": 42, "svg.fonttype": "none"')
    module=types.ModuleType('english_coupled_renderer');module.__file__=str(source)
    exec(compile(code,str(source),'exec'),module.__dict__)
    module.OUTPUT=OUT
    module.main()
    report=json.loads((OUT/'manifest.json').read_text('utf-8'))
    return report

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    report={'topology':[topology('fig_system_pjob_cn',1),topology('fig_single_source_pjob_cn',2)]}
    # These unchanged English diagrams have the same events and pair identities as the Chinese figures.
    for n,folder,stem in [(3,'terminology_en','fig_chain_en_nature'),(4,'','fig_parallel_en_nature')]:
        for ext in ('pdf','png','svg'):
            p=PAPER/'figures'/folder/(stem+'.'+ext)
            shutil.copyfile(p,OUT/f'Figure{n}.{ext}')
    report['coupled']=coupled()
    report['schedules']=schedules()
    for p in OUT.glob('*.pdf'):
        d=pymupdf.open(p)
        assert not re.search('[\u4e00-\u9fff]', ''.join(pg.get_text() for pg in d)),p
    report['optimization_calls']=0
    report['renderer_sha256']=sha(Path(__file__))
    report['artifacts']={p.name:sha(p) for p in OUT.iterdir() if p.suffix in ('.pdf','.svg','.png')}
    (OUT/'manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    print('English figures 1-7 generated; frozen schedule intervals retained; no optimizer used.')

if __name__=='__main__':main()
