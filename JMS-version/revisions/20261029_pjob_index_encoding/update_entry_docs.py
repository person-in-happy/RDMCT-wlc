from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, shutil

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
BACKEND=ROOT/'JMS-version/model4_pjob_fifo_20261029'
PARENT=ROOT/'JMS-version/gif/kexingyu'
OUT=PARENT/'pjob_fifo_20261029'

(BACKEND/'README.md').write_text('''# Pjob批次内编码与全局严格出片MILP

本目录独立实现全Pjob跨LP按序取片。当前旧队列仍使用原目录，本轮不启动新的实验批次。

输入产品先按工艺模式、腔室资格分组，再按实际晶圆全局编号生成 `Pjob_j[k]`。编号表同时保留实际ID及来源LP；同批次两片产品不得同时从LP取出。

- `pjob_order.py`：输入编码、相邻非空LP的连续时间分界、同Pjob取片同步限制、最终全局序号解码与顺序重放检查。
- `model.py`：保留库存选择、PW对、工艺周期与完整资源模型，接入新增顺序约束。
- `seed.py`：按批次内连续区段分腔，构造满足统一出片顺序的起点。
- `validate.py`：检查实际晶圆、编码、来源LP及严格取片顺序；原物理检查保持执行。

同一Pjob仍可拆分至多个PW对和腔室。不同Pjob可交错出片，资格有交集且模式相容时可以组对；后续加工与回片不要求全路线FIFO。辅助晶圆实体仍作为可复用资源。

设非空Pjob数为J、非空Pjob--LP组数为G、产品数为N，产品库存选择块为2GN；跨LP顺序增加G-J个连续辅助量。禁止同批同步取片使用已有同步选择变量，不增加产品身份排列变量。

输出保留 `events/pairs/cycles/jobs` 格式，增加 `product_encoding` 及每片产品的 `pjob_index`、`encoded_product`、`wafer_number`。`model_scope` 为 `pjob_global_fifo_v2`。最终输出按全Pjob取片次序解码；求解阶段中的物理验解使用相同映射。

29项正确性测试通过，包含完整模型赋值检查、两阶段输出、跨LP逆序/同时取片拒绝以及跨Pjob同步取片保留。它们是开发验证，不计入文稿实验次数。

统一命令见[当前实验清单](../MODEL4_EXPERIMENT_COMMANDS.md)：`paper` 102次、`qualification` 6次、`rhythm` 48次；选割比较 `paper_cuts` 72次可选。所有正式实验在可见前台启动，保存冻结协议与独立目录。
''','utf-8')

manifest=json.loads((OUT/'manifest.json').read_text('utf-8'))
rows=[]
for n,v in manifest['sizes'].items():
    lower=v['lower_bound_per_configuration'];listed=v['count']
    rows.append(dict(n=int(n),listed=listed,listed_per_configuration=listed//2,
        lower_bound_per_configuration=str(lower),lower_bound_union_four_configurations=str(2*lower),
        path='pjob_fifo_20261029/'+v['file'],sha256=v['sha256']))
for name in ('README.md','current_model.json'):
    shutil.copy2(PARENT/name,HERE/'original'/('kexingyu_'+name))
pointer=dict(updated_utc=datetime.now(timezone.utc).isoformat(),model='pjob_global_fifo',
    export_manifest='pjob_fifo_20261029/manifest.json',
    manifest_sha256=hashlib.sha256((OUT/'manifest.json').read_bytes()).hexdigest(),
    lower_bound_formula='N! / ((N/4)!^2 * (N/2)!) * 2^(N/2)',
    release_rule='Strict global Pjob index order, no simultaneous same-Pjob initial pickup',
    qualification='LP1->CH2; LP2->CH3; LP3,LP4->CH2 or CH3',
    union_definition='4x1/2x2 x H3/H10; identical H orders merged; union lower bound = 2*L(N)',
    complete_enumeration=False,exact_total=None,files=rows)
(PARENT/'current_model.json').write_text(json.dumps(pointer,ensure_ascii=False,indent=2),'utf-8')
doc='''# 按Pjob统一序号严格出片的可行排程

更新于2026-10-29。同一Pjob跨LP按统一序号依次取片，不允许同时取片；不同Pjob可交错。下列记录筛自已有动作序列，保留数值时刻，未重新求解MILP。

| 产品数 | 不同序列总数 | 每固定配置已列 | 每配置构造下界 |
|---|---:|---:|---:|
'''
for row in rows:
    doc+=f"| {row['n']} | [{row['listed']}]({row['path']}) | {row['listed_per_configuration']} | {row['lower_bound_per_configuration']} |\n"
doc+='''
每个规模覆盖纯4×1、纯2×2及H=3/10。两种配方各占总数一半，相同配方在两个阈值下的相同动作序列合并计数。下界为构造族大小，不是最优排程数量或全部排程的精确总数。

四LP各N/4片：Pjob1仅含LP1且只允许CH2；Pjob2仅含LP2且只允许CH3；Pjob3含LP3/LP4且可用两腔。Pjob3必须先取完LP3产品，再取LP4产品。因此构造族为 `N! / ((N/4)!^2 (N/2)!) × 2^(N/2)`。每个产品块完成回片和清洁后才开始下一块，块间隔900秒。

导出文件逐条增加批次编码与实际晶圆出片序列，保留全部产品与辅助晶圆取放动作。7402条记录均通过库存、资格、顺序和去重检查；36个完整时间见证通过独立物理重放。16/32片保留数较少来自对旧抽样记录的筛选，不代表构造空间只有这些排程。

- [完整时间排程示例](pjob_fifo_20261029/examples/)
- [当前导出与验证记录](pjob_fifo_20261029/manifest.json)
- [机器可读目录](current_model.json)
- [此前规则的原始数据](model4_pjob_20261027/README.md)，保留不覆盖。
- [本次修订审阅](../../revisions/20261029_pjob_index_encoding/REVIEW_CN.md)
'''
(PARENT/'README.md').write_text(doc,'utf-8')
(OUT/'README.md').write_text(doc.replace('pjob_fifo_20261029/',''),'utf-8')
print('Updated independent backend and schedule entry documentation')
