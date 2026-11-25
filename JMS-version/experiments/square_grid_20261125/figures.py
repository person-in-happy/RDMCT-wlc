"""Export each verified squared-objective Gantt chart at its existing single-column dimensions."""
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

from grid import JMS,R,OUT,read,digest,metrics,rel,rows,atom
sys.path.insert(0,str(JMS/"tools"))
import render_huber_gantt_cn as gantt


def main():
    old=R/"gantt_huber_comparison_20261125"
    refs={r["summary"]["n"]:r for r in read(old/"comparison.json") if r["summary"]["variant"]=="huber"}
    grid=rows(OUT/"threshold_cells.csv")
    four,=[r for r in grid if r["case"]=="pure" and r["gA"]==r["gB"]=="0p01pct"]
    four_cell=read(JMS/four["cell"])
    assert four["primary_schedule_sha256"]==refs[4]["summary"]["source_sha256"]
    sixteen=read(OUT/"gantt16/result.json")
    assert sixteen["eligible"] and sixteen["replay"]["valid"] and sixteen["record"]["gap"]==0
    seventy_five=read(OUT/"gantt75/square.json")
    details={
        4:(JMS/four["cell"],four_cell["B_lower"]),
        16:(OUT/"gantt16/result.json",sixteen["record"]["lower"]),
        75:(OUT/"gantt75/square.json",seventy_five["lower"])
    }
    output=JMS/"figures/square_gantt_20261125";output.mkdir(exist_ok=True)
    os.environ["SOURCE_DATE_EPOCH"]="0"
    gantt.plt.rcParams.update({"font.sans-serif":["Microsoft YaHei","SimHei","DejaVu Sans"],
                               "axes.unicode_minus":False,"pdf.fonttype":42})
    catalogue=[]
    for n,record in refs.items():
        schedule=JMS/record["summary"]["source"]
        native=JMS/record["summary"]["certificate"]
        assert digest(schedule)==record["summary"]["source_sha256"] and digest(native)==record["summary"]["certificate_sha256"]
        proof,lower=details[n]
        initial=next(r for r in read(old/"comparison.json") if r["summary"]["n"]==n and r["summary"]["variant"]=="old")
        before=metrics(read(JMS/initial["summary"]["source"]));score=metrics(read(schedule))
        assert abs(score["secondary"]-lower)<1e-5
        record["summary"].update(certificate=rel(proof),certificate_sha256=digest(proof),secondary=score["secondary"])
        with tempfile.TemporaryDirectory(dir=output) as path:
            scratch=Path(path)
            with patch.object(gantt,"OUTPUT",scratch):chart=gantt.draw(record)
            name=f"fig_schedule_n{n}_square_cn.pdf"
            (scratch/chart["chart"]).replace(output/name)
        chart.update(chart=name,metrics=score,prior_metrics=before,lower=lower,
                     native=rel(native),native_sha256=digest(native))
        assert digest(output/name)==chart["chart_sha256"]
        catalogue.append(chart)
    atom(output/"manifest.json",catalogue)

if __name__=="__main__":main()
