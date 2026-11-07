# Equal-total-time mode/cleaning crossover

- Recipe convention: `4x1=180 s`; `2x2=90+90 s`.
- Modes: pure 4x1, pure 2x2, and 1:1 mixed; for odd N, 4x1 receives the extra product wafer.
- Required bridge exchange: `4 s` when combined.
- Cmax cutoff: last product-wafer return to LP; terminal cleaning with no later process is excluded.
- Exact certificate set complete: `False`.

## Clean3 and clean10

| Wafers | Cleaning interval | Cmax 4x1 | Cmax 2x2 | Cmax mixed | Best of three | Pure-mode winner |
| ---: | ---: | ---: | ---: | ---: | --- | --- |

## Switches

| Wafers | Last 4x1 win | First 2x2 win | Observed switches |
| ---: | ---: | ---: | --- |
| 8 | None | 4 |  |
| 16 | 4 | 6 | 4:4x1 -> 6:2x2 |

## Incomplete/invalid cells

- (16, 5, 'pure22'): non-certificate row status=timelimit, gap=0.3975346687211094, physical=True, product-return-Cmax=True
- n=16, clean=5: missing one or more exact three-mode cells
