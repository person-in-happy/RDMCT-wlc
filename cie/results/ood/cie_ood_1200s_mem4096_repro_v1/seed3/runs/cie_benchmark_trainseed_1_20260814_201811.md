# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `scip_default, adaptive_cutsel, hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[3]`
- Time limit: `1200.0 s` per run
- Schedule-stability profile: `full`
- Instances: `9`
- Empty suites: `0`

## Aggregated results

| Method | Stability | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| adaptive_cutsel | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.6352 | 1141 | 0 | 2400 | 9990 | 1.786 | 7.463e+04 | 780.2 | 1 [1, 1] |
| HEM | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.6878 | 1141 | 0.09857 | 2400 | 9990 | 1.785 | 7.47e+04 | 780.2 | 1 [1, 1] |
| HEM + Beam | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.6502 | 1141 | 0.08083 | 2400 | 9990 | 1.786 | 7.467e+04 | 780.2 | 1 [1, 1] |
| HEM + Structure | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.643 | 1141 | 0.05739 | 2400 | 9990 | 1.775 | 7.451e+04 | 780.2 | 1 [1, 1] |
| Proposed | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.6403 | 1141 | 0.1593 | 2400 | 9990 | 1.775 | 7.426e+04 | 780.2 | 1 [0.9999, 1] |
| 23D Features Only | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.5587 | 1141 | 0.05199 | 2400 | 9990 | 1.778 | 7.461e+04 | 780.2 | 1 [1, 1] |
| SCIP | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1141+/-0.5641 | 1141 | 0 | 2400 | 9990 | 1.781 | 7.432e+04 | 780.2 | 1 [1, 1] |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 9 | 9 | 1/1 | 6 | 0.6667 | 0.05073 | 0.2852 | 0.5703 |
| HEM | 9 | 9 | 1/1 | 7 | 0.7778 | 0.6609 | 0.02734 | 0.1641 |
| HEM + Beam | 9 | 9 | 1/1 | 6 | 0.6667 | 0.6073 | 0.08203 | 0.4102 |
| HEM + Structure | 9 | 9 | 1/1 | 7 | 0.7778 | 0.292 | 0.08203 | 0.4102 |
| adaptive_cutsel | 9 | 9 | 1/1 | 4 | 0.4444 | 0.6437 | 0.4551 | 0.5703 |
| 23D Features Only | 9 | 9 | 1/1 | 7 | 0.7778 | 0.4573 | 0.125 | 0.4102 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 9 | 0% | 9 | 0.006444 | 0 | n/a% |
| HEM | 9 | 0% | 9 | 0.01073 | 0 | n/a% |
| HEM + Beam | 9 | 0% | 9 | 0.01115 | 0 | n/a% |
| HEM + Structure | 9 | 0% | 9 | 0.0001363 | 0 | n/a% |
| adaptive_cutsel | 9 | 0% | 9 | 0.01159 | 0 | n/a% |
| 23D Features Only | 9 | 0% | 9 | 0.003144 | 0 | n/a% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 9 | 0.6667 | 0.05284% | 0.02952% |
| structure_with_greedy | HEM -> HEM + Structure | 9 | 0.7778 | 0.368% | 0.01933% |
| structure_with_beam | HEM + Beam -> Proposed | 9 | 0.6667 | 0.6073% | 0.1199% |
| beam_with_structure | HEM + Structure -> Proposed | 9 | 0.7778 | 0.292% | 0.03084% |

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
