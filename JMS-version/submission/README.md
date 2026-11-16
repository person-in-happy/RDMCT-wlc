# Current English submission

The English source is `../JMS_Submission_EN.tex`. It is assembled from the translated prose in `manuscript_body_en.tex` and the equations, table values, and bibliography in the current Chinese source. The build checks its Chinese-source hash so later Chinese edits cannot silently produce a partly outdated translation.

The title follows the author's live revision to emphasize full-occupancy processing. Funding was confirmed as absent on 14 November 2026. On 15 November 2026, the author confirmed that only the existing manuscript-preparation AI declaration should be retained. This choice is recorded in the submission materials.

Build from the repository root:

```powershell
G:\conda\python.exe -X utf8 JMS-version/tools/build_submission_en.py --render-docx
```

Regenerate English diagrams and Gantt charts only when their rendering changes:

```powershell
G:\conda\python.exe -X utf8 JMS-version/tools/render_submission_figures_en.py
```

The rendering script reads frozen records and performs no optimization. Figures 6 and 7 retain their original intervals, share a four-column legend, and remain at single-column size. Figure 5 retains only product processing in its top lane and auxiliary loan intervals below.

The deliverables are in `../output/submission/`. The outer ZIP is a delivery bundle; the inner LaTeX ZIP is a flat submission-source archive. `UPLOAD_README.txt` maps files to upload roles and records the official rules actually checked, the remaining journal-guide checks, and the author's confirmed disclosure choice. It is an upload aid, not part of the manuscript.

`translation_checks.json` and `validation.json` record source hashes, cross-language equation and table consistency, reference checks, PDF builds, and independent source-archive rebuilding. PDF previews and Word-document previews are in `../output/.build_en/`. The bundled DOCX renderer could not start because its Python `pdf2image` dependency was absent; the five Word files were rendered with installed Microsoft Word and inspected as page images. OOXML generation uses Python's standard library because no workspace dependency loader is available in this Windows session.

Raw results, models, checkpoints, historical review records, and the separate `../../JMS/` manuscript are outside this submission cleanup.

The reviewed English layout has 18 pages, balanced final columns, centered table cells, and no LaTeX warnings. Figure spacing and paragraph boundaries around floats were adjusted to preserve readable single-column schedules without sparse trailing pages. `visual_review.json` records the final layout review and delivery checks; `cleanup.json` lists removed obsolete submission files and their prior hashes.
