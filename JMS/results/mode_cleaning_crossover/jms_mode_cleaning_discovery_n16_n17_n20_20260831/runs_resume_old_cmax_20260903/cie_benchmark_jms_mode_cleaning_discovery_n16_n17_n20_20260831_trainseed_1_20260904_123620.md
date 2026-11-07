# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `proposed`
- Seeds: `[1]`
- Time limit: `14400.0 s` per run
- Schedule-stability profile: `stage2_off`
- Instances: `14`
- Empty suites: `0`

## Aggregated results

| Method | Stability | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Proposed | stage2_off | mode_n020_clean06_mixed11 | n020_clean06_equal_total180 | 1 | 1 | 1 | 1042+/-0 | 1042 | 0.02659 | 1042 | 1542 | 0 | 3509 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n020_clean06_pure22 | n020_clean06_equal_total180 | 1 | 1 | 0 | 1.44e+04+/-0 | 1.44e+04 | 0.407 | 2.88e+04 | 1568 | 0.2366 | 3.227e+05 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n020_clean07_mixed11 | n020_clean07_equal_total180 | 1 | 1 | 1 | 251.2+/-0 | 251.4 | 0.03108 | 251.2 | 1147 | 0 | 2476 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n020_clean07_pure22 | n020_clean07_equal_total180 | 1 | 1 | 0 | 1.44e+04+/-0 | 1.44e+04 | 0.01288 | 2.88e+04 | 1060 | 0.4096 | 4.339e+05 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n020_clean07_pure41 | n020_clean07_equal_total180 | 1 | 1 | 1 | 0.6292+/-0 | 0.7125 | 0.08611 | 0.6292 | 1106 | 0 | 0 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n020_clean08_mixed11 | n020_clean08_equal_total180 | 1 | 1 | 1 | 252.1+/-0 | 252.3 | 0.02008 | 252.1 | 1147 | 0 | 2548 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n020_clean08_pure22 | n020_clean08_equal_total180 | 1 | 1 | 0 | 1.44e+04+/-0 | 1.44e+04 | 0.02192 | 2.88e+04 | 1060 | 0.4096 | 4.375e+05 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n020_clean08_pure41 | n020_clean08_equal_total180 | 1 | 1 | 1 | 0.7796+/-0 | 0.9205 | 0.05633 | 0.7796 | 1106 | 0 | 100 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n020_clean09_mixed11 | n020_clean09_equal_total180 | 1 | 1 | 1 | 203.9+/-0 | 203.9 | 0.01612 | 203.9 | 1147 | 0 | 2075 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n020_clean09_pure22 | n020_clean09_equal_total180 | 1 | 1 | 0 | 1.44e+04+/-0 | 1.44e+04 | 0.0187 | 2.88e+04 | 1060 | 0.4096 | 4.376e+05 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n020_clean09_pure41 | n020_clean09_equal_total180 | 1 | 1 | 1 | 0.7829+/-0 | 0.8959 | 0.05777 | 0.7829 | 1106 | 0 | 0 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n020_clean10_mixed11 | n020_clean10_equal_total180 | 1 | 1 | 1 | 212.7+/-0 | 212.8 | 0.02361 | 212.7 | 1147 | 0 | 2158 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n020_clean10_pure22 | n020_clean10_equal_total180 | 1 | 1 | 0 | 1.44e+04+/-0 | 1.44e+04 | 0.01964 | 2.88e+04 | 1060 | 0.4096 | 4.339e+05 | 1e+04 | n/a |
| Proposed | stage2_off | mode_n020_clean10_pure41 | n020_clean10_equal_total180 | 1 | 1 | 1 | 0.591+/-0 | 0.7093 | 0.04199 | 0.591 | 1106 | 0 | 100 | 1e+04 | n/a |

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
