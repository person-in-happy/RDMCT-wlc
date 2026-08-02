# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `scip_default, adaptive_cutsel, hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[3]`
- Time limit: `1200.0 s` per run
- Instances: `9`
- Empty suites: `0`

## Aggregated results

| Method | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| adaptive_cutsel | cie_ood | 40_to_64_wafers | 9 | 0.3333 | 0 | 1200+/-0 | 400.1 | 0 | 2400 | 8938 | 2.031 | 7.717e+04 | 9470 | 1 [1, 1] |
| HEM | cie_ood | 40_to_64_wafers | 9 | 0.3333 | 0 | 1200+/-0 | 400 | 0.05486 | 2400 | 8242 | 1.834 | 7.028e+04 | 1e+04 | 1 [1, 1] |
| HEM + Beam | cie_ood | 40_to_64_wafers | 9 | 0.4444 | 0 | 1200+/-0 | 533.4 | 0.054 | 2400 | 7552 | 1.473 | 6.109e+04 | 9242 | 1 [1, 1] |
| HEM + Structure | cie_ood | 40_to_64_wafers | 9 | 0.4444 | 0 | 1200+/-0 | 533.3 | 0.05192 | 2400 | 7522 | 1.45 | 6.233e+04 | 9242 | 1 [1, 1] |
| Proposed | cie_ood | 40_to_64_wafers | 9 | 0.3333 | 0 | 1200+/-0 | 405.6 | 0.03208 | 2400 | 8203 | 1.811 | 7.148e+04 | 1e+04 | 1 [1, 1] |
| 23D Features Only | cie_ood | 40_to_64_wafers | 9 | 0.4444 | 0 | 1200+/-0 | 533.4 | 0.03639 | 2400 | 7510 | 1.46 | 6.587e+04 | 9242 | 1 [1, 1] |
| SCIP | cie_ood | 40_to_64_wafers | 9 | 0.3333 | 0 | 1200+/-0 | 464 | 0 | 2400 | 8270 | 1.849 | 6.926e+04 | 1e+04 | 1 [1, 1] |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 3 | 3 | 1/1 | 1 | 0.3333 | -7.336 | n/a | n/a |
| HEM | 3 | 3 | 1/1 | 1 | 0.3333 | -3.488 | n/a | n/a |
| HEM + Beam | 3 | 3 | 1/1 | 1 | 0.3333 | -3.369 | n/a | n/a |
| HEM + Structure | 3 | 3 | 1/1 | 2 | 0.6667 | -0.03535 | n/a | n/a |
| adaptive_cutsel | 3 | 3 | 1/1 | 2 | 0.6667 | 10.29 | n/a | n/a |
| 23D Features Only | 3 | 3 | 1/1 | 2 | 0.6667 | 9.773 | n/a | n/a |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 3 | 1.41% | 3 | 0.03711 | 0 | n/a% |
| HEM | 3 | 0.8387% | 3 | 0.02266 | 0 | n/a% |
| HEM + Beam | 3 | 0.8387% | 3 | 0.03328 | 0 | n/a% |
| HEM + Structure | 3 | 0% | 3 | 0 | 0 | n/a% |
| adaptive_cutsel | 3 | 10.85% | 3 | 0.2191 | 0 | n/a% |
| 23D Features Only | 3 | -0.3537% | 3 | 0.01607 | 0 | n/a% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 3 | 0.3333 | -0.1097% | -0.08976% |
| structure_with_greedy | HEM -> HEM + Structure | 3 | 0 | -3.444% | -0.05739% |
| structure_with_beam | HEM + Beam -> Proposed | 3 | 0.3333 | -3.369% | -0.06816% |
| beam_with_structure | HEM + Structure -> Proposed | 3 | 0.6667 | -0.03535% | 0.00364% |

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
