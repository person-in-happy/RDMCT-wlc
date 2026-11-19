# Current English submission

The English source is `../JMS_Submission_EN.tex`. It is assembled from the translated prose in `manuscript_body_en.tex` and the equations, table values, and bibliography in the current Chinese source. The build checks its Chinese-source hash so later Chinese edits cannot silently produce a partly outdated translation.

The title follows the author's live revision to emphasize full-occupancy processing. Funding was confirmed as absent on 14 November 2026. On 15 November 2026, the author confirmed that only the existing manuscript-preparation AI declaration should be retained. This choice is recorded in the submission materials.

Build from the repository root:

```powershell
G:\conda\python.exe -X utf8 JMS-version/tools/build_submission_en.py --document-python "C:/Program Files/WindowsApps/OpenAI.CodexPrimaryRuntime.v26-1112-611-0_26.1112.611.0_x64__3k8sg7r9htsxt/dependencies/python/python.exe" --render-docx
```

Regenerate English diagrams and Gantt charts only when their rendering changes:

```powershell
G:\conda\python.exe -X utf8 JMS-version/tools/render_submission_figures_en.py
```

The rendering script reads frozen records and performs no optimization. Figures 5 and 6 retain their original intervals, share a four-column action legend, and remain at single-column size. Their time labels and units appear after the final tick on the same line. Figures 3, 5, and 6 contain their symbol and line-style explanations inside the images. Extraneous vertical margins are trimmed from all six figures while preserving their printed scale; the crop check preserves every visible drawing pixel. The matching Chinese figures are regenerated with `tools/render_compact_figures_cn.py` and stored in `figures/compact_20261117/`.

The deliverables are in `../output/submission/`. The outer ZIP is a delivery bundle; the inner LaTeX ZIP is a flat submission-source archive. `UPLOAD_README.txt` maps files to upload roles and records the official rules actually checked, the remaining journal-guide checks, and the author's confirmed disclosure choice. It is an upload aid, not part of the manuscript.

`translation_checks.json` and `validation.json` record source hashes, cross-language equation and table consistency, first-citation reference order, author order, PDF builds, and independent source-archive rebuilding. PDF previews and Word-document previews are in `../output/.build_en/`. The bundled DOCX renderer was attempted on 17 November 2026 but could not convert the documents because LibreOffice is unavailable in this Windows environment. The five Word files were instead rendered with installed Microsoft Word and inspected as page images. OOXML generation uses the configured bundled Python runtime.

Raw results, models, checkpoints, historical review records, and the separate `../../JMS/` manuscript are outside this submission cleanup.

The latest 17 November revision uses the English manuscript as the editorial reference and synchronizes the same changes back to the Chinese review source. Tables 1 and 2 retain concise definitions; equipment defaults and learning/solver settings are consolidated in Section 4.1. The former Section 4.4 on coupled continuous-processing, cleaning, and inventory effects, including its three tables and one figure, has been removed. Repeated descriptions of objectives, initialization, selection, decoding, and schedule results have been shortened. The remaining six figures have been renumbered; former Figures 6 and 7 are now Figures 5 and 6.

Lincong Wei is first author; Lizhen Shao is second and corresponding author. The objective comparison retains the four-product mixed and two 16-product instances, in a single-column table with centered cells. The English manuscript contains 34 numbered equations, one unnumbered joint-objective expression, 11 tables, 6 figures, and 32 references. The reviewed English layout has 17 pages (previously 20), balanced final columns, centered table cells, and no LaTeX warnings. The synchronized Chinese layout has 15 pages (previously 17). `visual_review.json` records the current layout and delivery checks; `revisions/20261117_en_compact/` preserves the before-state and change audit. The older `cleanup.json` is a historical record, not the current package manifest.

The subsequent Table 8 revision retains the four instance rows using SCIP's default separation settings and removes the separation-setting column. Its 72-run count, accompanying discussion, and related component interpretation are synchronized in both languages. The removed root-separation comparisons remain in the frozen research records and the revision snapshot, while the manuscript presents the retained default-setting results. `revisions/20261117_remove_root_separation/` records this revision and its checks.

The terminology and translation revision unifies batch makespan, total waiting time, maximum individual waiting time, and rhythm deviation across the Chinese and English manuscripts, captions, figure legends, cover letter, and submission metadata. It corrects robot access to two chamber positions, distinguishes wafer-carrying positions from robot hands, and clarifies the processing time excluded from chamber residency limits. Mathematical expressions, numerical results, citation order, and frozen schedule evidence are unchanged. The revised English abstract has 213 words. `revisions/20261117_terminology_translation/` preserves the before-state, replacement records, and final checks.

The abbreviation-consistency revision uses CTs throughout the manuscript prose and adjusts singular constructions grammatically. LP, LL, AL, MILP, and HEM definitions are aligned with their first uses; AL denotes the aligner. Context-dependent LP/LPs and LL/LLs forms are retained. The English training-set description uses MILP scheduling instances. Scientific content, equations, numerical tables, figure assets, and bibliography entries are unchanged. A concurrent Chinese abstract punctuation edit was preserved. The before-state and checks are in `revisions/20261117_abbreviation_consistency/`.
