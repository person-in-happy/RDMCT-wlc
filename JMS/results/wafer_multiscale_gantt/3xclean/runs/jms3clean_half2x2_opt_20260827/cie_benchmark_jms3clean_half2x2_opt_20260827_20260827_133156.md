# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `proposed`
- Seeds: `[1]`
- Time limit: `7200.0 s` per run
- Schedule-stability profile: `stage2_off`
- Instances: `12`
- Empty suites: `0`

## Aggregated results

| Method | Stability | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Proposed | stage2_off | wafer16_mixed11_clean3 | n016_f008_m008_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 22.88+/-0 | 22.95 | 0.02108 | 22.88 | 1530 | 0 | 86.92 | 1e+04 | n/a |
| Proposed | stage2_off | wafer16_pure22_clean3 | n016_f000_m016_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 941.4+/-0 | 941.5 | 0.0224 | 941.4 | 1894 | 0 | 3.824e+04 | 1e+04 | n/a |
| Proposed | stage2_off | wafer16_pure41_clean3 | n016_f016_m000_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 0.5345+/-0 | 0.594 | 0 | 0.5345 | 944 | 0 | 100 | 1e+04 | n/a |
| Proposed | stage2_off | wafer17_mixed11_clean3 | n017_f009_m008_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 381.2+/-0 | 381.3 | 0.02461 | 381.2 | 1976 | 0 | 4308 | 1e+04 | n/a |
| Proposed | stage2_off | wafer17_pure22_clean3 | n017_f000_m017_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 66.12+/-0 | 66.23 | 0.02232 | 66.12 | 1964 | 0 | 3020 | 1e+04 | n/a |
| Proposed | stage2_off | wafer17_pure41_clean3 | n017_f017_m000_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 2.062+/-0 | 2.216 | 0.01725 | 2.062 | 1494 | 0 | 200 | 1e+04 | n/a |
| Proposed | stage2_off | wafer20_mixed11_clean3 | n020_f010_m010_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 29.64+/-0 | 29.8 | 0.1047 | 29.64 | 2208 | 0 | 404.9 | 1e+04 | n/a |
| Proposed | stage2_off | wafer20_pure22_clean3 | n020_f000_m020_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 0 | 7200+/-0 | 7201 | 0.01509 | 1.44e+04 | 2126 | 0.005201 | 8570 | 1e+04 | n/a |
| Proposed | stage2_off | wafer20_pure41_clean3 | n020_f020_m000_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 1.811+/-0 | 1.918 | 0.02073 | 1.811 | 1598 | 0 | 100 | 1e+04 | n/a |
| Proposed | stage2_off | wafer8_mixed11_clean3 | n008_f004_m004_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 0.4808+/-0 | 0.541 | 0.02164 | 0.4808 | 1146 | 0 | 9.355 | 1e+04 | n/a |
| Proposed | stage2_off | wafer8_pure22_clean3 | n008_f000_m008_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 3.241+/-0 | 3.305 | 0.353 | 3.241 | 1070 | 0 | 14.68 | 1e+04 | n/a |
| Proposed | stage2_off | wafer8_pure41_clean3 | n008_f008_m000_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 0.08695+/-0 | 0.1041 | 0.04009 | 0.08695 | 610 | 0 | 0 | 86 | n/a |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 0 | n/a | n/a% | n/a% |
| structure_with_greedy | HEM -> HEM + Structure | 0 | n/a | n/a% | n/a% |
| structure_with_beam | HEM + Beam -> Proposed | 0 | n/a | n/a% | n/a% |
| beam_with_structure | HEM + Structure -> Proposed | 0 | n/a | n/a% | n/a% |

## Interpretation guardrails

- Compare methods only on identical instance-seed pairs.
- Metric directions: solving time, PAR-2, best objective, gap, and PDI are all lower-is-better for these minimization models.
- Best objective measures incumbent quality; gap measures remaining certificate uncertainty; PDI measures anytime primal-dual progress; time is a speed claim only when solve outcomes are comparable.
- Mean node count is diagnostic, not a monotone quality metric: fewer nodes can mean an efficient tree or a stalled root relaxation.
- Report timeout-aware gap and primal-dual integral beside wall-clock time.
- `adaptive_cutsel` is the original four-parameter SCIP hybrid selector interface. It is the full learned ACS method only when `--acs_predictions` contains held-out predictions from a separately trained ACS model.
- `hem` requires a separately trained 13-feature checkpoint; using the 23-feature checkpoint would invalidate the ablation.
- `hem_beam` reuses the exact HEM checkpoint and changes only greedy to beam decoding.
- `hem_structure` reuses the exact Proposed checkpoint and structure reranking, changing only beam to greedy decoding.
- `a3c` and `beam_search` share the same independently trained flat-A3C checkpoint and differ only in greedy versus beam decoding.
- `proposed` uses the separately trained 23-feature role-submodular checkpoint; every method receives the same SCIP, memory, warm-start, instance, and solver-seed limits.
- Schedule wait and cadence metrics are observational in the benchmark; no method receives an extra postprocessing budget.
