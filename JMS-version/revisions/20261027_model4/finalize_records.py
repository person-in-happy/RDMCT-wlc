"""Update navigation and record the finished Chinese-only manuscript revision."""
from pathlib import Path
import difflib, hashlib, json

PAPER = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def main():
    for name in ('README.md', 'README_简化版.md'):
        path = PAPER/'gif/kexingyu'/name
        text = path.read_text('utf-8-sig')
        note = ('模型4新增：按Pjob与来源库存去除产品身份置换，'
                '8/16/32片分别列出40,320/50,000/60,000条。'
                '见[模型4文件、具体排程与计数证据](model4_pjob_20261027/README.md)。'
                '以下原模型2记录保留其原输入和计数口径。\n\n')
        if 'model4_pjob_20261027/README.md' not in text:
            title, rest = text.split('\n', 1)
            path.write_text(title+'\n\n'+note+rest.lstrip('\n'), 'utf-8')
    path = PAPER/'README.md'
    text = path.read_text('utf-8-sig')
    text = text.replace('# JMS项目：采用模型2', '# JMS项目：模型4中文稿与模型2冻结实验')
    text = text.replace('项目采用同质工艺加工时间、允许阈值前清洁且达到阈值必须清洁的联合模型。模型说明以论文正文为准，不再维护独立的重复说明文档。',
        '中文主稿采用Pjob批次任务模型4，保留同质工艺时长及阈值前可选清洁规则。模型4已完成数学建模和构造性可行排程；完整MILP后端尚未实现，现有求解实验入口仍属于模型2。英文稿未随本次中文修改同步。模型说明以论文正文为准。')
    text = text.replace('- `gif/kexingyu/`：模型2可行取放序列及验证证据；Git保存无损压缩文本，使用该目录简化版说明读取。',
        '- `gif/kexingyu/`：原模型2可行序列及证据；[模型4新序列](gif/kexingyu/model4_pjob_20261027/README.md)单独归档。\n'
        '- `tools/model4_feasible_orders.py`：Pjob构造、取放输出和任意记录提取验解，不是完整MILP求解器。\n'
        '- [实验复用与补跑审计](revisions/20261027_model4/EXPERIMENT_REUSE_AND_RERUN_CN.md)：结果归属、复验条件、补跑矩阵和实际命令。\n'
        '- `revisions/20261027_model4/`：中文原稿备份、修改差异、哈希和独立导出审计。')
    text = text.replace('稿件编译入口为`tools/build_submission.ps1`，中英文打包入口为`tools/package_submission_bilingual.py`。审稿证据规则见`REVIEW_WORKFLOW.md`。',
        '当前仅编译模型4中文稿：`G:\\conda\\python.exe -X utf8 JMS-version/tools/build_model4_cn.py`（从仓库根目录执行）。'
        '原`tools/build_submission.ps1`及`tools/package_submission_bilingual.py`用于中英文一致的旧流程；英文未同步期间不能据其生成模型4双语投稿包。审稿证据规则见`REVIEW_WORKFLOW.md`。')
    path.write_text(text, 'utf-8')
    source = PAPER/'JMS_Review_CN.tex'
    original = HERE/'original/JMS_Review_CN.tex'
    diff = difflib.unified_diff(original.read_text('utf-8-sig').splitlines(True),
        source.read_text('utf-8-sig').splitlines(True), fromfile='original/JMS_Review_CN.tex', tofile='JMS_Review_CN.tex')
    (HERE/'manuscript.patch').write_text(''.join(diff), 'utf-8')
    files = [original, HERE/'original/JMS_Review_CN.pdf', source, PAPER/'JMS_Review_CN.pdf',
        PAPER/'output/pdf/JMS_Review_CN.pdf']
    report = {str(p.relative_to(PAPER)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (HERE/'manuscript_hashes.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), 'utf-8')
    print('Navigation, Chinese-only diff and five manuscript hashes recorded.')


if __name__ == '__main__':
    main()
