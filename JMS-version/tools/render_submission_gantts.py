"""Draw the three publication Gantt charts from validated schedule events."""
import json
import math
import os
from pathlib import Path
import shutil
import sys

import render_submission_figures_en as english
from current_defaults_swimlane import build
from render_huber_gantt_cn import LEGEND_LABELS, draw, plt, read, sha

PAPER = Path(__file__).resolve().parents[1]
EXPERIMENT = PAPER / "results/chamber_wait_20261126"
OUTPUT = PAPER / "figures/gantt_20261126"
SCHEDULES = {
    4: EXPERIMENT / "holding_tiebreak/n4/schedule.json",
    16: EXPERIMENT / "holding_tiebreak/n16/schedule.json",
    75: EXPERIMENT / "n75_first_parallel_sync/result.json",
}
sys.path.insert(0, str(PAPER / "experiments/square_residence_20261125"))
from score import metrics

LABELS = LEGEND_LABELS | {
    "ATR取片": "ATR取出", "ATR放片": "ATR放入", "VTR取放": "VTR取出/放入",
    "承片等待": "持片等待", "腔室加工": "工艺加工",
}


def render_schedule(n, source):
    certificate = source.with_name("evidence.json")
    proof = read(certificate)
    data = read(source)
    assert sha(source) == proof["schedule_sha256"]
    assert proof["original_rows_valid"] and proof["physical_validation"]["valid"]
    assert n == sum(w["product"] for w in data["jobs"])
    # build checks coverage of every explicit event and overlap on each display lane.
    _, bars, _, _ = build(data)
    measured = metrics(data)
    release = max(bar["end"] for bar in bars)
    for key, value in (("cmax", measured["cmax"]), ("secondary", measured["secondary"]),
                       ("equipment_release", release)):
        assert math.isclose(value, proof["after"][key], abs_tol=1e-5), (n, key, value)
    summary = {
        "n": n, "source": source.relative_to(PAPER).as_posix(), "source_sha256": sha(source),
        "certificate": certificate.relative_to(PAPER).as_posix(), "certificate_sha256": sha(certificate),
        "cmax": measured["cmax"], "equipment_end": release, "secondary": measured["secondary"],
    }
    record = {"summary": summary, "replay": proof["physical_validation"], "display": {"intervals": len(bars)}}
    target = OUTPUT / f"fig_schedule_n{n}_square_cn.pdf"
    result = draw(record, target=target, legend_labels=LABELS, terminal_labels=("末片回片", "设备释放"))
    result["metrics"] = measured
    return result


def main():
    os.environ["SOURCE_DATE_EPOCH"] = "0"
    plt.rcParams.update({"font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                         "axes.unicode_minus": False, "pdf.fonttype": 42})
    OUTPUT.mkdir(exist_ok=True)
    charts = [render_schedule(n, source) for n, source in SCHEDULES.items()]
    (OUTPUT / "manifest.json").write_text(json.dumps(charts, ensure_ascii=False, indent=2) + "\n", "utf-8")
    english_manifest = english.OUTPUT / "manifest.json"
    if not english_manifest.exists():
        english.main()
    else:
        # The other figures have separate sources, including a native English Pareto plot.
        figures = {}
        schedules = {}
        artifacts = {}
        for number, chart in enumerate(charts, 7):
            figures[number] = english.render(number, OUTPUT / chart["chart"], english.LANES | english.ACTIONS)
            assert figures[number]["source_sha256"] == chart["chart_sha256"]
            schedules[chart["n"]] = {key: chart[key] for key in (
                "n", "source", "source_sha256", "certificate", "certificate_sha256", "intervals",
                "events", "cmax", "equipment_end", "secondary")}
            schedules[chart["n"]].update(figure=number, intervals_unchanged=True,
                                          legend_columns=4, single_column=True)
            for suffix in ("pdf", "png", "svg"):
                asset = english.OUTPUT / f"Figure{number}.{suffix}"
                artifacts[asset.name] = sha(asset)
        manifest = read(english_manifest)
        manifest["figures"] = [figures.get(item["figure"], item) for item in manifest["figures"]]
        manifest["schedules"] = [schedules.get(item["n"], item) for item in manifest["schedules"]]
        manifest["artifacts"].update(artifacts)
        english_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    cie = PAPER.parent / "cie/products/figures_current"
    for number, chart in enumerate(charts, 7):
        for source in (OUTPUT / chart["chart"], english.OUTPUT / f"Figure{number}.pdf"):
            shutil.copyfile(source, cie / source.name)


if __name__ == "__main__":
    main()
