# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `proposed`
- Seeds: `[1]`
- Time limit: `1200.0 s` per run
- Schedule-stability profile: `stage2_off`
- Instances: `12`
- Empty suites: `0`

## Aggregated results

| Method | Stability | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Proposed | stage2_off | wafer16_mixed11_clean3 | n016_f008_m008_proc180_clean3 | 1 | 1 | 1 | 326.4+/-0 | 326.5 | 0.05777 | 326.4 | 1890 | 0 | 2.484e+04 | 1e+04 | n/a |
| Proposed | stage2_off | wafer16_pure22_clean3 | n016_f000_m016_proc180_clean3 | 1 | 1 | 1 | 38.52+/-0 | 38.66 | 0.0213 | 38.52 | 1856 | 0 | 748 | 1e+04 | n/a |
| Proposed | stage2_off | wafer16_pure41_clean3 | n016_f016_m000_proc180_clean3 | 1 | 1 | 1 | 0.6526+/-0 | 0.7575 | 0 | 0.6526 | 944 | 0 | 100 | 1e+04 | n/a |
| Proposed | stage2_off | wafer17_mixed11_clean3 | n017_f009_m008_proc180_clean3 | 1 | 1 | 1 | 507.8+/-0 | 507.9 | 0.03399 | 507.8 | 1890 | 0 | 3.762e+04 | 1e+04 | n/a |
| Proposed | stage2_off | wafer17_pure22_clean3 | n017_f000_m017_proc180_clean3 | 1 | 1 | 1 | 10.92+/-0 | 11.06 | 0.02161 | 10.92 | 2684 | 0 | 450.4 | 1e+04 | n/a |
| Proposed | stage2_off | wafer17_pure41_clean3 | n017_f017_m000_proc180_clean3 | 1 | 1 | 1 | 2.666+/-0 | 2.807 | 0.04029 | 2.666 | 1002 | 0 | 299 | 1e+04 | n/a |
| Proposed | stage2_off | wafer20_mixed11_clean3 | n020_f010_m010_proc180_clean3 | 1 | 1 | 1 | 654+/-0 | 654.2 | 0.02281 | 654 | 2658 | 0 | 7747 | 1e+04 | n/a |
| Proposed | stage2_off | wafer20_pure22_clean3 | n020_f000_m020_proc180_clean3 | 1 | 1 | 1 | 2.1+/-0 | 2.248 | 0.07007 | 2.1 | 2760 | 0 | 1.014 | 1e+04 | n/a |
| Proposed | stage2_off | wafer20_pure41_clean3 | n020_f020_m000_proc180_clean3 | 1 | 1 | 1 | 2.023+/-0 | 2.146 | 0 | 2.023 | 1106 | 0 | 200 | 1e+04 | n/a |
| Proposed | stage2_off | wafer8_mixed11_clean3 | n008_f004_m004_proc180_clean3 | 1 | 1 | 1 | 0.5666+/-0 | 0.6358 | 0.02382 | 0.5666 | 834 | 0 | 0 | 1e+04 | n/a |
| Proposed | stage2_off | wafer8_pure22_clean3 | n008_f000_m008_proc180_clean3 | 1 | 1 | 1 | 1.568+/-0 | 1.607 | 0.6356 | 1.568 | 768 | 0 | 44.51 | 1e+04 | n/a |
| Proposed | stage2_off | wafer8_pure41_clean3 | n008_f008_m000_proc180_clean3 | 1 | 1 | 1 | 0.1049+/-0 | 0.1272 | 0.04887 | 0.1049 | 610 | 0 | 0 | 86 | n/a |

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
