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

- (24, 3, 'pure22'): seed pairs [] != [(1, 1)]
- (24, 3, 'pure22'): expected 1 rows, found 0 (missing or duplicate seed cell)
- (24, 3, 'mixed11'): non-certificate row status=timelimit, gap=0.009556903996525114, physical=True, product-return-Cmax=True
- (24, 4, 'pure22'): non-certificate row status=timelimit, gap=1.1818181818181819, physical=True, product-return-Cmax=True
- (24, 4, 'mixed11'): non-certificate row status=timelimit, gap=0.02987594983088591, physical=True, product-return-Cmax=True
- (24, 5, 'pure22'): non-certificate row status=timelimit, gap=0.2284722222222184, physical=True, product-return-Cmax=True
- (24, 5, 'mixed11'): Combined bridge 2_5 is not one 4.0s four-gripper exchange: D:\git\git\RDMCT-A3C\JMS\results\mode_cleaning_crossover\jms_submission_n24_H3_H6\solutions\mode_n024_clean05_mixed1__mode_n024_clean05_mixed11_equal___proposed__s1_t1__948d8bf760f486ff.sol
- (24, 6, 'pure22'): non-certificate row status=timelimit, gap=0.3055555555555557, physical=True, product-return-Cmax=True
- (24, 6, 'mixed11'): non-certificate row status=timelimit, gap=0.10402097814685266, physical=True, product-return-Cmax=True
- n=24, clean=3: missing one or more exact three-mode cells
- n=24, clean=4: missing one or more exact three-mode cells
- n=24, clean=5: missing one or more exact three-mode cells
- n=24, clean=6: missing one or more exact three-mode cells
