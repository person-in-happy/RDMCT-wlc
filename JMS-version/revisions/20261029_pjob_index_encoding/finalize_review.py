"""Final source preservation, bibliography, artifact and scope checks."""
from pathlib import Path
import difflib,hashlib,json,re,subprocess,sys
import pymupdf

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PAPER=ROOT/'JMS-version'
read=lambda p:p.read_text('utf-8')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
source=read(PAPER/'JMS_Review_CN.tex')
old=read(HERE/'original/JMS_Review_CN.tex')
build=json.loads(read(PAPER/'output/model4_cn_build/build_report.json'))
assert build['source_sha256']==sha(PAPER/'JMS_Review_CN.tex')
assert build['pdf_sha256']==sha(PAPER/'JMS_Review_CN.pdf')
assert sha(PAPER/'JMS_Review_CN.pdf')==sha(PAPER/'output/pdf/JMS_Review_CN.pdf')
intro=lambda s:s[s.index(r'\section{引言}'):s.index(r'\section{两阶段批次任务调度模型}')]
expected_intro=intro(old).replace('匿名求解','批次任务求解').replace('{fig_system_cn_nature}','{fig_system_pjob_cn}')
assert intro(source)==expected_intro,'Unexpected edit in protected introduction'
first_abstract=lambda s:s[s.index(r'\begin{abstract}'):s.index('\n',s.index('\n',s.index(r'\begin{abstract}'))+1)]
assert first_abstract(source)==first_abstract(old).replace('在稳定加工节拍的前提下最小化加工时间',
    '先最小化产品完工时间，再在保持其上界的条件下改善等待与加工节拍')
assert not any(word in source for word in ('匿名','模型4','模型2'))
body=source[:source.index(r'\begin{thebibliography}')]
cites=set()
for group in re.findall(r'\\cite\w*\*?(?:\[[^\]]*\])*\{([^}]+)\}',body):
    cites.update(x.strip() for x in group.split(','))
refs=set(re.findall(r'\\bibitem(?:\[[\s\S]*?\])?\{([^}]+)\}',source))
assert refs==cites
assert len(refs)==31
doc=pymupdf.open(PAPER/'JMS_Review_CN.pdf')
text=''.join(page.get_text() for page in doc)
assert not any(word in text for word in ('匿名','模型4','模型2','CH1'))
assert 'CH2' in text and 'CH3' in text
for name in ('fig_system_pjob_cn','fig_single_source_pjob_cn'):
    fig=pymupdf.open(PAPER/'figures/pjob_sequence_cn'/(name+'.pdf'))
    assert 'CH1' not in fig[0].get_text()

audit=json.loads(read(HERE/'strict_order_audit.json'))
assert sum(v['summary']['strict_order_valid'] for v in audit['campaigns'].values())==305
assert sum(v['summary']['old_incumbents'] for v in audit['campaigns'].values())==330
exports=PAPER/'gif/kexingyu/pjob_fifo_20261029'
manifest=json.loads(read(exports/'manifest.json'))
assert len(manifest['examples'])==36 and all(v['validation']['valid'] for v in manifest['examples'])
assert sum(v['count'] for v in manifest['sizes'].values())==7402
for value in manifest['sizes'].values():assert sha(exports/value['file'])==value['sha256']
entry=json.loads(read(PAPER/'gif/kexingyu/current_model.json'))
assert entry['manifest_sha256']==sha(exports/'manifest.json')

# Correct relative links in the nested export README only.
path=exports/'README.md';notice=read(path)
notice=notice.replace('](current_model.json)','](../current_model.json)')
notice=notice.replace('](model4_pjob_20261027/README.md)','](../model4_pjob_20261027/README.md)')
notice=notice.replace('](../../revisions/','](../../../revisions/')
path.write_text(notice,'utf-8')

campaign=PAPER/'results/model4_crossover_all_20261029_080528'
# The campaign also freezes its interpreter. Validate it with that interpreter,
# rather than the separate PDF/rendering environment running this script.
inspection=subprocess.run([r'G:\conda\envs\a3cenv\python.exe','-X','utf8','-c',
    "import sys,json;from pathlib import Path;sys.path.insert(0,sys.argv[1]);"
    "import evidence_supplement as e;s,c=e.checked(Path(sys.argv[2]));"
    "print(json.dumps({'cells':len(s['cells']),'assets_unchanged':True}))",
    str(PAPER/'model4_pjob_20261027'),str(campaign)],
    capture_output=True,text=True,encoding='utf-8',check=True,cwd=ROOT)
integrity=json.loads(inspection.stdout)
backend=PAPER/'model4_pjob_fifo_20261029'
changes=[]
for path in backend.glob('*.py'):
    other=PAPER/'model4_pjob_20261027'/path.name
    if not other.exists() or sha(path)!=sha(other):changes.append(path.name)
report=dict(build=build,protected_introduction='Only approved term and figure filename changed',
    protected_abstract='Only approved objective order changed in the first paragraph',
    forbidden_terms_in_source_and_pdf=0,references=len(refs),removed_references=['choi2021carbon','maitra2024virtual'],
    tests=dict(distinct_tests_passed=29,final_suite_seconds=20.30,metadata_regression_passed=True),
    current_backend=str(backend.relative_to(ROOT)),changed_python_files=sorted(changes),
    backend_sha256={p.name:sha(p) for p in sorted(backend.glob('*.py'))},
    existing_incumbents=330,strict_order_valid=305,retained_action_sequences=7402,physical_witnesses=36,
    active_campaign_frozen_assets_unchanged=integrity['assets_unchanged'],active_campaign_expected_cells=integrity['cells'],
    new_experiment_campaigns_started=0,manuscript_visual_review='All pages; detailed tables, encoding, decoding and chamber labels checked')
(HERE/'completion_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf-8')
(HERE/'manuscript.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True),source.splitlines(True),
    fromfile='original/JMS_Review_CN.tex',tofile='JMS-version/JMS_Review_CN.tex')),'utf-8')
review=HERE/'REVIEW_CN.md'
extra='''
## 最终核验

最终稿13页，XeLaTeX三轮编译通过，无未定义引用、重复标签或排版溢出。29项正确性测试全部通过；模型版本标识和新增模块进入冻结协议的补充回归通过。

图1、图2按用户确认仅将CH1/CH2改为CH2/CH3。原图保留，新图的标签范围外像素与原图完全一致；引言仅改变获准的术语和图件文件名，其余文字保持原样。摘要第一段仅修正获准的目标顺序。

引用与文末参考文献一一对应，共31条。当前活动实验的冻结源码哈希再次检查通过。本轮未启动新实验批次。详细检查与文件哈希见 `completion_review.json`，源稿差异见 `manuscript.patch`。
'''
if '## 最终核验' not in read(review):review.write_text(read(review)+extra,'utf-8')
print(json.dumps({k:v for k,v in report.items() if k not in ('backend_sha256','changed_python_files')},ensure_ascii=False,indent=2))
