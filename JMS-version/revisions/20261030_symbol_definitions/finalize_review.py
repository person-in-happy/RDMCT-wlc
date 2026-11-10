"""Record the symbol-definition revision and verify its editorial scope."""
from pathlib import Path
import difflib
import hashlib
import json
import re

HERE = Path(__file__).resolve().parent
PAPER = HERE.parents[1]
source = PAPER / 'JMS_Review_CN.tex'
original = HERE / 'original/JMS_Review_CN.tex'
before = original.read_text('utf-8')
after = source.read_text('utf-8')


def equations(text):
    return {
        re.search(r'\\label\{([^}]+)\}', body).group(1): body
        for body in re.findall(r'\\begin\{equation\}(.*?)\\end\{equation\}', text, re.S)
    }


def normalized(body):
    replacements = [
        (r's\in\mathcal S', r'\varsigma\in\mathcal S'),
        (r'_{is}', r'_{i\varsigma}'),
        (r'_{c,e-1}', r'_{c,h-1}'),
        (r'a_{vce}', r'a_{vch}'),
        (r'_{ce}', r'_{ch}'),
        ('(e>1)', '(h>1)'),
        (r'\ell\in\Gamma_o', r'u\in\Gamma_o'),
        (r'h_{o\ell}', r'h_{ou}'),
        (r"h_{o'\ell}", r"h_{o'u}"),
        (r'\rho^r_', r'\delta^\rho_'),
        (r'y^r_', r'y^\rho_'),
        (r'\rho^{\rm VTR}', r'\delta^{\rm VTR}'),
        (r'\mathcal Q^w', r'\mathcal W'),
        (r'\mathcal I_h', r'\mathcal I_{\rm rhythm}'),
        (r'\mathcal F_k', r'\mathcal F_t'),
    ]
    for old, new in replacements:
        body = body.replace(old, new)
    return re.sub(r'\s+', '', body)


old_eq, new_eq = equations(before), equations(after)
assert old_eq.keys() == new_eq.keys()
assert all(normalized(body) == normalized(new_eq[key]) for key, body in old_eq.items())
renamed = [key for key in old_eq if old_eq[key] != new_eq[key]]

# The unnumbered resource-unit disjunction uses renamed local indices only.
star_pattern = r'\\begin\{equation\*\}(.*?)\\end\{equation\*\}'
old_star = re.findall(star_pattern, before, re.S)
new_star = re.findall(star_pattern, after, re.S)
assert len(old_star) == len(new_star) == 1
star = old_star[0]
for old, new in [
    (r's_j', r"s_{\iota'}"), (r's_i', r's_\iota'),
    (r'e_j', r"e_{\iota'}"), (r'e_i', r'e_\iota'),
    (r'r_j', r"u_{\iota'}"), (r'r_i', r'u_\iota'),
    (r'\theta_{ij}', r"\vartheta_{\iota\iota'}"),
    (r'\epsilon_{ij}', r"\epsilon_{\iota\iota'}"),
    ('(R+1)', r'(K_\rho+1)'),
]:
    star = star.replace(old, new)
assert re.sub(r'\s+', '', star) == re.sub(r'\s+', '', new_star[0])

old_sections = list(re.finditer(r'\\section\{', before))
new_sections = list(re.finditer(r'\\section\{', after))
assert before[:old_sections[1].start()] == after[:new_sections[1].start()]
assert before[old_sections[3].start():] == after[new_sections[3].start():]
assert re.findall(r'\\cite\w*\{([^}]+)\}', before) == re.findall(r'\\cite\w*\{([^}]+)\}', after)
assert not any(ord(c) < 32 and c not in '\n\r\t' for c in after)
assert not any(term in after for term in ('匿名', '模型4', '模型2'))

build = json.loads((PAPER / 'output/model4_cn_build/build_report.json').read_text('utf-8'))
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert build['source_sha256'] == sha(source)
assert build['pdf_sha256'] == sha(PAPER / 'JMS_Review_CN.pdf')
assert sha(PAPER / 'JMS_Review_CN.pdf') == sha(PAPER / 'output/pdf/JMS_Review_CN.pdf')
assert build['undefined_references'] == build['overfull_boxes'] == build['duplicate_labels'] == 0

report = {
    'date': '2026-10-30',
    'original_source_sha256': sha(original),
    'build': build,
    'numbered_equations': len(old_eq),
    'renamed_equation_labels': renamed,
    'numbered_equations_unchanged_after_explicit_renaming': True,
    'unnumbered_resource_disjunction_unchanged_after_explicit_renaming': True,
    'abstract_and_introduction_unchanged': True,
    'experiments_conclusion_references_unchanged': True,
    'citations_unchanged': True,
    'forbidden_submission_terms_absent': True,
    'control_character_check_passed': True,
    'visual_review': {
        'contact_sheet_pages': list(range(1, 15)),
        'detailed_pages': [2, 3, 4, 9, 10, 11],
        'tables_legible': True,
        'visible_clipping_or_overlap': False,
    },
    'solver_edits_in_this_revision': False,
    'new_experiment_runs': 0,
    'new_experiments_required_for_notation_revision': False,
}
(HERE / 'completion_review.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
(HERE / 'manuscript.patch').write_text(''.join(difflib.unified_diff(
    before.splitlines(keepends=True), after.splitlines(keepends=True),
    fromfile='original/JMS_Review_CN.tex', tofile='JMS-version/JMS_Review_CN.tex')), 'utf-8')
(HERE / 'REVIEW_CN.md').write_text('''# 符号、类型与下标定义修订记录

日期：2026-10-30。修订源文件为 `JMS-version/JMS_Review_CN.tex`。

## 修改内容

- 明确 `j` 为Pjob编号、`k` 为该Pjob内部第几片产品、`ell` 为LP编号。`ell_jk` 的值为第j个任务中第k片产品的来源LP，由输入编号表确定。
- 表1将有序编号表与来源LP参数分开，逐项说明参数类型、取值范围及各下标含义；表2逐项说明决策与辅助变量类型，以及0–1变量取1所代表的事件。
- 模型开头集中定义基本索引；在各约束前补充派生标记、事件时间引用、清洁段、物理单元、等待项、节拍指标及两阶段固定集合的定义。
- 统一资源类、物理单元、来源区域和清洁段的局部下标，避免与Pjob产品序号、LP编号及动作结束时刻混淆；同步更新相关公式。
- 补充编码、初始赋值、末端解码的映射含义，以及上标0、星号和排序上标(k)的解释。加入Pjob1编号表(1,3,26,27)对应 `ell_1,3=2` 的例子。

## 核对结果

- 共38个编号公式，9处仅更换符号。按明确映射归一化后，全部编号公式与修订前一致；无编号的资源单元互斥公式也通过同样的核对。
- 摘要、引言以及实验章节至文末保持原文，引用未增删。
- XeLaTeX三遍编译通过，PDF为14页，无未定义引用、重复标签或越界警告。
- 已检查14页缩略图，并详细检查第2、3、4、9、10、11页；两张参数/变量表及新增定义无可见裁切或重叠。
- 本轮仅修改文稿说明与符号，不修改求解器，不启动实验，不改变已有实验结果。本次符号修订不要求追加实验。

## 文件

- `original/`：修订前原稿与PDF。
- `manuscript.patch`：相对本轮原稿的完整差异。
- `completion_review.json`：公式核对、范围检查、编译结果及最终文件哈希。
- `revise_symbols.py`：初始修订过程记录；后续细调以当前原稿、差异文件及最终哈希为准。
''', 'utf-8')
print(json.dumps(report, ensure_ascii=False, indent=2))
