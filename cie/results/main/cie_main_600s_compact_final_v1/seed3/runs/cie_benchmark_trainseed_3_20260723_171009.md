# CIE Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[3]`
- Time limit: `600.0 s` per run
- Instances: `20`
- Empty suites: `0`

## Aggregated results

| Method | Suite | Scale | Runs | Inc. rate | Opt. rate | SCIP time | End-to-end | Callback | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 225.2+/-267.5 | 225.3 | 0.04681 | 375.1 | 2195 | 0.2567 | 7429 | 9475 | n/a |
| HEM + Beam | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 224.6+/-266.9 | 224.5 | 0.05464 | 374.6 | 2195 | 0.2566 | 7445 | 9475 | n/a |
| HEM + Structure | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 226.5+/-269.8 | 226.7 | 0.03547 | 376.5 | 2195 | 0.2572 | 7643 | 9475 | n/a |
| Proposed | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 227.3+/-270.3 | 227.5 | 0.05629 | 377.4 | 2195 | 0.2572 | 7666 | 9475 | n/a |
| 23D Features Only | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.65 | 230.9+/-283.7 | 230.9 | 0.04758 | 440.9 | 2215 | 0.264 | 8110 | 9503 | n/a |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 20 | 20 | 1/1 | 4 | 0.2 | 2.766 | 0.8059 | 1 |
| HEM + Beam | 20 | 20 | 1/1 | 8 | 0.4 | 13.5 | 0.3189 | 1 |
| HEM + Structure | 20 | 20 | 1/1 | 6 | 0.3 | 0.8721 | 0.8835 | 1 |
| 23D Features Only | 20 | 20 | 1/1 | 9 | 0.45 | 19.67 | 0.3096 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 20 | -6.543e-14% | 20 | -0.0005055 | 10 | 14.86% |
| HEM + Beam | 20 | -1.091e-14% | 20 | -0.000587 | 12 | 22.44% |
| HEM + Structure | 20 | 0% | 20 | 0 | 10 | 8.311% |
| 23D Features Only | 20 | 0.7292% | 20 | 0.006765 | 9 | 15.01% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 15 | 0.3333 | 0.0282% | 0% |
| structure_with_greedy | HEM -> HEM + Structure | 15 | 0.4667 | 6.1% | 0% |
| structure_with_beam | HEM + Beam -> Proposed | 17 | 0.4706 | 13.5% | 0% |
| beam_with_structure | HEM + Structure -> Proposed | 15 | 0.4 | 0.8721% | -0.00288% |

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
