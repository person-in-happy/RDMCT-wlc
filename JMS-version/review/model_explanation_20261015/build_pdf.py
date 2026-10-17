from pathlib import Path
import subprocess, re, json, hashlib
import pymupdf
from PIL import Image,ImageDraw

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
BUILD=HERE/'build'
BUILD.mkdir(exist_ok=True)
md=(PAPER/'MODEL_EXPLANATION_CN.md').read_text(encoding='utf-8')
tex=(PAPER/'JMS_Review_CN.tex').read_text(encoding='utf-8')
mapping=json.loads((HERE/'equation_mapping.json').read_text(encoding='utf-8'))
assert hashlib.sha256((PAPER/'JMS_Review_CN.tex').read_bytes()).hexdigest()==mapping['manuscript_sha256']
source_formulas={}
for m in re.finditer(r'\\begin\{equation\}(.*?)\\end\{equation\}',tex,re.S):
    label=re.search(r'\\label\{([^}]+)\}',m[1])[1]
    source_formulas[label]=re.sub(r'\\label\{[^}]+\}','',m[1]).strip()
matches=list(re.finditer(r'<!-- (eq:[^ ]+) -->\s*\$\$(.*?)\$\$',md,re.S))
assert len(matches)==42
for i,m in enumerate(matches,1):
    formula=re.sub(r'\\tag\{\d+\}','',m[2]).strip()
    assert formula==source_formulas[m[1]],m[1]
    assert re.search(r'\\tag\{(\d+)\}',m[2])[1]==str(i)
    stop=matches[i].start() if i<len(matches) else len(md)
    assert '例子' in md[m.end():stop] or '代入' in md[m.end():stop],m[1]
# Markdown export links resolve relative to the repository paper directory.
export=md.split('\n',1)[1]
export=re.sub(r'\[([^\]]+)\]\(([^)]+)\)',
    lambda m:m[0] if re.match(r'https?://',m[2]) else m[1],export)
(BUILD/'export.md').write_text(export,encoding='utf-8')
cmd=['pandoc',str(BUILD/'export.md'),'-f','markdown+tex_math_dollars+raw_tex',
     '-s','-t','latex','-o',str(BUILD/'MODEL_EXPLANATION_CN.tex'),
     '--toc','--toc-depth=2','-V','documentclass=ctexart','-V','fontsize=10pt',
     '-V','geometry:a4paper,margin=22mm,headsep=8mm',
     '-V','mainfont=Cambria','-V','sansfont=Microsoft YaHei','-V','monofont=Consolas',
     '-V','colorlinks=true','-V','linkcolor=blue','-V','urlcolor=blue',
     '-M','title=稿件模型与公式逐项实例说明','-M','date=2026年10月15日 · 对应修改后正文42式',
     '-M','toc-title=目录','-H',str(HERE/'header.tex')]
res=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
(BUILD/'pandoc.log').write_bytes(res.stdout)
assert res.returncode==0,res.stdout
latex_path=BUILD/'MODEL_EXPLANATION_CN.tex'
latex=latex_path.read_text(encoding='utf-8')
# Keep each appendix symbol heading with its definition and example.
latex=re.sub(r'(\\textbf\{表[12]-\d+)',r'\\Needspace{6\\baselineskip}\n\1',latex)
# The four-row compatibility truth table should remain on one page.
latex=latex.replace(r'\begin{longtable}[]{@{}llll@{}}',
                    r'\Needspace{9\baselineskip}'+'\n'+r'\begin{longtable}[]{@{}llll@{}}')
latex_path.write_text(latex,encoding='utf-8')
for run in range(3):
    res=subprocess.run(['xelatex','-interaction=nonstopmode','-halt-on-error','-file-line-error',
                        'MODEL_EXPLANATION_CN.tex'],cwd=BUILD,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (BUILD/f'pass_{run+1}.txt').write_bytes(res.stdout)
    if res.returncode:
        raise RuntimeError(res.stdout[-6000:].decode('utf-8',errors='replace'))
log=(BUILD/'MODEL_EXPLANATION_CN.log').read_text(encoding='utf-8',errors='replace')
issues=[line for line in log.splitlines() if any(s in line for s in
    ['Overfull','undefined references','undefined on input','Missing character','Float too large'])]
doc=pymupdf.open(BUILD/'MODEL_EXPLANATION_CN.pdf')
pngs=[]
for i,page in enumerate(doc):
    p=HERE/f'page_{i+1:02d}.png'
    page.get_pixmap(matrix=pymupdf.Matrix(1.2,1.2)).save(p)
    pngs.append(p)
for i in range(0,len(pngs),6):
    sheet=Image.new('RGB',(1350,1920),'#dddddd')
    draw=ImageDraw.Draw(sheet)
    for j,p in enumerate(pngs[i:i+6]):
        im=Image.open(p).convert('RGB'); im.thumbnail((440,915))
        x=(j%3)*450+(450-im.width)//2; y=(j//3)*960+25
        sheet.paste(im,(x,y)); draw.text((x,y-20),str(i+j+1),fill='black')
    sheet.save(HERE/f'contact_{i//6+1:02d}.png')
report={'pages':len(doc),'formulas_match_manuscript':42,'symbol_entries':58,
        'source_sha256':mapping['manuscript_sha256'],'markdown_sha256':hashlib.sha256(md.encode()).hexdigest(),
        'compile_issues':issues}
(HERE/'build_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
