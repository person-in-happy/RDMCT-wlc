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
| Proposed | stage2_off | mode_n024_clean03_mixed11 | n024_clean03_equal_total180 | 1 | 1 | 0 | 7200+/-0 | 7200 | 0.02364 | 1.44e+04 | 2324 | 0.009557 | 5.156e+04 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n024_clean03_pure22 | n024_clean03_equal_total180 | 1 | 0 | 0 | 7199+/-0 | 7200 | 0.03974 | 1.44e+04 | n/a | n/a | n/a | n/a | n/a |
| Proposed | stage2_off | mode_n024_clean03_pure41 | n024_clean03_equal_total180 | 1 | 1 | 1 | 6.032+/-0 | 6.209 | 0.4292 | 6.032 | 1268 | 0 | 598.8 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n024_clean04_mixed11 | n024_clean04_equal_total180 | 1 | 1 | 0 | 7200+/-0 | 7200 | 0.02973 | 1.44e+04 | 1827 | 0.02988 | 8.323e+04 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n024_clean04_pure22 | n024_clean04_equal_total180 | 1 | 1 | 0 | 7200+/-0 | 7200 | 0.09018 | 1.44e+04 | 2928 | 1.182 | 3.902e+05 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n024_clean04_pure41 | n024_clean04_equal_total180 | 1 | 1 | 1 | 2.92+/-0 | 3.059 | 0 | 2.92 | 1268 | 0 | 300 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n024_clean05_mixed11 | n024_clean05_equal_total180 | 1 | 1 | 1 | 1985+/-0 | 1985 | 0.02068 | 1985 | 1796 | 0 | 2.157e+04 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n024_clean05_pure22 | n024_clean05_equal_total180 | 1 | 1 | 0 | 7200+/-0 | 7200 | 0.05684 | 1.44e+04 | 1769 | 0.2285 | 1.419e+05 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n024_clean05_pure41 | n024_clean05_equal_total180 | 1 | 1 | 1 | 3.013+/-0 | 3.162 | 0 | 3.013 | 1268 | 0 | 300 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n024_clean06_mixed11 | n024_clean06_equal_total180 | 1 | 1 | 0 | 7200+/-0 | 7201 | 0.05473 | 1.44e+04 | 1263 | 0.104 | 1.169e+05 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n024_clean06_pure22 | n024_clean06_equal_total180 | 1 | 1 | 0 | 7200+/-0 | 7200 | 0.05184 | 1.44e+04 | 1880 | 0.3056 | 3.193e+05 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n024_clean06_pure41 | n024_clean06_equal_total180 | 1 | 1 | 1 | 1.559+/-0 | 1.701 | 0.05273 | 1.559 | 1268 | 0 | 198.8 | 1e+04 | n/a |

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
