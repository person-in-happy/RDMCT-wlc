from pathlib import Path
import re
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch,FancyArrowPatch
P=Path(__file__).resolve().parents[1]
fig,ax=plt.subplots(figsize=(7.0,2.25));ax.set_xlim(0,10);ax.set_ylim(0,3);ax.axis('off')
def box(x,y,w,h,text,color='#edf2f7'):
 ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.04',facecolor=color,edgecolor='#243b53',linewidth=.8));ax.text(x+w/2,y+h/2,text,ha='center',va='center',fontsize=8.5)
def arrow(a,b,color='#245a81'):
 ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=9,linewidth=1,color=color))
box(.1,1.25,1.25,.6,'Product LPs')
box(1.85,1.25,1.2,.6,'ATR')
box(1.85,2.25,1.2,.55,'Aligner')
box(3.55,1.9,1.55,.6,'Upper load lock')
box(3.55,.55,1.55,.6,'Lower load lock')
box(5.65,1.25,1.15,.6,'VTR')
box(7.55,2.05,2.15,.65,'CH2: four positions')
box(7.55,.95,2.15,.65,'CH3: four positions')
box(5.5,.05,1.9,.55,'Dummy storage','#fff0df')
for a,b in [((1.35,1.65),(1.85,1.65)),((1.85,1.43),(1.35,1.43)),((2.3,1.85),(2.3,2.25)),((2.6,2.25),(2.6,1.85)),((3.05,1.7),(3.55,2.18)),((3.55,.83),(3.05,1.4)),((5.1,2.18),(5.65,1.7)),((5.65,1.4),(5.1,.83)),((6.8,1.72),(7.55,2.4)),((7.55,2.18),(6.8,1.56)),((6.8,1.5),(7.55,1.4)),((7.55,1.17),(6.8,1.32))]:arrow(a,b)
arrow((6.15,.6),(6.15,1.25),'#a95717');arrow((6.45,1.25),(6.45,.6),'#a95717')
ax.plot([3.28,3.28],[.15,2.9],ls='--',lw=.8,color='#7b8794')
ax.text(.15,.25,'Atmospheric product route',fontsize=8.5,color='#245a81')
ax.text(7.65,.23,'Vacuum domain',fontsize=8.5)
fig.subplots_adjust(left=.01,right=.99,bottom=.02,top=.98)
fig.savefig(P/'figures/fig_system_tase.pdf');plt.close(fig)
s=(P/'TASE_Submission_EN.tex').read_text('utf-8').replace('fig_system_en_nature','fig_system_tase')
# Remove redundant plots; retain all the quantitative comparisons.
for block in re.findall(r'\\begin\{figure\*\}.*?\\end\{figure\*\}',s,flags=re.S):
 if 'fig_resource_gantt_cleanH10_w16_41_en' in block or 'fig04_workflow_en' in block:s=s.replace(block,'')
s=s.replace('Figure~\\ref{fig:workflow-en-new} shows that','The measured instance means show that')
s=s.replace('The charts compare resource occupancy and event coordination between the two modes.','The charts illustrate chained-mode resource occupancy and event coordination; the parallel-mode times appear in the comparison table.')
s=s.replace('Resource Gantt charts show both pure modes for 16 wafers at $H=10$ and $H=3$.','Resource Gantt charts show chained-mode operation for 16 wafers at $H=10$ and $H=3$.')
s=s.replace('The resource Gantt charts use 16 wafers and compare the pure modes at $H=10$ and 3.','The resource Gantt charts show 16-wafer chained operation at $H=10$ and 3.')
# Remove repeated parameter prose.
s=s.replace('Table~\\ref{tab:gantt-config-en} specifies the experimental parameters for the representative 16-wafer Gantt charts. Two rotating chambers share the VTR, while product and dummy wafers compete for robots, load locks, and chamber spaces along their respective routes; cleaning counts, rotation, and transfer times are represented in the same MILP. All displayed schedules satisfy the original-model constraints checked by SCIP and an independent event-time validation. The charts illustrate chained-mode resource occupancy and event coordination; the parallel-mode times appear in the comparison table.','The two chambers share the VTR. Displayed schedules pass original-model and event-time checks.')
# Compact full grid by grouping identical rows, retaining all H ranges and distinction in cleaning.
lines=s.splitlines();out=[]
for line in lines:
 if re.match(r'8 & [4-9] &',line):continue
 if line.startswith('8 & 10 &'):line=line.replace('8 & 10 &','8 & 4--10 &',1)
 if re.match(r'16 & [6-9] &',line):continue
 if line.startswith('16 & 10 &'):line=line.replace('16 & 10 &','16 & 6--10 &',1)
 if re.match(r'24 & [89] &',line):continue
 if line.startswith('24 & 10 &'):line=line.replace('24 & 10 &','24 & 8--10 &',1)
 out.append(line)
s='\n'.join(out)+'\n'
(P/'TASE_Submission_EN.tex').write_text(s,encoding='utf-8')
cn=(P/'TASE_Review_CN.tex').read_text('utf-8')
cn=cn.replace('\\section{计算实验与结果分析}',r'''\section{计算实验与结果分析}
本文区分两类实验配置：冻结算法基准的标称并行加工及每次链式曝光均为180~s，模块驻留上限为500~s，core标称组$H=5$；模式比较使用180~s对90+90~s以及10000~s模块驻留上限。前者评价同一实例上的求解方法，不能作为相同累计加工时长的模式比较。算法基准共同采用仅根节点分离割的受控配置。''')
cn=cn.replace(r'&&\bigl(\nu\in\{FL,BL,P,BU,FU\}\bigr),',r'\\[-1pt]&\nu\in\{FL,BL,P,BU,FU\},')
cn=cn.replace(r's^{B}_{cq}&\ge e^L_{c,q-1}-M(1-a^L_c),\qquad',r's^{B}_{cq}&\ge e^L_{c,q-1}-M(1-a^L_c),\\')
(P/'TASE_Review_CN.tex').write_text(cn,encoding='utf-8')

