# Equal-total-time mode/cleaning crossover

- Recipe convention: `4x1=180 s`; `2x2=90+90 s`.
- Modes: pure 4x1, pure 2x2, and 1:1 mixed; for odd N, 4x1 receives the extra product wafer.
- Required bridge exchange: `4 s` when combined.
- Cmax cutoff: last product-wafer return to LP; terminal cleaning with no later process is excluded.
- Exact certificate set complete: `False`.

## Clean3 and clean10

| Wafers | Cleaning interval | Cmax 4x1 | Cmax 2x2 | Cmax mixed | Best of three | Pure-mode winner |
| ---: | ---: | ---: | ---: | ---: | --- | --- |
| 8 | 3 | 610 | 578 | 654 | 2x2 | 2x2 |

## Switches

| Wafers | Last 4x1 win | First 2x2 win | Observed switches |
| ---: | ---: | ---: | --- |
| 8 | None | 3 |  |
| 16 | None | None |  |

## Incomplete/invalid cells

- (16, 3, 'pure22'): non-certificate row status=timelimit, gap=0.9857707516996058, physical=True, product-return-Cmax=True
- n=16, clean=3: missing one or more exact three-mode cells
