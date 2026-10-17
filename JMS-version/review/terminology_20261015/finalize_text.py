from pathlib import Path
import json

HERE = Path(__file__).resolve().parent
p = HERE.parents[1] / 'JMS_Review_CN.tex'
s = p.read_text(encoding='utf-8')
edits = [
    ('清洁间隔', '清洁阈值'),
    ('清洁上限', '清洁阈值'),
    ('清洁频率实验', '清洁阈值实验'),
    ('清洁自身不计数', '清洁不计入生产周期'),
    ('已有CT研究建立了加工、搬运与吞吐率之间的解析关系', '已有CT研究建立了工艺处理、搬运与吞吐率之间的解析关系'),
    ('沉积均匀性和加工能力', '沉积均匀性和工艺处理能力'),
    ('完成全部工艺处理的产品从腔室', '完成全部工艺处理的产品晶圆从腔室'),
    ('晶圆完整路线', '完整晶圆路线'),
    ('上下装载锁的晶圆槽位', '上下装载锁的晶圆槽位'),
    ('相邻生产周期间隔由交换前等待与交换过程共同构成。', '此处的相邻生产周期间隔指前一周期结束至后一周期开始的时间，由交换前等待与交换过程共同构成。'),
    ('在名义工艺时长系数的', '在工艺时长系数为1的'),
    ('在所测0.9--1.1工艺时长系数范围内', '在所测工艺时长系数0.9--1.1范围内'),
    ('时间精修', '时刻精修'),
    ('时间质量与界收敛', '排程时序质量与界收敛'),
    ('把晶圆从释放推进到返回', '把晶圆从释放推进到返回'),
    ('两种产品配方数量相等', '两种配方的产品晶圆数量相等'),
    ('两种产品数量相等', '两种配方的产品晶圆数量相等'),
    ('两种产品数量各半', '两种配方的产品晶圆数量各半'),
    ('产品数量各半的混合模式', '两种配方产品晶圆数量各半的混合模式'),
    ('校验的排程', '校验的排程'),
]
counts = []
for old, new in edits:
    if old != new and old in s:
        counts.append({'old':old, 'new':new, 'count':s.count(old)})
        s = s.replace(old, new)
# Distinguish route-task indices from the reusable physical auxiliary inventory.
old = r'令$\mathcal A^{\rm int}$表示共同的腔内先后关系，$\mathcal A_{is}(\gamma)$表示晶圆$i$在来源$s$及搬运选择$\gamma$下的供回片先后弧。'
new = r'令$\mathcal I$为晶圆路线任务集合，其中每片产品晶圆对应一条完整路线，辅助晶圆每次借用对应一条供回路线。$\mathcal A^{\rm int}$表示共同的腔内先后关系，$\mathcal A_{is}(\gamma)$表示任务$i$在来源$s$及搬运选择$\gamma$下的供回片先后弧。'
assert s.count(old)==1
s=s.replace(old,new)
p.write_text(s,encoding='utf-8',newline='\n')
(HERE/'final_text_changes.json').write_text(json.dumps(counts,ensure_ascii=False,indent=2),encoding='utf-8')
print('Final terminology pass:',len(counts))
