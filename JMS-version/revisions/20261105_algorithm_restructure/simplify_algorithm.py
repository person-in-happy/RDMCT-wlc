from pathlib import Path
import shutil

# Neutral descriptions of evidence replace defensive commentary, without changing data.
OUTSIDE_EDITS = {
    '该证据仅证明产品完工时间最优，不证明等待、节拍或全部动作完成时间同时最优。': '',
    '上述结果验证了批次编码、物理资源约束与具体晶圆排程之间的映射；规模性能、节拍改善及算法比较仍需在统一参数下进一步检验。':
    '上述结果验证了批次编码、物理资源约束与具体晶圆排程之间的映射。',
    '此表不据不同实例的完工时间推断模式优劣，也不将固定结构子问题最优等同于完整模型最优。': '',
    '它们是当前参数下的具体可行性见证，并非在同一预算下重新求解所得的算法比较样本。':
    '这些排程经当前参数重新核验，用于展示不同配方的具体执行过程。',
    '未通过当前参数检查的历史结果不用于本节的数值比较。': '',
    '当前证据包含一份已证最优排程及不同配方的可行性见证。更大规模的全局最优性、两种指派表示的效率差异、学习割选择的效果及两阶段精修的统计收益，仍需在相同驻留含义、时域和比较预算下完成对应实验。限时可行结果只能作为上界，未获得可行解的超时不能作为不可行性证明。':
    '上述排程包含一份已证最优结果及不同配方的可行性见证，展示了批次任务、腔室周期和具体晶圆动作之间的对应关系。',
}

def main():
    here=Path(__file__).resolve().parent
    source=here.parents[1]/'JMS_Review_CN.tex'
    s=source.read_text('utf-8')
    shutil.copy2(source,here/'before_simplification.tex')
    start=s.index('可选的初始解策略采用确定性的串行构造')
    end=s.index(r'\subsection{从初始排程到两阶段优化结果}',start)
    s=s[:start]+r'''初始排程按任务资格和批次内序号构造：先将产品划分为连续区段并分配到允许腔室，再按工艺模式组成PW对，以辅助片补齐空位；随后安排生产周期、$2\times2$连续处理链及清洁边界，沿供片、加工和回片路径，结合操作时长、机械手移动与资源释放时刻依次确定各事件的开始时间。所得排程经出片顺序、资源占用和驻留条件检查后记为$\mathcal S^0$。将其中的产品对、辅助身份、分腔、周期占位及动作时刻对应到模型变量，并补齐资源次序与逻辑辅助量，得到完整初始赋值$\xi^0=\mathsf{Enc}(\mathcal S^0)$；其中$\mathsf{Enc}$表示物理排程到模型赋值的映射。

在此起点上，结构保持二元骨架（structure-preserving binary skeleton，SPBS）以缩短$C_{\max}$为目标逐层改善排程。第一层固定主要离散选择，调整连续时刻和原子同步取放；随后依次开放VTR次序、装载锁次序和其余资源次序；最后开放周期占位、前后侧及手分配，保留PW对组成、辅助身份、分腔、库存指派和周期类型。令$t\in\{1,\ldots,5\}$为层号，$\mathcal F_t$为该层固定的离散分量索引集合，以该层起点$\widehat\xi$为参考，临时约束为
\begin{equation}
\xi_d=\widehat\xi_d\quad(d\in\mathcal F_t),\qquad
\mathcal F_1\supseteq\cdots\supseteq\mathcal F_5.
\label{eq:spbs-fix-cn}
\end{equation}
每层至多使用结构化改善预算的五分之一，并将当前最好可行赋值传给下一层。改善后的赋值经完整验证后作为第一阶段的起点；进入第一阶段时解除全部临时固定关系。初始化成本与主求解时间分别记录。

'''+s[end:]
    start=s.index(r'\paragraph{第一阶段：联合调整配对、分腔、周期与资源次序}')
    end=s.index(r'\subsection{收尾动作的时序压缩}',start)
    s=s[:start]+r'''\paragraph{第一阶段：联合调整配对、分腔、周期与资源次序}
以初始化结果为当前可行解，在第2节的完整可行域$\mathcal F$中按式~\eqref{eq:primary-objective-cn}最小化$C_{\max}$；关闭初始化时，直接搜索该可行域。搜索同时调整产品配对、合格腔室分配、周期占位、清洁位置及搬运次序，并重新协调动作时刻。各腔室的生产段通过共享VTR、装载锁与辅助片的资源约束衔接，满足工艺和驻留条件的搬运与加工可以重叠执行。每获得产品回片完工时间更短的可行排程，即更新当前最好解。第一阶段由SCIP实现\citep{achterberg2009scip,bestuzheva2023scip}，也可接入冻结的学习选割策略辅助搜索\citep{wang2023hem}。停止时，将当前最好赋值及其产品完工时间分别记为$\widehat\xi$和$\widehat C$，记录有效下界、间隙与停止状态，并将所得排程送入第二阶段。

\paragraph{第二阶段：保留主要结构并精修时序}
以$\widehat\xi$为起点，按式~\eqref{eq:secondary-domain-cn}固定配对、分腔、周期占位、辅助身份、手分配及资源次序，并将产品完工时间限定在$\widehat C+\varepsilon_C$内。调整动作开始时刻和原子同步取放选择，以式~\eqref{eq:secondary-objective-cn}协调总等待、最大单项等待与同链相邻周期开始间隔的变化。具体而言，供片动作向后续加工靠近，卸片后的回片衔接被压紧，同一链内的周期开始时刻在资源和驻留条件下重新分布。通过完整验证的改善结果替换第一阶段排程，随后进入收尾处理；各阶段分别记录目标值和实际耗时。

'''+s[end:]
    s=s.replace('上标$\\star$表示最终保留结果，不表示已证明全局最优。','上标$\\star$表示最终保留结果。')
    s=s.replace('最终排程是已找到的最好可行结果；其产品完工时间是否全局最优，应由第一阶段的界证据判定。','排程的求解状态由第一阶段的可行上界与有效下界共同确定。')
    s=s.replace('\\textbf{2. 验证并映射起点。}通过物理检查的候选记为$\\mathcal S^0$，映射并补全为$\\xi^0$，检查完整模型；检查失败则记录初始化失败，不作为可行起点。', '\\textbf{2. 映射起点。}将构造并验证的排程$\\mathcal S^0$映射为完整模型赋值$\\xi^0$。')
    s=s.replace('若无可行解，返回停止记录。','记录求解状态。')
    for a,b in OUTSIDE_EDITS.items():
        assert a in s,a
        s=s.replace(a,b)
    source.write_text(s,encoding='utf-8',newline='\n')
    print('Initial construction and assignment mapping reduced to one paragraph; defensive commentary removed.')

if __name__=='__main__':
    main()
