from pathlib import Path
import re
P=Path(__file__).resolve().parents[1];s=(P/'TASE_Submission_EN.tex').read_text('utf-8')
start=s.index('\\section{Introduction}');end=s.index('\\section{Problem description')
intro=r'''\section{Introduction}
Cluster tools coordinate processing modules, robots and load locks in semiconductor fabrication. Residency limits, shared handling resources and cleaning couple wafer routes and production output \cite{pan2018survey}. Multi-space modules and multi-finger robots add parallel processing and paired handling opportunities \cite{gu2024applied,gu2024multifinger}. This paper studies finite batches in plasma-enhanced chemical vapor deposition (PECVD) equipment with two four-position rotating chambers.

\begin{figure}[t]
\centering\includegraphics[width=\linewidth]{fig_system_en_nature}
\caption{Dual-source rotating-chamber tool and product/dummy routes.}
\label{fig:system-en-new}
\end{figure}

Products enter from atmospheric load ports; reusable dummy wafers enter from vacuum storage. Under the prescribed full-occupancy recipe, dummies fill unused positions and occupy chambers during cleaning. Their return times constrain subsequent product processing. We call these separate supplies dual-source operation, and their interleaved use of robots and chambers mixed flow. The scheduler must jointly determine product and dummy movements, robot service order, and the timing of complete processing and cleaning chains.

Two qualified processing modes are compared conditionally: $4\times1$ processes four wafers once, whereas $2\times2$ alternates paired exchanges so that every product receives two consecutive exposures. Equal cumulative nominal process time allows a scheduling comparison; it does not establish physical recipe equivalence. Cycle counts and chain initialization/termination can move cleaning inside or after the product-processing horizon. Consequently, the mode with the shortest individual cycle need not complete the lot first.

Prior work develops throughput analysis, residency-constrained linear programming and timed Petri-net models \cite{perkinson1994throughput,rostami2002optimal,wu2010closedform,qiao2012sojourn}. Extensions include revisiting routes, multiple wafer types, selectable modules and joint release/handling decisions \cite{qiao2014revisiting,wang2020multiple,wang2025virtualcell,yang2025miptwowafers}. Cleaning-aware models coordinate task sequences, wafer delay and cleaning triggers \cite{kim2013cleaning,yu2020delay,qiao2022binary,li2022conditioncleaning}. Recent T-ASE work addresses failure-related scheduling and noncyclic reinforcement-learning control \cite{zhu2025failuredeadlock,kim2025noncyclicdeadlock,kim2025adaptivecluster}. These studies motivate coordinated automation, but their schedules cannot be transferred unchanged to the present dual-source routes and rotating-chamber occupancy rules.

Learning can also assist mathematical optimization through cut ranking or selection \cite{tang2020cut,huang2022cutranking,paulus2022looking}. The hierarchical sequence model (HEM) chooses the number and ordered subset of cuts \cite{wang2023hem}. Here, mathematical variable roles augment that representation while the MILP retains responsibility for process feasibility. Numerical comparisons include HEM, configured SCIP, adaptive cut scoring and component ablations on identical models.

The contributions are: 1) a joint finite-batch model of product/dummy logistics, full occupancy, periodic cleaning and shared-resource timing under prescribed pair layouts; 2) makespan-first timing refinement and bound-based identification of how cleaning-induced chain segmentation changes mode preference; and 3) a solver framework combining structure-preserving binary-skeleton (SPBS) initialization and role-aware cut selection, with separate evidence for initialization, timing quality and search performance. The experiments support SPBS and timing refinement benefits; they do not establish statistically significant superiority of the complete learned selector over HEM.

'''
s=s[:start]+intro+s[end:]
start=s.index('\\subsection{SPBS initial solution}');end=s.index('\\subsection{HEM baseline')
spbs=r'''\subsection{SPBS initial solution}
SPBS constructs a conservative discrete schedule from the recipe and tool layout. Products are paired in input order; parallel-mode pairs are placed sequentially and chained-mode pairs round-robin across chambers. Complete chains determine cleaning boundaries, and deterministic load-lock slots break symmetry. ATR/VTR order follows product progression and dummy return.

A restricted MILP fixes the binary skeleton and solves for compatible event times. Five relaxation levels successively release VTR order, load-lock order, other resource orders, and slot choices, retaining prescribed structural assignments. Large instances start at less restrictive levels. Each subproblem uses a zero objective, feasibility emphasis, aggressive heuristics and no cut separation, and stops at its first feasible solution. Failure to find one within a level's budget is not an infeasibility certificate.

After completing auxiliary schedule-quality variables, a candidate must pass the original-model feasibility check before becoming an incumbent. The main solve restores original bounds. These initial schedules are precomputed in the reported benchmark; their construction cost is excluded from main-solve timing and PDI. Thus the SPBS comparison estimates the value of an available feasible start, not an initialization-inclusive speedup.

'''
s=s[:start]+spbs+s[end:]
# compact baseline background to one paragraph; role definitions and core equations are retained.
start=s.index('Prior learning-based cut selectors address');end=s.index('Starting from the 13 generic HEM features')
s=s[:start]+r'''The direct learned comparator reproduces HEM's 2023 count/sequence decomposition with 13 generic row-quality features: objective parallelism, efficacy, support, integral support, violation, and four statistics each of row and objective coefficients \cite{wang2023hem}. Training splits, seeds, budgets, candidate limits and hidden dimensions are shared. The later sequence/set extension \cite{wang2024hemset} is related work, not an evaluated baseline.

'''+s[end:]
# Remove duplicate prose preceding empirical tables, retaining boundary evidence and numerical interpretation.
a=s.index('For 8 wafers, the three makespans remain');b=s.index('The 24-wafer extension')
s=s[:a]+r'''For 8 wafers, chained processing is preferred throughout $H=3$--10. For 16 wafers, parallel, mixed and chained modes are preferred at $H=3$, $H=4$, and $H=5$--10, respectively. At $H=5$, the validated 898-s chained schedule beats both competing optima even though its own optimality is unresolved. At $H=6$--10, 898~s is proven optimal, 4.87\% below parallel operation.

The 16-wafer chained layout contains four product pairs per chamber. It splits them as 2+2 at $H=3$, 3+1 at $H=4$, and one chain at $H\ge5$. Equal internal-cleaning counts at $H=3$ and 4 therefore need not give equal makespans. The study compares the joint effect of the cleaning limit and regenerated admissible chain layout.

'''+s[b:]
# Keep the DOE numbers in text; the plot repeats those exact means.
s=re.sub(r'\\begin\{figure\}\[!htbp\].*?\\end\{figure\}',lambda m:'' if '\\label{fig:doe-en-new}' in m[0] else m[0],s,flags=re.S)
s=s.replace('Figure~\\ref{fig:doe-en-new} shows a sharp transition.','The results show a sharp transition.')
# equation width
s=s.replace(r'&&\bigl(\nu\in\{FL,BL,P,BU,FU\}\bigr),',r'\\[-1pt]&\nu\in\{FL,BL,P,BU,FU\},')
# This baseline is configured (root-only separation), not an unrestricted factory-default solver.
s=s.replace('SCIP default &','Configured SCIP &')
s=s.replace('Default SCIP has the highest','Configured SCIP has the highest')
s=s.replace('The compared methods use the same MILP, SCIP version, instances, and random seeds, and each comparison family uses common time and memory limits.','Within each comparison family, methods share the MILP, SCIP version, instances, random seeds, time and memory limits. The algorithm benchmark uses root-only cut separation, including its configured SCIP baseline.')
(P/'TASE_Submission_EN.tex').write_text(s,encoding='utf-8')
print('Main manuscript refined for length and protocol clarity.')

