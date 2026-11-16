"""Build the Chinese solver explanation PDF without touching experiment inputs.

Requires ReportLab and the Microsoft YaHei fonts on Windows. Dependencies may
also be supplied in JMS-version/tmp/pdfs/suanfashuoming_deps. Rendering/QA is a
separate operation. The document explains the manuscript algorithm and never starts experiments.
"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
from xml.sax.saxutils import escape
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
JMS = ROOT / 'JMS-version'
DEPS = JMS / 'tmp/pdfs/suanfashuoming_deps'
if DEPS.exists():
    sys.path.insert(0, str(DEPS))

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table,
    TableStyle, PageBreak, Flowable,
)

OUTPUT = JMS / 'suanfashuoming.pdf'
QA = JMS / 'tmp/pdfs/suanfashuoming'
SOURCES = [
    'JMS-version/JMS_Review_CN.tex',
    'JMS-version/model4_pjob_nonprocessing_20261103/model.py',
    'JMS-version/model4_pjob_nonprocessing_20261103/seed.py',
    'JMS-version/model4_pjob_nonprocessing_20261103/reference_completion.py',
    'JMS-version/model4_pjob_nonprocessing_20261103/joint_algorithms.py',
    'JMS-version/model4_pjob_nonprocessing_20261103/run_experiments.py',
    'JMS-version/model4_pjob_nonprocessing_20261103/pjob_order.py',
    'JMS-version/model4_pjob_nonprocessing_20261103/validate.py',
    'cie/configs/cie_proposed_train.json',
    'cie/configs/cie_proposed_inference.json',
    'cie/results/repro_manifest/selected_checkpoint_manifest.csv',
    'utils.py', 'cutsel_agent_parallel.py', 'algorithms.py',
    'parallel_reinforce_algorithm.py', 'environments.py',
    'pointer_net.py', 'pointer_net_end_token.py',
]

NAVY = colors.HexColor('#17384D')
TEAL = colors.HexColor('#167D88')
INK = colors.HexColor('#243444')
MUTED = colors.HexColor('#617383')
LINE = colors.HexColor('#D9E3E9')
PALE = colors.HexColor('#F1F6F8')
WHITE = colors.white
W, H = A4
MARGIN = 46
CONTENT = W - 2 * MARGIN


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def observe():
    import csv
    manifest = ROOT / 'cie/results/repro_manifest/selected_checkpoint_manifest.csv'
    with manifest.open(encoding='utf-8-sig', newline='') as stream:
        records = [r for r in csv.DictReader(stream) if r['family'] == 'proposed']
    checks = []
    for record in records:
        actual = digest(ROOT / record['checkpoint'])
        if actual != record['checkpoint_sha256']:
            raise RuntimeError('Frozen policy hash mismatch: ' + record['checkpoint'])
        checks.append(dict(training_seed=record['training_seed'], epoch=record['epoch'],
                           checkpoint=record['checkpoint'], sha256=actual,
                           feature_dim=record['feature_dim'], hash_verified=True))
    if not checks:
        raise RuntimeError('No proposed policy records found')
    return dict(
        observed_at=datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M +08:00'),
        scope='manuscript_RL_DMCT_full_algorithm',
        sources={name: digest(ROOT / name) for name in SOURCES},
        policy_checks=checks,
        training_instances=[p.name for p in sorted((ROOT/'cie/data/policy_training/train').glob('*.lp'))],
        external_reference='https://arxiv.org/abs/2302.00244',
        status='manuscript_and_implementation_explained_no_experiments_started',
    )


def setup_fonts():
    pdfmetrics.registerFont(TTFont('CN', 'C:/Windows/Fonts/msyh.ttc', subfontIndex=0))
    pdfmetrics.registerFont(TTFont('CN-Bold', 'C:/Windows/Fonts/msyhbd.ttc', subfontIndex=0))
    pdfmetrics.registerFont(TTFont('Math', 'C:/Windows/Fonts/cambria.ttc', subfontIndex=0))
    pdfmetrics.registerFontFamily('CN', normal='CN', bold='CN-Bold', italic='CN', boldItalic='CN-Bold')


STYLES = {}


def setup_styles():
    STYLES.update({
        'body': ParagraphStyle('body', fontName='CN', fontSize=11, leading=18,
                               textColor=INK, wordWrap='CJK', spaceAfter=7.5),
        'small': ParagraphStyle('small', fontName='CN', fontSize=9.2, leading=14.2,
                                textColor=MUTED, wordWrap='CJK', spaceAfter=5),
        'table': ParagraphStyle('table', fontName='CN', fontSize=9.8, leading=15.3,
                                textColor=INK, wordWrap='CJK'),
        'thead': ParagraphStyle('thead', fontName='CN-Bold', fontSize=9.8, leading=15.3,
                                textColor=WHITE, wordWrap='CJK'),
        'h1': ParagraphStyle('h1', fontName='CN-Bold', fontSize=22, leading=31,
                             textColor=NAVY, spaceAfter=12),
        'h2': ParagraphStyle('h2', fontName='CN-Bold', fontSize=12.7, leading=19,
                             textColor=TEAL, spaceBefore=9, spaceAfter=6, keepWithNext=True),
        'title': ParagraphStyle('title', fontName='CN-Bold', fontSize=27, leading=38,
                                textColor=NAVY, spaceAfter=5),
        'subtitle': ParagraphStyle('subtitle', fontName='CN', fontSize=11, leading=18,
                                   textColor=MUTED, spaceAfter=13),
        'formula': ParagraphStyle('formula', fontName='CN', fontSize=12.5, leading=22.7,
                                  textColor=NAVY, spaceBefore=2, spaceAfter=7, alignment=TA_CENTER),
        'box': ParagraphStyle('box', fontName='CN', fontSize=10.5, leading=17,
                              textColor=NAVY, wordWrap='CJK'),
        'flow': ParagraphStyle('flow', fontName='CN', fontSize=9.1, leading=13.2,
                               textColor=INK, wordWrap='CJK', alignment=TA_CENTER),
    })


def p(text, style='body'):
    # Use an embedded mathematical font for glyphs absent from Microsoft YaHei.
    # Keep the base and combining accent together so the hat stays over xi.
    text = text.replace('ξ̂', '<font name="Math">ξ<super>̂</super></font>')
    for char in 'ᵍ⁰₁₂₃₄₅ₐₜ∇⊇⌈⌉':
        text = text.replace(char, '<font name="Math">' + char + '</font>')
    return Paragraph(text, STYLES[style])


def head(text):
    obj = p(text, 'h1')
    obj.bookmark_title = text
    return obj


def h2(text):
    return p(text, 'h2')


def table(rows, widths, header=True, compact=False):
    data = [[p(str(cell), 'thead' if header and i == 0 else 'table') for cell in row]
            for i, row in enumerate(rows)]
    out = Table(data, colWidths=widths, hAlign='LEFT', repeatRows=1 if header else 0)
    commands = [
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 4 if compact else 6.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4 if compact else 6.5),
        ('LINEBELOW', (0, -1), (-1, -1), .6, LINE),
        ('ROWBACKGROUNDS', (0, 1 if header else 0), (-1, -1), [WHITE, PALE]),
    ]
    if header:
        commands += [('BACKGROUND', (0, 0), (-1, 0), NAVY)]
    out.setStyle(TableStyle(commands))
    out.spaceAfter = 8
    return out


def box(text):
    out = Table([[p(text, 'box')]], colWidths=[CONTENT])
    out.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), PALE),
        ('LINEBEFORE', (0, 0), (0, -1), 3, TEAL),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
    ]))
    out.spaceAfter = 9
    return out


class ProcessDiagram(Flowable):
    def __init__(self):
        super().__init__()
        self.width = CONTENT
        self.height = 259

    def draw(self):
        c = self.canv
        main_x, main_w, side_x, side_w = 18, 298, 337, CONTENT - 337
        box_h = 34
        centers = [237, 194, 151, 108, 65, 22]
        def node(x, center, w, label, highlight=False):
            c.setFillColor(colors.HexColor('#E7F3F3') if highlight else PALE)
            c.setStrokeColor(TEAL if highlight else LINE)
            c.roundRect(x, center-box_h/2, w, box_h, 5, fill=1, stroke=1)
            para = p(label, 'flow')
            _, height = para.wrap(w-14, box_h-4)
            para.drawOn(c, x+7, center-height/2)
        def arrow(x1, y1, x2, y2):
            import math
            c.setStrokeColor(TEAL)
            c.setFillColor(TEAL)
            c.setLineWidth(.9)
            c.line(x1, y1, x2, y2)
            angle = math.atan2(y2-y1, x2-x1)
            shape = c.beginPath()
            shape.moveTo(x2, y2)
            for da in (.48, -.48):
                shape.lineTo(x2-5*math.cos(angle+da), y2-5*math.sin(angle+da))
            shape.close()
            c.drawPath(shape, fill=1, stroke=0)
        labels = [
            '任务、库存与参数 → 完整 MILP',
            '物理起点 → Enc 补全与双重验证',
            'SPBS：五层改善产品完工上界',
            '第一阶段：完整联合搜索 min Cmax',
            '可选第二阶段：等待与节拍精修',
            'Dec 恢复身份 → 独立重放 → 输出',
        ]
        for y, label in zip(centers, labels):
            node(main_x, y, main_w, label, y == 108)
        for a, b in zip(centers, centers[1:]):
            arrow(main_x+main_w/2, a-box_h/2, main_x+main_w/2, b+box_h/2)
        node(side_x, 237, side_w, '既有 MILP<br/>离线采样训练')
        node(side_x, 194, side_w, '冻结策略参数 θ')
        node(side_x, 108, side_w, 'RL-DMCT-S<br/>选割回调', True)
        arrow(side_x+side_w/2, 220, side_x+side_w/2, 211)
        arrow(side_x+side_w/2, 177, side_x+side_w/2, 125)
        arrow(main_x+main_w, 113, side_x, 113)
        arrow(side_x, 103, main_x+main_w, 103)


class Document(BaseDocTemplate):
    def afterFlowable(self, flowable):
        if hasattr(flowable, 'bookmark_title'):
            key = 'page-' + str(self.page)
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(flowable.bookmark_title, key, level=0, closed=False)


def decorate(canvas, doc):
    canvas.saveState()
    canvas.setTitle('文稿算法求解逻辑详解：RL-DMCT')
    canvas.setAuthor('RDMCT-A3C 项目技术说明')
    canvas.setSubject('任务编码、SPBS、学习选割、联合优化、时序精修与晶圆解码')
    canvas.setFont('CN', 8.1)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, H-29, 'RDMCT-A3C  /  求解流程说明')
    canvas.drawRightString(W-MARGIN, H-29, '文稿算法 · RL-DMCT')
    canvas.setStrokeColor(LINE)
    canvas.setLineWidth(.6)
    canvas.line(MARGIN, H-37, W-MARGIN, H-37)
    canvas.line(MARGIN, 35, W-MARGIN, 35)
    canvas.drawString(MARGIN, 22, '依据当前中文文稿与实现整理 · 示例均为机制示意')
    canvas.drawRightString(W-MARGIN, 22, f'第 {doc.page} 页')
    canvas.restoreState()


def build_story(obs):
    from suanfashuoming_content import build_story as content_story
    return content_story(globals(), obs)


def main():
    setup_fonts()
    setup_styles()
    obs = observe()
    QA.mkdir(parents=True, exist_ok=True)
    (QA/'evidence_snapshot.json').write_text(json.dumps(obs, ensure_ascii=False, indent=2), encoding='utf-8')
    doc = Document(str(OUTPUT), pagesize=A4, leftMargin=MARGIN, rightMargin=MARGIN,
                   topMargin=51, bottomMargin=46, title='文稿算法求解逻辑详解：RL-DMCT',
                   author='RDMCT-A3C 项目技术说明', pageCompression=1)
    frame = Frame(MARGIN, 46, CONTENT, H-51-46, leftPadding=0, bottomPadding=0,
                  rightPadding=0, topPadding=0, id='content')
    doc.addPageTemplates(PageTemplate(id='main', frames=[frame], onPage=decorate))
    doc.build(build_story(obs))
    print(json.dumps(dict(output=str(OUTPUT), bytes=OUTPUT.stat().st_size,
                          observed_at=obs['observed_at'], status=obs['status']), ensure_ascii=False))


if __name__ == '__main__':
    main()
