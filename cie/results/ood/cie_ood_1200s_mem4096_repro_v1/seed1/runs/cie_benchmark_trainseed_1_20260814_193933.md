# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `scip_default, adaptive_cutsel, hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[1]`
- Time limit: `1200.0 s` per run
- Schedule-stability profile: `full`
- Instances: `9`
- Empty suites: `0`

## Aggregated results

| Method | Stability | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| adaptive_cutsel | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.921 | 1141 | 0 | 2400 | 9177 | 1.476 | 6.782e+04 | 710.2 | 1 [0.9998, 1] |
| HEM | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.7354 | 1141 | 0.147 | 2400 | 8546 | 1.325 | 6.356e+04 | 711.3 | 1 [0.9998, 1] |
| HEM + Beam | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.6748 | 1141 | 0.1055 | 2400 | 9223 | 1.507 | 6.875e+04 | 720.3 | 1 [1, 1] |
| HEM + Structure | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.6599 | 1141 | 0.06318 | 2400 | 9990 | 1.82 | 7.462e+04 | 780.2 | 1 [0.9998, 1] |
| Proposed | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.6297 | 1141 | 0.08856 | 2400 | 9990 | 1.82 | 7.457e+04 | 780.2 | 1 [0.9998, 1] |
| 23D Features Only | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.5673 | 1141 | 0.05018 | 2400 | 9990 | 1.819 | 7.464e+04 | 780.2 | 1 [0.9998, 1] |
| SCIP | full | cie_ood | 40_to_64_wafers | 9 | 1 | 0 | 1140+/-0.6332 | 1141 | 0 | 2400 | 9990 | 1.803 | 7.449e+04 | 780.2 | 1 [1, 1] |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 9 | 9 | 1/1 | 2 | 0.2222 | 0.03959 | 0.8086 | 1 |
| HEM | 9 | 9 | 1/1 | 4 | 0.4444 | -35.91 | 0.8203 | 1 |
| HEM + Beam | 9 | 9 | 1/1 | 3 | 0.3333 | -17.41 | 0.8496 | 1 |
| HEM + Structure | 9 | 9 | 1/1 | 4 | 0.4444 | 0.05871 | 0.4219 | 1 |
| adaptive_cutsel | 9 | 9 | 1/1 | 1 | 0.1111 | -24.93 | 0.9629 | 1 |
| 23D Features Only | 9 | 9 | 1/1 | 6 | 0.6667 | 0.1724 | 0.2129 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 9 | 0% | 9 | -0.01686 | 0 | n/a% |
| HEM | 9 | -36.55% | 9 | -0.4945 | 0 | n/a% |
| HEM + Beam | 9 | -21.25% | 9 | -0.3124 | 0 | n/a% |
| HEM + Structure | 9 | 0% | 9 | 0 | 0 | n/a% |
| adaptive_cutsel | 9 | -25.5% | 9 | -0.3441 | 0 | n/a% |
| 23D Features Only | 9 | 0% | 9 | -0.0007842 | 0 | n/a% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 9 | 0.6667 | -18.5% | 0.02847% |
| structure_with_greedy | HEM -> HEM + Structure | 9 | 0.4444 | -35.94% | -0.05923% |
| structure_with_beam | HEM + Beam -> Proposed | 9 | 0.3333 | -17.41% | -0.04888% |
| beam_with_structure | HEM + Structure -> Proposed | 9 | 0.4444 | 0.05871% | 0% |

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
