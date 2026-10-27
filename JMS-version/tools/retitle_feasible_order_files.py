"""Update derived text headers and offset indexes, preserving sequence bodies."""
from pathlib import Path
from datetime import datetime,timezone
import gzip,hashlib,json,math,os
from feasible_order_titles import filename,heading

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'JMS-version/gif/kexingyu'


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
    return h.hexdigest()


def main():
    backup=BASE/'title_revision_20261027'
    if not backup.is_dir():raise ValueError('Preserve original manifests/indexes before this migration')
    replacements={};audit=[]
    for name,simple in (('manifest.json',False),('simple_manifest.json',True)):
        manifest=json.loads((BASE/name).read_text(encoding='utf-8'))
        for entry in manifest['files']:
            n=entry['n'];count=entry['count'] if simple else entry['unique_orders']
            original=BASE/entry['path'];dest=BASE/filename(n,count,simple)
            if dest.exists():raise ValueError('Already exists: '+str(dest))
            if digest(original)!=entry['sha256']:raise ValueError('Original text hash mismatch')
            previous=entry['path'];body_hash=hashlib.sha256();new_hash=hashlib.sha256()
            header=heading(n,count,simple).encode('utf-8-sig')
            temporary=dest.with_suffix('.txt.pending')
            with original.open('rb') as source,temporary.open('xb') as target:
                old_header=source.readline();target.write(header);new_hash.update(header)
                for block in iter(lambda:source.read(8*1024*1024),b''):
                    target.write(block);body_hash.update(block);new_hash.update(block)
            if digest(temporary)!=new_hash.hexdigest():raise RuntimeError('Written text hash mismatch')
            delta=len(header)-len(old_header)
            if simple:
                index=BASE/entry['index']
                if digest(index)!=entry['index_sha256']:raise ValueError('Original index hash mismatch')
                temp_index=index.with_suffix('.gz.pending');rows=0
                with gzip.open(index,'rt',encoding='utf-8') as source,gzip.open(temp_index,'wt',encoding='utf-8') as target:
                    for line in source:
                        row=json.loads(line);row['offset']+=delta;rows+=1
                        target.write(json.dumps(row,separators=(',',':'))+'\n')
                if rows!=count:raise ValueError('Index count mismatch')
                # All indexed text chunks remain byte-identical; verify boundary samples.
                with gzip.open(temp_index,'rt',encoding='utf-8') as source,temporary.open('rb') as target:
                    for line in source:
                        row=json.loads(line)
                        if row['id'] in (1,count//2,count):
                            target.seek(row['offset']);record=target.read(row['bytes']).decode('utf-8')
                            if hashlib.sha256(record.split('\n')[1].encode('utf-8')).hexdigest()!=row['sequence_sha256']:
                                raise RuntimeError('Index offset repair failed')
                os.replace(temp_index,index);entry['index_sha256']=digest(index)
            # Rename only the explicitly verified files within the requested directory.
            assert original.resolve().parent==BASE.resolve() and dest.resolve().parent==BASE.resolve()
            os.replace(temporary,dest);original.unlink()
            replacements[previous]=dest.name
            entry.update(path=dest.name,sha256=new_hash.hexdigest(),bytes=dest.stat().st_size,
                lower_bound_per_configuration=str(math.factorial(n)),lower_bound_type='constructive N!; not an estimate',
                exact_total_known=False)
            audit.append(dict(old_path=previous,new_path=dest.name,old_header=old_header.decode('utf-8-sig'),
                new_header=header.decode('utf-8-sig'),header_byte_delta=delta,unchanged_body_sha256=body_hash.hexdigest(),
                lower_bound_per_configuration=str(math.factorial(n)),exported_count=count))
            print('UPDATED '+dest.name,flush=True)
        manifest['title_revision_utc']=datetime.now(timezone.utc).isoformat()
        manifest['bound_scope']='Each fixed pure-recipe/H configuration; original 100000-second horizon; no optimum or additional Cmax restriction.'
        (BASE/name).write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    for path in BASE.glob('README*.md'):
        text=path.read_text(encoding='utf-8-sig')
        for old,new in replacements.items():text=text.replace(old,new)
        path.write_text(text,encoding='utf-8-sig')
    (backup/'revision_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
