"""Lossless gzip exports for Git, and verified local text restoration."""
from pathlib import Path
import argparse,gzip,hashlib,json,shutil

ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'JMS-version/gif/kexingyu'


def digest(path):
    value=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(8*1024*1024),b''):value.update(block)
    return value.hexdigest()


def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--restore',action='store_true');a=parser.parse_args()
    catalog=BASE/'compressed_exports.json'
    if a.restore:
        for entry in json.loads(catalog.read_text(encoding='utf-8'))['files']:
            source=BASE/entry['gzip'];target=BASE/entry['text']
            if target.exists():
                if digest(target)!=entry['text_sha256']:raise ValueError('Existing text differs: '+str(target))
                print('ALREADY VERIFIED '+target.name,flush=True);continue
            if digest(source)!=entry['gzip_sha256']:raise ValueError('Compressed file hash mismatch')
            temporary=target.with_suffix('.txt.restoring')
            with gzip.open(source,'rb') as src,temporary.open('xb') as dst:shutil.copyfileobj(src,dst,8*1024*1024)
            if digest(temporary)!=entry['text_sha256']:raise ValueError('Restored text hash mismatch')
            temporary.rename(target);print('RESTORED '+target.name,flush=True)
        return
    records=[]
    for name in ('manifest.json','simple_manifest.json'):
        manifest=json.loads((BASE/name).read_text(encoding='utf-8-sig'))
        for entry in manifest['files']:
            source=BASE/entry['path'];target=source.with_suffix('.txt.gz')
            if digest(source)!=entry['sha256']:raise ValueError('Text differs from manifest')
            if target.exists():raise ValueError('Preserve existing archive: '+str(target))
            with source.open('rb') as src,target.open('xb') as raw:
                with gzip.GzipFile(filename='',mode='wb',fileobj=raw,compresslevel=6,mtime=0) as dst:shutil.copyfileobj(src,dst,8*1024*1024)
            check=hashlib.sha256()
            with gzip.open(target,'rb') as stream:
                for block in iter(lambda:stream.read(8*1024*1024),b''):check.update(block)
            if check.hexdigest()!=entry['sha256']:raise ValueError('Lossless verification failed')
            records.append(dict(text=source.name,gzip=target.name,text_sha256=entry['sha256'],gzip_sha256=digest(target),
                                original_bytes=source.stat().st_size,compressed_bytes=target.stat().st_size))
            print('VERIFIED '+target.name+' '+str(target.stat().st_size)+' bytes',flush=True)
    catalog.write_text(json.dumps(dict(files=records),ensure_ascii=False,indent=2),encoding='utf-8')


if __name__=='__main__':main()
