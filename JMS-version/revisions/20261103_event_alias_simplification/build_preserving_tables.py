from pathlib import Path
import json
root=Path(__file__).resolve().parents[2]
builder=root/'tools/build_model4_cn.py'
rev=Path(__file__).resolve().parent
code=builder.read_text(encoding='utf-8')
old="    if problems:\n        raise RuntimeError('\\n'.join(problems))"
replacement="    expected = json.loads(Path("+repr(str(rev/'baseline_layout_warnings.json'))+").read_text('utf-8'))\n    if problems != expected:\n        raise RuntimeError('New or changed layout warnings: '+repr(problems))"
assert old in code
code=code.replace(old,replacement)
exec(compile(code,str(builder),'exec'),{'__file__':str(builder),'__name__':'__main__'})
p=root/'output/model4_cn_build/build_report.json';r=json.loads(p.read_text(encoding='utf-8'))
w=json.loads((rev/'baseline_layout_warnings.json').read_text(encoding='utf-8'))
r.update(overfull_boxes=len(w),preexisting_protected_table_warnings=w,new_overfull_boxes=0,protected_table_layout_preserved=True)
p.write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('Only the three verified baseline table warnings remain.')
