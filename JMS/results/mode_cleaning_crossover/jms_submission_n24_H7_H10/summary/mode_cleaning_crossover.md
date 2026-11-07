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
| 24 | None | None |  |

## Incomplete/invalid cells

- (24, 7, 'pure22'): non-certificate row status=timelimit, gap=0.8679775280898973, physical=True, product-return-Cmax=True
- (24, 7, 'mixed11'): non-certificate row status=timelimit, gap=0.06202208920985547, physical=True, product-return-Cmax=True
- (24, 8, 'pure22'): non-certificate row status=timelimit, gap=0.4691211401425178, physical=True, product-return-Cmax=True
- (24, 8, 'mixed11'): non-certificate row status=timelimit, gap=0.06202208920985547, physical=True, product-return-Cmax=True
- (24, 9, 'pure22'): non-certificate row status=timelimit, gap=0.4691211401425178, physical=True, product-return-Cmax=True
- (24, 9, 'mixed11'): non-certificate row status=timelimit, gap=0.06202208920985547, physical=True, product-return-Cmax=True
- (24, 10, 'pure22'): non-certificate row status=timelimit, gap=0.46912113895486923, physical=True, product-return-Cmax=True
- (24, 10, 'mixed11'): non-certificate row status=timelimit, gap=0.06202208920985547, physical=True, product-return-Cmax=True
- n=24, clean=7: missing one or more exact three-mode cells
- n=24, clean=8: missing one or more exact three-mode cells
- n=24, clean=9: missing one or more exact three-mode cells
- n=24, clean=10: missing one or more exact three-mode cells
