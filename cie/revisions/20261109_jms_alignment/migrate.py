"""One-off CIE Chinese review migration from the dated JMS source; no experiments."""
from pathlib import Path
import re, json, shutil, hashlib, zipfile

ROOT = Path(__file__).resolve().parents[3]
REV = Path(__file__).resolve().parent
P = ROOT/'cie/products'
J = ROOT/'JMS-version'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
source = (J/'JMS_Review_CN.tex').read_text('utf-8')
source_hash = sha(J/'JMS_Review_CN.tex')
assert source_hash == '78dc0942483834dbb31482e33c581f4fd344d717b7939803c72aedc0d11fc715', 'Review changed JMS source before migration'
shutil.copy2(J/'JMS_Review_CN.tex', REV/'authoritative_JMS_Review_CN.tex')
intro = source[source.index(r'\section{引言}'):source.index(r'\section{旋转腔组合设备调度模型}')]
model = source[source.index(r'\section{旋转腔组合设备调度模型}'):source.index(r'\section{结构化初始化')]
body = source[source.index(r'\section{引言}'):source.index(r'\section*{CRediT')]
# Preserve all scientific content, while grouping historical diagnostics as appendices.
appendices = []
for title, next_title in [
    ('批次表示与逐片表示的对照','默认配置下的编码补充对照'),
    ('固定结构与联合搜索的预算对照','100~s默认配置的最新结果'),
    ('历史选割评估与规模限制','同步取片与最优性验证')]:
    begin = body.index('\\subsection{'+title+'}')
    end = body.index('\\subsection{'+next_title+'}')
    part = body[begin:end]
    # Keep the D Gantt figure in the main text.
    if title == '历史选割评估与规模限制':
        fig = part.index(r'\begin{figure*}')
        # The first wide table is not a figure; this is the final Gantt figure.
        gantt = part[fig:]
        part = part[:fig]
        body = body[:begin]+gantt+body[end:]
    else:
        body = body[:begin]+body[end:]
    appendices.append(part.replace(r'\subsection{',r'\section{'))

body = body.replace('第5节给出结论。','第5节讨论工业工程意义与适用边界，第6节给出结论；附录保留历史参数配置与完整负结果。')
discussion = r'''
\section{工业工程意义与适用边界}
本文的决策对象是满片条件下产品、辅助晶圆与共享设备资源的联合组织。PW对将成对搬运与周期占位连接，Pjob库存表示在同质条件下消除部分产品身份指派，并通过确定解码恢复具体执行动作。其价值在于能够检查一种生产组织方案是否同时满足库存、处理链和资源时序约束，而不是仅给出抽象工件顺序。

对求解流程，结构化初始化提供可行上界，学习选割调整求解器的搜索过程，固定结构精修改善已有排程的时序。这三种作用应分别评价。现有D数据支持部分实例上的起点改善，但学习排序随分离协议改变，尚不能把组合流程的全部收益归因于学习策略。对实际设备，产品交付与全部设备占用结束还应分别报告；产品完工提前可能伴随复位或辅助片占用延后。

目前不能据四个已有可行输入的小实例决定实际产线的模式选择、辅助片最佳数量或全规模部署。现有1片产品见证已经验证清洁、连续处理和辅助复用同时成立，但不证明库存瓶颈；含构造失败的统一墙钟比较、多产品竞争、长连续链与清洁和库存的配对敏感性，仍是检验工业适用性的必要证据。历史配置E仅用于解释机制，旧固定配对CIE模型的实验也不代表当前PW联合模型的性能。

'''
body = body.replace(r'\section{结论}',discussion+r'\section{结论}')
abstract = source.split(r'\begin{abstract}',1)[1].split(r'\end{abstract}',1)[0]
prefix = source[:source.index(r'\begin{document}')]
prefix = prefix.replace(r'\documentclass[final,5p,times,twocolumn]{elsarticle}',r'\documentclass[preprint,12pt,nonatbib]{elsarticle}')
prefix = re.sub(r'\\graphicspath\{.*\}\n',r'\\graphicspath{{./}}\n',prefix)
prefix = prefix.replace(r'\usepackage{dblfloatfix}',r'\usepackage{lineno}')
prefix = prefix.replace(r'\setcounter{dblbotnumber}{1}','')
prefix += '\n'+r'\usepackage[margin=22mm]{geometry}'+'\n'+r'\newsavebox{\CIEtablebox}'+'\n'
prefix = prefix.replace(r'\biboptions{numbers,sort&compress}',r'\usepackage[backend=biber,style=apa,natbib=true,doi=true,url=true]{biblatex}'+'\n'+r'\addbibresource{rdmct_cie_current_references.bib}')
prefix = prefix.replace(r'\journal{Journal of Manufacturing Systems}',r'\journal{Computers \& Industrial Engineering}')
prefix = prefix.replace('JMS_Review_CN','CIE_Review_CN')
prefix += '\n'+r'\hypersetup{pdfauthor={},pdftitle={PW-pair scheduling: Chinese review manuscript},pdfsubject={Anonymous working manuscript}}'+'\n'
front = r'''
\begin{document}
\raggedbottom
\begin{frontmatter}
\title{基于PW对的双源混流旋转腔组合设备两阶段调度与结构化求解}
\begin{abstract}
'''+abstract+r'''
\end{abstract}
\begin{keyword}
Semiconductor manufacturing \sep Cluster tool scheduling \sep Wafer pairing \sep Mixed-integer linear programming \sep Structured initialization \sep Cut selection
\end{keyword}
\end{frontmatter}
\modulolinenumbers[5]
\linenumbers
'''
declarations = r'''
\section*{数据与研究材料可用性}
研究实例、完整赋值、事件重放记录、冻结配置、策略出处及文件哈希已在项目内保存。可公开范围、匿名评审访问方式和永久归档标识符尚待作者确认；当前稿不声称数据已公开。不同模型与资源协议分别归档，原始失败和无可行解记录保留。

\section*{声明与作者信息处理}
本文件为匿名中文审阅工作稿。逐作者贡献、基金、利益冲突和最终投稿批准信息在单独标题页及提交清单中核对，不在匿名正文中列出可识别信息。完成中文审阅、英文全文同步和作者确认后，方可形成正式英文投稿稿。

\section*{生成式AI和AI辅助技术使用说明}
本稿修订使用OpenAI ChatGPT和Codex辅助文稿组织、语言编辑、LaTeX与引用一致性检查、实验命令实现及结果边界核对。论文图形沿用确定性绘图结果，未使用生成式图像工具。最终提交版本的人工审阅、事实确认和责任声明须由作者完成。
\FloatBarrier
\appendix
'''
text = prefix+front+body+declarations+'\n'.join(appendices)+r'''
\FloatBarrier
\printbibliography[title={参考文献}]
\end{document}
'''
# One-column review layout: preserve mathematical content, avoid narrow-column enlargement.
text = text.replace(r'\begin{table*}',r'\begin{table}').replace(r'\end{table*}',r'\end{table}')
text = text.replace(r'\begin{figure*}',r'\begin{figure}').replace(r'\end{figure*}',r'\end{figure}')
(P/'rdmct_cie_analysis_focused_zh.tex').write_text(text,encoding='utf-8')

# Generate an APA-compatible bibliography from the preserved JMS metadata, not old CIE keys.
metadata = json.loads((J/'JMS_references.json').read_text('utf-8'))
keys = sorted(set(k.strip() for m in re.finditer(r'\\cite\w*\{([^}]+)\}',text) for k in m.group(1).split(',')))
entries = []
for key in keys:
    d = metadata[key]
    typ = {'conference':'inproceedings','webpage':'online','preprint':'misc'}.get(d['type'],'article')
    authors = d['author']
    author = ' and '.join(('{'+a+'}') if d.get('corporate') else a for a in authors)
    fields = {'author':author,'title':d['title']}
    for f in ('year','journal','booktitle','volume','number','pages','publisher','doi','url'):
        if d.get(f) and not (f=='year' and d[f]=='n.d.'): fields[f]=d[f]
    if d.get('accessed')=='September 7, 2026': fields['urldate']='2026-09-07'
    entries.append('@'+typ+'{'+key+',\n'+',\n'.join('  '+f+' = {'+str(v)+'}' for f,v in fields.items())+'\n}\n')
(P/'rdmct_cie_current_references.bib').write_text('\n'.join(entries),encoding='utf-8')
figures = []
dirs = ['current_defaults_20261103','final_results_cn','pjob_sequence_cn','terminology_cn','']
for name in re.findall(r'\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}',text):
    matches = [J/'figures'/d/(name+ext) for d in dirs for ext in ('.pdf','.png','.jpg') if (J/'figures'/d/(name+ext)).exists()]
    if not matches: raise FileNotFoundError(name)
    original=matches[0];target=P/original.name;shutil.copy2(original,target)
    figures.append(dict(source=str(original.relative_to(ROOT)),file=target.name,sha256=sha(target)))

eng_title='PW-pair-based two-stage MILP scheduling and structured solution methods for dual-source mixed-flow rotating-chamber cluster tools'
eng_abstract='''Dual-source mixed-flow rotating-chamber cluster tools require full occupancy during processing and cleaning, with reusable auxiliary wafers filling otherwise vacant positions. We formulate a two-stage mixed-integer linear program using two-wafer pairs to connect handling operations and chamber cycles, and batch inventory variables to recover individual wafer identities. The formulation jointly determines pairing, chamber assignment, cleaning, auxiliary-wafer reuse, and resource sequences. The first stage minimizes product-return makespan; the second retains its upper bound and principal discrete structure while refining waiting and cadence. A structured initialization procedure is combined with five-level binary-skeleton improvement and feature and inference extensions to hierarchical learning-based cut selection. Under the default 100-s nonprocessing residence and robot holding limits, four of eight small instances have certified primary optima and one yields a feasible time-limited schedule. In 180 conditional algorithm runs, initialization reduces the two-wafer mixed-instance makespan from 518 to 505 s and the four-wafer mixed-instance makespan from 542 to 541 s under root separation. Learned-cut rankings change with the instance and separation protocol. Another 36 structural comparisons support exploiting existing schedules before joint search, whereas 12 completion-tail comparisons yield no improvement. Historical extended-window experiments support conditional timing refinement but are reported separately. The evidence supports verifiable wafer decoding and conditional initialization benefits; it does not establish consistent cut-selection superiority, large-scale scalability, or end-to-end acceleration.'''
highlights=[
'Wafer pairs connect handling and chamber cycles in a joint scheduling MILP.',
'Batch inventory variables support deterministic decoding of wafer identities.',
'Structured initialization improves selected feasible schedules under time limits.',
'Cut-selection rankings depend on the instance and separation protocol.',
'Product-return makespan and final equipment occupancy are evaluated separately.']
assert len(eng_abstract.split())<=250 and all(len(x)<=85 for x in highlights)
(P/'highlights_analysis_focused.txt').write_text('\n'.join(highlights)+'\n',encoding='utf-8')
(P/'abstract_current_en.txt').write_text(eng_title+'\n\n'+eng_abstract+'\n',encoding='utf-8')
title = (REV/'before/title_page.tex').read_text('utf-8')
title = re.sub(r'\{\\Large\\bfseries .*?\\par\}',lambda _:r'{\Large\bfseries '+eng_title+r'\par}',title,flags=re.S)
title = title.replace(r'Lizhen Shao$^{1,*}$ and Lincong Wei$^{1}$',r'Lizhen Shao$^{1,*}$, Lincong Wei$^{1}$, and Wei Wang$^{1}$')
title = title.replace(r'\subsection*{Declaration of competing interest}',r'\subsection*{Author verification required}'+'\nAuthor list follows the current JMS Chinese manuscript. Author order, affiliations, email addresses, contributions, funding, competing interests, and final submission consent require author verification. Wei Wang\'s email has not been supplied.\n\n'+r'\subsection*{Declaration of competing interest (draft)}')
(P/'title_page.tex').write_text(title,encoding='utf-8')
cover=r'''\documentclass[11pt]{article}
\usepackage[margin=1in]{geometry}
\begin{document}
\noindent\textbf{Cover letter working draft --- author approval required}\par
\bigskip
Dear Editor,\par
We are preparing the manuscript ``'''+eng_title+r'''" for consideration by \textit{Computers \& Industrial Engineering}.
The study develops a wafer-pair and batch-inventory representation of a full-occupancy scheduling problem with shared handling resources and reusable auxiliary wafers. It evaluates structured primal initialization and frozen learning-based cut-selection extensions using explicit model and comparison-budget boundaries.
The current evidence shows conditional initialization benefits and verifiable execution schedules. It does not establish universal superiority of learned cuts. Historical models are reported separately from the current joint formulation.
The work addresses computerized decision methods for industrial engineering. Before submission, the authors must complete the English manuscript, end-to-end and coupled-constraint validation, data-access arrangements, and author declarations. This draft does not certify originality, exclusive submission, or approval by all authors.\par
\bigskip
Corresponding author details are maintained on the separate title page.
\end{document}
'''
(P/'cover_letter_draft.tex').write_text(cover,encoding='utf-8')
manifest=dict(jms_source_sha256=source_hash, chinese_primary='rdmct_cie_analysis_focused_zh.tex',
    preserved_intro_except_roadmap=True,preserved_model_sha256=hashlib.sha256(model.encode()).hexdigest(),
    bibliography_keys=keys,figures=figures,english_abstract_words=len(eng_abstract.split()),
    highlight_lengths=[len(x) for x in highlights],
    official_template_sha256=sha(REV/'official/elsarticle.zip'),
    full_english_status='Historical model; not synchronized and not eligible for current-model submission',
    solver_started=False)
normalized_model = model.replace(r'\begin{table*}',r'\begin{table}').replace(r'\end{table*}',r'\end{table}').replace(r'\begin{figure*}',r'\begin{figure}').replace(r'\end{figure*}',r'\end{figure}')
assert normalized_model in text, 'Model scientific content changed'
text = text.replace(r'p{0.14\textwidth}p{\dimexpr0.86\textwidth-8pt\relax}',r'p{0.24\textwidth}p{\dimexpr0.76\textwidth-8pt\relax}')
text = text.replace(r'p{0.11\textwidth}p{0.14\textwidth}p{0.71\textwidth}',r'p{0.24\textwidth}p{0.16\textwidth}p{0.56\textwidth}')
text = text.replace(r'\begin{tabular}',r'\begin{lrbox}{\CIEtablebox}\begin{tabular}')
text = text.replace(r'\end{tabular}',r'\end{tabular}\end{lrbox}\ifdim\wd\CIEtablebox>\linewidth\resizebox{\linewidth}{!}{\usebox{\CIEtablebox}}\else\usebox{\CIEtablebox}\fi')
text = text.replace(r'\includegraphics[width=0.93\linewidth]{fig_chain_cn_nature}',r'\includegraphics[width=0.65\linewidth]{fig_chain_cn_nature}')
text = text.replace(r'\includegraphics[width=\linewidth]{fig_parallel_cn_nature}',r'\includegraphics[width=0.70\linewidth]{fig_parallel_cn_nature}')
(P/'rdmct_cie_analysis_focused_zh.tex').write_text(text,encoding='utf-8')
(REV/'migration_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(manifest,ensure_ascii=False,indent=2))
