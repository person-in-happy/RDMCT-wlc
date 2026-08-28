# JMS 50-wafer supplementary Gantt evidence

Generated and independently validated on 2026-08-25 with the `a3cenv`
environment. The three frozen models share the wafer17 timing/device parameters
and differ only in the product recipe counts.

## Frozen policy and solve protocol

- method: 23D Proposed hierarchical cut selector
- training seed / solver seed: 1 / 1
- decode/postprocessing: beam search (beam size 3) + structure rerank
- candidate/selected-cut cap: 128/16
- total SCIP budget per instance: 1200 s; phase 2 reserves at most 60 s
- checkpoint SHA-256: `23961d2d9f09473982a79271642fca1d6e76cd0bf3837240d5e38a2361d824ce`
- complete command: [`../../run_wafer50_gantt_evidence.ps1`](../../run_wafer50_gantt_evidence.ps1)

## Results

| Configuration | Counts 4x1/2x2 | Primary status | Cmax (s) | Gap | Feasible WPH | Independent check |
| --- | ---: | --- | ---: | ---: | ---: | --- |
| pure 2x2 | 0/50 | timelimit | 5944.0000019 | 0.7359813 | 30.2826 | pass |
| pure 4x1 | 50/0 | optimal | 2298.0000010 | 0 | 78.3290 | pass |
| 1:1 mixed | 25/25 | timelimit | 5794.0000000 | 0.6976267 | 31.0666 | pass |

The pure-2x2 and mixed values are feasible incumbents, not proven optima. Their
WPH values are therefore achieved schedule rates, not upper bounds on achievable
throughput. Pure-4x1 is the only configuration proven optimal in this run.

## Evidence files

- raw benchmark: [`runs/cie_benchmark_wafer50_gantt_20260825_20260825_160801.json`](runs/cie_benchmark_wafer50_gantt_20260825_20260825_160801.json)
- batch validation report: [`validation/cie_manufacturing_metrics.md`](validation/cie_manufacturing_metrics.md) (`3` solutions, `0` invalid)
- pure-2x2 charts: [`gantt/wafer50_22_20260825/index.html`](gantt/wafer50_22_20260825/index.html)
- pure-4x1 charts: [`gantt/wafer50_41_20260825/index.html`](gantt/wafer50_41_20260825/index.html)
- 1:1 mixed charts: [`gantt/wafer50_mix_25_25_20260825/index.html`](gantt/wafer50_mix_25_25_20260825/index.html)

All saved `.sol` files were reloaded against the corresponding serialized LP
and checked by SCIP with feasibility tolerance `1.000001e-6`. These three charts
are schedule-feasibility evidence. A single training/solver seed is not a
statistical algorithm comparison and must not be presented as one.
