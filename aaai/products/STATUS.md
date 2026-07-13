# AAAI-27 Draft Status

This directory uses the official AAAI-27 Author Kit downloaded on 2026-07-05.

Files:

- `rdmct_aaai27.tex`: anonymous AAAI-27 main-paper draft;
- `rdmct_aaai27.bib`: bibliography;
- `rdmct_pipeline.pdf`: paper pipeline figure;
- `rdmct_reproducibility.tex`: wrapper for the official checklist;
- `ReproducibilityChecklist.tex`: checklist with honest draft answers;
- `rdmct_reproducibility.pdf`: compiled two-page checklist draft;
- `AuthorKit27/`: unmodified official template, style, bibliography style, and reproducibility checklist;
- `AuthorKit27.zip`: original official download.

The draft is format-ready but not yet scientifically submission-ready.
Before submission, replace the dashes in the main comparison table with frozen multi-seed results, add hardware details, update the provisional checklist answers, and rerun the page/overflow/font checks.

The fixed-quota repair was replaced by policy-anchored role-submodular completion on 2026-07-07. Existing 23D checkpoints predate this rollout transition and are intentionally rejected by the new `cut_postprocessor_schema`; retrain them under `aaai/models/proposed_submodular`.

Do not add performance claims before independently trained HEM-13D, role-23D-feature-only, and role-23D-submodular checkpoints, the Adaptive Cut Selection baseline, multi-seed Petri experiments, and cross-family/MIPLIB experiments are complete. The formal benchmark report must show `claim_ready: true` from paired Wilcoxon tests with Holm correction.
