"""Update review entry points and create a flat, Chinese-only source bundle."""
from pathlib import Path
import json, hashlib, shutil, zipfile, subprocess

HERE=Path(__file__).resolve().parent
CIE=HERE.parents[1]
P=CIE/'products'
notice='''> **2026-11-09 当前版本说明（覆盖下方历史状态）：** 模型和实验冲突一律以新版 `JMS-version/JMS_Review_CN.tex` 为准。当前更新稿是 [CIE 中文稿](products/rdmct_cie_analysis_focused_zh.tex)，补强实验见 [新命令](docs/CIE_CURRENT_EXPERIMENT_COMMANDS.md)，投稿缺口见 [审查记录](products/CIE_CURRENT_REVIEW_CN.md)。下方旧模型、旧统计与固定内存命令仅保留历史记录，不适用于当前稿。旧英文正文、旧补充稿及20260817源包尚未同步，不得和当前中文稿/新Highlights/新标题页混合提交。

---

'''
for relative in ('README.md','products/README.md','products/manuscript_versions.md',
                 'products/submission_metadata.md','products/submission_metadata_analysis_focused.md',
                 'docs/cie_submission_runbook_zh.md'):
    f=CIE/relative
    if not f.exists():continue
    txt=f.read_text('utf-8-sig')
    if txt.startswith('> **2026-11-09 当前版本说明'):continue
    backup=HERE/'before'/relative.replace('/','__')
    if not backup.exists():shutil.copy2(f,backup)
    banner=notice
    if f.parent!=CIE:
        banner=banner.replace('(products/','(../products/').replace('(docs/','(../docs/')
    f.write_text(banner+txt,encoding='utf-8')

# A single current Chinese entry; the old source remains in before/.
(P/'rdmct_cie_draft_zh.tex').write_text('% Current Chinese review entry; historical source in revisions/20261109_jms_alignment/before/.\n\\input{rdmct_cie_analysis_focused_zh.tex}\n',encoding='utf-8')
shutil.copy2(P/'rdmct_cie_analysis_focused_zh.pdf',P/'rdmct_cie_draft_zh.pdf')

# Remove only obsolete render images from earlier iterations, within this directory.
report=json.loads((HERE/'build_report.json').read_text('utf-8'))
for f in (HERE/'rendered').glob('*.png'):
    stem=f.stem
    if stem.startswith(('page-','contact-')) and int(stem.rsplit('-',1)[1])>report['pages']:
        f.unlink()

name='rdmct_cie_analysis_focused_zh'
manifest=json.loads((HERE/'migration_manifest.json').read_text('utf-8'))
stage=HERE/'bundle';stage.mkdir(exist_ok=True)
files=[P/(name+'.tex'),P/'rdmct_cie_current_references.bib',HERE/'build'/(name+'.bbl')]
files += [P/item['file'] for item in manifest['figures']]
for f in files:shutil.copy2(f,stage/f.name)
(stage/'README.txt').write_text('Chinese anonymous REVIEW SOURCE only; not a synchronized English submission.\nCompile with a current TeX distribution including elsarticle, ctex, biblatex-apa and Biber:\nxelatex '+name+'\nbiber '+name+'\nxelatex '+name+'\nxelatex '+name+'\nAll assets are flat. Title page and cover letter are intentionally separate.\n',encoding='utf-8')
zip_path=P/'CIE_current_CN_review_source_20261109.zip'
with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED) as z:
    for f in stage.iterdir():z.write(f,f.name)
verify=HERE/'bundle_verify';verify.mkdir(exist_ok=True)
with zipfile.ZipFile(zip_path) as z:z.extractall(verify)
commands=[['xelatex','-interaction=nonstopmode','-halt-on-error',name+'.tex'],['biber',name]]
commands += [commands[0]]*2
for i,cmd in enumerate(commands):
    r=subprocess.run(cmd,cwd=verify,capture_output=True,text=True,encoding='utf-8',errors='replace')
    (verify/f'pass_{i+1}.txt').write_text(r.stdout+r.stderr,encoding='utf-8')
    print('bundle',i+1,r.returncode,flush=True)
    if r.returncode:raise RuntimeError(r.stdout[-1200:])
log=(verify/(name+'.log')).read_text('utf-8',errors='replace')
issues=[s for s in log.splitlines() if any(x in s for x in ('Overfull','undefined','multiply defined','Missing character','LaTeX Error'))]
assert not issues,issues
(HERE/'bundle_report.json').write_text(json.dumps(dict(zip=str(zip_path),sha256=hashlib.sha256(zip_path.read_bytes()).hexdigest(),files=[f.name for f in stage.iterdir()],isolated_compile=True,issues=issues,english_submission_ready=False),indent=2),encoding='utf-8')
