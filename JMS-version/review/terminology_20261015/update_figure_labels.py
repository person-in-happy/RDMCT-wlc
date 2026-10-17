"""Make Chinese vector-label variants without changing plot geometry or data."""
from pathlib import Path
import json
import hashlib
import pymupdf

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
FIGURES = PAPER / 'figures'
OUT = FIGURES / 'terminology_cn'
OUT.mkdir(exist_ok=True)
fontpath = Path('C:/Windows/Fonts/msyh.ttc')
font = pymupdf.Font(fontfile=str(fontpath))
boldpath = Path('C:/Windows/Fonts/msyhbd.ttc')
stems = ['fig_chain_cn_nature', 'fig_parallel_cn_nature',
         'fig05_doe_cn_nature', 'fig04_workflow_cn_nature'] + [
    f'fig_resource_gantt_cleanH{h}_w16_{mode}_cn_nature'
    for h in [10, 3] for mode in ['41', '22']]
mapping = {'腔室加工/自转': '工艺处理', '腔室加工': '工艺处理',
           '并行加工': '并行生产', '校准': '对准',
           '晶圆数': '产品晶圆数', '链式滑动': '链式换片', '自转': '旋转'}
reports = []
titles = {'路线总等待': 'a', '路线最大等待': 'b', '节拍变异系数': 'c', '节拍偏差': 'd',
          '平均PDI': 'a', '证明最优率 (%)': 'b', '平均求解时间 (s)': 'c'}
for stem in stems:
    src = FIGURES / (stem + '.pdf')
    doc = pymupdf.open(src)
    report = {'source': str(src), 'sha256': hashlib.sha256(src.read_bytes()).hexdigest(), 'labels': []}
    for page in doc:
        edits = []
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines', []):
                for span in line['spans']:
                    old = span['text']
                    new = old
                    for a, b in mapping.items():
                        new = new.replace(a, b)
                    header = stem in ['fig04_workflow_cn_nature', 'fig05_doe_cn_nature'] and old in titles
                    letter = stem in ['fig04_workflow_cn_nature', 'fig05_doe_cn_nature'] and old in ['a','b','c','d']
                    if header:
                        new = f'({titles[old]}) {old}'
                    if letter:
                        new = ''
                    if old == new:
                        continue
                    assert line['dir'] == (1.0, 0.0)
                    bbox = pymupdf.Rect(span['bbox'])
                    y = span['origin'][1]
                    size = span['size']
                    # Use a narrow interior strip: remove this text, not neighboring lines.
                    page.add_redact_annot(pymupdf.Rect(bbox.x0 - .05, y - size * .6,
                                                     bbox.x1 + .05, y - size * .2), fill=False)
                    edits.append((span, new, header))
        page.apply_redactions(images=0, graphics=0, text=0)
        page.insert_font(fontname='EditorialYaHei', fontfile=str(fontpath))
        page.insert_font(fontname='EditorialYaHeiBold', fontfile=str(boldpath))
        for span, new, header in edits:
            size = span['size']
            box = pymupdf.Rect(span['bbox'])
            y = span['origin'][1]
            if header:
                x = span['origin'][0] - 4
                y += 2.3
                size = 7.5
            elif 'gantt' in stem:
                x = span['origin'][0]
            else:
                x = (box.x0 + box.x1 - font.text_length(new, fontsize=size)) / 2
            rgb = pymupdf.sRGB_to_pdf(span['color'])
            if new:
                page.insert_text((x, y), new, fontname='EditorialYaHeiBold' if header else 'EditorialYaHei',
                                 fontsize=size, color=rgb)
            report['labels'].append({'old': span['text'], 'new': new})
    doc.subset_fonts()
    doc.save(OUT / (stem + '.pdf'), garbage=4, deflate=True)
    doc.close()
    updated = pymupdf.open(OUT / (stem + '.pdf'))
    for page in updated:
        page.get_pixmap(matrix=pymupdf.Matrix(3, 3)).save(OUT / (stem + '.png'))
        text = page.get_text()
        assert '腔室加工' not in text and '校准' not in text
    # Export the final PDF appearance as vector outlines, keeping the original editable SVG untouched.
    (OUT / (stem + '.svg')).write_text(updated[0].get_svg_image(text_as_path=True),encoding='utf-8')
    assert hashlib.sha256(src.read_bytes()).hexdigest() == report['sha256']
    reports.append(report)
(HERE / 'figure_label_audit.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'figures':len(reports),'label_changes':sum(len(x['labels']) for x in reports)}))
