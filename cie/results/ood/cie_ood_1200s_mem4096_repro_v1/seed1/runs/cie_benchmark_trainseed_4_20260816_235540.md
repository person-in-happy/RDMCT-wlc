# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[1]`
- Time limit: `1200.0 s` per run
- Schedule-stability profile: `full`
- Instances: `9`
- Empty suites: `0`

## Aggregated results

| Method | Stability | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1141+/-0.6756 | 1141 | 0.1014 | 2400 | 9332 | 1.64 | 7.12e+04 | 766.6 | n/a |
| HEM + Beam | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.7377 | 1141 | 0.09215 | 2400 | 9332 | 1.641 | 7.132e+04 | 766.6 | n/a |
| HEM + Structure | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-1.247 | 1141 | 0.09334 | 2400 | 9228 | 1.511 | 6.934e+04 | 737.7 | n/a |
| Proposed | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.8202 | 1141 | 0.1059 | 2400 | 9221 | 1.508 | 7.052e+04 | 737.7 | n/a |
| 23D Features Only | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.865 | 1141 | 0.06313 | 2400 | 9232 | 1.515 | 7.301e+04 | 737.7 | n/a |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 9 | 9 | 1/1 | 7 | 0.7778 | -8.519 | 0.2129 | 0.6387 |
| HEM + Beam | 9 | 9 | 1/1 | 5 | 0.5556 | -8.264 | 0.3262 | 0.6523 |
| HEM + Structure | 9 | 9 | 1/1 | 4 | 0.4444 | -1.319 | 0.8203 | 0.8203 |
| 23D Features Only | 9 | 9 | 1/1 | 9 | 1 | 4.193 | 0.001953 | 0.007812 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 9 | -7.018% | 9 | 0.1323 | 0 | n/a% |
| HEM + Beam | 9 | -7.018% | 9 | 0.1333 | 0 | n/a% |
| HEM + Structure | 9 | 0.1765% | 9 | 0.002833 | 0 | n/a% |
| 23D Features Only | 9 | 0.2773% | 9 | 0.006831 | 0 | n/a% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 9 | 0.5556 | -0.1565% | 0.03348% |
| structure_with_greedy | HEM -> HEM + Structure | 9 | 0.7778 | -7.266% | 1.12% |
| structure_with_beam | HEM + Beam -> Proposed | 9 | 0.5556 | -8.264% | 0.09839% |
| beam_with_structure | HEM + Structure -> Proposed | 9 | 0.4444 | -1.319% | -0.002698% |

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
