# AAAI-27 Cut-Selection Benchmark Report

This report is generated from raw per-instance, per-seed records. No missing or failed run is imputed.

## Run configuration

- Methods: `scip_default, adaptive_cutsel, hem, rdmct_feature_only, hem_beam, hem_structure, proposed`
- Seeds: `[3]`
- Time limit: `300.0 s` per run
- Instances: `20`
- Empty suites: `0`

## Aggregated results

| Method | Suite | Scale | Runs | Inc. rate | Opt. rate | Time | PAR-2 | Best obj. | Gap | PDI | Max wait | Speedup vs SCIP (95% CI) |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| adaptive_cutsel | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 0.2 | 0.2 | 2.9+/-8.95 | 482.6 | 1104 | 0 | 1275 | 7514 | 0.6682 [0.3636, 0.9727] |
| HEM | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 0.2 | 0.2 | 3.25+/-10.35 | 482.9 | 1104 | 0 | 1407 | 7514 | 0.6102 [0.2971, 0.9073] |
| HEM + Beam | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 0.2 | 0.2 | 2.85+/-9.08 | 482.7 | 1104 | 0 | 1304 | 7514 | 0.6669 [0.3312, 1.007] |
| HEM + Structure | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 0.2 | 0.2 | 3.35+/-10.72 | 483.2 | 1104 | 0 | 1596 | 7514 | 0.7839 [0.4216, 1.058] |
| Proposed | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 0.2 | 0.2 | 3.45+/-11.17 | 483.1 | 1104 | 0 | 1522 | 7514 | 0.5436 [0.2636, 0.8236] |
| 23D Features Only | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 0.2 | 0.2 | 3.6+/-11.6 | 483.1 | 1104 | 0 | 1575 | 7514 | 0.5782 [0.2532, 0.8347] |
| SCIP | cie_core_nominal | 8_to_32_wafers_nominal_processing | 20 | 0.2 | 0.2 | 3.4+/-12.08 | 483.2 | 1104 | 0 | 1596 | 7514 | 1 [1, 1] |

## Paired evidence for the proposed method

- Claim-ready gate: **NOT YET PASSED**
- Rule: For every baseline: >=10 valid pairs, mean PDI improvement >=5%, win rate >=60%, no lower incumbent rate, and Holm-adjusted p<0.05.

| Proposed vs. | All pairs | PDI pairs | Base/Prop incumbent rate | Wins | Win rate | Mean PDI improvement | Wilcoxon p | Holm p |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 20 | 4 | 0.2/0.2 | 1 | 0.25 | -1.228 | n/a | n/a |
| HEM | 20 | 4 | 0.2/0.2 | 2 | 0.5 | 1.093 | n/a | n/a |
| HEM + Beam | 20 | 4 | 0.2/0.2 | 2 | 0.5 | -0.6151 | n/a | n/a |
| HEM + Structure | 20 | 4 | 0.2/0.2 | 1 | 0.25 | 10.82 | n/a | n/a |
| adaptive_cutsel | 20 | 4 | 0.2/0.2 | 1 | 0.25 | 15.41 | n/a | n/a |
| 23D Features Only | 20 | 4 | 0.2/0.2 | 1 | 0.25 | 1.381 | n/a | n/a |

## Paired secondary effects

Positive objective/time improvement and positive absolute gap reduction favor Proposed.

| Proposed vs. | Objective pairs | Mean objective improvement | Gap pairs | Mean absolute gap reduction | Both-optimal time pairs | Mean time improvement |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SCIP | 4 | 0% | 4 | 0 | 3 | -1.235% |
| HEM | 4 | 0% | 4 | 0 | 3 | 16.8% |
| HEM + Beam | 4 | 0% | 4 | 0 | 4 | 8.523% |
| HEM + Structure | 4 | 0% | 4 | 0 | 3 | 10.83% |
| adaptive_cutsel | 4 | 0% | 4 | 0 | 4 | -9.028% |
| 23D Features Only | 4 | 0% | 4 | 0 | 3 | 1.282% |

## Controlled module effects (PDI)

Each row changes one module while holding the paired checkpoint family and decode setting fixed where applicable.

| Effect | Baseline -> Target | Pairs | Win rate | Mean improvement | Median improvement |
| --- | --- | ---: | ---: | ---: | ---: |
| beam_without_structure | HEM -> HEM + Beam | 3 | 0.3333 | 0.725% | 0% |
| structure_with_greedy | HEM -> HEM + Structure | 3 | 0.3333 | -19.06% | -1.82% |
| structure_with_beam | HEM + Beam -> Proposed | 4 | 0.5 | -0.6151% | 4.545% |
| beam_with_structure | HEM + Structure -> Proposed | 3 | 0.3333 | 10.82% | 0% |

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
