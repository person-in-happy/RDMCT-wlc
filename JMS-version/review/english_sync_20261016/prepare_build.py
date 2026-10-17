from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent
PREV=HERE.parent/'model_simplification_20261015'
for name in ['header.tex','build_pdf.py']:
    shutil.copy2(PREV/name,HERE/name)
p=HERE/'header.tex';p.write_text(p.read_text(encoding='utf-8').replace('2026-10-15','2026-10-16'),encoding='utf-8')
p=HERE/'build_pdf.py';p.write_text(p.read_text(encoding='utf-8').replace('2026年10月15日 · 对应修改后正文42式','2026年10月16日 · 中英文正文同步42式'),encoding='utf-8')
