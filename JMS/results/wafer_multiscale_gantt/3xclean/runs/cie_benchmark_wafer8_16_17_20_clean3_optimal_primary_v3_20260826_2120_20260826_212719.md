# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `proposed`
- Seeds: `[1]`
- Time limit: `600.0 s` per run
- Schedule-stability profile: `stage2_off`
- Instances: `12`
- Empty suites: `0`

## Aggregated results

| Method | Stability | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Proposed | stage2_off | wafer16_mixed11_clean3 | n016_f008_m008_proc180_clean3 | 1 | 1 | 1 | 277.7+/-0 | 277.8 | 0.06486 | 277.7 | 1890 | 0 | 2.102e+04 | 1e+04 | n/a |
| Proposed | stage2_off | wafer16_pure22_clean3 | n016_f000_m016_proc180_clean3 | 1 | 1 | 1 | 44.24+/-0 | 44.3 | 0.01646 | 44.24 | 1856 | 0 | 2146 | 1e+04 | n/a |
| Proposed | stage2_off | wafer16_pure41_clean3 | n016_f016_m000_proc180_clean3 | 1 | 1 | 1 | 0.4868+/-0 | 0.5757 | 0 | 0.4868 | 944 | 0 | 0 | 1e+04 | n/a |
| Proposed | stage2_off | wafer17_mixed11_clean3 | n017_f009_m008_proc180_clean3 | 1 | 1 | 1 | 62.46+/-0 | 62.59 | 0.01812 | 62.46 | 1890 | 0 | 201.3 | 1e+04 | n/a |
| Proposed | stage2_off | wafer17_pure22_clean3 | n017_f000_m017_proc180_clean3 | 1 | 1 | 1 | 10.48+/-0 | 10.58 | 0.01478 | 10.48 | 2684 | 0 | 459.4 | 1e+04 | n/a |
| Proposed | stage2_off | wafer17_pure41_clean3 | n017_f017_m000_proc180_clean3 | 1 | 1 | 1 | 1.001+/-0 | 1.129 | 0 | 1.001 | 1002 | 0 | 100 | 1e+04 | n/a |
| Proposed | stage2_off | wafer20_mixed11_clean3 | n020_f010_m010_proc180_clean3 | 1 | 1 | 1 | 30.13+/-0 | 30.29 | 0.01929 | 30.13 | 2658 | 0 | 195.8 | 1e+04 | n/a |
| Proposed | stage2_off | wafer20_pure22_clean3 | n020_f000_m020_proc180_clean3 | 1 | 1 | 1 | 131.2+/-0 | 131.3 | 0.01656 | 131.2 | 2760 | 0 | 6322 | 1e+04 | n/a |
| Proposed | stage2_off | wafer20_pure41_clean3 | n020_f020_m000_proc180_clean3 | 1 | 1 | 1 | 1.19+/-0 | 1.278 | 0 | 1.19 | 1106 | 0 | 100 | 1e+04 | n/a |
| Proposed | stage2_off | wafer8_mixed11_clean3 | n008_f004_m004_proc180_clean3 | 1 | 1 | 1 | 0.3279+/-0 | 0.3964 | 0.02176 | 0.3279 | 834 | 0 | 0 | 1e+04 | n/a |
| Proposed | stage2_off | wafer8_pure22_clean3 | n008_f000_m008_proc180_clean3 | 1 | 1 | 1 | 0.5497+/-0 | 0.6059 | 0.3594 | 0.5497 | 768 | 0 | 45.66 | 1e+04 | n/a |
| Proposed | stage2_off | wafer8_pure41_clean3 | n008_f008_m000_proc180_clean3 | 1 | 1 | 1 | 0.07866+/-0 | 0.09481 | 0.03585 | 0.07866 | 610 | 0 | 0 | 86 | n/a |

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
