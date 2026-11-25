"""Format the complete certified grid for the manuscript."""
from itertools import product
from verify_table import CASES,SIXTEEN,g,new_cells


def number(val):
    exact=round(val*256)/256
    if abs(val-exact)<2e-5:
        val=exact
    return f"{val:.6f}".rstrip("0").rstrip(".")


def render(grid):
    labels=(r"$4\times1$",r"$2\times2$","混合")
    rows=[]
    for case_index,case in enumerate(CASES):
        scale=case_index//3
        mode=case_index%3
        for j,(ga,tag) in enumerate(zip(g.LEVELS,("10","1","0.01"))):
            cells=[grid[case,ga,gb] for gb in g.LEVELS]
            assert len({r["primary_schedule_sha256"] for r in cells})==1
            size=r"\multirow{9}{*}{"+str((2,4,8,16)[scale])+"}" if mode==j==0 else ""
            recipe=r"\multirow{3}{*}{"+labels[mode]+"}" if j==0 else ""
            vals=[cells[0]["f_A"],*(r["f_B"] for r in cells)]
            end=r"\\\midrule" if mode==2 and j==2 and scale<3 else r"\\"
            rows.append(" & ".join([size,recipe,tag,*map(number,vals)])+end)
    return "\n".join(rows)


if __name__=="__main__":
    grid=g.get_grid()|new_cells()
    assert set(grid)==set(product(CASES,g.LEVELS,g.LEVELS))
    print(render(grid))
