"""Read-only evidence inventory; never imports/runs experiment code."""
from pathlib import Path
import json
from collections import Counter

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SKIP = {'.git', '__pycache__', '.pytest_cache', 'frozen_code', 'frozen_sources', 'node_modules', '.venv'}

def walk(base):
    import os
    for directory, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for f in files:
            yield Path(directory) / f

def main():
    import sys
    if len(sys.argv) > 1:
        for s in sys.argv[1:]:
            p = ROOT/s
            print('\nFILE',s)
            if p.is_dir():
                print('\n'.join(str(q.relative_to(ROOT)) for q in list(walk(p))[:35]))
                continue
            if p.suffix == '.json':
                d = json.loads(p.read_text(encoding='utf-8-sig'))
                if isinstance(d, list):
                    print('list_length',len(d),'first',str(d[:1])[:3500])
                else:
                    print('keys',list(d))
                    print(str(d)[:4500])
            else:
                print(p.read_text(encoding='utf-8-sig')[:12000])
        return
    records = []
    for base in [ROOT/'JMS-version/results', ROOT/'JMS/results', ROOT/'cie/results', ROOT/'T-ASE-version/results', ROOT/'RL-SAT', ROOT/'ablation_results', ROOT/'_results']:
        if not base.exists():
            continue
        for campaign in sorted(p for p in base.iterdir() if p.is_dir()):
            files = list(walk(campaign))
            interesting = [p for p in files if p.suffix.lower() in {'.csv','.json','.md'} and any(x in p.name.lower() for x in ['summary','report','audit','protocol','manifest','status','progress','validation','analysis','certificate'])]
            records.append({'campaign':str(campaign.relative_to(ROOT)).replace('\\','/'), 'files':len(files), 'extensions':dict(Counter(p.suffix for p in files)), 'evidence_files':[str(p.relative_to(ROOT)).replace('\\','/') for p in interesting]})
    (OUT/'inventory.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    for r in records:
        print(r['campaign'],r['files'],len(r['evidence_files']))

if __name__ == '__main__':
    main()
