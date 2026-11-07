from pathlib import Path
import re
P=Path(__file__).resolve().parents[1];s=(P/'TASE_Submission_EN.tex').read_text('utf-8')
a=s.index('\\section{Structure-aware');b=s.index('\\section{Computational')
spbs=s[s.index('\\subsection{SPBS initial solution}'):s.index('\\subsection{HEM baseline')]
method=r'''\section{Structure-Aware Solution Framework}
\label{sec:method-new}
SCIP generates valid inequalities, checks incumbents and maintains primal/dual bounds \cite{achterberg2009scip,bestuzheva2023scip}. SPBS provides an initial feasible schedule and \method{} selects from solver-generated cuts. Neither component changes the model's integer feasible set. The supplementary material gives the expanded network, feature and training definitions.

'''+spbs+r'''\subsection{Role-aware hierarchical cut selection}
The 2023 HEM sequence model is the direct learned baseline \cite{wang2023hem}; its later sequence/set extension is related work \cite{wang2024hemset}. The 13 baseline features measure objective parallelism, efficacy, support, integral support, violation, and four statistics each of cut and objective coefficients. Ten added features describe five variable-role coefficient masses, finite-bound mass, positive-coefficient mass, discrete--continuous coupling, dominant-role mass and role entropy. Roles are binary, general integer, objective-active continuous, other continuous auxiliary, and residual variables. For cut coefficients $a_{ij}$, role mass is
\begin{equation}
p_{ig}=\frac{\sum_{j:x_j\in g}|a_{ij}|}{\sum_j|a_{ij}|+\varepsilon}.
\end{equation}
Feature extraction uses variable type, objective coefficient and global bounds, so renaming variables leaves the representation unchanged.

After layer normalization, separate linear projections of the 13 generic and ten role features are fused with a sigmoid gate. A one-layer 128-unit LSTM encodes candidates; a pointer decoder uses one glimpse and masks previously selected rows \cite{vinyals2015pointer}. A high-level policy predicts the retained count. At inference, width-three beam search retains the highest accumulated log-probability prefixes \cite{choo2022beam}. Candidates are capped at 128 in efficacy order; at most 20\% and 16 rows are retained, subject to SCIP's limit. Forced cuts remain under solver control.

The first $\lceil0.25k\rceil$ decoded rows serve as fixed anchors. Greedy completion selects remaining rows from at most $2k$ policy/heuristic candidates by marginal gain of
\begin{equation}
\begin{aligned}
F(S)={}&\sum_{i\in S}(0.35q_i+0.20r_i)
+0.25\sum_g d_g\sqrt{\sum_{i\in S}p_{ig}}\\
&+\frac{0.20}{|\mathcal R|}\sum_{u\in\mathcal R}\max_{i\in S}s_{ui}.
\end{aligned}
\end{equation}
Here $q_i$ combines instantaneous cut quality and role descriptors, $r_i$ is a normalized pointer-rank prior, $d_g$ is pool role demand, and $s_{ui}$ is clipped cosine similarity. Nonnegative weights make this a monotone submodular surrogate. For fixed anchors and pool, greedy residual completion has the standard $1-1/e$ approximation property \cite{nemhauser1978analysis}; this is not a guarantee for PDI or solve time. Anchor order precedes greedy-completion order when cuts enter the LP.

\subsection{Training protocol}
Training uses five instances, five independent training seeds and the fixed epoch-60 checkpoint. Each epoch collects eight 30-s/1024-MB rollouts with two workers. The terminal PDI is the cost; the first eligible candidate-set action supplies the high/low-level log-probability sample. Parallel hierarchical REINFORCE uses separate exponential-moving-average baselines (decay 0.9), sequence-length-normalized low-level log probability, and gradient clipping at 2 \cite{williams1992reinforce,mnih2016a3c}. The high level updates every two epochs. Adam learning rates start at $10^{-4}$ and $5\times10^{-4}$ and decay by 0.96 every ten epochs. HEM, feature-only and complete policies are trained separately. Stochastic training and beam inference are distinguished; test-instance performance is not used to select checkpoints.

'''
s=s[:a]+method+s[b:]
for block in re.findall(r'\\begin\{figure\}.*?\\end\{figure\}',s,flags=re.S):
 if any(x in block for x in ['fig_system_en','fig_resource_gantt','fig04_workflow']):
  s=s.replace(block,block.replace(r'\begin{figure}',r'\begin{figure*}').replace(r'\end{figure}',r'\end{figure*}').replace(r'width=\linewidth',r'width=0.94\textwidth'))
full=(P/'TASE_Supplement_EN.tex').read_text('utf-8')
header=full[:full.index('\\begin{document}')]
model=full[full.index('\\section{Problem description'):full.index('\\section{Computational')]
model=model.replace(r'&&\bigl(\nu\in\{FL,BL,P,BU,FU\}\bigr),',r'\\[-1pt]&\nu\in\{FL,BL,P,BU,FU\},')
model=model.replace(r's^{B}_{cq}&\ge e^L_{c,q-1}-M(1-a^L_c),\qquad',r's^{B}_{cq}&\ge e^L_{c,q-1}-M(1-a^L_c),\\')
model=model.replace(r'a^L_c,&j\text{ is a $2\times2$ head or tail demand},',r'a^L_c,&j\text{ is a chain endpoint demand},')
supp=header+r'''\begin{document}
\title{Supplementary Model and Solver Details}
\author{}\maketitle
This supplement accompanies \textit{Coordinated Scheduling and Process-Mode Selection for Dual-Source Rotating-Chamber Cluster Tools}. It expands notation, physical constraints, initial-schedule construction and the learned cut selector. It contains no additional experimental outcomes.
'''+model+r'''\section*{AI Assistance}
OpenAI ChatGPT and Codex assisted with language revision, translation, LaTeX preparation and explanation of the model and solver code. The mathematical formulation and previously reported numerical evidence were preserved.
\bibliographystyle{IEEEtran}
\bibliography{references}
\end{document}
'''
(P/'TASE_Supplement_EN.tex').write_text(supp,encoding='utf-8')
(P/'TASE_Submission_EN.tex').write_text(s,encoding='utf-8')
cn=(P/'TASE_Review_CN.tex').read_text('utf-8')
idx=cn.index('\\label{sec:results')
cn=cn[:idx]+cn[idx:].replace('\\subsection{实验设计',r'''\noindent 本文区分两类实验配置：冻结算法基准的标称并行加工及每次链式曝光均为180~s，模块驻留上限为500~s，core标称组$H=5$；模式比较使用180~s对90+90~s以及10000~s模块驻留上限。前者评价同一实例上的求解方法，不能作为相同累计加工时长的模式比较。算法基准还共同采用仅根节点分离割的配置，因此其中SCIP为受控配置基线。

\subsection{实验设计''',1)
cn=cn.replace(r'&&\bigl(\nu\in\{FL,BL,P,BU,FU\}\bigr),',r'\\[-1pt]&\nu\in\{FL,BL,P,BU,FU\},')
cn=cn.replace(r's^{B}_{cq}&\ge e^L_{c,q-1}-M(1-a^L_c),\qquad',r's^{B}_{cq}&\ge e^L_{c,q-1}-M(1-a^L_c),\\')
(P/'TASE_Review_CN.tex').write_text(cn,encoding='utf-8')

