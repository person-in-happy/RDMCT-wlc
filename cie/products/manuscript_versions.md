# Manuscript versions

## Preserved original version

The original manuscript requested by the author remains unchanged. Its frozen SHA-256 values are:

| File | SHA-256 |
| --- | --- |
| `rdmct_cie_draft.tex` | `BF6EC29B711B0B811B8943376483CE7AD64F3B2448F4E64C986015F13E922252` |
| `rdmct_cie_draft_zh.tex` | `98F657E690C1A40C4539A2CB18748DB7EBD0769CF86A9BD24F902739FD60C8C8` |
| `rdmct_cie_draft.pdf` | `B22FFA339C28AC9580827F3099D3F34E9F8CC12AC34F294DE0A329087D12A4B2` |
| `rdmct_cie_draft_zh.pdf` | `F89B9EE37998603D77526F8DB12BE9F99E0A6892547EA9620B897023BDC53002` |

## Analysis-focused version

- `rdmct_cie_analysis_focused.tex/pdf`: newly written English CIE manuscript.
- `rdmct_cie_analysis_focused_zh.tex/pdf`: synchronized Chinese review manuscript.
- `manuscript_analysis_focused_anonymous.tex/pdf`: independent anonymous submission entry and compiled PDF for the new version.
- `highlights_analysis_focused.txt`: English Highlights dedicated to the new version; the original Highlights file is unchanged.
- `submission_metadata_analysis_focused.md`: submission metadata and outstanding author confirmations for the new version.
- `CIE_RDMCTHBS_anonymous_source_20260817.zip`: flat anonymous main-manuscript source bundle; SHA-256 `389188585ED0DD758DA354E680F9A206A726BAE0EB274E8A4889808ACA4F9D2C`.
- `CIE_RDMCTHBS_anonymous_supplement_source_20260817.zip`: separate anonymous supplement source bundle; SHA-256 `FBB5276FB4C20B9B59CE07339D8E35194F39B7DB1E73082ACEF715B9EC8CABB0`.

This version reorganizes the paper around industrial logic, model decisions, mechanism-level evidence, and result interpretation. Training hyperparameters and run-matrix details are not presented as the main narrative. The new version adds a dual-source equipment-flow diagram and an explicit mapping from industrial rules to mathematical mechanisms and scheduling consequences.

Both ZIP archives were extracted into fresh temporary directories and compiled from their packaged files. The main bundle passed `pdflatex -> bibtex -> pdflatex -> pdflatex`; the supplement passed two `pdflatex` passes. Every packaged member matched its authoritative source by SHA-256; all references resolved; neither log contained a LaTeX error, undefined citation/reference, or overfull box; and source, figure, rebuilt-PDF text, and PDF-metadata identity scans returned no matches. The rebuilt 28-page manuscript and 10-page supplement had exactly the same extracted text as the corresponding frozen PDFs. No byte-identical-PDF claim is made because compilation metadata may differ.

The formal OOD experiment is complete: all 729 runs reached the time limit but returned independently validated incumbents, with no runner or solution-writing errors. Across the nine larger configurations, adaptive cut selection achieved the lowest mean OOD PDI; the globally Holm-adjusted method contrasts were not significant. The analysis-focused manuscripts therefore use OOD as evidence of feasible-schedule delivery under distribution shift, not as evidence that RDMCT-HBS ranks first out of distribution.
