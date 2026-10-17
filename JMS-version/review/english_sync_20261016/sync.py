from pathlib import Path
import re,hashlib,json,shutil,difflib
from table_definitions import INPUTS,VARIABLES
from algorithm_notes import NOTES

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
cnpath=PAPER/'JMS_Review_CN.tex'; enpath=PAPER/'JMS_Submission_EN.tex'; mdpath=PAPER/'MODEL_EXPLANATION_CN.md'
for p in [cnpath,enpath,mdpath,PAPER/'JMS_Submission_EN.pdf',PAPER/'output/pdf/MODEL_EXPLANATION_CN.pdf']:
    backup=HERE/(p.stem+'.before'+p.suffix)
    if p.exists() and not backup.exists(): shutil.copy2(p,backup)
cn=cnpath.read_text(encoding='utf-8')
assert cn==(HERE/'JMS_Review_CN.before.tex').read_text(encoding='utf-8'),'Chinese source changed during synchronization'
old=(HERE/'JMS_Submission_EN.before.tex').read_text(encoding='utf-8')
en=old
en=en.replace(r'\graphicspath{{figures/}}',r'\graphicspath{{figures/terminology_en/}{figures/}}')
eqs=re.findall(r'\\begin\{equation\}.*?\\end\{equation\}',cn,re.S)
eqmap={re.search(r'\\label\{([^}]+)\}',e)[1].removesuffix('-cn'):e for e in eqs}
assert len(eqs)==42
model=(HERE/'model_en.template.tex').read_text(encoding='utf-8')
model=re.sub(r'@@(eq:[^@]+)@@',lambda m:eqmap[m[1]].replace(m[1]+'-cn',m[1]+'-en'),model)
tables=re.findall(r'\\begin\{table\*\}.*?\\end\{table\*\}',cn,re.S)[:2]
records=[]
for ti,(table,definitions) in enumerate(zip(tables,[INPUTS,VARIABLES]),1):
    a=table.index('\\midrule\n')+len('\\midrule\n');b=table.index('\\bottomrule')
    rows=table[a:b].strip().splitlines()
    assert len(rows)==len(definitions)
    newrows=[]
    for ri,(row,(kind,definition)) in enumerate(zip(rows,definitions),1):
        symbol,cnkind,cndef=row.removesuffix(r'\\').split(' & ')
        newrows.append(' & '.join([symbol,kind,definition])+r'\\')
        records.append(dict(table=ti,row=ri,symbol=symbol,cn_type=cnkind,cn_definition=cndef,en_type=kind,en_definition=definition))
    newtable=table[:a]+'\n'.join(newrows)+'\n'+table[b:]
    newtable=newtable.replace('核心集合与输入参数','Core sets and input parameters').replace('核心决策与必要的派生、线性化量','Core decisions and necessary derived and linearization quantities')
    newtable=newtable.replace('符号 & 类型 & 定义与作用','Symbol & Type & Definition and role').replace('tab:symbol-cn-','tab:symbol-en-')
    newtable=newtable.replace(r'C{0.23\textwidth}C{0.10\textwidth}C{0.61\textwidth}',r'C{0.21\textwidth}C{0.12\textwidth}C{0.61\textwidth}')
    model=model.replace(f'@@TABLE{ti}@@',newtable)
for token,label,file,caption,width in [
    ('FIGCHAIN','chain','fig_chain_en_nature',r'$2\times2$ chained production. Auxiliary pair D preserves full occupancy at the chain head and tail. Rotation and exchanges make each product pair participate in two adjacent production cycles, giving every product two exposures.','0.93\\linewidth'),
    ('FIGPARALLEL','parallel','fig_parallel_en_nature',r'$4\times1$ parallel production. Two PW pairs are loaded successively around a rotation, filling all four positions for one synchronous exposure. Pairs leave in last-in--first-out order; auxiliary wafers fill product shortages.','\\linewidth'),
]:
    figure='\n'.join([r'\begin{figure}[t]',r'\centering',r'\includegraphics[width='+width+']{'+file+'}',r'\caption{'+caption+'}',r'\label{fig:'+label+'-en}',r'\end{figure}'])
    model=model.replace('@@'+token+'@@',figure)
assert '@@' not in model
a=en.index(r'\section{Problem description');b=en.index(r'\section{Structure-aware MILP',a)
en=en[:a]+model+'\n\n'+en[b:]
# Synchronize every numbered formula, including unchanged algorithm and metric formulas.
def formula(m):
    label=re.search(r'\\label\{([^}]+)\}',m[0])[1]
    base=label.removesuffix('-en')
    return eqmap[base].replace(base+'-cn',base+'-en')
en=re.sub(r'\\begin\{equation\}.*?\\end\{equation\}',formula,en,flags=re.S)
for base,note in NOTES.items():
    pos=en.index(r'\end{equation}',en.index('\\label{'+base+'-en}'))+len(r'\end{equation}')
    en=en[:pos]+'\n\n'+note+'\n'+en[pos:]

def replace(a,b):
    global en
    assert a in en,a[:120]
    en=en.replace(a,b)

replace(r'\ead{m202420836@xs.ustb.edu.cn}'+'\n','')
replace(r'\label{sec:method-new}'+'\n','')
replace('the decoder state $d_r$ and all encoder states', 'the decoder state $d_r$ formed from the selected prefix and all encoder states')
replace('The $k_t$ selected cuts are added to the current LP',r'The final ordered sequence is denoted $S_t^\star$, with $\star$ labeling the output of this round. The $k_t$ selected cuts are added to the current LP')
replace('and Holm correction within each prespecified analysis family.',r'and Holm correction within each prespecified analysis family; $p$ in a statistical test denotes its $p$-value.')
# Keep the user's confirmed deletion, instead of restoring the old English-only table.
en,n=re.subn(r'\\begin\{table\}\[!t\](?:(?!\\end\{table\}).)*?\\label\{tab:joint-search-en\}.*?\\end\{table\}', '',en,flags=re.S)
assert n==1
replace(r'Table~\ref{tab:joint-search-en} gives feasible makespans under common initialization, computed as the actual time of the final product return to its load port.',r'Feasible makespans in the common-initialization comparison are measured by the actual time of the final product return to its original load port.')
# The second reference has different surrounding prose in the earlier English version.
en=en.replace(r'Table~\ref{tab:joint-search-en}', 'the preceding common-initialization comparison under the 300-s total solve budget')
scope=r'''\paragraph{Cleaning-policy revision and scope of evidence.}
The revised model permits optional cleaning before the threshold and requires cleaning when the threshold is reached, with expanded candidate capacities in Eq.~\eqref{eq:candidate-bounds-en}. The existing numerical results, model sizes, and optimality certificates in this section come from the previous cleaning policy or historical fixed layouts and are retained as records for those models. They do not certify optimality over the expanded feasible region. Under the same physical constraints, historical schedules may provide feasible candidates for the revised model but must be revalidated after transfer. Mode rankings, time-limited performance, and optimal values under the revised policy require new solves and validation.'''
replace(r'\section{Computational experiments and results}',r'\section{Computational experiments and results}'+'\n\n'+scope)
replace('Processing segments follow cycle limits and complete-chain boundaries, including 500-s cleaning and associated dummy loading, unloading, rotation, and transport.',r'In this historical fixed-layout experiment, early cleaning after $H-1$ cycles was allowed only to reserve capacity for the following complete $2\times2$ chain. That layout generator forms production segments using cycle limits and complete-chain boundaries, including 500-s cleaning and associated auxiliary loading, unloading, rotation, and transport.')
replace('The cleaning interval $H$ counts full-occupancy cycles per chamber:', 'The cleaning threshold $H$ counts full-occupancy production cycles per chamber:')
# Remove an English-only alias for auxiliary wafers that is absent from the Chinese source.
en=en.replace('process-enabling carriers (PECs)','auxiliary wafers').replace('new PEC-bounded head','new auxiliary-bounded head')
en=en.replace('dual-source material flow','dual-source wafer flow').replace('Material origins','Wafer origins')
en=en.replace('material routes','wafer routes').replace('material route','wafer route').replace('material location','wafer location')
en=en.replace('These material and resource constraints','These wafer and resource constraints')
en=en.replace('complete material routes','complete wafer routes')
# Uniform auxiliary-wafer terminology while retaining stable LaTeX labels and asset names.
protected=[]
def protect(m):
    protected.append(m[0]);return f'PROTECTEDTOKEN{len(protected)-1}ENDTOKEN'
en=re.sub(r'\\(?:label|eqref|ref|includegraphics|citep|citet)(?:\[[^\]]*\])?\{[^}]*\}',protect,en)
en=re.sub(r'\bDummies\b','Auxiliary wafers',en)
en=re.sub(r'\bdummies\b','auxiliary wafers',en)
en=re.sub(r'\bDummy\b','Auxiliary',en)
en=re.sub(r'\bdummy\b','auxiliary',en)
en=en.replace('auxiliary (auxiliary) wafers','auxiliary wafers')
en=re.sub(r'PROTECTEDTOKEN(\d+)ENDTOKEN',lambda m:protected[int(m[1])],en)
en=en.replace('cleaning intervals','cleaning thresholds').replace('cleaning interval','cleaning threshold')
en=en.replace('concurrent chamber processing','concurrent chamber production')
en=en.replace('other material actions','other wafer-handling actions').replace('restricted by material, capacity, and timing constraints','restricted by wafer, capacity, and timing constraints')
en=en.replace(r'\textquotesingle s',"'s")
# Current Chinese statistical notation states that R-squared is the coefficient of determination.
en=re.sub(r'(The prespecified PDI factorial model[^\n]*?)\$R\^2=0\.998\$',lambda m:m[1]+r'coefficient of determination $R^2=0.998$',en) if 'The prespecified PDI factorial model' in en else en
# Translate the configuration table in the same order as the authoritative Chinese rows.
pos=en.index(r'\label{tab:gantt-config-en}');a=en.index(r'\midrule',pos)+len(r'\midrule');b=en.index(r'\bottomrule',a)
en=en[:a]+r'''
Rotating chambers & CH1 and CH2 share VTR; 4 wafer positions per chamber & Recipe duration & $4\times1$: 180~s; $2\times2$: 90+90~s\\
Cleaning & At most $H=3$--10 production cycles between cleanings; auxiliary-only cleaning lasts 500~s & Chamber actions & 180$^\circ$ rotation: 2~s; gap between adjacent chamber actions: 1~s\\
ATR & 1 two-hand robot, capacity 2; load/unload 4~s; complete loaded transfer 11~s & VTR & 1 four-hand robot, capacity 4; loaded transfer 4~s; empty repositioning 4~s\\
ATR details & LL--LP empty return 6~s; PW-pair exchange at AL 8~s & AL & Capacity 1; minimum alignment occupancy 20~s per wafer\\
Load locks & Upper-slot pumping/reset 30~s; lower-slot venting/reset 25~s & LL capacity & Upper and lower load locks each contain 2 independent slots\\
Wafer sources & LP1--LP4, each holding 25 wafers & Auxiliary wafers & 8 reusable wafers, 4 per chamber; storage capacity 10 wafers\\
Batch and model & Basic product batch size 4; 13 route steps & Chamber bound & At most 15 $4\times1$ batch slots per PM\\
Model bounds & Big-$M=10000$; module and robot residency bounds 10000~s & Waiting option & Avoidable-wait hard cap 0 disables this optional restriction\\
Objective & Product-return makespan and waiting refinement & Policy & Training seed 1, epoch 60, 23-dimensional features\\
Decoder and cuts & Beam width 3; candidate pool 128; at most 16 cuts per round & Solver & SCIP seed 1; available, validated initial schedules\\
Solve and chart selection & Product-return objective; makespan bounds for mode comparison; waiting-refined schedules for Gantt charts & Schedule validation & Original-model and independent validation of every schedule\\
'''+en[b:]
assert not re.search(r'[\u4e00-\u9fff]',en),'Untranslated Chinese remains in English source'
assert 'tab:joint-search-en' not in en
enpath.write_text(en,encoding='utf-8',newline='\n')

# Refresh the existing Chinese explanation rather than inventing a separate English companion.
md=(HERE/'MODEL_EXPLANATION_CN.before.md').read_text(encoding='utf-8')
def sync_explanation(m):
    base=m[1].removesuffix('-cn')
    body=eqmap[base][len(r'\begin{equation}'):-len(r'\end{equation}')]
    body=re.sub(r'\\label\{[^}]+\}','',body).strip()
    number=list(eqmap).index(base)+1
    return '<!-- '+m[1]+' -->\n$$\n'+body+f'\n\\tag{{{number}}}\n$$'
md=re.sub(r'<!-- (eq:[^ ]+) -->\s*\$\$(.*?)\$\$',sync_explanation,md,flags=re.S)
for rec in records:
    pattern=rf'(\*\*表{rec["table"]}-{rec["row"]:02d}[^\n]*\*\*\n\n\*\*类型与定义。\*\* )[^\n]+'
    md,count=re.subn(pattern,lambda m:m[1]+rec['cn_type']+'；'+rec['cn_definition'],md)
    assert count==1,(rec['table'],rec['row'])
md=md.replace('更新日期：2026-10-15。','更新日期：2026-10-16。')
md=md.replace('不推定英文稿或其他副本已同步。','英文投稿正文已同步为相同的42式与43行符号表；本说明按中文正文讲解，中英文公式编号一一对应。')
cnsha=hashlib.sha256(cnpath.read_bytes()).hexdigest();ensha=hashlib.sha256(enpath.read_bytes()).hexdigest()
md=re.sub(r'(SHA-256前16位为 `)[^`]+`',lambda m:m[1]+cnsha[:16]+'`',md)
md=md.replace('本轮未重跑这些实验，仅对新清洁规则运行小型回归测试。','本轮仅同步英文稿与实例说明，未重跑实验或回归测试；2026-10-15清洁规则修订的测试记录另见对应修改日志。')
md=md.replace('本轮修改联合模型的清洁触发约束、候选容量与独立验解器，同步修改式（5）、式（19）及其说明；保留42个公式编号和历史实验结果。','2026-10-15的修订已修改联合模型清洁约束、候选容量与独立验解器。本轮以当前中文稿为准同步英文及本说明，保留42个公式编号和历史实验结果，不改动模型代码。')
version='\n\n**中英文对应。** 英文正文为 [JMS_Submission_EN.tex](JMS_Submission_EN.tex)，SHA-256前16位 `'+ensha[:16]+'`。中文与英文的42个编号公式及43行符号逐项对应；英文已采用相同六段模型组织，并保留共同初始解对照表的删除。\n'
md+=version
mdpath.write_text(md,encoding='utf-8',newline='\n')
mapping={'manuscript_sha256':cnsha,'english_sha256':ensha,'equations':{k+'-cn':i+1 for i,k in enumerate(eqmap)},'symbol_rows':[24,19]}
(HERE/'equation_mapping.json').write_text(json.dumps(mapping,indent=2),encoding='utf-8')
(HERE/'symbol_mapping.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
(HERE/'english.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),en.splitlines(True),fromfile='English before',tofile='English synchronized')),encoding='utf-8')
print(json.dumps({'equations':42,'symbol_rows':[24,19],'chinese_sha256':cnsha,'english_sha256':ensha}))
