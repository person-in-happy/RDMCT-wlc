# -*- coding: utf-8 -*-

import os
import re
import struct
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from path_utils import append_date_to_filename


ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "template_patent.docx"
ASSET_DIR = ROOT / "patent_assets"
OUTPUT = ROOT / "docs" / append_date_to_filename("patent_final.docx")
FALLBACK_OUTPUT = ROOT / "docs" / append_date_to_filename("patent_final_updated.docx")


TITLE = "一种面向双源混流旋转腔组合设备调度的结构感知混合整数规划层次强化学习束搜索求解方法"
KEYWORDS_CN = "组合设备，双源混流，旋转腔，混合整数规划，结构感知割选择，层次强化学习，束搜索"
KEYWORDS_EN = (
    "cluster tools, dual-source mixed flow, rotary chamber, mixed integer programming, "
    "structure-aware cut selection, hierarchical reinforcement learning, beam search"
)

ABSTRACT = (
    "本发明公开了一种面向双源混流旋转腔组合设备调度的结构感知混合整数规划层次强化学习束搜索求解方法。"
    "首先，针对含产品晶圆流和 PEC wafer 流的双源混流旋转腔设备，建立能够完整表达专用 4x1 模式和专用 2x2 模式的精确混合整数规划模型，"
    "其中 4x1 模式用于四工位满载一次加工，2x2 模式用于在 PEC 边界辅助下使产品晶圆完成两次加工。"
    "随后，将所述混合整数规划模型加载至分支定界求解器，在分离阶段提取候选割特征；"
    "在通用 cut 几何统计量之外，进一步构造与路径划分、4x1 分配、2x2 分配、时序和完工变量族相关的结构感知特征。"
    "在此基础上，构建包含高层割比例策略和低层割序列策略的层次强化学习模型，并设计 family-aware 的 cut 修复与重排机制，"
    "依据结构变量族配额和 cut 多样性对低层输出进行后处理。"
    "推理阶段采用束搜索对候选割序列进行多路径扩展与择优保留，再将目标割序列反馈给求解器继续分支定界。"
    "与现有技术相比，本发明在保持复杂工艺约束严格可行的基础上，提高了大规模双源混流旋转腔调度混合整数规划问题的求解效率、稳定性和最终解质量。"
)

CLAIMS = """
1. 一种面向双源混流旋转腔组合设备调度的结构感知混合整数规划层次强化学习束搜索求解方法，其特征在于，包括如下步骤：
建立双源混流旋转腔组合设备的混合整数规划模型，所述混合整数规划模型至少描述产品晶圆流、PEC wafer 流、4x1 加工模式、2x2 加工模式、资源容量约束、时间连续性约束以及目标完工时间约束；
将所述混合整数规划模型加载至分支定界求解器，在求解器分离阶段获取候选割集合；
针对所述候选割集合提取候选割的通用几何特征和结构感知特征，并将所述特征输入层次强化学习策略；
由高层策略输出当前分离阶段的割选择比例，由低层策略输出候选割的有序选择序列；
依据不同结构变量族的配额与多样性，对低层输出的候选割序列进行修复与重排，得到结构感知目标割序列；
在推理阶段采用束搜索对低层策略输出进行多路径扩展与保留，输出最终割序列；
将所述最终割序列反馈至所述分支定界求解器，用于当前节点的候选割筛选与排序；
继续执行分支定界求解，输出求解状态、目标值、变量取值和求解时间。

2. 根据权利要求1所述的方法，其特征在于，所述双源混流旋转腔组合设备包括两个并行旋转工艺模块，其中第一旋转工艺模块为 4x1 专用模块，第二旋转工艺模块为 2x2 专用模块；所述 4x1 模式表示四个工艺位全部放满后统一加工一次并统一取出，所述 2x2 模式表示在前导 PEC wafer 和尾部 PEC wafer 作用下，使每片产品晶圆完成两次加工而首尾 PEC wafer 各完成一次加工。

3. 根据权利要求1所述的方法，其特征在于，所述混合整数规划模型中将产品晶圆按产品对进行抽象，并建立如下变量中的至少一种：产品对路由变量、产品对到 4x1 槽位的分配变量、产品对到 2x2 有序位置的分配变量、2x2 加工周期激活变量、槽位开始时间变量、槽位结束时间变量、加工周期开始时间变量、加工周期结束时间变量、产品对完工时间变量以及系统最大完工时间变量。

4. 根据权利要求3所述的方法，其特征在于，所述混合整数规划模型包括如下约束中的至少一种：每个产品对仅能选择 4x1 路径或 2x2 路径中的一种；每个被使用的 4x1 槽位恰好容纳两个产品对；进入 2x2 模式的产品对形成前缀有序队列；根据 2x2 有序队列自动激活相应数量的加工周期；在 2x2 模式下仅首周期和尾周期使用 PEC 边界；相邻槽位或相邻加工周期满足传输间隔和工艺持续时间约束；系统最大完工时间不小于任一产品对的完工时间。

5. 根据权利要求1所述的方法，其特征在于，所述结构感知特征至少包括以下信息中的一种或多种：候选割在路径变量族上的参与比例、候选割在 4x1 分配变量族上的参与比例、候选割在 2x2 分配变量族上的参与比例、候选割在时序变量族上的参与比例、候选割在完工变量族上的参与比例、候选割在其他变量族上的参与比例、二进制变量占比、连续变量占比、主导变量族占比以及变量族熵。

6. 根据权利要求1所述的方法，其特征在于，所述层次强化学习策略包括：高层比例策略网络，用于根据候选割特征集合输出割选择比例；低层序列策略网络，用于根据候选割特征输出候选割索引序列；其中，所述低层序列策略网络为指针网络、带结束标记的指针网络、Transformer 序列网络或其它能够输出有序候选割序列的神经网络。

7. 根据权利要求1所述的方法，其特征在于，在得到低层策略输出的候选割序列后，进一步构造 family-aware 的 cut 修复与重排机制，根据不同结构变量族在候选割中的统计占比生成变量族配额，并结合 cut 之间的冗余度对割序列进行重排，以提升路径、装载、时序和完工相关结构瓶颈的覆盖能力。

8. 根据权利要求1所述的方法，其特征在于，所述束搜索至少包括如下步骤：以候选割的初始选择状态构造初始束集合；基于低层序列策略网络对每个部分序列扩展多个候选割索引；根据路径累计概率或累计评分对扩展后的部分序列进行排序；仅保留前 k 个评分最高的部分序列；在输出结束标记或达到最大解码长度后，选择评分最高的完整序列作为目标割序列。

9. 根据权利要求1所述的方法，其特征在于，在将目标割序列反馈至分支定界求解器之前，还包括对低层策略或束搜索结果进行合法性过滤，所述合法性过滤至少包括：去除重复索引、去除越界索引、识别结束标记，并将未被选中的候选割按原顺序补充在目标割序列尾部。

10. 一种面向双源混流旋转腔组合设备调度的求解系统，其特征在于，包括：混合整数规划建模模块、候选割特征提取模块、结构感知特征构造模块、高层策略模块、低层策略模块、family-aware 重排模块、束搜索模块以及求解器交互模块；所述求解器交互模块用于将目标割序列反馈至分支定界求解器并输出调度求解结果。

11. 一种电子设备，其特征在于，包括存储器和处理器，所述存储器中存储有计算机程序，所述处理器执行所述计算机程序时实现权利要求1至9任一项所述的方法。

12. 一种计算机可读存储介质，其上存储有计算机程序，其特征在于，所述计算机程序被处理器执行时实现权利要求1至9任一项所述的方法。
""".strip()

FULL_SPEC = """
1、相关技术背景（背景技术）

1.1 背景技术
半导体制造过程中，组合设备（Cluster Tools，CT）广泛用于多道真空工艺的连续加工。典型组合设备由若干加工模块（Process Module，PM）、负载锁（Load Lock，LL）、机械手、校准模块以及必要的缓存模块构成。随着制程复杂度增加，单一传统 PM 在设备占地、工艺种类和吞吐率方面逐渐难以满足高端制造需求，因此出现了在单一腔体内部集成多个工艺位并通过内部旋转机构完成多步加工的旋转腔设备。

对于带四个工艺位的旋转腔，在部分等离子工艺中，为避免空腔加工损伤腔底或夹具，旋转腔在执行工艺时要求四个工艺位均被晶圆占满。为此，实际设备中常引入 PEC storage 模块，用 PEC wafer 对产品晶圆不足的工位进行补位。这样，系统中同时存在两类流：产品晶圆流和 PEC wafer 流。两类晶圆在形成批次进入旋转腔时发生合流，在加工完成后又分别回到不同的后继路径，形成双源混流调度问题。

在本发明所针对的设备中，两个并行四腔旋转 PM 分别执行两类加工模式：其一为 4x1 模式，即四个工艺位全部放满，统一加工一次，再全部取出；其二为 2x2 模式，即先以 PEC wafer 形成前导边界，再使前一产品对与后一产品对在相邻周期中交叉加工，从而保证每片产品晶圆完成两次加工，而首尾 PEC wafer 仅加工一次。

该问题同时受到批次组成约束、PEC wafer 数量与边界使用约束、旋转腔内部同步加工与顺序旋转约束、资源互斥与时间连续性约束以及大规模混合整数规划求解效率约束的共同影响。现有研究中，常采用 Petri 网或混合整数规划（MIP）来描述组合设备调度逻辑；在求解层面，则大量依赖商业或开源求解器的默认分支定界与割平面策略。对于具有严格物理规则的双源混流旋转腔问题，仅靠默认求解器往往难以在大规模实例上稳定获得高质量解。

1.2 与本发明相关的现有技术一

1.2.1 现有技术一的技术方案
现有技术一通常采用传统混合整数规划方法对旋转腔或组合设备调度问题进行建模，并调用标准求解器进行分支定界求解。其典型流程为：建立批次分配变量、时间变量和资源顺序变量；通过线性约束描述工艺顺序、容量限制、驻留时间和资源互斥；将 MIP 模型输入求解器，由求解器使用默认的割平面选择、节点选择和启发式策略完成求解。

1.2.2 现有技术一的缺点
与本发明相比，该类现有技术至少存在以下缺点：默认割选择策略不针对双源混流旋转腔问题的结构特征，无法充分利用该类 MIP 中的约束语义；在大规模实例中，求解器在根节点和后续节点产生大量候选割，但默认策略无法高效判别哪些割更有利于收紧路径、装载、时序与完工相关的关键结构；对于 2x2 模式中的“产品晶圆两次加工、首尾 PEC 一次加工”的特殊工艺，默认求解器在搜索层面缺乏问题特定的加速机制。

1.2.3 现有技术一的出处
已公开文献中的技术。可参考与带旋转腔组合设备调度、Cluster Tool 调度及多工艺位模块调度相关的公开论文，例如《Scheduling of Multi-Finger-Robotic Cluster Tools with Multi-Space Process Modules》等。

1.3 与本发明相关的现有技术二

1.3.1 现有技术二的技术方案
现有技术二主要是 Learning to Cut 类方法，即使用神经网络或强化学习对通用 MIP 求解中的割选择进行学习。典型方案为：在求解器分离阶段抽取候选割特征；使用策略网络对候选割进行打分或排序；在训练阶段通过强化学习更新网络参数；在测试阶段使用贪心策略或简单采样策略输出割序列。

1.3.2 现有技术二的缺点
与本发明相比，该类现有技术至少存在以下缺点：一是侧重通用 MILP，不结合双源混流旋转腔设备的物理语义与精确调度模型；二是多数方法仅使用通用 cut 几何统计量，没有显式表达候选割作用于哪类调度变量族；三是缺少依据变量族配额和 cut 多样性进行 family-aware 修复与重排的机制；四是测试阶段常采用单一路径贪心解码，策略稳定性不足。

1.3.3 现有技术二的出处
已公开文献中的技术。可参考《Learning Cut Selection for Mixed-Integer Linear Programming via Hierarchical Sequence Model》，International Conference on Learning Representations，2023。

2、本发明技术方案的详细阐述（发明内容）

2.1 本发明所要解决的技术问题（发明目的）
本发明旨在解决以下技术问题：
（1）如何针对双源混流旋转腔组合设备，建立能够完整表达 4x1 与 2x2 两种加工模式的精确 MIP 模型；
（2）如何在保证 MIP 严格可行性的基础上，提高大规模调度实例的求解速度和最终解质量；
（3）如何针对求解器分离阶段的大量候选割，构造一种适配调度 MIP 的结构感知学习式割选择方法；
（4）如何在层次强化学习的基础上进一步结合 family-aware 重排与束搜索提升测试阶段稳定性。

2.2 本发明提供的完整技术方案（发明方案）

2.2.1 步骤一：建立双源混流旋转腔组合设备的精确 MIP 模型
本发明首先建立面向双源混流旋转腔设备的精确 MIP 模型。将设备建模为包含两个并行旋转 PM 的组合设备：4x1 专用 PM 和 2x2 专用 PM。将产品晶圆按两片为一对进行抽象，定义产品对集合 J；对 4x1 路径定义槽位集合 F；对 2x2 路径定义有序位置集合 R 及其对应加工周期集合 C。

建立如下变量：产品对路由变量、产品对到 4x1 槽位的分配变量、产品对到 2x2 有序位置的分配变量、4x1 槽位使用变量、2x2 位置使用变量、2x2 周期激活变量、4x1 槽位开始与结束时间变量、2x2 周期开始与结束时间变量、产品对完工时间变量以及系统最大完工时间变量。

以系统最大完工时间最小为目标，即最小化 c_max，且 c_max 不小于任一产品对的完工时间。模型包括如下关键约束：每个产品对仅能选择 4x1 路径或 2x2 路径中的一种；每个被使用的 4x1 槽位必须恰好容纳两个产品对；进入 2x2 模式的产品对形成前缀有序队列；根据 2x2 有序队列自动激活相应数量的加工周期；在 2x2 模式下仅首周期和尾周期使用 PEC 边界，以保证产品晶圆完成两次加工而首尾 PEC 仅加工一次；相邻槽位或相邻加工周期满足传输间隔和工艺持续时间约束；系统最大完工时间不小于任一产品对的完工时间。

2.2.2 步骤二：将 MIP 模型加载至分支定界求解器并构造候选割特征
本发明将上述 MIP 模型加载至求解器，优选使用 SCIP 或兼容的分支定界求解器。在求解器执行分离阶段时，会产生候选割集合。针对每个候选割，提取候选割特征。

候选割特征包括两部分。第一部分为通用 cut 几何特征，至少包括目标平行性、割有效性、支撑度、整数变量支撑度、归一化违反度、割系数均值、割系数最大值、割系数最小值、割系数标准差、目标函数系数均值、目标函数系数最大值、目标函数系数最小值以及目标函数系数标准差。第二部分为结构感知特征，至少包括候选割在路径变量族、4x1 分配变量族、2x2 分配变量族、时序变量族、完工变量族以及其他变量族上的参与比例，以及二进制变量占比、连续变量占比、主导变量族占比和变量族熵。

通过上述结构感知特征，候选割不再仅以一般 LP 几何量来表征，而能够显式反映其主要作用于调度模型中的哪类结构瓶颈。

2.2.3 步骤三：构建层次强化学习割选择策略
为了同时决定“选择多少割”和“具体选择哪些割”，本发明采用层次强化学习策略。高层策略网络根据候选割特征集合输出一个割选择比例，用于决定本轮保留的候选割数量。低层策略采用指针网络或等价的序列策略网络，对候选割序列进行有序选择，输出一个割索引序列。优选地，低层策略支持结束标记 end token，当输出结束标记时表示当前轮割选择结束。

与现有方法不同的是，本发明在策略输入前增加了结构感知输入适配模块，对通用几何特征和结构语义特征分别进行归一化、投影和门控融合，从而增强网络对结构语义的利用能力。

2.2.4 步骤四：构造 family-aware 的 cut 修复与重排机制
在低层策略输出候选割序列之后，本发明不直接将其作为最终结果，而是进一步构造 family-aware 的 cut 修复与重排机制。该机制根据候选割在不同变量族上的统计占比生成结构变量族配额，并结合 cut 之间的冗余度与多样性对低层输出进行修复与重排。

具体而言，首先根据候选割在路径、装载、时序和完工等变量族上的聚合分布生成当前节点的变量族配额；然后优先从低层序列中保留满足变量族配额的 cut；对于不足部分，再依据结构得分与冗余惩罚从候选序列尾部和启发式序列中补足，以避免最终 cut 集合过度集中在某一类变量族上。通过该机制，可提高最终 cut 集合对关键结构瓶颈的覆盖能力。

2.2.5 步骤五：对层次策略网络进行并行强化学习训练
本发明在训练阶段采用并行强化学习方式对高层和低层策略进行训练。将上述调度 MIP 的求解过程封装为环境，每次求解实例时，求解器在分离阶段调用当前策略网络进行候选割选择。训练过程中记录候选割特征状态、高层输出的割选择比例动作、低层输出的割索引序列动作以及实例求解时间、节点数、原始对偶间隙或原始对偶积分等反馈。

优选地，以求解时间作为主要奖励，也可将节点数、原始对偶间隙、原始对偶积分或其加权组合作为奖励。训练时使用随机解码进行探索，低层策略采用带基线的策略梯度更新，高层策略采用独立的策略梯度更新。

2.2.6 步骤六：在测试阶段结合束搜索输出更优割序列
在获得训练好的高层和低层策略后，本发明在推理阶段采用束搜索代替单一路径贪心解码。具体步骤为：对当前候选割集合构造初始束；使用低层策略网络对每个部分序列扩展多个候选割索引；依据路径累计概率或累计评分对候选部分序列进行排序；仅保留前 k 条得分最高的候选割序列；直至输出结束标记或达到最大解码长度；选择得分最高的完整割序列作为当前轮分离阶段的割选择结果。

在本发明中，束搜索结果还会进一步经过 family-aware 修复与重排，从而兼顾学习策略概率、变量族覆盖度以及 cut 多样性。

2.2.7 步骤七：将学习式割选择结果反馈至求解器并输出最终调度解
求解器根据高层比例策略、低层序列策略、family-aware 重排机制以及束搜索结果得到候选割序列，对当前节点的候选割进行筛选和排序，随后继续执行分支定界。最终输出包括：求解状态、最优目标值或当前最优可行目标值、非零变量取值、求解时间、总节点数、原始对偶间隙以及原始对偶积分。

本发明还可进一步输出多种求解模式下的消融结果，包括：默认求解器、仅强化学习策略、仅束搜索启发式以及强化学习与束搜索结合模式。

2.3 本发明技术方案带来的有益效果
与现有技术相比，本发明至少具有以下有益效果：
（1）通过产品对和加工周期建模，能够精确表达双源混流旋转腔组合设备中 4x1 与 2x2 两种工艺模式；
（2）通过结构感知候选割表征，使策略网络能够识别不同变量族对应的关键调度瓶颈，而不再仅依赖通用几何特征；
（3）通过 family-aware 的 cut 修复与重排机制，提高 branch-and-cut 过程中路径、装载、时序和完工约束的覆盖能力；
（4）通过在推理阶段引入束搜索，提高低层 cut 序列解码的稳定性，减少单一路径贪心策略带来的性能波动；
（5）在保持复杂工艺约束严格可行的基础上，提高大规模双源混流旋转腔调度 MIP 的求解效率和最终解质量。

3、针对2中的技术方案，是否还有别的替代方案同样能完成发明目的
在不脱离本发明核心思想的前提下，还可采用以下替代方案：
（1）求解器替代：可将 SCIP 替换为 Gurobi、CPLEX 或其它支持分支定界与割平面的 MIP 求解器；
（2）低层序列模型替代：可将指针网络替换为 Transformer、带注意力机制的循环神经网络或其它能够输出候选割排序序列的模型；
（3）高层比例策略替代：可采用离散档位分类器、Beta 分布策略网络或其它回归/采样策略代替当前的割比例输出网络；
（4）强化学习算法替代：可采用 A3C、PPO、REINFORCE、SAC 或其它策略优化方法，只要仍然围绕候选割特征输入、割比例决策、割序列输出与求解性能反馈展开，均属于本发明的等同方案；
（5）搜索算法替代：可将束搜索替换为 best-first search、MCTS 或其它保留多候选路径的序列搜索方法；
（6）结构感知替代：可将变量族比例、结构熵、主导变量族等特征替换为其它能够反映调度结构语义的统计量，只要其作用仍是增强候选割对调度结构瓶颈的可辨识性，即属于本发明的等同方案。

4、本发明的技术关键点和欲保护点是什么
本发明的技术关键点和欲保护点至少包括：
（1）面向双源混流旋转腔组合设备的精确 MIP 建模方式；
（2）将 4x1 专用 PM 与 2x2 专用 PM 统一纳入同一调度模型的路由与时间约束体系；
（3）使用产品对和加工周期对 2x2 模式中的双次加工与 PEC 边界进行编码的方法；
（4）将 MIP 求解器分离阶段的候选割集合构造成结构感知强化学习状态的方法；
（5）在通用 cut 几何特征之外引入变量族参与比例和结构熵等特征的结构感知候选割表征方法；
（6）采用“高层选取割比例、低层输出割序列”的层次强化学习割选择框架；
（7）依据变量族配额与 cut 多样性对低层输出进行修复与重排的 family-aware 机制；
（8）在推理阶段将学习式割选择与束搜索结合，以提升求解稳定性和解质量的方法；
（9）将上述方法应用于双源混流旋转腔组合设备调度 MIP 求解的整体系统方案。

5、附图
建议附图如下：
图1：带双旋转 PM、LL、机械手和 PEC storage 的组合设备结构示意图；
图2：4x1 模式下四工位装满、统一加工、统一取出的时序示意图；
图3：2x2 模式下“前导 PEC + 产品对流水交叉 + 尾部 PEC”的时序示意图；
图4：旋转腔调度逻辑与 Petri 网关系示意图；
图5：MIP 变量定义示意图；
图6：MIP 目标函数与部分约束示意图；
图7：MIP 约束示意图（二）；
图8：MIP 约束示意图（三）。
""".strip()

FIGURE_CAPTIONS = [
    ("wdc.png", "图1 带双旋转 PM、负载锁、机械手和 PEC storage 的双源混流旋转腔组合设备结构示意图"),
    ("mode_4x1.png", "图2 4x1 加工模式的时序示意图"),
    ("mode_2x2.png", "图3 2x2 加工模式的时序示意图"),
    ("PN.jpeg", "图4 旋转腔调度逻辑与 Petri 网关系示意图"),
    ("1.png", "图5 MIP 变量定义示意图"),
    ("2.png", "图6 MIP 目标函数与约束示意图（一）"),
    ("3.png", "图7 MIP 约束示意图（二）"),
    ("4.png", "图8 MIP 约束示意图（三）"),
]


def get_image_size(path):
    data = path.read_bytes()
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    if data[:2] == b"\xff\xd8":
        i = 2
        while i < len(data):
            while i < len(data) and data[i] != 0xFF:
                i += 1
            while i < len(data) and data[i] == 0xFF:
                i += 1
            if i >= len(data):
                break
            marker = data[i]
            i += 1
            if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                _, height, width = struct.unpack(">BHH", data[i + 2:i + 7])
                return width, height
            if i + 1 >= len(data):
                break
            seglen = struct.unpack(">H", data[i:i + 2])[0]
            i += seglen
    raise ValueError(f"Unsupported image format: {path}")


def make_paragraph(text="", bold=False, size=24, center=False):
    ppr = ""
    if center:
        ppr = "<w:pPr><w:jc w:val=\"center\"/></w:pPr>"
    rpr = ""
    if bold or size != 24:
        rpr_parts = []
        if bold:
            rpr_parts.append("<w:b/>")
            rpr_parts.append("<w:bCs/>")
        if size != 24:
            rpr_parts.append(f"<w:sz w:val=\"{size}\"/>")
            rpr_parts.append(f"<w:szCs w:val=\"{size}\"/>")
        rpr = f"<w:rPr>{''.join(rpr_parts)}</w:rPr>"
    if text == "":
        return f"<w:p>{ppr}<w:r>{rpr}<w:t xml:space=\"preserve\"></w:t></w:r></w:p>"
    text = escape(text)
    return f"<w:p>{ppr}<w:r>{rpr}<w:t xml:space=\"preserve\">{text}</w:t></w:r></w:p>"


def make_page_break():
    return "<w:p><w:r><w:br w:type=\"page\"/></w:r></w:p>"


def make_image_paragraph(rid, docpr_id, name, width_emu, height_emu):
    return (
        "<w:p><w:pPr><w:jc w:val=\"center\"/></w:pPr><w:r><w:drawing>"
        "<wp:inline distT=\"0\" distB=\"0\" distL=\"0\" distR=\"0\" "
        "xmlns:wp=\"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing\">"
        f"<wp:extent cx=\"{width_emu}\" cy=\"{height_emu}\"/>"
        f"<wp:docPr id=\"{docpr_id}\" name=\"{escape(name)}\"/>"
        "<a:graphic xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\">"
        "<a:graphicData uri=\"http://schemas.openxmlformats.org/drawingml/2006/picture\">"
        "<pic:pic xmlns:pic=\"http://schemas.openxmlformats.org/drawingml/2006/picture\">"
        "<pic:nvPicPr>"
        f"<pic:cNvPr id=\"{docpr_id}\" name=\"{escape(name)}\"/>"
        "<pic:cNvPicPr/>"
        "</pic:nvPicPr>"
        "<pic:blipFill>"
        f"<a:blip r:embed=\"{rid}\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"/>"
        "<a:stretch><a:fillRect/></a:stretch>"
        "</pic:blipFill>"
        "<pic:spPr>"
        "<a:xfrm><a:off x=\"0\" y=\"0\"/>"
        f"<a:ext cx=\"{width_emu}\" cy=\"{height_emu}\"/></a:xfrm>"
        "<a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom>"
        "</pic:spPr>"
        "</pic:pic>"
        "</a:graphicData>"
        "</a:graphic>"
        "</wp:inline>"
        "</w:drawing></w:r></w:p>"
    )


def split_lines(text):
    return [line.rstrip() for line in text.strip().splitlines()]


def extract_sect_pr(document_xml):
    match = re.search(r"(<w:sectPr[\s\S]*</w:sectPr>)\s*</w:body>\s*</w:document>\s*$", document_xml)
    if match:
        return match.group(1)
    return (
        "<w:sectPr>"
        "<w:pgSz w:w=\"11906\" w:h=\"16838\"/>"
        "<w:pgMar w:top=\"1440\" w:right=\"1800\" w:bottom=\"1440\" w:left=\"1800\" "
        "w:header=\"851\" w:footer=\"992\" w:gutter=\"0\"/>"
        "<w:cols w:space=\"425\"/>"
        "<w:docGrid w:type=\"lines\" w:linePitch=\"312\"/>"
        "</w:sectPr>"
    )


def prepare_image_specs():
    specs = []
    max_width_emu = int(5.8 * 914400)
    for idx, (file_name, caption) in enumerate(FIGURE_CAPTIONS, start=1):
        path = ASSET_DIR / file_name
        width, height = get_image_size(path)
        scale = min(1.0, max_width_emu / float(width * 9525))
        width_emu = int(width * 9525 * scale)
        height_emu = int(height * 9525 * scale)
        specs.append(
            {
                "file_name": file_name,
                "caption": caption,
                "rid": f"rId{100 + idx}",
                "docpr_id": 300 + idx,
                "width_emu": width_emu,
                "height_emu": height_emu,
                "path": path,
            }
        )
    return specs


def build_document_xml(sect_pr, image_specs):
    body = []
    body.append(make_paragraph("权利交底书", bold=True, size=32, center=True))
    body.append(make_paragraph(""))
    body.append(make_paragraph(TITLE, bold=True, size=30, center=True))
    body.append(make_paragraph(""))
    body.append(make_paragraph(f"中文关键词：{KEYWORDS_CN}", size=24))
    body.append(make_paragraph(f"英文关键词：{KEYWORDS_EN}", size=24))
    body.append(make_page_break())

    body.append(make_paragraph("摘要", bold=True, size=28, center=True))
    body.append(make_paragraph(""))
    body.append(make_paragraph(ABSTRACT, size=24))
    body.append(make_page_break())

    body.append(make_paragraph("权利要求书", bold=True, size=28, center=True))
    body.append(make_paragraph(""))
    for line in split_lines(CLAIMS):
        body.append(make_paragraph(line, size=24))
    body.append(make_page_break())

    body.append(make_paragraph("说明书", bold=True, size=28, center=True))
    body.append(make_paragraph(""))
    for line in split_lines(FULL_SPEC):
        body.append(make_paragraph(line, size=24))
    body.append(make_page_break())

    body.append(make_paragraph("附图说明与附图", bold=True, size=28, center=True))
    body.append(make_paragraph(""))
    for image_spec in image_specs:
        body.append(make_paragraph(image_spec["caption"], bold=True, size=24))
        body.append(make_image_paragraph(
            image_spec["rid"],
            image_spec["docpr_id"],
            image_spec["file_name"],
            image_spec["width_emu"],
            image_spec["height_emu"],
        ))
        body.append(make_paragraph(""))

    body_xml = "".join(body) + sect_pr
    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document "
        "xmlns:wpc=\"http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas\" "
        "xmlns:cx=\"http://schemas.microsoft.com/office/drawing/2014/chartex\" "
        "xmlns:mc=\"http://schemas.openxmlformats.org/markup-compatibility/2006\" "
        "xmlns:o=\"urn:schemas-microsoft-com:office:office\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" "
        "xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\" "
        "xmlns:v=\"urn:schemas-microsoft-com:vml\" "
        "xmlns:wp14=\"http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing\" "
        "xmlns:wp=\"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing\" "
        "xmlns:w10=\"urn:schemas-microsoft-com:office:word\" "
        "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" "
        "xmlns:w14=\"http://schemas.microsoft.com/office/word/2010/wordml\" "
        "xmlns:w15=\"http://schemas.microsoft.com/office/word/2012/wordml\" "
        "xmlns:wpg=\"http://schemas.microsoft.com/office/word/2010/wordprocessingGroup\" "
        "xmlns:wpi=\"http://schemas.microsoft.com/office/word/2010/wordprocessingInk\" "
        "xmlns:wne=\"http://schemas.microsoft.com/office/word/2006/wordml\" "
        "xmlns:wps=\"http://schemas.microsoft.com/office/word/2010/wordprocessingShape\" "
        "mc:Ignorable=\"w14 w15 wp14\">"
        f"<w:body>{body_xml}</w:body></w:document>"
    )


def update_rels(xml_text, image_specs):
    insert = []
    for image_spec in image_specs:
        ext = image_spec["path"].suffix.lower().lstrip(".")
        target = f"media/{image_spec['file_name']}"
        insert.append(
            f"<Relationship Id=\"{image_spec['rid']}\" "
            "Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/image\" "
            f"Target=\"{target}\"/>"
        )
    return xml_text.replace("</Relationships>", "".join(insert) + "</Relationships>")


def update_content_types(xml_text, image_specs):
    additions = []
    if ".png" in {spec["path"].suffix.lower() for spec in image_specs} and "Extension=\"png\"" not in xml_text:
        additions.append("<Default Extension=\"png\" ContentType=\"image/png\"/>")
    if ".jpeg" in {spec["path"].suffix.lower() for spec in image_specs} and "Extension=\"jpeg\"" not in xml_text:
        additions.append("<Default Extension=\"jpeg\" ContentType=\"image/jpeg\"/>")
    if additions:
        xml_text = xml_text.replace("</Types>", "".join(additions) + "</Types>")
    return xml_text


def main():
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    image_specs = prepare_image_specs()

    with zipfile.ZipFile(TEMPLATE, "r") as zin:
        template_document = zin.read("word/document.xml").decode("utf-8", errors="replace")
        sect_pr = extract_sect_pr(template_document)
        new_document_xml = build_document_xml(sect_pr, image_specs)
        rels_xml = zin.read("word/_rels/document.xml.rels").decode("utf-8", errors="replace")
        content_types_xml = zin.read("[Content_Types].xml").decode("utf-8", errors="replace")

        rels_xml = update_rels(rels_xml, image_specs)
        content_types_xml = update_content_types(content_types_xml, image_specs)

        target_path = OUTPUT
        try:
            with zipfile.ZipFile(target_path, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename in {"word/document.xml", "word/_rels/document.xml.rels", "[Content_Types].xml"}:
                        continue
                    zout.writestr(item, zin.read(item.filename))
                zout.writestr("word/document.xml", new_document_xml.encode("utf-8"))
                zout.writestr("word/_rels/document.xml.rels", rels_xml.encode("utf-8"))
                zout.writestr("[Content_Types].xml", content_types_xml.encode("utf-8"))
                for image_spec in image_specs:
                    zout.write(image_spec["path"], arcname=f"word/media/{image_spec['file_name']}")
        except PermissionError:
            target_path = FALLBACK_OUTPUT
            with zipfile.ZipFile(target_path, "w", zipfile.ZIP_DEFLATED) as zout:
                for item in zin.infolist():
                    if item.filename in {"word/document.xml", "word/_rels/document.xml.rels", "[Content_Types].xml"}:
                        continue
                    zout.writestr(item, zin.read(item.filename))
                zout.writestr("word/document.xml", new_document_xml.encode("utf-8"))
                zout.writestr("word/_rels/document.xml.rels", rels_xml.encode("utf-8"))
                zout.writestr("[Content_Types].xml", content_types_xml.encode("utf-8"))
                for image_spec in image_specs:
                    zout.write(image_spec["path"], arcname=f"word/media/{image_spec['file_name']}")

    print(str(target_path))


if __name__ == "__main__":
    main()
