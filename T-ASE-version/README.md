# T-ASE 转投版本

核对日期：2026-09-15。原始 `JMS-version` 未覆盖，冻结实验未重跑。

## 文件

- `TASE_Submission_EN.tex/pdf`：IEEE 双栏、双匿名英文正文。
- `TASE_Supplement_EN.tex/pdf`：模型符号、约束及求解网络的展开细节。
- `TASE_Review_CN.tex/pdf`：保留原稿完整论证的中文内部核对版；不是压缩英文正文的逐段翻译，不用于英文投稿。
- `SUBMISSION_GUIDE_CN.md`：官方要求、适配记录及尚需作者核对事项。
- `EXPERIMENTS_CN.md`：补实验优先级、实际命令及验收标准。
- `Cover_Letter_EN.txt`：匿名投稿信草稿。
- `evidence/`：来源哈希和本次检查记录；不上传给审稿人。

## 构建

从项目根目录运行：

```powershell
Set-Location D:\git\git\RDMCT-A3C
python .\T-ASE-version\tools\build.py --lang all
```

`tools/prepare_manuscripts.py` 等迁移脚本仅记录本次转投过程；请直接编辑最终 TeX 后用 `build.py` 编译，不要重新运行迁移脚本覆盖后续人工修改。

## 关键科学边界

模式比较采用 180 s 对 90+90 s、模块驻留上限 10000 s；冻结算法基准的标称并行加工和每次链式曝光均为 180 s、模块驻留上限 500 s。两组分别回答模式选择和同实例求解性能问题，不能混用。

保留 SPBS 和等总预算精修的结果；学习选割相对 HEM 未显著领先。原始算法基准采用根节点割分离配置，正文已将 SCIP 标作受控配置基线。参数敏感性不是随机扰动执行验证，计算可行性也不是实机验证。

上传包不包含作者姓名、单位、邮箱、CRediT、内部审查说明或本地结果路径。作者信息应在投稿系统中另填。


## ??????

?? tools/resumable_experiments.py ? --resume ????? --execute ??????????? tools/resumable_model_scale.py ?????????????????????????? SPBS ??????? [EXPERIMENTS_CN.md](EXPERIMENTS_CN.md)?
