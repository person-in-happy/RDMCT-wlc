from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent
PREV=HERE.parent/'symbol_definitions_20261015'
for filename in ['header.tex','build_manuscript.py','build_pdf.py']:
    shutil.copy2(PREV/filename,HERE/filename)
p=HERE/'build_manuscript.py'
s=p.read_text(encoding='utf-8')
s=s.replace('assert eq(old)==eq(new) and len(eq(new))==42', '''assert len(eq(new))==42
changed=[]
for before,after in zip(eq(old),eq(new)):
    if before!=after: changed.append(re.search(r'\\\\label\\{([^}]+)\\}',after)[1])
assert set(changed)=={'eq:primary-objective-cn','eq:secondary-wait-cn','eq:secondary-rhythm-cn','eq:secondary-objective-cn'},changed''')
s=s.replace("'equations_unchanged':42", "'equations_unchanged':38,'equations_simplified':changed")
p.write_text(s,encoding='utf-8')
p=HERE/'build_pdf.py'
s=p.read_text(encoding='utf-8').replace("'symbol_entries':58", "'symbol_entries':sum(mapping['symbol_rows'])")
p.write_text(s,encoding='utf-8')
print('Prepared independent compilation and formula-difference checks.')
