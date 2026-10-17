from pathlib import Path
import re, json, shutil, hashlib, difflib

HERE=Path(__file__).resolve().parent
PAPER=HERE.parents[1]
src=PAPER/'JMS_Review_CN.tex'
target=PAPER/'MODEL_EXPLANATION_CN.md'
backup=HERE/'MODEL_EXPLANATION_CN.before.md'
if not backup.exists():
    shutil.copy2(target,backup)
old=backup.read_text(encoding='utf-8')
tex=src.read_text(encoding='utf-8')
equations={}
for m in re.finditer(r'\\begin\{equation\}(.*?)\\end\{equation\}',tex,re.S):
    label=re.search(r'\\label\{([^}]+)\}',m[1])[1]
    equations[label]=re.sub(r'\\label\{[^}]+\}','',m[1]).strip()
assert len(equations)==42
numbers={label:i+1 for i,label in enumerate(equations)}
blocks={}
for m in re.finditer(r'^### 式（(\d+)）：([^\n]+)\n<!-- (eq:[^ ]+) -->',old,re.M):
    stop=re.search(r'^## |^### 式（\d+）：|^### 此后行内公式一：',old[m.end():],re.M)
    finish=m.end()+stop.start() if stop else len(old)
    blocks[m[3]]=(int(m[1]),m[2],old[m.end():finish].strip())
assert len(blocks)==38
mapping={num:numbers[label] for label,(num,_,_) in blocks.items()}
def renumber(s):
    return re.sub(r'（(\d+)）',lambda m:'（'+str(mapping[int(m[1])])+'）',s)
def terminology(s):
    for a,b in [('清洁间隔','清洁阈值'),('物料单元','晶圆路线任务'),('物料','晶圆'),
                ('辅助片','辅助晶圆'),('两次曝光','两次工艺处理'),('首次/末次曝光','首次/末次工艺处理'),
                ('曝光周期','生产周期'),('曝光区间','生产区间'),('曝光','工艺处理'),
                ('清洁前最大加工周期数','清洁前最大生产周期数'),
                ('H数的是满片加工周期','H数的是满片生产周期'),('最新403 s排程','403 s已保存排程'),
                ('最新追加验证','2026-10-13追加验证')]:
        s=s.replace(a,b)
    return s
def clean(s):
    return terminology(renumber(s))

intro=old[:old.index('## 第2节：')]
intro=intro[intro.index('## 阅读起点：'):]
intro=clean(intro)
intro=intro.replace('CH为加工腔室','CH为工艺腔室')
intro=intro.replace('本次只统一稿件数学记号，实际约束、实验配置及数值结果保持原义。',
    '本说明沿用修改后正文的数学记号，不改变实际约束、实验配置及数值结果。')
intro=intro.replace('清洁仍记', '清洁类型仍记')
opening=r'''# 稿件模型与公式逐项实例说明

更新日期：2026-10-15。依据为本次读取的中文投稿正文 [JMS_Review_CN.tex](JMS_Review_CN.tex)。本版覆盖全部42个编号公式：第2节模型31式、第3节求解方法9式、第4节评价指标2式；不推定英文稿或其他副本已同步。

每个公式按“原式、用途与量、数值代入、直观含义或反例”解释。公式从正文按标签直接提取，显示编号与修改后的正文一致。模型部分依次按物理路径、匹配关系、动作时间、工艺与清洁、实体资源、两阶段优化排列。附录按当前表1、表2顺序解释全部58行符号（28行集合与参数、30行变量）。

**统一术语。** 本文的物料均为晶圆，晶圆包括产品晶圆和辅助晶圆。工艺腔室的加工包括生产与清洁；生产指按产品配方进行的工艺处理。“加工周期”包含生产周期与清洁周期；清洁不计入生产周期。装卸、旋转与等待分别计时。

**如何使用本说明。** 先读4片产品的贯穿实例，再按正文公式号查阅。标注“实际例子”的数字来自已保存并通过验证的排程；“教学例子”仅检查正在解释的局部关系。不同教学例子不能拼接为一份已经通过全部约束验证的完整排程。所有时间单位均为秒。

## 公式导航

| 正文对应部分 | 公式 | 要回答的问题 |
|---|---|---|
| 2.1 单源与双源物理加工路径 | (1) | 产品和辅助晶圆从哪里来、怎样返回？ |
| 2.2 晶圆、PW对与腔室周期的匹配关系 | (2)-(7) | 谁与谁配对，去哪个腔室，参加哪些周期？ |
| 2.3 动作时间与先后逻辑 | (8)-(13) | 动作何时执行，哪些必须先后或同步？ |
| 2.4 两种工艺模式与清洁处理 | (14)-(20) | 工艺处理次数、旋转装卸和清洁如何衔接？ |
| 2.5 辅助晶圆复用与机械手、模块资源 | (21)-(25) | 实体晶圆、物理手和模块怎样避免冲突？ |
| 2.6 完工时间优先的两阶段优化 | (26)-(31) | 先优化什么，再在什么范围内精修？ |
| 第3节 初始化与学习增强求解 | (32)-(40) | 怎样构造起点、编码与选择割、训练策略？ |
| 第4节 实验评价 | (41)-(42) | 终止gap与全过程PDI有什么区别？ |
'''

new_sections={
'eq:secondary-domain-cn':('第二阶段保留主要结构及产品完工时间上界',r'''
**用途与量。** $\widehat\xi$是第一阶段当前最好可行解，$\widehat C$是其产品回片完工时间；$\mathcal D_{\rm fix}$列出第二阶段固定的配对、分腔、周期占位、辅助身份、物理手、随行入片选择与资源次序。$\varepsilon_C$是允许的完工时间数值容差。

**教学例子。** 第一阶段获得$\widehat C=532$，取$\varepsilon_C=10^{-6}$，则第二阶段要求$C_{\max}\le532.000001$。若原解把p1分配到CH1，且对应z属于固定集合，就施加$z_{p1,CH1}=1$；把p1改去CH2不属于本阶段允许的调整。

**可调整部分。** 指定的同地点原子取放同步选择与连续时刻仍可调整。例如在保持主要结构的条件下，将一项动作从110 s前移到105 s，只要全部路线、资源约束及完工时间上界仍成立，就可接受。531 s也满足上界，公式没有要求完工时间必须等于532 s。

**直观含义。** 先保住第一阶段已有的产品完工时间，再改善排程时序。第一阶段不必已经证明全局最优；532 s若只是当前可行上界，就不能称为完整联合问题的最优值。
'''),
'eq:secondary-wait-cn':('总等待与最大单项等待',r'''
**用途与量。** $\mathcal Q^w$是纳入评价的等待项集合；$\omega_\alpha$为必要操作或移动之外的非负等待。$L_{\rm sum}$是这些项的总和，$L_{\max}$是每一项的共同上界，后一不等式对所有$\alpha\in\mathcal Q^w$成立。

**教学例子。** VTR取片结束101 s、必要移动2 s、装片开始108 s，运输等待为$108-101-2=5$ s。另两项等待为0、10 s，则$L_{\rm sum}=5+0+10=15$，约束要求$L_{\max}\ge10$。

**反例与边界。** 取$L_{\max}=8$会违反10 s等待项的约束；取12在约束层面仍允许。只有相应正权目标取得紧值时，才能把$L_{\max}$直接读作实际最大等待10 s。并行等待的不同晶圆分别累计：两片各等5 s可贡献10 s总等待，不能只算时间轴上的5 s。

**直观含义。** 总等待衡量累计负担，最大等待关注最突出的单项延迟；二者都不能代替产品完工时间。
'''),
'eq:secondary-rhythm-cn':('相邻生产周期间隔的变化',r'''
**用途与量。** $h_{ceq}$是生产周期的开始时刻；$\Delta_{ceq}$是后一个开始间隔减去前一个间隔；非负$v_{ceq}$给出$|\Delta_{ceq}|$的上界。本式仅在$\mathcal I_h$指定的同腔、同一$2\times2$链连续三周期上使用，相邻两边界都须保留一个对。

**教学例子。** 三个生产周期在100、200、320 s开始，相邻间隔为100和120 s，故$\Delta=120-100=20$，$v\ge20$。改为100、210、320 s后，两间隔都是110 s，$\Delta=0$，$v$的最小值为0。若时刻为100、220、320 s，差分为$-20$，两条不等式仍要求$v\ge20$。

**适用范围。** 贯穿实例中CH2仅有两个生产周期，不能形成三连点，因此不生成该差分项。也不能借CH1的一次生产来凑第三点，或跨过清洁边界计算。

**直观含义。** 惩罚的是节拍间隔的变化，不是单次工艺处理时长；等间隔并不意味着间隔必须尽可能短。生产时长仍由式（15）保持为给定值。
'''),
'eq:secondary-softwait-cn':('等待超过软上限的惩罚量',r'''
**用途与量。** $\bar\omega_\alpha$为等待软上限，$\eta_\alpha$为非负超额的上界。与驻留硬约束不同，超过软上限仍可行，但会在启用相应正权重时增加目标代价。

**教学例子。** 等待10 s、软上限8 s时，$\eta\ge10-8=2$且$\eta\ge0$，最小可取2；等待5 s时，$\eta\ge-3$和$\eta\ge0$合起来使最小可取0。

**反例与边界。** 若同一物理区段还有9 s的硬驻留上限，不能通过支付2 s软超额惩罚放行10 s驻留。关闭软等待功能时不生成超额变量和对应目标项，不等于把软上限改成零。

**直观含义。** 软上限表示希望达到的水平，硬上限表示必须满足的可行条件。限时解中$\eta$可能未取紧，报告实际超额时应从事件时刻重算。
'''),
'eq:secondary-objective-cn':('将等待与节拍指标组成第二阶段目标',r'''
**用途与量。** $\Phi$按非负权重组合总等待、最大单项等待、节拍差分绝对值上界和可选软等待超额。此目标在原可行域及式（27）的范围内最小化，不能为了降低$\Phi$任意增加产品完工时间。

**教学代入。** 采用正文权重$(\lambda_1,\lambda_2,\lambda_3)=(1,10,25)$并关闭软项。若等待为5、0、10 s，唯一节拍差分为20 s，且辅助上界均取紧，则$\Phi=1\times15+10\times10+25\times20=615$。若其他量不变、节拍差分降为0，则目标为115。

**软项例子。** 在上述615的教学例子中，额外启用8 s软上限并取教学权重$\lambda_4=3$，只有10 s等待产生2 s超额，故目标变成$615+3\times2=621$。这里的3是教学权重，不声称为正式实验参数。

**直观含义。** 615是加权目标值，不是产品在615 s完工。总等待减少也不保证加权目标减少，例如最大等待显著增大时，第二项可能抵消第一项的改善。仅当对应权重为正且最小化使上界取紧时，$L_{\max},v,\eta$才等于相应实际指标；评价限时解应重算真实指标。
''')}

def make_block(label):
    number=numbers[label]
    if label in new_sections:
        title,body=new_sections[label]
    else:
        _,title,body=blocks[label]
        title=terminology(title)
        body=re.sub(r'^\$\$.*?\$\$\s*','',body,flags=re.S)
        body=clean(body)
    formula=equations[label]
    return f'### 式（{number}）：{title}\n<!-- {label} -->\n\n$$\n{formula}\n\\tag{{{number}}}\n$$\n\n'+body.strip()+'\n'

groups={1:'第2节 / 2.1 单源与双源物理加工路径',2:'第2节 / 2.2 晶圆、PW对与腔室周期的匹配关系',
8:'第2节 / 2.3 动作时间与先后逻辑',14:'第2节 / 2.4 两种工艺模式与清洁处理',
21:'第2节 / 2.5 辅助晶圆复用与机械手、模块资源',26:'第2节 / 2.6 完工时间优先的两阶段优化',
32:'第3节：初始化与学习增强求解，式（32）至（40）',41:'第4节：实验评价关系，式（41）至（42）'}
content=[opening,intro]
for label,number in numbers.items():
    if number in groups:
        content.append('## '+groups[number]+'\n')
    content.append(make_block(label))

tail=old[old.index('### 此后行内公式一：'):old.index('## 附录：')]
content.append(clean(tail))

# Definitions come directly from the current manuscript tables; examples are preserved by symbol key.
def key(s):
    return re.sub(r'\s+','',s)
old_examples={}
for line in old[old.index('## 附录：'):].splitlines():
    if line.startswith('| $'):
        cells=line.strip().strip('|').split(' | ')
        assert len(cells)==4,(len(cells),line)
        old_examples[key(cells[0].strip())]=cells[3].strip()
extra={
r'$N$':r'$N=|\mathcal W|=N_{\zeta}+N_{\psi}\in\mathbb Z_{\ge0}$。贯穿实例为4片产品、8片辅助晶圆，仍取$N=4$，不是12。',
r'$H$':r'$H\in\mathbb Z,\ H\ge2$。$H=3$时通常生产3周期后清洁；清洁后立即开始$2\times2$时允许在2周期后提前清洁。清洁自身不计数。',
r'$d_o,r_c$':r'单位s，启用动作的时长由输入给定。贯穿实例VTR取放1、ATR取放4、腔室半周旋转2；等待不并入这些时长。',
r'$P_{\max},Q_{\max}$':r'非负整数容量界。本例分别为10和6；实际启用5个PW对和两腔合计3个加工周期。候选PW对数不等于辅助晶圆库存。',
r'$\overline T,d_m$':r'单位s。$\overline T$为有效时域上界；$d_{\zeta}=180,d_{\psi}=90,d_{\mathrm{cl}}=500$。$2\times2$产品参加两次90 s生产，清洁500 s另计。'
}
extra={key(k):v for k,v in extra.items()}
appendix=['## 附录：当前表1、表2的58行符号速查\n\n以下符号、类型及定义逐行提取自当前正文；取值与示例单独补充。为便于PDF阅读，每行符号展开为一条说明。']
tables=re.findall(r'\\begin\{table\*\}.*?\\end\{table\*\}',tex,re.S)[:2]
row_counts=[]
for ti,table in enumerate(tables,1):
    rows=table.split('\\midrule\n')[1].split('\\bottomrule')[0].strip().splitlines()
    row_counts.append(len(rows))
    appendix.append(f'### 表{ti}：'+('核心集合与输入参数' if ti==1 else '核心决策变量、辅助变量与连续时间变量'))
    for ri,row in enumerate(rows,1):
        cells=row.removesuffix(r'\\').split(' & ')
        assert len(cells)==3
        symbol,kind,definition=cells
        symbol_key=key(symbol)
        example=extra.get(symbol_key)
        if example is None:
            assert symbol_key in old_examples,symbol
            example=clean(old_examples[symbol_key])
        appendix.append(f'**表{ti}-{ri:02d}　{symbol}**\n\n**类型与定义。** {kind}；{definition}\n\n**取值与例子。** {example}')
assert row_counts==[28,30]
appendix.append(clean(old[old.index('### 容易混淆的同名字母'):]))
content.append('\n\n'.join(appendix))
result='\n\n'.join(content)
# Strengthen the updated capacity and cleaning explanation without changing the source model.
anchor='**教学例子。** 若仍有这4片但H=3，则清洁上界为'
addition=r'''**三项容量逐项数。** $N=4$只数产品；含产品PW对最多4个。每个生产周期最多需要一个纯辅助补位对，按$T=6$预留6个编号。每次清洁需要两个纯辅助对，按$2J_{\max}$预留。因此$P_{\max}=N+T+2J_{\max}$数的是全批次可启用的占位任务编号，不是两台腔室各有这么多实体PW对，也不是要备这么多辅助晶圆。辅助库存8片由身份与复用约束另管。

'''
assert anchor in result
result=result.replace(anchor,addition+anchor)
result=result.replace('**直观含义。** H数的是满片生产周期',
    '**计数结论。** 两次清洁之间通常有$H$个生产周期；仅在上述提前清洁条件成立时为$H-1$个。若从一次清洁结束数到下一次清洁结束，还会包含后一次清洁本身，因此加工周期总数分别为$H+1$或$H$。两种计数口径不能混用。\n\n**直观含义。** H数的是满片生产周期')
# The old formula heading and timetable use terminology that must match the revised manuscript.
result=result.replace('首次、末次工艺处理与连续两次加工','首次、末次参与周期与连续两次生产')
result=result.replace('每个生产周期至少包含产品、每片产品最多出现1或2次','每个生产周期至少包含产品、每片产品按其配方参加1或2次工艺处理')
result=result.replace('纯辅助满片应按清洁或合法补位结构处理，不能凭空增加产品加工周期。',
    '两个纯辅助对构成的完整周期只能按清洁处理；生产补位必须与至少一个含产品对同周期出现，不能凭空增加生产周期。')
result=result.replace('A1为(0,1)', '借用A1的辅助晶圆路线任务为(0,1)')
result=result.replace('每片晶圆有一个既定来源区域', '每个晶圆路线任务有一个既定来源区域')
result=result.replace('本说明只解释当前稿件及其验证实例，不把教学数值作为新实验结果。需要重新运行实验或构建投稿包时，使用[README](README.md)中的现行命令。',
    '本说明用于阅读与核查当前稿件，教学数值不作为新实验结果。')
result=result.replace('最新','已保存的')
result+='\n\n## 来源与版本核对\n\n正文与全部42式以本轮读取的 `JMS-version/JMS_Review_CN.tex` 为准，其SHA-256前16位为 `'+hashlib.sha256(src.read_bytes()).hexdigest()[:16]+'`。下列路径均相对于 `JMS-version/`，对应已保存文件；本轮只读核查，没有重新运行优化。\n\n'
for title,path in [
    ('532 s贯穿实例','results/joint_model/structure_check_20261011_203359/matched_n4_H10_mixed_dual/scip_fixed/result.json'),
    ('532 s实例的独立验解记录','results/joint_model_validation/structure_check_20261011/audit.json'),
    ('403 s辅助身份对照','results/joint_model/auxiliary_partition_retry_20261013_103715/result.json'),
    ('403 s实例及追加验证记录','results/joint_model_validation/followup_20261013/audit.json')]:
    assert (PAPER/path).is_file()
    result+='**'+title+'。**\n\n'+r'\path{'+path+'}\n\n'
result+='两个实例的保存记录均显示物理重放有效，且对应验解记录确认完整联合模型约束成立。532 s的最优性限于原固定结构；403 s为可行上界。本轮更新未改变投稿正文、实验结果或模型代码。\n'
assert len(re.findall(r'^<!-- eq:',result,re.M))==42
assert len(re.findall(r'^### 式（\d+）：',result,re.M))==42
assert '38个编号公式' not in result and '55行' not in result
assert result.count('### 此后行内公式一：')==1
target.write_text(result,encoding='utf-8',newline='\n')
(HERE/'revision.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),result.splitlines(True),fromfile='before',tofile='after')),encoding='utf-8')
(HERE/'equation_mapping.json').write_text(json.dumps({'manuscript_sha256':hashlib.sha256(src.read_bytes()).hexdigest(),
    'equations':numbers,'old_to_new':mapping,'symbol_rows':row_counts},ensure_ascii=False,indent=2),encoding='utf-8')
print('Updated 42 formula explanations and 58 symbol entries.')
