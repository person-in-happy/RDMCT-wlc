# Final AAAI Ablation Execution

## Method Matrix

| Method | Checkpoint | Features | High-level policy | Decode | Structure rerank |
| --- | --- | ---: | --- | --- | --- |
| SCIP | none | native | no | native | no |
| HEM | independently trained HEM | 13 | yes | greedy | no |
| HEM + Beam | exact same HEM checkpoint | 13 | yes | beam search | no |
| HEM + Structure | exact same Proposed checkpoint | 23 | yes | greedy | role-submodular |
| Proposed | independently trained proposed | 23 | yes | beam search | role-submodular |

HEM and HEM + Beam share the exact checkpoint, while HEM + Structure and Proposed
share their exact checkpoint. The resulting 2x2 design isolates structure-aware
selection and beam decoding, including their interaction on cleaning-heavy instances.
The optional feature-only checkpoint can separately diagnose the 23-dimensional
representation without role-submodular completion. All methods receive the same instance,
SCIP seed, warm start, memory cap, and solve time for each paired run.

## Training

Run five independent training seeds:

```powershell
.\aaai\run_aaai.ps1 -Stage train-hem -Seeds '1,2,3,4,5'
.\aaai\run_aaai.ps1 -Stage train-proposed -Seeds '1,2,3,4,5'
```

HEM and Proposed use the same submodular Petri training split and matched
epoch, sample, SCIP-time, memory, and optimizer budgets.

## Final Benchmark

```powershell
.\aaai\run_aaai.ps1 -Stage benchmark-all -Seeds '1,2,3,4,5' -TimeLimit 600 `
  -Suites 'petri_large,petri_wafer100_stress'
```

The standard per-run limit is 600 seconds. The manifest gives the held-out
100-wafer stress instance 3600 seconds for every method. Do not lower one
baseline's budget or add Proposed-only schedule postprocessing.

Outputs are written under:

```text
aaai/results/final_benchmark/petri_ablation_<timestamp>/runs
aaai/results/final_benchmark/petri_ablation_<timestamp>/combined
```

The raw CSV contains time, nodes, gap, primal-dual integral, total schedule
wait, maximum individual wait, cadence coefficient of variation, and cadence
deviation. The combined report applies paired one-sided Wilcoxon tests with
Holm correction.

## Metric Interpretation

All four headline metrics are lower-is-better for the minimization problems:

| Metric | What it measures | Valid advantage claim |
| --- | --- | --- |
| Mean solving time | Wall-clock cost | Faster only when solve status and solution quality are comparable; use PAR-2 when timeouts occur. |
| Mean best objective | Quality of the best feasible incumbent | Lower makespan/cost; report incumbent rate to prevent missing-solution selection bias. |
| Mean primal-dual gap | Remaining distance between incumbent and certified bound | Lower means a stronger optimality certificate; zero means proven optimal. |
| Mean primal-dual integral | Area of the primal-dual gap over time | Lower means better anytime progress and is the primary paired metric for timeout-heavy tests. |

Mean node count is diagnostic rather than monotone: fewer nodes may indicate an
efficient search, but it may also mean the solver stalled at the root. It cannot
prove superiority without objective, gap, PDI, and status evidence.

## Claim Gate

Do not state that Proposed is superior until every reported baseline has at
least 10 valid paired runs, mean PDI improvement of at least 5%, win rate of at
least 60%, and Holm-adjusted p-value below 0.05. Report timeout-aware gap and
PDI alongside speedup, and treat the 100-wafer result as a stress case rather
than the sole statistical basis for the paper claim.

## 100-Wafer Schedule Figure

The formal schedule configuration reserves 10800 seconds for makespan and 3600
seconds for linear schedule stabilization. Phase two fixes makespan and every
discrete decision, then minimizes total wait, maximum individual wait, and
within-cleaning-epoch cadence deviation. This figure is a schedule-quality case
study and is separate from the equal-budget cut-selection ablation.
