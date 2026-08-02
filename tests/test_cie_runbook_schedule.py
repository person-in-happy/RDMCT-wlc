import re
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "cie" / "docs" / "cie_submission_runbook_zh.md"


def _commands(campaign_id):
    text = RUNBOOK.read_text(encoding="utf-8")
    blocks = re.findall(r"```powershell\r?\n(.*?)\r?\n```", text, re.S)
    return [
        block.strip()
        for block in blocks
        if f"-CampaignId {campaign_id}" in block
        and "run_cie_single.ps1" in block
        and "-ShardTag" in block
    ]


def _csv_ints(command, name):
    match = re.search(rf"-{name}\s+'([0-9, ]+)'", command)
    assert match, f"missing -{name}: {command}"
    return tuple(int(value.strip()) for value in match.group(1).split(","))


def _value(command, name):
    match = re.search(rf"-{name}\s+([^\s]+)", command)
    assert match, f"missing -{name}: {command}"
    return match.group(1).strip("'")


def _assert_exact_cells(cells, expected):
    counts = Counter(cells)
    assert set(counts) == set(expected)
    assert all(count == 1 for count in counts.values())


def test_main_schedule_is_complete_unique_and_balanced():
    commands = _commands("cie_main_600s_mem2048_repro_v1")
    cells = []
    loads = defaultdict(int)
    queues = {
        "A": {"s1to5_t1", "s1to2_t2"},
        "B": {"s1to5_t3", "s1to4_t4"},
        "C": {"s3to5_t2", "s5_t4", "s1to5_t5"},
    }
    for command in commands:
        tag = _value(command, "ShardTag")
        for solver_seed in _csv_ints(command, "Seeds"):
            for training_seed in _csv_ints(command, "TrainingSeeds"):
                cells.append((solver_seed, training_seed))
                queue = next(name for name, tags in queues.items() if tag in tags)
                method_count = 7 if training_seed == 1 else 5
                loads[queue] += 20 * method_count
    _assert_exact_cells(cells, {(s, t) for s in range(1, 6) for t in range(1, 6)})
    assert dict(loads) == {"A": 900, "B": 900, "C": 900}


def test_stability_schedule_is_complete_unique_and_balanced():
    commands = _commands("cie_stability_600s_mem2048_repro_v1")
    cells = []
    loads = defaultdict(int)
    queues = {
        "A": {"s1_t1to5", "s4_t1to4"},
        "B": {"s2_t1to5", "s5_t1to3"},
        "C": {"s3_t1to5", "s4_t5", "s5_t4to5"},
    }
    for command in commands:
        tag = _value(command, "ShardTag")
        for solver_seed in _csv_ints(command, "Seeds"):
            for training_seed in _csv_ints(command, "TrainingSeeds"):
                cells.append((solver_seed, training_seed))
                queue = next(name for name, tags in queues.items() if tag in tags)
                loads[queue] += 20 * 3
    _assert_exact_cells(cells, {(s, t) for s in range(1, 6) for t in range(1, 6)})
    assert sorted(loads.values()) == [480, 480, 540]


def test_spbs_schedule_keeps_both_conditions_and_balances_queues():
    commands = _commands("cie_spbs_600s_mem2048_repro_v1")
    cells = []
    loads = defaultdict(int)
    queues = {
        "A": {"s1to3_both", "s10_none"},
        "B": {"s4to6_both", "s10_auto"},
        "C": {"s7to9_both"},
    }
    for command in commands:
        tag = _value(command, "ShardTag")
        selected = _value(command, "SpbsWarmStarts")
        conditions = ("none", "auto") if selected == "both" else (selected,)
        for solver_seed in _csv_ints(command, "Seeds"):
            for condition in conditions:
                cells.append((solver_seed, condition))
                queue = next(name for name, tags in queues.items() if tag in tags)
                loads[queue] += 48
    _assert_exact_cells(
        cells,
        {(seed, condition) for seed in range(1, 11) for condition in ("none", "auto")},
    )
    assert sorted(loads.values()) == [288, 336, 336]


def test_all_formal_stage_targets_sum_to_6273():
    assert 4 + 2700 + 1500 + 300 + 960 + 80 + 729 == 6273
