"""Static final checks; does not execute experiments."""
from pathlib import Path
import ast,hashlib,json,re
from inventory import ROOT,OUT

docs=[ROOT/'JMS-version/THESIS_REVIEW_AND_PLAN_CN.md',ROOT/'JMS-version/EXPERIMENT_COMMANDS.md']
missing=[]
for p in docs:
    text=p.read_text(encoding='utf-8')
    for dest in re.findall(r'\]\(([^)]+)\)',text):
        if dest.startswith(('https:','http:','#')):continue
        path=(p.parent/dest.split('#')[0]).resolve()
        if not path.exists():missing.append({'document':str(p),'target':dest})
driver=ROOT/'JMS-version/tools/thesis_gap_experiments.py'
ast.parse(driver.read_text(encoding='utf-8'))
record=json.loads((OUT/'entry_verification.json').read_text(encoding='utf-8'))
assert hashlib.sha256(driver.read_bytes()).hexdigest()==record['driver_sha256']
old=ROOT/'JMS-version/tools/default_gap_experiments.py'
assert hashlib.sha256(old.read_bytes()).hexdigest()=='0126f320dae698a346d0322f9133eef3a5f3d44d302bf090a87885d2742daba0'
assert not missing,missing
result={'local_document_links_valid':True,'new_driver_syntax_valid':True,'driver_matches_checked_hash':True,'old_driver_unchanged':True,'formal_experiments_launched':False,'manuscript_modified':False,'documents':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in docs}}
(OUT/'delivery_checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
