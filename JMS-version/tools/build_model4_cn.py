"""Compile and audit the Model4 Chinese manuscript without changing English assets."""
from pathlib import Path
import hashlib, json, re, shutil, subprocess
import pymupdf

PAPER = Path(__file__).resolve().parents[1]
BUILD = PAPER/'output/model4_cn_build'


def main():
    BUILD.mkdir(parents=True, exist_ok=True)
    # Compile a local source/figure snapshot so editor builds in PAPER cannot
    # concurrently truncate the auxiliary files read at the end of a pass.
    source = (PAPER/'JMS_Review_CN.tex').read_text('utf-8')
    shutil.copy2(PAPER/'JMS_Review_CN.tex', BUILD/'JMS_Review_CN.tex')
    for name in re.findall(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', source):
        matches = [p for p in (PAPER/'figures').rglob(name+'.*') if p.suffix.lower() in ('.pdf','.png','.jpg','.jpeg','.eps')]
        if not matches:
            raise FileNotFoundError('Missing manuscript figure: '+name)
        for figure in matches:
            target = BUILD/figure.relative_to(PAPER)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(figure,target)
    for iteration in range(3):
        result = subprocess.run(['xelatex', '-interaction=nonstopmode', '-halt-on-error',
            '-file-line-error', '-output-directory='+str(BUILD), 'JMS_Review_CN.tex'],
            cwd=BUILD, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        (BUILD/f'pass_{iteration+1}.txt').write_bytes(result.stdout)
        if result.returncode:
            raise RuntimeError(result.stdout[-5000:].decode('utf-8', errors='replace'))
        print(f'XeLaTeX completed={iteration+1}/3 failed=0', flush=True)
    log = (BUILD/'JMS_Review_CN.log').read_text('utf-8', errors='replace')
    problems = [line for line in log.splitlines() if any(term in line for term in
        ('Overfull', 'undefined references', 'undefined on input', 'Float too large', 'multiply defined'))]
    if problems:
        raise RuntimeError('\n'.join(problems))
    source = (PAPER/'JMS_Review_CN.tex').read_text('utf-8')
    labels = re.findall(r'\\label\{([^}]+)\}', source)
    refs = re.findall(r'\\(?:ref|eqref)\{([^}]+)\}', source)
    assert len(labels) == len(set(labels)), 'Duplicate labels'
    assert not(set(refs)-set(labels)), 'Missing labels'
    assert source.count('\\label{tab:symbol-cn-a}') == 1
    assert source.count('\\caption{批次任务调度的参数与集合配置（续）}') <= 1
    assert source.count('批次任务调度的关键决策变量') == 1
    assert '模型4' not in source and '模型2' not in source, 'Internal model labels in submission text'
    assert 'a_{wpr}' not in source and 'm_w' not in source
    pdf = BUILD/'JMS_Review_CN.pdf'
    doc = pymupdf.open(pdf)
    pages = []
    for index, page in enumerate(doc):
        text = ''.join(page.get_text().split())
        if any(term in text for term in ('批次任务调度的参数与集合配置', '批次任务调度的输入参数与集合配置', '批次任务调度的关键决策变量',
            '算法末端的晶圆排程解码', '求解覆盖及停止状态', '时序精修的阶段内变化',
            '规范化晶圆取放顺序的导出数量', '双源实例预处理前的规模')):
            pages.append(index)
            page.get_pixmap(matrix=pymupdf.Matrix(1.7,1.7)).save(BUILD/f'review_page_{index+1:02d}.png')
    from PIL import Image, ImageOps, ImageDraw
    for begin in range(0, len(doc), 6):
        canvas = Image.new('RGB',(1200,1500),'#dddddd')
        draw = ImageDraw.Draw(canvas)
        for pos,index in enumerate(range(begin,min(begin+6,len(doc)))):
            pix = doc[index].get_pixmap(matrix=pymupdf.Matrix(.65,.65))
            im = Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
            im.thumbnail((380,710))
            x=(pos%3)*400+10; y=(pos//3)*750+30
            canvas.paste(im,(x,y));draw.text((x,y-20),f'Page {index+1}',fill='black')
        canvas.save(BUILD/f'contact_{begin+1:02d}.jpg')
    for target in (PAPER/'JMS_Review_CN.pdf', PAPER/'output/pdf/JMS_Review_CN.pdf'):
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(pdf,target)
    report=dict(pages=len(doc), reviewed_page_candidates=[p+1 for p in pages],
        source_sha256=hashlib.sha256((PAPER/'JMS_Review_CN.tex').read_bytes()).hexdigest(),
        pdf_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(), undefined_references=0,
        overfull_boxes=0, duplicate_labels=0, compilation_passes=3)
    (BUILD/'build_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps(report,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
