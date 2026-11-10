from pathlib import Path
import re
p=Path('JMS-version/JMS_Review_CN.tex');s=p.read_text(encoding='utf-8')
rev=Path('JMS-version/revisions/20261103_event_alias_simplification')
start=s.index(r'\subsection{批次任务与产品晶圆编码}')
end=s.index(r'\section{批次任务编码、两阶段求解与晶圆解码}')
model=s[start:end]
def replace(a,b):
 global model
 assert a in model,a[:100]
 model=model.replace(a,b)
def paragraph(prefix,new):
 global model
 lines=model.splitlines();ids=[i for i,l in enumerate(lines) if l.startswith(prefix)];assert len(ids)==1,(prefix,ids)
 lines[ids[0]]=new;model='\n'.join(lines)+'\n'
def equation(label,new):
 global model
 pat=r'\\begin\{equation\}(?:(?!\\end\{equation\}).)*?\\label\{'+re.escape(label)+r'\}(?:(?!\\end\{equation\}).)*?\\end\{equation\}'
 matches=list(re.finditer(pat,model,re.S));assert len(matches)==1,label
 m=matches[0];model=model[:m.start()]+new+model[m.end():]
# One start/end family with action identities instead of additional clocks.
anchor=r'\noindent\textbf{批次内非递减顺序出片：}'
replace(anchor,r'''动作时刻统一采用表~\ref{tab:symbol-cn-b}中的$s_o,e_o$。为明确动作身份，下标$o$可写成$(i,a)$、$(p,a)$或$(c,q,a)$，分别定位晶圆路线$i$、PW对$p$或腔室周期$(c,q)$的动作；$a$是取片、放片或旋转等动作标签。这些下标只定位已有动作，不增加时刻变量。加工周期的开始时刻沿用$S_{cq}$。

'''+anchor)
replace(r'''建立对应变量。$s^{\rm pick}_{pr}$是非负实数变量，表示位置$(p,r)$的晶圆在LP取片的开始时刻，直接引用对应
动作的$s_o$。因此，相邻非空LP之间满足''',r'''建立对应变量。对每个对内位置$(p,r)$，以下$o=((p,r),\mathrm{pick})$定位其LP取片动作。相邻非空LP之间满足''')
replace(r's^{\rm pick}_{pr}',r's_o')
paragraph('于是，较小编号LP中属于该任务的产品取片开始时刻',r'''于是，较小编号LP中属于该任务的产品取片开始时刻均不晚于下一非空LP中该任务产品的取片开始时刻。$o_{jk}$是解码后$\mathrm{Pjob}_j[k]$的LP取片动作索引，因此批次内顺序可直接写为''')
replace(r's^{\rm pick}_{j,k+1}',r's_{o_{j,k+1}}');replace(r's^{\rm pick}_{jk}',r's_{o_{jk}}')
# Remove a repeated LP-location indicator that only abbreviates the inventory sum.
replace(r'$\chi_{pr\ell}$是二元辅助变量，表示位置$(p,r)$的产品晶圆是否来自LP $\ell$，满足$\chi_{pr\ell}=\sum_jx_{j\ell pr}$；回片使用同一LP。',r'位置$(p,r)$的产品来源及回片LP直接由$\sum_jx_{j\ell pr}$确定。')
replace(r'产品源端和回片地点按$\chi_{pr\ell}$联结',r'产品源端和回片地点按$\sum_jx_{j\ell pr}$联结')
# Conditional linking and pair synchronization use the original action clocks.
paragraph('产品晶圆或辅助晶圆的个体阶段必须',r'''单片动作须与被选中的PW对动作一致。对待联结的两个动作$o,o'$，$x$引用相应库存指派、周期占位或搬运选择的既有二元变量。联结条件为''')
replace(r's^{\rm ref}',r's_{o\prime}');replace(r'e^{\rm ref}',r'e_{o\prime}')
model=model.replace(r'o\prime',"o'")
paragraph('$i_1=(p,0)',r'''对同一原子段$a$，取$o=((p,0),a)$、$o'=((p,1),a)$，分别定位PW对$p$中两片晶圆的动作。成对搬运要求''')
for a,b in [(r's_{i_1a}','s_o'),(r's_{i_2a}',"s_{o'}"),(r'e_{i_1a}','e_o'),(r'e_{i_2a}',"e_{o'}")]:replace(a,b)
# Product/dummy source events are action indices in the same s/e family.
model=re.sub(r'([se])_\{i_\{\\rm ([PD])\},\\mathrm\{(LLput|ALput|ALpick|pick)\}\}',lambda m:m.group(1)+r'_{(i_{\rm '+m.group(2)+r'},\mathrm{'+m.group(3)+'})}',model)
# Eliminate the cycle-end alias by exact substitution.
paragraph('一个加工周期只有在前一周期结束后才能开始',r'''一个加工周期只有在前一周期结束后才能开始，持续时间由所选加工类型确定。周期结束时刻直接写为$S_{cq}+\sum_m d_mK_{cqm}$，因此，有''')
equation('eq:cycle-time-cn',r'''\begin{equation}
\begin{aligned}
S_{cq}&\ge0,\\
S_{cq}+\sum_m d_mK_{cqm}&\le B U_{cq},\\
S_{cq}&\ge S_{c,q-1}+\sum_m d_mK_{c,q-1,m}\\
&\quad-M(1-U_{cq})\qquad(q>1).
\end{aligned}
\label{eq:cycle-time-cn}
\end{equation}''')
paragraph('新装对位于前侧；保留对经旋转转到后侧',r'''新装对位于前侧；保留对经旋转转到后侧，且上一周期必须在前侧。新链首的$2\times2$产品对最后装入前侧。动作$(p,\mathrm{load})$与$(p,\mathrm{unload})$分别是PW对$p$的装入与卸出；$(c,q,\mathrm{rot-})$与$(c,q,\mathrm{rot+})$分别是该周期前、后的半周旋转，由$U_{cq}$与$\upsilon_{cq}$启用，各持续$r_c$。装载联结为''')
equation('eq:cycle-load-cn',r'''\begin{equation}
\begin{aligned}
X_{pcq}=1\ \Rightarrow\quad
&S_{cq}\ge e_{(p,\mathrm{load})},\\
&s_{(p,\mathrm{unload})}\ge S_{cq}+\sum_m d_mK_{cqm};\\
A_{pcq}=1,\ f_{pcq}=0\ \Rightarrow\quad
&e_{(p,\mathrm{load})}\le s_{(c,q,\mathrm{rot-})};\\
A_{pcq}=1,\ f_{pcq}=1\ \Rightarrow\quad
&s_{(p,\mathrm{load})}\ge e_{(c,q,\mathrm{rot-})},\\
&S_{cq}=e_{(p,\mathrm{load})};\\
\kappa_{cq}=1\ \Rightarrow\quad
&s_{(c,q,\mathrm{rot-})}\ge S_{c,q-1}\\
&\qquad+\sum_m d_mK_{c,q-1,m}.
\end{aligned}
\label{eq:cycle-load-cn}
\end{equation}''')
equation('eq:cycle-unload-cn',r'''\begin{equation}
\begin{aligned}
Z_{pcq}=1,\ f_{pcq}=1\quad
&\Rightarrow e_{(p,\mathrm{unload})}\le s_{(c,q,\mathrm{rot+})},\\
Z_{pcq}=1,\ f_{pcq}=0,\ \upsilon_{cq}=1\quad
&\Rightarrow s_{(p,\mathrm{unload})}\ge e_{(c,q,\mathrm{rot+})},\\
Z_{pcq}=1,\ f_{pcq}=0,\ \upsilon_{cq}=0\quad
&\Rightarrow s_{(p,\mathrm{unload})}\ge e_{(c,q+1,\mathrm{rot-})}.
\end{aligned}
\label{eq:cycle-unload-cn}
\end{equation}''')
# Cleaning retains every original timing inequality; only action references change.
paragraph('$s_v,e_v$是非负实数变量',r'''$o_v$是生产任务$v$的加工动作索引；$o_{ch}^{\nu}$是区段$h$后清洁任务的阶段动作索引，其中$\nu\in\{FL,BL,P,BU,FU\}$依次标识前装、后装、清洁处理、后卸与前卸。完整清洁任务从前装开始至前卸结束，各阶段直接使用对应动作的起止时刻。清洁前后关系及动作链为''')
for a,b in [(r's_v',r's_{o_v}'),(r'e_v',r'e_{o_v}')]:
 # Only within the cleaning formula, so other words and LaTeX labels are untouched.
 a0=model.index(r'\label{eq:clean-counter-cn}');b0=model.index(r'\subsection{辅助晶圆复用与机械手、模块资源}',a0)
 block=model[a0:b0].replace(a,b);model=model[:a0]+block+model[b0:]
for tag in ['FL','BL','P','BU','FU']:
 for se in ['s','e']:
  model=model.replace(se+r'^{\rm cl,'+tag+r'}_{ch}',se+r'_{o_{ch}^{'+tag+'}}')
replace(r'e^{\rm cl}_{c,h-1}',r'e_{o_{c,h-1}^{FU}}')
replace(r's^{\rm cl}_{ch}',r's_{o_{ch}^{FL}}')
# Primary objective returns use the original event end.
paragraph('$e_{pr,\\mathrm{return}}$是非负实数变量',r'''对每个位置$(p,r)$，以下$o=((p,r),\mathrm{return})$定位其返回原LP的动作，$\mathrm{return}$是回片动作标签。只对产品晶圆形成主目标下界：''')
replace(r'e_{pr,\mathrm{return}}',r'e_o')
# Statistical expressions are not extra optimization variables.
replace(r'$\mathrm{WPH}$是非负实数评价变量，表示每小时产品产出率，按$3600N/C_{\max}$计算，单位为片/小时。',r'每小时产品产出率按$\mathrm{WPH}=3600N/C_{\max}$统计，单位为片/小时。')
replace(r'$\omega_\alpha$是非负实数辅助变量，表示等待项$\alpha$的事件间隔扣除必要操作或移动时长后的余量，计算时直接使用事件时刻之差。',r'$\omega_\alpha$表示等待项$\alpha$对应的时刻差表达式，即后继动作开始时刻减去前驱动作结束时刻，再扣除必要操作或移动时长，不另设等待变量。')
replace(r'$L_{\rm sum}$是非负实数辅助变量，表示总路线等待，按$L_{\rm sum}=\sum_{\alpha\in\mathcal W}\omega_\alpha$计算。',r'总路线等待按$\sum_{\alpha\in\mathcal W}\omega_\alpha$计算，实验统计简记为$L_{\rm sum}$。')
s=s[:start]+model+s[end:]
# One dependent use in the output-completion model must follow the removed cycle-end alias.
s=s.replace(r'&C_{\mathrm{end}}\ge E_{cq}\quad(c\in\mathcal C,q\in\mathcal Q_c).',r'&C_{\mathrm{end}}\ge S_{cq}+\sum_m d_mK_{cqm}\\'+'\n'+r'&\hspace{4em}(c\in\mathcal C,q\in\mathcal Q_c).')
for forbidden in [r's^{\rm pick}',r's^{\rm ref}',r'e^{\rm ref}',r's_{ia}',r'e_{ia}',r'E_{cq}',r'E_{c,q-1}',r's_p^{\rm load}',r's^{\rm load}',r'^{\rm cl,',r'e_{pr,\mathrm{return}}',r'\chi_{pr\ell}']:
 assert forbidden not in s,forbidden
p.write_text(s,encoding='utf-8')
print('Event aliases replaced; all original cleaning constraints retained.')
