"""Publish the verified Model4 catalog without replacing frozen export evidence."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'JMS-version/gif/kexingyu'
REL = 'model4_pjob_20261027'


def main():
    manifest = json.loads((BASE/REL/'manifest.json').read_text('utf-8'))
    checks = BASE/REL/'verification_20261028'
    export = json.loads((checks/'exports.json').read_text('utf-8'))
    replay = json.loads((checks/'backend_replay.json').read_text('utf-8'))
    if export['total_records'] != 150320 or export['failed'] != 0 or replay['passed'] != 36:
        raise ValueError('Verification incomplete')
    rows = []
    for f in manifest['files']:
        n = f['n']
        lower = math.factorial(n)//math.factorial(n//4)**4 * 2**(n//2)
        if str(lower) != f['family_count_per_configuration']:
            raise ValueError('Lower bound mismatch')
        rows.append(dict(n=n, listed=f['count'], listed_per_configuration=f['count']//2,
                         lower_bound_per_configuration=str(lower),
                         lower_bound_union_four_configurations=str(2*lower),
                         path=f"{REL}/{f['path']}", sha256=f['sha256']))
    # Keep the prior Model2 explanations, with their original relative links.
    for source, target in [('README.md', 'README_model2_详细历史.md'),
                           ('README_简化版.md', 'README_model2_简化历史.md')]:
        dest = BASE/target
        if not dest.exists():
            dest.write_bytes((BASE/source).read_bytes())
    table = '\n'.join(f"| {r['n']} | [{r['listed']:,}条]({r['path']}) | {r['listed_per_configuration']:,} | {int(r['lower_bound_per_configuration']):,} | {int(r['lower_bound_union_four_configurations']):,} |" for r in rows)
    content = f'''# 模型4：可行排程列举与数量下界

更新于2026-10-28。当前入口采用模型4的Pjob库存和腔室资格口径；原模型2文件保留溯源，不作为当前计数结果。

| 产品数N | 已列不重复取放顺序（点击文件） | 每个固定配置已列 | 每个固定配置总数量下界 | 四配置合并去重后的总数量下界 |
|---|---:|---:|---:|---:|
{table}

文件位于 `JMS-version/gif/kexingyu/{REL}/`，文件名和首行都已注明模型4、已列数量及每配置下界；同目录有无损 `.txt.gz` 版本。每条记录完整列出该排程全部产品及实际辅助片的取放，按开始时间排序，仅显示晶圆、ATR/VTR取放和地点。同刻动作写作 `{{动作A || 动作B}}`。

**这些是可行排程数量的下界，不是最优排程数量，也不是精确总数。** 已列数量是导出配额；没有完成整个空间枚举，不能从导出配额推算覆盖率。

## 固定输入与计数规则

每个规模覆盖纯4×1、纯2×2与H=3、H=10四个配置；双源、两腔CH2/CH3、8片辅助片，四个LP各N/4片产品，时间域100000秒。Pjob1来自LP1且仅可用CH2；Pjob2来自LP2且仅可用CH3；Pjob3来自LP3/LP4且可用两个腔室。该下界针对这组明确输入；修改资格、库存、时域或添加紧的Cmax限制后需要重新检查。

同一Pjob、同一LP内仅交换产品身份不算新排程。产品按该组的取片次序规范化编号。数值时间和纯等待长度不参与去重；这些文件按取放动作开始次序及同刻分组区分，不据此声称完整刻画所有并行关系。

## 下界推导

N表示**产品晶圆片数**，不含辅助片，也不是动作数。四种来源LP各出现N/4次，来源顺序共有 `N!/((N/4)!)^4` 种；LP3/LP4共N/2次取片各可选择两个加工腔室，因此：

`L(N) = N!/((N/4)!)^4 × 2^(N/2)`。

对每一组来源/腔室选择，每次只处理一个产品，以辅助片补位，产品回片并完成清洁后再进入下一块。4×1每块一次生产曝光，2×2同腔连续两次生产曝光，随后清洁，均满足H=3和10。每块间隔900秒，覆盖完整物料归还、LL复位和搬运间隔；8/16/32片的最坏完整终点分别为7150/14350/28750秒，未超时域。

改变来源顺序会改变ATR取片顺序，改变腔室选择会改变VTR放片位置，因此不同构造编号产生不同取放序列。L(N)是这个串行构造族的精确大小，也是整个可行空间的下界。它不包含所有自由配对、双腔并行、交错搬运和清洁位置。

四配置合并时，H=3/10在本构造中产生相同的取放顺序，应合并；4×1与2×2的动作链不同，两个构造族不相交。因此合并下界为 **2L(N)**，不是4L(N)。这表示四组不同输入下动作序列集合的并集，不是某个单一固定配方实例的空间。

## 验证与完整示例

2026-10-28重新核对全部150,320条输出的哈希、去重、库存、资格、规范编号和索引，并验证gzip无损。36条完整规模代表见证全部通过当前模型4正式独立验证器的物理与Pjob检查；6项构造/计数回归测试通过。没有对每条记录重求MILP，也没有进行最优性认证。

- [完整规则、六条易读示例及任意记录提取命令]({REL}/README.md)
- [本次逐条文件审计]({REL}/verification_20261028/exports.json)
- [本次模型4完整时间见证重放]({REL}/verification_20261028/backend_replay.json)
- [机器可读当前目录](current_model.json)
- 模型2历史说明：[简化版](README_model2_简化历史.md)、[详细版](README_model2_详细历史.md)。旧N!下界保留原归属。
'''
    (BASE/'README.md').write_text(content, 'utf-8')
    (BASE/'README_简化版.md').write_text(content.replace('# 模型4：可行排程列举与数量下界', '# 模型4：简化取放排程与数量下界', 1), 'utf-8')
    catalog = dict(updated_utc=datetime.now(timezone.utc).isoformat(), model='model4_pjob',
        export_manifest=f'{REL}/manifest.json',
        manifest_sha256=hashlib.sha256((BASE/REL/'manifest.json').read_bytes()).hexdigest(),
        lower_bound_formula='N!/((N/4)!)^4 * 2^(N/2)',
        qualification='LP1->CH2; LP2->CH3; LP3,LP4->CH2 or CH3',
        union_definition='4x1/2x2 x H3/H10; identical H orders merged; union lower bound = 2*L(N)',
        complete_enumeration=False, exact_total=None, files=rows)
    (BASE/'current_model.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2), 'utf-8')
    print('Published Model4 catalog for 8, 16, 32 products; historical evidence preserved.')


if __name__ == '__main__':
    main()
