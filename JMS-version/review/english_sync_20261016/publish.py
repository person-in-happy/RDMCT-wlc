from pathlib import Path
import hashlib,json,shutil
HERE=Path(__file__).resolve().parent; PAPER=HERE.parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
mapping=json.loads((HERE/'equation_mapping.json').read_text())
en=json.loads((HERE/'english_build_report.json').read_text())
md=json.loads((HERE/'build_report.json').read_text())
assert sha(PAPER/'JMS_Review_CN.tex')==mapping['manuscript_sha256']
assert sha(PAPER/'JMS_Submission_EN.tex')==mapping['english_sha256']==en['source_sha256']
assert sha(PAPER/'MODEL_EXPLANATION_CN.md')==md['markdown_sha256']
assert not en['issues'] and not md['compile_issues']
out=PAPER/'output/pdf';out.mkdir(parents=True,exist_ok=True)
deliveries=[(HERE/'english_build/JMS_Submission_EN.pdf',PAPER/'JMS_Submission_EN.pdf'),
            (HERE/'english_build/JMS_Submission_EN.pdf',out/'JMS_Submission_EN.pdf'),
            (HERE/'build/MODEL_EXPLANATION_CN.pdf',out/'MODEL_EXPLANATION_CN.pdf')]
records=[]
for source,dest in deliveries:
    shutil.copy2(source,dest)
    assert sha(source)==sha(dest)
    records.append({'path':str(dest),'sha256':sha(dest)})
report={'chinese_source_sha256':mapping['manuscript_sha256'],'english_source_sha256':mapping['english_sha256'],
        'explanation_source_sha256':md['markdown_sha256'],'english_pages':en['pages'],'explanation_pages':md['pages'],
        'outputs':records}
(HERE/'delivery_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
