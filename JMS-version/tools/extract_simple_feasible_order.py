"""Extract one large-file record and reconstruct its full feasible witness."""
from pathlib import Path
import argparse,gzip,hashlib,json
from export_simple_feasible_orders import ROOT,permutation_at,substitute,abstract_handling,render


def main():
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--directory',default='JMS-version/gif/kexingyu')
    parser.add_argument('--n',type=int,required=True,choices=(8,16,32))
    parser.add_argument('--id',type=int,required=True)
    parser.add_argument('--output',required=True,help='New directory for the extracted text and full numeric witness')
    a=parser.parse_args();base=Path(a.directory).resolve();out=Path(a.output).resolve()
    if not out.is_relative_to(ROOT/'JMS-version/gif/kexingyu'):raise ValueError('Keep extracted output under JMS-version/gif/kexingyu')
    manifest=json.loads((base/'simple_manifest.json').read_text(encoding='utf-8'))
    entry=next(v for v in manifest['files'] if v['n']==a.n)
    if not 1<=a.id<=entry['count']:raise ValueError('Record number out of range')
    with gzip.open(base/entry['index'],'rt',encoding='utf-8') as stream:
        row=next(json.loads(line) for line in stream if json.loads(line)['id']==a.id)
    with gzip.open(base/entry['templates'],'rt',encoding='utf-8') as stream:template=json.load(stream)[row['template']]
    ids=[f'LP{lp}_W{w}' for lp in range(1,5) for w in range(1,a.n//4+1)]
    order=permutation_at(ids,int(row['permutation_rank']));text=render(template['groups'],order)
    if hashlib.sha256(text.encode('utf-8')).hexdigest()!=row['sequence_sha256']:raise ValueError('Reconstruction hash mismatch')
    with (base/entry['path']).open('rb') as stream:
        stream.seek(row['offset']);record=stream.read(row['bytes']).decode('utf-8')
    if record.split('\n')[1]!=text:raise ValueError('Text and witness do not match')
    witnesses={case:substitute(data,order) for case,data in template['witnesses'].items()}
    for witness in witnesses.values():
        if render(abstract_handling(witness),order)!=text:raise ValueError('Projection mismatch')
    out.mkdir(parents=True,exist_ok=False)
    (out/'sequence.txt').write_text(record,encoding='utf-8-sig')
    (out/'witnesses.json').write_text(json.dumps(witnesses,ensure_ascii=False,indent=2),encoding='utf-8')
    print('EXTRACTED and physically revalidated '+str(out))


if __name__=='__main__':main()
