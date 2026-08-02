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
| HEM | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 205.8+/-258.3 | 206 | 0.04281 | 355.9 | 2195 | 0.2569 | 7089 | 9475 | n/a |
| HEM + Beam | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 205.7+/-258.2 | 205.7 | 0.04694 | 355.6 | 2195 | 0.2569 | 7066 | 9475 | n/a |
| HEM + Structure | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 207.8+/-259.8 | 207.8 | 0.0311 | 357.8 | 2195 | 0.257 | 7245 | 9475 | n/a |
| Proposed | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 207.2+/-259.5 | 207.3 | 0.05044 | 357.1 | 2195 | 0.257 | 7242 | 9475 | n/a |
| 23D Features Only | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 1 | 0.75 | 217.9+/-276.3 | 218.1 | 0.04315 | 367.9 | 2183 | 0.244 | 7126 | 9503 | n/a |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 20 | 20 | 1/1 | 5 | 0.25 | 4.251 | 0.5693 | 1 |
| HEM + Beam | 20 | 20 | 1/1 | 5 | 0.25 | 3.602 | 0.7466 | 1 |
| HEM + Structure | 20 | 20 | 1/1 | 6 | 0.3 | 16.99 | 0.3649 | 1 |
| 23D Features Only | 20 | 20 | 1/1 | 6 | 0.3 | -14.4 | 0.8187 | 1 |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HEM | 20 | 0% | 20 | -0.0001635 | 10 | 18.07% |
| HEM + Beam | 20 | 0% | 20 | -0.0001635 | 10 | 18.02% |
| HEM + Structure | 20 | 0% | 20 | 0 | 12 | 24.09% |
| 23D Features Only | 20 | -0.4101% | 20 | -0.01302 | 10 | -27.73% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 15 | 0.4667 | 7.332% | 0% |
| structure_with_greedy | HEM -> HEM + Structure | 15 | 0.4667 | 1.51% | 0% |
| structure_with_beam | HEM + Beam -> Proposed | 15 | 0.3333 | 3.602% | 0% |
| beam_with_structure | HEM + Structure -> Proposed | 17 | 0.3529 | 16.99% | 0% |

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
