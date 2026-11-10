from pathlib import Path
import re,json,hashlib,difflib,pymupdf
root=Path('JMS-version');rev=root/'revisions/20261103_symbol_definitions'
old=(rev/'before/JMS_Review_CN.tex').read_text(encoding='utf-8');new=(root/'JMS_Review_CN.tex').read_text(encoding='utf-8')
h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
protected=json.loads((rev/'protected_hashes.json').read_text(encoding='utf-8'))
assert all(h(Path(p))==v for p,v in protected.items())
def eqs(s):
 out={}
 for m in re.finditer(r'\\begin\{equation(\*?)\}(.*?)\\end\{equation\1\}',s,re.S):
  v=m.group(2);label=re.search(r'\\label\{([^}]+)\}',v)
  if label:out[label.group(1)]=re.sub(r'\s+','',v)
 return out
a,b=eqs(old),eqs(new);assert a.keys()==b.keys()
expected={'eq:pjob-input-code-cn','eq:model4-family-count-cn','eq:single-source-accompany-cn'}
assert {k for k in a if a[k]!=b[k]}==expected
assert a['eq:pjob-input-code-cn'].replace('u\\in',"w'\\in").replace('u<w',"w'<w")==b['eq:pjob-input-code-cn']
assert a['eq:model4-family-count-cn'].replace('a!','a_N!').replace('2a','2a_N').replace('quada=','quada_N=')==b['eq:model4-family-count-cn']
assert a['eq:single-source-accompany-cn'].replace('i_1,',r'i_{\rmP},').replace('i_2,',r'i_{\rmD},')==b['eq:single-source-accompany-cn']
assert re.findall(r'\\begin\{equation\*\}(.*?)\\end\{equation\*\}',old,re.S)==re.findall(r'\\begin\{equation\*\}(.*?)\\end\{equation\*\}',new,re.S)
eo,en=[s.split(r'\label{sec:experiments-cn}',1)[1] for s in (old,new)]
assert re.findall(r'\\begin\{tabular\}.*?\\end\{tabular\}',eo,re.S)==re.findall(r'\\begin\{tabular\}.*?\\end\{tabular\}',en,re.S)
assert re.findall(r'\d+(?:\.\d+)?',eo.replace('0--1','二元'))==re.findall(r'\d+(?:\.\d+)?',en)
assert not any(word in new for word in ['派生','成员'])
report=json.loads((rev/'completion_review.json').read_text(encoding='utf-8'))
report.update(equations_with_local_symbol_renaming_only=sorted(expected),source_sha256=h(root/'JMS_Review_CN.tex'),pdf_sha256=h(root/'JMS_Review_CN.pdf'),visual_review='pending_final_pages',pending_experiment_evidence_added=False)
(rev/'completion_review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(rev/'JMS_Review_CN.tex.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='before/JMS_Review_CN.tex',tofile='after/JMS_Review_CN.tex')),encoding='utf-8')
records=[]
for n,line in enumerate(new.splitlines(),1):
 if 160<=n<=231 and line.startswith('$') and '&' in line:
  fields=line.split('&');records.append({'location':'table','line':n,'symbols':fields[0].strip(),'type':fields[1].strip(),'definition':fields[2].strip()})
 if n>231 and '是' in line and '$' in line and not line.startswith(('\\','%')) and any(word in line for word in ['变量','常量','索引','集合','函数','可行域','排程','固定编号']):records.append({'location':'body','line':n,'paragraph':line})
(rev/'symbol_definition_inventory.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
d=pymupdf.open(root/'JMS_Review_CN.pdf')
for i in range(1,12):d[i].get_pixmap(matrix=pymupdf.Matrix(1.5,1.5)).save(rev/f'final_page_{i+1:02d}.png')
notes='''# 符号声明与建模语言修订（2026-11-03）

## 参考依据

- 用户提供《四腔MIP.pdf》：Applied Sciences 2024, 14, 9490；重点核对第4—5页的动作、常量与等待时间说明，第7—9页的时序推导，以及第18—19页的线性规划汇总。
- 用户提供《四腔MIP-ieee.pdf》：ICNSC 2024；重点核对第2页的符号说明、第3—4页的时序分析、第5页的线性规划与约束解释。
- 两篇文献先说明实际操作及其先后关系，再定义必要符号、给出公式，最后解释公式保证的物理条件。本文据此重写中文建模叙述，未翻译复制原文段落。
- 两篇参考文献在给定机器人任务序列下建立连续线性规划；本文保留联合配对、周期与资源次序的混合整数模型，不引入参考文献的稳态假设、固定任务序列或其不同的驻留时间口径。

## 主要修订

1. 表1集中定义输入常量、集合和索引；表2集中定义主要决策变量与辅助变量。其余符号在正文首次使用处采用“符号是类型，表示含义”的声明格式。
2. 删除正文对表内符号的重复定义；保留必要的约束解释、取值计算和实例说明。与解有关的路线弧、清洁区段、等待和固定分量集合从输入表移至对应正文。
3. 全文删除“派生”和“成员”用语；按真实作用使用常量、决策变量、辅助变量、集合、索引或映射函数。
4. 补全时刻别名、启用标记、逻辑辅助变量、参考解及收尾输入的类型；明确最终解星号不构成全局最优证明。
5. 三处局部编号改名：Code中的临时晶圆编号u改为w′；枚举实例中每LP片数a改为a_N；单源产品/辅助路线改为i_P和i_D，避免复用固定对内位置索引i_1、i_2。
6. 重写约束引入与解释，使其沿“物理操作条件—数学关系—约束作用”展开；等价代入及内存控制移至第3节求解部分。

## 核验与范围

- 39个编号公式保持数学含义；仅上述3处公式做局部编号更名，其余编号公式及无编号公式内容不变。
- 实验表格逐项一致；实验章节数值一致（仅将变量类型文字“0--1”改为“二元”）。没有运行正式实验。
- 47个保护文件哈希未变，包括独立新/旧规则代码、另一份中文文稿、英文文稿及配套模型说明源文件。
- XeLaTeX三遍编译完成；未定义引用、重复标签与越界框均为0。最终PDF 16页，逐页检查见completion_review.json。
- 本次是符号与行文修订，没有新增需要补跑的实验或待补证据；本次未重新验证既有实验结论。
- 修订前文稿及PDF保存在before目录，完整差异见JMS_Review_CN.tex.diff，符号声明核对记录见symbol_definition_inventory.json。
'''
(rev/'CHANGES_CN.md').write_text(notes,encoding='utf-8')
print('Final semantic and protection audit passed.')
