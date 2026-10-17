from pathlib import Path
import re, json, hashlib, shutil, difflib

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
source=PAPER/'JMS_Review_CN.tex'
explanation=PAPER/'MODEL_EXPLANATION_CN.md'
for p in [source,explanation,PAPER/'JMS_Review_CN.pdf',PAPER/'output/pdf/MODEL_EXPLANATION_CN.pdf']:
    backup=HERE/(p.stem+'.before'+p.suffix)
    if not backup.exists(): shutil.copy2(p,backup)
old=(HERE/'JMS_Review_CN.before.tex').read_text(encoding='utf-8')
s=old
def replace(a,b):
    global s
    assert a in s,a[:120]
    s=s.replace(a,b)
def paragraph(start,end,text):
    global s
    a=s.index(start); b=s.index(end,a)
    s=s[:a]+text+'\n\n'+s[b:]
def equation(label,text):
    global s
    pattern=r'\\begin\{equation\}(?:(?!\\end\{equation\}).)*?\\label\{'+re.escape(label)+r'\}.*?\\end\{equation\}'
    s,n=re.subn(pattern,lambda _:r'\begin{equation}'+'\n'+text+'\n'+r'\label{'+label+'}\n'+r'\end{equation}',s,flags=re.S)
    assert n==1,label

paragraph('表~\\ref{tab:symbol-cn-a}与表~\\ref{tab:symbol-cn-b}', '\\begin{table*}',r'''表~\ref{tab:symbol-cn-a}汇总模型所需集合、输入与容量上界，表~\ref{tab:symbol-cn-b}列出核心决策、派生标记及线性化辅助量。采用统一事件时刻$s_o,e_o$：对给定时长的物理动作，$e_o=s_o+d_ob_o$可直接代入；对跨越多个动作的资源占用区间，起止时刻由对应取放事件联结，区间长度不预先固定。装卸、旋转、周期和清洁阶段的时刻仅是这些事件的索引化写法，不另设一套独立时钟。

下标$w,i,p,c,q$依次表示产品晶圆、晶圆路线任务、PW对、腔室及该腔候选加工周期；$o,o'$为动作或资源占用任务，$\alpha$为等待项。$r=0,1$在$a_{wpr},d_{pr}$中为对内成员位，在$y^r_{oo'}$中则为资源；$\ell\in\Gamma_o$为物理手或槽位。借用需求$j=(p,r)$定位一次辅助晶圆使用，$\tau$定位一片实体辅助晶圆。清洁区段$e$和生产任务$v$仅用于清洁动作窗口，均由周期序列识别。

上标或下标$\zeta,\psi,\mathrm{cl}$标记两种生产工艺与清洁，load、unload、rot$\pm$、ref、return、max标记装载、卸载、周期前后旋转、参考阶段、回片与最大值；它们不是额外的决策索引。时间单位为s，二元量取1表示所述选择成立、取0表示不成立。派生量由已有变量确定，保留其简写是为避免在多条约束中重复展开；其定义关系不增加独立决策自由度。''')

# Consolidate the two tables without losing definitions required by formulas.
tables=re.findall(r'\\begin\{table\*\}.*?\\end\{table\*\}',s,re.S)[:2]
records=[]
omit={1:{7,18,20,25},2:{8,10,14,15,16,18,19,24,26,27,30}}
overrides={
(1,6):(r'$\mathcal C$', '集合',r'$\mathcal C=\{\mathrm{CH1,CH2}\}$为工艺腔室集合，$c$为腔室编号。'),
(1,8):(r'$\mathcal Q_c$', '索引集合',r'$\mathcal Q_c=\{1,\ldots,Q_{\max}\}$为腔室$c$的候选加工周期集合，$q$为周期编号。'),
(1,26):(r'$\mathcal D_{\rm fix},\mathcal Q^w,\mathcal I_h$', '索引集合',r'$\mathcal D_{\rm fix}$为第二阶段固定分量的索引集合（索引$d$）；$\mathcal Q^w$为等待项集合（索引$\alpha$，上标$w$为等待标签）；$\mathcal I_h$为同腔、同一$2\times2$链内连续三个生产周期的中心索引$(c,q)$集合。'),
(2,1):(r'$a_{wpr},v_p;\ d_{pr}$','二元决策/派生量',r'$a_{wpr}=1$表示产品$w$占对$p$的成员位$r\in\{0,1\}$；$v_p=1$表示启用该对。$d_{pr}=v_p-\sum_w a_{wpr}$表示该位置由辅助晶圆补齐，不是额外的成员选择。'),
(2,4):(r'$K_{cqm},X_{pcq};\ U_{cq}$','二元决策/派生量',r'$K_{cqm}=1$表示腔室$c$周期$q$采用加工类型$m$；$X_{pcq}=1$表示对$p$参加该周期。$U_{cq}=\sum_mK_{cqm}\in\{0,1\}$为周期启用标记。'),
(2,7):(r'$s_o,e_o$','事件时刻',r'动作或资源占用任务$o$的开始、结束时刻（s）。固定时长动作的$e_o$由$s_o+d_ob_o$确定；占用区间端点由对应物理事件联结。'),
(2,12):(r'$S_{cq},E_{cq};\ n_{cq}$','时刻别名/计数',r'$S_{cq},E_{cq}$为腔室$c$周期$q$的加工起止事件时刻（s）；$n_{cq}\in\{0,\ldots,H\}$为该周期结束后的累计生产周期数，清洁后归零。'),
(2,13):(r'$f_{pcq};\ \kappa_{cq},\upsilon_{cq}$','二元决策/派生量',r'$f_{pcq}=1$表示对$p$位于腔室$c$周期$q$的访问前侧。$\kappa_{cq}=\sum_p(X_{pcq}-A_{pcq})$标记保留上一周期的一个对；$\upsilon_{cq}=U_{cq}-\sum_p(X_{pcq}-Z_{pcq})$标记本周期后全部退出，二者由占位及首末周期标记确定。'),
(2,17):(r'$a_{vce},q^{\rm cl}_{ce}$','区段标记',r'$a_{vce}=1$表示生产任务$v$属于腔室$c$的清洁区段$e$；$q^{\rm cl}_{ce}=1$表示该段后有清洁。二者由周期序列联结，用于表达清洁动作窗口；此处$q^{\rm cl}$是标记名，不是周期索引。'),
(2,23):(r'$C_{\max}$','非负辅助量',r'所有产品$w$回到原LP的时刻$e_{w,\mathrm{return}}$的共同上界（s）；第一阶段最小化该上界，return、max为语义标签。'),
(2,25):(r'$\omega_\alpha,L_{\max}$','等待表达式/辅助量',r'$\omega_\alpha$为等待项$\alpha$中对应事件间隔扣除必要时长后的非负余量（s），由事件时刻计算；$L_{\max}$为所有单项等待的共同上界（s）。'),
(2,28):(r'$v_{cq}$','非负线性化辅助量',r'腔室$c$内以周期$q$为中心的连续三个生产周期的节拍变化上界（s），即$|S_{c,q+1}-2S_{cq}+S_{c,q-1}|$的上界；仅对$(c,q)\in\mathcal I_h$定义。'),
}
for ti,table in enumerate(tables,1):
    a=table.index('\\midrule\n')+len('\\midrule\n'); b=table.index('\\bottomrule')
    rows=table[a:b].strip().splitlines(); revised=[]
    for ri,row in enumerate(rows,1):
        if ri in omit[ti]: continue
        symbol,kind,definition=overrides.get((ti,ri),row.removesuffix(r'\\').split(' & '))
        revised.append(' & '.join([symbol,kind,definition])+r'\\')
        records.append(dict(table=ti,old_row=ri,row=len(revised),symbol=symbol,kind=kind,definition=definition))
    new=table[:a]+'\n'.join(revised)+'\n'+table[b:]
    new=new.replace(r'\begin{table*}[t]',r'\begin{table*}[!t]')
    new=new.replace('核心决策变量、辅助变量与连续时间变量','核心决策与必要的派生、线性化量')
    s=s.replace(table,new)

replace('各动作满足','对给定时长的物理动作，结束时刻由开始时刻与启用状态确定，满足')
replace('二元量$U_{cq}$标识周期启用，$K_{cqm}$选择周期类型，',r'$K_{cqm}$选择周期类型，$U_{cq}=\sum_mK_{cqm}\in\{0,1\}$简记周期启用状态，')
replace(r'令$f_{pcq}$表示加工时位于机械手访问前侧的对，$\kappa_{cq}$表示保留上一周期的一个对，$\upsilon_{cq}$表示本周期后全部退出；三者均为二元量：',r'令二元量$f_{pcq}$选择加工时位于机械手访问前侧的对。由占位变化派生$\kappa_{cq}$和$\upsilon_{cq}$，分别标记保留上一周期的一个对和本周期后全部退出，取值均为0或1；它们无需作为独立选择：')
paragraph('清洁区段$e$由上述周期类型序列中的清洁边界导出。', '\\begin{equation}',r'''清洁区段$e$由周期类型序列中的清洁边界导出。记$\mathcal V_c$为腔室$c$的生产任务集合（一个$4\times1$批次或一个$2\times2$生产周期），$a_{vce}=1$表示任务$v$属于区段$e$，$q^{\rm cl}_{ce}=1$表示该区段后有清洁；这些标记由周期结构联结，不另作清洁次数与区段划分决策。内部段以清洁结束，末段是否清洁由式~\eqref{eq:clean-counter-cn}确定。

任务$v$的起止事件记为$s_v,e_v$。区段$e$后的完整清洁任务起止事件记为$s^{\rm cl}_{ce},e^{\rm cl}_{ce}$，阶段起止事件记为$s^{\rm cl,\nu}_{ce},e^{\rm cl,\nu}_{ce}$，其中$\nu\in\{FL,BL,P,BU,FU\}$依次表示前装、后装、清洁处理、后卸、前卸。所有符号均引用相应物理事件，完整任务从前装开始到前卸结束。清洁前后关系及动作链为''')
replace('给定解后，$x^{\\zeta}_{pcbl},x^{\\psi}_{pck}$分别记录$4\\times1$批次侧位与$2\\times2$产品对链位置，均由$X,A,Z,f$及周期类型导出。相应批次、链段与清洁区段用于解释排程与固定布局基准，不另设一套独立配对。','给定解后，$4\\times1$批次侧位、$2\\times2$产品对链位置及清洁区段均可由$X,A,Z,f$与周期类型恢复，无需再引入独立的位置变量。')
replace('每对的装卸时刻沿用其物理动作，周期前后半周旋转记为',r'对$p$的装卸起止时刻记为$s_p^{\rm load},e_p^{\rm load},s_p^{\rm unload},e_p^{\rm unload}$，均沿用对应物理动作；腔室$c$周期$q$前后半周旋转的起止时刻记为$s_{cq}^{\rm rot\pm},e_{cq}^{\rm rot\pm}$，旋转动作记为')
replace('令$C_w$为产品晶圆$w$完成下装载锁返回并回到LP的时刻，第一阶段优化目标为','直接以回片动作结束时刻$e_{w,\\mathrm{return}}$表示产品晶圆$w$回到原LP的时刻，第一阶段优化目标为')
equation('eq:primary-objective-cn',r'''C_{\max}\ge e_{w,\mathrm{return}}\ (w\in\mathcal W),\qquad
\min_{\xi\in\mathcal F}C_{\max}.''')
replace('前述约束共同定义联合可行域$\\mathcal F$。',r'前述约束共同定义联合可行域$\mathcal F$，$\xi$为其中全部保留变量构成的向量。')
replace('集合$\\mathcal D_{\\rm fix}$包含第二阶段固定的配对、',r'$\xi_d$为向量的第$d$个分量，带帽量在第二阶段作为常量。集合$\mathcal D_{\rm fix}$包含第二阶段固定的配对、')
replace('$L_{\\rm sum}$累计这些等待，$L_{\\max}$为其最大值的上界；并行发生的不同晶圆等待分别计入。',r'总等待直接以$\sum_\alpha\omega_\alpha$计入目标，$L_{\max}$为最大单项等待的上界；并行发生的不同晶圆等待分别计入。$\omega_\alpha$是事件时刻的差分表达式，不再增加独立等待决策。')
replace('总等待直接以$\\sum_\\alpha\\omega_\\alpha$计入目标，',r'总等待直接以$\sum_\alpha\omega_\alpha$计入目标，实验表中的$L_{\rm sum}$仅为该求和结果的统计简写，不是独立变量；')
equation('eq:secondary-wait-cn',r'L_{\max}\ge\omega_\alpha\ge0,\qquad \alpha\in\mathcal Q^w.')
paragraph('对腔室$c$，清洁区段$e$表示相邻清洁之间的生产段，','\\begin{equation}',r'''节拍项直接使用周期开始时刻$S_{cq}$。集合$\mathcal I_h$包含同一腔室、同一$2\times2$链内连续三个生产周期的中心索引$(c,q)$，相邻两处边界均保留一个对，即$\kappa_{cq}=\kappa_{c,q+1}=1$，不跨清洁或链边界计算。第二阶段固定周期结构后，该集合随之确定。后一个开始间隔减去前一个间隔为$S_{c,q+1}-2S_{cq}+S_{c,q-1}$，以非负辅助量$v_{cq}$线性表示其绝对值上界，无需再引入区段时钟或差分变量：''')
equation('eq:secondary-rhythm-cn',r'''\begin{aligned}
v_{cq}&\ge S_{c,q+1}-2S_{cq}+S_{c,q-1},\\
v_{cq}&\ge-S_{c,q+1}+2S_{cq}-S_{c,q-1}
\quad((c,q)\in\mathcal I_h).
\end{aligned}''')
equation('eq:secondary-objective-cn',r'''\begin{aligned}
\min\ \ &\lambda_1\sum_{\alpha\in\mathcal Q^w}\omega_\alpha+\lambda_2L_{\max}\\
&+\lambda_3\sum_{(c,q)\in\mathcal I_h}v_{cq}
+\lambda_4\sum_{\alpha\in\mathcal Q^w}\eta_\alpha.
\end{aligned}''')
replace(r'$v_{ceq}=|\Delta_{ceq}|$',r'$v_{cq}=|S_{c,q+1}-2S_{cq}+S_{c,q-1}|$')
# Explain retained auxiliary variables rather than replacing linear constraints with products.
replace('因此，生产周期至少含一个产品对，',r'$B_p,B_p^{\psi},X^P_{pcq}$以及下文的$A^{\psi}_{pcq},Z^{\psi}_{pcq}$均为逻辑联结辅助量。给定成员、模式和占位后其取值确定，仍保留线性约束以避免直接使用二元变量乘积。因此，生产周期至少含一个产品对，')
replace(r'表~\ref{tab:joint-search-cn}列出共同初始解下获得的可行完工时间，按最后一片产品实际返回原LP的时刻计算。',r'共同初始解对照中的可行完工时间统一按最后一片产品实际返回原LP的时刻计算。')
replace(r'原同初始解算法对照仍按表~\ref{tab:joint-search-cn}评价。',r'原同初始解算法对照仍按上述共同初始解及300~s总求解预算评价。')

geteq=lambda text:re.findall(r'\\begin\{equation\}.*?\\end\{equation\}',text,re.S)
assert len(geteq(s))==len(geteq(old))==42
assert re.findall(r'\\label\{[^}]+\}',s)==re.findall(r'\\label\{[^}]+\}',old)
source.write_text(s,encoding='utf-8',newline='\n')

md=(HERE/'MODEL_EXPLANATION_CN.before.md').read_text(encoding='utf-8')
oldmd=md
eqdict={re.search(r'\\label\{([^}]+)\}',e)[1]:re.sub(r'\\label\{[^}]+\}','',e[len(r'\begin{equation}'):-len(r'\end{equation}')]).strip() for e in geteq(s)}
def sync_formula(m):
    label=m[1]; number=int(re.search(r'\\tag\{(\d+)\}',m[2])[1])
    return '<!-- '+label+' -->\n$$\n'+eqdict[label]+f'\n\\tag{{{number}}}\n$$'
md=re.sub(r'<!-- (eq:[^ ]+) -->\s*\$\$(.*?)\$\$',sync_formula,md,flags=re.S)
# Rebuild the appendix from retained table entries, keeping actual examples for each.
entries={}
for m in re.finditer(r'\*\*表([12])-(\d+)[^\n]+\*\*\n(.*?)(?=\n\*\*表[12]-|\n### |\n## |\Z)',oldmd,re.S):
    example=m[3].split('**取值与例子。**',1)[1].strip()
    entries[int(m[1]),int(m[2])]=example
appendix='## 附录：精简后的符号表逐项速查\n\n表中保留核心决策和必要辅助量；事件时刻别名、阶段标签在对应公式处解释。每条仍说明下标及一个数值例子。\n\n'
for ti in (1,2):
    appendix+=f'### 表{ti}\n\n'
    for rec in [r for r in records if r['table']==ti]:
        example=entries[ti,rec['old_row']]
        if (ti,rec['old_row'])==(1,6): example=r'$c\in\{\mathrm{CH1,CH2}\}$；CH1与CH2是两个腔室编号。'
        if (ti,rec['old_row'])==(1,8): example=r'若$Q_{\max}=6$，每腔预留$q=1,\ldots,6$；实际未启用的周期标记为0。'
        if (ti,rec['old_row'])==(1,26): example=r'若CH2同一链连续生产周期为1、2、3，则节拍集合含$(\mathrm{CH2},2)$；仅有两个周期时不生成节拍项。'
        if (ti,rec['old_row'])==(2,17): example=r'$a_{v,CH2,1}=1$表示任务$v$在CH2首个生产段；该段后无清洁时$q^{\rm cl}_{CH2,1}=0$。'
        if (ti,rec['old_row'])==(2,28): example=r'开始时刻为100、200、320 s时，两个间隔为100、120 s，故$v_{cq}\ge20$；取$v_{cq}=15$不可行。'
        appendix+=f'**表{ti}-{rec["row"]:02d}　{rec["symbol"]}**\n\n**类型与定义。** {rec["kind"]}；{rec["definition"]}\n\n**取值与例子。** {example}\n\n'
a=md.index('## 附录：'); b=md.index('## 来源与版本核对',a)
md=md[:a]+appendix+md[b:]
# Update explanatory prose for eliminated notation; do not retain stale definitions.
md=md.replace('$C_w$是产品w的回片结束时刻，$C_{\\max}$不小于所有$C_w$',r'$e_{w,\mathrm{return}}$是产品w的回片结束时刻，$C_{\max}$不小于所有产品的该时刻')
md=md.replace('$L_{\\rm sum}$是这些项的总和，','总等待直接在目标中求和，')
md=md.replace('$L_{\\rm sum}=5+0+10=15$',r'$\sum_\alpha\omega_\alpha=5+0+10=15$')
md=md.replace('；它不同于加工开始时刻$h_{ceq}$','；周期开始时刻统一使用$S_{cq}$')
md=re.sub(r'\*\*用途与量。\*\* \$h_\{ceq\}.*?\n',lambda _:r'**用途与量。** $S_{cq}$沿用周期开始时刻；非负$v_{cq}$给出二阶时间差$|S_{c,q+1}-2S_{cq}+S_{c,q-1}|$的上界。本式仅在$\mathcal I_h$指定的同腔、同一$2\times2$链连续三周期上使用。'+'\n',md)
md=md.replace(r'$C_w,C_{\max}\in\mathbb R_{\ge0}$',r'$C_{\max}\in\mathbb R_{\ge0}$')
md=md.replace(r'$C_w$',r'$e_{w,\mathrm{return}}$').replace(r'$C_{W3}$',r'$e_{W3,\mathrm{return}}$')
md=md.replace(r'C_{W3}',r'e_{W3,\mathrm{return}}')
md=md.replace(r'$a^{\zeta}_{cbe},a^{\psi}_{cqe}\in\{0,1\}$',r'$a_{vce}\in\{0,1\}$')
md=md.replace('分别记录4×1批次和2×2工艺处理属于哪个清洁区段；不是产品成员量', '记录生产任务$v$属于腔室$c$的哪个清洁区段$e$；不是产品成员量')
md=md.replace(r'v_{ceq}',r'v_{cq}').replace(r'(c,e,q)',r'(c,q)')
md=md.replace(r'$\Phi$', '第二阶段目标值')
md=md.replace(r'$\Phi=',r'$')
md=re.sub(r'^\| 含产品模式集合 .*?\n', '', md, flags=re.M)
md=re.sub(r'^\| 批次/链位置量 .*?\n', '', md, flags=re.M)
md=md.replace('全部58行符号（28行集合与参数、30行变量）',f'全部{len(records)}行符号（{sum(r["table"]==1 for r in records)}行集合与参数、{sum(r["table"]==2 for r in records)}行决策与辅助量）')
# Replace the old generalized index paragraphs, which listed removed reporting indices.
a=md.index('下标按所指对象解释：'); b=md.index('**成员变量的完整读法。**',a)
md=md[:a]+r'''下标$w,i,p,c,q$分别为产品晶圆、路线任务、PW对、腔室、加工周期；$r=0,1$在成员变量中为对内位置，在资源次序变量中为资源；$\ell$为物理手或槽位，$j=(p,r)$为一次辅助借用，$\tau$为实体辅助晶圆。时间单位为s，二元量取1表示相应选择成立。

本次精简直接代入产品回片时刻、总等待和节拍二阶时间差，移除仅用于结果记录的位置符号。$d_{pr}$、$U_{cq}$、$\kappa_{cq}$、$\upsilon_{cq}$是由其他量确定的简写。逻辑“与”、最大值和绝对值仍保留线性化辅助量，避免把MILP改写成非线性模型。装卸与清洁阶段时刻均引用原物理事件，不形成新的独立时钟。

'''+md[b:]
sha=hashlib.sha256(source.read_bytes()).hexdigest()
md=re.sub(r'(SHA-256前16位为 `)[^`]+`',lambda m:m[1]+sha[:16]+'`',md)
md=md.replace('本轮同步补充投稿正文与本说明的符号、下标释义，公式、实验结果与模型代码未改变。','本轮同步精简正文符号与本说明，等式定义通过直接代入消去；保留42个公式编号。实验结果与求解代码未改变，本文稿精简不代表重新运行实验。')
explanation.write_text(md,encoding='utf-8',newline='\n')
numbers={re.search(r'\\label\{([^}]+)\}',e)[1]:i+1 for i,e in enumerate(geteq(s))}
(HERE/'equation_mapping.json').write_text(json.dumps({'manuscript_sha256':sha,'equations':numbers,'symbol_rows':[sum(r['table']==i for r in records) for i in (1,2)]},indent=2),encoding='utf-8')
(HERE/'symbol_definitions.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
(HERE/'revision.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='before',tofile='after')),encoding='utf-8')
print(json.dumps({'symbol_rows':[sum(r['table']==i for r in records) for i in (1,2)],'formulas':42,'sha256':sha}))
