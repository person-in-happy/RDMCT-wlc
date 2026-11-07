from pathlib import Path
import re,json
P=Path(__file__).resolve().parents[1]
s=(P/'TASE_Submission_EN.tex').read_text('utf-8')
# Full detail remains in a separately named supplement; it includes no identifying data.
supp=s.replace('Coordinated Scheduling and Process-Mode Selection for Dual-Source Rotating-Chamber Cluster Tools','Supplementary Details: Coordinated Scheduling of Dual-Source Rotating-Chamber Cluster Tools')
(P/'TASE_Supplement_EN.tex').write_text(supp,encoding='utf-8')
# Remove two duplicated notation catalogues; physical and algebraic definitions remain in text.
s=re.sub(r'Tables~\\ref\{tab:symbol-en-a\}.*?(?=\\subsection\{Source interfaces)',r'''The model uses chambers $c\\in\\mathcal C$, product wafers $w\\in\\mathcal W$, product-containing pairs $p\\in\\mathcal P^F\\cup\\mathcal P^L$, batch positions $b\\in\\mathcal B_c$, chain positions $k\\in\\mathcal K_c$, cycles $q\\in\\mathcal Q_c$, and cleaning segments $e\\in\\mathcal E_c$. Physical operations $o\\in\\mathcal O$ have start/end times $s_o,e_o$, duration $d_o$, and binary activation $b_o$. Binary $u$ denotes batch/position activation, $f$ dummy filling, $t$ or $h$ a tail, $g$ dummy assignment, $h_{o\\ell}$ slot use, and $y$ resource order. Bars denote prescribed input data. $M$ is a valid horizon bound. The supplementary material provides the complete notation catalogue and expanded explanations.

''',s,flags=re.S)
# Remove only redundant equation paraphrases; retain paragraphs that add material constraints.
drop=['source-membership-en','route-union-en','pair-slot-en','activation-prefix-en','operation-time-en','precedence-en','full-capacity-en','mix-position-en','dummy-assign-en','slot-select-en','stage-link-en','double-transfer-en','spbs-fix-en','role-mass-en','gated-encoding-en','lstm-encoding-en','pointer-decoding-en','policy-en','beam-score-en']
for label in drop:
 s=re.sub(r'Equation~\\eqref\{eq:'+label+r'\}[^\n]*(?:\n\n)', '',s)
# Shorten generic learning exposition but retain mathematical adapter, policy, completion and training.
start=s.index('The fused candidates, in the deterministic order')
end=s.index('\\subsection{Stepwise selection')
s=s[:start]+r'''The gated embeddings are processed by a one-layer LSTM with hidden dimension 128 and a pointer decoder with one glimpse. Masking prevents repeated candidates. A high-level policy chooses $k_t$; the low-level policy factorizes as
\begin{equation}
\pi_\theta(k_t,i_{1:k_t}\mid S_t)=\pi_\theta^H(k_t\mid S_t)
\prod_{r=1}^{k_t}\pi_\theta^L(i_r\mid S_t,i_{1:r-1}).
\label{eq:policy-en}
\end{equation}
Training samples from the policy. Inference retains three prefixes with largest accumulated conditional log-probability after each extension. This is a probability-guided search, without a guarantee for the resulting MILP objective.

'''+s[end:]
start=s.index('\\subsection{Stepwise selection')
end=s.index('\\noindent\\textbf{Step 6:')
s=s[:start]+r'''\subsection{Candidate limits and role-submodular completion}
SCIP supplies valid candidate inequalities. At most 128 rows are retained in decreasing efficacy order, breaking ties by original index; forced rows stay under solver control. The high-level action determines a cut fraction subject to a 0.2 cap, the solver's limit, and a maximum of 16 cuts. At least two are selected when allowed. The width-three decoder constructs the ordered subset; pointer-network and neural-search precedents are given in \cite{vinyals2015pointer,choo2022beam}.

'''+s[end:]
s=s.replace('\\noindent\\textbf{Step 6: role-submodular completion.} ','')
# Algorithm table duplicates the explicit pipeline.
s=re.sub(r'\\begin\{table\}\[!htbp\].*?\\end\{table\}',lambda m:'' if '\\algorithmtitle' in m[0] else m[0],s,flags=re.S)
# Endpoint table is a strict subset of the grid.
s=re.sub(r'\\begin\{table\*\}\[!htbp\].*?\\end\{table\*\}',lambda m:'' if '\\label{tab:mode-extended-en}' in m[0] else m[0],s,flags=re.S)
s=s.replace('Table~\\ref{tab:mode-extended-en} compares cleaning endpoints; Table~\\ref{tab:clean-crossover-en} gives the full $H=3$--10 grid.','Table~\\ref{tab:clean-crossover-en} gives the $H=3$--10 comparison.')
# Identical pure41 schedule repeated at H3; explain that it also represents H3.
s=re.sub(r'\\begin\{figure\}\[!t\].*?\\end\{figure\}',lambda m:'' if '\\label{fig:gantt-cleanH3-41-en}' in m[0] else m[0],s,flags=re.S)
s=s.replace('16-wafer pure $4\\times1$ schedule at $H=10$.','16-wafer pure $4\\times1$ schedule at $H=10$ (identical at $H=3$).')
s=s.replace('Four resource Gantt charts show both pure modes','Resource Gantt charts show both pure modes').replace('The four resource Gantt charts use','The resource Gantt charts use')
# Preserve all numerical evidence, condense repeated conclusion into a restrained summary.
start=s.index('\\section{Conclusions}')
end=s.index('\\section*{Acknowledgment}')
s=s[:start]+r'''\section{Conclusions}
The proposed two-stage MILP coordinates product and reusable dummy flows, chamber occupancy, cleaning and shared-resource timing for finite batches. Under prescribed qualified recipes and pair layouts, the preferred mode depends on lot size and cleaning-induced chain segmentation. Chained processing reaches 898~s for a 16-wafer lot without activated cleaning, compared with 944~s for parallel processing. Valid upper and lower bounds establish the reported mode choices without treating a time limit as an infeasibility proof.

The frozen computational evidence supports the scheduling value of precomputed feasible starts and equal-budget waiting/cadence refinement. It does not establish statistical superiority of the complete cut selector over HEM, nor a universal out-of-distribution advantage. Further work should measure initialization-inclusive decision latency, relax prescribed pair placement, and validate disturbance handling and recipe qualification on physical equipment.

'''+s[end:]
# Split long equations without changing mathematics.
s=s.replace(r's^{B}_{cq}&\ge e^L_{c,q-1}-M(1-a^L_c),\qquad',r's^{B}_{cq}&\ge e^L_{c,q-1}-M(1-a^L_c),\\')
s=s.replace(r'q^{\rm cl}_{ch},&j\text{ is a cleaning demand}.',r'q^{\rm cl}_{ch},&j\text{ is a cleaning demand}.')
s=s.replace(r'a^L_c,&j\text{ is a $2\times2$ head or tail demand},',r'a^L_c,&j\text{ is a chain endpoint demand},')
# Direct HEM table is redundant with the complete table; keep statistics in prose.
s=re.sub(r'\\begin\{table\}\[!htbp\].*?\\end\{table\}',lambda m:'' if '\\label{tab:hem-direct-en}' in m[0] else m[0],s,flags=re.S)
s=s.replace('Table~\\ref{tab:hem-direct-en} presents this prespecified direct comparison.','Table~\\ref{tab:all-methods} includes this prespecified direct comparison.')
# Correctly distinguish the frozen algorithm configuration from the equal-recipe mode experiment.
target='The numerical values in Table~\\ref{tab:gantt-config-en} define the computational configuration.'
s=s.replace(target,r'''Two experiment families use different prescribed configurations. The frozen algorithm benchmark uses nominal 180-s durations for both a parallel process and each chained exposure, a 500-s module-residency bound, and $H=5$ in the nominal core suite. Its PDI and schedule-quality comparisons concern methods solving the same instances; they do not compare equal-dose process modes. The mode-selection study instead uses 180~s versus 90+90~s and a 10000-s module-residency bound. The numerical values in Table~\ref{tab:gantt-config-en} apply to the latter family.''')
# Initial 500-run HEM comparison time is total budget, as formal runner reserves stage two.
# IEEE bib style initials need spaces to preserve multiple initials.
bib=(P/'references.bib').read_text('utf-8')
bib=re.sub(r'(?<=[A-Z])\.(?=[A-Z])','. ',bib)
(P/'references.bib').write_text(bib,encoding='utf-8')
(P/'TASE_Submission_EN.tex').write_text(s,encoding='utf-8')
print('Condensed main manuscript; expanded details preserved separately.')

