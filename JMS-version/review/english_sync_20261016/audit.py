from pathlib import Path
import re,json,hashlib

HERE=Path(__file__).resolve().parent; PAPER=HERE.parents[1]
cn=(PAPER/'JMS_Review_CN.tex').read_text(encoding='utf-8')
en=(PAPER/'JMS_Submission_EN.tex').read_text(encoding='utf-8')
old=(HERE/'JMS_Submission_EN.before.tex').read_text(encoding='utf-8')
assert cn==(HERE/'JMS_Review_CN.before.tex').read_text(encoding='utf-8')
def equations(s):
    result=[]
    for m in re.finditer(r'\\begin\{equation\}(.*?)\\end\{equation\}',s,re.S):
        label=re.search(r'\\label\{([^}]+)\}',m[1])[1]
        body=re.sub(r'\\label\{[^}]+\}','',m[1])
        result.append((re.sub(r'-(?:cn|en)$','',label),re.sub(r'\s+','',body)))
    return result
assert equations(cn)==equations(en) and len(equations(en))==42
def tabulars(s):
    tables={}
    for t in re.findall(r'\\begin\{table\*?\}.*?\\end\{table\*?\}',s,re.S):
        label=re.search(r'\\label\{([^}]+)\}',t)
        if not label or 'symbol-' in label[1] or label[1].startswith('alg:'):continue
        key=re.sub(r'-(?:zh|cn|en)(?=-|$)','-LANG',label[1])
        body=t[t.index(r'\begin{tabular}'):t.index(r'\end{tabular}')]
        # Ignore layout dimensions and translated headings; data rows retain numeric tokens.
        body=body[body.index(r'\midrule'):]
        tables[key]=re.findall(r'(?<![A-Za-z])\d+(?:\.\d+)?',body)
    return tables
ct,et=tabulars(cn),tabulars(en)
assert ct.keys()==et.keys(),(ct.keys()-et.keys(),et.keys()-ct.keys())
differences={k:{'cn':ct[k],'en':et[k]} for k in ct if ct[k]!=et[k]}
assert not differences,differences
def labels(s):return set(re.findall(r'\\label\{([^}]+)\}',s))
refs=set(re.findall(r'\\(?:eqref|ref)\{([^}]+)\}',en))
assert not refs-labels(en),refs-labels(en)
oldfloat=lambda s:[t for t in re.findall(r'\\begin\{table\*?\}.*?\\end\{table\*?\}',s,re.S) if r'\label{tab:' in t and 'symbol-' not in t and 'joint-search-' not in t]
# Terminology changes are permitted; table numeric values are compared independently above.
md=(PAPER/'MODEL_EXPLANATION_CN.md').read_text(encoding='utf-8')
matches=list(re.finditer(r'<!-- (eq:[^ ]+) -->\s*\$\$(.*?)\$\$',md,re.S))
assert len(matches)==42
for i,m in enumerate(matches):
    math=re.sub(r'\\tag\{\d+\}','',m[2])
    assert re.sub(r'\s+','',math)==equations(cn)[i][1],m[1]
    assert re.search(r'\\tag\{(\d+)\}',m[2])[1]==str(i+1)
rows=json.loads((HERE/'symbol_mapping.json').read_text(encoding='utf-8'))
assert len(rows)==43
assert len(re.findall(r'\*\*表[12]-\d+',md))==43
assert r'J_{\max}=T' in en and r'1\le n_{c,q-1}\le H' in en
assert r'J_{\max}=\lfloor' not in en
assert 'tab:joint-search' not in en
report={'matching_numbered_formulas':42,'matching_symbol_rows':43,'matching_experiment_tables':len(ct),'all_references_resolved':True,'chinese_source_unchanged':True,'equation_order':[x[0] for x in equations(en)]}
(HERE/'audit_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='equation_order'}))
