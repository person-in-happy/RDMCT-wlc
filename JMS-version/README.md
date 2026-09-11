# JMS稿件与本地排版版本

- `JMS_Review_CN.tex`、`JMS_Review_CN.pdf`：中文稿件与核对PDF。
- `JMS_Submission_EN.tex`、`JMS_Submission_EN.pdf`：同步的英文稿件与PDF。
- `output/submission/`：英文投稿PDF、自包含源文件包`JMS_Source_EN.zip`、可编辑`Highlights.txt`。
- `figures/`：正文10张图的中英文图件、矢量源文件、图2原始照片与绘图脚本。
- `figures/temp/`：此前要求的8片/24片补充甘特图，另含`_4s`版本；未收入正文投稿包。
- `results/`与`warm_starts/`：保留的实验依据。原始实验和证书同时保留在仓库的`JMS/results/`和`cie/results/`。

图2用于展示商业PECVD腔室背景，并非本文建模设备的实测照片。原图无Logo，未裁切、修补或生成性编辑。作者已确认先完成本地排版；官网未提供论文转载许可，正式投稿前仍需获得图片权利人的授权。英文源包中的`FIGURE_PERMISSION.txt`保留这一待办。

在仓库根目录重新构建：

```powershell
& .\JMS-version\tools\build_submission.ps1 -Python G:\conda\python.exe
```

构建脚本核对公式和章节数量，独立解压编译英文源文件包，并在成功后清理自身编译目录。需要Python、PyMuPDF、XeLaTeX及文中声明的标准LaTeX包。

正文甘特图使用`figures/render_manuscript_gantt.py`重绘；图2现使用Syskey官网PECVD开腔实物照片，原始JPEG和来源记录见`figures/origin/pecvd_official/`；旧CIM框架图不再引用。补充图使用`render_temp_ll_release.py`和`render_temp_4s.py`。绘图使用项目Python环境。

已确认的编译日志与审阅报告已删除。混存历史源代码、模型和解的旧目录，以及旧图件，完整保存在`../manuscript_archive/20260911_finalization/`，不属于投稿包。37个冻结模型已迁至`results/frozen_models_20260906/`，原路径与SHA-256映射见`results/frozen_model_paths.json`。
