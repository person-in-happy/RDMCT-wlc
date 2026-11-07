"""Create independent IEEE manuscripts from the frozen JMS sources; never edit inputs."""
from pathlib import Path
import re, shutil, hashlib, json, csv, subprocess

PAPER = Path(__file__).resolve().parents[1]
ROOT = PAPER.parent
SOURCE = ROOT / 'JMS-version'

def braced(s, start):
    assert s[start] == '{'
    depth = 1
    for j in range(start + 1, len(s)):
        if s[j] == '{': depth += 1
        elif s[j] == '}': depth -= 1
        if depth == 0: return s[start+1:j], j+1
    raise ValueError('Unbalanced braces')

def bibliography(source):
    entries = []
    parts = re.split(r'\\bibitem\[.*?\]\{([^}]+)\}', source, flags=re.S)
    for key, block in zip(parts[1::2], parts[2::2]):
        fields = {}
        for m in re.finditer(r'\\bibinfo\{([^}]+)\}', block):
            value, _ = braced(block, m.end())
            fields.setdefault(m[1], []).append(re.sub(r'\s+', ' ', value))
        if not fields:
            if key == 'appliedprecisioncvd':
                fields = {'author':['{Applied Materials}'], 'title':['Producer XP Precision CVD'], 'url':['https://www.appliedmaterials.com/us/en/product-library/producer-xp-precision-cvd.html'], 'note':['Accessed: Sep. 7, 2026']}
            elif key == 'wang2024hemset':
                fields = {'author':['Wang, J.','Wang, Z.','Li, X.','Kuang, Y.','Shi, Z.','Zhu, F.','Yuan, M.','Zeng, J.','Zhang, Y.','Wu, F.'], 'title':['Learning to Cut via Hierarchical Sequence/Set Model for Efficient Mixed-Integer Programming'], 'year':['2024'], 'journal':['arXiv preprint arXiv:2404.12638'], 'url':['https://arxiv.org/abs/2404.12638']}
            else: raise ValueError(key)
        doi = re.search(r'\\doi\{([^}]+)\}', block)
        if doi: fields['doi'] = [doi[1]]
        url = re.search(r'\\url\{([^}]+)\}', block)
        if url and not doi: fields['url'] = [url[1]]
        typ = 'article' if 'journal' in fields else 'inproceedings' if 'booktitle' in fields else 'misc'
        items = []
        for field, values in fields.items():
            value = ' and '.join(values) if field == 'author' else values[0]
            items.append(f'  {field} = {{{value}}}')
        entries.append('@'+typ+'{'+key+',\n'+',\n'.join(items)+'\n}')
    return '\n\n'.join(entries)+'\n'

ABSTRACT = r'''Finite-batch scheduling of rotating-chamber cluster tools requires coordination of product supply, reusable dummy wafers, and periodic cleaning. This paper develops a mixed-integer linear programming model for dual-source mixed flows under full-occupancy, residency, and shared-resource constraints. A makespan-first second stage refines waiting and processing cadence within the first-stage bound. Structure-preserving initial schedules and role-aware hierarchical cut selection support time-limited solution. Computational mode comparisons use prescribed wafer-pair layouts and equal cumulative nominal processing times. The preferred mode changes with lot size and cleaning-induced chain segmentation; for 16 wafers without activated cleaning, chained processing reduces product-return makespan by 4.87\% relative to parallel processing. On the frozen algorithm benchmark, equal-budget two-stage optimization reduces total route wait by 51.91\%, while precomputed initial schedules increase incumbent availability from 51.67\% to 100\% during the subsequent solve. The learned cut selector and its hierarchical baseline have similar observed performance without a statistically established difference. These results support conditional process-mode comparison and coordinated event scheduling; physical recipe equivalence and production deployment are not established by the computational experiments.'''
NTP = '''Engineers operating semiconductor cluster tools must coordinate production wafers with reusable dummy wafers that occupy otherwise empty positions and support chamber cleaning. A faster chamber cycle does not necessarily finish a finite lot sooner: dummy returns, robot access, and the point at which cleaning interrupts a processing chain can change the preferred operating mode. The proposed scheduler takes qualified recipes, equipment capacities, action durations, a wafer-pair layout, and available dummy inventory as inputs. It returns timed handling, processing, and cleaning actions, and can refine waiting after obtaining a feasible completion-time bound. Its intended use is offline evaluation of operating alternatives and preparation of candidate schedules. Application requires checking the input timings and occupancy rules against the actual tool and validating the resulting actions with the equipment control system. The reported tests use deterministic computational instances; they do not demonstrate film-quality equivalence, disturbance recovery, or production-line deployment. Initial-schedule construction also consumes time outside the reported main-solver budget. Users with a strict decision deadline should include this preparation cost and retain a validated fallback schedule.'''
CN_ABSTRACT = r'''旋转腔组合设备的有限批次调度需要协调产品供给、可复用辅助晶圆和周期清洁。本文针对双源混流建立混合整数线性规划模型，联合描述满片占用、驻留及共享资源约束，并在第一阶段完工时间上界内精修等待和加工节拍。结构保持初始排程与角色感知层次割选择用于支持限时求解。模式比较采用预设晶圆配对布局与相同累计名义加工时长。计算结果表明，优选模式随批量和清洁引起的链分段变化；16片且未激活清洁时，链式加工的产品回片完工时间较并行加工降低4.87\%。冻结算法基准中，同总预算两阶段工作流将路线总等待降低51.91\%；预计算初始排程使后续求解的可行解获得率从51.67\%提高至100\%。学习选割与层次基线的观测性能接近，差异未得到统计显著性支持。结果支持给定工艺条件下的模式比较和协调排程，不构成配方等效性或实际产线部署的验证。'''
CN_NTP = '''半导体组合设备运行人员需要同时安排产品晶圆和可复用辅助晶圆，后者用于空工位补位及腔室清洁。单个加工周期更短，不一定使有限批次更早完成，因为辅助晶圆回流、机械手可用性和清洁切断加工链的位置都会影响模式选择。所提调度器以已合格配方、设备容量、动作时长、晶圆配对布局和辅助晶圆库存为输入，给出搬运、加工、清洁的时间安排，并在获得可行完工时间上界后改善等待。预期用途是离线比较运行方案和准备候选排程。应用前需要根据真实设备核对时间及占位规则，并通过设备控制系统验证动作。本文采用确定性计算实例，尚未验证薄膜质量等效性、扰动恢复或实际产线部署。初始排程构造还消耗主求解预算之外的时间；有严格决策截止时间时，应计入该准备成本并保留经验证的回退排程。'''

def main():
    (PAPER/'figures').mkdir(parents=True, exist_ok=True)
    (PAPER/'evidence').mkdir(exist_ok=True)
    inputs = {}
    for lang, name in [('EN','JMS_Submission_EN'),('CN','JMS_Review_CN')]:
        original = (SOURCE/(name+'.tex')).read_text('utf-8')
        inputs[name+'.tex'] = hashlib.sha256((SOURCE/(name+'.tex')).read_bytes()).hexdigest()
        s = original
        s = re.sub(r'\\documentclass\[[^\]]+\]\{elsarticle\}', r'\\documentclass[journal]{IEEEtran}', s)
        s = s.replace('\\journal{Journal of Manufacturing Systems}', '').replace('\\biboptions{sort&compress}', '\\usepackage{cite}')
        s = re.sub(r'\\begin\{frontmatter\}.*?\\begin\{abstract\}', lambda m: '\\title{'+('Coordinated Scheduling and Process-Mode Selection for Dual-Source Rotating-Chamber Cluster Tools' if lang=='EN' else '双源旋转腔组合设备的协调调度与工艺模式选择')+'}\n\\author{}\n\\maketitle\n\\begin{abstract}', s, count=1, flags=re.S)
        abstract, ntp = (ABSTRACT,NTP) if lang=='EN' else (CN_ABSTRACT,CN_NTP)
        s = re.sub(r'\\begin\{abstract\}.*?\\end\{abstract\}', lambda m: '\\begin{abstract}\n'+abstract+'\n\\end{abstract}\n\n{\\small\\noindent\\textit{Note to Practitioners}---'+ntp+'\\par}\n', s, count=1, flags=re.S)
        s = s.replace('\\begin{keyword}','\\begin{IEEEkeywords}').replace('\\end{keyword}','\\end{IEEEkeywords}').replace('\\sep',',').replace('\\end{frontmatter}','').replace('\\citep{','\\cite{')
        s = s.replace('JMSCiteBlue','TASECiteBlue').replace('JMS_Review_CN','TASE_Review_CN')
        s = s.replace('\\usepackage{microtype}','\\usepackage[expansion=false]{microtype}')
        s = s.replace('\\usepackage{graphicx}','\\usepackage{graphicx}\n\\usepackage{newtxtext,newtxmath}')
        s = s.replace('\\setcounter{equation}{0}','')
        s = s.replace('\\setcounter{dbltopnumber}{1}','\\setcounter{dbltopnumber}{2}')
        s = s.replace('\\renewcommand{\\dbltopfraction}{0.72}','\\renewcommand{\\dbltopfraction}{0.90}')
        s = re.sub(r'\\FloatBarrier\s*','',s)
        s = s.replace('\\scriptsize','\\footnotesize')
        if lang == 'EN':
            s=s.replace('Section~2 defines material routes, process constraints, and the two-stage model. Section~3 presents initialization and cut selection. Section~4 analyzes mode choice, schedule quality, and computational performance. Section~5 concludes.', 'Sections~II--V present the scheduling model, solution framework, computational evaluation, and conclusions, respectively.')
            s=s.replace('Advanced semiconductor', 'Advanced semiconductor')
            s=s.replace('OpenAI Codex assisted with the development and debugging of numerical solution methods and experimental visualization. Numerical results come from solver experiments, and event plots depict validated schedules. ', '')
            s=s.replace('Its contributions are:', 'The automation contribution is the coordination of reusable occupancy resources with finite-batch product flow, with explicit limits on what timing refinement and learned search can guarantee. Its contributions are:')
            s=s.replace('These results quantify schedule availability, timing quality, and bound convergence separately.', 'These results quantify schedule availability, timing quality, and bound convergence separately. The parameter-perturbation study reoptimizes deterministic instances and does not test execution under random disturbances. A feasible returned schedule satisfies the modeled constraints; this does not prove closed-loop stability, recovery from breakdowns, or a hard online response-time guarantee.')
            # Include the full published-method / ablation comparison already available in frozen results.
            rows=list(csv.DictReader((ROOT/'cie/results/main/cie_main_600s_mem2048_repro_v1/submission_analysis/cie_submission_method_summary.csv').open(encoding='utf-8-sig')))
            labels={'scip_default':'SCIP default','adaptive_cutsel':'Adaptive cut scoring','hem':'HEM-13D','rdmct_feature_only':'23D features only','hem_beam':'HEM + beam','hem_structure':'Structure + greedy','proposed':r'\method{}'}
            by={r['method']:r for r in rows}
            table=r'''\begin{table*}[t]
\centering\footnotesize
\caption{Complete frozen 2700-run comparison with common initial schedules and 600-s solver budgets. Values are means over 20 instance aggregates. Gap uses SCIP's terminal definition.}
\label{tab:all-methods}
\begin{tabular}{lrrrrr}\toprule
Method & Runs & PDI & Solve time (s) & Gap (\%) & Optimal (\%)\\\midrule
'''
            for method in labels:
                r=by[method]
                table+=f"{labels[method]} & {r['raw_runs']} & {float(r['primal_dual_integral']):.2f} & {float(r['solving_time']):.2f} & {100*float(r['gap']):.2f} & {100*float(r['optimal_rate']):.1f} "+r'\\'+'\n'
            table+=r'\bottomrule\end{tabular}\end{table*}'
            s=s.replace('The comparison jointly evaluates role-aware representation', 'Table~\\ref{tab:all-methods} adds default SCIP, validation-tuned adaptive cut scoring, and component ablations from the same frozen experiment. Nonlearning methods use five solver seeds per instance (100 runs each); each learned method additionally uses five training seeds (500 runs each). Default SCIP has the highest observed optimal rate and lowest mean terminal gap, while the complete method has the lowest observed PDI and solve time. There is no consistent dominance across metrics.\n\n'+table+'\n\nThe comparison jointly evaluates role-aware representation')
            start=s.index('\\section*{CRediT')
        else:
            start=s.index('\\section*{CRediT') if '\\section*{CRediT' in s else s.index('\\section*{作者')
        s=s[:start]
        ack = ('OpenAI ChatGPT and Codex assisted with language revision and Chinese--English translation throughout the manuscript, the restructuring of the Abstract, Note to Practitioners, Introduction and Discussion, LaTeX preparation, and development/debugging of the numerical solution and visualization code described in Sections~III--IV. Reported numerical results are retained from solver experiments; no new experimental outcomes were generated for this manuscript conversion.' if lang=='EN' else 'OpenAI ChatGPT与Codex用于全文语言修订和中英翻译、摘要及面向实践者说明等段落重组、LaTeX整理，并辅助第III--IV节数值求解与可视化代码的开发调试。报告数值来自已有求解实验，本次转投改稿未生成新的实验结果。')
        s+='\\section*{'+('Acknowledgment' if lang=='EN' else 'AI使用说明')+'}\n'+ack+'\n\n\\bibliographystyle{IEEEtran}\n\\bibliography{references}\n\\end{document}\n'
        s=s.replace('\\usepackage[colorlinks=true', '\\hypersetupPLACEHOLDER\n\\usepackage[colorlinks=true') if False else s
        s=s.replace('\\graphicspath{{figures/}}','\\hypersetup{pdfauthor={},pdftitle={Coordinated Scheduling and Process-Mode Selection},pdfsubject={},pdfkeywords={}}\n\\graphicspath{{figures/}}')
        for figure in re.findall(r'\\includegraphics\[[^\]]*\]\{([^}]+)\}',s):
            source=SOURCE/'figures'/(figure+'.pdf')
            if not source.is_file(): raise FileNotFoundError(source)
            shutil.copy2(source,PAPER/'figures'/source.name)
        (PAPER/('TASE_Submission_EN.tex' if lang=='EN' else 'TASE_Review_CN.tex')).write_text(s,encoding='utf-8')
    (PAPER/'references.bib').write_text(bibliography((SOURCE/'JMS_Submission_EN.tex').read_text('utf-8')),encoding='utf-8')
    (PAPER/'evidence/source_hashes.json').write_text(json.dumps(inputs,indent=2),encoding='utf-8')
    for name in ['IEEEtran.cls','IEEEtran.bst']:
        located=subprocess.check_output(['kpsewhich',name],text=True).strip()
        shutil.copy2(located,PAPER/name)
    print('Created independent English and Chinese IEEE sources; original sources unchanged.')

if __name__=='__main__': main()
