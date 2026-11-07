"""Render the JMS citation-sequence bibliography from preserved source metadata.

Style: Journal of Manufacturing Systems -> Elsevier NLM/Vancouver CSL.
Does not add/delete citations or modify manuscript scientific content.
"""
from pathlib import Path
import argparse, difflib, hashlib, json, re, shutil

PAPER = Path(__file__).resolve().parents[1]
META = PAPER / 'JMS_references.json'
NAMES = ('JMS_Review_CN', 'JMS_Submission_EN')
ABBREVIATIONS = {
 'IEEE Transactions on Automation Science and Engineering':'IEEE Trans Autom Sci Eng',
 'IEEE Transactions on Semiconductor Manufacturing':'IEEE Trans Semicond Manuf',
 'IEEE Transactions on Industrial Informatics':'IEEE Trans Ind Inform',
 'IEEE/CAA Journal of Automatica Sinica':'IEEE/CAA J Autom Sin',
 'Applied Sciences':'Appl Sci',
 'Expert Systems with Applications':'Expert Syst Appl',
 'International Journal of Production Research':'Int J Prod Res',
 'Journal of Manufacturing Systems':'J Manuf Syst',
 'Pattern Recognition':'Pattern Recognit',
 'Mathematical Programming Computation':'Math Program Comput',
 'ACM Transactions on Mathematical Software':'ACM Trans Math Softw',
 'Mathematical Programming':'Math Program',
 'Machine Learning':'Mach Learn',
 'Sensors':'Sensors', 'Procedia CIRP':'Procedia CIRP', 'Measurement: Sensors':'Meas Sens',
}

def group(s, start):
    assert s[start] == '{'
    depth = 1
    i = start + 1
    while depth:
        if s[i] == '{' and s[i-1] != '\\': depth += 1
        if s[i] == '}' and s[i-1] != '\\': depth -= 1
        i += 1
    return s[start+1:i-1], i

def fields(block):
    out = {}
    for m in re.finditer(r'\\bibinfo\{',block):
        key, end = group(block, m.end()-1)
        value, end = group(block, end)
        out.setdefault(key, []).append(re.sub(r'\s+',' ',value).strip())
    return out

def blocks(s):
    matches = list(re.finditer(r'\\bibitem(?:\[.*?\])?\{([^}]+)\}',s,re.S))
    return {m.group(1):s[m.end():(matches[i+1].start() if i+1<len(matches) else s.index(r'\end{thebibliography}'))].strip() for i,m in enumerate(matches)}

def raw(authors, year, title, **kwargs):
    return dict(author=authors.split('|'),year=year,title=title,**kwargs)

RAW = {
 'appliedprecisioncvd':dict(author=['Applied Materials'], corporate=True, title='Producer XP Precision CVD', year='n.d.', type='webpage',url='https://www.appliedmaterials.com/us/en/product-library/producer-xp-precision-cvd.html',accessed='September 7, 2026'),
 'maitra2024virtual':raw('Maitra, V.|Su, Y.|Shi, J.','2024','Virtual metrology in semiconductor manufacturing: Current status and future prospects',journal='Expert Systems with Applications',volume='249',pages='123559'),
 'choi2021carbon':raw('Choi, J.E.|Hong, S.J.','2021','Machine learning-based virtual metrology on film thickness in amorphous carbon layer deposition process',journal='Measurement: Sensors',volume='16',pages='100046'),
 'weng2022jit':raw('Weng, W.|Chen, J.|Zheng, M.|Fujimura, S.','2022','Realtime scheduling heuristics for just-in-time production in large-scale flexible job shops',journal='Journal of Manufacturing Systems',volume='63',pages='64--77'),
 'rahmani2014robust':raw('Rahmani, D.|Heydari, M.','2014','Robust and stable flow shop scheduling with unexpected arrivals of new jobs and uncertain processing times',journal='Journal of Manufacturing Systems',volume='33',pages='84--92'),
 'sun2024manufacturing':raw('Sun, L.|Lyu, P.|Zhang, X.|Wu, J.|Wang, Q.|Ervin, J.|Chi, Y.','2024','Machine learning technologies for semiconductor manufacturing',booktitle='2024 Conference of Science and Technology for Integrated Circuits (CSTIC)',publisher='IEEE',pages='1--7'),
 'chen2020anomaly':raw('Chen, C.Y.|Chang, S.C.|Liao, D.Y.','2020','Equipment anomaly detection for semiconductor manufacturing by exploiting unsupervised learning from sensory data',journal='Sensors',volume='20',pages='5650'),
 'biebl2020maintenance':raw('Biebl, F.|Glawar, R.|Jalali, A.|Ansari, F.|Haslhofer, B.|de~Boer, P.|Sihn, W.','2020','A conceptual model to enable prescriptive maintenance for etching equipment in semiconductor manufacturing',journal='Procedia CIRP',volume='88',pages='64--69'),
 'wang2024hemset':raw('Wang, J.|Wang, Z.|Li, X.|Kuang, Y.|Shi, Z.|Zhu, F.|Yuan, M.|Zeng, J.|Zhang, Y.|Wu, F.','2024','Learning to Cut via Hierarchical Sequence/Set Model for Efficient Mixed-Integer Programming',type='preprint',archive='arXiv:2404.12638'),
}

def extract_metadata():
    result = {}
    for name in NAMES:
        for key,block in blocks((PAPER/(name+'.tex')).read_text('utf-8')).items():
            if key in RAW:
                entry = dict(RAW[key])
            else:
                f = fields(block)
                assert f.get('title') and f.get('author'), key
                entry = {k:(v if k=='author' else v[0]) for k,v in f.items()}
            if 'type' not in entry:
                entry['type'] = 'conference' if 'booktitle' in entry else 'article'
            for field,pattern in [('doi',r'\\doi\{([^}]+)\}'),('url',r'\\url\{([^}]+)\}')]:
                m = re.search(pattern,block)
                if m: entry[field] = m.group(1)
            if 'journal' in entry:
                entry['journal_short'] = ABBREVIATIONS[entry['journal']]
            if key in result: assert entry == result[key], f'Different metadata for {key}'
            result[key] = entry
    return result

def pages(value):
    # CSL minimal page ranges. Leave compound article:page locators intact.
    m = re.fullmatch(r'(\d+)--(\d+)',value)
    if not m: return value
    a,b = m.groups()
    if len(a)==len(b):
        i=0
        while i<len(a)-1 and a[i]==b[i]: i+=1
        b=b[i:]
    return a+'--'+b

def author(entry):
    if entry.get('corporate'): return entry['author'][0]
    values=[]
    for name in entry['author'][:6] if len(entry['author'])>=7 else entry['author']:
        surname, initials = name.rsplit(',',1)
        values.append(surname.strip()+' '+re.sub(r'[.\s]','',initials))
    if len(entry['author'])>=7: values.append('et~al.')
    return ', '.join(values)

def render(entry):
    a=author(entry)
    start=a+(' ' if a.endswith('.') else '. ')+entry['title']+'.\n'
    kind=entry['type']
    if kind=='article':
        start+=entry['journal_short']+' '+entry['year']+';'+entry['volume']+':'+pages(entry['pages'])+'.'
    elif kind=='conference':
        start+='In: '+entry['booktitle']+'. '+(entry.get('publisher','')+'; ' if entry.get('publisher') else '')+entry['year']
        if entry.get('pages'): start+=', p. '+pages(entry['pages'])
        start+='.'
    elif kind=='preprint':
        start+='[Preprint]. '+entry['archive']+'; '+entry['year']+'.'
    elif kind=='webpage':
        start+=entry['year'].rstrip('.')+'.'
    else: raise ValueError(kind)
    if entry.get('doi'):
        start+='\n\\url{https://doi.org/'+entry['doi']+'}.'
    elif entry.get('url'):
        start+='\n\\url{'+entry['url']+'}'
        if entry.get('accessed'): start+=' (accessed '+entry['accessed']+')'
        start+='.'
    return start

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--record',required=True,help='New review directory relative to JMS-version')
    args=parser.parse_args()
    audit=(PAPER/args.record).resolve()
    assert audit.is_relative_to(PAPER)
    backup=audit/'before';backup.mkdir(parents=True,exist_ok=True)
    metadata=json.loads(META.read_text('utf-8')) if META.exists() else extract_metadata()
    result={}
    for name in NAMES:
        path=PAPER/(name+'.tex');old=path.read_text('utf-8')
        oldblocks=blocks(old)
        before,rest=old.split(r'\begin{thebibliography}',1)
        tail=rest.split(r'\end{thebibliography}',1)[1]
        keys=list(dict.fromkeys(k.strip() for g in re.findall(r'\\cite\w*\{([^}]+)\}',before) for k in g.split(',')))
        assert set(keys)==set(oldblocks), 'Uncited or missing entry: '+name
        assert set(keys)<=set(metadata)
        for ext in ('.tex','.pdf'):
            src=PAPER/(name+ext)
            if src.exists():
                assert not (backup/src.name).exists(), 'Do not overwrite a dated backup'
                shutil.copy2(src,backup/src.name)
        before=before.replace(r'\biboptions{sort&compress}',r'\biboptions{numbers,sort&compress}')
        new=before+'\\begin{thebibliography}{'+str(len(keys))+'}\n'
        new+='% JMS: Elsevier NLM/Vancouver, first-citation order. Generated by tools/format_jms_references.py.\n\\interlinepenalty=10000\n\n'
        new+='\n\n'.join('\\bibitem{'+key+'}\n'+render(metadata[key]) for key in keys)
        new+='\n\n\\end{thebibliography}'+tail
        # Reference formatting and numeric-citation option are the only changes.
        assert old.split(r'\begin{thebibliography}')[0].replace(r'\biboptions{sort&compress}',r'\biboptions{numbers,sort&compress}')==before
        path.write_text(new,encoding='utf-8',newline='\n')
        (audit/(name+'.diff')).write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='before/'+path.name,tofile=path.name)),encoding='utf-8')
        result[name]={'count':len(keys),'old_order':list(oldblocks),'new_order':keys,'content_before_bibliography_unchanged_except_numeric_option':True,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
    META.write_text(json.dumps(metadata,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (audit/'reference_audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:{'references':v['count'],'first_four':v['new_order'][:4]} for k,v in result.items()},indent=2))

if __name__=='__main__': main()
