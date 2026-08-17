# CIE anonymous source-bundle manifest

Freeze date: 2026-08-17 (Asia/Shanghai). The authoritative manuscript is the analysis-focused version.

## Main manuscript source

Archive: `CIE_RDMCTHBS_anonymous_source_20260817.zip`
SHA-256: `389188585ED0DD758DA354E680F9A206A726BAE0EB274E8A4889808ACA4F9D2C`

Flat archive contents:

- `manuscript.tex`
- `manuscript.bbl`
- `rdmct_cie_references.bib`
- `Figure_DOE_PDI_effects.png`

The source was copied from `rdmct_cie_analysis_focused.tex`; that file already identifies the author as `Anonymous author(s)`, so the one-line wrapper is not needed inside the archive.

## Supplement source

Archive: `CIE_RDMCTHBS_anonymous_supplement_source_20260817.zip`
SHA-256: `FBB5276FB4C20B9B59CE07339D8E35194F39B7DB1E73082ACEF715B9EC8CABB0`

Flat archive contents:

- `supplement.tex`
- `Figure_S1_DOE_diagnostics.png`

## Independent verification

Each archive was extracted into a new temporary directory. The main archive passed `pdflatex`, `bibtex`, and two final `pdflatex` passes; the supplement passed two `pdflatex` passes. All citations and references resolved, and neither log contained a LaTeX error, undefined citation/reference, or overfull box.

Every packaged member matched its authoritative source by SHA-256. The rebuilt 28-page manuscript and 10-page supplement had exactly the same extracted text as the corresponding frozen PDFs. This verifies source closure and rendered textual content; it does not claim that the PDF binaries are byte-identical, because job names, timestamps, and other compilation metadata may differ.

Source files, figures, rebuilt PDF text, and PDF metadata were scanned for author names, affiliations, e-mail addresses, personal repository links, ORCID identifiers, and local drive paths. No identity leak was found.

## Upload roles

Upload `manuscript_analysis_focused_anonymous.pdf` as the anonymous manuscript, the main ZIP as its editable source, `highlights_analysis_focused.txt` as the separate Highlights file, `title_page.pdf` separately as the non-reviewer title page, and `rdmct_cie_supplement.pdf` as supplementary material. Use the supplement ZIP only when the submission system requests editable supplement source.

Do not include title-page, cover-letter, metadata, Chinese-review, internal-audit, experiment-result, checkpoint, or log files in either anonymous source archive.

The archives must be regenerated after any manuscript, bibliography, figure, supplement, or anonymous data-link change.
