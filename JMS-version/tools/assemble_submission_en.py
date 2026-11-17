"""Assemble the English manuscript, retaining the current Chinese mathematics and data."""
from pathlib import Path
import re
import hashlib
import json

PAPER = Path(__file__).resolve().parents[1]
CN = PAPER / 'JMS_Review_CN.tex'
BODY = PAPER / 'submission/manuscript_body_en.tex'

INPUT_ROWS = ['Batch jobs $\\mathcal J=\\{1,\\ldots,J\\}$ and products $\\mathrm{Pjob}_j$ in job $j$.', 'Ascending physical-identifier list for job $j$, and source LP of its $k$th product.', 'Product counts by job and LP, by job, by recipe, and for the entire batch.', 'Job mode $m_j\\in\\mathcal M=\\{\\zeta,\\psi,\\mathrm{cl}\\}$ ($4\\times1$, $2\\times2$, cleaning); nonempty eligible set $\\mathcal C_j\\subseteq\\mathcal C=\\{\\mathrm{CH2},\\mathrm{CH3}\\}$.', 'PW pairs $\\mathcal P=\\{1,\\ldots,P_{\\max}\\}$, chamber cycles $\\mathcal Q_c=\\{1,\\ldots,Q_{\\max}\\}$, and wafer-route tasks $\\mathcal I=\\mathcal P\\times\\{0,1\\}$.', 'Upper bounds on production cycles, cleaning operations, PW pairs, and cycles per chamber.', 'Source regions $\\mathcal S=\\{A,V\\}$ (atmosphere, vacuum); $\\sigma=0$ for single-source and $1$ for dual-source supply.', 'Candidate physical operations and resource-occupancy intervals generated from route and cycle templates.', 'Resources, resource capacities, and auxiliary wafers $\\mathcal D=\\{1,\\ldots,D\\}$.', 'Processing duration of type $m$.', 'ATR handling, VTR handling, and chamber-$c$ half-turn durations.', 'ATR exchange, VTR exchange, and empty ATR travel from LL to LP.', 'Product alignment, upper-LL pumping, and lower-LL venting durations.', 'Upper/lower LL-slot reset durations, measured from completion of opposite-side pickup.', 'Operation duration, required predecessor--successor interval, and resource repositioning/reset interval.', 'Cleaning threshold in production cycles, $H\\ge2$.', 'Residency limit for route $i$ on resource $\\rho$; measurement conventions in Section~\\ref{sec:model-resource-cn}.', 'Scheduling horizon and relaxation constant $M=B+\\max\\{\\delta_{oo\\prime},\\delta^\\rho_{oo\\prime},r_c\\}$.', 'Nonnegative weights for total waiting, maximum individual waiting, and rhythm variation.', 'Tolerance on the product-completion upper bound.']
VARIABLE_ROWS = [('Binary decision', 'Assigns a job-$j$ product from LP $\\ell$ to position $(p,r)$; defined for $N_{j\\ell}>0$.'), ('Binary decision', 'Pair activation, processing-type selection, and chamber assignment.'), ('Binary decision', 'Pair--cycle occupancy, cycle type, and placement on the accessible side.'), ('Binary decision', 'Assigns auxiliary $\\tau\\in\\mathcal D$ to position $(p,r)$.'), ('Binary decision', 'Resource-unit assignment, resource service order, and paired handling synchronization.'), ('Real decision', 'Start times of operation $o$ and chamber cycle $(c,q)$.'), ('Auxiliary', 'Operation end time $e_o$ (real) and activation $b_o$ (binary).'), ('Real auxiliary', 'Pickup-time boundary between consecutive nonempty LPs of job $j$.'), ('Integer auxiliary', 'Production-cycle count since cleaning after cycle $(c,q)$, in $\\{0,\\ldots,H\\}$.'), ('Binary auxiliary', 'Product presence, $2\\times2$ product presence, and product-containing pair occupancy of cycle $(c,q)$.'), ('Binary auxiliary', 'Product assignment and auxiliary demand at position $(p,r)$.'), ('Binary auxiliary', 'Atmospheric and vacuum supply of route $i$.'), ('Real decision', 'Upper bound on product return times to the original LPs.'), ('Real auxiliary', 'Upper bounds on individual waiting and absolute variation of cycle-start intervals.')]
CAPTIONS = {
 'tab:joint-two-stage-cn': 'Two-stage and normalized joint objectives (paired means, times in s)',
 'tab:symbol-cn-a': 'Input parameters and sets',
 'tab:symbol-cn-b': 'Principal decision and auxiliary variables (real and integer variables are nonnegative)',
 'tab:structure-ablation-cn': 'Search strategies for four mixed-recipe instances (three-seed means, s)',
 'tab:refinement-ablation-cn': 'Timing refinement of the same schedule (three-seed means, s)',
 'tab:rhythm-weight-cn': 'Rhythm-weight ablation (three-seed means, times in s)',
 'tab:journal-structure-cn': 'Search strategies for four small dual-source instances (three-seed mean product completion, s)',
 'tab:journal-algorithm-cn': 'SPBS and cut selection: training seed 1 and three solver seeds (mean product completion, s)',
 'tab:journal-training-cn': 'Initialization across training seeds (mean product completion, s)',
 'tab:journal-transfer-cn': 'Algorithms across recipes and supply scenarios (mean product completion, s)',
 'tab:journal-transfer-components-cn': 'Components with shared SPBS inputs (mean product completion, s)',
}
WORDS = {
 '两阶段': 'Two-stage', '联合目标': 'Joint objective',
 '先固定后联合': 'Fixed then joint', '联合搜索': 'Joint', '固定结构': 'Fixed',
 '供片来源与腔室限制': 'Supply / eligibility', '精修前等待': 'Waiting before', '精修后等待': 'Waiting after',
 '单源、限制腔室': 'Single, restricted', '双源、限制腔室': 'Dual, restricted',
 '单源': 'Single', '双源': 'Dual', '16片纯': '16 products, pure ',
 '总等待': 'Total waiting', '节拍偏差': 'Rhythm deviation', '实例': 'Instance',
 '等待：前': 'Waiting: before', '后': 'after', '下界/上界': 'Lower/upper bound',
 'LP分布': 'LP distribution', '跨LP': 'Across LPs', '同LP': 'Same LP', '配方': 'Recipe',
 '固定结构精修后': 'After refinement', '第一阶段': 'Stage one', '指标': 'Metric',
 '产品完工时间': 'Product completion', '最大单项等待': 'Maximum individual waiting',
 '全部占用结束': 'End of all occupancy', '加工周期/清洁次数': 'Production/cleaning cycles',
 '借用次数/实际辅助片数': 'Loans/physical auxiliaries', '再次借用次数/同时借用峰值': 'Repeat loans/peak simultaneous loans',
 '有效节拍中心数': 'Valid rhythm centers', '辅助片数': 'Auxiliaries',
 '纯': 'Pure ', '混合': 'Mixed', '2片': '2 products', '4片': '4 products',
 '无SPBS': 'Without SPBS', '有SPBS': 'With SPBS', '方法': 'Method',
 '场景': 'Scenario', '三个纯': 'Three pure ',
 '仅扩展特征': 'Features only', '去结构重排': 'No reranking', '贪心替代束搜索': 'Greedy decoding',
 '联合': 'Joint', '固定': 'Fixed',
}
FIGURES = {
 'fig:system-zh-new': ('Figure1', 'Topology and wafer routes of the dual-source mixed-flow rotating-chamber cluster tool.'),
 'fig:single-source-cn': ('Figure2', 'Topology and wafer routes of the single-source rotating-chamber cluster tool.'),
 'fig:chain-zh': ('Figure3', r'Event sequence of $2\times2$ chained production.'),
 'fig:parallel-zh': ('Figure4', r'Event sequence of $4\times1$ parallel production.'),
 'fig:small-optimal-gantt-cn': ('Figure5', r'Optimal product-completion schedule for two pure $4\times1$ products from the same LP.'),
 'fig:current-defaults-gantt-cn': ('Figure6', r'Complete feasible resource schedule for 16 pure $4\times1$ products.'),
}

def environments(source, kind):
    return {re.search(r'\\label\{([^}]+)\}', m.group())[1]: m.group()
            for m in re.finditer(r'\\begin\{'+kind+r'\*?\}[\s\S]*?\\end\{'+kind+r'\*?\}', source)}

def translated_table(label, table):
    table = re.sub(r'\\caption\{[^\n]+\}', lambda _: '\\caption{'+CAPTIONS[label]+'}', table)
    if label in ('tab:symbol-cn-a', 'tab:symbol-cn-b'):
        rows = INPUT_ROWS if label.endswith('-a') else VARIABLE_ROWS
        index = 0
        lines = []
        for line in table.splitlines():
            if line.startswith('符号'):
                line = r'Symbol & Definition\\\midrule' if label.endswith('-a') else r'Symbol & Type & Definition\\\midrule'
            elif line.startswith('$') and ' & ' in line:
                symbol = line.split(' & ', 1)[0]
                translation = rows[index]
                line = symbol + ' & ' + (translation if isinstance(translation, str) else ' & '.join(translation)) + r'\\'
                index += 1
            lines.append(line)
        assert index == len(rows)
        table = '\n'.join(lines)
        # Widen the symbol column for English-table readability.
        if label.endswith('-a'):
            table = table.replace(r'0.14\textwidth', r'0.20\textwidth').replace(r'0.86\textwidth', r'0.80\textwidth')
        else:
            table = table.replace(r'0.11\textwidth', r'0.19\textwidth').replace(r'0.14\textwidth', r'0.18\textwidth').replace(r'0.71\textwidth', r'0.59\textwidth')
    else:
        for a,b in sorted(WORDS.items(),key=lambda p:-len(p[0])):
            table = table.replace(a,b)
        # All numerical cells are inherited directly; compact centered headers wrap.
        table = table.replace('16 products, pure ', '16 products, ')
        if label == 'tab:joint-two-stage-cn':
            for mode in ('4\\times1', '2\\times2'):
                table = table.replace('{Pure $'+mode+'$}', r'{\shortstack{Pure\\$'+mode+'$}}')
        if label == 'tab:structure-ablation-cn':
            table = table.replace('Fixed then joint', r'\shortstack{Fixed then\\joint}')
        if label == 'tab:rhythm-weight-cn':
            table = table.replace('Total waiting',r'\shortstack{Total\\waiting}').replace('Rhythm deviation',r'\shortstack{Rhythm\\deviation}')
            table = table.replace(r'{16 products, $2\times2$}',r'{\shortstack{16 products\\$2\times2$}}')
        if label == 'tab:journal-structure-cn':
            table = table.replace(r'\begin{tabular}',r'\setlength{\tabcolsep}{3pt}'+'\n'+r'\begin{tabular}')
        if label == 'tab:journal-structure-cn':
            table = table.replace('Fixed then joint',r'\shortstack{Fixed then\\joint}').replace('Across LPs',r'\shortstack{Across\\LPs}')
        if label == 'tab:journal-algorithm-cn':
            table = table.replace(r'\begin{tabular}',r'\setlength{\tabcolsep}{3.5pt}'+'\n'+r'\begin{tabular}')
        if label == 'tab:journal-training-cn':
            table = table.replace('productsMixed', 'products, mixed')
            table = table.replace(r'\begin{tabular}',r'\setlength{\tabcolsep}{5pt}'+'\n'+r'\begin{tabular}')
        if label == 'tab:journal-transfer-components-cn':
            table = table.replace('Three Pure ', 'Three pure ').replace('三个Pure ', 'Three pure ')
    assert not re.search('[\u4e00-\u9fff]', table), (label, re.findall('[\u4e00-\u9fff]+',table))
    return table.replace(r'o\prime', "o'")

def main():
    expected='7078c4ce14e5c33f6848686c962aebbffc6d81070f62704763a119e25574927b'
    if hashlib.sha256(CN.read_bytes()).hexdigest()!=expected:
        raise RuntimeError('The Chinese manuscript changed. Review the English translation before updating its source hash.')
    source = CN.read_text('utf-8')
    body = BODY.read_text('utf-8')
    eqs, tables, figs = [environments(source,k) for k in ('equation','table','figure')]
    for label,eq in eqs.items():
        assert body.count('{{EQ:'+label+'}}') == 1, label
        body = body.replace('{{EQ:'+label+'}}',eq)
    for label,table in tables.items():
        assert body.count('{{TABLE:'+label+'}}') == 1, label
        body = body.replace('{{TABLE:'+label+'}}','\n\n'+translated_table(label,table)+'\n\n')
    for label,fig in figs.items():
        stem,caption=FIGURES[label]
        fig=re.sub(r'(\\includegraphics(?:\[[^]]*\])?)\{[^}]+\}',lambda m:m[1]+'{'+stem+'}',fig)
        fig=re.sub(r'\\caption\{[^\n]+\}',lambda _:'\\caption{'+caption+'}',fig)
        if label=='fig:chain-zh':fig=fig.replace('0.93\\linewidth','0.89\\linewidth')
        assert body.count('{{FIG:'+label+'}}') == 1
        body=body.replace('{{FIG:'+label+'}}','\n\n'+fig+'\n\n')
    bibliography=source[source.index(r'\small',source.index(r'\section*{CRediT')):]
    body=body.replace('{{BIBLIOGRAPHY}}',bibliography)
    preamble=source[:source.index(r'\title')]
    preamble=re.sub(r'\\usepackage\{iftex\}[\s\S]*?(?=\\usepackage\{amsmath)', '',preamble)
    preamble=preamble.replace('xelatex','pdflatex').replace(r'\usepackage{microtype}',r'\usepackage[expansion=false]{microtype}')
    preamble=re.sub(r'\\graphicspath\{[^\n]+',lambda _:r'\graphicspath{{figures/submission_en/}}',preamble)
    preamble=preamble.replace(r'\newcommand{\method}{RDMCT-HBS}'+'\n','')
    preamble=preamble.replace('算法~','Algorithm~').replace('：',': ')
    preamble=preamble.replace(r'\usepackage{subcaption}'+'\n','')
    preamble=re.sub(r'\\captionsetup\[subfigure\][^\n]*\n','',preamble)
    preamble=preamble.replace(r'\usepackage{dblfloatfix}',r'\usepackage{stfloats}')
    preamble=preamble.replace(r'\usepackage{graphicx}',r'\usepackage{graphicx,makecell}')
    preamble=preamble.replace(r'\usepackage{xurl}',r'\usepackage{xurl}'+'\n'+r'\urlstyle{same}')
    preamble=preamble.replace(r'\begin{document}',r'''\clubpenalty=10000
\widowpenalty=10000
\brokenpenalty=10000
\setlength{\textfloatsep}{10pt plus 2pt minus 2pt}
\setlength{\intextsep}{10pt plus 2pt minus 2pt}
\setlength{\floatsep}{8pt plus 2pt minus 2pt}
\setlength{\dbltextfloatsep}{10pt plus 2pt minus 2pt}
\setlength{\dblfloatsep}{8pt plus 2pt minus 2pt}
\begin{document}''')
    result=preamble+body
    result=result.replace(r'\shortstack{',r'\makecell[c]{')
    title=re.search(r'\\title\{([^}]+)\}',body)[1]
    result=result.replace(r'\begin{document}', '\\hypersetup{pdftitle={'+title+'},pdfauthor={Lincong Wei; Lizhen Shao; Wei Wang}}\n'+r'\begin{document}')
    assert '{{EQ:' not in result and '{{TABLE:' not in result and '{{FIG:' not in result
    assert not re.search('[\u4e00-\u9fff]', result)
    assert len(eqs)==34 and len(tables)==11 and len(figs)==6
    abstract=re.search(r'\\begin\{abstract\}([\s\S]*?)\\end\{abstract\}',result)[1]
    word_count=len(abstract.split())
    assert word_count<=250,word_count
    target=PAPER/'JMS_Submission_EN.tex'
    target.write_text(result,'utf-8')
    report={'chinese_source_sha256':hashlib.sha256(CN.read_bytes()).hexdigest(),
            'english_source_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),
            'equations':len(eqs),'tables':len(tables),'figures':len(figs),
            'bibliography_items':len(re.findall(r'\\bibitem',result)),
            'abstract_word_count':word_count,'funding':'No specific funding; confirmed by author on 2026-11-14'}
    (PAPER/'submission/translation_checks.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
