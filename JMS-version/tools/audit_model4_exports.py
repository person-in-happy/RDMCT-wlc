"""Independent read-only audit of serialized Model4 handling sequences."""
from collections import Counter
import argparse, gzip, hashlib, json, re, time
from pathlib import Path
from model4_feasible_orders import ROOT, family_count, unrank_plan, allowed, sha

def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--report', type=Path, default=ROOT/'JMS-version/revisions/20261027_model4/export_audit.json')
    args=parser.parse_args()
    base=ROOT/'JMS-version/gif/kexingyu/model4_pjob_20261027'
    manifest=json.loads((base/'manifest.json').read_text('utf-8'))
    report={'files':[], 'failed':0, 'identity_permutations_counted':False}
    for rel,expected in manifest['dependencies'].items():
        assert sha(ROOT/rel)==expected,rel
        assert sha(base/'evidence/frozen_code'/rel)==expected,rel
    for item in manifest['files']:
        start=time.monotonic(); unique=set(); cases=Counter(); count=0
        path=base/item['path']
        for key,hashkey in [('path','sha256'),('compressed_path','compressed_sha256'),
                            ('index','index_sha256'),('representative_witnesses','representative_sha256')]:
            assert sha(base/item[key])==item[hashkey]
        digest=hashlib.sha256()
        with gzip.open(base/item['compressed_path'],'rb') as stream:
            for data in iter(lambda:stream.read(4*1024*1024),b''):digest.update(data)
        assert digest.hexdigest()==item['sha256']
        with path.open('rb') as stream,gzip.open(base/item['index'],'rt',encoding='utf-8') as index:
            for line in index:
                row=json.loads(line);count+=1
                assert row['id']==count
                stream.seek(row['offset'])
                lines=stream.read(row['bytes']).decode('utf-8').splitlines()
                assert lines[0].startswith(f'[{count:06d}]') and len(lines)==3
                chain=lines[1];digest=hashlib.sha256(chain.encode('utf-8')).hexdigest()
                assert digest==row['sequence_sha256'] and digest not in unique
                unique.add(digest)
                pickups=re.findall(r'LP([1-4])\.(\d+) ATR取 LP([1-4])',chain)
                loads=re.findall(r'LP([1-4])\.(\d+)\+PEC\d+ VTR放 CH([23])',chain)
                assert len(pickups)==len(loads)==item['n']
                mapping={(int(lp),int(slot)):int(c) for lp,slot,c in loads}
                assert len(mapping)==item['n']
                seen=Counter();plan=[]
                for lp,slot,location in pickups:
                    lp,slot,location=map(int,(lp,slot,location));assert lp==location
                    seen[lp]+=1;assert slot==seen[lp]
                    chamber=mapping[lp,slot];assert chamber in allowed(lp)
                    plan.append((lp,chamber))
                assert seen==Counter({lp:item['n']//4 for lp in range(1,5)})
                assert plan==unrank_plan(item['n'],int(row['rank']))
                cases[row['recipe']]+=1
                if count%10000==0 or count==item['count']:
                    elapsed=time.monotonic()-start
                    print(f'n={item["n"]} audited={count}/{item["count"]} failed=0 ETA={elapsed/count*(item["count"]-count):.1f}s',flush=True)
        assert count==item['count'] and str(family_count(item['n']))==item['family_count_per_configuration']
        assert all(cases[k.split('_H')[0]]==v for k,v in item['per_configuration'].items())
        report['files'].append(dict(n=item['n'],records=count,distinct=len(unique),
            text_sha256=item['sha256'],lossless_gzip=True,inventory_eligibility_canonical_ids=True,
            index_offsets_and_hashes=True,full_space_count=None))
    report['total_records']=sum(v['records'] for v in report['files'])
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
    print('AUDIT COMPLETE '+str(report['total_records']),flush=True)

if __name__=='__main__':main()
