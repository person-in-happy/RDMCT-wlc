from pathlib import Path
import hashlib,json,re,shutil
import pymupdf

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
mr=json.loads((HERE/'manuscript_report.json').read_text())
er=json.loads((HERE/'build_report.json').read_text())
assert not mr['compile_issues'] and not er['compile_issues']
assert mr['source_sha256']==er['source_sha256']==sha(PAPER/'JMS_Review_CN.tex')
assert er['markdown_sha256']==sha(PAPER/'MODEL_EXPLANATION_CN.md')
s=(PAPER/'JMS_Review_CN.tex').read_text(encoding='utf-8')
assert 'tab:joint-search-cn' not in s
assert len(re.findall(r'\\begin\{equation\}',s))==42
assert er['symbol_entries']==43
md=(PAPER/'MODEL_EXPLANATION_CN.md').read_text(encoding='utf-8')
for removed in [r'C_{W3}',r'h_{ceq}',r'\Delta_{ceq}',r'a^{\zeta}_{cbe}',r'a^{\psi}_{cqe}',r'x^{\zeta}_{pcbl}',r'x^{\psi}_{pck}']:
    assert removed not in md,removed
outputs=[
    (HERE/'manuscript_build/JMS_Review_CN.pdf',PAPER/'JMS_Review_CN.pdf'),
    (HERE/'manuscript_build/JMS_Review_CN.pdf',PAPER/'output/pdf/JMS_Review_CN.pdf'),
    (HERE/'build/MODEL_EXPLANATION_CN.pdf',PAPER/'output/pdf/MODEL_EXPLANATION_CN.pdf'),
]
report=[]
for src,dst in outputs:
    with pymupdf.open(src) as doc:
        pages=len(doc)
    dst.parent.mkdir(exist_ok=True,parents=True)
    shutil.copy2(src,dst)
    assert sha(dst)==sha(src)
    report.append({'path':str(dst),'pages':pages,'sha256':sha(dst)})
(HERE/'delivery_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'outputs':len(outputs),'manuscript_pages':mr['pages'],'explanation_pages':er['pages'],'symbol_entries':43}))
