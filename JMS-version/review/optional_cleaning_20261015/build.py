from pathlib import Path
import re,json,subprocess,hashlib
import pymupdf
from PIL import Image,ImageDraw

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
tex=(PAPER/'JMS_Review_CN.tex').read_text(encoding='utf-8')
old=(HERE/'JMS_Review_CN.before.tex').read_text(encoding='utf-8')
md=(PAPER/'MODEL_EXPLANATION_CN.md').read_text(encoding='utf-8')
equations=lambda s:{re.search(r'\\label\{([^}]+)\}',m[1])[1]:re.sub(r'\\label\{[^}]+\}','',m[1]).strip()
    for m in re.finditer(r'\\begin\{equation\}(.*?)\\end\{equation\}',s,re.S)}
before=equations(old);after=equations(tex)
assert len(after)==42 and before.keys()==after.keys()
changed=[k for k in after if before[k]!=after[k]]
assert set(changed)=={'eq:candidate-bounds-cn','eq:clean-counter-cn'}
matches=list(re.finditer(r'<!-- (eq:[^ ]+) -->\s*\$\$(.*?)\$\$',md,re.S))
assert len(matches)==42
for i,m in enumerate(matches,1):
    assert re.sub(r'\\tag\{\d+\}','',m[2]).strip()==after[m[1]],m[1]
    assert re.search(r'\\tag\{(\d+)\}',m[2])[1]==str(i)
floats=lambda s:re.findall(r'\\begin\{(?:table\*?|figure\*?)\}.*?\\end\{(?:table\*?|figure\*?)\}',s[s.index(r'\section{计算实验与结果分析}'):],re.S)
assert floats(old)==floats(tex)
assert re.findall(r'\\cite[pt]?\{[^}]+\}',old)==re.findall(r'\\cite[pt]?\{[^}]+\}',tex)

def run(cmd,cwd,log):
    result=subprocess.run(cmd,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    log.write_bytes(result.stdout)
    if result.returncode:raise RuntimeError(result.stdout[-5000:].decode('utf-8',errors='replace'))

build=HERE/'build';build.mkdir(exist_ok=True)
export=md.split('\n',1)[1]
export=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',lambda m:m[0] if re.match(r'https?://',m[2]) else m[1],export)
(build/'explanation.md').write_text(export,encoding='utf-8')
run(['pandoc',str(build/'explanation.md'),'-f','markdown+tex_math_dollars+raw_tex','-s','-t','latex',
    '-o',str(build/'MODEL_EXPLANATION_CN.tex'),'--toc','--toc-depth=2','-V','documentclass=ctexart',
    '-V','fontsize=10pt','-V','geometry:a4paper,margin=22mm,headsep=8mm','-V','mainfont=Cambria',
    '-V','sansfont=Microsoft YaHei','-V','monofont=Consolas','-V','colorlinks=true',
    '-M','title=稿件模型与公式逐项实例说明','-M','date=2026年10月15日 · 阈值前可选清洁修订',
    '-M','toc-title=目录','-H',str(PAPER/'review/model_simplification_20261015/header.tex')],PAPER,build/'pandoc.log')
explanation=(build/'MODEL_EXPLANATION_CN.tex').read_text(encoding='utf-8')
explanation=re.sub(r'(\\textbf\{表[12]-\d+)',r'\\Needspace{6\\baselineskip}\n\1',explanation)
explanation=explanation.replace(r'\begin{longtable}[]{@{}llll@{}}',r'\Needspace{9\baselineskip}'+'\n'+r'\begin{longtable}[]{@{}llll@{}}')
(build/'MODEL_EXPLANATION_CN.tex').write_text(explanation,encoding='utf-8')
report={'changed_equations':changed,'matching_equations':42,'historical_tables_figures_unchanged':True,'documents':{}}
for name,cwd in [('JMS_Review_CN',PAPER),('MODEL_EXPLANATION_CN',build)]:
    for i in range(3):
        run(['xelatex','-interaction=nonstopmode','-halt-on-error','-file-line-error',
            '-output-directory='+str(build),name+'.tex'],cwd,build/f'{name}_pass{i+1}.txt')
    log=(build/(name+'.log')).read_text(encoding='utf-8',errors='replace')
    issues=[line for line in log.splitlines() if any(k in line for k in ['Overfull','Float too large','undefined references','undefined on input','Missing character'])]
    doc=pymupdf.open(build/(name+'.pdf'))
    pages=[]
    for i,page in enumerate(doc):
        path=HERE/f'{name}_{i+1:02}.png'
        page.get_pixmap(matrix=pymupdf.Matrix(1.1,1.1)).save(path);pages.append(path)
    for i in range(0,len(pages),12):
        sheet=Image.new('RGB',(1600,1800),'#ddd');draw=ImageDraw.Draw(sheet)
        for j,path in enumerate(pages[i:i+12]):
            im=Image.open(path).convert('RGB');im.thumbnail((390,560))
            x=j%4*400+(400-im.width)//2;y=j//4*600+25
            sheet.paste(im,(x,y));draw.text((x,y-20),str(i+j+1),fill='black')
        sheet.save(HERE/f'{name}_contact_{i//12+1}.png')
    report['documents'][name]={'pages':len(doc),'issues':issues,'pdf':str(build/(name+'.pdf'))}
report['source_sha256']=hashlib.sha256((PAPER/'JMS_Review_CN.tex').read_bytes()).hexdigest()
(HERE/'build_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
