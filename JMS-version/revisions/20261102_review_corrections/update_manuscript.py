from pathlib import Path
import difflib
import shutil

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
backup = HERE / 'original'
backup.mkdir(parents=True, exist_ok=True)
for name in ('JMS_Review_CN.tex', 'JMS_Review_CN.pdf'):
    if not (backup / name).exists():
        shutil.copy2(PAPER / name, backup / name)
old = (backup / 'JMS_Review_CN.tex').read_text('utf-8')
text = old


def change(a, b):
    global text
    assert text.count(a) == 1, a[:100]
    text = text.replace(a, b)


change(r'相同严格出片规则下，六种实例的逐片与库存表示获得一致的产品完工时间，库存表示的建模及起点检查耗时降低9.26\%--14.98\%。',
       '相同严格出片规则下，六种实例的库存表示压缩了身份选择与条件时刻联结，所得产品完工时间与逐片表示一致。')
change('Sun等报告了不同腔室工艺时长的差异，并利用设备数据分析定位导致吞吐率损失的\n步骤',
       'Sun等介绍了智能设备数据分析工具在半导体制造质量、效率与生产率改进中的\n应用')
change('建模、初始赋值准备和求解时间分别记录。成员表示对照另外汇总建模与起点检查的合计耗时，包含模型生成、公共赋值映射与可行性检查；历史SPBS起点构造和求解后完整模型复核分别记录。',
       '建模、初始赋值准备和求解时间分别记录。成员表示对照采用完整模型的变量数、约束数、非零元和进程内存评价表示规模；历史SPBS起点构造和求解后完整模型复核分别记录。')
change(r'表~\ref{tab:representation-cn}列出预处理前的完整模型规模与三个种子的平均开销，峰值内存取建模和求解阶段的进程RSS，完整模型回填复核的耗时与内存另计。',
       r'表~\ref{tab:representation-cn}列出预处理前的完整模型规模与三个种子的平均进程峰值内存。峰值内存取建模和求解阶段的进程RSS，完整模型回填复核的耗时与内存另计。')
start = text.index(r'\begin{table*}', text.index(r'\subsection{相同出片规则下的成员表示对照}'))
end = text.index(r'\end{table*}', start) + len(r'\end{table*}')
table = text[start:end].replace('{llrrrrrrr}', '{llrrrrrr}')
lines = []
for line in table.splitlines():
    if line.count('&') == 8:
        cols = line.split('&')
        line = '&'.join(cols[:6] + cols[7:])
    lines.append(line)
text = text[:start] + '\n'.join(lines).replace('准备耗时包含建模、起点映射与检查。', '') + text[end:]
change(r'六种实例的总变量数减少0.01\%--0.22\%，约束矩阵非零元减少0.05\%--12.81\%，建模及起点检查耗时减少9.26\%--14.98\%。',
       r'六种实例的总变量数减少0.01\%--0.22\%，约束矩阵非零元减少0.05\%--12.81\%。')
change('较小的成员选择块与更简洁的联结表达式使相同物理排程的模型准备更快；求解阶段的资源占用按实例列于表中。',
       '库存表示通过较小的成员选择块和更简洁的联结表达式承载相同物理排程，求解阶段的资源占用按实例列于表中。')
anchor = r'8片纯$2\times2$的原目标消融包括'
flow = r'''为同时评价供回衔接与腔内占用，进一步统计产品流经时间，即从首次LP取片开始至返回原LP结束的时长。表~\ref{tab:product-flow-cn}分解8片、$H=3$混合实例的阶段内变化。单源排程将部分供回等待移至腔内，产品路线等待减少534~s、腔内驻留增加416~s，产品流经时间总和减少118~s；双源排程的腔内驻留保持不变，产品流经时间总和减少836~s。两者的产品完工时间上界均保持，体现了供片时刻与设备内各区段时序的协调。

\begin{table*}[t]
\centering\small
\caption{8片、$H=3$混合实例的产品时间分解（阶段一$\to$阶段二）}
\label{tab:product-flow-cn}
\begin{tabular}{lrrrr}\toprule
来源 & 路线等待总和/s & 腔内驻留总和/s & 产品流经时间总和/s & 流经时间降幅(\%)\\\midrule
单源 & $1014\to480$ & $3252\to3668$ & $5194\to5076$ & 2.27\\
双源 & $1330\to494$ & $1536\to1536$ & $3794\to2958$ & 22.03\\
\bottomrule\end{tabular}
\par\smallskip\footnotesize 每行三个种子的均值；仅统计产品晶圆。腔内驻留从装片结束至卸片开始计，包含工艺处理；流经时间从首次LP取片开始至原LP回片结束计。各产品时长分别求和。
\end{table*}

'''
change(anchor, flow + anchor)
start = text.index(r'\begin{tabular}', text.index(r'\label{tab:completion-cn}'))
end = text.index(r'\end{tabular}', start) + len(r'\end{tabular}')
text = text[:start] + r'''\begin{tabular}{lrrr}\toprule
实例 & $C_{\max}$ & $C_{\mathrm{end}}$ & 回片后尾部\\\midrule
4片，$H=3$ & 1491 & 2457 & 966\\
8片，$H=3$ & 3933 & 4899 & 966\\
8片，资格异构 & 4707 & 5725 & 1018\\
\bottomrule\end{tabular}''' + text[end:]
change('单源排程收尾前后的完整完工时间（s）', '单源排程收尾后的完成边界（s）')
change(r'每行三个种子的均值，收尾前后$C_{\max}$相同。$C_{\mathrm{end}}$覆盖全部动作和装载锁复位；各等待与节拍分量由新事件分别计算。',
       r'每行三个种子的均值，收尾前后$C_{\max}$相同。$C_{\mathrm{end}}$覆盖全部动作和装载锁复位；回片后尾部为$C_{\mathrm{end}}-C_{\max}$。各等待与节拍分量由新事件分别计算。')
change(r'表~\ref{tab:completion-cn}中的4片和8片单源实例分别将全部动作完工时间由100018~s降至2457~s和4899~s，同时保持1491~s和3933~s的产品完工时间；路线等待仍分别为840~s和1680~s。资格单源实例的全部动作完工时间由14985~s降至5725~s。',
       r'表~\ref{tab:completion-cn}中的4片和8片单源实例在产品回片后均以966~s完成已安排的末端工作，全部动作完工时间分别为2457~s和4899~s，产品完工时间保持1491~s和3933~s；路线等待仍分别为840~s和1680~s。资格单源实例的全部动作完工时间为5725~s，产品回片后的尾部为1018~s。')
change(r'库存表示的建模及起点检查耗时减少9.26\%--14.98\%，并减少身份选择列与条件时刻联结。',
       r'库存表示减少身份选择列与条件时刻联结，使约束矩阵非零元减少0.05\%--12.81\%。')
change('固定结构内的等待与节拍评价由此形成了可量化的工序衔接改进与时序权衡。',
       r'8片、$H=3$混合实例的单源和双源产品流经时间总和分别减少2.27\%和22.03\%。固定结构内的路线等待、腔内驻留与节拍评价由此形成了可量化的工序衔接改进与时序权衡。')
assert '9.26' not in text and '14.98' not in text
assert not any(t in text for t in ('匿名', '模型4', '模型2'))
(PAPER / 'JMS_Review_CN.tex').write_text(text, 'utf-8')
(HERE / 'manuscript.patch').write_text(''.join(difflib.unified_diff(old.splitlines(True), text.splitlines(True), fromfile='original/JMS_Review_CN.tex', tofile='JMS-version/JMS_Review_CN.tex')), 'utf-8')
print('Manuscript updated; source backup and diff saved.')
