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
| Proposed | stage2_off | wafer16_mixed11_clean3 | n016_f008_m008_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 142.1+/-0 | 142.2 | 0.02354 | 142.1 | 1530 | 0 | 2766 | 553 | n/a |
| Proposed | stage2_off | wafer16_pure22_clean3 | n016_f000_m016_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 0 | 7199+/-0 | 7200 | 0.02626 | 1.44e+04 | 3512 | 1.03 | 3.654e+05 | 28 | n/a |
| Proposed | stage2_off | wafer16_pure41_clean3 | n016_f016_m000_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 0.4833+/-0 | 0.5447 | 0.03894 | 0.4833 | 944 | 0 | 0 | 104 | n/a |
| Proposed | stage2_off | wafer17_mixed11_clean3 | n017_f009_m008_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 385.2+/-0 | 385.3 | 0.02803 | 385.2 | 1976 | 0 | 6562 | 150 | n/a |
| Proposed | stage2_off | wafer17_pure22_clean3 | n017_f000_m017_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 0 | 7196+/-0 | 7197 | 0.02405 | 1.44e+04 | 3752 | 0.9123 | 3.436e+05 | 28 | n/a |
| Proposed | stage2_off | wafer17_pure41_clean3 | n017_f017_m000_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 1.905+/-0 | 2.043 | 0.03786 | 1.905 | 1494 | 0 | 200 | 74 | n/a |
| Proposed | stage2_off | wafer20_mixed11_clean3 | n020_f010_m010_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 0 | 7200+/-0 | 7201 | 0.02749 | 1.44e+04 | 2582 | 0.1812 | 1.115e+05 | 551 | n/a |
| Proposed | stage2_off | wafer20_pure22_clean3 | n020_f000_m020_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 1754+/-0 | 1754 | 0.03244 | 1754 | 2126 | 0 | 4095 | 608 | n/a |
| Proposed | stage2_off | wafer20_pure41_clean3 | n020_f020_m000_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 1.907+/-0 | 2.134 | 0.02904 | 1.907 | 1598 | 0 | 200 | 86 | n/a |
| Proposed | stage2_off | wafer8_mixed11_clean3 | n008_f004_m004_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 1.557+/-0 | 1.586 | 0.01438 | 1.557 | 1146 | 0 | 23.74 | 68 | n/a |
| Proposed | stage2_off | wafer8_pure22_clean3 | n008_f000_m008_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 3.688+/-0 | 3.724 | 0.4545 | 3.688 | 1070 | 0 | 60.44 | 28 | n/a |
| Proposed | stage2_off | wafer8_pure41_clean3 | n008_f008_m000_p4x1_180_p2x2_90x2_clean3 | 1 | 1 | 1 | 0.05178+/-0 | 0.06812 | 0.02174 | 0.05178 | 610 | 0 | 0 | 68 | n/a |

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
